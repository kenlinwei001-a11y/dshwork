---
name: reasoning-extraction-skill
description: "识别公式、规则、多步推导与中间结论，形成 Reasoning 节点及输入输出依赖。触发：把推导过程抽出来、整理公式与规则、还原推理链。不适用：抽取结论 Claim、生成新的推导。"
---

# Reasoning Extraction Skill

## Skill ID
SK-10

## Purpose
识别公式、规则、多步推导和中间结论，形成 Reasoning 节点及输入输出依赖。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：把推导过程抽出来｜整理公式与规则｜还原推理链
- 不要在此调用：抽取结论 Claim、生成新的推导
## 边界与不适用

- 不做：不补写缺失步骤、不替作者合理化跳跃
- 不做：无法复原的环节标 GAP，不虚构
- 缺输入：先有包含公式或规则步骤的原文
