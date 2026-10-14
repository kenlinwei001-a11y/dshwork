# -*- coding: utf-8 -*-
"""主体归一：规则判官（Semantica reasoning，替代 JEV）+ 待人工判断标签。"""
import json, re
from pathlib import Path
from collections import Counter, defaultdict
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from semantica_metrics import stats as _jstats, fmt as _jfmt, tier_fmt as _tier_fmt

WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"; OUT = PKG / "外部核验"
nodes = json.loads((PKG / "graph/nodes.yaml").read_text(encoding="utf-8"))
vals = defaultdict(list)
for n in nodes:
    vals[n["subject"]].append({"value": str(n["value"]), "unit": n.get("unit", "")})
ded = json.loads((OUT / "dedup-candidates.yaml").read_text(encoding="utf-8"))
pairs = []
for kind in ("same_value", "diff_value", "half_valued", "entity_only"):
    for p in ded["buckets"].get(kind, []):
        pairs.append((p["a"], p["b"], p["similarity"], kind))
print("候选总数:", len(pairs))

ROLES = [("grade_fire", ["耐火等级"]), ("grade_safety", ["结构安全等级", "安全等级"]),
 ("grade_seismic", ["抗震设防", "抗震等级"]), ("role_person", ["名誉主任", "主任", "教授", "负责人", "导师"]),
 ("area", ["建筑面积", "使用面积", "面积"]), ("indicator", ["指标上限", "人均", "指标", "定额"]),
 ("standard", ["标准"]), ("fee", ["费用", "费", "金额", "造价"]), ("demand", ["需求", "合计"]),
 ("total", ["总额"]), ("count", ["人数", "数量", "条数", "篇数"]),
 ("period", ["天数", "工期", "时间", "日期", "年限"]), ("state", ["状态"]),
 ("award", ["特等奖", "一等奖", "奖"]), ("project", ["课题", "项目"]),
 ("fund", ["资金", "经费", "投资"]), ("load", ["负荷", "荷载"]), ("rate", ["率", "系数"])]
def role(x):
    for name, kws in ROLES:
        if any(k in x for k in kws): return name
    return "other"
def year(x):
    m = re.search(r'(20\d{2})', x); return m.group(1) if m else ""
def stdref(x):
    m = re.search(r'(GB\s*/?\s*T?\s*\d+)', x, re.I); return re.sub(r'\s+', '', m.group(1)).upper() if m else ""

def judge(a, b, sim):
    sa, sb = {v["value"] for v in vals.get(a, [])}, {v["value"] for v in vals.get(b, [])}
    ra, rb = role(a), role(b); ya, yb = year(a), year(b); ga, gb = stdref(a), stdref(b)
    samev = bool(sa and sb and sa == sb)
    diffv = bool(sa and sb and sa != sb)
    if ga and gb and ga != gb: return "DIFF", "different_standard_ref", (ra, rb)
    if ya and yb and ya != yb: return "DIFF", "different_year", (ra, rb)
    if ra != rb and "other" not in (ra, rb): return "DIFF", "different_role", (ra, rb)
    if samev and ra == rb and ra != "other": return "SAME", "same_value_same_role", (ra, rb)
    if diffv and ra == rb and ra != "other": return "CONFLICT", "same_role_diff_value", (ra, rb)
    if samev: return "SAME", "same_value_only", (ra, rb)
    return "UNKNOWN", "insufficient", (ra, rb)

llm = {}
lp = OUT / "llm-subject-alignment.yaml"
if lp.exists():
    try:
        for r in json.loads(lp.read_text(encoding="utf-8")).get("results", []):
            llm[(r["a"], r["b"])] = r
    except Exception: pass
print("已载入 LLM 判定:", len(llm))

entries = []
for i, (a, b, sim, kind) in enumerate(pairs):
    verdict, why, (ra, rb) = judge(a, b, sim)
    l = llm.get((a, b), {})
    review = verdict in ("SAME", "CONFLICT", "UNKNOWN")
    label = "待人工判断" if review else "不需人工"
    disagree = bool(l) and ((l.get("verdict") == "SAME") != (verdict == "SAME"))
    if disagree: label = "待人工判断（引擎分歧）"
    entries.append({
        "id": f"NR-{i+1:04d}", "review_label": label,
        "subjects": [a, b],
        "value_a": "；".join(f'{v["value"]}{v["unit"]}' for v in vals.get(a, [])[:3]) or "",
        "value_b": "；".join(f'{v["value"]}{v["unit"]}' for v in vals.get(b, [])[:3]) or "",
        "same_value": bool({v["value"] for v in vals.get(a, [])} and {v["value"] for v in vals.get(a, [])} == {v["value"] for v in vals.get(b, [])}),
        "role": {"a": ra, "b": rb},
        "name_similarity": sim,
        "rule_engine": {"verdict": verdict, "basis": why},
        "llm_judge": {"verdict": l.get("verdict"), "confidence": l.get("confidence"), "reason": l.get("reason", "")} if l else None,
        "proposed_action": {"SAME": "建议合并为单一主体（事实单源）",
                            "CONFLICT": "并入口径冲突，交人工裁决取值",
                            "UNKNOWN": "信息不足，交人工判断"}.get(verdict, "不合并"),
        "human_decision": "",
    })
cnt = Counter(e["review_label"] for e in entries)
vc = Counter(e["rule_engine"]["verdict"] for e in entries)
print("标签分布:", dict(cnt))
print("规则判定分布:", dict(vc))
_rs = _jstats(str(OUT), "rule"); _ls = _jstats(str(OUT), "llm")
_ACC = {"source": "semantica_metrics（实测，非硬编码）",
        "rule_engine_vs_human": _rs.get("accuracy"), "llm_vs_human": _ls.get("accuracy"),
        "llm_same_precision": _ls.get("same_precision"), "llm_diff_precision": _ls.get("diff_precision"),
        "llm_observed_range": _ls.get("range"), "n_ground_truth": _ls.get("n")}
queue = [e for e in entries if e["review_label"].startswith("待人工判断")]
(OUT / "subject-normalization-queue.yaml").write_text(json.dumps({
  "label_convention": "review_label: 待人工判断 = 需人工决定是否归一；不需人工 = 已判定为不同概念",
  "judge": "semantica.reasoning 规则判官（替代 JEV）+ DeepSeek LLM 判官（交叉校验）",
  "accuracy": _ACC,
  "totals": {"candidates": len(entries), "need_human": len(queue)},
  "entries": entries,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("已写 subject-normalization-queue.yaml | 待人工判断:", len(queue))
