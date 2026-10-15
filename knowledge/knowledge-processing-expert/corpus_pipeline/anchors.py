# -*- coding: utf-8 -*-
"""anchors —— 位置锚与重绑（**共享层唯一实现**）

两层分离：物理层（章节→子章节→切片→句子）从属；逻辑层（claim/evidence/node）引用。
**ID 是身份，锚是位置**：
  · 主锚 `doc_span + quote` —— **文档固有坐标，与切块/分句都无关**
  · `sentence_id` 索引（可重建）· `slice_id` 代指（当前这一代，**不是身份**）
精度分级：`exact` / `slice` / `UNLOCATED`（天生无逐字引文）/ `DANGLING`（**仅重绑失败**）。

由项目侧环节（如 s6c）调用；MCP 工具亦调用本模块（**不得 import 环节脚本**，那会执行整条环节）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _load_chunks(root: Path) -> dict:
    f = root / "chunks" / "chunks.jsonl"
    if not f.exists():
        return {}
    return {d["id"]: d for d in (json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip())}


def load_sentences(root: Path, chunks: dict) -> list:
    """句子索引：sentences.jsonl 自身不含 span ⇒ 按切片文本顺序推出**文档级坐标**。"""
    f = root / "chunks" / "sentences.jsonl"
    if not f.exists():
        return []
    by_chunk: dict = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            by_chunk.setdefault(d.get("chunk_id"), []).append(d)
    out = []
    for c in chunks.values():
        txt, base = c.get("text") or "", (c.get("span") or [0, 0])[0]
        cursor = 0
        for sd in sorted(by_chunk.get(c["id"], []), key=lambda x: x.get("seq") or 0):
            t = sd.get("text") or ""
            k = txt.find(t, cursor) if t else -1
            if k < 0:
                k = txt.find(t) if t else -1
            if k < 0:
                continue
            out.append({"sentence_id": sd.get("id"), "chunk_id": c["id"],
                        "doc_span": [base + k, base + k + len(t)]})
            cursor = k + len(t)
    out.sort(key=lambda x: x["doc_span"][0])
    return out


def anchor_of(rec: dict, chunks: dict, sentence_idx: list, doc_text: str) -> dict:
    sid = str(rec.get("source") or rec.get("chunk") or "").strip()
    ch = chunks.get(sid)
    a = {"doc_span": None, "quote": None, "sentence_id": None, "slice_id": sid or None,
         "order": None, "locatable": False, "precision": None, "position_status": "UNLOCATED"}
    q, t = str(rec.get("quote") or "").strip(), str(rec.get("text") or "").strip()
    cand = q or t
    if not cand:
        # 无逐字文本（事实节点只有 predicate）⇒ 退化为**切片级**锚（诚实标精度），**不是失效**
        if ch is not None:
            a.update(doc_span=list(ch.get("span") or []) or None, locatable=True,
                     precision="slice", position_status="ok")
        else:
            a["position_status"] = "UNLOCATED" if not sid else "DANGLING"
        return a
    pos = doc_text.find(cand[:40]) if len(cand) >= 6 else -1
    if pos < 0 and ch is not None:
        k = (ch.get("text") or "").find(cand[:24]) if len(cand) >= 6 else -1
        if k >= 0:
            pos = (ch.get("span") or [0, 0])[0] + k
    if pos >= 0:
        a.update(doc_span=[pos, pos + len(cand)], quote=cand, locatable=True,
                 precision="exact", position_status="ok")
        for sd in sentence_idx:
            if sd["doc_span"][0] <= pos < sd["doc_span"][1]:
                a["sentence_id"] = sd["sentence_id"]
                break
    elif ch is not None:
        a.update(doc_span=list(ch.get("span") or []) or None, locatable=True,
                 precision="slice", position_status="ok")
    else:
        a["position_status"] = "UNLOCATED" if not sid else "DANGLING"
    return a


def _doc_text(root: Path, chunks: dict) -> str:
    np = root / "source" / "normalized.md"
    if np.exists():
        return np.read_text(encoding="utf-8")
    return "\n".join((chunks[k].get("text") or "") for k in
                     sorted(chunks, key=lambda x: (chunks[x].get("span") or [0])[0]))


def _targets(root: Path):
    return [(root / "graph" / "claims.yaml", "claims", "list"),
            (root / "graph" / "nodes.yaml", "nodes", "list"),
            (root / "evidence" / "evidence.yaml", "evidence", "list")]


def attach(root: Path, write: bool = True) -> dict:
    """给 claims/nodes/evidence 挂锚（幂等）。"""
    chunks = _load_chunks(root)
    doc = _doc_text(root, chunks)
    sents = load_sentences(root, chunks)
    stat = {}
    for f, key, _t in _targets(root):
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        items = d if isinstance(d, list) else (d.get(key) or [])
        for it in items:
            it["anchor"] = anchor_of(it, chunks, sents, doc)
        by = {}
        for it in items:
            s_ = it["anchor"].get("slice_id")
            if s_:
                by.setdefault(s_, []).append(it)
        for _s, grp in by.items():
            grp.sort(key=lambda x: (x["anchor"]["doc_span"][0] if x["anchor"]["doc_span"] else 10 ** 9,
                                    str(x.get("id"))))
            for i, it in enumerate(grp):
                it["anchor"]["order"] = i
        if write:
            json.dump(items, f.open("w", encoding="utf-8"), ensure_ascii=False, indent=1)
        c = {}
        for it in items:
            k = f"status:{it['anchor'].get('position_status')}"
            p = f"precision:{it['anchor'].get('precision')}"
            c[k] = c.get(k, 0) + 1
            c[p] = c.get(p, 0) + 1
        stat[key] = {"total": len(items), **c}
    return {"stats": stat, "sentences_indexed": len(sents),
            "doc_chars": len(doc), "doc_text_source": "source/normalized.md"}


def rebind(root: Path, write: bool = True) -> dict:
    """重绑 **DANGLING** 者：ID 不变，只回填**当前这一代**索引；失败保持 DANGLING 待审。"""
    chunks = _load_chunks(root)
    doc = _doc_text(root, chunks)
    sents = load_sentences(root, chunks)
    healed, still = [], []
    for f, key, _t in _targets(root):
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        items = d if isinstance(d, list) else (d.get(key) or [])
        for it in items:
            a = it.get("anchor") or {}
            if a.get("position_status") != "DANGLING":
                # ★ 只重绑 DANGLING。UNLOCATED（天生无逐字引文）**不是失效**，不得当目标
                #   （否则报告被数百条噪声淹没 —— 实测踩到）。
                continue
            cand = str(it.get("quote") or it.get("text") or "").strip()
            p = doc.find(cand[:40]) if len(cand) >= 6 else -1
            if p < 0 and len(cand) >= 6:
                p = doc.find(cand[:24])
            if p < 0:
                still.append(str(it.get("id")))
                continue
            sid = next((c["id"] for c in chunks.values()
                        if (c.get("span") or [0, 0])[0] <= p < (c.get("span") or [0, 0])[1]), None)
            s_id = next((s["sentence_id"] for s in sents
                         if s["doc_span"][0] <= p < s["doc_span"][1]), None)
            it["anchor"] = {**a, "doc_span": [p, p + len(cand)], "quote": cand[:400],
                            "slice_id": sid, "sentence_id": s_id,
                            "locatable": True, "precision": "exact", "position_status": "ok"}
            healed.append(str(it.get("id")))
        if write:
            json.dump(items, f.open("w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"targets": len(healed) + len(still), "healed": healed, "still_dangling": still,
            "policy": "ID 不变；只回填当前位置索引；失败保持 DANGLING 待审"}
