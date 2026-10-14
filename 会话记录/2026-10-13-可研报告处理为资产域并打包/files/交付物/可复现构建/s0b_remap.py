# -*- coding: utf-8 -*-
"""chunk id 重映射：将语义抽取引用的旧 chunk id 映射到「从原稿重推」的干净 chunk 集。

为什么不直接沿用旧 chunk：旧 chunks 派生自被另一进程追加过附录的中间文件，
其 chunk id 不可再作为溯源锚点。本案以 build/parts/*.jsonl（本任务 20:16 写入、
未被污染的预抽取分区）作为旧侧权威文本，按确定性规则映射：

  L1 文本完全相同
  L2 一方包含另一方（取长度差最小者）
  L3 字符二元组 Jaccard 最大且 ≥ 0.60
  未命中 => 登记为 dangling，显式呈现，不编造锚点。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert")
from corpus_pipeline import stage_1_normalize, stage_3_chunk  # noqa: E402

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"

# ---- 旧侧：预抽取分区（未被污染）----
old = {}
for p in sorted((BUILD / "parts").glob("P*.jsonl")):
    for line in p.read_text(encoding="utf-8").splitlines():
        if line:
            c = json.loads(line)
            old[c["id"]] = c["text"]

# ---- 新侧：从原稿重推 ----
clean = (BUILD / "doc-clean" / "大数据研究中心可研.md").read_text(encoding="utf-8")
tmp = BUILD / "_newchunks"
stage_1_normalize(clean, tmp / "source")
norm = (tmp / "source" / "normalized.md").read_text(encoding="utf-8")
new = stage_3_chunk(norm, tmp / "chunks")
new_text = {c["id"]: c["text"] for c in new}

exact = {t: i for i, t in new_text.items()}


def bigrams(s):
    s = "".join(s.split())
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


NEW_GRAMS = {i: bigrams(t) for i, t in new_text.items()}


MIN_RATIO = 0.60   # 包含关系必须体量相当，否则短块会吞掉长表（实测：表12-1 被映射到「其他」二字块）


def map_one(text):
    if text in exact:
        return exact[text], "L1_exact"
    cands = []
    for i, t in new_text.items():
        if text in t or t in text:
            ratio = min(len(text), len(t)) / max(len(text), len(t))
            if ratio >= MIN_RATIO:          # 体量相当才算同一语义块
                cands.append((abs(len(t) - len(text)), i))
    if cands:
        cands.sort()
        return cands[0][1], "L2_contain"
    g = bigrams(text)
    best, score = None, 0.0
    for i, ng in NEW_GRAMS.items():
        inter = len(g & ng)
        if not inter:
            continue
        j = inter / len(g | ng)
        if j > score:
            best, score = i, j
    if best and score >= 0.60:
        return best, f"L3_jaccard({score:.2f})"
    return None, f"unmatched(best={score:.2f})"


mapping, levels, unmatched = {}, {}, []
for oid, text in old.items():
    nid, how = map_one(text)
    levels[oid] = how
    if nid:
        mapping[oid] = nid
    else:
        unmatched.append({"old_id": oid, "preview": text[:80], "reason": how})

# ---- 重写抽取产物 ----
cited, cdangling = set(), set()
OUT = BUILD / "extractions-clean"
OUT.mkdir(exist_ok=True)


def remap(oid):
    if not oid:
        return oid
    cited.add(oid)
    if oid in mapping:
        return mapping[oid]
    cdangling.add(oid)
    return oid


for p in sorted((BUILD / "extractions").glob("*.json")):
    units = json.loads(p.read_text(encoding="utf-8"))
    for u in units:
        u["chunk_id_original"] = u["chunk_id"]
        u["chunk_id"] = remap(u["chunk_id"])
        for f in u.get("facts", []):
            f["source_original"] = f.get("source")
            f["source"] = remap(f.get("source"))
        for e in u.get("evidence", []):
            e["chunk_original"] = e.get("chunk")
            e["chunk"] = remap(e.get("chunk"))
        for r in u.get("relations", []):
            pass
    (OUT / p.name).write_text(json.dumps(units, ensure_ascii=False, indent=1), encoding="utf-8")

report = {
    "old_chunks": len(old), "new_chunks": len(new),
    "mapped": len(mapping), "unmatched": len(unmatched),
    "levels": {lv: sum(1 for v in levels.values() if v.startswith(lv)) for lv in ("L1", "L2", "L3", "unmatched")},
    "cited_ids": len(cited), "cited_mapped": len(cited & set(mapping)), "cited_dangling": sorted(cdangling),
    "unmatched_detail": unmatched[:40],
}
(BUILD / "remap_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "unmatched_detail"}, ensure_ascii=False, indent=2))
