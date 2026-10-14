# -*- coding: utf-8 -*-
"""探测：Semantica 的 llm 方法（DeepSeek）在中文上是否可用。"""
import json, os, time
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from semantica_env import load_env as _load_env
_load_env()  # 缺 key 直接退出，避免 provider 静默降级为空结果
WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"
chunks = [json.loads(l) for l in (PKG / "chunks/chunks.jsonl").read_text(encoding="utf-8").splitlines() if l]
txt = chunks[336]["text"][:900]
print("key 已设置:", bool(os.environ.get("DEEPSEEK_API_KEY")))
from semantica.semantic_extract.ner_extractor import NERExtractor
from semantica.semantic_extract.relation_extractor import RelationExtractor
from semantica.semantic_extract.triplet_extractor import TripletExtractor
out = {}
for label, cls in (("ner", NERExtractor), ("relation", RelationExtractor), ("triplet", TripletExtractor)):
    try:
        t0 = time.time()
        ex = cls(method="llm", provider="deepseek", llm_model="deepseek-chat")
        if label == "ner":
            r = ex.extract(txt)
        elif label == "relation":
            ents = NERExtractor(method="llm", provider="deepseek", llm_model="deepseek-chat").extract(txt)
            r = ex.extract(txt, entities=ents)
        else:
            r = ex.extract(txt)
        out[label] = {"ok": True, "n": len(r or []), "sample": [str(x)[:110] for x in (r or [])[:6]], "s": round(time.time()-t0, 1)}
        print(f"[{label}] OK {len(r or [])} 条 ({out[label]['s']}s)")
        for s in out[label]["sample"][:4]: print("      ", s)
    except Exception as e:
        out[label] = {"ok": False, "error": str(e)[:300]}
        print(f"[{label}] FAIL {str(e)[:200]}")
(Path(WS)/"kabuild/_llm_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
