#!/bin/sh
# Semantica 外部核验一键链：只读语料包，产物写入 <corpus>/外部核验/
# 用法: KP_CORPUS_DIR=/path/to/语料包 sh run_all.sh
set -e
SP="${SEMANTICA_PY:-/Users/apple/.venvs/semantica/bin/python}"
D=$(cd "$(dirname "$0")" && pwd)
if [ -f /Users/apple/.semantica/env ]; then . /Users/apple/.semantica/env; fi
echo "[preflight] 凭据载入自检"; "$SP" "$D/semantica_env.py" || exit 1
for s in semantica_p0 semantica_p1p2 semantica_p1a_refine semantica_report semantica_rule_judge semantica_normalize_queue semantica_refine_confidence semantica_merge_judges semantica_make_review_md; do
  echo "[run] $s"; "$SP" "$D/$s.py"
done
if [ -n "$DEEPSEEK_API_KEY" ]; then
  for s in semantica_judge_test semantica_judge_bulk; do echo "[run-llm] $s"; "$SP" "$D/$s.py"; done
else
  echo "[skip] 未设置 DEEPSEEK_API_KEY，跳过 LLM 判官两脚本"
fi
echo done
