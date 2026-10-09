"""kp_toolkit 命令行入口。

用法：
  python -m kp_toolkit.cli segment <text|@file>        # 分句
  python -m kp_toolkit.cli chunk  <text|@file>         # 分块
  python -m kp_toolkit.cli validate-graph <graph.json> # 图谱校验
"""
from __future__ import annotations
import json
import sys

from .segmentation import segment_sentences, segment_chunks
from .graph import validate_graph


def _read_arg(s: str) -> str:
    if s.startswith("@"):
        with open(s[1:], encoding="utf-8") as f:
            return f.read()
    return s


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法见模块 docstring", file=sys.stderr)
        return 2
    cmd = argv[1]
    if cmd == "segment":
        print(json.dumps(segment_sentences(_read_arg(argv[2])), ensure_ascii=False, indent=2))
    elif cmd == "chunk":
        print(json.dumps(segment_chunks(_read_arg(argv[2])), ensure_ascii=False, indent=2))
    elif cmd == "validate-graph":
        with open(argv[2], encoding="utf-8") as f:
            graph = json.load(f)
        print(json.dumps(validate_graph(graph), ensure_ascii=False, indent=2))
    else:
        print(f"未知命令 {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
