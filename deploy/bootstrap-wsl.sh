#!/usr/bin/env bash
# WorkDSH 一键部署（克隆模式）—— WSL2 / Ubuntu（也支持普通 Linux）
#
# 用法：
#   bash deploy/bootstrap-wsl.sh                    # 装到 ~/workdsh，端口 18989
#   bash deploy/bootstrap-wsl.sh --ref main         # 指定分支/提交
#   bash deploy/bootstrap-wsl.sh --dir ~/src/workdsh
#   bash deploy/bootstrap-wsl.sh --with-sessions    # 额外导入仓库自带的会话
#   bash deploy/bootstrap-wsl.sh --no-start         # 只装不启动
#   bash deploy/bootstrap-wsl.sh --dry-run          # 只打印计划（任何系统都能跑）
#   bash deploy/bootstrap-wsl.sh --skip semantica,patches
#   bash deploy/bootstrap-wsl.sh --json             # 末尾输出机器可读汇总
#
# 刻意不做：不写模型 API Key；不替你授权 Tavily/postgresql；不复制他人会话全集。
set -euo pipefail

VERSION="1"
REPO_URL="https://github.com/kenlinwei001-a11y/dshwork.git"
REF=""
DIR="$HOME/workdsh"
PORT="18989"
DSH_HOME="$HOME/.workdsh/preview"
AGENTS_HOME="$HOME/.agents"
MCP_SERVERS_ROOT="$HOME/workdsh-mcp-servers"
SEMANTICA_VENV="$HOME/.venvs/semantica"
SKIP=""
HEAP="8192"
DRY=0
START=1
DO_BUILD=1
WITH_SESSIONS=0
FORCE_SKILLS=0
AS_JSON=0
ALLOW_LINUX=0
RUN_ID="$(date +%Y%m%d-%H%M%S)"
WARN_FILE="$(mktemp)"
RUNNING=0
RC=0
trap 'rm -f "$WARN_FILE"' EXIT

usage() { sed -n '2,20p' "$0"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --ref) [ -n "$2" ] || { echo "--ref 需要值"; exit 2; }; REF="$2"; shift 2 ;;
    --dir) [ -n "$2" ] || { echo "--dir 需要值"; exit 2; }; DIR="$2"; shift 2 ;;
    --repo) [ -n "$2" ] || { echo "--repo 需要值"; exit 2; }; REPO_URL="$2"; shift 2 ;;
    --port) [ -n "$2" ] || { echo "--port 需要值"; exit 2; }; PORT="$2"; shift 2 ;;
    --skip) SKIP="$2"; shift 2 ;;
    --heap) [ -n "$2" ] || { echo "--heap 需要值（MB）"; exit 2; }; HEAP="$2"; shift 2 ;;
    --with-sessions) WITH_SESSIONS=1; shift ;;
    --force-skills) FORCE_SKILLS=1; shift ;;
    --no-start) START=0; shift ;;
    --no-build) DO_BUILD=0; shift ;;
    --dry-run) DRY=1; shift ;;
    --json) AS_JSON=1; shift ;;
    --allow-linux) ALLOW_LINUX=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1（--help 看用法）"; exit 2 ;;
  esac
done

skipped() { case ",$SKIP," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

step() { echo; echo "───────────────────────────────────────────"; echo "▶ $*"; echo "───────────────────────────────────────────"; }
ok()   { echo "  [OK] $*"; }
warn() { echo "  [WARN] $*"; echo "$*" >> "$WARN_FILE"; }
die()  { echo "  [FAIL] $*" >&2; exit 1; }
run()  { if [ "$DRY" = "1" ]; then echo "  [dry] $*"; else "$@"; fi; }
runsh(){ if [ "$DRY" = "1" ]; then echo "  [dry] bash $*"; else bash "$@"; fi; }
trap 'die "第 $LINENO 行失败（看上面的输出）"' ERR

echo "╔══════════════════════════════════════════╗"
echo "║ WorkDSH 克隆模式部署 v$VERSION"
echo "╚══════════════════════════════════════════╝"
echo "  目标目录: $DIR"
if [ -n "$REF" ]; then echo "  引用:     $REF"; else echo "  引用:     默认分支"; fi
echo "  端口:     $PORT（只监听 127.0.0.1，Windows 浏览器经 WSL 转发访问）"
echo "  Node 堆:  $HEAP MB（WORKDSH_PREVIEW_HEAP_MB）"
echo "  DSH_HOME: $DSH_HOME"
echo "  AGENTS:   $AGENTS_HOME"
if [ "$DRY" = "1" ]; then echo "  模式:     DRY-RUN（只打印，不落盘）"; fi

step "0/9 环境预检"
UNAME="$(uname -s)"
if [ "$DRY" != "1" ]; then
  if [ "$UNAME" = "Darwin" ]; then die "这是 macOS：请用 bash deploy/scripts/setup-all.sh；本脚本面向 WSL2/Linux"; fi
  if [ "$UNAME" != "Linux" ]; then die "不支持的系统：$UNAME（请用 WSL2 或 Ubuntu）"; fi
  if ! grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
    if [ "$ALLOW_LINUX" != "1" ]; then die "不是 WSL 环境（/proc/version 无 microsoft）。确认是 Ubuntu/WSL2，或加 --allow-linux"; fi
    warn "非 WSL 的 Linux，已按 --allow-linux 继续"
  fi
else
  echo "  [dry] 跳过平台判定（macOS/Windows 也能 dry-run）"
fi

need() { command -v "$1" >/dev/null 2>&1; }
for bin in git node corepack python3 patch; do
  if need "$bin"; then ok "$bin: $("$bin" --version 2>/dev/null | head -1)"; else
    die "缺 $bin。Ubuntu: sudo apt update && sudo apt install -y git curl build-essential patch python3 python3-venv python3-dev；Node 装 ^22.19 或 >=24"
  fi
done
NODE_V="$(node -v | sed 's/^v//')"
NODE_MAJOR="$(echo "$NODE_V" | cut -d. -f1)"
NODE_MINOR="$(echo "$NODE_V" | cut -d. -f2)"
if [ "$NODE_MAJOR" -ge 24 ] || { [ "$NODE_MAJOR" -eq 22 ] && [ "$NODE_MINOR" -ge 19 ]; }; then
  ok "Node $NODE_V 符合 engines（^22.19.0 或 >=24）"
else
  warn "Node $NODE_V 不满足 engines（需要 ^22.19.0 或 >=24）"
fi
PY_V="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
case "$PY_V" in
  3.10|3.11|3.12|3.13) ok "python3 $PY_V（semantica 要求 3.10-3.13）" ;;
  *) warn "python3 $PY_V 不在 3.10-3.13，semantica 可能装不上" ;;
esac
if need curl; then ok "curl 可用"; else warn "缺 curl，健康检查退化为 node 探测"; fi

step "1/9 获取仓库"
if [ -d "$DIR/.git" ]; then
  ok "已存在仓库：$DIR"
  run git -C "$DIR" fetch --all --prune --quiet || warn "git fetch 失败（离线？）继续用现有提交"
  if [ -n "$REF" ]; then run git -C "$DIR" checkout -q "$REF" || die "切到 $REF 失败"; fi
else
  run mkdir -p "$(dirname "$DIR")"
  run git clone "$REPO_URL" "$DIR" || die "克隆失败：$REPO_URL"
  if [ -n "$REF" ]; then run git -C "$DIR" checkout -q "$REF" || die "切到 $REF 失败"; fi
  ok "已克隆：$REPO_URL"
fi
if [ "$DRY" != "1" ]; then
  [ -d "$DIR" ] || die "目录不存在：$DIR"
  cd "$DIR"
  HEAD="$(git rev-parse --short HEAD)"
  ok "HEAD=$HEAD"
  [ -f deploy/scripts/install-local-config.sh ] || die "仓库结构不对：缺 deploy/scripts/install-local-config.sh"
fi
if [ "$DRY" = "1" ]; then echo "  [dry] 进入 $DIR"; else cd "$DIR"; fi

step "2/9 Web 依赖 / 构建 / Profile 安装"
if skipped build; then
  warn "按 --skip build 跳过（Profile 不会安装，界面起不来）"
else
  if [ "$DRY" = "1" ]; then
    echo "  [dry] cd $DIR/apps/web"
    echo "  [dry] corepack enable"
    echo "  [dry] corepack pnpm install --frozen-lockfile"
    if [ "$DO_BUILD" = "1" ]; then echo "  [dry] corepack pnpm build"; fi
    echo "  [dry] WORKDSH_PREVIEW_HOME=$DSH_HOME DSH_AGENTS_HOME=$AGENTS_HOME corepack pnpm preview:install"
  else
    cd "$DIR/apps/web"
    if ! corepack enable >/dev/null 2>&1; then
      if need sudo; then sudo corepack enable || die "corepack enable 失败"; else die "corepack enable 失败且没有 sudo"; fi
    fi
    ok "corepack 就绪"
    corepack pnpm install --frozen-lockfile
    if [ "$DO_BUILD" = "1" ]; then corepack pnpm build; else warn "按 --no-build 跳过构建"; fi
    WORKDSH_PREVIEW_HOME="$DSH_HOME" DSH_AGENTS_HOME="$AGENTS_HOME" corepack pnpm preview:install
    ok "Profile 安装完成：$DSH_HOME/profiles/preview"
    cd "$DIR"
  fi
fi

step "3/9 知识处理 venv + 6 个基础技能"
if skipped knowledge; then
  warn "按 --skip knowledge 跳过"
else
  if [ -f "$DIR/knowledge/setup.sh" ]; then
    if [ "$FORCE_SKILLS" = "1" ]; then runsh "$DIR/knowledge/setup.sh" --force; else runsh "$DIR/knowledge/setup.sh"; fi
  else
    warn "缺 knowledge/setup.sh，跳过"
  fi
fi

step "4/9 MCP 服务端程序包（filesystem / playwright）"
if skipped mcp-servers; then
  warn "按 --skip mcp-servers 跳过（这两条连接会连不上）"
else
  if [ "$DRY" = "1" ]; then
    echo "  [dry] MCP_SERVERS_ROOT=$MCP_SERVERS_ROOT bash deploy/scripts/install-mcp-servers.sh"
  else
    MCP_SERVERS_ROOT="$MCP_SERVERS_ROOT" bash "$DIR/deploy/scripts/install-mcp-servers.sh" || warn "install-mcp-servers.sh 返回非零"
  fi
fi

step "5/9 semantica MCP（venv + 补丁）"
if skipped semantica; then
  warn "按 --skip semantica 跳过（semantica 连接会连不上）"
else
  SEM_PY="python3"
  for cand in python3.12 python3.11 python3.10; do
    if need "$cand"; then SEM_PY="$cand"; break; fi
  done
  if [ "$DRY" = "1" ]; then
    echo "  [dry] SEMANTICA_PYTHON=$SEM_PY SEMANTICA_VENV=$SEMANTICA_VENV bash deploy/scripts/install-semantica-mcp.sh"
  else
    SEMANTICA_PYTHON="$SEM_PY" SEMANTICA_VENV="$SEMANTICA_VENV" bash "$DIR/deploy/scripts/install-semantica-mcp.sh" || warn "install-semantica-mcp.sh 返回非零"
  fi
fi

step "6/9 导入存档：技能 / 专家 / MCP 连接器 / Agent 预设"
if skipped config; then
  warn "按 --skip config 跳过（界面上将看不到技能与专家）"
else
  if [ "$DRY" = "1" ]; then
    echo "  [dry] bash deploy/scripts/install-local-config.sh $DSH_HOME $AGENTS_HOME"
  else
    MCP_SERVERS_ROOT="$MCP_SERVERS_ROOT" SEMANTICA_VENV="$SEMANTICA_VENV" \
      bash "$DIR/deploy/scripts/install-local-config.sh" "$DSH_HOME" "$AGENTS_HOME" || warn "install-local-config.sh 返回非零"
  fi
fi

step "7/9 重放本地补丁（可选）"
if skipped patches; then
  warn "按 --skip patches 跳过"
else
  if [ -f "$DIR/deploy/scripts/reapply-local-patches.sh" ]; then
    if [ "$DRY" = "1" ]; then
      echo "  [dry] bash deploy/scripts/reapply-local-patches.sh"
    else
      bash "$DIR/deploy/scripts/reapply-local-patches.sh" || warn "补丁未全部重放（插件通常仍可运行）"
    fi
  else
    warn "缺 reapply-local-patches.sh，跳过"
  fi
fi

step "8/9 会话导入"
if [ "$WITH_SESSIONS" != "1" ]; then
  echo "  （未加 --with-sessions，跳过；仓库只带少量脱敏会话）"
else
  n=0
  if [ -d "$DIR/会话记录" ]; then
    for d in "$DIR"/会话记录/*/; do
      if [ -f "$d/manifest.json" ]; then
        if [ "$DRY" = "1" ]; then echo "  [dry] import $(basename "$d")"; else
          bash "$DIR/deploy/scripts/import-session.sh" "$d" || warn "导入失败：$(basename "$d")"
        fi
        n=$((n+1))
      fi
    done
  fi
  ok "导入会话 $n 条"
fi

step "9/9 校验（数清楚，不猜）"
if [ "$DRY" = "1" ]; then
  echo "  [dry] 统计技能/专家/修订/预设/连接器，并逐条检查 MCP 命令是否存在"
else
  count_md() { find "$1" -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l | tr -d ' '; }
  count_json() { find "$1" -maxdepth 1 -name '*.json' 2>/dev/null | wc -l | tr -d ' '; }
  SKILL_N="$(count_md "$AGENTS_HOME/skills")"
  PROF_N="$(count_md "$DSH_HOME/skills")"
  EXP_N="$(count_json "$DSH_HOME/storages/workdsh_experts/experts")"
  REV_N="$(count_json "$DSH_HOME/storages/workdsh_experts/revisions")"
  CONN_N="$(count_json "$DSH_HOME/storages/workdsh_connectors/definitions")"
  PRESET_N="$(find "$AGENTS_HOME/.workdsh-state/experts/presets" -maxdepth 2 -name preset.json 2>/dev/null | wc -l | tr -d ' ')"
  ARCH_SKILL_N="$(count_md "$DIR/deploy/config/skills")"
  ARCH_EXP_N="$(count_json "$DIR/deploy/config/experts/experts")"
  ok "技能：用户根 $SKILL_N / Profile 根 $PROF_N（存档 $ARCH_SKILL_N）"
  ok "专家：$EXP_N（存档 $ARCH_EXP_N）；发布修订 $REV_N；Agent 预设 $PRESET_N"
  ok "MCP 连接器：$CONN_N"
  if [ "$SKILL_N" -lt "$ARCH_SKILL_N" ]; then warn "用户根技能数少于存档（$SKILL_N < $ARCH_SKILL_N）"; fi
  if [ "$EXP_N" -lt "$ARCH_EXP_N" ]; then warn "专家数少于存档（$EXP_N < $ARCH_EXP_N）"; fi
  missing=0
  for f in "$DSH_HOME"/storages/workdsh_connectors/definitions/*.json; do
    [ -f "$f" ] || continue
    cmd="$(node -e 'const j=require(process.argv[1]);const r=j.record||j;process.stdout.write(String(r.command||""))' "$f" 2>/dev/null || true)"
    [ -n "$cmd" ] || continue
    if [ -x "$cmd" ] || command -v "$cmd" >/dev/null 2>&1; then :; else
      warn "MCP $(basename "$f" .json) 的命令不存在：$cmd"
      missing=$((missing+1))
    fi
  done
  if [ "$missing" -eq 0 ]; then ok "所有 MCP 命令均存在"; else warn "$missing 条 MCP 连接的命令缺失（按第 4/5 步补装）"; fi
  if [ -f "$DIR/tools/expert-report/build.mjs" ]; then ok "资料包构建器可用：node tools/expert-report/build.mjs --check"; fi
fi

step "启动服务"
if [ "$START" != "1" ] || [ "$DRY" = "1" ]; then
  echo "  （未启动）手动启动："
  echo "  cd $DIR/apps/web && WORKDSH_PREVIEW_HOME=$DSH_HOME DSH_AGENTS_HOME=$AGENTS_HOME WORKDSH_PREVIEW_PORT=$PORT corepack pnpm preview"
else
  LOG="$DSH_HOME/logs/preview-$RUN_ID.log"
  mkdir -p "$DSH_HOME/logs"
  PIDF="$DSH_HOME/preview.pid"
  if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF" 2>/dev/null)" 2>/dev/null; then
    ok "已有 preview 在运行（pid $(cat "$PIDF")）"
    RUNNING=1
  else
    cd "$DIR/apps/web"
    nohup env WORKDSH_PREVIEW_HOME="$DSH_HOME" DSH_AGENTS_HOME="$AGENTS_HOME" WORKDSH_PREVIEW_PORT="$PORT" WORKDSH_PREVIEW_HEAP_MB="$HEAP" node scripts/start-preview.mjs > "$LOG" 2>&1 &
    echo $! > "$PIDF"
    ok "已启动 pid $(cat "$PIDF")，日志 $LOG"
    cd "$DIR"
  fi
  i=0
  while [ "$i" -lt 90 ]; do
    CODE=""
    if need curl; then CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null || true)"
    else CODE="$(node -e 'fetch("http://127.0.0.1:'"$PORT"'/").then(r=>console.log(r.status)).catch(()=>{})' 2>/dev/null || true)"; fi
    case "$CODE" in
      200|302|401) RUNNING=1; break ;;
    esac
    i=$((i+1))
    sleep 2
  done
  if [ "$RUNNING" = "1" ]; then ok "WSL 内可访问：http://127.0.0.1:$PORT（HTTP $CODE）"; else warn "180 秒内未就绪，看日志：$LOG"; fi
fi

step "浏览器访问（Windows 侧）"
WSL_IP=""
if [ "$DRY" != "1" ] && [ "$UNAME" = "Linux" ] && need hostname; then
  WSL_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
fi
echo "  服务只监听 WSL 内的 127.0.0.1:$PORT。Windows 浏览器打开："
echo "    http://127.0.0.1:$PORT"
if [ -n "$WSL_IP" ]; then
  echo "  若打不开（localhost 转发被关或端口冲突），二选一："
  echo "    A. Windows 管理员 PowerShell："
  echo "       netsh interface portproxy add v4tov4 listenport=$PORT listenaddress=127.0.0.1 connectport=$PORT connectaddress=$WSL_IP"
  echo "    B. 确认 %UserProfile%\\.wslconfig 里有："
  echo "       [wsl2]"
  echo "       localhostForwarding=true"
  echo "  然后 wsl --shutdown 重开 WSL，再跑本脚本。"
fi

WARN_N="$(wc -l < "$WARN_FILE" | tr -d ' ')"
echo
echo "═══════════════════════════════════════════"
if [ "$WARN_N" -gt 0 ]; then
  echo "需要你知道的 $WARN_N 条："
  nl -ba "$WARN_FILE" | sed 's/^/  /'
  echo
fi
cat <<EOF
还差两件只有你能做的事：
  1. 配自己的模型 API Key（不随仓库走）：界面按提示添加，或写 $DSH_HOME/.credentials.yaml
  2. postgresql / tavily 属于 dsh 侧另一套存储：需要时在「MCP 连接器」里添加；Tavily 要浏览器重新授权

常用后续：
  bash $DIR/deploy/bootstrap-wsl.sh                  # 幂等重跑，补齐缺的步骤
  cd $DIR/apps/web && WORKDSH_PREVIEW_HOME=$DSH_HOME corepack pnpm preview   # 前台启动看日志
  node $DIR/tools/expert-report/build.mjs --check    # 资料包是否与机器一致
═══════════════════════════════════════════
EOF

if [ "$AS_JSON" = "1" ]; then
  echo "BEGIN_BOOTSTRAP_JSON"
  DSH_HOME="$DSH_HOME" AGENTS_HOME="$AGENTS_HOME" PORT="$PORT" RUNNING="$RUNNING" DIR="$DIR" WARN_FILE="$WARN_FILE" node - <<'NODE'
const fs = require('node:fs');
const e = process.env;
const countSkill = p => { try { return fs.readdirSync(p).filter(d => fs.existsSync(p + '/' + d + '/SKILL.md')).length; } catch { return 0; } };
const countJson = p => { try { return fs.readdirSync(p).filter(f => f.endsWith('.json')).length; } catch { return 0; } };
const countPreset = p => { try { return fs.readdirSync(p).filter(d => fs.existsSync(p + '/' + d + '/preset.json')).length; } catch { return 0; } };
let warnings = [];
try { warnings = fs.readFileSync(e.WARN_FILE, 'utf8').split('\n').filter(Boolean); } catch {}
const out = {
  ok: warnings.length === 0,
  running: e.RUNNING === '1',
  url: 'http://127.0.0.1:' + e.PORT,
  repo: e.DIR,
  dshHome: e.DSH_HOME,
  agentsHome: e.AGENTS_HOME,
  counts: {
    userSkills: countSkill(e.AGENTS_HOME + '/skills'),
    profileSkills: countSkill(e.DSH_HOME + '/skills'),
    experts: countJson(e.DSH_HOME + '/storages/workdsh_experts/experts'),
    revisions: countJson(e.DSH_HOME + '/storages/workdsh_experts/revisions'),
    connectors: countJson(e.DSH_HOME + '/storages/workdsh_connectors/definitions'),
    presets: countPreset(e.AGENTS_HOME + '/.workdsh-state/experts/presets'),
  },
  warnings,
};
console.log(JSON.stringify(out, null, 1));
NODE
  echo "END_BOOTSTRAP_JSON"
fi
