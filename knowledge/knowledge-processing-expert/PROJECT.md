# 知识抽取项目（Knowledge Extraction Project）

把历史稿件（docx/pdf/md）经七道工序，产出「语料包」，供写作 Agent 使用——写作 Agent 只拿脱敏骨架 `skeletons.jsonl`，永远拿不到原文 `chunks.jsonl`。

## 组成

| 模块 | 路径 | 说明 |
|------|------|------|
| 专家 | `agents/knowledge-processing-expert.md` | 「知识处理专家」，工具+LLM 分层，绑定 21 技能 |
| 工具层 | `kp_toolkit/` | 确定性工具（分句/建图/溯源/冲突/schema） |
| 七道工序 | `corpus_pipeline/` | 语料包流水线（归一化→骨架→切块→本体→回放→质量→脱敏索引） |
| 30 文件契约 | `corpus_pipeline/spec.py` + `full_emit.py` | 30 产物清单 + 全部发射器 + 8 个 reemit |
| 嵌入层 | `corpus_pipeline/embed.py` | fastembed 向量化，输出 embeddings.parquet |
| 存储后端 | `corpus_pipeline/backends.py` | PG/Neo4j/Qdrant 适配器 + 文件系统回退 |
| MCP | `mcp/server.py` + `mcp/servers/`（5 入口） | stdio MCP 服务（65 工具，按权限域拆 5 组） |
| 专家包元数据 | `.workdsh-expert/plugin.json` | 专家身份/展示/技能声明 |

## 七道工序 → 30 文件

```
1 归一化   → source/normalized.md, offset_map.json, assets/, original.<ext>
2 骨架抽取 → outline.yaml（章节层级 + 法定大纲覆盖校验）, meta.yaml
3 切块     → chunks/chunks.jsonl（语义边界，表格/图注独立成块）, embeddings.parquet
4 本体抽取 → graph/nodes|rules|relations|claims.yaml, evidence/*, provenance.yaml ※语义接 LLM
5 推演回放 → reasoning/derivation|decisions|trace（按规则重算、比对原值、检矛盾）
6 质量登记 → quality/conflicts|gaps|gate_report, graph/invariants.yaml（闸门）
7 脱敏索引 → chunks/skeletons.jsonl, index/node_index|term_index|signature, style/*（数值→{{node:Nxx}}）
```

## MCP 工具清单（29 个）

| 类别 | 工具 |
|------|------|
| 处理（8） | `corpus_run` / `segment_sentences` / `segment_chunks` / `validate_graph` / `detect_numeric_conflicts` / `detect_time_conflicts` / `build_provenance` / `validate_schema` |
| 契约（1） | `manifest` |
| Agent 访问（10） | `corpus_get_chunk` / `corpus_get_skeleton` / `corpus_where_used` / `graph_get_node` / `graph_query` / `graph_explain` / `graph_impact` / `graph_why` / `gate_check` / `evidence_get` |
| 嵌入（2） | `embed` / `embed_chunks` |
| 重发（8） | `reemit_meta` / `reemit_provenance` / `reemit_invariants` / `reemit_evidence` / `reemit_reasoning` / `reemit_quality` / `reemit_style` / `reemit_index` |

## 用法

```bash
# 七道工序全链路（含 original 落盘 + 30 文件产出）
.venv/bin/python -m corpus_pipeline.cli run 稿件.docx --out 语料包目录

# 工具层自测
python3 -m kp_toolkit.test_kp_toolkit
python3 -m corpus_pipeline.test_pipeline
python3 -m corpus_pipeline.test_llm_extraction

# 嵌入（embeddings.parquet）
.venv/bin/python -c "from corpus_pipeline.embed import build_embeddings; ..."

# MCP 服务（65 工具，按权限域拆 5 组，用 venv python）
# 单一 kp-mcp（全部 65 工具）：.venv/bin/python mcp/server.py
# 按组拆分（推荐）：.venv/bin/python mcp/servers/kp_processing_server.py   # 30 工具
.venv/bin/python mcp/server.py
```

## 依赖

- 已装（venv）：pymupdf、python-docx、fastembed、pyarrow、psycopg2-binary、neo4j、qdrant-client
- MCP：纯标准库实现，无需 `mcp` SDK

## 关键安全边界

写作 Agent 只拿到 `chunks/skeletons.jsonl`（数值已替换为 `{{node:Nxx}}` 占位符），
数值单源存在图节点里；原文 `chunks/chunks.jsonl` 永不外发。

## 注册说明（DSH Host）

- 5 组 MCP 连接定义在 WorkDSH「MCP 服务管理」里注册，存储于
  `~/.test-runtime/preview/storages/workdsh_connectors/definitions/{kp-processing,kp-assembly,kp-library,kp-semantic,kp-reserved}.json`。
- 每个连接 `transport=stdio`、`command=.venv/bin/python`、`args=mcp/servers/kp_<组>_server.py`。
- 修改后需重启 DSH Host 才生效。
