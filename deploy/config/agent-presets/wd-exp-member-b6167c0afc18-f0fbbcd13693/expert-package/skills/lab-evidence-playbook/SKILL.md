---
name: lab-evidence-playbook
description: 把检测报告与过程文档（委托、合同评审、任务单、样品流转、风险评估、原始记录、环境、仪器运行、校准证书）抽成规则无关的证据包，带文档清单、字段值、span 定位、缺失项与一致性初筛。
---

# 实验室证据抽取 playbook

## 何时使用

- 收到一份检测报告包，需要给审核专家准备可定位的事实；
- 报告对应多个标准/方法，需要先确认声明方法与库内标准是否匹配；
- 需要逐格抽结果表、校准曲线、空白/平行/加标、试剂、仪器、环境；
- 需要列出缺件，而不是直接判不合格。

## 执行顺序

1. 建档：report_id、项目、实验室、文件目录。
2. 盘点：doc_type 分类、sha256、页数、是否扫描件。
3. 解析：文本层优先；扫描件 OCR 并标 confidence。
4. 报告层：编号、委托方、样品、日期、方法、仪器、结果表、检出限、结论。
5. 记录层：按 document-types.md 的字段抽原始记录/环境/仪器/校准/样品。
6. 对账：样品编号、数量、日期、方法、仪器编号、结果与原始记录一致性。
7. 缺件：对照方法应有记录，列 missing。
8. 质量：LOCATED 比例、quote 可检索、单位、表头、重复。
9. 入库：report_document / report_evidence。
10. 交接：证据包 + 缺失 + flags。

## 硬口径

- 规则无关：不读标准、不引用 rule_id、不下 PASS/FAIL。
- 每个字段带 doc_id/page/quote/confidence；表格带 block_id。
- ND、未检出、<检出限 原样保留。
- 方法声明逐字保留；与库内标准不一致记 method_match=mismatch。
- 缺失就是缺失；OCR 不可辨标 UNLOCATED，不猜字。

## 资料

- references/evidence-pack-schema.md：证据包字段与校验。
- references/document-types.md：10 类文档与抽取字段。
- references/sample-202203001.md：16 份报告包样例与方法 mismatch。
- references/handoff-to-audit.md：交给 3/4/5 号审核专家的契约。
- templates/evidence-pack.json：证据包模板。
