---
name: sentence-segmentation-skill
description: "把 Chunk 切成 Sentence 并生成稳定的 Sentence ID。触发：给每句话编号、分句以便引用定位、准备 Claim 追踪的句子粒度。不适用：语义分块（semantic-chunking）、摘要改写。"
---

# Sentence Segmentation Skill

## Skill ID
SK-02

## Purpose
将 Chunk 切分为 Sentence，并生成稳定的 Sentence ID，支撑 Claim 追踪和 Semantic Diff。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：给每句话编号｜分句以便引用定位｜准备 Claim 追踪的句子粒度
- 不要在此调用：语义分块（semantic-chunking）、摘要改写
## 边界与不适用

- 不做：不改写句子、不做摘要
- 不做：ID 在同一修订内保持稳定，不因重跑重排
- 缺输入：先有 Chunk
