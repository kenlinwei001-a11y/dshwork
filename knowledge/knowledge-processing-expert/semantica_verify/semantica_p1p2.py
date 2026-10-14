# -*- coding: utf-8 -*-
"""P0-b 探测 + P1 实体消歧与 PROV-O 溯源 + P2 切块对照。"""
import json, os, time, statistics
from pathlib import Path
from collections import defaultdict

WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"
OUT = PKG / "外部核验"; OUT.mkdir(parents=True, exist_ok=True)
(OUT / "provenance").mkdir(parents=True, exist_ok=True)

nodes = json.loads((PKG / "graph/nodes.yaml").read_text(encoding="utf-8"))
rels = json.loads((PKG / "graph/relations.yaml").read_text(encoding="utf-8"))
chunks = [json.loads(l) for l in (PKG / "chunks/chunks.jsonl").read_text(encoding="utf-8").splitlines() if l]
conf_curated = json.loads((PKG / "quality/conflicts.yaml").read_text(encoding="utf-8"))

res = {}

# ---------- P0-b 探测：中文抽取是否可用 ----------
probe = {"llm_env_keys": {k: bool(os.environ.get(k)) for k in
         ["GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "GOOGLE_API_KEY"]}}
try:
    from semantica.semantic_extract.triplet_extractor import TripletExtractor
    txt = "上海财经大学中山北一路校区大数据研究中心总建筑面积为18319平方米，项目总投资为13032万元。"
    for meth in ("pattern",):
        try:
            tr = TripletExtractor(method=meth).extract(txt)
            probe[f"triplet_{meth}"] = [str(t)[:80] for t in (tr or [])[:5]]
        except Exception as e:
            probe[f"triplet_{meth}"] = "ERR " + str(e)[:120]
except Exception as e:
    probe["triplet"] = "import ERR " + str(e)[:120]
res["P0b_probe"] = probe
print("[P0-b 探测]", json.dumps(probe, ensure_ascii=False)[:400])

# ---------- P1-a 实体消歧 ----------
from semantica.deduplication import detect_duplicates
ents = []
seen = set()
for n in nodes:
    s = n["subject"]
    if s not in seen:
        seen.add(s); ents.append({"id": s, "name": s, "type": "fact_subject"})
for r in rels:
    for k in ("from", "to"):
        v = r.get(k)
        if v and not str(v).startswith(("N-", "CL-", "R")) and v not in seen:
            seen.add(v); ents.append({"id": v, "name": v, "type": "entity"})
t0 = time.time()
cands = detect_duplicates(ents, method="pairwise", similarity_threshold=0.72, confidence_threshold=0.6)
pairs = []
for c in cands:
    pairs.append({"a": c.entity1.get("name"), "b": c.entity2.get("name"),
                  "similarity": round(float(getattr(c, "similarity_score", 0)), 3),
                  "confidence": round(float(getattr(c, "confidence", 0)), 3)})
pairs.sort(key=lambda x: -x["similarity"])
print(f"[P1-a] DuplicateDetector: {len(ents)} 实体 -> {len(pairs)} 组候选  ({time.time()-t0:.1f}s)")
for p in pairs[:12]:
    print(f"        {p['a']}  ~  {p['b']}   sim={p['similarity']} conf={p['confidence']}")
res["P1a_dedup"] = {"module": "semantica.deduplication.DuplicateDetector", "entities": len(ents),
                    "candidates": pairs, "note": "只报候选，不执行合并（合并会改变语料，需人工复核）"}

# ---------- P0-a' 按官方顺序：以高相似度=同一实体 归并后再检冲突 ----------
from semantica.conflicts import ConflictDetector
parent = {e["id"]: e["id"] for e in ents}
def find(x):
    while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[rb] = ra
HIGH = 0.9
merged = [p for p in pairs if p["similarity"] >= HIGH]
for p in merged:
    if p["a"] in parent and p["b"] in parent: union(p["a"], p["b"])
canon = {k: find(k) for k in parent}
groups = defaultdict(list)
for k, v in canon.items(): groups[v].append(k)
multi = {k: v for k, v in groups.items() if len(v) > 1}
records = [{"id": canon.get(n["subject"], n["subject"]), "source": n["source"], "value": str(n["value"]),
            "subject": n["subject"], "node": n["id"]} for n in nodes]
det = ConflictDetector()
found = det.detect_value_conflicts(records, "value")
curated_subjects = {str(c.get("subject")) for c in conf_curated}
newc = []
for c in found:
    vals = getattr(c, "conflicting_values", [])
    members = [n["subject"] for n in nodes if canon.get(n["subject"]) == getattr(c, "entity_id", None)]
    cur = any(m in curated_subjects for m in members) or any(str(v) in str(x.get("values")) for x in conf_curated for v in vals)
    newc.append({"canonical": getattr(c, "entity_id", None), "members": sorted(set(members)),
                 "values": list(vals), "severity": str(getattr(c, "severity", "")),
                 "already_in_curated": bool(cur)})
print(f"[P0-a'] 高相似归并组 {len(multi)} 组；归并后检出数值冲突 {len(newc)} 项（其中已在原 13 项内 {sum(1 for x in newc if x['already_in_curated'])}）")
for x in newc[:10]:
    print(f"        {x['canonical']} 成员={x['members'][:3]} 值={x['values']} 新={not x['already_in_curated']}")
res["P0a_prime_conflicts_after_dedup"] = {"module": "semantica.conflicts.ConflictDetector",
    "order": "deduplication -> conflicts（官方要求顺序）", "high_similarity_groups": len(multi),
    "conflicts": newc, "rule": "只检测，不调用 ConflictResolver"}

# ---------- P1-b PROV-O 溯源 ----------
from semantica.provenance import ProvenanceManager
prov_path = OUT / "provenance" / "prov.db"
if prov_path.exists(): prov_path.unlink()
prov = ProvenanceManager(storage_path=str(prov_path))
t0 = time.time(); ok = 0; fail = 0
for n in nodes:
    conf = 0.6 if "待核" in str(n.get("value", "")) else (0.85 if n.get("caliber") else 0.95)
    try:
        prov.track_entity(entity_id=n["id"], source=str(n.get("source", "")),
                          metadata={"subject": n["subject"], "value": str(n["value"]),
                                    "unit": n.get("unit", ""), "time": n.get("time", ""),
                                    "caliber": n.get("caliber", "")},
                          confidence=conf, entity_type="fact", activity_id="kp-stage4-extraction",
                          source_location=str(n.get("source", "")), source_quote=str(n["subject"]))
        ok += 1
    except Exception as e:
        fail += 1
        if fail <= 3: print("   track_entity 失败:", str(e)[:120])
stats = {}
try: stats = prov.get_statistics()
except Exception as e: stats = {"error": str(e)[:120]}
print(f"[P1-b] ProvenanceManager: 记录 {ok} 条（失败 {fail}）({time.time()-t0:.1f}s)  stats={json.dumps(stats, ensure_ascii=False)[:200]}")
res["P1b_provenance"] = {"module": "semantica.provenance.ProvenanceManager", "storage": "SQLiteStorage",
                         "tracked": ok, "failed": fail, "db": str(prov_path.relative_to(PKG)),
                         "standard": "W3C PROV-O + SHA-256 checksum", "statistics": stats,
                         "downstream": "P1-a 去重与 P0-a' 冲突检测的权威来源"}

# ---------- P2-a 切块对照 ----------
from semantica.split import Splitter
norm = (PKG / "source/normalized.md").read_text(encoding="utf-8")
ours = [len(c["text"]) for c in chunks]
cmp_ = {"ours": {"count": len(chunks), "avg": round(statistics.mean(ours), 1),
                 "median": statistics.median(ours), "max": max(ours), "total_chars": sum(ours)}}
for meth, size in (("recursive", 1000), ("sentence", 500)):
    try:
        t0 = time.time()
        out = Splitter(method=meth, chunk_size=size, chunk_overlap=0).split(norm)
        lens = [len(getattr(c, "text", str(c))) for c in out]
        cmp_[f"semantica_{meth}"] = {"count": len(out), "avg": round(statistics.mean(lens), 1),
                                     "median": statistics.median(lens), "max": max(lens),
                                     "total_chars": sum(lens), "elapsed_s": round(time.time()-t0, 2)}
        print(f"[P2-a] Splitter({meth},{size}): {len(out)} 块  平均 {round(statistics.mean(lens),1)} 字")
    except Exception as e:
        cmp_[f"semantica_{meth}"] = "ERR " + str(e)[:140]
        print(f"[P2-a] Splitter({meth}) 失败：{str(e)[:120]}")
print(f"[P2-a] 我们的切块：{len(chunks)} 块  平均 {round(statistics.mean(ours),1)} 字  中位 {statistics.median(ours)}")
res["P2a_chunking"] = {"module": "semantica.split.Splitter", "comparison": cmp_}

text = json.dumps(res, ensure_ascii=False, indent=2)
(OUT / "semantica-results.yaml").write_text(text, encoding="utf-8")
print("\n已写:", OUT / "semantica-results.yaml")
