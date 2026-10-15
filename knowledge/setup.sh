#!/usr/bin/env bash
# 一键复现「知识处理 + 推演写作」环境：venv + 依赖 + 6 个 skill
# 用法：bash setup.sh [--force]
#   --force  覆盖已存在且内容不同的 skill（默认跳过并告警，见下）
#
# ⚠ 为什么默认不覆盖：本脚本会把 skills/ 装到 ~/.agents/skills/。若那台机器上
#   这些 skill 已经被改过（手工编辑、或二次开发），原来的 rm -rf + cp 会**静默丢掉改动**。
#   实测踩过：在某台改过 skill 的机器上重跑，3 个 SKILL.md 被仓库版覆盖。
#   所以默认只装"没有的"和"内容一致的"，遇到内容不同就跳过并提示 —— 要覆盖必须显式 --force。
set -euo pipefail

FORCE=0
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "未知参数: ${a}（支持 --force）"; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")" && pwd)"
KP="$ROOT/knowledge-processing-expert"

echo "== 1/3 建 venv + 装依赖 =="
cd "$KP"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r requirements.txt

echo "== 2/3 安装 6 个 skill 到 ~/.agents/skills =="
SKILLS_DIR="${HOME}/.agents/skills"
mkdir -p "$SKILLS_DIR"

# 判据：这次安装会不会改变目标？只比"源里有的文件"——目标多出来的（如 *.bak）不算差异。
install_changes_target() {
  local src="$1" dst="$2" f rel
  [ -d "$dst" ] || return 0
  while IFS= read -r -d '' f; do
    rel="${f#"$src"}"
    [ -f "$dst/$rel" ] || return 0          # 目标缺文件 ⇒ 会改变
    cmp -s "$f" "$dst/$rel" || return 0     # 内容不同   ⇒ 会改变
  done < <(find "$src" -type f -print0 2>/dev/null)
  return 1                                   # 源里每个文件目标都有且相同 ⇒ 不会改变
}

n_installed=0; n_same=0; n_protected=0
for s in "$ROOT"/skills/*/; do
  name="$(basename "$s")"
  target="$SKILLS_DIR/$name"
  if [ -d "$target" ]; then
    if install_changes_target "$s" "$target"; then
      if [ "$FORCE" != "1" ]; then
        echo "  ⚠ 跳过 skill: $name"
        echo "      目标已存在且与本次要装的内容不同 —— 那台机器上可能有手改/二开"
        echo "      目标: $target"
        echo "      确认要覆盖就重跑: bash setup.sh --force"
        n_protected=$((n_protected+1))
        continue
      fi
    else
      echo "  跳过 skill: ${name}（已是最新）"
      n_same=$((n_same+1))
      continue
    fi
  fi
  rm -rf "$target"
  cp -R "$s" "$target"
  echo "  已安装 skill: $name"
  n_installed=$((n_installed+1))
done
echo "  小结: 安装 $n_installed / 已最新 $n_same / 保护跳过 $n_protected"
[ "$n_protected" -gt 0 ] && echo "  ⚠ 有 $n_protected 个 skill 因内容不同被跳过（未改动它们）"

echo "== 3/3 回归测试 =="
cd "$KP"
for t in corpus_pipeline/test_*.py kp_toolkit/test_*.py; do
  PYTHONPATH=. .venv/bin/python "$t" >/dev/null 2>&1 && echo "  PASS $t" || echo "  FAIL $t"
done

cat <<'EOF'

== 完成。还需手动两步（无法脚本化，需在 WorkDSH 界面操作）==

① 注册 5 组 MCP（「MCP 服务管理」→ 添加 MCP → stdio，公共 command 为 <本目录>/knowledge-processing-expert/.venv/bin/python）：
   kp-processing → args [<本目录>/knowledge-processing-expert/mcp/servers/kp_processing_server.py]   (30 工具)
   kp-assembly   → args [<本目录>/knowledge-processing-expert/mcp/servers/kp_assembly_server.py]     (16 工具)
   kp-library    → args [<本目录>/knowledge-processing-expert/mcp/servers/kp_library_server.py]      (7 工具)
   kp-semantic   → args [<本目录>/knowledge-processing-expert/mcp/servers/kp_semantic_server.py]     (6 工具)
   kp-reserved   → args [<本目录>/knowledge-processing-expert/mcp/servers/kp_reserved_server.py]     (6 工具)

② 导入专家（专家界面 → 新建，粘贴 experts/*.md 的 frontmatter + 正文，绑定对应 skill）：
   推演写作专家  → experts/deductive-writer-expert.md   （6 个 skill）
   知识处理专家  → experts/knowledge-processing-expert.md （21 个 skill）

EOF
