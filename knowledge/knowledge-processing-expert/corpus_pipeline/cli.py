"""corpus_pipeline 命令行入口。

用法：
  python -m corpus_pipeline.cli run <file.txt|file.md> [--out DIR] [--legal outline.yaml]
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from . import run_pipeline
from .readers import read_document


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "run":
        print(__doc__, file=sys.stderr)
        return 2
    src = Path(argv[2])
    out = Path("corpus-package")
    legal = None
    i = 3
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out = Path(argv[i + 1]); i += 2
        elif argv[i] == "--legal" and i + 1 < len(argv):
            legal = json.loads(Path(argv[i + 1]).read_text(encoding="utf-8")); i += 2
        else:
            i += 1
    raw, _kind = read_document(src)
    result = run_pipeline(raw, out, legal)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
