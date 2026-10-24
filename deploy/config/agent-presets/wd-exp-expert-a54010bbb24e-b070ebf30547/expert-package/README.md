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

## 工具 + LLM 映射（21 个技能 → 分层）

| 档 | 技能 | 模式 |
|----|------|------|
| 🔵 确定性工具 | sentence-segmentation / provenance-binding / semantic-graph-compilation / document-parsing(格式) / conflict-detection(数字·时间) | 代码，零 LLM |
| 🟡 混合 | entity-resolution / ontology-resolution / semantic-chunking / claim-evidence-binding / evidence-extraction / extraction-quality-audit | 工具打底 + LLM 兜底 |
| 🔴 语义 LLM | fact/entity/relation/claim/reasoning 抽取 / claim-validation / graph-deductive-writing / knowledge-generalization | LLM 结构化 + validator |
| ⚙️ 编排 | knowledge-processing-toolchain | 工具+LLM 分层 SOP |

## 交付物

- 统一语义图谱 JSON（entities/relations/facts/reasoning/claims/evidence/conflicts/validations）
- 冲突待审清单、证据覆盖审计表、schema 校验结果
- 绑定证据与溯源链的正文（下游）

## 状态

- 已完成：专家发布、工具层、七道工序、30 文件契约、存储后端、MCP、toolchain 技能。
