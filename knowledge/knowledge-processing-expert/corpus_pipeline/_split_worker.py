# -*- coding: utf-8 -*-
"""_split_worker —— 在 semantica venv 里批量切片，stdin/stdout 传 JSON。

## 为什么批量

按章节逐个起 subprocess，几百章 = 几百次 Python 启动（每次 2-3 秒），整体超时。
改成一次进程内循环所有段落，只起一次。

## 协议

stdin  JSON:
    {"method": "structural", "chunk_size": 1200, "chunk_overlap": 120,
     "segments": [{"key": "s0", "text": "..."}, {"key": "s1", "text": "..."}]}

stdout JSON:
    {"ok": true,
     "results": [{"key": "s0", "chunks": [{"index","text","start","end","method",
                                            "para_count","sentence_count"}]}],
     "stats": {"segments": N, "chunks": M, "chars": K}}

stdout 只输出 JSON（semantica 往 stderr 打 PyTorch 警告，不影响解析）。
"""
import json
import sys


def main():
    try:
        req = json.load(sys.stdin)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "bad stdin: %s" % e}, ensure_ascii=False))
        return

    method = req.get("method", "structural")
    chunk_size = int(req.get("chunk_size", 1200))
    chunk_overlap = int(req.get("chunk_overlap", 120))
    segments = req.get("segments") or []

    try:
        from semantica.split import TextSplitter
        splitter = TextSplitter(method=method, chunk_size=chunk_size,
                                chunk_overlap=chunk_overlap)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "splitter init: %s" % e},
                         ensure_ascii=False))
        return

    results, total = [], 0
    for seg in segments:
        key = str(seg.get("key") or "")
        text = seg.get("text") or ""
        if not text.strip():
            results.append({"key": key, "chunks": []})
            continue
        try:
            cs = splitter.split(text)
        except Exception as e:
            results.append({"key": key, "chunks": [],
                            "error": str(e)[:200]})
            continue
        bag = []
        for i, c in enumerate(cs):
            txt = getattr(c, "text", "") or ""
            st = getattr(c, "start_index", 0) or 0
            en = getattr(c, "end_index", None)
            if en is None:
                en = st + len(txt)
            meta = getattr(c, "metadata", {}) or {}
            bag.append({
                "index": i, "text": txt, "start": st, "end": en,
                "method": meta.get("method", method),
                "para_count": meta.get("paragraph_count") or
                              (len([p for p in txt.split("\n\n") if p.strip()]) or 1),
                "sentence_count": meta.get("sentence_count"),
                "token_count": meta.get("token_count"),
                "element_types": meta.get("element_types"),
            })
        total += len(bag)
        results.append({"key": key, "chunks": bag})

    print(json.dumps({"ok": True, "results": results,
                      "stats": {"segments": len(segments), "chunks": total,
                                "method": method}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
