---
name: ontology-resolution-skill
description: "把候选 Entity 映射到项目 Ontology Registry 的标准类型、属性与约束。触发：按本体归类、映射到标准类型、检查属性是否符合约束。不适用：创建或扩写本体（需人工评审）。"
---

# Ontology Resolution Skill

## Skill ID
SK-04

## Purpose
将候选 Entity 映射到项目 Ontology Registry 中的标准类型、属性和约束。

## 何时使用

调用条件：已有 Ontology Registry（标准类型/属性/约束）与待映射实体。
- 典型请求：按本体归类｜映射到标准类型｜检查属性是否符合约束
- 不要在此调用：创建或扩写本体（需人工评审）
## 边界与不适用

- 不做：不擅自新增类型或修改约束
- 不做：找不到合适类型时输出待评审候选，不硬塞
- 缺输入：先有 Ontology Registry 与待映射实体
