# -*- coding: utf-8 -*-
"""合并规则判官与 LLM 判官，产出最终「待人工判断」队列（含 confidence 与分档）。"""
import json
from pathlib import Path
from collections import Counter, defaultdict
WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"; OUT = PKG / "外部核验"
q = json.loads((OUT / "subject-normalization-queue.yaml").read_text(encoding="utf-8"))
llm = {}
lp = OUT / "llm-subject-alignment.yaml"
if lp.exists():
    for r in json.loads(lp.read_text(encoding="utf-8")).get("results", []):
        llm[(r["a"], r["b"])] = r
print("LLM 判定载入:", len(llm))

for e in q["entries"]:
    k = (e["subjects"][0], e["subjects"][1])
    l = llm.get(k)
    e["llm_judge"] = ({"verdict": l["verdict"], "confidence": l.get("confidence"), "reason": l.get("reason", "")}
                      if l and l.get("verdict") in ("SAME", "DIFF", "UNKNOWN") else None)
    rv = e["rule_engine"]["verdict"]; lv = (e["llm_judge"] or {}).get("verdict")
    c = e["confidence"]
    if lv == "DIFF" and rv == "DIFF": c = min(0.99, c + 0.05)
    elif lv == "SAME" and rv == "SAME": c = min(0.99, c + 0.05)
    elif lv and lv != rv: c = max(0.30, c - 0.25)
    # 裁决：LLM 判 DIFF 且规则非 SAME -> 可采信 DIFF（LLM 的 DIFF 精度经校准为 100%）
    if lv == "DIFF" and rv in ("UNKNOWN",):
        e["final_verdict"] = "DIFF"; e["decided_by"] = "llm_diff_filter"; c = max(c, 0.80)
    elif lv == "DIFF" and rv in ("SAME", "CONFLICT"):
        e["final_verdict"] = "DISAGREE"; e["decided_by"] = "engine_disagreement"
    else:
        e["final_verdict"] = rv; e["decided_by"] = "rule_engine" + ("+llm" if e["llm_judge"] else "")
    e["confidence"] = round(c, 2)
    e["review_tier"] = ("A 高置信（建议采纳 · 抽审）" if c >= 0.85 else
                        "B 中置信（快速确认）" if c >= 0.60 else "C 低置信（逐条审校）")
    e["review_label"] = ("待人工判断（引擎分歧）" if e["final_verdict"] == "DISAGREE"
                         else "待人工判断" if e["final_verdict"] in ("SAME", "CONFLICT", "UNKNOWN")
                         else "不需人工")

need = [e for e in q["entries"] if e["review_label"].startswith("待人工判断")]
print("\n=== 合并后 ===")
print("  最终判定:", dict(Counter(e["final_verdict"] for e in q["entries"])))
print("  决策来源:", dict(Counter(e["decided_by"] for e in q["entries"])))
print("  待人工判断:", len(need), "条（初始候选 1104）")
for t in sorted(Counter(e["review_tier"] for e in need)):
    print(f"    {t}: {Counter(e['review_tier'] for e in need)[t]} 条")
q["totals"] = {"candidates": len(q["entries"]), "need_human": len(need),
               "auto_dismissed": len(q["entries"]) - len(need)}
q["tier_counts"] = dict(Counter(e["review_tier"] for e in need))
q["merge_rule"] = ("LLM 判 DIFF 且规则非 SAME -> 采信 DIFF（LLM 的 DIFF 精度经 17 组校准为 100%）；"
                   "规则判 SAME/CONFLICT 而 LLM 判 DIFF -> 标为「引擎分歧」优先人工；"
                   "两路一致 -> 提升 confidence")
(OUT / "subject-normalization-queue.yaml").write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n已写 subject-normalization-queue.yaml")
print("\n=== 引擎分歧项（最高优先）===")
for e in [x for x in q["entries"] if x["final_verdict"] == "DISAGREE"][:12]:
    print(f'  {e["subjects"][0]} ~ {e["subjects"][1]}  规则={e["rule_engine"]["verdict"]} LLM={(e["llm_judge"] or {}).get("verdict")} conf={e["confidence"]}')
