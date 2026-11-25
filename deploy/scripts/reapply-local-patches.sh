#!/usr/bin/env bash
# 重打"会被升级冲掉"的本地补丁。装完/升级完插件后跑一次即可（可重复执行，已打的会跳过）。
#
# 什么时候必须跑：
#   - `dsh plugin add/update dsh-mcp-connector` 之后（node_modules 被重装 ⇒ 侧栏入口会重新冒出来）
#   - `dsh plugin add/update @xiaoso/dsh-workflow-lite` 之后（左侧导航/右侧面板入口、rule 宽容补丁会消失）
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

echo "== @xiaoso/dsh-workflow-lite：左侧导航 + 右侧面板入口 =="
WL="$DSH_HOME/profiles/$PROFILE/node_modules/@xiaoso/dsh-workflow-lite/lib/client.js"
if [ ! -f "$WL" ]; then
  echo "  跳过：找不到 $WL"
else
  node "$HERE/patches/workflow-lite/patch-workflow-lite-dock.mjs" "$WL"
  node "$HERE/patches/workflow-lite/patch-workflow-lite-nav.mjs" "$WL"
  for marker in workflow-lite-nav workflow-lite-dock; do
    if grep -q "$marker" "$WL"; then
      echo "  ✓ $marker"
    else
      echo "  ✗ $marker 未生效，请人工检查 $WL"; exit 1
    fi
  done
  WL_INDEX="$DSH_HOME/profiles/$PROFILE/node_modules/@xiaoso/dsh-workflow-lite/lib/index.mjs"
  if [ -f "$WL_INDEX" ]; then
    node "$HERE/patches/workflow-lite/patch-workflow-lite-rule.mjs" "$WL_INDEX"
    if grep -q "rule_object" "$WL_INDEX"; then
      echo "  ✓ rule_object"
    else
      echo "  ✗ rule_object 未生效，请人工检查 $WL_INDEX"; exit 1
    fi
  fi
fi

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

echo "== dsh-moki-taskboard：0.2.1 路由兼容垫片 =="
MOKI_HOST="$DSH_HOME/profiles/$PROFILE/node_modules/dsh-moki-taskboard/dist/host.mjs"
if [ ! -f "$MOKI_HOST" ]; then
  echo "  跳过：找不到 $MOKI_HOST"
else
  if node "$HERE/patches/moki-taskboard/patch-moki-route.mjs" --home "$DSH_HOME" --profile "$PROFILE"; then
    if grep -q 'route.resource(req, admitted.peer)' "$MOKI_HOST"; then
      echo "  ✓ moki route shim"
    else
      echo "  ✗ moki route shim 未生效，请人工检查 $MOKI_HOST"; exit 1
    fi
  else
    echo "  ⚠ moki route shim 未应用（插件布局未知？不阻断）"
  fi
fi

cat <<'EOF'

提醒：这些补丁改的是第三方包（dsh-mcp-connector / @xiaoso/dsh-workflow-lite / dsh-moki-taskboard），每次插件升级都会没；
重跑本脚本即可；moki 另有 launchd 看守会每隔几十秒自动重打，正常升级后无需手工处理。
另：semantica 的补丁在 venv 里，升级 semantica 后需重跑 install-semantica-mcp.sh。
EOF
