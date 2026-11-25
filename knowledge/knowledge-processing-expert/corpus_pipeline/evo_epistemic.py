# -*- coding: utf-8 -*-
"""evo_epistemic —— 三件事：实体有效性 / fact-claim 三分 / 因果判定（零 LLM）。

## 一、实体有效性五关

| 关 | 字段 | 判据 |
|---|---|---|
| 身份 | `id` / `type` / `name` / `scope` / `aliases` | 必须有 id，且全局唯一 |
| 证据 | `locator` | 至少一条可复现定位（file+section+quote）；无则 `slot`/`proposed` |
| 一致性 | `conflicts` | 同名不同义 / 值冲突 → `contested` |
| 权威性 | `authority` | `standard` / `report` / `derived` —— 不能把「报告提到」当「现实成立」 |
| 生命周期 | `epistemic_status` | `proposed` → `verified` → `contested` → `deprecated` |

## 二、fact / claim / rule 三分（按来源+推导，不按措辞）

| 情况 | 类型 | 判据 |
|---|---|---|
| 能直接指到原文，可复现，无推理 | **fact** | 有 locator + 无 formula |
| 由公式/规则算出，不引入解释 | **derived_fact** | 有 formula + 有 gate |
| 解释/判断/预测/风险/效益 | **claim** | 无 locator 直达原文 + 有 premise |
| 标准/制度「应/必须」 | **rule** | 有 expression + authority=standard |

**判定顺序（不可颠倒）**：
1. 有 locator 且无 formula → fact
2. 有 formula/expression → derived_fact 或 rule
3. 其余 → claim

## 三、因果判定

**不是因果的关系类型**（必须排除）：
- `association`   —— 只是相关
- `derivation`    —— 计算依赖
- `composition`   —— 部分-整体
- `hierarchy` / `citation` / `tests` / `guards` / `reuse` / `has_limit`

**真因果需要 5 条**（可研报告里大多不满足）：
1. 时间先后  2. 机制  3. 反事实  4. 控制混杂  5. 可重复

**故**：报告里的「有利于/促进/导致」标 `causal_claim` + `status=unverified`，
**不标 `causes` 事实边**。只有同时有 mechanism + conditions + evidence 才降级为 `causes`。
"""
from __future__ import annotations
import json
import re
from pathlib import Path

# ---------- 一、实体有效性 ----------
AUTHORITY = {
    "clause": "standard", "limit": "report", "metric": "report",
    "entity": "report", "category": "report", "concept": "report",
    "gate": "derived", "guard": "derived", "claim": "derived",
}

STATUS_RULES = [
    # (条件, 状态, 理由)
    (lambda t: t.get("type") == "clause" and "待补" in str(t.get("definition") or ""),
     "slot", "标准槽：条款原文/页码为空"),
    (lambda t: t.get("type") == "limit",
     "reported", "报告指标值，非标准强制限值"),
    (lambda t: bool(t.get("evidence")),
     "verified", "有 evidence 引用"),
    (lambda t: True,
     "proposed", "无证据引用"),
]


def assess_entities(terms: list, rels: list) -> dict:
    """实体有效性五关。返回 {assessed:[...], stats:{...}, problems:{...}}"""
    # 冲突检测：同一 name 出现在多个 id
    by_name = {}
    for t in terms:
        nm = str(t.get("name") or "").strip()
        if nm:
            by_name.setdefault(nm, []).append(t.get("id"))
    dup_names = {k: v for k, v in by_name.items() if len(v) > 1}

    # 孤立/悬空
    tids = {t.get("id") for t in terms}
    linked = set()
    for r in rels:
        linked.add(r.get("source")); linked.add(r.get("target"))
    dangling = [r.get("id") for r in rels
                if r.get("source") not in tids or r.get("target") not in tids]

    out, stats = [], {}
    for t in terms:
        st, why = "proposed", ""
        for cond, s, w in STATUS_RULES:
            if cond(t):
                st, why = s, w
                break
        nm = str(t.get("name") or "").strip()
        if nm in dup_names:
            st, why = "contested", "同名多 id：%s" % dup_names[nm]
        auth = AUTHORITY.get(str(t.get("type")), "report")
        has_loc = bool(t.get("evidence"))
        rec = {
            "id": t.get("id"), "type": t.get("type"),
            "epistemic_status": st, "authority": auth,
            "status_reason": why,
            # 五关拆解
            "gate_identity": bool(t.get("id") and t.get("type")),
            "gate_evidence": has_loc,
            "gate_consistency": nm not in dup_names,
            "gate_authority": auth in ("standard", "report", "derived"),
            "gate_lifecycle": st in ("proposed", "verified", "reported", "slot"),
        }
        out.append(rec)
        stats[st] = stats.get(st, 0) + 1
    return {"assessed": out, "stats": stats,
            "problems": {"duplicate_names": len(dup_names),
                         "dangling_relations": len(dangling)},
            "pass_all_five": sum(1 for r in out if all(
                r[k] for k in ("gate_identity", "gate_evidence",
                               "gate_consistency", "gate_authority", "gate_lifecycle")))}


# ---------- 二、fact / claim / rule 三分 ----------
def classify_epistemic(terms: list, rels: list) -> dict:
    """把节点分成 fact / derived_fact / claim / rule / slot。"""
    # gate 的 target_var（供 derived_fact 判定）
    gate_vars = {}
    for t in terms:
        if t.get("type") != "gate": continue
        d = str(t.get("definition") or "")
        m = re.search(r"表达式[：:]\s*([^；]+)", d)
        if not m: continue
        e = m.group(1).strip()
        mv = re.match(r"^([a-z_][a-z0-9_]*)\s*==", e) or \
             re.match(r"^abs\(\s*([a-z_][a-z0-9_]*)\s*[-*]", e)
        if mv:
            gate_vars[mv.group(1)] = t.get("id")

    out = {}
    for t in terms:
        tid = t.get("id"); ty = str(t.get("type") or "")
        has_ev = bool(t.get("evidence"))
        d = str(t.get("definition") or "")
        has_formula = bool(re.search(r"公式|计算链|=\s*[\d{]", d))
        is_slot = "待补" in d and ty in ("clause", "concept", "claim")

        # 按 term.type 分流（不按「有没有 evidence」一刀切）
        if ty == "clause":
            kind = "slot" if is_slot else "fact"
        elif ty == "gate":
            kind = "rule"
        elif ty == "guard":
            kind = "rule"          # 风险守卫也是规则
        elif ty == "claim":
            kind = "claim"
        elif ty == "limit":
            kind = "fact"          # 报告指标值 = 观察到的 fact
        elif ty == "metric":
            # 有 gate 定义它 / 有公式 → derived_fact；否则 → fact（报告观察值）
            kind = "derived_fact" if (tid in gate_vars.values() or has_formula) else "fact"
        elif ty in ("entity", "category"):
            kind = "entity"        # 实体不是 fact
        elif ty == "concept":
            # 概念：有公式 → rule；无 → claim（解释性）
            kind = "rule" if "公式" in d else "claim"
        else:
            kind = "fact" if has_ev else "claim"
        out.setdefault(kind, []).append({"id": tid, "type": ty,
                                          "has_evidence": has_ev,
                                          "name": str(t.get("name"))[:50]})
    return {"by_kind": {k: len(v) for k, v in out.items()},
            "samples": {k: v[:3] for k, v in out.items()},
            "detail": out}


# ---------- 三、因果判定 ----------
NON_CAUSAL = {"association", "derivation", "composition", "hierarchy",
              "equivalence", "citation", "tests", "guards", "reuse",
              "has_limit", "requires"}
CAUSAL_WORDS = ("有利于", "促进", "导致", "引起", "造成", "带动", "提升",
                "改善", "降低", "增加", "有利于")


def assess_causality(terms: list, rels: list) -> dict:
    """判因果。只有同时有 mechanism + conditions + evidence 才给 causes。"""
    causal_edges, suspicious = [], []
    for r in rels:
        rt = str(r.get("relation_type") or "")
        if rt in NON_CAUSAL:
            continue
        if rt in ("causes", "contributes_to", "prevents", "enables"):
            cc = r.get("connection_condition") or {}
            has_mech = bool(isinstance(cc, dict) and cc.get("mechanism"))
            has_cond = bool(isinstance(cc, dict) and cc.get("conditions"))
            has_ev = bool(r.get("evidence"))
            causal_edges.append({
                "id": r.get("id"), "type": rt,
                "source": r.get("source"), "target": r.get("target"),
                "strength": "strong" if (has_mech and has_cond and has_ev) else "weak",
                "status": "supported" if (has_mech and has_cond and has_ev) else "unverified",
            })

    # 报告里的「有利于/促进/导致」出现在 claim 文本里 → 标 causal_claim
    for t in terms:
        txt = str(t.get("definition") or "") + str(t.get("name") or "")
        if t.get("type") in ("claim", "concept"):
            hit = [w for w in CAUSAL_WORDS if w in txt]
            if hit:
                suspicious.append({"id": t.get("id"), "type": t.get("type"),
                                   "causal_words": hit[:3],
                                   "advice": "标 causal_claim + status=unverified，不标 causes"})
    return {"causal_edges": causal_edges,
            "causal_edge_count": len(causal_edges),
            "causal_words_in_claim": len(suspicious),
            "need_downgrade": suspicious[:10],
            "excluded_relation_types": sorted(NON_CAUSAL)}


CAUSAL_VERBS = ("导致", "引起", "造成", "促进", "提升", "改善", "降低",
                "带动", "有利于", "有助于", "增强", "削弱")


def build_causal_claims(workspace, version: str = "", *, out_version=None, write=True) -> dict:
    """把「含因果词但无机制/条件/证据」的论证性节点，落地为 causal_claim 节点。

    **不假装是因果事实**：status 一律 `unverified`，strength 一律 `weak`，
    除非 definition 里同时有「机制」「条件」「证据」三件。
    """
    ws = Path(workspace)
    ver = version or json.loads((ws/"active.json").read_text(encoding="utf-8"))["active_version"]
    src = ws/"versions"/ver
    terms = json.loads((src/"terms.json").read_text(encoding="utf-8"))
    rels = json.loads((src/"relations.json").read_text(encoding="utf-8"))

    created = []
    for t in terms:
        if t.get("type") not in ("claim", "concept"):
            continue
        d = str(t.get("definition") or "") + " " + str(t.get("name") or "")
        verbs = [v for v in CAUSAL_VERBS if v in d]
        if not verbs:
            continue
        # 找「因 → 果」：动词前后各取一段
        cause = effect = ""
        for v in verbs:
            i = d.find(v)
            if i < 0: continue
            cause = d[max(0, i - 40):i].strip().lstrip("，。、 ")
            effect = d[i + len(v):i + len(v) + 40].strip().split("，")[0].split("。")[0]
            break
        has_mech = bool(re.search(r"机制|原理|路径|because|由于.*导致", d))
        has_cond = bool(re.search(r"在.*条件下|前提|仅当|若", d))
        has_ev = bool(t.get("evidence"))
        strong = has_mech and has_cond and has_ev
        cid = "cc_" + str(t.get("id")).replace("claim_", "").replace("concept_", "")[:40]
        created.append({
            "id": cid,
            "name": "因果主张：%s" % str(t.get("name"))[:40],
            "type": "causal_claim",
            "definition": "%s → %s。原文：%s" % (cause[:60], effect[:60], d[:160]),
            "scope": "论证性主张，未证实因果",
            "aliases": [str(t.get("id"))],
            "evidence": list(t.get("evidence") or []),
            # ★ 因果五件的字段
            "cause": cause[:120], "effect": effect[:120],
            "mechanism": "" if not has_mech else "definition 中有机制描述",
            "conditions": "" if not has_cond else "definition 中有条件描述",
            "strength": "strong" if strong else "weak",
            "status": "supported" if strong else "unverified",
            "causal_verbs": verbs,
            "derived_from_node": t.get("id"),
        })

    if not write:
        return {"created": len(created), "nodes": created}

    out_ver = out_version or (ver + "_causal")
    dst = ws/"versions"/out_ver
    dst.mkdir(parents=True, exist_ok=True)
    all_terms = terms + created
    new_rels = list(rels)
    # causal_claim --derived_from--> 原节点
    for c in created:
        src_id = c.get("derived_from_node")
        if src_id:
            new_rels.append({
                "id": "rl_%s_src" % c["id"], "source": c["id"],
                "relation_type": "derivation", "target": src_id,
                "connection_condition": {"role": "derived_from"},
                "description": "", "evidence": [],
            })
    for nm, data in [("terms", all_terms), ("relations", new_rels)]:
        (dst/(nm+".json")).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    for nm in ("constraints", "evidence", "mappings"):
        f = src/(nm+".json")
        (dst/(nm+".json")).write_text(f.read_text(encoding="utf-8") if f.exists() else "[]",
                                      encoding="utf-8")
    (ws/"active.json").write_text(json.dumps({"active_version": out_ver}), encoding="utf-8")
    return {"created": len(created), "version": out_ver,
            "nodes": created}


def audit(workspace, version: str = "") -> dict:
    """三合一审计。"""
    ws = Path(workspace)
    ver = version or json.loads((ws/"active.json").read_text(encoding="utf-8"))["active_version"]
    src = ws/"versions"/ver
    terms = json.loads((src/"terms.json").read_text(encoding="utf-8"))
    rels = json.loads((src/"relations.json").read_text(encoding="utf-8"))
    return {"version": ver,
            "entity_validity": assess_entities(terms, rels),
            "epistemic": classify_epistemic(terms, rels),
            "causality": assess_causality(terms, rels)}
