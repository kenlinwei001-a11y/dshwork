#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Semantica MCP 连接器幂等安装进任意 DSH 运行时的 definitions。

背景：DSH 的 MCP 连接器注册在 <运行时home>/storages/workdsh_connectors/definitions/*.json，
不经过「MCP 连接器管理」界面（那里看不到 semantica/kp-*）。新增运行时（如备份 profile、
新 profile）需要同样的定义文件，本脚本负责幂等补齐。

设计约束：
  * 凭据不写进定义：定义只「引用」~/.semantica/env，密钥始终只存在于那一个 600 文件；
  * 备份写到 definitions/ 的【上级】目录，避免加载器枚举时把 .bak 当定义读进来；
  * 幂等：已是目标状态则零改动；仅 args/enabled 等关键字段差异才覆盖；
  * 默认只检查（dry-run），加 --apply 才写盘。

用法：
  python3 install_connector.py                      # 检查所有运行时
  python3 install_connector.py --apply              # 写入所有运行时
  python3 install_connector.py --apply --home /tmp/probe_home
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RUNTIME_ROOT = Path("/Users/apple/workdsh/.test-runtime")
ENV_FILE = Path("/Users/apple/.semantica/env")
VENV_PY = Path("/Users/apple/.venvs/semantica/bin/python")
KG_PATH = "/Users/apple/.semantica/graph.json"

MCP_CMD = (
    "[ -f /Users/apple/.semantica/env ] && . /Users/apple/.semantica/env; "
    "SEMANTICA_KG_PATH=/Users/apple/.semantica/graph.json "
    "exec /Users/apple/.venvs/semantica/bin/python -m semantica.mcp_server"
)

DESCRIPTION = (
    "图原生上下文与决策基础设施（15 工具）：实体/关系抽取、决策记录与检索、先例查找、"
    "因果链、知识图谱增删改查、推理、图分析、导出｜已接入 DeepSeek LLM（凭据取自 ~/.semantica/env）"
)

TARGET = {
    "id": "semantica",
    "title": "Semantica",
    "description": DESCRIPTION,
    "serverName": "semantica",
    "transport": "stdio",
    "command": "/bin/sh",
    "args": ["-c", MCP_CMD],
    "enabled": True,
}

CRITICAL = ("serverName", "transport", "command", "args", "enabled")


def discover_homes() -> list[Path]:
    """运行时 home：含 profiles/ 或 storages/ 的目录。"""
    if not RUNTIME_ROOT.is_dir():
        return []
    out = []
    for d in sorted(RUNTIME_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if (d / "profiles").is_dir() or (d / "storages").is_dir():
            out.append(d)
    return out


def def_path(home: Path) -> Path:
    return home / "storages" / "workdsh_connectors" / "definitions" / "semantica.json"


def load_record(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("record")
    except Exception:
        return None


def same_critical(rec) -> bool:
    if not isinstance(rec, dict):
        return False
    return all(rec.get(k) == TARGET.get(k) for k in CRITICAL)


def check_prereqs() -> list[tuple[bool, str]]:
    rows = []
    rows.append((ENV_FILE.exists(), "凭据文件 " + str(ENV_FILE)))
    if ENV_FILE.exists():
        txt = ENV_FILE.read_text(encoding="utf-8")
        for var in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
            rows.append((("export " + var) in txt, "  含 " + var))
    rows.append((VENV_PY.exists(), "venv python " + str(VENV_PY)))
    if VENV_PY.exists():
        for mod in ("openai", "instructor", "semantica"):
            ok = subprocess.run([str(VENV_PY), "-c", "import " + mod],
                                capture_output=True).returncode == 0
            rows.append((ok, "  可导入 " + mod))
    return rows


def install(home: Path, apply: bool) -> tuple[str, str]:
    """返回 (状态, 说明)。状态：installed / unchanged / updated / would-create / would-update"""
    p = def_path(home)
    rec = load_record(p) if p.exists() else None
    if rec is not None and same_critical(rec):
        return ("unchanged", "已是目标状态（args/enabled 一致）")
    if rec is None:
        if not apply:
            return ("would-create", "缺失 → 将创建 " + str(p))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"version": 1, "record": TARGET}, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8")
        return ("installed", "已创建 " + str(p))
    # 存在但不一致 → 备份到 definitions 的上级目录
    if not apply:
        return ("would-update", "args/enabled 不一致 → 将备份后覆盖")
    backup_dir = home / "storages" / "workdsh_connectors"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(p, backup_dir / ("semantica.json.bak." + stamp))
    merged = dict(rec)
    merged.update(TARGET)
    merged["createdAt"] = rec.get("createdAt", datetime.now().isoformat() + "Z")
    merged["updatedAt"] = datetime.now().isoformat() + "Z"
    p.write_text(json.dumps({"version": 1, "record": merged}, ensure_ascii=False, indent=1) + "\n",
                 encoding="utf-8")
    return ("updated", "已备份到 " + str(backup_dir) + "/semantica.json.bak." + stamp + " 并覆盖")


def main() -> int:
    ap = argparse.ArgumentParser(description="幂等安装 Semantica MCP 连接器到 DSH 运行时")
    ap.add_argument("--apply", action="store_true", help="实际写入（默认只检查）")
    ap.add_argument("--home", action="append", default=None, help="指定运行时 home，可重复")
    ap.add_argument("--skip-prereq", action="store_true", help="跳过前置条件检查")
    args = ap.parse_args()

    homes = [Path(h).expanduser().resolve() for h in args.home] if args.home else discover_homes()
    if not homes:
        print("未发现任何运行时 home"); return 2

    if not args.skip_prereq:
        print("== 前置条件 ==")
        bad = 0
        for ok, label in check_prereqs():
            print(("  [OK]   " if ok else "  [缺失] ") + label)
            bad += 0 if ok else 1
        print()

    print("== 连接器定义（%s） ==" % ("写入模式" if args.apply else "仅检查，未写盘；加 --apply 生效"))
    changed = 0
    for h in homes:
        state, msg = install(h, args.apply)
        changed += 1 if state in ("installed", "updated") else 0
        print("  %-42s %-14s %s" % (str(h), state, msg))
    print()
    if not args.apply:
        print("检查完成；如需写入请加 --apply")
    else:
        print("写入完成，本次改动 %d 个运行时。若对应会话正在运行，需让它重连（新会话或重启 dsh web）后生效。" % changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
