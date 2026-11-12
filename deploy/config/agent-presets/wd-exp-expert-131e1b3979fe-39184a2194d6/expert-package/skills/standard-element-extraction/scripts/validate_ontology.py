# -*- coding: utf-8 -*-
"""轻本体校验器：把 ontology.json 的类/关系/不变式变成可执行检查

用法：
  python3 validate_ontology.py --ses a.json [b.json ...] [--graph x.json ...]
退出码：有 ERROR → 1
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ONT = json.load(open(os.path.join(HERE, "ontology.json"), encoding="utf-8"))
CLS, REL = ONT["classes"], ONT["relations"]

ERR, WARN, INFO = [], [], []

def err(m): ERR.append(m)
def warn(m): WARN.append(m)

def get_collection(ses, name):
    c = CLS.get(name, {}).get("collection")
    if c == "standard":
        return [ses] if ses.get("standard_id") else []
    return ses.get(c) or []

def check_class(name, items, sid):
    spec = CLS[name]
    key = spec.get("key")
    seen = set()
    if key:
        for it in items:
            k = it.get(key)
            if not k: err(f"{sid}/{name}: 缺主键 {key}")
            if k in seen: err(f"{sid}/{name}: 主键重复 {k}")
            seen.add(k)
    for it in items:
        for f in spec.get("required", []):
            v = it.get(f)
            if v is None or v == "" or v == []:
                err(f"{sid}/{name}[{it.get(key,'?')}]: 必填字段为空 {f}")
        for f, dom in spec.get("enums", {}).items():
            v = it.get(f)
            if v is not None and v not in dom:
                warn(f"{sid}/{name}[{it.get(key,'?')}]: {f}={v} 不在枚举 {dom[:3]}…")
    if key and any(str(it.get(key, "")).startswith("ARC-") for it in items):
        for it in items:
            rid = it.get(key, "")
            if rid.startswith("ARC-"):
                cat = it.get("category")
                parts = rid.split("-")
                if len(parts) > 1 and cat and parts[1] != cat:
                    err(f"{sid}: rule_id {rid} 与 category {cat} 不一致")

def check_rule_extra(ses, sid):
    for r in ses.get("audit_rule_cards") or []:
        rid = r.get("rule_id")
        a = r.get("anchor") or {}
        if not (a.get("clause") and a.get("page") and a.get("quote")):
            err(f"{sid}/{rid}: anchor 不全（需 clause+page+quote）")
        ts = r.get("check_targets") or []
        if not ts:
            err(f"{sid}/{rid}: 缺 check_targets")
        for t in ts:
            for f in ("target_type", "field", "match_hints", "locator_strategy"):
                if not t.get(f): err(f"{sid}/{rid}: check_targets 缺 {f}")
        if not (r.get("evidence_required") or []):
            warn(f"{sid}/{rid}: evidence_required 为空")

def check_params(ses, sid):
    for p in ses.get("ion_parameters") or []:
        for f in ("dl_mg_L", "loq_mg_L"):
            if p.get(f) is None: err(f"{sid}: ion_parameters[{p.get('ion')}] 缺 {f}")
    for p in ses.get("parameters") or []:
        v = p.get("value")
        if isinstance(v, (int, float)) and not p.get("unit"):
            warn(f"{sid}/param[{p.get('name')}]: 数值缺 unit（无量纲请写 1）")

def check_elements(ses, sid):
    cl_type = {c["clause"]: c.get("type", "") for c in ses.get("clause_registry") or []}
    for e in ses.get("elements") or []:
        if e.get("origin") in ("derived", "convention") and not e.get("derive_from"):
            err(f"{sid}/{e.get('element_id')}: origin={e.get('origin')} 但无 derive_from")
        # 条件约束：obligation 为空 ⇔ 信息型条款
        ob = e.get("obligation")
        anchor = (e.get("anchor") or {}).get("clause", "")
        t = cl_type.get(anchor, "")
        if ob is None and not str(t).startswith("informative"):
            err(f"{sid}/{e.get('element_id')}: 锚定条款 {anchor}（type={t}）为规范型，但 obligation 为空")
        if ob is not None and ob not in ("MUST","SHOULD","MAY","MUST_NOT","INFO"):
            warn(f"{sid}/{e.get('element_id')}: obligation={ob} 非标准模态")

def check_gaps(ses, sid):
    for g in ses.get("gaps") or []:
        # 契约 v1.1：字段名以 SES 规范 §11 为准，旧名 affects 兼容
        if not (g.get("affected_clauses") or g.get("affects") or []):
            err(f"{sid}/{g.get('gap_id')}: affected_clauses 为空")

def check_graph(path):
    g = json.load(open(path, encoding="utf-8"))
    ids = {n["id"] for n in g.get("nodes", [])}
    ops = set(REL)
    seen = set()
    for e in g.get("edges", []):
        f, t, op = e.get("from"), e.get("to"), e.get("operator")
        if f not in ids: err(f"{os.path.basename(path)}: 边起点不存在 {f}")
        if t not in ids: err(f"{os.path.basename(path)}: 边终点不存在 {t}")
        if op not in ops: warn(f"{os.path.basename(path)}: 未知算子 {op}")
        k = (f, t, op)
        if k in seen: warn(f"{os.path.basename(path)}: 重复边 {k}")
        seen.add(k)
    for n in g.get("nodes", []):
        if n["type"] == "Rule":
            a = (n.get("attrs") or {}).get("anchor") or {}
            if not a.get("quote"): err(f"{os.path.basename(path)}: 规则节点无 anchor {n['id']}")


def check_rule_predicate_xor(ses, sid):
    """Rule: predicate 与 qualitative_check 严格二选一（契约 §1/§4）。"""
    for r in ses.get("audit_rule_cards") or []:
        rid = r.get("rule_id", "?")
        has_p = bool(r.get("predicate"))
        has_q = bool(r.get("qualitative_check"))
        if has_p and has_q:
            err(f"{sid}/{rid}: predicate 与 qualitative_check 不得并存")
        elif not has_p and not has_q:
            err(f"{sid}/{rid}: 缺 predicate 或 qualitative_check")
        if has_q:
            for f in ("question", "acceptable", "needs_review", "unacceptable"):
                if not (r["qualitative_check"].get(f) or []):
                    err(f"{sid}/{rid}: qualitative_check 缺 {f}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ses", nargs="+", default=[])
    ap.add_argument("--graph", nargs="+", default=[])
    a = ap.parse_args()
    for p in a.ses:
        ses = json.load(open(p, encoding="utf-8")); sid = ses.get("standard_id", os.path.basename(p))
        for name in CLS:
            items = get_collection(ses, name)
            if not items:
                continue
            check_class(name, items, sid)
        check_rule_extra(ses, sid); check_rule_predicate_xor(ses, sid); check_params(ses, sid)
        check_elements(ses, sid); check_gaps(ses, sid)
    for p in a.graph:
        check_graph(p)
    print(f"ERROR {len(ERR)}  WARN {len(WARN)}")
    for m in ERR[:20]: print("  ERROR", m)
    for m in WARN[:10]: print("  WARN ", m)
    sys.exit(1 if ERR else 0)

if __name__ == "__main__":
    main()
