---
name: claim-extraction-skill
description: "识别判断、结论、风险、预测、因果判断和建议等 Claim，并建立依赖关系。"
---

# Claim Extraction Skill

## Skill ID
SK-07

## Purpose
识别判断、结论、风险、预测、因果判断和建议等 Claim，并建立依赖关系。

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

## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。
