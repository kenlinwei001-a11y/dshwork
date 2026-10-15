# Skill · relation-extraction-skill（SK-05）

## 名称与定位

- **名称**：`relation-extraction-skill`（Skill ID SK-05）
- **一句话**：抽取实体之间的业务语义关系，并绑定关系证据和来源 Sentence。

## 角色

七道工序**第 4 道「本体抽取」**的关系通道：实体之间的边（供给、投资、隶属、位于、生产等），是推演链与影响传播的结构基础。

## 输入

实体列表 + Sentence/Chunk + 关系类型体系（十类关系/领域关系）

## 输出

- 关系列表：relation_id、from、to、type、时间范围
- 每条关系绑定证据 + 来源 Sentence（供溯源与反向回读）

## 执行规则（语义，LLM 结构化 + validator）

- from/to 必须指向已存在实体 id（validator 校验悬空引用）。
- 关系 type 必须来自合法类型集合。
- 关系必须绑定来源 Sentence（无证据的关系不成立）。

## 关系

上游：entity-extraction / entity-resolution / ontology-resolution；下游：semantic-graph-compilation-skill（边装配）。
