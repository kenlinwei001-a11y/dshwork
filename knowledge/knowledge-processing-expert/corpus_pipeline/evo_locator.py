# -*- coding: utf-8 -*-
"""evo_locator —— 给 term 补细粒度 locator（file / section / chunk / quote / hash）。

## 为什么

现在 term 的证据是 `evidence: ["ev_inv_civil_rows"]` —— 指到 evidence 节点。
但 evidence 节点只有 `source: "表13-1 土建工程1.1至1.7行"`，**没有原文 quote 和 hash**。

「可复现」要求：**给定 locator 能重新取到那段原文，且校验它没变**。

## locator 结构

    "locator": {
      "file": "上海财经大学...可研报告（修订版）.docx",
      "section": "13.3 投资估算",
      "chunk_id": "c-a0a9cf13a201",
      "quote": "<原文片段，前后各 40 字>",
      "hash": "sha256 前 16 位",       ← 原文变了 hash 就变
      "char_span": [1234, 1301]
    }

## 取原文策略（确定性）

1. term.name（去括号/去占位）在 chunk 里精确出现 → 取该 chunk
2. term 的 definition 里第一个「中文名 + 数字」的模式串 → 在 chunk 里找
3. 都找不到 → locator = null，标 `unlocatable`

**不猜**：找不到就是找不到。
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

QUOTE_PAD = 40


def load_chunks(chunks_jsonl) -> dict:
    """chunk_id → chunk"""
    out = {}
    p = Path(chunks_jsonl)
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        out[c.get("id")] = c
    return out


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _norm(s: str) -> str:
    """去占位符/括号，用于匹配。"""
    s = re.sub(r"\{子系统\d\}", "", str(s or ""))
    s = re.sub(r"[（(].*?[）)]", "", s)
    return s.strip()


def find_locator(term: dict, chunks: dict, *, doc_name: str = "") -> dict | None:
    """给单个 term 找 locator。找不到返回 None。"""
    name = _norm(term.get("name") or "")
    # 尝试 1：name 全串
    cands = [name] if len(name) >= 2 else []
    # 尝试 2：definition 里的「中文名 + 数字」
    d = str(term.get("definition") or "")
    m = re.search(r"([\u4e00-\u9fa5]{2,12})\s*[=为:：]?\s*[\d,]+", d)
    if m:
        cands.append(m.group(1))
    # 尝试 3：name 的前 6 字
    if len(name) >= 4:
        cands.append(name[:6])

    for key in cands:
        if not key:
            continue
        for cid, c in chunks.items():
            txt = str(c.get("text") or "")
            i = txt.find(key)
            if i < 0:
                continue
            a = max(0, i - QUOTE_PAD)
            b = min(len(txt), i + len(key) + QUOTE_PAD)
            quote = txt[a:b]
            return {
                "file": doc_name or _doc_name_of(c),
                "section": c.get("section") or c.get("section_struct_no") or "",
                "chunk_id": cid,
                "quote": quote,
                "hash": _hash(quote),
                "char_span": [a, b],
            }
    return None


def _doc_name_of(chunk: dict) -> str:
    for a in (chunk.get("source_anchors") or []):
        if isinstance(a, dict) and a.get("document_name"):
            return a["document_name"]
    return chunk.get("document_id") or ""


def attach(workspace, version: str = "", chunks_jsonl=None, *,
           out_version=None, write=True) -> dict:
    """给 workspace 的所有 term 补 locator。"""
    ws = Path(workspace)
    ver = version or json.loads((ws/"active.json").read_text(encoding="utf-8"))["active_version"]
    src = ws/"versions"/ver
    terms = json.loads((src/"terms.json").read_text(encoding="utf-8"))
    rels = json.loads((src/"relations.json").read_text(encoding="utf-8"))
    cons = json.loads((src/"constraints.json").read_text(encoding="utf-8"))
    evid = json.loads((src/"evidence.json").read_text(encoding="utf-8"))

    chunks = load_chunks(chunks_jsonl) if chunks_jsonl else {}
    if not chunks:
        return {"error": "需要 chunks.jsonl（找不到原文就无法给 quote/hash）",
                "chunks_loaded": 0}

    stats = {"total": len(terms), "located": 0, "unlocatable": 0, "by_type": {}}
    out_terms = []
    for t in terms:
        loc = find_locator(t, chunks)
        nt = dict(t)
        if loc:
            nt["locator"] = loc
            stats["located"] += 1
            ty = str(t.get("type") or "")
            stats["by_type"][ty] = stats["by_type"].get(ty, 0) + 1
        else:
            nt["locator"] = None
            nt["locator_status"] = "unlocatable"
            stats["unlocatable"] += 1
        out_terms.append(nt)

    out_ver = out_version or (ver + "_located")
    if write:
        dst = ws/"versions"/out_ver
        dst.mkdir(parents=True, exist_ok=True)
        for nm, data in [("terms", out_terms), ("relations", rels),
                         ("constraints", cons), ("evidence", evid)]:
            (dst/(nm+".json")).write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        mp = src/"mappings.json"
        (dst/"mappings.json").write_text(
            mp.read_text(encoding="utf-8") if mp.exists() else "[]", encoding="utf-8")
        (ws/"active.json").write_text(
            json.dumps({"active_version": out_ver}), encoding="utf-8")
    stats["version"] = out_ver
    return stats
