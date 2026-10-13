#!/usr/bin/env bash
# 把 semantica 装成可用的 MCP 服务（独立 venv + 上游 bug 补丁）。
#
# 为什么需要这个脚本：
#   1) semantica 要求 Python >=3.10,<3.14；macOS 自带的是 3.9，直接 pip install 会失败。
#   2) semantica 0.7.0 的 get_graph_analytics 有三个自带 bug，不打补丁这个工具必坏。
#   3) 补丁打在 venv 里，pip 升级会覆盖 —— 升级后请重跑本脚本。
#
# 用法：
#   bash deploy/scripts/install-semantica-mcp.sh
# 可用环境变量覆盖：
#   SEMANTICA_PYTHON   （默认 python3.11）
#   SEMANTICA_VENV     （默认 ~/.venvs/semantica）
#   SEMANTICA_KG_PATH  （默认 ~/.semantica/graph.json，图持久化位置）
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"          # deploy/
PY="${SEMANTICA_PYTHON:-python3.11}"
VENV="${SEMANTICA_VENV:-$HOME/.venvs/semantica}"
KG="${SEMANTICA_KG_PATH:-$HOME/.semantica/graph.json}"
PATCH_FILE="$HERE/patches/semantica-0.7.0-graph-analytics.patch"

command -v "$PY" >/dev/null 2>&1 || { echo "✗ 找不到 ${PY}（semantica 需要 Python >=3.10,<3.14）"; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<(3,14) else 1)' \
  || { echo "✗ $PY 版本不符：$("$PY" -V 2>&1)"; exit 1; }
[ -f "$PATCH_FILE" ] || { echo "✗ 缺补丁：$PATCH_FILE"; exit 1; }

echo "== 1/4 建 venv：$VENV =="
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip

echo "== 2/4 装 semantica[graph-embeddings]（含 gensim，Node2Vec 用）=="
"$VENV/bin/pip" install --quiet 'semantica[graph-embeddings]'

echo "== 3/4 打上游 bug 补丁（可重复执行）=="
SITE="$("$VENV/bin/python" -c 'import os,semantica;print(os.path.dirname(os.path.dirname(semantica.__file__)))')"
# patch 对"已应用的 hunk"返回非零，且 --forward 仍会落 .rej —— 兜住并清理，保证可重复执行
( cd "$SITE" && patch -p1 --batch --forward < "$PATCH_FILE" ) || true
find "$SITE/semantica" -name '*.rej' -delete 2>/dev/null || true
MARK=$("$VENV/bin/python" - <<'EOF'
import semantica, pathlib
n = pathlib.Path(semantica.__file__).parent
hits = sum(1 for p in n.rglob("*.py") if "NOTE(patched)" in p.read_text(encoding="utf-8", errors="ignore"))
print(hits)
EOF
)
echo "   含补丁标记的文件数：${MARK}（应为 3：centrality / community / mcp_server）"

echo "== 4/4 准备图持久化目录 + 输出连接器定义 =="
mkdir -p "$(dirname "$KG")"
OUT="$HERE/connectors/semantica.generated.json"
"$VENV/bin/python" - "$OUT" "$VENV" "$KG" <<'EOF'
import json, sys
out, venv, kg = sys.argv[1], sys.argv[2], sys.argv[3]
cmd = f"SEMANTICA_KG_PATH={kg} exec {venv}/bin/python -m semantica.mcp_server"
rec = {
  "id": "semantica", "title": "Semantica",
  "description": "图原生上下文与决策基础设施（15 工具）：实体/关系抽取、决策记录与检索、先例查找、因果链、知识图谱增删改查、推理、图分析、导出。",
  "serverName": "semantica", "transport": "stdio",
  "command": "/bin/sh", "args": ["-c", cmd],
  "enabled": True,
}
json.dump({"version": 1, "record": rec}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("   已生成：" + out)
EOF

cat <<EOF

装好了。剩下一步（登记到部署里）：
   把 $OUT 复制成 <DSH_HOME>/storages/workdsh_connectors/definitions/semantica.json
   —— 注意只放这一处；放到 storages/mcp_connector.json 会与它同名冲突（serverName already in use）。
自检：重启后 pgrep -f semantica.mcp_server 应有 1 个进程；
      调 get_graph_analytics 应返回 {"node_count":…, "edge_count":…, "top_nodes_by_pagerank":[…], "community_count":…}
EOF
