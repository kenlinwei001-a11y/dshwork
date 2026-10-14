---
name: semantic-graph-compilation-skill
description: "将 Entity、Fact、Claim、Evidence、Reasoning、Scenario、Decision 等编译成统一 Semantic Graph。"
---

# Semantic Graph Compilation Skill

## Skill ID
SK-15

## Purpose
将 Entity、Fact、Claim、Evidence、Reasoning、Scenario、Decision 等编译成统一 Semantic Graph。

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

<!-- kp-patch:v1 -->
## 论断级关系词表（7 类扩展）

原 `TEN_RELATIONS`（has_value / has_attribute / instance_of / part_of / causes /
depends_on / supports / contradicts / temporal / located_in）覆盖的是**事实与实体**关系。
论断之间还需要 7 类，否则 `premise_refs` / `derived_from` 字段**无从填充**——
不是不想填，是**没有可填的语义槽**。

| 关系 | 语义 | 端 |
|------|------|----|
| `cites` | 这条结论依据哪条规范/文件 | claim → mandate |
| `restates` | 总论/结论复述各章结论 | claim → claim |
| `causes` | 因果链条 | claim → claim |
| `derives` | 显式推演派生 | claim → claim |
| `precedes` | 论证顺序/前置条件 | claim → claim |
| `quantifies` | 结论与其数值绑定 | claim → node |
| `specializes` | 通则落到本项目 | claim → mandate |

实现：`corpus_pipeline/relations_ext.py`（`CLAIM_RELATIONS` + `derive_expected_relations`）。

**「复述层」必须是节点层，不只是边**：可行性研究报告的「总论」与「结论」按体例是
**全篇论断的复述层**。若该层没有 claim 节点，`restates` 边无从建立，
后果是：①改一处漏三处无法被机检；②「结论章不得出现新数」无法机检。
因此编译时须保证总论/结论章**成层**（有 claim 节点），而不只是补边。

