# -*- coding: utf-8 -*-
"""Semantica 接入：P0 冲突第二双眼睛 + 抽取交叉校验；P1 实体消歧 + PROV-O 溯源；P2 切块对照。
只读语料包，产物写入 <pkg>/外部核验/。铁律：只检测、不裁决。
"""
import json, sys, time, statistics
from pathlib import Path
from collections import defaultdict, Counter

WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"
OUT = PKG / "外部核验"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "provenance").mkdir(parents=True, exist_ok=True)

def jload(p, default=None):
    p = Path(p)
    if not p.exists(): return default
    return json.loads(p.read_text(encoding="utf-8"))

nodes = jload(PKG / "graph/nodes.yaml", [])
rels = jload(PKG / "graph/relations.yaml", [])
chunks = [json.loads(l) for l in (PKG / "chunks/chunks.jsonl").read_text(encoding="utf-8").splitlines() if l]
conf_curated = jload(PKG / "quality/conflicts.yaml", [])
print(f"载入：事实 {len(nodes)} 条 | 关系 {len(rels)} 条 | chunk {len(chunks)} 条 | 现有冲突 {len(conf_curated)} 项")

report = {"semantica_version": None, "runs": {}}
import semantica
report["semantica_version"] = getattr(semantica, "__version__", "?")

# ============================ P0-a 冲突检测 ============================ #
from semantica.conflicts import ConflictDetector
t0 = time.time()
records = [{"id": n["subject"], "source": n["source"], "value": str(n["value"]),
            "unit": n.get("unit", "") or "—", "node": n["id"]} for n in nodes]
det = ConflictDetector()
c_val = det.detect_entity_conflicts(records)          # 全属性扫描
c_unit = det.detect_value_conflicts(records, "unit")  # 口径（单位）分歧
elapsed_a = time.time() - t0

def c2d(c):
    d = {}
    for k in ("conflict_id", "property_name", "conflicting_values", "severity", "entity_id",
              "conflict_type", "sources", "source_count", "detected_at", "metadata", "description"):
        if hasattr(c, k):
            v = getattr(c, k)
            d[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
    return d

sa = [c2d(c) for c in c_val]
sa_unit = [c2d(c) for c in c_unit]
# 只保留 value 属性的分歧（entity_id 即 subject）
val_conf = [c for c in sa if str(c.get("property_name")) == "value"]
print(f"[P0-a] ConflictDetector: 全属性 {len(sa)} 项 / value 属性 {len(val_conf)} 项 / unit 属性 {len(sa_unit)} 项  ({elapsed_a:.1f}s)")
report["runs"]["P0a_conflicts"] = {"module": "semantica.conflicts.ConflictDetector",
    "methods": ["detect_entity_conflicts", "detect_value_conflicts"],
    "total_all_props": len(sa), "value_conflicts": val_conf, "unit_conflicts": sa_unit,
    "elapsed_s": round(elapsed_a, 2),
    "rule": "只检测，不调用 ConflictResolver（项目铁律：冲突一律待审，不裁决）"}

# ============================ P0-b 抽取交叉校验 ============================ #
cross = {"module": "semantica.semantic_extract", "methods_tried": [], "probe": [], "summary": {}}
try:
    from semantica.semantic_extract import NERExtractor, RelationExtractor  # type: ignore
except Exception:
    from semantica.semantic_extract.ner_extractor import NERExtractor
    from semantica.semantic_extract.relation_extractor import RelationExtractor
sample = [chunks[i] for i in (108, 336, 1126) if i < len(chunks)]
for meth in ("pattern", "ml"):
    try:
        t1 = time.time()
        ner = NERExtractor(method=meth)
        ents = ner.extract(sample[0]["text"])
        cross["methods_tried"].append({"method": meth, "ok": True, "sample_entities": len(ents)})
        cross["probe"].append({"method": meth, "chunk": sample[0]["id"],
                               "entities": [str(getattr(e, "text", e))[:40] for e in ents[:10]]})
        print(f"[P0-b] NERExtractor(method={meth}) 可用，样例抽到 {len(ents)} 个实体 ({time.time()-t1:.1f}s)")
    except Exception as e:
        cross["methods_tried"].append({"method": meth, "ok": False, "error": str(e)[:160]})
        print(f"[P0-b] NERExtractor(method={meth}) 不可用：{str(e)[:120]}")
(OUT / "extraction-crosscheck.yaml").write_text(json.dumps(cross, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "conflicts-semantica.yaml").write_text(json.dumps(report["runs"]["P0a_conflicts"], ensure_ascii=False, indent=2), encoding="utf-8")
print("P0 落盘完成")
