---
name: provenance-binding-skill
description: "建立对象间来源链，使 Decision 可反向追溯到 Claim、Reasoning、Fact、Evidence、Sentence、Chunk 与 Document。触发：给结论挂溯源链、检查引用是否悬空、决策能不能倒查到原文。不适用：判断内容真假、补造来源。"
---

# Provenance Binding Skill

## Skill ID
SK-16

## Purpose
建立对象之间的来源链，使 Decision 可以反向追溯到 Claim、Reasoning、Fact、Evidence、Sentence、Chunk 和 Document。

## 何时使用

调用条件：已有上下游对象及其定位信息。
- 典型请求：给结论挂溯源链｜检查引用是否悬空｜决策能不能倒查到原文
- 不要在此调用：判断内容真假、补造来源
## 边界与不适用

- 不做：只建链不造链
- 不做：悬空引用显式标记，不静默删除
- 缺输入：先有上下游对象及其定位信息
