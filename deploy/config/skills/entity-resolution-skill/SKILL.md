---
name: entity-resolution-skill
description: "解决同义词、别名、简称与跨文档重复，并识别 NOT_SAME 与 AMBIGUOUS。触发：这两个名字是不是同一家、合并别名和简称、跨文档去重。不适用：新增实体、判定实体类型。"
---

# Entity Resolution Skill

## Skill ID
SK-11

## Purpose
解决同义词、别名、简称和跨文档实体重复问题，并识别 NOT_SAME 与 AMBIGUOUS。

## 何时使用

调用条件：已有实体列表及各自的证据提及（mention）。
- 典型请求：这两个名字是不是同一家｜合并别名和简称｜跨文档去重
- 不要在此调用：新增实体、判定实体类型
## 边界与不适用

- 不做：证据不足时输出 AMBIGUOUS 或 NOT_SAME，不硬合并
- 不做：不改写实体描述与原文提及
- 缺输入：先有实体列表及各自的证据提及
