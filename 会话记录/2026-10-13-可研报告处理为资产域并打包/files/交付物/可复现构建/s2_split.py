# -*- coding: utf-8 -*-
"""把 chunks.jsonl 按顶层章节切分为语义抽取分区（供 LLM 层并行抽取）。"""
import json
import re
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
ROOT = WS / "SHUFE-BDC-2019-001"
OUT = Path(__file__).resolve().parent / "parts"
OUT.mkdir(exist_ok=True)

cs = [json.loads(l) for l in (ROOT / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l]

# 顶层章节边界
bounds = [i for i, c in enumerate(cs) if re.match(r"^#\s", c["text"])]
bounds.append(len(cs))

# 分区：按章节归并（保持章节完整，避免语义断裂）
PARTS = {
    "P1": ("封面·目录·总论·学校简介", 0, 4),
    "P2": ("项目建设背景及必要性分析", 4, 5),
    "P3": ("项目选址及建设条件·项目建设内容及规模", 5, 7),
    "P4": ("项目规划设计方案", 7, 8),
    "P5": ("节能设计·环境影响评价", 8, 10),
    "P6": ("卫生防疫与劳动安全·社会稳定风险·项目管理及实施进度·招投标方案", 10, 14),
    "P7": ("投资估算及资金筹措·社会效益·结论与建议·附件", 14, len(bounds) - 1),
}

manifest = []
for pid, (title, a, b) in PARTS.items():
    lo, hi = bounds[a], bounds[b]
    part = cs[lo:hi]
    (OUT / f"{pid}.jsonl").write_text(
        "\n".join(json.dumps({"id": c["id"], "index": c["index"], "type": c["type"], "text": c["text"]},
                             ensure_ascii=False) for c in part), encoding="utf-8")
    manifest.append({"part": pid, "title": title, "chunk_range": [lo, hi - 1],
                     "chunks": len(part), "chars": sum(len(c["text"]) for c in part),
                     "file": f"build/parts/{pid}.jsonl"})

(OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
for m in manifest:
    print(f"{m['part']}  chunks={m['chunks']:4d} chars={m['chars']:6d}  idx{m['chunk_range'][0]}-{m['chunk_range'][1]}  {m['title']}")
