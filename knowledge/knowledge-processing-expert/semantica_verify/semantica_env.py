# -*- coding: utf-8 -*-
"""统一从 ~/.semantica/env 载入凭据（幂等，不覆盖已存在的环境变量）。

为什么必须调用：
  Semantica 的 LLM provider 在【构造时】读环境变量；未载入时它不会报错，而是
  【静默降级】（返回空结果）——曾导致 169 个 chunk 的三元组全部为空却显示「成功」。
  因此所有需要 LLM 的脚本都必须在 import semantica 之前调用 load_env()。

用法：
  import sys; from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  from semantica_env import load_env
  load_env()                      # 缺 key 直接退出（strict），避免静默降级
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(os.environ.get("SEMANTICA_ENV_FILE", "/Users/apple/.semantica/env"))
REQUIRED = ("DEEPSEEK_API_KEY",)


def load_env(path=None, required=REQUIRED, strict: bool = True) -> dict:
    """把 env 文件里的 export 变量灌进 os.environ；已存在的不覆盖。

    返回 {变量名: 是否就绪}。strict=True 且缺必需项时抛 SystemExit。
    """
    p = Path(path) if path else ENV_FILE
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export ") and "=" in line:
                k, v = line[7:].split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    status = {k: bool(os.environ.get(k)) for k in required}
    if strict:
        missing = [k for k, ok in status.items() if not ok]
        if missing:
            raise SystemExit("致命：缺少 " + "、".join(missing) + "（检查 " + str(p) + "；或先 export）")
    return status


def env_status() -> dict:
    """不抛异常地返回全部相关变量状态（用于诊断输出）。"""
    keys = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL")
    return {k: bool(os.environ.get(k)) for k in keys}


if __name__ == "__main__":
    load_env(strict=False)
    for k, ok in env_status().items():
        print(("  [OK]   " if ok else "  [缺失] ") + k)
    print("env 文件:", ENV_FILE, "存在" if ENV_FILE.exists() else "不存在")
