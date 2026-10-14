# -*- coding: utf-8 -*-
"""给「待人工判断」加 confidence 与审校分档，并用 17 组标准答案校准分档阈值。"""
import json
from pathlib import Path
from collections import defaultdict, Counter
WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"; OUT = PKG / "外部核验"
q = json.loads((OUT / "subject-normalization-queue.yaml").read_text(encoding="utf-8"))
E = q["entries"]

BASE = {"same_value_same_role": 0.90, "same_role_diff_value": 0.62, "same_value_only": 0.58,
        "insufficient": 0.35, "different_standard_ref": 0.95, "different_year": 0.95, "different_role": 0.92}

def conf(e):
    b = e["rule_engine"]["basis"]
    c = BASE.get(b, 0.4)
    if e["name_similarity"] >= 0.85: c += 0.04
    ll = e["llm_judge"] or {}
    lv = ll.get("verdict")
    if lv and lv != "ERROR" and lv != "MISSING":
        rv = e["rule_engine"]["verdict"]
        agree = (lv == "SAME" and rv == "SAME") or (lv == "DIFF" and rv == "DIFF") or (lv == "UNKNOWN" and rv == "UNKNOWN")
        if agree: c += 0.05
        else: c -= 0.18
    lp = ll.get("confidence")
    if isinstance(lp, (int, float)): c = c * 0.85 + float(lp) * 0.15
    return round(max(0.05, min(0.99, c)), 2)

def tier(c):
    if c >= 0.90: return "A 免审（可直接采纳建议）"
    if c >= 0.75: return "B 快速确认（抽查）"
    return "C 逐条审校"

for e in E:
    e["confidence"] = conf(e)
    e["review_tier"] = tier(e["confidence"])

# ---- 用 17 组标准答案校准 ----
rev = json.loads((OUT / "dedup-review.yaml").read_text(encoding="utf-8"))
GOLD = {(x["a"], x["b"]): {"confirmed_alias": "SAME", "false_positive": "DIFF", "needs_review": "UNKNOWN"}[x["verdict"]]
        for x in rev["entries"]}
buckets = defaultdict(lambda: [0, 0])   # tier -> [correct, total]
cal = []
for e in E:
    k = (e["subjects"][0], e["subjects"][1])
    if k not in GOLD: continue
    gold = GOLD[k]; pred = e["rule_engine"]["verdict"]
    pred = "SAME" if pred == "SAME" else ("DIFF" if pred == "DIFF" else "UNKNOWN")
    hit = pred == gold
    b = e["review_tier"]; buckets[b][0] += hit; buckets[b][1] += 1
    cal.append({"pair": f"{k[0]} ~ {k[1]}", "gold": gold, "pred": pred, "hit": hit,
                "confidence": e["confidence"], "tier": b})
print("=== 分档校准（17 组标准答案）===")
for b in sorted(buckets):
    ok, n = buckets[b]
    print(f"  {b:24s} {ok}/{n}  精度 {ok/n:.0%}")

need = [e for e in E if e["review_label"].startswith("待人工判断")]
tc = Counter(e["review_tier"] for e in need)
print("\n=== 490 条待人工判断的分档 ===")
for t in sorted(tc): print(f"  {t:24s} {tc[t]} 条")
print(f"  → 免审 {tc.get('A 免审（可直接采纳建议）',0)} 条 + 快速确认 {tc.get('B 快速确认（抽查）',0)} 条，逐条审校仅 {tc.get('C 逐条审校',0)} 条")

q["confidence_model"] = {
  "components": {"rule_basis": BASE, "name_similarity_bonus": "+0.04 若 >=0.85",
                 "llm_agreement": "+0.05 一致 / -0.18 分歧", "llm_confidence": "加权 15%"},
  "tiers": {"A": ">=0.90 免审", "B": "0.75-0.89 快速确认", "C": "<0.75 逐条审校"},
  "calibration_on_17_ground_truth": {b: {"correct": v[0], "total": v[1],
      "precision": round(v[0]/v[1], 3) if v[1] else None} for b, v in buckets.items()},
  "purpose": "避免人工全量审校：先采纳 A 档建议，只对 B/C 档投入人力",
}
q["tier_counts"] = {t: tc[t] for t in sorted(tc)}
(OUT / "subject-normalization-queue.yaml").write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "confidence-calibration.yaml").write_text(json.dumps({
  "ground_truth": "17 组人工复核", "detail": cal,
  "tier_precision": {b: {"correct": v[0], "total": v[1], "precision": round(v[0]/v[1], 3) if v[1] else None}
                     for b, v in buckets.items()}}, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n已写 confidence-calibration.yaml")
