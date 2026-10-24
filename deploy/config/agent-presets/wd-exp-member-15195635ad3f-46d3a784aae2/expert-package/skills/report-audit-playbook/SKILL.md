---
name: report-audit-playbook
description: 用已匹配标准的 C1/C6 规则与证据包审核检测报告正文和结果页，输出逐条判定、报告文字 span 与条款回指；不抽数、不判过程记录。
---

# 报告审核 playbook

## 何时使用

- 一份报告已关联多个标准，且证据包已生成；
- 需要按 C1 方法适用性、C6 数据与计算逐条判定；
- 需要把判定贴回报告原文并回指条款；
- 需要识别方法 mismatch，避免错套规则。

## 执行顺序

1. 装载 report_standard，只取 method_match=match 的标准。
2. 取 rule 表中 C1/C6，以及 C8 中 check_target 为报告的规则。
3. 从证据包取 report、methods、instruments、fields。
4. 逐条：观测值 → applicability → predicate → verdict。
5. 公式复算并记录报告值/复算值/偏差。
6. target 用 evidence span；失败标 UNLOCATED。
7. 写 audit_result，CONFLICT_PENDING 单列。
8. 交 5 号裁定。

## 硬口径

- 方法 mismatch 不套规则，全部 CONFLICT_PENDING。
- 缺证不默认通过；按 on_missing。
- 每条结果有 rule_id、verdict、target、clause_anchor。
- 不审过程记录、不抽数、不改证据包。

## 资料

- references/audit-contract.md：判定、路由、落库、升级。
- references/report-evidence-map.md：报告字段与定位。
- references/sample-202203001.md：样例审核发现。
- templates/audit-result.json：结果记录模板。
