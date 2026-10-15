# Skill · evidence-extraction-skill

## 名称与定位

- **名称**：`evidence-extraction-skill`
- **一句话**：定位支持 Fact 或 Claim 的原始证据，包括文档、页码、章节、Chunk、Sentence 和文本范围。

## 角色

七道工序**第 4 道「本体抽取」**的证据通道。Evidence 节点是溯源链的末端——每条论断最终要追到原文定位（SourceAnchor 含 table_cell/char）。

## 输入

Fact/Claim + 原文（Document IR + Sentence/Chunk 定位）

## 输出

- Evidence 列表：evidence_id、类型（文档/表格/图/脚注）、文档、页码、章节、Chunk、Sentence、文本范围
- 可信度/版本信息
- 与 Fact/Claim 的绑定

## 执行规则

- 证据必须锚定到原文精确定位（document_id + table_cell/char，validate_source_anchor 校验）。
- 一条证据可支撑多条事实；一条事实可有多条证据。
- 找不到证据时显式声明「无证据」，不硬编。

## 关系

上游：document-parsing / sentence-segmentation；下游：claim-evidence-binding-skill、provenance-binding-skill、graph-deductive-writing-skill（引用体例成句）。
