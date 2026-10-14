# -*- coding: utf-8 -*-
"""差异感知判决：用名称差异片段区分「不同实例」与「同义写法」，并重新校准 confidence。"""
import json, re, difflib
from pathlib import Path
from collections import defaultdict, Counter
WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"; OUT = PKG / "外部核验"
q = json.loads((OUT / "subject-normalization-queue.yaml").read_text(encoding="utf-8"))

CONTRAST = ["净", "名誉", "博士", "硕士", "干球", "湿球", "当量", "等价", "费率", "率",
            "地上", "地下", "室内", "室外", "冷", "热", "进", "出", "含", "不含", "暂定", "待核"]
OPTIONAL = ["用", "等", "约", "上限", "下限", "需求", "合计", "面积需求", "数", "量"]
SYNONYM_PAIRS = [("建设", "建筑安装"), ("费", "费用"), ("建筑面积", "需求建筑面积"),
                 ("使用面积", "面积需求合计"), ("天数", "工作天数"), ("招标估算金额", "费")]
def frags(a, b):
    sm = difflib.SequenceMatcher(None, a, b); out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal": continue
        out.append((a[i1:i2], b[j1:j2]))
    return out

def refined(e):
    a, b = e["subjects"]; ra, rb = e["role"]["a"], e["role"]["b"]
    fa = frags(a, b)
    joined = "".join(x + y for x, y in fa)
    has_digit = bool(re.search(r"\d", joined))
    has_contrast = any(c in joined for c in CONTRAST)
    all_optional = all((not x or x in OPTIONAL) and (not y or y in OPTIONAL) for x, y in fa) if fa else False
    known_syn = any((x in p and y in p) or (x in p or y in p) for p in SYNONYM_PAIRS for x, y in fa) if fa else False
    base = e["rule_engine"]["basis"]
    if base in ("different_standard_ref", "different_year"): return "DIFF", base, 0.95
    if base == "different_role": return "DIFF", base, 0.90
    if has_digit: return "DIFF", "different_spec_number", 0.88
    if has_contrast: return "DIFF", "contrast_token_diff", 0.85
    if all_optional: return "SAME", "optional_suffix_diff", 0.82
    if known_syn: return "SAME", "known_synonym", 0.88
    if base == "same_value_same_role": return "SAME", base, 0.90
    if base == "same_role_diff_value": return "CONFLICT", base, 0.62
    if base == "same_value_only": return "SAME", base, 0.60
    return "UNKNOWN", "insufficient", 0.35

for e in q["entries"]:
    v, why, c = refined(e)
    e["rule_engine"] = {"verdict": v, "basis": why}
    e["confidence"] = c
    e["review_tier"] = "A 高置信（建议采纳 · 抽审）" if c >= 0.85 else ("B 中置信（快速确认）" if c >= 0.60 else "C 低置信（逐条审校）")
    e["review_label"] = "待人工判断" if v in ("SAME", "CONFLICT", "UNKNOWN") else "不需人工"

rev = json.loads((OUT / "dedup-review.yaml").read_text(encoding="utf-8"))
GOLD = {(x["a"], x["b"]): {"confirmed_alias": "SAME", "false_positive": "DIFF", "needs_review": "UNKNOWN"}[x["verdict"]] for x in rev["entries"]}
bk = defaultdict(lambda: [0, 0]); detail = []
for e in q["entries"]:
    k = (e["subjects"][0], e["subjects"][1])
    if k not in GOLD: continue
    g = GOLD[k]; p = e["rule_engine"]["verdict"]; hit = p == g
    bk[e["review_tier"]][0] += hit; bk[e["review_tier"]][1] += 1
    detail.append({"pair": f"{k[0]} ~ {k[1]}", "gold": g, "pred": p, "hit": hit, "conf": e["confidence"], "tier": e["review_tier"]})
print("=== 重新校准（17 组标准答案）===")
for t in sorted(bk): print(f"  {t:26s} {bk[t][0]}/{bk[t][1]}  精度 {bk[t][0]/bk[t][1]:.0%}")
misses = [d for d in detail if not d["hit"]]
print("  失分项:", [f'{d["pair"]}(gold={d["gold"]},pred={d["pred"]})' for d in misses])

need = [e for e in q["entries"] if e["review_label"] == "待人工判断"]
tc = Counter(e["review_tier"] for e in need)
vc = Counter(e["rule_engine"]["verdict"] for e in q["entries"])
print(f"\n=== 结果 ===")
print("  全部 %d 组判定分布: %s" % (len(q["entries"]), dict(vc)))
print("  待人工判断 %d 条（原 490）" % len(need))
for t in sorted(tc): print(f"    {t}: {tc[t]} 条")
q["confidence_model"] = {
  "order": ["不同标准号/年份 -> DIFF", "角色不同 -> DIFF", "差异片段含数字 -> DIFF(不同实例)",
            "差异片段含对立词 -> DIFF", "差异仅为可选后缀 -> SAME", "已知同义对 -> SAME",
            "同值同角色 -> SAME", "同角色不同值 -> CONFLICT", "其余 -> UNKNOWN"],
  "tiers": {"A": ">=0.85 建议采纳, 抽审", "B": "0.60-0.84 快速确认", "C": "<0.60 逐条审校"},
  "calibration_on_17": {t: {"correct": v[0], "total": v[1], "precision": round(v[0]/v[1], 3) if v[1] else None} for t, v in bk.items()},
}
q["totals"] = {"candidates": len(q["entries"]), "need_human": len(need)}
q["tier_counts"] = {t: tc[t] for t in sorted(tc)}
(OUT / "subject-normalization-queue.yaml").write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "confidence-calibration.yaml").write_text(json.dumps({"ground_truth": "17 组人工复核", "detail": detail,
  "tier_precision": {t: {"correct": v[0], "total": v[1], "precision": round(v[0]/v[1], 3) if v[1] else None} for t, v in bk.items()}},
  ensure_ascii=False, indent=2), encoding="utf-8")
print("\n已写 subject-normalization-queue.yaml / confidence-calibration.yaml")
