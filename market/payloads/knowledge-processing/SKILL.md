---
name: knowledge-processing
description: 把文档/语料（docx/pdf/md）经七道工序处理为结构化知识图谱语料包，产出 30 个契约文件（含脱敏骨架 skeletons.jsonl）。当用户要求把稿件处理成语料包、跑「归一化→骨架→切块→本体→回放→质量→脱敏索引」七道工序流水线、产出知识图谱/脱敏骨架、或使用 kp_toolkit / corpus_pipeline / MCP 29 工具时使用。与 knowledge-processing-toolchain 的区别：本 skill 覆盖完整流水线与 30 文件产物契约，toolchain 覆盖工具+LLM 分层方法论。
---

# 知识处理（Knowledge Processing）

## 目的

把一份历史稿件（docx/pdf/md）经七道工序产出「语料包」：30 个契约文件，供写作 Agent 使用。写作 Agent 只拿脱敏骨架，永远拿不到原文。

## 何时使用

- 用户要求「把稿件处理成语料包」「跑七道工序」「产出语料包」
- 用户要求「结构化知识图谱」「脱敏骨架 skeletons.jsonl」「30 文件契约」
- 用户上传 docx/pdf 要求处理为可溯源、可审计的图谱
- 用户提到 kp_toolkit / corpus_pipeline / kp-mcp 工具

不适用：单纯的文本总结/改写（通用写作）；图谱尚未构建时的自由写作。

## 项目位置

代码工程：`/Users/apple/Desktop/workdsh/knowledge-processing-expert/`（kp_toolkit、corpus_pipeline、mcp/server.py）。

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
cd /Users/apple/Desktop/workdsh/knowledge-processing-expert
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

## MCP 工具（29 个）

`mcp/server.py`（stdio，NDJSON 帧，用 venv python 启动）。分五组：

- 处理（8）：corpus_run / segment_sentences / segment_chunks / validate_graph / detect_numeric_conflicts / detect_time_conflicts / build_provenance / validate_schema
- 契约（1）：manifest
- Agent 访问（10）：corpus_get_chunk / corpus_get_skeleton / corpus_where_used / graph_get_node / graph_query / graph_explain / graph_impact / graph_why / gate_check / evidence_get
- 嵌入（2）：embed / embed_chunks
- 重发（8）：reemit_meta / reemit_provenance / reemit_invariants / reemit_evidence / reemit_reasoning / reemit_quality / reemit_style / reemit_index

## 嵌入

`corpus_pipeline/embed.py`：fastembed（ONNX，无 torch）+ paraphrase-multilingual-MiniLM-L12-v2（384 维，支持中文）。`build_embeddings` 严格输出 `chunks/embeddings.parquet`（pyarrow）。

## 存储

`corpus_pipeline/backends.py`：PG/Neo4j/Qdrant 真实适配器 + 文件系统回退。环境变量 KP_PG_DSN / KP_NEO4J_URI / KP_QDRANT_URL 配置；docker-compose.yml + storage/schema.sql 在项目目录。未配置时自动回退文件系统（对象存储）。

## 铁律

- 冲突一律「待审」呈现，不擅自改数字或补口径。
- 缺失事实保持显式未知（TODO/待补充），绝不编造。
- 数值单源存在图节点；正文可反向回读为图谱节点。
- 能确定性的绝不交给模型；需要语义的才调 LLM，且必须结构化 + 校验。
