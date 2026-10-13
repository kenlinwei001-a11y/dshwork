# 归档说明（kp-patch）

**这是什么**：知识抽取与推演写作环节优化的补丁包 + 安装器 + 诊断报告。
**归档时间**：2026-10-13
**上游落点**：`knowledge/knowledge-processing-expert/`（10 个新模块 + 7 处文件补丁）
**配套文档**：`共存交接说明.md`（与 semantica 那条线的文件级归属与共存约定）、`README.md`

## 内容

| 路径 | 作用 |
|------|------|
| `corpus_pipeline/*.py` | 10 个新模块（source_ledger / closure_verify / stage_gates / objective_criteria / relations_ext / providers / providers_semantica / units / alias / verify_pipeline） |
| `install.py` | 装 8 模块 + 4 文件补丁（幂等、带时间戳备份） |
| `install_mcp_tools.py` | 注册 MCP 工具（schema + dispatch + 分组） |
| `install_pipeline_gates.py` | 把门禁接进流水线（包装 run_pipeline / gate_check_draft） |
| `apply_skills.py` + `skills/PATCHES.md` | 5 个 skill 的插入式增量 |
| `surgical_rollback.py` | 按标记外科式回滚（**不要用旧 .bak**） |

## 使用

```bash
cd <kp 工程>
python tools/kp-patch/install.py --check
python tools/kp-patch/install.py
python tools/kp-patch/install_mcp_tools.py
python tools/kp-patch/install_pipeline_gates.py
python tools/kp-patch/apply_skills.py --skills-dir /Users/apple/.agents/skills
```

回滚：`python tools/kp-patch/surgical_rollback.py --check|--rollback`
