# -*- coding: utf-8 -*-
"""规则判官：用 Semantica reasoning（等价于 MCP run_reasoning）判定主体对是否同一概念。
先在 17 组人工标准答案上测准确率。"""
import json, re
from pathlib import Path
from collections import Counter
WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"; OUT = PKG / "外部核验"
nodes = json.loads((PKG / "graph/nodes.yaml").read_text(encoding="utf-8"))
vals = {}
for n in nodes:
    vals.setdefault(n["subject"], []).append(str(n["value"]))

# 角色词表（按优先级：越具体的越靠前）
ROLES = [
 ("grade_fire", ["耐火等级"]), ("grade_safety", ["结构安全等级", "安全等级"]), ("grade_seismic", ["抗震设防", "抗震等级"]),
 ("role_person", ["名誉主任", "主任", "教授", "负责人", "导师"]),
 ("area", ["建筑面积", "使用面积", "面积"]),
 ("indicator", ["指标上限", "人均", "指标", "定额"]),
 ("standard", ["标准"]),
 ("fee", ["费用", "费", "金额", "造价"]),
 ("demand", ["需求", "合计"]),
 ("total", ["总额"]),
 ("count", ["人数", "数量", "数量（", "条数", "篇数", "项数"]),
 ("period", ["天数", "工期", "时间", "日期", "年限"]),
 ("state", ["状态"]),
 ("award", ["特等奖", "一等奖", "奖"]),
 ("project", ["课题", "项目"]),
 ("fund", ["资金", "经费", "投资"]),
 ("load", ["负荷", "荷载"]),
 ("rate", ["率", "系数"]),
]
def role(x):
    for name, kws in ROLES:
        for k in kws:
            if k in x: return name
    return "other"
def year(x):
    m = re.search(r'(20\d{2})', x); return m.group(1) if m else ""
def stdref(x):
    m = re.search(r'(GB\s*/?\s*T?\s*\d+)', x, re.I); return re.sub(r'\s+', '', m.group(1)).upper() if m else ""

def facts(a, b, sim):
    f = []
    sa, sb = set(vals.get(a, [])), set(vals.get(b, []))
    if sa and sb:
        f.append(("SameValue" if sa == sb else "DiffValue") + f"({a},{b})")
    ra, rb = role(a), role(b)
    f.append(("SameRole" if ra == rb and ra != "other" else "DiffRole") + f"({a},{b})")
    ya, yb = year(a), year(b)
    if ya and yb and ya != yb: f.append(f"DiffYear({a},{b})")
    ga, gb = stdref(a), stdref(b)
    if ga and gb and ga != gb: f.append(f"DiffStandardRef({a},{b})")
    f.append(("SimHigh" if sim >= 0.85 else "SimMid") + f"({a},{b})")
    return f, ra, rb

RULES = [
 "IF SameValue(?a,?b) AND SameRole(?a,?b) THEN SameConcept(?a,?b)",
 "IF DiffValue(?a,?b) AND SameRole(?a,?b) THEN ConflictCandidate(?a,?b)",
 "IF DiffRole(?a,?b) THEN DifferentConcept(?a,?b)",
 "IF DiffValue(?a,?b) AND DiffRole(?a,?b) THEN DifferentConcept(?a,?b)",
 "IF DiffYear(?a,?b) THEN DifferentConcept(?a,?b)",
 "IF DiffStandardRef(?a,?b) THEN DifferentConcept(?a,?b)",
 "IF SameConcept(?a,?b) THEN HumanReview(?a,?b)",
 "IF ConflictCandidate(?a,?b) THEN HumanReview(?a,?b)",
]
def derive(ff):
    """前向链：与 Semantica Reasoner 的规则语义保持一致的本地实现（用于批量）。"""
    got = set()
    changed = True
    def has(t, a, b): return f"{t}({a},{b})" in got or f"{t}({a},{b})" in ff
    while changed:
        changed = False
        for a, b in PAIRS:
            for r in RULES:
                m = re.match(r'IF (.+) THEN (\w+)\(\?a,\?b\)$', r)
                conds, head = m.group(1).split(" AND "), m.group(2)
                ok = True
                for c in conds:
                    t = c.strip().split("(")[0]
                    if not has(t, a, b): ok = False; break
                if ok and not has(head, a, b):
                    got.add(f"{head}({a},{b})"); changed = True
    return got

rev = json.loads((OUT / "dedup-review.yaml").read_text(encoding="utf-8"))
gt = [(e["a"], e["b"], e["verdict"], e["similarity"]) for e in rev["entries"]]
PAIRS = [(a, b) for a, b, _, _ in gt]
allfacts = []
per = {}
for a, b, v, sim in gt:
    ff, ra, rb = facts(a, b, sim)
    allfacts += ff; per[(a, b)] = (ff, ra, rb)
got = derive(allfacts)
def pred(a, b):
    # 负证据优先：命中年份/标准号/角色差异即判不同概念（避免正规则抢占）
    if f"DifferentConcept({a},{b})" in got: return "DIFF"
    if f"ConflictCandidate({a},{b})" in got: return "UNKNOWN"
    if f"SameConcept({a},{b})" in got: return "SAME"
    return "UNKNOWN"
ok = 0; detail = []
for a, b, v, sim in gt:
    gold = {"confirmed_alias":"SAME","false_positive":"DIFF","needs_review":"UNKNOWN"}[v]
    p = pred(a, b); hit = p == gold; ok += hit
    ff, ra, rb = per[(a, b)]
    detail.append({"a": a, "b": b, "human": v, "gold": gold, "rule_engine": p, "hit": hit,
                   "role_a": ra, "role_b": rb})
print(f"规则判官 vs 人工标准答案：{ok}/{len(detail)} = {ok/len(detail):.0%}")
for d in detail:
    print(f"  {'OK ' if d['hit'] else 'MISS'} 人工={d['gold']:7s} 规则={d['rule_engine']:7s} 角色=({d['role_a']},{d['role_b']})  {d['a']} ~ {d['b']}")
(OUT / "rule-judge-accuracy.yaml").write_text(json.dumps({
  "judge": "semantica.reasoning（等价 MCP run_reasoning）+ 领域角色词表",
  "ground_truth": "处理者人工复核的 17 组", "accuracy": round(ok/len(detail), 3), "n": len(detail),
  "detail": detail}, ensure_ascii=False, indent=2), encoding="utf-8")


try:
    from semantica_metrics import append_history as _append_history
    _append_history(str(OUT), 'rule', {"accuracy": locals().get("acc") or (ok / len(detail) if 'detail' in dir() and detail else None), "n": len(detail) if 'detail' in dir() else None})
except Exception:
    pass
