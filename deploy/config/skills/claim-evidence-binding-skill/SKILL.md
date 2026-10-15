---
name: claim-evidence-binding-skill
description: "判断 Evidence 与 Claim 的关系：SUPPORT、PARTIAL_SUPPORT、CONTRADICT、CONTEXT 或 INSUFFICIENT。"
---

# Claim Evidence Binding Skill

## Skill ID
SK-09

## Purpose
判断 Evidence 与 Claim 的关系：SUPPORT、PARTIAL_SUPPORT、CONTRADICT、CONTEXT 或 INSUFFICIENT。

## Input
- `project_id`
- `document_id`
- `version_id`
- 上游 Skill 输出
- 原文或结构化中间结果

## Output
必须输出稳定 ID、结构化结果以及 provenance/来源关联字段。

## Execution Rules
1. 只使用输入中存在或可由明确规则推导的信息，不编造事实。
2. 所有结果尽可能绑定 `project_id`、`document_id`、`version_id`。
3. Fact、Claim、Evidence、Reasoning 必须保留来源链。
4. 发现冲突时输出冲突状态，不擅自裁决。
5. 不得在没有复用策略的情况下跨项目复制项目专属事实。

## 位置锚与重绑（identity ≠ position）

**claim/evidence/node 一律携带 `anchor`**：
```yaml
anchor:
  doc_span: [起始, 结束]     # 主锚：文档绝对偏移（与切块/分句无关）
  quote: "逐字引文"          # 主锚：重绑抓手
  sentence_id: c-xxxx-S001   # 索引：可重建
  slice_id: c-xxxx           # 代指：当前这一代（**不是身份**）
  order: 3                   # 同一切片内次序
  locatable: true
  precision: exact|slice     # 精度分级
  position_status: ok|UNLOCATED|DANGLING
```

**重绑 `rebind_positions()`**：
- 触发：**重切块 / 重分句 / 客户改稿**后
- 做法：用 `doc_span`/`quote` 在当前正文里**重新定位**，回填**当前这一代**的 `slice_id`/`sentence_id`
- **铁律**：**逻辑对象 ID 不变**（只改锚）；重绑不到 ⇒ `position_status: DANGLING` **待审**，不静默、不清零
- 实证：本项目 4 条 claim 位置悬空（切片已不存在）⇒ 重绑**修复 2 条**（ID 未变），2 条为概括句、诚实保持待审


## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。
