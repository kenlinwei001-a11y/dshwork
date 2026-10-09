#!/usr/bin/env bash
# 一键复现「知识处理 + 推演写作」环境：venv + 依赖 + 6 个 skill
# 用法：bash setup.sh
set -euo pipefail

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
for s in "$ROOT"/skills/*/; do
  name="$(basename "$s")"
  rm -rf "$SKILLS_DIR/$name"
  cp -R "$s" "$SKILLS_DIR/$name"
  echo "  已安装 skill: $name"
done

echo "== 3/3 回归测试 =="
cd "$KP"
for t in corpus_pipeline/test_*.py kp_toolkit/test_*.py; do
  PYTHONPATH=. .venv/bin/python "$t" >/dev/null 2>&1 && echo "  PASS $t" || echo "  FAIL $t"
done

cat <<'EOF'

== 完成。还需手动两步（无法脚本化，需在 WorkDSH 界面操作）==

① 注册 kp-mcp（MCP 连接 → 新增 stdio）：
   serverName: kp-mcp
   command:    <本目录>/knowledge-processing-expert/.venv/bin/python
   args:       [<本目录>/knowledge-processing-expert/mcp/server.py]
   cwd:        <本目录>/knowledge-processing-expert

② 导入专家（专家界面 → 新建，粘贴 experts/*.md 的 frontmatter + 正文，绑定对应 skill）：
   推演写作专家  → experts/deductive-writer-expert.md   （6 个 skill）
   知识处理专家  → experts/knowledge-processing-expert.md （21 个 skill）

EOF
