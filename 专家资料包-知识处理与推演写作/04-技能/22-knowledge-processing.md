# Skill：knowledge-processing

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。文中结论均可按 01-关系总览/02-数据来源与核对说明.md 复核。

## 1. 元数据（SKILL.md frontmatter）

| 字段 | 值 |
|---|---|
| name | knowledge-processing |
| description | 把文档/语料（docx/pdf/md）经七道工序处理为结构化知识图谱语料包，产出 30 个契约文件（含脱敏骨架 skeletons.jsonl）。当用户要求把稿件处理成语料包、跑「归一化→骨架→切块→本体→回放→质量→脱敏索引」七道工序流水线、产出知识图谱/脱敏骨架、或使用 kp_toolkit / corpus_pipeline / MCP 工具（5 组 65 工具）时使用。与 knowledge-processing-toolchain 的区别：本 skill 覆盖完整流水线与 30 文件产物契约，toolchain 覆盖工具+LLM 分层方法论。 |

## 2. 职责与触发

- 中文职责：七道工序语料包
- 能力简述：把文档/语料经「归一化→骨架→切块→本体→回放→质量→脱敏索引」处理为 30 个契约文件的知识图谱语料包。
- 配备专家：未被这两个专家配备（本地已安装，属于同一知识处理链路）
- 资源规模：1 个文件，合计 6.0 KB

## 3. SKILL.md 正文（全文）

~~~markdown
---
name: knowledge-processing
description: 把文档/语料（docx/pdf/md）经七道工序处理为结构化知识图谱语料包，产出 30 个契约文件（含脱敏骨架 skeletons.jsonl）。当用户要求把稿件处理成语料包、跑「归一化→骨架→切块→本体→回放→质量→脱敏索引」七道工序流水线、产出知识图谱/脱敏骨架、或使用 kp_toolkit / corpus_pipeline / MCP 工具（5 组 65 工具）时使用。与 knowledge-processing-toolchain 的区别：本 skill 覆盖完整流水线与 30 文件产物契约，toolchain 覆盖工具+LLM 分层方法论。
---

# 知识处理（Knowledge Processing）

## 目的

把一份历史稿件（docx/pdf/md）经七道工序产出「语料包」：30 个契约文件，供写作 Agent 使用。写作 Agent 只拿脱敏骨架，永远拿不到原文。

## 何时使用

- 用户要求「把稿件处理成语料包」「跑七道工序」「产出语料包」
- 用户要求「结构化知识图谱」「脱敏骨架 skeletons.jsonl」「30 文件契约」
- 用户上传 docx/pdf 要求处理为可溯源、可审计的图谱
- 用户提到 kp_toolkit / corpus_pipeline / kp-*（5 组 MCP）工具

不适用：单纯的文本总结/改写（通用写作）；图谱尚未构建时的自由写作。

## 项目位置

代码工程：`/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/`（kp_toolkit、corpus_pipeline、mcp/server.py）。

## 七道工序

| 工序 | 做什么 | 产出 |
|------|--------|------|
| 1 归一化 | 去页眉页脚、公式转 LaTeX、表格结构化、保留字符偏移 | source/normalized.md, offset_map.json, assets/, original.<ext> |
| 2 骨架抽取 | 识别章节层级、映射法定大纲、覆盖校验 | outline.yaml, meta.yaml |
| 3 切块 | 语义边界切 chunk（表格/图注独立成块）、记录 span | chunks/chunks.jsonl, embeddings.parquet |
| 4 本体抽取 | 抽事实/规则/论断/证据 + 十类关系（语义，接 LLM） | graph/nodes\|rules\|relations\|claims.yaml, evidence/*, provenance.yaml |
| 5 推演回放 | 按规则重算、比对原值、检矛盾 | reasoning/derivation\|decisions\|trace |
| 6 质量登记 | 登记冲突/缺口、跑不变式、出闸门 | quality/conflicts\|gaps\|gate_report, graph/invariants.yaml |
| 7 脱敏索引 | 数值→{{node:Nxx}}、节点倒排、术语归一、签名 | chunks/skeletons.jsonl, index/*, style/* |

## 运行方式

```bash
cd /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert
# 七道工序全链路（docx/pdf 解析需 venv 里的 pymupdf/python-docx）
.venv/bin/python -m corpus_pipeline.cli run 稿件.docx --out 语料包目录
# 确定性工具层自测
python3 -m kp_toolkit.test_kp_toolkit
python3 -m corpus_pipeline.test_pipeline
python3 -m corpus_pipeline.test_llm_extraction
```

`run_pipeline` 关键参数：

- `legal_outline`：法定大纲列表（工序 2 覆盖校验用）
- `extractions`：LLM 语义抽取输出（缺省时工序 4 降级为数值占位）
- `original_path`：原稿路径（落盘 source/original.<ext>）

## 30 文件契约

契约定义在 `corpus_pipeline/spec.py`（MANIFEST 列表，含主存/副本/可变/Agent 形式）。要点：

- **主存列是权威副本**，副本列是冗余拷贝，以主存为准。
- **Agent 访问形式**：① 注入（constraints/meta/outline/gate/style/terms）· ② 工具调用（corpus_get_chunk 等 10 个）· ③ 内嵌（conflicts/gaps）· ✕ 不对外（原文/整包/事件流）。
- **安全边界**：写作 Agent 只拿 `chunks/skeletons.jsonl`（数值已替换为 {{node:Nxx}}），永远不拿 `chunks/chunks.jsonl`（原文）。

## 确定性 vs 语义（tool+LLM 分层）

- 确定性步骤（分句/分块/建图/溯源/数字·时间冲突/schema 校验）→ kp_toolkit 代码，零 LLM，可复现可单测。
- 语义步骤（实体/事实/关系/Claim/证据/推理抽取、证据判断、推演写作）→ LLM 结构化输出 + schema + validator + 重试（复用 20 个抽取技能）。
- 分层方法论详见 knowledge-processing-toolchain skill。

## MCP 工具（65 个，按权限域拆 5 组）

`mcp/server.py`（stdio，NDJSON 帧，用 venv python 启动），按 `KP_MCP_GROUP` / `--group` 拆 5 个 MCP：

- kp-processing（30）：知识处理七道工序 —— corpus_run / segment_* / detect_* / validate_graph / manifest / embed / reemit_* / corpus_search / graph_* / gate_check / evidence_get
- kp-assembly（16）：装配+验证+写作 —— schema_diff / decide_reuse / instantiate_project / build_work_package / gate_check_draft / bootstrap_ontology / impacted_assets / run_quality_gates / check_number_consistency / check_requirements / sensitivity_analysis / validate_shacl / assess_capability / validate_source_anchor / project_where_written / wp_get_facts
- kp-library（7）：资产库+发布 —— library_list_packages / library_search / library_get_asset / library_find_analog / library_status / library_promote / library_publish
- kp-semantic（6）：语义对齐+本体 —— resolve_concept / semantic_classify / ossie_import / ossie_export / ontology_export / ontology_import
- kp-reserved（6）：预留 —— semantic_search / asset_rerank / solve_constraint / graph_db_query / store_object / llm_invoke

## 嵌入

`corpus_pipeline/embed.py`：fastembed（ONNX，无 torch）+ paraphrase-multilingual-MiniLM-L12-v2（384 维，支持中文）。`build_embeddings` 严格输出 `chunks/embeddings.parquet`（pyarrow）。

## 存储

`corpus_pipeline/backends.py`：PG/Neo4j/Qdrant 真实适配器 + 文件系统回退。环境变量 KP_PG_DSN / KP_NEO4J_URI / KP_QDRANT_URL 配置；docker-compose.yml + storage/schema.sql 在项目目录。未配置时自动回退文件系统（对象存储）。

## 铁律

- 冲突一律「待审」呈现，不擅自改数字或补口径。
- 缺失事实保持显式未知（TODO/待补充），绝不编造。
- 数值单源存在图节点；正文可反向回读为图谱节点。
- 能确定性的绝不交给模型；需要语义的才调 LLM，且必须结构化 + 校验。
~~~

## 4. 资源清单

| 文件 | 字节 | 说明 |
|---|---|---|
| SKILL.md | 6144 | 技能主文档 |

## 5. MCP 关联（文本取证）

正文或资源中出现以下 MCP 标识：`kp_toolkit`。对应连接见 06-MCP/。

## 6. 运行依赖与边界

- 依赖：无额外外部服务。
- 本包副本：`99-原件/skills/knowledge-processing/`（逐字节复制，未改写）。
- 说明：本包只如实转述技能内容与资源，不对技能产出质量作任何承诺。
