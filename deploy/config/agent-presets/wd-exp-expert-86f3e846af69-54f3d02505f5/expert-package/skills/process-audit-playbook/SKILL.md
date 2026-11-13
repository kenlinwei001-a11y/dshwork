---
name: process-audit-playbook
description: 用已匹配标准的 C2–C5/C7 规则与证据包审核样品流转、前处理、仪器、试剂、操作步骤与质控记录，输出判定、记录位置与条款回指。
---

# 过程文档审核 playbook

## 何时使用

- 报告包里有原始记录、样品流转、仪器运行、环境、校准证书；
- 需要按 C2 样品、C3 仪器、C4 试剂、C5 流程、C7 质控逐条判；
- 需要确认缺件、记录冲突、校准有效期。

## 执行顺序

1. 取 report_standard 中 method_match=match 的标准。
2. 取 C2–C5/C7 规则，按 category/clause 排序。
3. 盘点 records/documents，建规则→证据索引。
4. 逐条取观测值；缺失按 on_missing。
5. 判定 applicability → predicate → verdict。
6. 定位记录 span；失败标 UNLOCATED。
7. 写 audit_result；C8 完整性 comment 交 5 号。
8. 交 5 号裁定。

## 硬口径

- 缺证不默认通过；不假设「实验室已做」。
- 记录冲突并列，不选正确值。
- 方法 mismatch 不套规则。
- 不审报告结果、不重算报告值。

## 资料

- references/audit-contract.md：判定、路由、落库、升级。
- references/process-evidence-map.md：记录字段与定位。
- references/sample-202203001.md：样例文档与缺件待核。
- templates/audit-result.json：结果记录模板。
