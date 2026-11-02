---
name: adjudication-playbook
description: 合并报告审核与过程文档审核的判定，做跨文档一致性、方法 mismatch、缺证/冲突处理与假通过复核，输出最终审核结论、问题清单与整改建议。
---

# 审核裁定 playbook

## 何时使用

- 3 号报告审核、4 号过程文档审核已完成；
- 需要按标准合并 verdict，处理 FAIL/缺证/冲突；
- 需要做跨文档一致性、方法 mismatch、假通过复核；
- 需要输出最终审核汇总与整改建议。

## 执行顺序

1. 锁定 report_id、项目、标准清单、证据版本。
2. 合并 3/4 结果，按 FAIL > 待审 > 待补 > 合格。
3. 方法 mismatch 单列，不参与合格判定。
4. 一致性检查：数值/日期/方法/仪器/样品/单位/签字。
5. 假通过复核：PASS 的定位、quote、方法、ND、冲突。
6. 生成 findings、missing、conflicts、remediation。
7. 输出审核汇总与页面结果。
8. 退回需补证/需复核项。

## 硬口径

- 不用平均分/多数票覆盖 FAIL。
- 缺证不得判合格；方法 mismatch 不得混入合格结论。
- 不重抽证据、不重跑全部规则、不改报告。
- 结论必须能回指 rule_id、证据位置、条款。

## 资料

- references/adjudication-contract.md：合并、优先级、页面契约。
- references/consistency-checks.md：一致性清单与假通过信号。
- references/sample-202203001.md：样例裁定要点。
- templates/audit-summary.json：审核汇总模板。
