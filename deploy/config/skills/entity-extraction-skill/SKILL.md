---
name: entity-extraction-skill
description: "抽取企业、基地、车间、产线、客户、材料、供应商等实体及其 mention。触发：把文中出现的公司和供应商列出来、有哪些产线与材料、抽取所有实体。不适用：同名消歧（entity-resolution）、本体类型归属（ontology-resolution）。"
---

# Entity Extraction Skill

## Skill ID
SK-03

## Purpose
从文本中抽取企业、基地、车间、产线、客户、材料、供应商等实体及其 mention。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：把文中出现的公司和供应商列出来｜有哪些产线与材料｜抽取所有实体
- 不要在此调用：同名消歧（entity-resolution）、本体类型归属（ontology-resolution）
## 边界与不适用

- 不做：不推断文中未出现的实体
- 不做：不合并别名，保留 mention 原文与位置
- 缺输入：先有 Sentence 或 Chunk
