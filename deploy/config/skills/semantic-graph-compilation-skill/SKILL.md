---
name: semantic-graph-compilation-skill
description: "把 Entity、Fact、Claim、Evidence、Reasoning、Scenario、Decision 编译成统一 Semantic Graph。触发：合成语义图谱、把抽取结果连成图、生成 semantic graph JSON。不适用：新增事实或判断、图数据库运维。"
---

# Semantic Graph Compilation Skill

## Skill ID
SK-15

## Purpose
将 Entity、Fact、Claim、Evidence、Reasoning、Scenario、Decision 等编译成统一 Semantic Graph。

## 何时使用

调用条件：已有各类抽取产物（Entity/Fact/Claim/Evidence/Reasoning/Scenario/Decision）。
- 典型请求：合成语义图谱｜把抽取结果连成图｜生成 semantic graph JSON
- 不要在此调用：新增事实或判断、图数据库运维
## 边界与不适用

- 不做：只编译不新增内容
- 不做：引用关系词表而不复制；非法引用报错，不静默丢弃
- 缺输入：先有各类抽取产物
