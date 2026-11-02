---
name: semantic-chunking-skill
description: "按章节、主题和语义边界把 Document IR 切成稳定 Chunk。触发：把文档切成块、按章节分段、为抽取准备输入。不适用：分句与编号（sentence-segmentation）、改写润色。"
---

# Semantic Chunking Skill

## Skill ID
SK-01

## Purpose
按照章节、主题和语义边界将 Document IR 切分为稳定的语义 Chunk，供后续抽取和检索使用。

## 何时使用

调用条件：已有 document-parsing-skill 产出的 Document IR（含页码、段落与原文定位）。
- 典型请求：把文档切成块｜按章节分段｜为抽取准备输入
- 不要在此调用：分句与编号（sentence-segmentation）、改写润色
## 边界与不适用

- 不做：只切块，不改写原文
- 不做：不跨章节强行合并；表格与代码整块保留
- 缺输入：先有 document-parsing-skill 产出的 Document IR
