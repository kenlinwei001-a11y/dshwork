# -*- coding: utf-8 -*-
"""P1-a 收敛：把 1104 组去重候选按「值是否一致」分类，产出可复核的别名/冲突候选清单。"""
import json, statistics
from pathlib import Path
from collections import defaultdict

WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"
OUT = PKG / "外部核验"
nodes = json.loads((PKG / "graph/nodes.yaml").read_text(encoding="utf-8"))
res = json.loads((OUT / "semantica-results.yaml").read_text(encoding="utf-8"))
curated = json.loads((PKG / "quality/conflicts.yaml").read_text(encoding="utf-8"))

vals = defaultdict(list)
for n in nodes:
    vals[n["subject"]].append({"value": str(n["value"]), "unit": n.get("unit", ""), "node": n["id"]})

def classify(a, b):
    va, vb = vals.get(a), vals.get(b)
    if va and vb:
        sa = {x["value"] for x in va}; sb = {x["value"] for x in vb}
        if sa == sb: return "same_value", sorted(sa)
        return "diff_value", [sorted(sa), sorted(sb)]
    if va or vb: return "half_valued", None
    return "entity_only", None

pairs = res["P1a_dedup"]["candidates"]
buckets = defaultdict(list)
for p in pairs:
    kind, detail = classify(p["a"], p["b"])
    buckets[kind].append({**p, "detail": detail})

curated_subjects = {str(c.get("subject")) for c in curated}
for kind in buckets:
    for p in buckets[kind]:
        p["in_curated"] = p["a"] in curated_subjects or p["b"] in curated_subjects

print(f"候选总数 {len(pairs)} → 分类：")
for k, v in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
    print(f"  {k:14s} {len(v):5d} 组  （其中命中既有冲突主体 {sum(1 for x in v if x['in_curated'])} 组）")

print("\n--- diff_value（值不一致：冲突候选，待审）前 12 组 ---")
for p in buckets["diff_value"][:12]:
    print(f"  {p['a']}  ~  {p['b']}   sim={p['similarity']}  值={p['detail']}")

print("\n--- same_value（值一致：别名候选）前 10 组 ---")
for p in buckets["same_value"][:10]:
    print(f"  {p['a']}  ~  {p['b']}   sim={p['similarity']}  值={p['detail']}")

out = {
  "module": "semantica.deduplication.DuplicateDetector",
  "method": "pairwise，similarity_threshold=0.72，confidence_threshold=0.6",
  "entities": res["P1a_dedup"]["entities"],
  "raw_candidates": len(pairs),
  "classification_rule": {
    "same_value": "两主体值完全一致 → 真别名候选（可直接归并）",
    "diff_value": "两主体值不一致 → 冲突候选（待审，不得自动归并）",
    "half_valued": "一方有值一方为实体名 → 实体别名候选",
    "entity_only": "双方均无值（关系中的实体）→ 实体别名候选",
  },
  "buckets": {k: v for k, v in buckets.items()},
  "counts": {k: len(v) for k, v in buckets.items()},
  "false_positive_samples": [p for p in buckets["diff_value"][:5]],
  "precision_note": "中文短名词的字符相似度假阳性高：如『2018年资产总额 ~ 2018年净资产总额』sim=0.888、"
                    "『多联室外机组（30HP）数量 ~ （10HP）数量』sim=0.883 均非同义。"
                    "因此本模块只能产出候选清单供人工复核，绝不自动合并（与项目铁律一致）。",
}
(OUT / "dedup-candidates.yaml").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n已写 {OUT/'dedup-candidates.yaml'}")

# PROV-O 统计落盘
prov = res["P1b_provenance"]
(OUT / "provenance-summary.yaml").write_text(json.dumps({
    "module": prov["module"], "standard": prov["standard"], "storage": prov["storage"],
    "tracked_entities": prov["tracked"], "failed": prov["failed"], "statistics": prov["statistics"],
    "db": prov["db"], "confidence_rule": "含『待核』=0.60；有口径=0.85；其余=0.95",
    "note": "本库为 W3C PROV-O 合规溯源，SHA-256 校验和可防篡改；与语料包自带 provenance.yaml 并存，前者为本处理者视图，后者为 Semantica 合规视图",
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("已写 provenance-summary.yaml")
