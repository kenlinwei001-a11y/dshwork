# -*- coding: utf-8 -*-
"""s5h —— 抽取驱动：由编译好的提示词逐片驱动抽取，并记录每片的 prompt_sha256。"""
import json, sys
from pathlib import Path
WS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WS / "build"))
from promptc.driver import run_all  # noqa: E402
print(json.dumps(run_all(), ensure_ascii=False, indent=2)[:1200])
