# -*- coding: utf-8 -*-
"""P0-b 交叉校验分析：消费 p0b-triplets.jsonl，产出精度/召回报告。
用法: KP_CORPUS_DIR=... python3 semantica_p0b_analyze.py
"""
from __future__ import annotations
import json, os, re, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from datetime import date

PKG = Path(os.environ["KP_CORPUS_DIR"]) if os.environ.get("KP_CORPUS_DIR") else Path("/Users/apple/Desktop/知识资产-上财大数据研究中心可研-2019ZX054/语料包")
OUT = PKG / "外部核验"
BT = chr(96); NL = chr(10)

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = re.sub(r"[\s,，。；;：:（）()\[\]【】、]", "", s)
    return s

def num_of(s: str):
    m = re.findall(r"\d+(?:\.\d+)?", norm(s).replace(",", ""))
    return m

def bigrams(s: str):
    s = norm(s)
    return {s[i:i+2] for i in range(max(0, len(s) - 1))} or {s}

def subj_match(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    if not a or not b: return False
    if a == b: return True
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a): return True
    A, B = bigrams(a), bigrams(b)
    if not A or not B: return False
    return len(A & B) / max(1, len(A | B)) >= 0.5

def val_match(v, text: str) -> bool:
    nums_v = num_of(str(v))
    nums_t = num_of(text)
    if not nums_v: return norm(str(v)) in norm(text)
    return all(any(x == y for y in nums_t) for x in nums_v)

nodes = json.loads((PKG / "graph/nodes.yaml").read_text(encoding="utf-8"))
recs = [json.loads(l) for l in (OUT / "p0b-triplets.jsonl").read_text(encoding="utf-8").splitlines() if l]
A = [r for r in recs if r["group"] == "A"]
B = [r for r in recs if r["group"] == "B"]
print("载入: A", len(A), "| B", len(B), "| 三元组总数", sum(len(r["triplets"]) for r in recs))

facts_by_chunk = defaultdict(list)
for n in nodes:
    facts_by_chunk[n.get("source")].append(n)

# ---------- A 组：我方事实的「被独立复现率」（精度代理） ----------
repro, missed, no_trip = [], [], []
for r in A:
    trips = r["triplets"]
    for f in facts_by_chunk.get(r["chunk"], []):
        hit = None
        for t in trips:
            if subj_match(f["subject"], t["subject"]) and val_match(f["value"], t["object"]):
                hit = t; break
            if subj_match(f["subject"], t["object"]) and val_match(f["value"], t["subject"]):
                hit = t; break
        (repro if hit else missed).append({"chunk": r["chunk"], "node": f["id"], "subject": f["subject"],
                                           "value": str(f["value"]), "unit": f.get("unit", ""),
                                           "matched": hit})
    if not trips: no_trip.append(r["chunk"])
tot_a = len(repro) + len(missed)
rate_a = len(repro) / tot_a if tot_a else 0
print("A 组: 我方事实 %d 条，被 Semantica 独立复现 %d 条 → %.1f%%；空三元组 chunk %d 个"
      % (tot_a, len(repro), rate_a * 100, len(no_trip)))

# ---------- B 组：候选漏抽（召回代理） ----------
seen = set()
cand = []
for r in B:
    for t in r["triplets"]:
        obj = t["object"]
        if not re.search(r"\d", obj): continue
        key = (norm(t["subject"]), norm(obj))
        if key in seen: continue
        seen.add(key)
        dup = any(subj_match(t["subject"], f["subject"]) and val_match(f["value"], obj)
                  for f in nodes)
        if not dup:
            cand.append({"chunk": r["chunk"], "subject": t["subject"], "predicate": t["predicate"],
                         "object": obj, "confidence": t["confidence"]})
print("B 组: 含数值三元组去重 %d 条，其中我方无对应事实的候选漏抽 %d 条" % (len(seen), len(cand)))

# ---------- 落盘 ----------
res = {
  "method": "semantica.semantic_extract.TripletExtractor(method='llm', provider='deepseek', llm_model='deepseek-chat')",
  "date": date.today().isoformat(),
  "scope": {"A_chunks": len(A), "B_chunks": len(B), "triplets_total": sum(len(r["triplets"]) for r in recs),
            "avg_triplets_per_chunk": round(sum(len(r["triplets"]) for r in recs) / max(1, len(recs)), 1)},
  "A_precision_proxy": {"our_facts": tot_a, "reproduced_by_semantica": len(repro),
                        "reproduce_rate": round(rate_a, 4), "empty_triplet_chunks": no_trip,
                        "missed_sample": missed[:40]},
  "B_recall_proxy": {"numeric_triplets": len(seen), "candidate_missed_facts": len(cand),
                     "candidates": cand[:80],
                     "note": "候选含 LLM 误报，属上界；须人工复核后才可入图"},
  "caveats": [
    "LLM 抽取存在误报与漏报；A 组复现率是「我方事实能被独立引擎复现」的代理指标，不等于抽取精度",
    "B 组候选来自随机 60 个未抽取 chunk，仅估计量级，不代表全量漏抽数",
    "匹配用名称包含/双字组 Jaccard≥0.5 + 数值全等，宽松匹配，故 A 组复现率偏乐观",
  ],
}
(OUT / "p0b-crosscheck.yaml").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

L = []; A_ = L.append
A_("# P0-b 全语料抽取交叉校验报告"); A_("")
A_("> 引擎 " + BT + "semantica 0.7.0" + BT + " ｜ 通道 Python API（A 方案）｜ 日期 " + date.today().isoformat()); A_("")
A_("## 一、做法"); A_("")
A_("用 LLM 三元组抽取（SPO）与我们的事实（subject/value）做结构对齐："); A_("")
A_("| 组 | 样本 | 目的 |")
A_("| --- | --- | --- |")
A_("- **A 组**：我方已抽取事实的来源 chunk（%d 个）→ 我方事实能否被独立引擎复现（精度代理）" % len(A))
A_("- **B 组**：随机 %d 个我方【未抽取】的 chunk（seed=42）→ 找候选漏抽（召回代理）" % len(B))
A_(""); A_("匹配规则：主体名包含或双字组 Jaccard ≥ 0.5，且数值全等。")
A_(""); A_("## 二、A 组结果（精度代理）"); A_("")
A_("| 项 | 值 |"); A_("| --- | --- |")
A_("| 我方事实（有来源 chunk 的） | %d 条 |" % tot_a)
A_("| 被 Semantica 独立复现 | **%d 条** |" % len(repro))
A_("| **复现率** | **%.1f%%** |" % (rate_a * 100))
A_("| 三元组为空的 chunk | %d 个 |" % len(no_trip))
A_(""); A_("## 三、B 组结果（召回代理）"); A_("")
A_("| 项 | 值 |"); A_("| --- | --- |")
A_("| 去重后的含数值三元组 | %d 条 |" % len(seen))
A_("| 我方无对应事实的**候选漏抽** | **%d 条** |" % len(cand))
A_(""); A_("## 四、边界（必读）"); A_("")
for cv in res["caveats"]: A_("- " + cv)
A_("")
(OUT / "P0B-交叉校验报告.md").write_text(NL.join(L), encoding="utf-8")
print("已写 p0b-crosscheck.yaml / P0B-交叉校验报告.md")
