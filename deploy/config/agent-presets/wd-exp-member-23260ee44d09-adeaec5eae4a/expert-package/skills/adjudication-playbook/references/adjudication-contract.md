# 裁定契约（5 号）

## 1 输入

- 3/4 号 audit_result（逐条）
- 证据包（report/documents/fields/records/missing/consistency_flags）
- report_standard（method_match）
- 规则（用于回指，不重新执行）

## 2 合并优先级

FAIL > CONFLICT_PENDING > UNVERIFIABLE > PASS / NOT_APPLICABLE。

- 任一 FAIL → 不合格（除非复核推翻并留痕）。
- 有 UNVERIFIABLE → 待补证据，不得合格。
- 有 CONFLICT_PENDING → 待审，写明冲突点。
- 方法 mismatch → 该标准不参与合格判定，单列。
- 主审规则未覆盖 → 未完成审核。

## 3 一致性检查

数值、日期、方法、仪器编号、样品编号/数量/状态、单位、签字/章。

## 4 假通过复核

PASS 抽查：LOCATED、quote 可检索、observed 来自原文、方法匹配、ND 未当 0、无冲突证据。可疑降级。

## 5 最终结论枚举

合格 / 不合格 / 待补证据 / 待审 / 未完成审核。

## 6 输出

audit_run + 汇总；findings 每条带 rule_id、standard_id、verdict、target、clause、整改建议、责任方。

## 7 页面契约

按项目 → 报告 → 标准/分类 → 规则判定展示；点击结果高亮 target span，回指 clause anchor。

## 8 禁止

- 不重抽证据、不重跑全部规则、不改报告。
- 不把方法 mismatch 混入合格结论。
- 不用模糊结论；不替代报告批准人。
