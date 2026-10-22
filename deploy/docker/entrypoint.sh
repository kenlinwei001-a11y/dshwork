#!/usr/bin/env bash
# 容器入口：首次运行把存档装进 /data，然后前台启动 WorkDSH preview。
set -eo pipefail

APP_DIR="$APP_DIR"; if [ -z "$APP_DIR" ]; then APP_DIR="/app"; fi
DSH_HOME="$WORKDSH_PREVIEW_HOME"; if [ -z "$DSH_HOME" ]; then DSH_HOME="/data/dsh"; fi
AGENTS_HOME="$DSH_AGENTS_HOME"; if [ -z "$AGENTS_HOME" ]; then AGENTS_HOME="/data/agents"; fi
PORT="$WORKDSH_PREVIEW_PORT"; if [ -z "$PORT" ]; then PORT="18989"; fi
HOST="$WORKDSH_PREVIEW_HOST"; if [ -z "$HOST" ]; then HOST="0.0.0.0"; fi
HEAP="$WORKDSH_PREVIEW_HEAP_MB"; if [ -z "$HEAP" ]; then HEAP="4096"; fi
MCP_ROOT="$MCP_SERVERS_ROOT"; if [ -z "$MCP_ROOT" ]; then MCP_ROOT="/opt/mcp-servers"; fi
SEM_VENV="$SEMANTICA_VENV"; if [ -z "$SEM_VENV" ]; then SEM_VENV="/opt/venvs/semantica"; fi
SEED_DIR="$SEED_SKILLS_DIR"; if [ -z "$SEED_DIR" ]; then SEED_DIR="/seed/.agents/skills"; fi
IMPORT_SESSIONS="$IMPORT_SESSIONS"; if [ -z "$IMPORT_SESSIONS" ]; then IMPORT_SESSIONS="0"; fi
FORCE_SEED="$FORCE_SEED"; if [ -z "$FORCE_SEED" ]; then FORCE_SEED="0"; fi
DRY="$ENTRYPOINT_DRY_RUN"; if [ -z "$DRY" ]; then DRY="0"; fi

mkdir -p "$DSH_HOME" "$AGENTS_HOME" "$DSH_HOME/logs" "$HOME"

echo "== WorkDSH 容器启动 =="
echo "  APP_DIR : $APP_DIR"
echo "  DSH_HOME: $DSH_HOME"
echo "  AGENTS  : $AGENTS_HOME"
echo "  LISTEN  : $HOST:$PORT   HEAP $HEAP MB"
echo "  MCP     : $MCP_ROOT ; semantica $SEM_VENV"

if [ -d "$SEED_DIR" ]; then
  mkdir -p "$AGENTS_HOME/skills"
  n=0
  for d in "$SEED_DIR"/*/; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    if [ ! -d "$AGENTS_HOME/skills/$name" ]; then
      cp -R "$d" "$AGENTS_HOME/skills/$name"
      n=$((n+1))
    fi
  done
  echo "  基础技能补装：$n 个（已存在不覆盖）"
fi

FIRST=0
if [ ! -d "$DSH_HOME/storages/workdsh_experts/experts" ]; then FIRST=1; fi
if [ "$FIRST" = "1" ] || [ "$FORCE_SEED" = "1" ]; then
  if [ "$FIRST" = "1" ]; then echo "  首次启动：导入存档（技能/专家/MCP/预设）"; else echo "  FORCE_SEED=1：重导存档"; fi
  MCP_SERVERS_ROOT="$MCP_ROOT" SEMANTICA_VENV="$SEM_VENV" \
    bash "$APP_DIR/deploy/scripts/install-local-config.sh" "$DSH_HOME" "$AGENTS_HOME"
else
  echo "  已存在数据，跳过存档导入（要重导设 FORCE_SEED=1）"
fi

if [ "$IMPORT_SESSIONS" = "1" ] && [ -d "$APP_DIR/会话记录" ]; then
  for d in "$APP_DIR"/会话记录/*/; do
    [ -f "$d/manifest.json" ] || continue
    echo "  导入会话：$(basename "$d")"
    bash "$APP_DIR/deploy/scripts/import-session.sh" "$d" || echo "  [WARN] 导入失败：$(basename "$d")"
  done
fi

count_skill() { find "$1" -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l | tr -d ' '; }
count_json() { find "$1" -maxdepth 1 -name '*.json' 2>/dev/null | wc -l | tr -d ' '; }
echo "  技能：用户根 $(count_skill "$AGENTS_HOME/skills") / Profile $(count_skill "$DSH_HOME/skills")"
echo "  专家：$(count_json "$DSH_HOME/storages/workdsh_experts/experts")  连接器：$(count_json "$DSH_HOME/storages/workdsh_connectors/definitions")"

if [ "$DRY" = "1" ]; then
  echo "  ENTRYPOINT_DRY_RUN=1：播种检查完成，退出"
  exit 0
fi

LOG="$DSH_HOME/logs/preview.log"
touch "$LOG"
cd "$APP_DIR/apps/web"
node scripts/start-preview.mjs >> "$LOG" 2>&1 &
PID=$!
cleanup() {
  echo "  收到停止信号，正在退出"
  kill -TERM "$PID" 2>/dev/null || true
  wait "$PID" 2>/dev/null || true
  exit 0
}
trap cleanup TERM INT
tail -n +1 -F "$LOG" &
TAIL_PID=$!
(
  i=0
  while [ "$i" -lt 180 ]; do
    URL="$(grep -oh 'http://[^ ]*token=[A-Za-z0-9_-]*' "$LOG" 2>/dev/null | tail -1 || true)"
    if [ -n "$URL" ]; then
      echo "$URL" > "$DSH_HOME/login-url.txt"
      echo "  登录链接已写入 $DSH_HOME/login-url.txt"
      break
    fi
    i=$((i+1))
    sleep 1
  done
) &
wait "$PID"
kill "$TAIL_PID" 2>/dev/null || true
