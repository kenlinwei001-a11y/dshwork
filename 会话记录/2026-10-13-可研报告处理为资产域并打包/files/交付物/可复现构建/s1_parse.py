# -*- coding: utf-8 -*-
"""工序 1-3（确定性工具层）：归一化 → 骨架抽取 + 304号文覆盖校验 → 语义切块。

输入：input/大数据研究中心可研.md（由原 docx 解析，含标题样式）
输出：SHUFE-BDC-2019-001/{source,outline.yaml,chunks/chunks.jsonl}
"""
import json
import re
import sys
from pathlib import Path

KP = "/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert"
sys.path.insert(0, KP)
from corpus_pipeline import stage_1_normalize, stage_2_outline, stage_3_chunk  # noqa: E402

WS = Path(__file__).resolve().parent.parent
ROOT = WS / "SHUFE-BDC-2019-001"
ROOT.mkdir(parents=True, exist_ok=True)

# ---- 法定大纲：发改投资规〔2023〕304号《政府投资项目可行性研究报告编写通用大纲》 covers ----
GOV = Path("/Users/apple/.agents/.workdsh-state/skills/retained-revisions/"
           "rev-624abe095b926ebf4cbf0804/feasibility-report-edu-research/references/outline-gov-2023.yaml")
legal: list[str] = []
if GOV.exists():
    for m in re.finditer(r"covers:\s*\[([^\]]*)\]", GOV.read_text(encoding="utf-8")):
        for item in m.group(1).split(","):
            item = item.strip().strip("'\"")
            if item and item not in legal:
                legal.append(item)
print(f"[legal] 304号文法定内容项 {len(legal)} 条")

raw = (WS / "input" / "大数据研究中心可研.md").read_text(encoding="utf-8")
s1 = stage_1_normalize(raw, ROOT / "source")
norm = (ROOT / "source" / "normalized.md").read_text(encoding="utf-8")
outline = stage_2_outline(norm, legal, ROOT / "outline.yaml")
chunks = stage_3_chunk(norm, ROOT / "chunks")

# chunk 清单（供语义层 LLM 抽取分区使用）
(Path(__file__).parent / "chunks_index.tsv").write_text(
    "\n".join(f"{c['id']}\t{c['index']}\t{c['type']}\t{len(c['text'])}\t"
              f"{c['text'][:90].replace(chr(10), ' ')}" for c in chunks), encoding="utf-8")

summary = {
    "stage1_kept_lines": len(norm.split("\n")),
    "sections": len(outline["sections"]),
    "chunks": len(chunks),
    "legal_covered": len(legal) - len(outline["missing"]),
    "legal_missing": outline["missing"],
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
