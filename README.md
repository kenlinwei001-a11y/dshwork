# 知识处理 + 推演写作 · 可复现环境

本仓库包含「知识处理专家」与「推演写作专家」的完整可复现环境：工程代码、6 个 skill 源、
2 个专家定义、一键安装脚本。同事 `git clone` 后按下方步骤即可得到与作者本机一致的系统。

## 目录结构

```
├── knowledge-processing-expert/   # 工程代码（corpus_pipeline / kp_toolkit / mcp / corpus-library）
│   ├── corpus_pipeline/           # 七道工序 + 装配引擎（schema_diff / semantic_model / ontology_schema / instantiate / contracts / runtime ...）
│   ├── kp_toolkit/                # 确定性工具（分句/建图/溯源/冲突/查数）
│   ├── mcp/server.py              # kp-mcp（48 工具）
│   ├── corpus-library/            # 历史语料资产库（PX-2026-001-feasibility 样例）
│   ├── ARCHITECTURE.md            # 五形态边界 + 分层声明（架构收口）
│   └── requirements.txt           # 依赖
├── skills/                        # 6 个 skill 源（推演写作专家依赖）
│   ├── graph-deductive-writing-skill
│   ├── claim-evidence-binding-skill
│   ├── conflict-detection-skill
│   ├── knowledge-processing-toolchain
│   ├── knowledge-generalization-skill
│   └── semantic-graph-compilation-skill
├── experts/                       # 2 个专家定义（供界面导入）
│   ├── deductive-writer-expert.md
│   └── knowledge-processing-expert.md
├── setup.sh                       # 一键安装脚本
└── README.md
```

## 快速复现（3 步）

### 第 1 步：自动安装（venv + 依赖 + 6 个 skill + 回归测试）

```bash
bash setup.sh
```

### 第 2 步：注册 kp-mcp（手动，WorkDSH 界面）

在 WorkDSH「MCP 连接」里新增一个 **stdio** 连接：

| 字段 | 值 |
|---|---|
| serverName | `kp-mcp` |
| command | `<本仓库>/knowledge-processing-expert/.venv/bin/python` |
| args | `["<本仓库>/knowledge-processing-expert/mcp/server.py"]` |
| cwd | `<本仓库>/knowledge-processing-expert` |

### 第 3 步：导入专家（手动，WorkDSH 界面）

在「专家」界面新建专家，粘贴 `experts/*.md` 的 frontmatter + 正文，绑定对应 skill：

- **推演写作专家** → `experts/deductive-writer-expert.md`（6 个 skill）
- **知识处理专家** → `experts/knowledge-processing-expert.md`（21 个 skill）

> 知识处理专家的 21 个 skill 里，有 15 个不在本仓库 `skills/` 里（document-parsing、fact/entity/relation/claim/reasoning/evidence-extraction 等），
> 这些是 WorkDSH 市场/内置的通用 skill，同事需在 WorkDSH 里通过市场安装，或用 `skillhub_search` 安装同名 skill。

## 核心依赖

- **必需**：`PyYAML`（推演写作 + 装配引擎的唯一硬依赖）。
- **可选**（知识处理七道工序）：`pymupdf` / `python-docx`（文档解析）、`neo4j` / `qdrant-client` / `fastembed`（图/向量）、`psycopg2-binary`（关系库）、`pyarrow`。见 `requirements.txt` 注释。

## 能力速览

- **kp-mcp（48 工具）**：七道工序 + `library_*` + `schema_diff` / `resolve_concept` / `ossie_import/export` / `ontology_*` / `check_number_consistency` / `instantiate_project` / `gate_check_draft` 等。
- **确定性主链路**：Schema Diff → Asset Resolver → Reuse Policy → Asset Assembler → Validation → Asset Publisher。
- **可插拔对接**：Apache Ossie（语义对齐）、Jev（语义分类，预留）、Semantica（本体管理，对齐 OWL/SHACL/SKOS）。
- **回归测试**：`corpus_pipeline/test_*.py` + `kp_toolkit/test_*.py`（17 个文件，全部通过）。

## 版本说明

- skill 的权威安装目录是 `~/.agents/skills/`，`setup.sh` 会把 `skills/` 下的 6 个 skill 复制过去。
- 专家定义、MCP 连接是 WorkDSH 的界面状态，无法完全脚本化，故第 2/3 步需手动（脚本已给出精确参数）。
