#!/usr/bin/env bash
# 重打"会被升级冲掉"的本地补丁。装完/升级完插件后跑一次即可（可重复执行，已打的会跳过）。
#
# 什么时候必须跑：
#   - `dsh plugin add/update dsh-mcp-connector` 之后（node_modules 被重装 ⇒ 侧栏入口会重新冒出来）
#   - 重装 preview profile 之后
# 用法：
#   bash deploy/scripts/reapply-local-patches.sh [DSH_HOME] [profile 名]
#   默认 DSH_HOME=~/workdsh/.test-runtime/preview，profile=preview
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
DSH_HOME="${1:-$HOME/workdsh/.test-runtime/preview}"
PROFILE="${2:-preview}"
PKG="$DSH_HOME/profiles/$PROFILE/node_modules/dsh-mcp-connector"
PATCH_FILE="$HERE/patches/dsh-mcp-connector-hide-sidebar-entry.patch"

echo "== dsh-mcp-connector：隐藏侧栏入口的补丁 =="
if [ ! -d "$PKG" ]; then
  echo "  跳过：找不到 $PKG"; exit 0
fi
if [ ! -f "$PATCH_FILE" ]; then
  echo "  ✗ 缺补丁：$PATCH_FILE"; exit 1
fi

BEFORE="$(grep -c 'sidebarVisible = false' "$PKG/lib/client.js" || true)"
if [ "$BEFORE" -ge 1 ]; then
  echo "  已打过，跳过（幂等）"
else
  # patch 对"已应用的 hunk"会返回非零，且 --forward 仍会落 .rej；这里兜住并清理
  ( cd "$PKG" && patch -p1 --batch --forward < "$PATCH_FILE" ) || true
  rm -f "$PKG/lib/"*.rej
fi
AFTER="$(grep -c 'sidebarVisible = false' "$PKG/lib/client.js" || true)"

# 判据：补丁后 client.js 里应恰好有 1 处 "sidebarVisible = false"（原来的初值）
if [ "$AFTER" -ge 1 ]; then
  echo "  ✓ 已生效（补丁前 $BEFORE 处 → 现在 $AFTER 处）"
else
  echo "  ✗ 补丁后仍未见 sidebarVisible = false，请人工检查 $PKG/lib/client.js"; exit 1
fi

# 兜底核对：两处都应改到位（初值 + 未就绪回落）
if grep -q 'snapshot.value?\.\[SHOW_SIDEBAR_ENTRY_FIELD\] !== false' "$PKG/lib/client.js" \
   && awk '/function resolveSidebarVisible/,/^\t\t}/' "$PKG/lib/client.js" | grep -q ': false;'; then
  echo "  ✓ 回落分支也已改到位"
else
  echo "  ⚠ 回落分支未见 : false; —— 入口可能仍会显示，请人工检查"
fi

cat <<'EOF'

提醒：这个补丁改的是第三方包，每次插件升级都会没；升级后重跑本脚本即可。
另：semantica 的补丁在 venv 里，升级 semantica 后需重跑 install-semantica-mcp.sh。
EOF
