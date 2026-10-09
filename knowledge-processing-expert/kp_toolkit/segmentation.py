"""确定性分句 / 分块（零 LLM）。

对应 sentence-segmentation-skill 的确定性部分：
- 按中英文标点 + 换行规则切句，生成稳定 ID（同输入同输出）。
- 按标题/空行切块，生成稳定 chunk ID。
"""
from __future__ import annotations
import hashlib
import re

_SENT_END = re.compile(r'(?<=[。！？!?；;])\s*|\n+')
_HEADING = re.compile(r'^\s*(#{1,6}\s+|\d+(?:\.\d+)*[、.．]\s*|\S{1,20}[：:]\s*$)')


def stable_id(text: str, prefix: str = "s") -> str:
    """由内容确定性派生 ID（SHA1 前 12 位），同内容同 ID。"""
    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"


def segment_sentences(text: str, doc_id: str = "doc") -> list[dict]:
    """把文本切分为句子，返回 [{id, text, index}]。"""
    raw = [s.strip() for s in _SENT_END.split(text) if s and s.strip()]
    out = []
    for i, s in enumerate(raw):
        out.append({
            "id": stable_id(f"{doc_id}:{i}:{s}", "sent"),
            "text": s,
            "index": i,
        })
    return out


def segment_chunks(text: str, doc_id: str = "doc") -> list[dict]:
    """按标题/空行把文本切为语义块，返回 [{id, heading, text, index}]。"""
    blocks = re.split(r'\n\s*\n', text)
    out = []
    for i, b in enumerate(blocks):
        b = b.strip()
        if not b:
            continue
        heading = ""
        m = _HEADING.match(b)
        if m:
            heading = m.group(0).strip()
        out.append({
            "id": stable_id(f"{doc_id}:chunk:{i}:{b}", "chunk"),
            "heading": heading,
            "text": b,
            "index": i,
        })
    return out
