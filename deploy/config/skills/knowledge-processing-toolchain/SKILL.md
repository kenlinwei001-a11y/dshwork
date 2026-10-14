---
name: knowledge-processing-toolchain
description: 以「工具 + LLM」分层模式做知识处理。确定性步骤（分句、分块、图谱编译、溯源、数字/时间冲突、schema 校验）调用 kp_toolkit 代码执行（零 LLM、可复现）；语义步骤（实体/事实/关系/Claim/证据/推理抽取、证据判断、推演写作）才调用 LLM，且必须按 schema 输出 JSON 并经 validator 校验、失败重试。当用户要求把文档/语料处理为结构化知识图谱、或要求「确定性走工具、语义走 LLM」时使用。
---

# 知识处理工具链（Tool + LLM）

## 核心原则

**能确定性计算的，绝不交给模型去"猜"；只有真正需要语义理解的，才调用 LLM。**

把知识处理流水线拆成两层：

```
确定性底座（工具层，kp_toolkit，零 LLM，可复现可单测）
  分句 · 分块 · 图谱编译 · 溯源链 · 数字/时间冲突 · schema 校验
        ↓ 输出结构化 JSON
语义层（LLM，结构化调用 + schema + validator + 重试）
  实体/事实/关系/Claim/证据/推理抽取 · 证据充分性判断 · 推演写作
```

## 确定性步骤（用工具，不调 LLM）

| 步骤 | kp_toolkit 函数 | 说明 |
|------|-----------------|------|
| 分句 | `segment_sentences(text, doc_id)` | 稳定 ID，同输入同输出 |
| 分块 | `segment_chunks(text, doc_id)` | 按标题/空行切块 |
| 图谱编译 | `compile_graph(items, project_id, version_id)` | 八类节点装配 |
| 图谱校验 | `validate_graph(graph)` | 悬空引用 / 重复 id |
| 溯源链 | `build_provenance(node_id, graph)` | 反向追到证据 |
| 数字冲突 | `detect_numeric_conflicts(facts)` | 输出「待审」 |
| 时间冲突 | `detect_time_conflicts(facts)` | 输出「待审」 |
| schema 校验 | `validate_schema(nodes, kind)` | 必填字段检查 |

运行方式：`python3 -m kp_toolkit.cli <command>`，或 `import kp_toolkit`。
自测：`python3 -m kp_toolkit.test_kp_toolkit`（全绿才算工具层就绪）。

## 语义步骤（才调 LLM，必须结构化）

只有以下步骤调用 LLM，且必须：
1. 按 `schema/output.json` 契约输出 JSON（不裸奔自由文本）。
2. 输出后立即经 `validators/validator.py` 确定性校验。
3. 校验失败 → 重试（最多 3 次）→ 仍失败则显式标记「待审」。

- 实体抽取（entity-extraction-skill）
- 事实抽取（fact-extraction-skill）
- 关系抽取（relation-extraction-skill）
- Claim 抽取（claim-extraction-skill）
- 证据/推理抽取（evidence-/reasoning-extraction-skill）
- 证据充分性判断（claim-validation-skill）
- 推演写作（graph-deductive-writing-skill）

## 工作流

1. 判定任务与文档类型，确定领域本体。
2. 工具层：解析 → 分句 → 分块 → 建图 → 溯源 → 数值/时间冲突 → schema 校验（全代码）。
3. LLM 层：语义抽取（结构化 + validator + 重试）。
4. 图谱编译与审计：统一图谱 + 冲突待审清单 + 质量审计。
5. 下游交付：检索 / 推演 / 写作，绑定证据与溯源链。

## 生产工具映射（从 kp_toolkit 升级到第三方库时）

- 分句/分块：spaCy / jieba / semantic-text-splitter
- 文档解析：docling / unstructured / PyMuPDF / python-docx / openpyxl
- 中文 NER：HanLP / LTP
- 图谱存储：rdflib / NetworkX / Neo4j / GraphRAG
- 向量检索：Qdrant / pgvector / Milvus
- 实体消解：dedupe / recordlinkage / sentence-transformers + faiss

## 铁律

- 确定性步骤绝不用 LLM 复现（否则失去可复现/可审计性）。
- LLM 步骤绝不裸奔自由文本，必须 schema + validator。
- 冲突一律「待审」，不擅自改数字或补口径。
- 缺失事实保持显式未知，不编造。

<!-- kp-patch:v1 -->
## 客观判据清单（判定不消费 LLM 的意见）

`corpus_pipeline/objective_criteria.py` 提供 12 条**确定性**判据（K1–K12）。
判据类型仅允许 8 种：**集合差 / 守恒等式 / 正则计数 / 数值比较 / 哈希一致 / 图算法 / 枚举成员 / 覆盖率比值**。

**三条铁律**：

1. **LLM 产出候选，工具判定候选是否合格**；判定**不消费 LLM 的意见**。
2. **无法客观化的项不得冒充 pass** —— 标 `judgment_required`，
   既不进自动门禁也不计为通过，交人工。
   当前明确列入的 3 项：论证是否成立、证据支持等级的语义判断、取舍是否可接受。
3. **探针必须自证**：每个探针须先在源中命中一个已知存在的正样本；
   未过标定则该判据 `invalid`。
   （教训：曾三次因探针故障把「探针坏了」误报成「源里没有」。）

**为什么不能用 NLP 分类器替代**：那只是把「LLM 主观」换成「模型主观」，
仍是不确定判定；写进 pass 通道比没有门禁更糟——它给了一个**虚假的保证**。

**需要的是确定性组件，不是模型**：中文分句器、量纲归一表、别名归并（编辑距离）、
表格解析器。四者均为输入确定、输出确定、可单测，且标准库即可实现。

