# 知识处理专家（knowledge-processing-expert）

以「工具 + LLM」分层架构，把文档与语料处理为结构化知识图谱的知识处理专家。

## 定位

- **专家类型**：单专家（agent）
- **人格**：沈溯源，知识处理专家
- **核心方法**：工具 + LLM 分层 —— 确定性步骤（解析/分句/建图/溯源/数值冲突/schema 校验）由工具（代码）执行，语义步骤（抽取/判断/推演）由 LLM 结构化调用 + validator 校验。

## 架构分层

```
确定性底座（工具层）：解析·分句切块·图谱编译·溯源·数字冲突·schema 校验
        ↓
语义层（LLM 编排）：实体/事实/关系/Claim/证据/推理抽取 · 证据判断 · 推演写作
        ↓
领域层（动态加载）：按文档类型加载领域本体与模板
```

## 工具 + LLM 映射（20 个技能 → 分层）

| 档 | 技能 | 模式 |
|----|------|------|
| 🔵 确定性工具 | sentence-segmentation / provenance-binding / semantic-graph-compilation / document-parsing(格式) / conflict-detection(数字·时间) | 代码，零 LLM |
| 🟡 混合 | entity-resolution / ontology-resolution / semantic-chunking / claim-evidence-binding / evidence-extraction / extraction-quality-audit | 工具打底 + LLM 兜底 |
| 🔴 语义 LLM | fact/entity/relation/claim/reasoning 抽取 / claim-validation / graph-deductive-writing / knowledge-generalization | LLM 结构化 + validator |

## 生产工具选型（GitHub 调研）

| 环节 | 首选 | 备选 |
|------|------|------|
| 文档解析 | [docling](https://github.com/docling-project/docling) / [unstructured](https://github.com/Unstructured-IO/unstructured) | PyMuPDF / python-docx / openpyxl / marker-pdf |
| 中文 NER | [HanLP](https://github.com/hankcs/HanLP) / [LTP](https://github.com/HIT-SCIR/ltp) | spaCy zh_core_web / jieba |
| 分句切块 | spaCy / semantic-text-splitter | jieba / 正则 |
| 知识图谱 | [rdflib](https://github.com/RDFLib/rdflib) / [NetworkX](https://github.com/networkx/networkx) | [Neo4j](https://github.com/neo4j/neo4j) / GraphRAG |
| 向量检索 | [Qdrant](https://github.com/qdrant/qdrant) / pgvector | Milvus / FAISS / Chroma |
| 实体消解 | dedupe / recordlinkage | sentence-transformers + faiss |

## 交付物

- 统一语义图谱 JSON（entities/relations/facts/reasoning/claims/evidence/conflicts/validations）
- 冲突待审清单、证据覆盖审计表、schema 校验结果
- 绑定证据与溯源链的正文（下游）

## 状态

- 已完成：专家重定位为「知识处理专家」、工具+LLM 分层架构、20 技能映射、GitHub 工具调研。
- 待完成：确定性工具代码落地、tool+LLM 技能重建、依赖预装、校验发布。

## 头像

当前未绑定头像。推荐 512×512 PNG/JPG（≤500KB），专业插画风：一位资深知识工程专家，背景为知识图谱节点与数据流，青蓝色（cyan-teal）调，与 categoryId `04-DataAI` 一致。
