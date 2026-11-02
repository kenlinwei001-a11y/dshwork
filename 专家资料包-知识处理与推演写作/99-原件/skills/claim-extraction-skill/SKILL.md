---
name: claim-extraction-skill
description: "识别判断、结论、风险、预测、因果与建议等 Claim，并建立依赖关系。触发：挑出结论和风险、区分事实与观点、整理因果链与中间结论。不适用：判定真伪（claim-validation）、定位原文出处（evidence-extraction）。"
---

# Claim Extraction Skill

## Skill ID
SK-07

## Purpose
识别判断、结论、风险、预测、因果判断和建议等 Claim，并建立依赖关系。

## 何时使用

调用条件：已有 Sentence 或 Chunk 文本。
- 典型请求：挑出结论和风险｜区分事实与观点｜整理因果链与中间结论
- 不要在此调用：判定真伪（claim-validation）、定位原文出处（evidence-extraction）
## 边界与不适用

- 不做：不判真伪、不改写原文措辞
- 不做：引述他人观点需标注归属，不算作者 Claim
- 缺输入：先有 Sentence 或 Chunk
