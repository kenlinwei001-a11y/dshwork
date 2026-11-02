---
name: extraction-quality-audit-skill
description: "对抽取结果执行结构完整性、证据覆盖、关系合法性、跨项目污染与孤立节点审计。触发：检查抽取质量、有没有漏证据或悬空关系、有没有跨项目串数据。不适用：修复数据（本 skill 只出问题清单）。"
---

# Extraction Quality Audit Skill

## Skill ID
SK-17

## Purpose
对抽取结果执行结构完整性、证据覆盖、关系合法性、跨项目污染和孤立节点等质量审计。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：检查抽取质量｜有没有漏证据或悬空关系｜有没有跨项目串数据
- 不要在此调用：修复数据（本 skill 只出问题清单）
## 边界与不适用

- 不做：只审计不改数据
- 不做：问题按严重度分级并附样例 ID
- 缺输入：先有抽取结果与图谱
