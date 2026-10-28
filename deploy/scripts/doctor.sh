#!/usr/bin/env bash
# WorkDSH 本地健康巡检：服务、token、文件句柄、审计/文件数量、专家预设、最近启动错误。
# 用法: bash deploy/scripts/doctor.sh [DSH_HOME] [AGENTS_HOME]
set -u
H="${1:-${DSH_HOME:-$HOME/workdsh/.test-runtime/preview}}"
A="${2:-${DSH_AGENTS_HOME:-$HOME/.agents}}"
LABEL="com.workdsh.preview"
LOG="$HOME/Library/Logs/$LABEL.log"
ERR="$HOME/Library/Logs/$LABEL.err"
FAIL=0
ok() { printf 'PASS  %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; FAIL=1; }
warn() { printf 'WARN  %s\n' "$*"; }

echo "== 服务 =="
if lsof -nP -iTCP:18989 -sTCP:LISTEN >/dev/null 2>&1; then ok "18989 已监听"; else bad "18989 未监听（运行 restart-preview.sh）"; fi
if launchctl list 2>/dev/null | grep -q "$LABEL"; then ok "$LABEL 已加载"; else bad "$LABEL 未加载"; fi

echo "== 文件句柄 =="
MAXP=$(sysctl -n kern.maxfilesperproc 2>/dev/null || echo 0)
[ "${MAXP:-0}" -ge 150000 ] && ok "kern.maxfilesperproc=$MAXP" || warn "kern.maxfilesperproc=$MAXP（低于 150000）"
ulimit -n | awk -v n="$(ulimit -n)" 'BEGIN{exit !(n>=150000)}' && ok "当前 shell ulimit -n=$(ulimit -n)" || true

echo "== 数据量 =="
if [ -d "$H" ]; then
  FILES=$(find "$H" -path '*/node_modules' -prune -o -type f -print 2>/dev/null | wc -l | tr -d ' ')
  AUDIT=$(find "$H/storages/workdsh_audit/events" -type f 2>/dev/null | wc -l | tr -d ' ')
  echo "      DSH 文件=$FILES  审计事件=$AUDIT"
  [ "$FILES" -lt 150000 ] && ok "文件数低于 150000" || warn "文件数偏高，检查审计/项目缓存"
  [ "$AUDIT" -lt 100000 ] && ok "审计事件低于 100000" || warn "审计事件偏高，运行 archive-audit-events.py"
else bad "DSH_HOME 不存在: $H"; fi

echo "== 专家预设 =="
if [ -f "$(dirname "$0")/check-expert-presets.mjs" ]; then
  node "$(dirname "$0")/check-expert-presets.mjs" --home "$H" --agents "$A" >/tmp/workdsh-doctor-experts.txt 2>&1
  if [ $? -eq 0 ]; then ok "专家预设全部一致"; else bad "专家预设存在 drift"; tail -8 /tmp/workdsh-doctor-experts.txt; fi
fi

echo "== 最近启动错误 =="
if [ -f "$ERR" ]; then
  RECENT=$(tail -200 "$ERR" 2>/dev/null | grep -cE 'EMFILE|startup failed|did not activate|initialize exceeded' || true)
  RECENT=${RECENT:-0}
  [ "$RECENT" -eq 0 ] && ok "最近 200 行无 EMFILE/启动失败/MCP 超时" || warn "最近 200 行有 $RECENT 处错误/超时"
fi
grep -a 'dsh web:' "$LOG" 2>/dev/null | tail -1 || true
echo
[ "$FAIL" -eq 0 ] && echo "巡检通过" || echo "巡检有失败项"
exit "$FAIL"
