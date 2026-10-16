#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""corpus_pipeline/chunking.py —— 优化后的切分（唯一实现）

**动机（本会话实测）**：原 stage_3_chunk 按空行 re.split(r'\\n\\s*\\n') 切：
  · 片数 1,178 · 中位 24 字符 · 最小 2（"水文"/"地震"… 列表项碎片）
  · span 用 pos += len(b)+2 手工累加 ⇒ offset 命中率仅 29.3%（833/1178 偏移错）
  · 内容哈希 ID ⇒ 22 个重复
  · 后果：s5h 需 1,178 × 3 = 3,533 次 LLM 调用，大量花在 2 字符碎片上

**优化（实测数据支撑）**：
  · markdown 用 Semantica structural：221 片 · offset 94.6% · 覆盖 99.3%（片数 −81%）
  · 相邻短片合并（下限 MIN_CHARS）⇒ 消除碎片
  · ID = 内容哈希 + 碰撞消歧（保证唯一）
  · 无 Semantica 时确定性回退（按空行 + 用 finditer 取精确 offset，修掉 span 漂移）

**纪律**：同输入同输出；片数与 ID 会变 ⇒ 下游须 anchors.rebind 重绑（锚用文档固有坐标，故可重绑）。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

MIN_CHARS = 30
TABLE_TYPE = "table"


def _sid(text: str, kind: str = "c") -> str:
    return f"{kind}-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"


def _classify(text: str) -> str:
    head = text.lstrip()
    if head.startswith("```table"):
        return TABLE_TYPE
    if re.match(r"^#{1,6}\s", head):
        return "heading"
    return "paragraph"


def _merge_short(items, min_chars=MIN_CHARS):
    """把过短的片并进相邻片（保持原文连续性与精确 span）"""
    out = []
    for it in items:
        if out and len(it["text"]) < min_chars:
            prev = out[-1]
            prev["text"] = (prev["text"] + "\n\n" + it["text"]).strip()
            prev["span"][1] = it["span"][1]
            prev["type"] = prev["type"] if prev["type"] == TABLE_TYPE else _classify(prev["text"])
        elif out and len(out[-1]["text"]) < min_chars:
            it["text"] = (out[-1]["text"] + "\n\n" + it["text"]).strip()
            it["span"][0] = out[-1]["span"][0]
            out[-1] = it
        else:
            out.append(it)
    return out


def _dedup_ids(items):
    seen, out = {}, []
    for it in items:
        base = _sid(it["text"])
        if base in seen:
            seen[base] += 1
            it["id"] = f"{base}#{seen[base]}"
        else:
            seen[base] = 1
            it["id"] = base
        out.append(it)
    return out


def chunk_structural(text: str):
    """Semantica structural（精确 offset）→ 合并短片 → 唯一 ID。失败返回 None。"""
    try:
        import sys
        _vp = "/Users/apple/.venvs/semantica/lib/python3.11/site-packages"
        if _vp not in sys.path:
            sys.path.append(_vp)
        from semantica.split import TextSplitter  # noqa: PLC0415
        ts = TextSplitter()
        ts.set_method("structural")
        cs = ts.split(text)
        items = [{"text": (c.text or "").strip(), "span": [c.start_index, c.end_index],
                  "type": _classify(c.text or "")} for c in cs
                 if c.start_index is not None and (c.text or "").strip()]
        if len(items) < 5:
            return None
        return _dedup_ids(_merge_short(items))
    except Exception:
        return None


def chunk_relaxed(text: str):
    """确定性回退：按空行切，但用 finditer 取真实 offset（修掉原实现的 span 漂移）。"""
    items = []
    for m in re.finditer(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*", text):
        raw = m.group()
        t = raw.strip()
        if not t:
            continue
        lead = len(raw) - len(raw.lstrip())
        items.append({"text": t, "span": [m.start() + lead, m.start() + lead + len(t)],
                      "type": _classify(t)})
    return _dedup_ids(_merge_short(items))


def chunk_document(text: str, prefer_structural: bool = True):
    """统一入口：优先 structural，不可用则精确回退。返回 (items, method)"""
    if prefer_structural:
        it = chunk_structural(text)
        if it:
            return it, "structural+merge+dedup"
    return chunk_relaxed(text), "relaxed+exact-span+merge+dedup"


if __name__ == "__main__":
    import json
    import sys
    ws = Path(__file__).resolve().parent.parent
    src = ws / "SHUFE-BDC-2019-001" / "source" / "normalized.md"
    if not src.exists():
        src = Path("/Users/apple/workdsh/.test-runtime/preview/workdsh-projects/"
                   "1667349c74609b4500654ac978662087a947e3f197112fe62706d819b8d081f0/"
                   "SHUFE-BDC-2019-001/source/normalized.md")
    t = src.read_text(encoding="utf-8")
    items, method = chunk_document(t)
    hits = sum(1 for it in items if t[it["span"][0]:it["span"][1]] == it["text"])
    L = sorted(len(it["text"]) for it in items)
    print(json.dumps({
        "method": method, "原文": len(t), "片数": len(items),
        "中位长": L[len(L) // 2], "最小": L[0], "最大": L[-1],
        "offset命中": f"{100*hits/len(items):.1f}%",
        "覆盖": f"{100*sum(len(it['text']) for it in items)/len(t):.1f}%",
        "ID唯一": f"{len({it['id'] for it in items})}/{len(items)}",
        "预计LLM调用(×3任务)": len(items) * 3,
    }, ensure_ascii=False, indent=1))
