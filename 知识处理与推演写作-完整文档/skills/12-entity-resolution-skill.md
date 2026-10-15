# Skill · entity-resolution-skill（SK-11）

## 名称与定位

- **名称**：`entity-resolution-skill`（Skill ID SK-11）
- **一句话**：解决同义词、别名、简称和跨文档实体重复问题，并识别 NOT_SAME 与 AMBIGUOUS。

## 角色

七道工序**第 4 道「本体抽取」**的消歧通道。跨文档同名/异名实体的统一与消歧，防止同一实体被拆成多个节点、不同实体被错误合并。

## 输入

候选实体/mention（entity-extraction 输出）+ 上下文

## 输出

- 合并/归一结果：alias/简称 → canonical entity
- NOT_SAME（同名不同实体，显式分离）
- AMBIGUOUS（无法判定，保留歧义，不强行映射）

## 执行规则

- 判定附证据（上下文/属性比对）。
- 不确定即 AMBIGUOUS，绝不强行合并或分离（与 EntityRegistry 的 ambiguous 判定一致）。
- 归一结果回写 mention 归属。

## 关系

上游：entity-extraction-skill；下游：ontology-resolution-skill、relation-extraction-skill、semantic-graph-compilation-skill。
