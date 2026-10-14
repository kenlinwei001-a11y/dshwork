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
| Semantica 桥接 | `corpus_pipeline/semantica_client.py` | 预留接口已接入：纯标准库 stdio MCP 客户端（NDJSON 帧），bootstrap_claim_ontology 自动连接（KP_SEMANTICA_AUTO=0 关闭、失败降级确定性规则）；ontology_export(source=semantica/both) 拉图快照；ontology_import(push_to_semantica) 推类/属性/词表进 Semantica 图。部署：`python -m semantica.mcp_server`（15 工具，KG 默认 ~/.semantica/graph.json，KP_SEMANTICA_KG_PATH 可覆盖） |
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


## Semantica 外部核验（v2）

对接方式与 v1 的「桥接」不同：v2 把它当作**可独立工作的外部图/语义基础设施**使用，而不是只做 Schema 演进的钩子。

| 项 | 落地 |
|----|------|
| 版本 | semantica 0.7.0，venv `/Users/apple/.venvs/semantica` |
| LLM 依赖 | `openai` + `instructor`（**缺失会导致 DeepSeek provider 报 not available**） |
| 凭据 | `~/.semantica/env`（600），连接器定义只引用不内嵌 |
| MCP | `semantica` 连接器（15 工具），由 definitions 目录注册，连接器管理器不可见 |
| KG | `/Users/apple/.semantica/graph.json` |

### 已落地的四类用法

1. **冲突检测互证**：`conflicts.ConflictDetector` 与我方 `kp_toolkit.detect_numeric_conflicts` 对 279 条原子数值事实给出同一结论（1 项），可作审计证据。**全程未调用 `ConflictResolver`**。
2. **中文语义抽取**：`semantic_extract` 的 `method="llm"` + DeepSeek；一个 chunk 得 8 实体 / 24 关系 / 25 三元组。`pattern` 仅英文、`ml` 缺 spaCy。
3. **实体消歧 + 合规溯源**：`DuplicateDetector` 出 1104 组候选；`ProvenanceManager` 记录 442 条实体、109 唯一来源、SHA-256 校验和（`外部核验/provenance/prov.db`）。
4. **实体归一判官**（暂代 JEV）：`reasoning` 规则前向链 + DeepSeek 判官双路合并，1104 -> 71 条待人工判断，带 `confidence` 与 A/B/C 分档。

### 判官校准（对 17 组人工标准答案）

| 判官 | 准确率 | 关键特性 |
|------|--------|----------|
| 规则判官（`reasoning`） | **15/17 = 88%** | 负证据优先（年份/标准号/角色/规格数字差异即判不同） |
| LLM 判官（DeepSeek） | 12/17 = 71% | 判 DIFF 精度 100%，判 SAME 精度仅 58% |

产物落于 `语料包/外部核验/`。**合并未执行，须人工确认。**


### MCP 通道与 Python API 通道的差异（实测结论）

| 通道 | provider 解析 | 中文可用性 | 关系/三元组 |
|------|---------------|-----------|-------------|
| Python API | 显式 `provider="deepseek"`（`semantica.llms.deepseek`） | 可用 | 可用（24 关系 / 25 三元组 per chunk） |
| MCP 工具 | 内部默认 `openai` provider，不读 DEEPSEEK key | 需 `OPENAI_API_KEY` + `OPENAI_BASE_URL` 指向 DeepSeek，且必须传 `model="deepseek-chat"` | **不可用**：`extract_relations` 硬编码 NER 为 `methods=["ml"]`（spaCy 未装） |

因此 `~/.semantica/env` 同时导出 `DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`OPENAI_BASE_URL` 三者；
改 env 后需让 MCP 进程重生（kill 后 Host 懒重生，或重启 dsh web）。


### 决策记录：关系/三元组走 Python API，不装 spaCy、不改 MCP 包装（2026-10-13）

问题：MCP 的 `extract_relations` 返回空。根因是 `mcp_server/__init__.py` 两处写死：
第 160 行 `NamedEntityRecognizer(methods=["ml"])`（spaCy 未装）与第 162 行 `TripletExtractor()`（漏传 method）。

评估与结论：

| 选项 | 结论 | 理由 |
|---|---|---|
| 装 spaCy + zh 模型 | 否决 | 只救第 160 行；第 162 行仍坏（三元组照样空）；zh 通用模型抽不到领域指标；两套引擎导致实体不一致 |
| 修 MCP 包装 | 暂不做 | 可行（TripletExtractor 签名支持 method），但改 site-packages，升级即丢 |
| **Python API（采纳）** | 采用 | 实测 24 关系 / 25 三元组；`semantica_verify/` 已固化 |

上游 0.7.0 为最新版，无修复版可升。
