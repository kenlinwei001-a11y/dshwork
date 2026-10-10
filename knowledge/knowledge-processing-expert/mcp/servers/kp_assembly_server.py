# -*- coding: utf-8 -*-
"""kp-assembly 入口：硬编码 GROUP=assembly，绕开 MCP connector 参数/环境变量传递 bug。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import os
os.environ["KP_MCP_GROUP"] = "assembly"
from mcp.server import main

if __name__ == "__main__":
    main()
