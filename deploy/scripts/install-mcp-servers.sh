#!/usr/bin/env bash
# 装 MCP 服务端程序包（playwright / filesystem / sequential-thinking）。
#
# 为什么需要它：deploy/config/mcp-connectors/ 里的 playwright 与 filesystem 两个定义，
# 指向 <MCP_SERVERS_ROOT>/node_modules/... 下的入口文件——那是另装的 npm 包，不在仓库里。
# 不跑本脚本，这两条 MCP 会出现在列表里但连不上（install-local-config.sh 会明确告警）。
#
# 用法：
#   bash deploy/scripts/install-mcp-servers.sh [目标目录]
#   默认目标 $HOME/workdsh-mcp-servers（与 install-local-config.sh 的 MCP_SERVERS_ROOT 一致）
#   DRY_RUN=1 只打印
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"        # deploy/
SRC="$HERE/mcp-servers"
ROOT="${1:-${MCP_SERVERS_ROOT:-$HOME/workdsh-mcp-servers}}"

[ -f "$SRC/package.json" ] || { echo "✗ 缺 $SRC/package.json"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "✗ 找不到 npm（需要 Node.js）"; exit 1; }
run() { if [ "${DRY_RUN:-0}" = "1" ]; then echo "  [dry] $*"; else "$@"; fi; }

echo "== 安装 MCP 服务端包 =="
echo "  目标: $ROOT"
node -e "const p=require('$SRC/package.json');for(const [k,v] of Object.entries(p.dependencies))console.log('    '+k+' '+v)" 2>/dev/null || true

run mkdir -p "$ROOT"
run cp "$SRC/package.json" "$SRC/package-lock.json" "$ROOT/"
echo "== npm install（用 lockfile 锁版本）=="
if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "  [dry] (cd '$ROOT' && npm ci)"
else
  ( cd "$ROOT" && npm ci --no-audit --no-fund )
fi

echo "== 自检：两个入口文件是否就位 =="
fail=0
for f in "node_modules/@playwright/mcp/cli.js" "node_modules/@modelcontextprotocol/server-filesystem/dist/index.js"; do
  if [ -f "$ROOT/$f" ]; then echo "  ✓ $f"; else echo "  ✗ $f 缺失"; fail=1; fi
done

cat <<EOF

装完了（${ROOT}）。两个入口都在的话，重启服务后 playwright / filesystem 两条 MCP 就能连上。
若 install-local-config.sh 报过"命令不存在"，跑完本脚本重跑它一次即可（或直接重启服务）。
EOF
exit $fail
