# -*- coding: utf-8 -*-
"""evo_bridge —— graph.json ⇄ EvoOntology workspace 双向桥接（零 LLM）。

## 为什么

知识处理专家产出 `graph.json`（八类节点）；EvoOntology 用五类记录
（terms/mappings/relations/constraints/evidence）。两者格式不同、工具不同，
不通就无法「融为一体」。

## 对齐本机「调整版」（1.1.0 + 本地改动）

本机 EvoOntology 已由使用者扩展，**关系类型从 5 种扩到 11 种**：

    受控 5 种：association / hierarchy / composition / equivalence / derivation

    扩展 6 种（本地 renderer.py 支持，validate() 不校验取值）：
      reasoning   claim ← 由 guard/gate 推导
      reuse       claim ← 复用报告规则/指标/限值
      citation    clause/claim ← 引用标准或条款
      has_limit   metric ← 挂报告限值
      tests       gate ← 测计算函数或目标
      guards      guard ← 监视 gate

**同时支持 `extraction_policy.yaml`**（本机 build-ontology 的抽取范围控制）。

## 映射（对齐本机 ontology_v3 的实践）

    graph.entities    → term(type=entity)
    graph.facts       → term(type=metric)        定义里带 value+unit+section
    graph.reasoning   → term(type=concept)       定义里带 formula，配 derivation 边
    graph.claims      → term(type=claim)         定义里带 claim_type+status
    graph.conflicts   → constraints.json + term(type=constraint)
    graph.evidence    → evidence.json
    graph.validations → 并入 claim 的 definition
    graph.relations   → relations(type=实体边)

**反向**按 type 拆回八类。

## 设计原则

- **definition 承载结构化内容**（学本机 v3：gate 的表达式/输入/失败信息都在 definition）
- **ID 前缀保持可识别**（ent_/fact_/rea_/clm_/ev_/cf_），反向能还原
- **不丢字段**：`_graph` 字段保存原始节点，反向时优先用它
"""
from __future__ import annotations
import json
from pathlib import Path

EVO_FILES = ("terms", "mappings", "relations", "constraints", "evidence")
TYPE_MAP = {"entities": ("entity", "ent"), "facts": ("metric", "fact"),
            "reasoning": ("concept", "rea"), "claims": ("claim", "clm"),
            "evidence": ("evidence", "ev"), "conflicts": ("constraint", "cf")}
BACK_MAP = {v[0]: k for k, v in TYPE_MAP.items()}


# 节点属性来源 5 类（对齐形包 ontology/fact_source_map.yaml 的 source_type）
SOURCE_TYPES = {
    "CUSTOMER":   "必须由客户提供（网上搜不到、算不出来）",
    "STANDARD":   "可检索标准/法规/公告得到",
    "JUDGMENT":   "客户声明但必须绑证据（判断类）",
    "DERIVED":    "由规则算出，绝不能问客户要",
    "INTERMEDIATE":"客户给值但必须用规则复算，不一致→待审",
}

# 节点角色 3 类（对齐形包 ontology/input_vs_derived.yaml 的 role）
ROLES = {
    "INPUT":        "输入：客户给或可检索",
    "INTERMEDIATE": "中间量：客户给值 + 规则复算",
    "DERIVED":      "推演结果：只能算",
}

# 本地扩展的 6 种关系类型（renderer.py 支持，validate 不校验）
EXT_REL_TYPES = ("reasoning", "reuse", "citation", "has_limit", "tests", "guards")
CTRL_REL_TYPES = ("association", "hierarchy", "composition", "equivalence", "derivation")


def load_policy(project_root) -> dict:
    """读 extraction_policy.yaml（本机 build-ontology 的机制）。缺失则返回不限制。"""
    p = Path(project_root) / "extraction_policy.yaml"
    if not p.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def apply_policy(terms: list, policy: dict) -> list:
    """按 policy 过滤 term（include/exclude types / ids / prefixes / name patterns / max）。"""
    if not policy:
        return terms
    import re as _re
    inc_t = set(policy.get("include_term_types") or [])
    exc_t = set(policy.get("exclude_term_types") or [])
    only = set(policy.get("include_only_term_ids") or [])
    exc_id = set(policy.get("exclude_term_ids") or [])
    exc_pref = tuple(policy.get("exclude_term_id_prefixes") or ())
    pats = [(_re.compile(p), p) for p in (policy.get("exclude_name_patterns") or [])]
    out = []
    for x in terms:
        tid, ty = str(x.get("id") or ""), str(x.get("type") or "")
        nm = str(x.get("name") or "")
        if inc_t and ty not in inc_t: continue
        if exc_t and ty in exc_t: continue
        if only and tid not in only: continue
        if tid in exc_id: continue
        if exc_pref and tid.startswith(exc_pref): continue
        if any(p.search(nm) for p, _ in pats): continue
        out.append(x)
    mx = int(policy.get("max_terms") or 0)
    return out[:mx] if mx else out


def _infer_source_role(fact: dict) -> dict:
    """推断四个正交字段（确定性，零 LLM）。

    **三个维度不能混在一个字段里**：

      source_type   值从哪来   CUSTOMER / STANDARD / JUDGMENT / DERIVED / INTERMEDIATE
      node_role     怎么产生   INPUT / INTERMEDIATE / DERIVED
      must_input    ★ 是否必须客户填空（布尔）
      caliber_status ★ 口径是否唯一：unique / ambiguous / missing

    判据表：
    ┌────────────────────────────┬───────────┬──────────────┬──────────┬───────────┐
    │ 状况                        │ source    │ role         │ must_in  │ caliber   │
    ├────────────────────────────┼───────────┼──────────────┼──────────┼───────────┤
    │ status=undefined（缺值）    │ CUSTOMER  │ INPUT        │ **true** │ missing   │
    │ status=provided + calibers  │ CUSTOMER  │ INPUT        │ false    │ ambiguous │
    │ status=provided             │ CUSTOMER  │ INPUT        │ false    │ unique    │
    │ status=computed + calibers  │ DERIVED   │ INTERMEDIATE │ false    │ ambiguous │
    │ status=computed             │ DERIVED   │ DERIVED      │ false    │ unique    │
    └────────────────────────────┴───────────┴──────────────┴──────────┴───────────┘

    **关键**：`computed + calibers` 既不能标成纯 DERIVED（口径有分歧要客户确认），
    也不能标成 must_input=true（值本身不用客户直接给，但**它的依赖要**）。
    """
    st = str(fact.get("status") or "").lower()
    mp = fact.get("mapping")
    has_cal = bool(isinstance(mp, dict) and (mp.get("calibers") or mp.get("caliber_scope")))

    if st in ("undefined", "missing", "todo"):
        # ★ 两种 undefined 语义完全不同：
        #   ① 有 rule → 依赖缺失导致算不出来，**该问它的依赖，不是问它**
        #   ② 无 rule → 客户确实没给，**直接问客户**
        if fact.get("rule"):
            return {"source_type": "DERIVED", "node_role": "DERIVED",
                    "must_input": False, "caliber_status": "missing",
                    "missing_reason": "dependency_missing"}
        return {"source_type": "CUSTOMER", "node_role": "INPUT",
                "must_input": True, "caliber_status": "missing",
                "missing_reason": "customer_not_provided"}
    if st == "computed":
        return {"source_type": "DERIVED",
                "node_role": "INTERMEDIATE" if has_cal else "DERIVED",
                "must_input": False,
                "caliber_status": "ambiguous" if has_cal else "unique"}
    # provided
    return {"source_type": "CUSTOMER", "node_role": "INPUT",
            "must_input": False,
            "caliber_status": "ambiguous" if has_cal else "unique"}


def _prune(terms, rels, cons, evid):
    """policy 删掉 term 后，同步删除悬空引用（否则 validate 报错）。"""
    tids = {t.get("id") for t in terms}
    rels = [r for r in rels if r.get("source") in tids and r.get("target") in tids]
    return terms, rels, cons, evid


def _wr(ws: Path, ver: str, name: str, data: list):
    d = ws / "versions" / ver
    d.mkdir(parents=True, exist_ok=True)
    (d / (name + ".json")).write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def graph_to_evo(graph: dict, workspace, version: str = "graph_v1",
                 *, write: bool = True, policy: dict | None = None) -> dict:
    """graph.json → EvoOntology workspace。返回各集合条数。"""
    ws = Path(workspace)
    items = graph.get("items") or {}
    meta = graph.get("meta") or {}
    terms, evid, rels, cons = [], [], [], []

    # evidence（先做，供 evidence_refs 用）
    for e in items.get("evidence") or []:
        evid.append({"id": e.get("id"), "source": str(e.get("name") or ""),
                     "query": str(e.get("page") or ""),
                     "result": str(e.get("date") or ""),
                     "validation_method": str(e.get("kind") or ""),
                     "timestamp": str(e.get("date") or ""), "_graph": e})

    # entities
    for x in items.get("entities") or []:
        terms.append({"id": x.get("id"), "name": str(x.get("name") or ""),
                      "type": "entity", "scope": str(x.get("source") or ""),
                      "definition": str(x.get("name") or ""), "aliases": [],
                      "evidence": [], "source_type": "CUSTOMER", "node_role": "INPUT",
                      "_graph": x})
    # facts → metric（带 source_type / role）
    for f in items.get("facts") or []:
        v, u = f.get("value"), f.get("unit") or ""
        _sr = _infer_source_role(f)
        terms.append({"id": f.get("id"),
                      "name": "%s = %s%s" % (f.get("subject"), v, (" " + u) if u else ""),
                      "type": "metric",
                      "definition": "%s %s %s%s ｜ %s" % (
                          f.get("subject"), f.get("predicate") or "", v,
                          (" " + u) if u else "", f.get("section") or ""),
                      "scope": str(f.get("section") or ""), "aliases": [],
                      "evidence": [f["source"]] if f.get("source") else [],
                      **_sr, "_graph": f})
    # reasoning → concept
    for r in items.get("reasoning") or []:
        terms.append({"id": r.get("id"),
                      "name": "计算函数：%s" % (r.get("rule_id") or r.get("id")),
                      "type": "concept",
                      "definition": "公式：%s；结果：%s；输入：%s" % (
                          r.get("formula") or "", r.get("result") or "",
                          ", ".join(r.get("inputs") or [])),
                      "scope": str(r.get("section") or ""), "aliases": [],
                      "evidence": [], "source_type": "DERIVED", "node_role": "DERIVED",
                      "_graph": r})
    # claims → claim
    for c in items.get("claims") or []:
        v = next((x for x in (items.get("validations") or [])
                  if x.get("claim") == c.get("id")), None)
        terms.append({"id": c.get("id"), "name": str(c.get("text") or "")[:60],
                      "type": "claim",
                      "definition": "%s ｜ claim_type=%s status=%s%s" % (
                          c.get("text") or "", c.get("claim_type") or "",
                          c.get("status") or "",
                          (" ｜ 校验=%s" % v.get("status")) if v else ""),
                      "scope": str(c.get("section") or ""), "aliases": [],
                      "evidence": list(c.get("evidence_refs") or []),
                      "source_type": "JUDGMENT", "node_role": "DERIVED", "_graph": c})
    # conflicts → constraint
    for cf in items.get("conflicts") or []:
        cons.append({"id": cf.get("id"), "target": ",".join(map(str, cf.get("involved") or [])),
                     "constraint_type": "conflict", "severity": str(cf.get("severity") or ""),
                     "scope": str(cf.get("type") or ""),
                     "description": str(cf.get("description") or ""),
                     "evidence_refs": [], "_graph": cf})

    # relations（实体边 + 推理边）
    for r in items.get("relations") or []:
        rels.append({"id": r.get("id"), "source": r.get("from"), "target": r.get("to"),
                     "relation_type": str(r.get("type") or "association"),
                     "connection_condition": "", "description": "",
                     "evidence": [], "_graph": r})
    for r in items.get("reasoning") or []:
        for src in (r.get("inputs") or []):
            rels.append({"id": "rl_%s_%s" % (r.get("id"), src),
                         "source": src, "target": r.get("output") or r.get("id"),
                         "relation_type": "derivation", "connection_condition": "",
                         "description": str(r.get("rule_id") or ""), "evidence": []})

    # 防孤立：每个 term 至少要有一条边
    #   entity 之间靠 has_part；其余挂到项目根实体（association）
    root = next((x.get("id") for x in (items.get("entities") or [])
                 if str(x.get("type") or "").lower() in ("project", "项目")), None)
    if not root:
        root = next((x.get("id") for x in (items.get("entities") or [])), None)
    linked = set()
    for r in rels:
        linked.add(r.get("source")); linked.add(r.get("target"))
    if root:
        for t_ in terms:
            if t_.get("id") in linked or t_.get("id") == root:
                continue
            rels.append({"id": "rl_anchor_%s" % t_.get("id"),
                         "source": root, "target": t_.get("id"),
                         "relation_type": "association", "connection_condition": "",
                         "description": "锚定到项目根，防孤立", "evidence": []})

    # 应用 extraction_policy（若给了）
    pol = policy or {}
    if pol:
        before = len(terms)
        terms = apply_policy(terms, pol)
        terms, rels, cons, evid = _prune(terms, rels, cons, evid)
        if len(terms) != before:
            # 过滤后重新补锚定边
            linked2 = set()
            for r in rels:
                linked2.add(r.get("source")); linked2.add(r.get("target"))
            if root:
                for t_ in terms:
                    if t_.get("id") in linked2 or t_.get("id") == root: continue
                    rels.append({"id": "rl_anchor_%s" % t_.get("id"),
                                 "source": root, "target": t_.get("id"),
                                 "relation_type": "association",
                                 "connection_condition": "",
                                 "description": "锚定到项目根，防孤立", "evidence": []})

    out = {"terms": terms, "mappings": [], "relations": rels,
           "constraints": cons, "evidence": evid}
    if write:
        for k in EVO_FILES:
            _wr(ws, version, k, out[k])
        (ws / "active.json").write_text(
            json.dumps({"active_version": version}, ensure_ascii=False), encoding="utf-8")
        (ws / "project.json").write_text(
            json.dumps({"project_id": graph.get("project_id"),
                        "title": meta.get("title"),
                        "source": "corpus_pipeline.graph_from_project",
                        "extraction_policy": pol},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    return {k: len(v) for k, v in out.items()}


def evo_to_graph(workspace, version: str = "", *, project_id: str = "", title: str = "") -> dict:
    """EvoOntology workspace → graph.json（八类节点）。"""
    ws = Path(workspace)
    ver = version or json.loads((ws / "active.json").read_text(encoding="utf-8"))["active_version"]
    d = ws / "versions" / ver
    rec = {}
    for k in EVO_FILES:
        p = d / (k + ".json")
        rec[k] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

    items = {k: [] for k in ("entities", "relations", "facts", "reasoning",
                             "claims", "evidence", "conflicts", "validations")}
    for t in rec["terms"]:
        raw = t.get("_graph")
        bucket = BACK_MAP.get(t.get("type"))
        if raw and bucket:
            items[bucket].append(raw); continue
        # 无 _graph 时按 type 重建最小结构
        base = {"id": t.get("id"), "name": t.get("name"),
                "definition": t.get("definition"), "section": t.get("scope")}
        if t.get("type") == "entity":
            items["entities"].append(base)
        elif t.get("type") == "metric":
            items["facts"].append({"id": t.get("id"), "subject": t.get("name"),
                                   "value": t.get("definition"), "unit": "",
                                   "section": t.get("scope")})
        elif t.get("type") == "concept":
            items["reasoning"].append({"id": t.get("id"), "rule_id": t.get("name"),
                                       "formula": t.get("definition"),
                                       "section": t.get("scope")})
        elif t.get("type") == "claim":
            items["claims"].append({"id": t.get("id"), "text": t.get("definition"),
                                    "claim_type": "inference", "status": "unverified",
                                    "section": t.get("scope")})
    for r in rec["relations"]:
        raw = r.get("_graph")
        if raw: items["relations"].append(raw); continue
        items["relations"].append({"id": r.get("id"), "from": r.get("source"),
                                   "to": r.get("target"),
                                   "type": r.get("relation_type"), "source": ""})
    for e in rec["evidence"]:
        items["evidence"].append(e.get("_graph") or {
            "id": e.get("id"), "name": e.get("source"), "date": e.get("timestamp"),
            "page": e.get("query"), "kind": e.get("validation_method")})
    for c in rec["constraints"]:
        items["conflicts"].append(c.get("_graph") or {
            "id": c.get("id"), "type": c.get("scope"), "severity": c.get("severity"),
            "description": c.get("description"), "involved": []})

    return {"skill_id": "semantic-graph-compilation-skill",
            "skill_name": "corpus_pipeline.evo_bridge",
            "project_id": project_id or "unknown",
            "version_id": ver,
            "meta": {"title": title, "data_cutoff": "", "compiled_at": ""},
            "items": items,
            "stats": {k: len(v) for k, v in items.items()}}


def evo_health(workspace, version: str = "") -> dict:
    """一致性检查：悬空引用 / 孤儿 term / 缺证据。"""
    ws = Path(workspace)
    ver = version or json.loads((ws / "active.json").read_text(encoding="utf-8"))["active_version"]
    d = ws / "versions" / ver
    rec = {}
    for k in EVO_FILES:
        p = d / (k + ".json")
        rec[k] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    tids = {t.get("id") for t in rec["terms"]}
    eids = {e.get("id") for e in rec["evidence"]}
    problems = {"dangling_relation": [], "dangling_evidence": [], "isolated_term": []}
    linked = set()
    for r in rec["relations"]:
        s, g = r.get("source"), r.get("target")
        linked.add(s); linked.add(g)
        if s not in tids or g not in tids:
            problems["dangling_relation"].append(r.get("id"))
    for t in rec["terms"]:
        for e in (t.get("evidence") or []):
            if e not in eids:
                problems["dangling_evidence"].append("%s → %s" % (t.get("id"), e))
    for t in rec["terms"]:
        if t.get("id") not in linked:
            problems["isolated_term"].append(t.get("id"))
    return {"version": ver,
            "counts": {k: len(v) for k, v in rec.items()},
            "problems": {k: (len(v), v[:5]) for k, v in problems.items()},
            "ok": not any(problems.values())}
