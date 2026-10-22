#!/usr/bin/env bash
# 把 deploy/config/ 里存档的本机配置**装进**目标部署。
#
# 为什么需要它：deploy/config/ 只是"存档"，没有任何东西会把它们装进去；
# 不跑这个脚本，克隆下来的人就看不到 skill / 专家 / MCP / 预设——文件在，系统里没有。
#
# 用法：
#   bash deploy/scripts/install-local-config.sh [DSH_HOME] [DSH_AGENTS_HOME]
#   默认 DSH_HOME=$HOME/workdsh/.test-runtime/preview
#        DSH_AGENTS_HOME=$HOME/.agents      （技能装到这里，与 launchd 的 env 一致）
# 可用环境变量覆盖：
#   MCP_SERVERS_ROOT   本机 MCP server 包所在地（filesystem / playwright 用），默认 $HOME/workdsh-mcp-servers
#   SEMANTICA_VENV     semantica 的 venv，默认 $HOME/.venvs/semantica
#   DRY_RUN=1          只打印不落盘
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"        # deploy/
REPO="$(cd "$HERE/.." && pwd)"                  # 仓库根
SRC="$HERE/config"

DSH_HOME="${1:-$HOME/workdsh/.test-runtime/preview}"
AGENTS_HOME="${2:-$HOME/.agents}"
MCP_SERVERS_ROOT="${MCP_SERVERS_ROOT:-$HOME/workdsh-mcp-servers}"
SEMANTICA_VENV="${SEMANTICA_VENV:-$HOME/.venvs/semantica}"
OLD_HOME="/Users/apple"
NODE_BIN="$(command -v node || true)"
PY_BIN="$(command -v python3.11 || command -v python3 || true)"

[ -d "$SRC" ] || { echo "✗ 找不到 $SRC"; exit 1; }
run() { if [ "${DRY_RUN:-0}" = "1" ]; then echo "  [dry] $*"; else "$@"; fi; }

# macOS 的 sed 用 -i ''，GNU sed（Linux/WSL）用 -i；自动选。
sed_in_place() {
  if sed --version >/dev/null 2>&1; then sed -i "$@"; else sed -i '' "$@"; fi
}

# 路径改写：把存档里写死的原作者路径，换成本机等价物。
# 按前缀从长到短排，避免 /Users/apple/workdsh 先吃掉 /Users/apple/workdsh-mcp-servers。
rewrite() {
  local f="$1"
  [ "${DRY_RUN:-0}" = "1" ] && return 0
  [ -f "$f" ] || return 0
  local args=(
    -e "s#${OLD_HOME}/workdsh-mcp-servers#${MCP_SERVERS_ROOT}#g"
    -e "s#${OLD_HOME}/workdsh/.test-runtime/preview#${DSH_HOME}#g"
    -e "s#${OLD_HOME}/Desktop/workdsh#${REPO}#g"
    -e "s#${OLD_HOME}/.venvs/semantica#${SEMANTICA_VENV}#g"
    -e "s#${OLD_HOME}/.semantica#${HOME}/.semantica#g"
    -e "s#${OLD_HOME}/mcp-workspace#${HOME}/mcp-workspace#g"
  )
  [ -n "$NODE_BIN" ] && args+=(-e "s#/usr/local/bin/node#${NODE_BIN}#g")
  [ -n "$PY_BIN" ] && args+=(-e "s#/usr/local/bin/python3.11#${PY_BIN}#g")
  sed_in_place "${args[@]}" "$f"
}
# 对整棵树里的文本文件做改写（函数在 find -exec 的子 shell 里不可见，所以用 while 读）
rewrite_tree() {
  local dir="$1"
  [ "${DRY_RUN:-0}" = "1" ] && return 0
  find "$dir" -type f \( -name '*.md' -o -name '*.json' -o -name '*.yml' -o -name '*.yaml' \
       -o -name '*.txt' -o -name '*.sh' -o -name '*.py' \) -print0 2>/dev/null \
    | while IFS= read -r -d '' f; do rewrite "$f"; done
}

echo "== 目标 =="
echo "  DSH_HOME        : $DSH_HOME"
echo "  DSH_AGENTS_HOME : $AGENTS_HOME"
echo "  MCP servers 根  : $MCP_SERVERS_ROOT"
echo "  semantica venv  : $SEMANTICA_VENV"
echo

echo "== 1/4 技能 =="
run mkdir -p "$AGENTS_HOME/skills"
n=0
for d in "$SRC/skills"/*/; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  run rm -rf "$AGENTS_HOME/skills/$name"
  run cp -R "$d" "$AGENTS_HOME/skills/$name"
  rewrite_tree "$AGENTS_HOME/skills/$name"
  n=$((n+1))
done
echo "  装了 $n 个技能 -> $AGENTS_HOME/skills"

echo "== 2/4 MCP 连接器 =="
DEST="$DSH_HOME/storages/workdsh_connectors/definitions"
run mkdir -p "$DEST"
warned=0
for f in "$SRC/mcp-connectors"/*.json; do
  [ -f "$f" ] || continue
  b="$(basename "$f")"
  [ "$b" = "global.json" ] && continue
  run cp "$f" "$DEST/$b"
  rewrite "$DEST/$b"
  # 自检：命令不存在就明确告警，别让人拿到一条"看着有、实际起不来"的死配置
  if [ "${DRY_RUN:-0}" != "1" ] && [ -n "$PY_BIN" ]; then
    cmd=$("$PY_BIN" -c "import json,sys;r=json.load(open(sys.argv[1],encoding='utf-8'))['record'];print(r.get('command',''))" "$DEST/$b" 2>/dev/null || echo "")
    if [ -n "$cmd" ] && [ ! -x "$cmd" ] && ! command -v "$cmd" >/dev/null 2>&1; then
      echo "    ⚠ $b: 命令不存在 -> ${cmd}（该 MCP 起不来，需先装对应依赖）"; warned=$((warned+1))
    fi
  fi
done
echo "  已装到 ${DEST}（$warned 条命令缺失）"

if [ "${SKIP_EXPERTS:-0}" = "1" ]; then
  echo "== 3/4 专家 =="
  echo "  [skip] SKIP_EXPERTS=1：保留目标里已有/已恢复的专家与预设"
  echo "== 4/4 Agent 预设 =="
  echo "  [skip] SKIP_EXPERTS=1"
else
  echo "== 3/4 专家 =="
  run mkdir -p "$DSH_HOME/storages/workdsh_experts"
  for sub in experts preferences revisions; do
    [ -d "$SRC/experts/$sub" ] || continue
    run cp -R "$SRC/experts/$sub" "$DSH_HOME/storages/workdsh_experts/" 2>/dev/null || true
  done
  echo "  已装 experts / preferences / revisions"
  echo "  跳过 bindings/：那是按会话绑定的状态，换机器后对应的会话不存在（装了也没用）"

  echo "== 4/4 Agent 预设 =="
  if [ -d "$SRC/agent-presets" ]; then
    run mkdir -p "$DSH_HOME/.agent-presets"
    run cp -R "$SRC/agent-presets/." "$DSH_HOME/.agent-presets/"
    echo "  已装到 $DSH_HOME/.agent-presets"
  fi
fi

cat <<EOF

装完了。剩下两件要人工：
  1. 重启服务让配置生效（launchctl kickstart -k gui/\$(id -u)/com.workdsh.preview）
  2. 上面报"命令不存在"的 MCP，先装对应依赖再重启；否则它在列表里但起不来

注意：plugin-manifest/ 没有安装——那份 package.json 里写的是本机缓存 tarball 的绝对路径，
属于安装过程的产物，应由 install-preview 流程重新生成，不能照抄。
EOF
