#!/usr/bin/env bash
# WorkDSH Linux 服务器一键部署（浏览器模式）
#
# 用法：
#   sudo bash deploy/bootstrap-linux.sh                     # 反代拓扑：应用只听 127.0.0.1:18989
#   sudo bash deploy/bootstrap-linux.sh --public            # 直接监听 0.0.0.0（无 TLS，需防火墙兜底）
#   sudo bash deploy/bootstrap-linux.sh --nginx-host dsh.example.com
#   bash deploy/bootstrap-linux.sh --no-systemd             # 无 sudo 时用 nohup
#   bash deploy/bootstrap-linux.sh --dry-run
#   bash deploy/bootstrap-linux.sh --ref main --port 18989 --heap 4096
#   bash deploy/bootstrap-linux.sh --with-sessions
#
# 不做的事：不配 TLS、不开防火墙、不写模型 API Key（应用用 ?token= 登录，启动时打印）。
set -euo pipefail

VERSION="1"
REPO_URL="https://github.com/kenlinwei001-a11y/dshwork.git"
REF=""
DIR="$HOME/workdsh"
PORT="18989"
BIND="127.0.0.1"
HEAP="8192"
SKIP=""
DRY=0
START=1
DO_BUILD=1
WITH_SESSIONS=0
FORCE_SKILLS=0
AS_JSON=0
USE_SYSTEMD=1
NGINX_NAME=""
WARN_FILE="$(mktemp)"
trap 'rm -f "$WARN_FILE"' EXIT

usage() { sed -n '2,15p' "$0"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --ref) [ -n "$2" ] || { echo "--ref 需要值"; exit 2; }; REF="$2"; shift 2 ;;
    --dir) [ -n "$2" ] || { echo "--dir 需要值"; exit 2; }; DIR="$2"; shift 2 ;;
    --port) [ -n "$2" ] || { echo "--port 需要值"; exit 2; }; PORT="$2"; shift 2 ;;
    --bind) [ -n "$2" ] || { echo "--bind 需要值"; exit 2; }; BIND="$2"; shift 2 ;;
    --heap) [ -n "$2" ] || { echo "--heap 需要值"; exit 2; }; HEAP="$2"; shift 2 ;;
    --public) BIND="0.0.0.0"; shift ;;
    --nginx-host) [ -n "$2" ] || { echo "--nginx-host 需要值"; exit 2; }; NGINX_NAME="$2"; shift 2 ;;
    --skip) SKIP="$2"; shift 2 ;;
    --with-sessions) WITH_SESSIONS=1; shift ;;
    --force-skills) FORCE_SKILLS=1; shift ;;
    --no-start) START=0; shift ;;
    --no-build) DO_BUILD=0; shift ;;
    --no-systemd) USE_SYSTEMD=0; shift ;;
    --dry-run) DRY=1; shift ;;
    --json) AS_JSON=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1"; exit 2 ;;
  esac
done

skipped() { case ",$SKIP," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }
step() { echo; echo "───────────────────────────────────────────"; echo "▶ $*"; echo "───────────────────────────────────────────"; }
ok() { echo "  [OK] $*"; }
warn() { echo "  [WARN] $*"; echo "$*" >> "$WARN_FILE"; }
die() { echo "  [FAIL] $*" >&2; exit 1; }
run() { if [ "$DRY" = "1" ]; then echo "  [dry] $*"; else "$@"; fi; }
runsh() { if [ "$DRY" = "1" ]; then echo "  [dry] bash $*"; else bash "$@"; fi; }
trap 'die "第 $LINENO 行失败（看上面输出）"' ERR

SUDO=""
if [ "$(id -u)" = "0" ]; then SUDO=""; elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then SUDO="sudo"; fi
RUN_USER="$(id -un)"; RUN_GROUP="$(id -gn)"
POWER_DESC="root"
if [ -n "$SUDO" ]; then POWER_DESC="sudo"; fi
DSH_HOME="$HOME/.workdsh/preview"
AGENTS_HOME="$HOME/.agents"
MCP_SERVERS_ROOT="$HOME/workdsh-mcp-servers"
SEMANTICA_VENV="$HOME/.venvs/semantica"
SERVICE="workdsh-preview"

echo "WorkDSH Linux 服务器部署 v$VERSION"
echo "  目录:   $DIR"
echo "  监听:   $BIND:$PORT  HEAP $HEAP MB"
echo "  服务:   $SERVICE  systemd=$USE_SYSTEMD  权限=$POWER_DESC"
echo "  DSH:    $DSH_HOME"
echo "  AGENTS: $AGENTS_HOME"
if [ "$DRY" = "1" ]; then echo "  模式:   DRY-RUN"; fi

step "0/9 预检"
if [ "$DRY" != "1" ]; then
  if [ "$(uname -s)" != "Linux" ]; then die "这是 $(uname -s)：服务器版只支持 Linux（WSL 用 bootstrap-wsl.sh，macOS 用 setup-all.sh）"; fi
fi
for bin in git node corepack python3 patch curl; do
  if command -v "$bin" >/dev/null 2>&1; then ok "$bin: $("$bin" --version 2>/dev/null | head -1)"; else die "缺 $bin：apt install -y git curl build-essential patch python3 python3-venv python3-dev；Node 需 ^22.19 或 >=24"; fi
done
NODE_V="$(node -v | sed 's/^v//')"; NODE_MAJOR="$(echo "$NODE_V" | cut -d. -f1)"; NODE_MINOR="$(echo "$NODE_V" | cut -d. -f2)"
if [ "$NODE_MAJOR" -ge 24 ] || { [ "$NODE_MAJOR" -eq 22 ] && [ "$NODE_MINOR" -ge 19 ]; }; then ok "Node $NODE_V 符合 engines"; else warn "Node $NODE_V 不满足 ^22.19 或 >=24"; fi
PY_V="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
case "$PY_V" in 3.10|3.11|3.12|3.13) ok "python3 $PY_V" ;; *) warn "python3 $PY_V 不在 3.10-3.13" ;; esac
if [ "$BIND" = "0.0.0.0" ]; then warn "监听 0.0.0.0：应用只有 ?token= 登录、无 TLS；公网请加反代+HTTPS 或防火墙白名单"; fi
if [ "$USE_SYSTEMD" = "1" ] && [ -z "$SUDO" ] && [ "$(id -u)" != "0" ]; then warn "无 root/sudo：无法装 systemd 服务，退化为 nohup"; USE_SYSTEMD=0; fi

step "1/9 获取仓库"
if [ -d "$DIR/.git" ]; then
  ok "已存在：$DIR"
  run git -C "$DIR" fetch --all --prune --quiet || warn "git fetch 失败，继续用现有提交"
  if [ -n "$REF" ]; then run git -C "$DIR" checkout -q "$REF" || die "切到 $REF 失败"; fi
else
  run mkdir -p "$(dirname "$DIR")"
  run git clone "$REPO_URL" "$DIR" || die "克隆失败"
  if [ -n "$REF" ]; then run git -C "$DIR" checkout -q "$REF"; fi
  ok "已克隆"
fi
if [ "$DRY" = "1" ]; then echo "  [dry] cd $DIR"; else cd "$DIR"; [ -f deploy/scripts/install-local-config.sh ] || die "仓库结构不对"; ok "HEAD=$(git rev-parse --short HEAD)"; fi

step "2/9 Web 依赖 / 构建 / Profile"
if skipped build; then warn "--skip build：Profile 不会安装"; else
  if [ "$DRY" = "1" ]; then
    echo "  [dry] cd $DIR/apps/web"
    echo "  [dry] corepack enable && corepack pnpm install --frozen-lockfile"
    if [ "$DO_BUILD" = "1" ]; then echo "  [dry] corepack pnpm build"; fi
    echo "  [dry] WORKDSH_PREVIEW_HOME=$DSH_HOME corepack pnpm preview:install"
  else
    cd "$DIR/apps/web"
    if ! corepack enable >/dev/null 2>&1; then
      if [ -n "$SUDO" ]; then $SUDO corepack enable; else die "corepack enable 失败且无 sudo"; fi
    fi
    corepack pnpm install --frozen-lockfile
    if [ "$DO_BUILD" = "1" ]; then corepack pnpm build; else warn "--no-build 跳过构建"; fi
    WORKDSH_PREVIEW_HOME="$DSH_HOME" DSH_AGENTS_HOME="$AGENTS_HOME" corepack pnpm preview:install
    cd "$DIR"; ok "Profile 安装完成"
  fi
fi

step "3/9 知识处理 venv + 基础技能"
if skipped knowledge; then warn "--skip knowledge"; else
  if [ -f "$DIR/knowledge/setup.sh" ]; then
    if [ "$FORCE_SKILLS" = "1" ]; then runsh "$DIR/knowledge/setup.sh" --force; else runsh "$DIR/knowledge/setup.sh"; fi
  else warn "缺 knowledge/setup.sh"; fi
fi

step "4/9 MCP 服务端程序包"
if skipped mcp-servers; then warn "--skip mcp-servers"; else
  if [ "$DRY" = "1" ]; then echo "  [dry] MCP_SERVERS_ROOT=$MCP_SERVERS_ROOT bash deploy/scripts/install-mcp-servers.sh"; else
    MCP_SERVERS_ROOT="$MCP_SERVERS_ROOT" bash "$DIR/deploy/scripts/install-mcp-servers.sh" || warn "install-mcp-servers.sh 非零"
  fi
fi

step "5/9 semantica"
if skipped semantica; then warn "--skip semantica"; else
  SEM_PY="python3"
  for c in python3.12 python3.11 python3.10; do if command -v "$c" >/dev/null 2>&1; then SEM_PY="$c"; break; fi; done
  if [ "$DRY" = "1" ]; then echo "  [dry] SEMANTICA_PYTHON=$SEM_PY SEMANTICA_VENV=$SEMANTICA_VENV bash deploy/scripts/install-semantica-mcp.sh"; else
    SEMANTICA_PYTHON="$SEM_PY" SEMANTICA_VENV="$SEMANTICA_VENV" bash "$DIR/deploy/scripts/install-semantica-mcp.sh" || warn "install-semantica-mcp.sh 非零"
  fi
fi

step "6/9 导入存档（技能/专家/MCP/预设）"
if skipped config; then warn "--skip config"; else
  if [ "$DRY" = "1" ]; then echo "  [dry] bash deploy/scripts/install-local-config.sh $DSH_HOME $AGENTS_HOME"; else
    MCP_SERVERS_ROOT="$MCP_SERVERS_ROOT" SEMANTICA_VENV="$SEMANTICA_VENV" bash "$DIR/deploy/scripts/install-local-config.sh" "$DSH_HOME" "$AGENTS_HOME" || warn "install-local-config.sh 非零"
  fi
fi

step "7/9 本地补丁"
if skipped patches; then warn "--skip patches"; else
  if [ -f "$DIR/deploy/scripts/reapply-local-patches.sh" ]; then
    if [ "$DRY" = "1" ]; then echo "  [dry] bash deploy/scripts/reapply-local-patches.sh"; else bash "$DIR/deploy/scripts/reapply-local-patches.sh" || warn "补丁未全部重放"; fi
  else warn "缺 reapply-local-patches.sh"; fi
fi

step "8/9 会话导入"
if [ "$WITH_SESSIONS" != "1" ]; then echo "  （未加 --with-sessions，跳过）"; else
  n=0
  if [ -d "$DIR/会话记录" ]; then
    for d in "$DIR"/会话记录/*/; do
      [ -f "$d/manifest.json" ] || continue
      if [ "$DRY" = "1" ]; then echo "  [dry] import $(basename "$d")"; else bash "$DIR/deploy/scripts/import-session.sh" "$d" || warn "导入失败：$(basename "$d")"; fi
      n=$((n+1))
    done
  fi
  ok "导入 $n 条会话"
fi

step "9/9 安装服务并启动"
NODE_BIN="$(command -v node)"
REPO_ABS="$DIR"
if [ "$DRY" != "1" ]; then REPO_ABS="$(cd "$DIR" && pwd -P)"; fi
if [ "$START" != "1" ]; then
  echo "  （--no-start）手动启动："
  echo "  cd $REPO_ABS/apps/web && WORKDSH_PREVIEW_HOME=$DSH_HOME WORKDSH_PREVIEW_PORT=$PORT WORKDSH_PREVIEW_HOST=$BIND $NODE_BIN scripts/start-preview.mjs"
elif [ "$DRY" = "1" ]; then
  echo "  [dry] 渲染 systemd 单元 -> /etc/systemd/system/$SERVICE.service 并 enable --now"
else
  if [ "$USE_SYSTEMD" = "1" ]; then
    UNIT_SRC="$REPO_ABS/deploy/systemd/workdsh-preview.service.template"
    [ -f "$UNIT_SRC" ] || die "缺 $UNIT_SRC"
    UNIT_TMP="$(mktemp)"
    sed -e "s#__USER__#$RUN_USER#g" -e "s#__GROUP__#$RUN_GROUP#g" -e "s#__REPO__#$REPO_ABS#g" \
        -e "s#__DSH_HOME__#$DSH_HOME#g" -e "s#__AGENTS_HOME__#$AGENTS_HOME#g" \
        -e "s#__PORT__#$PORT#g" -e "s#__HOST__#$BIND#g" -e "s#__HEAP__#$HEAP#g" \
        -e "s#__NODE__#$NODE_BIN#g" "$UNIT_SRC" > "$UNIT_TMP"
    if [ -n "$SUDO" ]; then
      $SUDO install -m 0644 "$UNIT_TMP" "/etc/systemd/system/$SERVICE.service"
      $SUDO systemctl daemon-reload
      $SUDO systemctl enable "$SERVICE" >/dev/null
      $SUDO systemctl restart "$SERVICE"
    else
      install -m 0644 "$UNIT_TMP" "/etc/systemd/system/$SERVICE.service"
      systemctl daemon-reload
      systemctl enable "$SERVICE" >/dev/null
      systemctl restart "$SERVICE"
    fi
    rm -f "$UNIT_TMP"
    ok "systemd 服务已安装并启动：$SERVICE"
  else
    mkdir -p "$DSH_HOME/logs"
    LOG="$DSH_HOME/logs/preview-server.log"
    ( cd "$REPO_ABS/apps/web" && nohup env WORKDSH_PREVIEW_HOME="$DSH_HOME" DSH_AGENTS_HOME="$AGENTS_HOME" WORKDSH_PREVIEW_PORT="$PORT" WORKDSH_PREVIEW_HOST="$BIND" WORKDSH_PREVIEW_HEAP_MB="$HEAP" "$NODE_BIN" scripts/start-preview.mjs > "$LOG" 2>&1 & echo $! > "$DSH_HOME/preview.pid" )
    ok "nohup 启动，日志 $LOG"
  fi
  i=0; CODE=""
  while [ "$i" -lt 60 ]; do
    CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null || true)"
    case "$CODE" in 200|302|401|403) break ;; esac
    i=$((i+1)); sleep 2
  done
  if [ "$i" -ge 60 ]; then warn "120 秒内 127.0.0.1:$PORT 未响应（看 journalctl -u $SERVICE）"; else ok "本机探活 HTTP $CODE"; fi
  LOGIN=""
  if [ "$USE_SYSTEMD" = "1" ]; then
    LOGIN="$(journalctl -u "$SERVICE" --no-pager -n 400 2>/dev/null | grep -o 'http://[^ ]*token=[A-Za-z0-9_-]*' | tail -1 || true)"
  else
    LOGIN="$(grep -o 'http://[^ ]*token=[A-Za-z0-9_-]*' "$DSH_HOME/logs/preview-server.log" 2>/dev/null | tail -1 || true)"
  fi
  if [ -n "$LOGIN" ]; then
    echo "  登录链接（含令牌，等同密码，不要公开）："
    echo "    $LOGIN"
  else
    warn "未抓到令牌登录链接：journalctl -u $SERVICE | grep token"
  fi
fi

step "反向代理（可选）"
if [ -n "$NGINX_NAME" ]; then
  OUT="$REPO_ABS/deploy/nginx/workdsh.generated.conf"
  if [ "$DRY" = "1" ]; then echo "  [dry] 生成 $OUT（server_name=$NGINX_NAME）"; else
    sed -e "s#__SERVER_NAME__#$NGINX_NAME#g" -e "s#__PORT__#$PORT#g" "$REPO_ABS/deploy/nginx/workdsh.conf.template" > "$OUT"
    ok "已生成 $OUT"
  fi
  echo "  安装："
  echo "    sudo cp $OUT /etc/nginx/conf.d/workdsh.conf"
  echo "    sudo nginx -t && sudo systemctl reload nginx"
  echo "  HTTPS：sudo certbot --nginx -d $NGINX_NAME"
else
  echo "  （未加 --nginx-host；模板见 deploy/nginx/workdsh.conf.template）"
fi

WARN_N="$(wc -l < "$WARN_FILE" | tr -d ' ')"
echo
echo "═══════════════════════════════════════════"
if [ "$WARN_N" -gt 0 ]; then echo "需要你知道的 $WARN_N 条："; nl -ba "$WARN_FILE" | sed 's/^/  /'; echo; fi
cat <<EOF
管理命令：
  systemctl status $SERVICE
  journalctl -u $SERVICE -f
  systemctl restart $SERVICE
数据与日志：$DSH_HOME（备份这一个目录即可）
还差两件只有你能做：模型 API Key；postgresql / tavily 单独添加与授权。
═══════════════════════════════════════════
EOF

if [ "$AS_JSON" = "1" ]; then
  echo "BEGIN_BOOTSTRAP_JSON"
  DSH_HOME="$DSH_HOME" AGENTS_HOME="$AGENTS_HOME" PORT="$PORT" BIND="$BIND" DIR="$REPO_ABS" WARN_FILE="$WARN_FILE" SERVICE="$SERVICE" node - <<'NODE'
const fs=require('node:fs');
const e=process.env;
const cs=p=>{try{return fs.readdirSync(p).filter(d=>fs.existsSync(p+'/'+d+'/SKILL.md')).length}catch{return 0}};
const cj=p=>{try{return fs.readdirSync(p).filter(f=>f.endsWith('.json')).length}catch{return 0}};
let w=[]; try{w=fs.readFileSync(e.WARN_FILE,'utf8').split('\n').filter(Boolean)}catch{}
console.log(JSON.stringify({
  ok:w.length===0, service:e.SERVICE, host:e.BIND, port:Number(e.PORT),
  repo:e.DIR, dshHome:e.DSH_HOME, agentsHome:e.AGENTS_HOME,
  counts:{userSkills:cs(e.AGENTS_HOME+'/skills'),profileSkills:cs(e.DSH_HOME+'/skills'),
    experts:cj(e.DSH_HOME+'/storages/workdsh_experts/experts'),
    revisions:cj(e.DSH_HOME+'/storages/workdsh_experts/revisions'),
    connectors:cj(e.DSH_HOME+'/storages/workdsh_connectors/definitions')},
  warnings:w},null,1));
NODE
  echo "END_BOOTSTRAP_JSON"
fi
