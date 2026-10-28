#!/usr/bin/env bash
# 稳妥重启 WorkDSH Web 预览，并打印本次启动后的访问 URL。
# 用法: bash deploy/scripts/restart-preview.sh
set -euo pipefail

LABEL="com.workdsh.preview"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/$LABEL.log"
PORT="${WORKDSH_PREVIEW_PORT:-18989}"
[ -f "$PLIST" ] || { echo "找不到 $PLIST" >&2; exit 2; }
STAMP=$(stat -f '%z' "$LOG" 2>/dev/null || echo 0)
echo "== 停 =="
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
sleep 3
echo "== 起 =="
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null \
  || launchctl kickstart -k "gui/$(id -u)/$LABEL" 2>/dev/null \
  || launchctl load -w "$PLIST" 2>/dev/null || true

for _ in $(seq 1 60); do
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && break
  sleep 1
done
if ! lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "启动失败：端口 $PORT 未监听" >&2
  echo "--- 最近日志 ---" >&2
  tail -20 "$LOG" 2>/dev/null >&2 || true
  echo "--- 最近错误 ---" >&2
  tail -20 "$HOME/Library/Logs/$LABEL.err" 2>/dev/null >&2 || true
  exit 1
fi
echo "服务已监听 $PORT"
TOKEN=""
for _ in $(seq 1 40); do
  TOKEN=$(grep -a -b 'dsh web:' "$LOG" 2>/dev/null | awk -F: -v off="$STAMP" '$1>off' | tail -1)
  [ -n "$TOKEN" ] && break
  sleep 1
done
echo "== 访问地址 =="
if [ -n "$TOKEN" ]; then
  echo "$TOKEN" | cut -d: -f2-
else
  echo "新 token 还没打印（可能仍在启动）；请查看 $LOG 最后一条 dsh web:"
  grep -a 'dsh web:' "$LOG" 2>/dev/null | tail -1 || true
fi
echo "浏览器如果还开着旧页面，打开上面的地址并强制刷新（Cmd+Shift+R）。"
