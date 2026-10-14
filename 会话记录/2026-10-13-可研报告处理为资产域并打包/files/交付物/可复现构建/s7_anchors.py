# -*- coding: utf-8 -*-
"""来源锚点补齐（确定性）：给每个 chunk/skeleton 挂上「文档 → 章节路径 → 字符区间」。

kp 的 gate_qg1 要求语义切片带来源锚点（section / source_anchors / document_id），
而 stage_3_chunk 产出的 chunk 只有 span，缺章节归属。此处按 chunk 顺序遍历、
遇到标题 chunk 即更新章节栈，得到每块的 section_path —— 同输入同输出。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "SHUFE-BDC-2019-001"
DOC_ID = "SHUFE-BDC-2019-001"
DOC_NAME = "上海财经大学中山北一路校区大数据研究中心 可行性研究报告（修订版）.docx"


def load_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def annotate(items):
    stack, out, meta = {}, [], {}
    for c in items:
        m = re.match(r"^(#{1,6})\s+(.*)$", c["text"])
        if m and c.get("type") == "heading":
            lvl = len(m.group(1))
            stack = {k: v for k, v in stack.items() if k < lvl}
            stack[lvl] = m.group(2).strip()
        path = [stack[k] for k in sorted(stack)]
        num = re.findall(r"^\d+(?:\.\d+)*", path[-1]) if path else []
        out.append({**c,
                    "document_id": DOC_ID,
                    "section": path[-1] if path else "",
                    "section_number": num[0] if num else "",
                    "section_path": path,
                    "source_anchors": [{"document_id": DOC_ID, "document_name": DOC_NAME,
                                        "section_path": path, "section_number": num[0] if num else "",
                                        "char_span": c.get("span")}]})
    return out


chunks = annotate(load_jsonl(ROOT / "chunks" / "chunks.jsonl"))
skels = annotate(load_jsonl(ROOT / "chunks" / "skeletons.jsonl"))
for name, items in (("chunks.jsonl", chunks), ("skeletons.jsonl", skels)):
    (ROOT / "chunks" / name).write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in items), encoding="utf-8")

no_anchor = [c["id"] for c in skels if not c.get("source_anchors")]
docs = {c["document_id"] for c in skels}
print(json.dumps({"chunks": len(chunks), "skeletons": len(skels),
                  "anchored": len(skels) - len(no_anchor), "document_ids": sorted(docs),
                  "distinct_sections": len({c["section"] for c in skels}),
                  "sample": {"id": skels[500]["id"], "section_path": skels[500]["section_path"]}},
                 ensure_ascii=False, indent=2))
