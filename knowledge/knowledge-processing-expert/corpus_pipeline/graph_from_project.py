# -*- coding: utf-8 -*-
"""graph_from_project —— 把 instantiate_project 产出的「项目图库」转成
推演写作专家要的「语义图谱 graph.json」（八类节点）。

为什么需要这一层：
  instantiate_project 产的是「项目图库」（meta/nodes/rules/bindings/gate_report），
  推演写作专家吃的是「语义图谱」（entities/relations/facts/reasoning/claims/
  evidence/conflicts/validations）。两者 schema 不同，必须转换。

映射规则：
  nodes[status=provided|computed]  -> facts
  nodes[status=undefined]          -> facts(value=null) + conflicts(覆盖完整性)
  rules + derivation               -> reasoning（formula 取 rules.expr）
  gate_report.replay_conflicts      -> conflicts（数字一致性，待审）
  gate_report.undefined             -> conflicts（覆盖完整性，待审）
  evidence                          -> 由 provided_facts 的 source/caliber 归纳
  entities/relations               -> 从 section + 节点族推导（可后补）
  claims/validations               -> 由 claims 模板生成骨架，状态 unverified

用法：
    from corpus_pipeline.graph_from_project import build_graph
    g = build_graph("华东理工-项目", meta={...}, provided=pf)
    json.dump(g, open("GRAPH.json","w"), ensure_ascii=False, indent=1)
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def _load(p: Path):
    try:
        from corpus_pipeline.fastload import load as _fl
    except Exception:
        _fl = None
    if not p.exists():
        return None
    if _fl is not None:
        return _fl(p)
    raw = p.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return yaml.safe_load(raw) if yaml else None


def _fid(label: str) -> str:
    return "F" + hashlib.md5(str(label).encode("utf-8")).hexdigest()[:6]


def _rid(rule: str) -> str:
    return "R" + hashlib.md5(str(rule).encode("utf-8")).hexdigest()[:6]


def build_graph(project_dir: str | Path, *, meta: dict | None = None,
                provided: list | None = None) -> dict:
    pd = Path(project_dir)
    nodes = _load(pd / "graph" / "nodes.yaml") or []
    rules = _load(pd / "graph" / "rules.yaml") or []
    deriv = _load(pd / "reasoning" / "derivation.yaml") or {}
    gate = _load(pd / "quality" / "gate_report.yaml") or {}
    pmeta = _load(pd / "meta.yaml") or {}
    meta = meta or {}

    # ---------------- facts ----------------
    facts, provided_facts, undefined_facts = [], [], []
    for n in nodes:
        lab = str(n.get("label") or n.get("subject") or "").strip()
        if not lab:
            continue
        st = str(n.get("status") or "provided")
        f = {
            "id": n.get("id") or _fid(lab),
            "subject": lab,
            "predicate": n.get("predicate") or "取值",
            "value": n.get("value"),
            "unit": n.get("unit") or "",
            "source": n.get("source") or n.get("evidence") or "E1",
            "section": "§" + str(n.get("section") or pmeta.get("section") or "?").lstrip("§"),
            "status": st,
            "lifecycle_state": "active",
            "mapping": None,          # 口径锚定（由 fsm 回填，见下）
        }
        if n.get("rule"):
            f["rule"] = n["rule"]
        if n.get("instruction"):
            f["instruction"] = n["instruction"]
        facts.append(f)
        (provided_facts if st == "provided" else undefined_facts if st == "undefined" else []).append(f)

    fact_id = {f["subject"]: f["id"] for f in facts}

    # ---------------- reasoning ----------------
    reasoning = []
    rule_of_target = {}
    for r in rules:
        tgt = str(r.get("target_label") or r.get("label") or "").strip()
        rid = str(r.get("id") or _rid(tgt))
        if not tgt:
            continue
        rule_of_target[tgt] = rid
    for r in rules:
        tgt = str(r.get("target_label") or r.get("label") or "").strip()
        if not tgt:
            continue
        rid = str(r.get("id") or _rid(tgt))
        deps = [str(d) for d in (r.get("deps") or [])]
        node = next((f for f in facts if f["subject"] == tgt), None)
        reasoning.append({
            "id": rid,
            "rule_id": rid,
            "formula": str(r.get("expr") or ""),
            "result": node["value"] if node else None,
            "desc": "%s → %s" % (rid, tgt),
            # deps 可能是「P-xxxx」节点 id（instantiate 已解析），也可能是事实名
            "inputs": [d if str(d).startswith("P-") else fact_id.get(d)
                       for d in deps
                       if (str(d).startswith("P-") or d in fact_id)],
            "deps_labels": deps,
            "output": node["id"] if node else None,
            "section": node["section"] if node else "§?",
        })

    # ---------------- 口径锚定回填（借 EvoOntology 的 Mapping 思想）----------------
    _fsm = None
    try:
        _fsm_path = Path(__file__).resolve().parent.parent / "corpus-library" / "fact_source_map.yaml"
        for cand in (pd / "fact_source_map.yaml", pd.parent / "形-可复用知识资产-v1.0" / "ontology" / "fact_source_map.yaml"):
            if cand.exists():
                _fsm = _load(cand); break
    except Exception:
        _fsm = None
    if _fsm:
        _map = {f["fact"]: (f.get("mapping") or {}) for f in (_fsm.get("facts") or [])}
        for f in facts:
            m = _map.get(f["subject"])
            if m and m.get("canonical"):
                f["mapping"] = {k: m.get(k) for k in ("calibers", "default", "semantic_filter", "grain")}
                f["caliber"] = m.get("default")

    # ---------------- conflicts ----------------
    conflicts = []
    try:
        from corpus_pipeline.caliber_check import classify_conflict as _cc
    except Exception:
        _cc = None
    for i, c in enumerate(gate.get("replay_conflicts") or [], start=1):
        _cj = _cc(str(c.get("subject")), c.get("provided"), c.get("recomputed"), _fsm) if _cc else {}
        conflicts.append({
            "id": "CF%d" % i,
            "type": "口径差异" if (_cj.get("kind") == "caliber_difference") else "数字一致性",
            "caliber_verdict": _cj.get("kind"),
            "caliber_reason": _cj.get("reason"),
            "severity": "高" if abs(float(c.get("recomputed") or 0) - float(c.get("provided") or 0)) > 100 else "中",
            "status": "待审",
            "description": "%s：客户提供 %s，规则重算 %s，差 %s。%s" % (
                c.get("subject"), c.get("provided"), c.get("recomputed"),
                round(float(c.get("recomputed") or 0) - float(c.get("provided") or 0), 2),
                c.get("reason") or ""),
            "involved": [fact_id[c["subject"]]] if c.get("subject") in fact_id else [],
        })
    base = len(conflicts)
    for i, u in enumerate(gate.get("undefined") or [], start=base + 1):
        conflicts.append({
            "id": "CF%d" % i, "type": "覆盖完整性", "severity": "高",
            "status": "待审",
            "description": "%s 因缺 %s 无法测算" % (u.get("target_label"), ", ".join(u.get("missing") or [])),
            "involved": [fact_id[u["target_label"]]] if u.get("target_label") in fact_id else [],
        })

    # ---------------- evidence ----------------
    evidence = [{
        "id": "E1",
        "name": meta.get("source_name") or "客户提供的基础资料",
        "date": meta.get("data_cutoff") or pmeta.get("data_cutoff") or "",
        "page": "全文", "kind": "E1",
    }]

    # ---------------- entities / relations ----------------
    # 实体从领域词典推导（不用正则抠碎片，见 entity_derivation.py）
    _ent_rels = []
    rels = _load(pd / "graph" / "relations.yaml") or []     # 可能不存在（轻量路径不建关系）

    # 分片能力探测（一次，写进图元信息，写作侧不必再探）
    _shard_status = {"available": False}
    try:
        from corpus_pipeline.shard_index import assert_shardable, NotShardable
        _r = assert_shardable(pd)
        _shard_status = {"available": True, "mode": "shard",
                         "sections": _r["sections"],
                         "unassigned_ratio": _r["unassigned_ratio"]}
    except Exception as _e:
        _shard_status = {"available": False, "mode": "full_fallback",
                         "reason": str(_e)[:160]}
    from corpus_pipeline.entity_derivation import derive as _derive_ent
    _m = {"title": meta.get("title") or pmeta.get("title") or "项目"}
    entities, _ent_rels = _derive_ent(facts, rules, rels, _m)

    # ---------------- relations（函数关系 = inputs → output）----------------
    relations = list(_ent_rels or [])   # 先并入实体关系（has_part / measured_by / bounded_by）
    for i, r in enumerate(reasoning, start=1):
        out = r.get("output")
        if not out:
            continue
        for src in (r.get("inputs") or []):
            relations.append({
                "id": "RL%03d" % (len(relations) + 1),
                "from": src, "to": out, "type": "computed_from",
                "subject": r.get("rule_id"),
                "payload": {"rule_id": r.get("rule_id"), "formula": r.get("formula"),
                            "result": r.get("result")},
                "source": {"kind": "derivation"},
            })
        # 同一规则多输入时补一条聚合边，便于图查询
        if len(r.get("inputs") or []) > 1:
            relations.append({
                "id": "RL%03d" % (len(relations) + 1),
                "from": "PRJ",
                "to": out, "type": "produces",
                "subject": r.get("rule_id"),
                "payload": {"rule_id": r.get("rule_id"), "input_count": len(r["inputs"])},
                "source": {"kind": "derivation"},
            })

    # ---------------- claims / validations ----------------
    claims, validations = [], []
    computed = [f for f in facts if f.get("status") == "computed"]
    for i, f in enumerate(computed, start=1):   # A4：全量产出 claim，不再只取前 5 个
        cid = "CL%d" % i
        rid = rule_of_target.get(f["subject"], "")
        st = "contradicted" if any(f["subject"] in c["description"] for c in conflicts) else "unverified"
        claims.append({
            "id": cid,
            "text": "%s = %s %s（由 %s 推演）" % (f["subject"], f["value"], f.get("unit") or "", rid),
            "claim_type": "inference", "type": "判断", "status": st,
            "section": f["section"],
            "deps": [rid] if rid else [],
            "evidence_refs": ["E1"], "premise_refs": [], "derived_from": [],
            "confidence": 0.7 if st == "unverified" else 0.4,
            "conflict": next((c["id"] for c in conflicts if f["subject"] in c["description"]), None),
            "valid_time": {"start": None, "end": None},
            "falsifiable_by": "若输入事实或规则口径变更，则本值不成立",
        })
        validations.append({
            "claim": cid,
            "status": "CONTRADICT" if st == "contradicted" else "SUPPORT",
            "reason": "由 %s 按 %s 计算" % (rid, f.get("rule") or "规则"),
        })

    return {
        "skill_id": "knowledge-processing-expert",
        "skill_name": "知识处理专家（沈溯源）",
        "project_id": meta.get("project_id") or pmeta.get("project_id") or "NEW-PROJECT",
        "document_id": meta.get("document_id") or "",
        "version_id": meta.get("version_id") or "V1.0-draft",
        "meta": {
            "title": meta.get("title") or pmeta.get("title") or "",
            "data_cutoff": meta.get("data_cutoff") or pmeta.get("data_cutoff") or "",
            "compiled_at": meta.get("compiled_at") or "",
            "compiled_by": "corpus_pipeline.graph_from_project",
            "based_on": pmeta.get("based_on") or {},
            # 分片能力在编译时就记录下来，写作侧不用再探一次
            "shard": _shard_status,
        },
        "items": {
            "entities": entities, "relations": relations,
            "facts": facts, "reasoning": reasoning,
            "claims": claims, "evidence": evidence,
            "conflicts": conflicts, "validations": validations,
        },
        "stats": {"facts": len(facts), "provided": len(provided_facts),
                  "undefined": len(undefined_facts), "reasoning": len(reasoning),
                  "computed": sum(1 for r in reasoning if r["result"] is not None),
                  "conflicts": len(conflicts)},
    }
