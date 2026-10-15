#!/usr/bin/env bash
# 一条命令把本机系统交接给新部署：skill / 专家 / agent 预设 / MCP / 对话。
#
# 为什么要有它：这些步骤分散在几个脚本里，漏掉任何一步都会"看着装好了、实际缺东西"
# （已经发生过两次：漏 install-local-config ⇒ 界面上看不到 skill/MCP；漏 install-mcp-servers
#  ⇒ MCP 列表里有但连不上）。串成一条，就没机会漏。
#
# 用法：
#   bash deploy/scripts/setup-all.sh                    # 装配置与 MCP（不含对话）
#   bash deploy/scripts/setup-all.sh --with-sessions    # 连对话一起导
#   bash deploy/scripts/setup-all.sh --skip mcp-servers,semantica   # 跳过某些步
# 环境变量：
#   DSH_HOME / DSH_AGENTS_HOME / MCP_SERVERS_ROOT / SEMANTICA_VENV 见各自脚本
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

WITH_SESSIONS=0
SKIP=""
while [ $# -gt 0 ]; do
  case "$1" in
    --with-sessions) WITH_SESSIONS=1; shift ;;
    --skip) SKIP="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done
skipped() { case ",${SKIP}," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

step() { echo; echo "───────────────────────────────────────────"; echo "▶ $*"; echo "───────────────────────────────────────────"; }

cd "$REPO"
echo "仓库: $REPO"
echo "跳过: ${SKIP:-（无）}"

step "1/5 交付包本体（venv + 依赖 + 6 个 skill）"
[ -f knowledge/setup.sh ] && bash knowledge/setup.sh || echo "  ⚠ 缺 knowledge/setup.sh，跳过"

if skipped mcp-servers; then echo "  （按 --skip 跳过 MCP 服务端包）"; else
  step "2/5 MCP 服务端程序包（playwright / filesystem / sequential-thinking）"
  bash "$HERE/install-mcp-servers.sh"
fi

if skipped semantica; then echo "  （按 --skip 跳过 semantica）"; else
  step "3/5 semantica MCP（venv + 上游 bug 补丁）"
  bash "$HERE/install-semantica-mcp.sh"
fi

step "4/5 配置导入：技能 / 专家 / Agent 预设 / MCP 连接器"
bash "$HERE/install-local-config.sh"
echo "  提示：上面若报某条 MCP「命令不存在」，就是它依赖的程序没装——见第 2/3 步。"

if [ "$WITH_SESSIONS" = "1" ]; then
  step "5/5 导入对话"
  n=0
  for d in 会话记录/*/; do
    [ -f "$d/manifest.json" ] || continue
    echo "  → $(basename "$d")"
    bash "$HERE/import-session.sh" "$d" || echo "    ⚠ 导入失败，继续"
    n=$((n+1))
  done
  echo "  共导入 $n 条会话"
else
  echo
  echo "（未加 --with-sessions，跳过对话导入）"
fi

cat <<EOF

═══════════════════════════════════════════
完成。剩下要人工的两件：
  1. 重启服务让配置生效：
     launchctl kickstart -k gui/\$(id -u)/com.workdsh.preview
  2. 配你自己的模型 API Key（不随仓库走）：
     界面会弹「添加一个 API Key」，或写进 <DSH_HOME>/.credentials.yaml
═══════════════════════════════════════════
EOF
