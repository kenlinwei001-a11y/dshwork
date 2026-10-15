# Skill · entity-extraction-skill（SK-03）

## 名称与定位

- **名称**：`entity-extraction-skill`（Skill ID SK-03）
- **一句话**：从文本中抽取企业、基地、车间、产线、客户、材料、供应商等实体及其 mention。

## 角色

七道工序**第 4 道「本体抽取」**的实体通道。实体是图谱的节点基础，mention 是实体的文本出现（支持消歧与溯源）。

## 输入

Sentence/Chunk（含原文定位）+ 领域本体提示（Ontology Registry）

## 输出

- 实体列表：entity_id、type（企业/基地/车间/产线/客户/材料/供应商等）、canonical name
- mention 列表：mention_id、entity_id、sentence_id、文本范围、normalized surface

## 执行规则（语义，LLM 结构化 + validator）

- 按 schema 输出 JSON；validator 校验类型合法性与字段完整性，失败重试。
- 只抽取输入中真实出现的实体，不推断不编造。
- mention 必须绑定来源 Sentence。

## 关系

下游：entity-resolution-skill（消歧）、ontology-resolution-skill（本体映射）、relation-extraction-skill（关系）。
