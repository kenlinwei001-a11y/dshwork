# 技能变更：v1.1.0（契约同步裁决）

> 目标：消除「规则卡」在契约 / 本体 / 校验器三处的口径冲突。
> 原则：契约优先，改实现不改数据；任何校验项必须能在契约中指到一行。

## 1 冲突与裁决

| # | 冲突 | 证据 | 裁决 |
|---|---|---|---|
| 1 | 契约谓 predicate 与 qualitative_check 二选一；本体 `Rule.required` 硬列 predicate | 定性卡 104 条 ERROR | 本体移除 predicate；新增 XOR 不变式（两者必居其一、不得并存、定性四键必填） |
| 2 | 契约页码只在 `anchor.page`；`cap.py lint` 要求顶层 `page` | 64/64 卡 anchor_complete 失败 | lint 改为 `page` 或 `anchor.page` 二取一（同一事实不设两处） |
| 3 | `SKILL.md` 要求 `primitives[]`（P1–P8）；契约从未定义 | SKILL.md L30/L41 | 删去 P1–P8 与 primitives，改为「predicate.op 取规范 §3 枚举或 qualitative_check 三档」 |
| 4 | 本体 `Gap.required` 用 desc/affects/min_request；SES 规范 §11 用 description/affected_clauses/request | 22 条 ERROR | 本体与 `check_gaps` 均改用规范字段名，兼容旧名 |
| 5 | 本体 `Element.obligation` 枚举缺 INFO；资料性要素无法表达 | 28 条 WARN | 契约 §5 与本体枚举补 INFO（表示无义务），warn 不再误报 |

## 2 改动文件

- `references/audit-rule-card-spec.md`：新增 v1.1 字段位置约定（页码只在 anchor；严格二选一；定性卡 NO_PASS）
- `references/standard-element-schema.md`：obligation 枚举补 INFO
- `scripts/ontology.json`：Rule.required 去 predicate；Gap.required 改规范字段名；Element.obligation 补 INFO；新增两条不变式说明
- `scripts/validate_ontology.py`：新增 `check_rule_predicate_xor`；`check_gaps` 用 affected_clauses；INFO 不再告警
- `scripts/cap.py`：`anchor_complete` 从 anchor 取 page
- `SKILL.md`：删 primitives/P1–P8，指向 §3 算子枚举
- 新增 `scripts/merge_ses.py`：确定性 SES 合并（07/02/03 + audit_result → ses.json，含 counts 与 sha）
- 新增 `tests/test_contract.py` + 4 个 fixture：数值卡、定性卡、两者都缺、两者并存

## 3 验收

```
python3 tests/test_contract.py        → contract: ALL PASS
validate_ontology.py --ses HJ84.ses   → ERROR 0  WARN 0（v1.1 后）
cap.py lint --ses HJ84.ses            → errors=0 warnings=0 ok=True
```

## 4 未纳入（需单独裁决）

- 是否给 Rule 增加顶层 `page`（当前结论：不设，避免同一事实两处）
- P1–P8 若未来要做"谓词级统计"，需以 `predicate.op` 为准升 v1.2，而不是恢复 primitives
