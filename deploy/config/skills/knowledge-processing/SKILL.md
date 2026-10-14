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

<!-- kp-patch:v1 -->
## 工序之外的三道机制（v1 新增）

七道工序解决「怎么处理」；下面三道解决「**怎么知道没漏**」。它们不是工序，是门禁。

| 机制 | 模块 | 作用 | 判据 |
|------|------|------|------|
| **源侧索引 source ledger** | `corpus_pipeline/source_ledger.py` | 让「漏了什么」成为可计算的问题 | 引用/表/带单位数值/标题/题注/设备参数 逐类枚举 |
| **闭环校验 closure verify** | `corpus_pipeline/closure_verify.py` | `S − P − 豁免 = ∅` | C1 依据 / C2 关键取值 / C3 章节 / C4 设备参数 / C5 题注 / C6 装配 / C7 关系 |
| **分步门禁 stage gates** | `corpus_pipeline/stage_gates.py` | 每步一道闭环，落在**可重做单元的出口** | S0–S11；含**探针正样本标定** |

**为什么必须有**：旧 `validate_extraction` 的三个循环都是 `for x in ext.get(...)`——
**只遍历产物**。对产物集合的任何遍历，逻辑上不可能发现「属于源而不属于产物」的元素。
因此「依据漏抽 54 条」这类缺陷会**静默通过**，不是校验不够严，是方向错了。

**契约扩展（30 → 32 文件）**：

| 新增文件 | 用途 |
|----------|------|
| `chunks/sentences.jsonl` | 句子层：Claim 追踪的最小单位，稳定 ID 可回溯到 chunk |
| `source_ledger.json` | 源侧索引：闭环校验的基准 |

**判定权归属**：门禁由**编排器**调用，**不由抽取/写作 Agent 自判**。
探针未过标定 ⇒ 该项 `invalid`，**不得输出「无误」**。

**可替换环节**：实体/关系/推理/图存储四个环节走 `corpus_pipeline/providers.py` 的 provider 接缝；
换实现（例如换成外部图基础设施）**不需要改任何门禁判据**。缺能力时该项判 `invalid`。


<!-- kp-patch:v2 -->
## Semantica 外部核验（v2 新增）

Semantica 是**图原生知识基础设施**（27 模块 / 6 层，官方原则：*Every Semantica module works independently*）。
在 v1 的 provider 接缝之外，它提供**另一种外部图实现**，可独立承担多道工序的一部分，也能与 LLM 组成组合。

### 前置（本机已就绪）

| 项 | 值 |
|----|----|
| venv | `/Users/apple/.venvs/semantica`（semantica 0.7.0） |
| LLM 路径依赖 | venv 内需 `openai` + `instructor`（缺则 DeepSeek provider 报 not available） |
| 凭据 | `~/.semantica/env`（600 权限，`DEEPSEEK_API_KEY`）；**不写进连接器定义** |
| KG | `/Users/apple/.semantica/graph.json` |
| MCP | 已注册 `semantica` 连接器（15 工具），由 definitions 目录管理，连接器管理器不可见 |

### 模块到工序映射

| 工序 | 模块 | 独立可用 | +LLM 组合 |
|------|------|----------|-----------|
| 1 归一化 | `ingest` + `parse` + `normalize` | 是 | DoclingParser 的 OCR/版面 |
| 3 切块 | `split.TextSplitter`（12 法） | 是（sentence/paragraph/recursive） | semantic_transformer / llm / entity_aware |
| 4 本体抽取 | `semantic_extract`（NER/关系/三元组/事件/共指） | 仅英文（pattern） | `method="llm"`：**中文唯一可用路径** |
| 4' 消歧 | `deduplication.DuplicateDetector` | 是 | - |
| 5 推演回放 | `reasoning`（前向链/后向链/Datalog/SPARQL/RETE/时间区间） | 是 | 第 8 种 LLM 图推理 |
| 6 质量 | `conflicts.ConflictDetector` + `ontology.SHACLGenerator` | 是（检测） | `expert review` 策略 |
| 全程溯源 | `provenance.ProvenanceManager` | 是（W3C PROV-O + SHA-256） | - |
| 决策台账 | `context` / MCP `record_decision` | 是 | GraphRAG 查询 |
| 实体归一（暂代 JEV） | `reasoning` 规则前向链（约等于 MCP `run_reasoning`） | 是 | DeepSeek 判官交叉校验 |

### 铁律约束（违反即作废）

1. **禁用 `ConflictResolver`**：其 7 种策略（可信度加权投票、最近优先等）会产出单一决议值，直接违反「冲突一律待审」。只用 `ConflictDetector`。
2. **归一只产候选**：LLM 判官**判 DIFF 精度 100%（可直接过滤）**，**判 SAME 精度仅 58%（系统性过度合并）**；合并必须人工确认。
3. **中文抽取必须 `method="llm"`**：`pattern` 是英文规则集（中文 0 实体），`ml` 依赖 spaCy（本机未装）。

### 实体归一（`run_reasoning` 暂代 JEV）

规则判官（对 17 组人工标准答案 **15/17 = 88%**）+ DeepSeek 判官（12/17 = 71%）双路合并：

```text
1104 组去重候选 -> 规则判官排除 737 -> LLM 的 DIFF 排除 296 -> 71 条待人工判断（降幅 94%）
  A 高置信 7 条（confidence >= 0.85，抽审）
  B 中置信 16 条（0.60-0.84，快速过目）
  C 低置信 48 条（< 0.60，逐条审校；含 53 条两路引擎分歧）
```

产物落位 `语料包/外部核验/`：`实体归一-人工判断清单.md`（末列填 合并/不合并/裁决）、
`entity-normalization-queue.tsv`、`subject-normalization-queue.yaml`（含 `confidence` / `review_tier`）。
**合并未执行，须人工确认。**

### 复现脚本（`构建脚本/`）

`semantica_p0.py`（冲突互证）、`semantica_p1p2.py`（消歧 + PROV-O + 切块）、`semantica_p1a_refine.py`（候选分类）、
`semantica_rule_judge.py`（规则判官 + 校准）、`semantica_normalize_queue.py` / `semantica_refine_confidence.py` /
`semantica_merge_judges.py` / `semantica_make_review_md.py` / `semantica_report.py`；
LLM 两脚本 `semantica_judge_test.py` / `semantica_judge_bulk.py` 需 `DEEPSEEK_API_KEY`。

### MCP 通道的正确调用姿势（2026-10-13 实测，务必照做）

MCP 版抽取与 Python API 版**不是同一套 provider 解析**，踩过三个坑：

1. **MCP 的 `extract_entities` 内部走 `openai` provider**，它**不读** `DEEPSEEK_API_KEY`。
   只设 DEEPSEEK key 时，调用会静默回退 pattern 并返回 `{"entities": []}`（无报错）。
2. 因此 `~/.semantica/env` 必须**同时**导出：
   `export OPENAI_API_KEY=<deepseek key>` 与 `export OPENAI_BASE_URL=https://api.deepseek.com/v1`
   （OpenAI SDK 原生读 `OPENAI_BASE_URL`，从而把 openai provider 指向 DeepSeek 端点）
3. **必须显式传 `model="deepseek-chat"`**；省略 model 会 422（`model: invalid type: null`）。

正确调用：

```text
mcp__semantica__extract_entities(
  text="…18319平方米…", method="llm", language="zh", model="deepseek-chat")
→ entities: [上海财经大学(ORG), 中山北一路校区(GPE), 18319平方米(CONCEPT), …]
```

**已知工具级缺陷**：`extract_relations` 的 MCP 包装**硬编码 NER 步为 `methods=["ml"]`**（spaCy 未装），
且 `TripletExtractor()` 用默认（pattern）；因此**经 MCP 无法走 LLM 抽关系/三元组**（返回空）。
关系与三元组请走 **Python API**：

```python
from semantica.semantic_extract import RelationExtractor, TripletExtractor
RelationExtractor(method="llm", provider="deepseek", llm_model="deepseek-chat")
TripletExtractor(method="llm", provider="deepseek", llm_model="deepseek-chat")
# 实测：1 个 chunk → 24 关系 / 25 三元组
```

**改完 env 后必须让 MCP 进程重生**：kill 掉 semantica 的 python 进程（Host 会懒重生），或重启 dsh web。
进程只在启动时读一次 env，运行中修改无效。

### 已决：不装 spaCy、不给 Semantica MCP 打补丁（2026-10-13）

评估过三个选项，结论如下（**后续不要再重新讨论**）：

| 选项 | 结论 | 理由 |
|---|---|---|
| 装 spaCy + zh 模型 | **否决** | 只能救 `mcp_server/__init__.py` 第 160 行写死的 `methods=["ml"]`，救不了第 162 行 `TripletExtractor()` 的漏传（签名本就支持 method）→ 三元组照样空；zh 通用模型抽不到领域指标；且会让 NER 工具与关系工具走两套引擎，同文本实体不一致 |
| 修 MCP 包装（约 5 行） | **暂不做** | 技术上可行，但改 site-packages，升级即丢 |
| **走 Python API** | **采纳** | 实测 1 chunk → 24 关系 / 25 三元组；provider/model 完全可控；已固化 `semantica_verify/` |

**A 方案下的通道分工（照此执行）**：

| 能力 | 走哪条通道 |
|---|---|
| 中文实体抽取 | MCP `extract_entities(method="llm", language="zh", model="deepseek-chat")` 或 Python API |
| 中文关系 / 三元组抽取 | **仅 Python API**：`RelationExtractor / TripletExtractor(method="llm", provider="deepseek", llm_model="deepseek-chat")` |
| 规则推理（实体归一判官） | MCP `run_reasoning` 或 `semantica.reasoning` |
| 决策台账 | MCP `record_decision` / `query_decisions` / `find_precedents` |
| 图谱 CRUD / 分析 / 导出 | MCP `add_entity` / `add_relationship` / `update_node` / `query_graph` / `get_graph_analytics` / `export_graph` |

上游 `semantica 0.7.0` 是本机最新版（PyPI 确认），无修复版可升。

### 已决：解析保持 DocumentParser，暂不部署 docling（2026-10-14）

| 项 | 结论 |
| --- | --- |
| 结论 | **保持 semantica.parse.DocumentParser**（Semantica 官方标准路径，非第三方替代，不构成降级） |
| docling 定位 | Semantica 的 **optional extra**：`Provides-Extra: parse-docling` / `Requires-Dist: docling>=2.107.0`；包内只有适配器 `docling_parser.py`，**不含 docling 本体** |
| 实测缺口 | 31 表 / 1551 单元格中 **270 个合并单元格(17.4%)** 被 python-docx 重复填充，**真实 colspan/rowspan 无法还原**；无表头识别；无 OCR；无版面模型 |
| 不装的依据 | ① 本件是 Word 2007+ 原生 docx，**非扫描件 -> OCR 无需求**；② 表格规模不大；③ docling 会引入 **torch**，此前实测与 numpy 2 冲突并**打穿过 `semantica.vector_store`**；④ 标准路径已够用 |
| 已做的缓解 | 按「左/上邻同值置空」去合并渲染（`ingest_parse/tables-by-semantica.md`），并把结构化表落盘（`tables.jsonl`） |
| 复核触发条件 | 出现扫描件 / 批量表格密集文档 / 需要真实单元格跨度或表头时，再部署并做安装后回归验证 |

**教训**：Semantica 是**适配层**——带接口，不带被适配的实体。向量（需 fastembed）、解析（需 docling）、LLM（需 provider key）都是同一形态；装之前先确认 extra 与依赖，并做安装后回归验证。

### 已决：不重建语料（2026-10-14）

**背景**：本轮补齐了 `source/original.docx`（1,123,286 B / 12 图 / 31 表），并用 Semantica 解析出
150,841 字正文 + 31 个表格的结构化数据（1,551 单元格）。但语料的 **1208 chunk 与 442 事实**
仍是基于【资料库文本视图】构建的，表格在语料中呈**扁平文本**。

**决定**：本轮**不重建语料**。核心数字保持不变（442 事实 / 1208 chunk / 13 冲突 / 7 缺口 / 514 关系）。

**含义**：

| 项 | 状态 |
| --- | --- |
| `外部核验/ingest_parse/tables.jsonl`（1,551 单元格） | 与语料**解耦**，仅作外部核验产物 |
| 语料中 31 个表格的内容 | 仍为扁平文本（如投资估算表、用水量表、技术指标表） |
| 若将来要表格入语料 | 需以 `parsed-by-semantica.md` + `tables.jsonl` 为源重跑七道工序，**核心数字会全部重算** |

**这不是跳过 Semantica**：加载与解析环节已真实执行并留证（`ingest_parse/semantica-attestation.yaml`），
只是**解析结果未回灌语料构建链**——属产品决策，非能力缺失。
