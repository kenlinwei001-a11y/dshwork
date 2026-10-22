#!/usr/bin/env bash
# 健康检查：应用需要 ?token=，401/403 也算"活着"
set -e
PORT="$WORKDSH_PREVIEW_PORT"
if [ -z "$PORT" ]; then PORT="18989"; fi
code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null || true)"
shown="$code"
if [ -z "$shown" ]; then shown="none"; fi
case "$code" in
  200|302|401|403) echo "healthy (HTTP $code)"; exit 0 ;;
  *) echo "unhealthy (HTTP $shown)"; exit 1 ;;
esac
