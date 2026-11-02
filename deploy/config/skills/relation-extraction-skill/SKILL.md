---
name: relation-extraction-skill
description: "抽取实体之间的业务语义关系，并绑定关系证据与来源 Sentence。触发：谁供应谁、产线和产品是什么关系、建立关系图谱。不适用：抽取属性事实（fact-extraction）、判定关系真假。"
---

# Relation Extraction Skill

## Skill ID
SK-05

## Purpose
抽取实体之间的业务语义关系，并绑定关系证据和来源 Sentence。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：谁供应谁｜产线和产品是什么关系｜建立关系图谱
- 不要在此调用：抽取属性事实（fact-extraction）、判定关系真假
## 边界与不适用

- 不做：不发明关系类型，沿用本文档定义的七族开放词表
- 不做：每条关系必须有证据句，无证据不落库
- 缺输入：先有实体与证据句
