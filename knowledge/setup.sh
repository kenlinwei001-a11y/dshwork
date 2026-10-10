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
