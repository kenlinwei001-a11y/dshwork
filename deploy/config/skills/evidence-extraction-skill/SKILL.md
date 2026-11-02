---
name: evidence-extraction-skill
description: "定位支撑 Fact 或 Claim 的原始证据（文档、页码、章节、Chunk、Sentence、文本范围）。触发：找出处和页码、给结论配原文、定位到具体段落。不适用：评价证据强弱与关系类别（claim-evidence-binding）。"
---

# Evidence Extraction Skill

## Skill ID
SK-08

## Purpose
定位支持 Fact 或 Claim 的原始证据，包括文档、页码、章节、Chunk、Sentence 和文本范围。

## 何时使用

调用条件：已有 Fact/Claim 与原文 IR（可定位到页码/段落）。
- 典型请求：找出处和页码｜给结论配原文｜定位到具体段落
- 不要在此调用：评价证据强弱与关系类别（claim-evidence-binding）
## 边界与不适用

- 不做：不生成不存在的引用
- 不做：找不到时输出缺失，不用相近段落冒充
- 缺输入：先有 Fact/Claim 与原文 IR
