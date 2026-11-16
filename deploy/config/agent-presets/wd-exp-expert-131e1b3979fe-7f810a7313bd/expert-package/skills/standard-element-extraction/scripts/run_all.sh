#!/usr/bin/env bash
# 一键回归：本体 → lint → benchmark
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$PWD"; MANIFEST="$HERE/manifest.json"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2;;
    --manifest) MANIFEST="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
[[ -f "$MANIFEST" ]] || { echo "缺少 manifest：$MANIFEST"; exit 2; }

SES_LIST=$(python3 -c "
import json,sys,os
d=json.load(open(sys.argv[1])); r=sys.argv[2]
print(' '.join(os.path.join(r,m['ses']) if not os.path.isabs(m['ses']) else m['ses'] for m in d['standards']))
" "$MANIFEST" "$ROOT")

echo "== 0 本体校验"
python3 "$HERE/validate_ontology.py" --ses $SES_LIST
echo "== 1 lint"
python3 "$HERE/cap.py" lint --ses $SES_LIST
echo "== 2 benchmark"
python3 "$HERE/benchmark.py" --manifest "$MANIFEST" --root "$ROOT"
echo "== ALL PASS"
