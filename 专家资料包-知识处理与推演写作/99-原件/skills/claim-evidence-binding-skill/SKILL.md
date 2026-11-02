---
name: claim-evidence-binding-skill
description: "判定 Evidence 与 Claim 的关系：SUPPORT、PARTIAL_SUPPORT、CONTRADICT、CONTEXT 或 INSUFFICIENT。触发：这条结论有没有证据支持、证据和说法是否矛盾、标出证据支持强度。不适用：最终裁决冲突（conflict-detection 只输出待审）、改写 Claim。"
---

# Claim Evidence Binding Skill

## Skill ID
SK-09

## Purpose
判断 Evidence 与 Claim 的关系：SUPPORT、PARTIAL_SUPPORT、CONTRADICT、CONTEXT 或 INSUFFICIENT。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：这条结论有没有证据支持｜证据和说法是否矛盾｜标出证据支持强度
- 不要在此调用：最终裁决冲突（conflict-detection 只输出待审）、改写 Claim
## 边界与不适用

- 不做：只判关系类别，不做最终裁决
- 不做：证据不足一律 INSUFFICIENT，不拔高为 SUPPORT
- 缺输入：先有 Claim 与候选证据
