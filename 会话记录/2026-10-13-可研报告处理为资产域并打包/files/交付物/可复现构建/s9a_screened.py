# -*- coding: utf-8 -*-
"""把外部核查线索处置台账写入语料包（须在 s8_report.py 之前运行）。"""
import json
from pathlib import Path

from screened_source import SCREENED

BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent / "SHUFE-BDC-2019-001"

(ROOT / "quality" / "screened_evidence.yaml").write_text(json.dumps(
    {"note": "外部核查线索处置台账。用户已明确：外部检索文件与报告**联合处理**——报告的"
             "技术函数/取值，其取值域约束与推理保证来自这些文件。因此凡在 references/raw 有原始摘录的线索"
             "均已进入 external/（依据层）并绑定到报告技术函数；adopted=true 表示已按条款级采纳，"
             "adopted=false 表示**依据未取到所以不下判定**（待核查），不以沾边文件顶上。",
     "source": "references/raw/*（20 份外部检索文件，台账见 external/documents.yaml）；"
               "另有 外部核查/appendix-外部规范与法定大纲核查.md 系另一进程的派生叙述，内容已被依据层覆盖，仅留档备查",
     "items": SCREENED,
     "adopted_count": sum(1 for x in SCREENED if x["adopted"]),
     "pending_count": sum(1 for x in SCREENED if not x["adopted"])},
    ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"ledger_items": len(SCREENED),
                  "adopted": sum(1 for x in SCREENED if x["adopted"]),
                  "pending": sum(1 for x in SCREENED if not x["adopted"])}, ensure_ascii=False))
