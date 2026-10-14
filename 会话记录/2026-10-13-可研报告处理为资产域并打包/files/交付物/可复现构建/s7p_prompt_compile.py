# -*- coding: utf-8 -*-
"""s7p —— 提示词编译环节（把所有 LLM 环节的提示词动态生成，泛化、不逐文档定制）。

三段式：① 识别（LLM 产出 → 代码受控校验，词表外一律不采纳）
        ② 装配（零 LLM：三层继承 + 槽位填充 + 闭合校验）
        ③ 生成（LLM 按 schema 输出；validator 校验，失败重试）
产出：SHUFE-BDC-2019-001/prompts/<doc_id>.<task>.json
      SHUFE-BDC-2019-001/quality/prompt_compile_report.yaml
"""
import json
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WS / "build"))
from promptc.compiler import compile_all  # noqa: E402

r = compile_all()
print(json.dumps({k: v for k, v in r.items() if k != "results"}, ensure_ascii=False, indent=2))
