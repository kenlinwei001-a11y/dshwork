# -*- coding: utf-8 -*-
"""P0-b 全语料抽取交叉校验（A 组验精度 / B 组估召回）。
用法: KP_CORPUS_DIR=/path/to/语料包 python3 semantica_p0b_crosscheck.py
产物: <corpus>/外部核验/p0b-triplets.jsonl（增量）+ p0b-crosscheck.yaml
"""
from __future__ import annotations
import json, os, random, sys, time
from pathlib import Path

# ---- 凭据载入（统一走 semantica_env；缺 key 直接退出，避免 provider 静默降级）----

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from semantica_env import load_env as _load_env
_load_env()  # 缺 key 直接退出，避免 provider 静默降级为空结果
PKG = Path(os.environ["KP_CORPUS_DIR"]) if os.environ.get("KP_CORPUS_DIR") else Path("/Users/apple/Desktop/知识资产-上财大数据研究中心可研-2019ZX054/语料包")
OUT = PKG / "外部核验"; OUT.mkdir(parents=True, exist_ok=True)
JSONL = OUT / "p0b-triplets.jsonl"
B_N = 60; SEED = 42

nodes = json.loads((PKG / "graph/nodes.yaml").read_text(encoding="utf-8"))
chunks = [json.loads(l) for l in (PKG / "chunks/chunks.jsonl").read_text(encoding="utf-8").splitlines() if l]
by_id = {c["id"]: c for c in chunks}
fact_sources = sorted({n["source"] for n in nodes if n.get("source") in by_id})
A = [by_id[s] for s in fact_sources]
used = set(fact_sources)
pool = [c for c in chunks if c["id"] not in used]
random.seed(SEED)
B = random.sample(pool, min(B_N, len(pool)))
print("A 组（我方已抽取的来源 chunk）:", len(A), flush=True)
print("B 组（未抽取随机样本，seed=%d）:" % SEED, len(B), flush=True)
print("chunk 总数:", len(chunks), "| 未被抽取:", len(pool), flush=True)

from semantica.semantic_extract.triplet_extractor import TripletExtractor
ex = TripletExtractor(method="llm", provider="deepseek", llm_model="deepseek-chat")

done = set()
if JSONL.exists():
    for l in JSONL.read_text(encoding="utf-8").splitlines():
        try: done.add(json.loads(l)["chunk"])
        except Exception: pass
print("已完成（断点续跑）:", len(done), flush=True)

t0 = time.time(); n_ok = 0; n_fail = 0
with JSONL.open("a", encoding="utf-8") as fh:
    for i, c in enumerate(A + B):
        cid = c["id"]
        if cid in done: continue
        trips = None
        for attempt in range(3):
            try:
                raw = ex.extract(c["text"][:2000]) or []
                trips = [{"subject": str(getattr(t, "subject", "")), "predicate": str(getattr(t, "predicate", "")),
                          "object": str(getattr(t, "object", "")),
                          "confidence": float(getattr(t, "confidence", 0) or 0)} for t in raw]
                break
            except Exception as e:
                if attempt == 2: print("  ERR", cid, str(e)[:120], flush=True)
                time.sleep(2 + attempt * 3)
        if trips is None:
            n_fail += 1; continue
        fh.write(json.dumps({"chunk": cid, "group": "A" if cid in fact_sources else "B",
                             "text_len": len(c["text"]), "triplets": trips}, ensure_ascii=False) + "\n")
        fh.flush(); n_ok += 1
        if not trips and n_ok == 1:
            print("  警告：首个 chunk 返回 0 三元组，疑似 provider 降级", flush=True)
        if n_ok % 20 == 0:
            print("  进度 %d/%d  %ds" % (n_ok, len(A) + len(B) - len(done), round(time.time() - t0)), flush=True)
print("抽取完成: 成功 %d | 失败 %d | 耗时 %ds" % (n_ok, n_fail, round(time.time() - t0)), flush=True)
