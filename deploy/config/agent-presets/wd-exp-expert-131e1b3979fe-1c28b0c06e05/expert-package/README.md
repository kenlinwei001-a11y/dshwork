# 标准要素抽取专家（knowledge-processing-expert）

把「技术与流程标准」解构成**可执行、可判定、可溯源**的结构化要素与审核规则，供下游审核专家逐条核对检测报告与过程记录。由原「知识处理专家 副本」改造而来，保留工具 + LLM 分层、稳定 ID 与条款锚分离、证据与溯源纪律。

## 定位

- **产出**：可审核结构 + 审核规则 + 判定口径 + 报告定位线索。
- **不产出**：报告合格/不合格结论（归审核专家）。
- **判据**：一条要求抽对了，审核专家拿它 + 报告能判 PASS / FAIL / 缺证，并回指条款原文。

## 覆盖范围

- 标准正文：方法标准、产品限量标准、管理规范（类型决定十二族权重）。
- **规范性引用文件**：第 2 章与正文引用递归覆盖；未上传即列入待上传清单并提醒。
- **实验室内部文件**：SOP、质控规程、仪器说明书、记录表单；标 IMPLEMENTS / STRICTER / LOOSER / CONFLICT / MISSING / EXTRA。
- **过程文档**：原始记录、前处理记录、仪器使用记录、试剂配制记录、质控记录、样品流转单。

## 产出九件套

条款登记册、引用登记册、要素包（SE-12）、公式卡、流程与流路图、依赖推演图、实验室对齐表、分类审核规则卡（C1–C8）、质量与交接包。

规则**不分级、只分类**；每张卡带谓词、证据要求、缺失处置（缺证不默认通过）、核对文档与报告定位线索。

## 使用

1. 提供标准文件；如标准引用了其他文件，按「待上传清单」补充。
2. 提供实验室 SOP / 质控规程 / 仪器说明书（可选，但影响规则口径）。
3. 说明下游报告类型与字段、是否有固定模板。
4. 得到 SES 包与规则卡；交给审核专家与审核结果页面。

## 文件

- agents/knowledge-processing-expert.md：专家正文
- skills/standard-element-extraction/references/standard-element-schema.md：字段级 schema 与 ID 方案
- skills/standard-element-extraction/references/audit-rule-card-spec.md：规则卡语法、C1–C8 分类、定位契约
- skills/standard-element-extraction/references/reference-closure-and-lab-docs.md：引用闭包与实验室文件对齐
- skills/standard-element-extraction/references/hj671-2013-worked-example.md：HJ 671—2013 端到端示范（39 张规则卡）
- skills/standard-element-extraction/references/hj671-2013-graph.md：全量关系图谱说明与 4 个 Mermaid 视图
- skills/standard-element-extraction/templates/hj671-2013-graph.json：全量图谱数据（240 节点 / 260 边 / 5 个视图）
- skills/standard-element-extraction/references/standard-store.md：落库与多标准/多报告模型
- skills/standard-element-extraction/scripts/：建库、按 standard_id 导入、按报告展开规则
- skills/standard-element-extraction/references/handoff-contract.md：审核专家与结果页面的接手契约
- skills/standard-element-extraction/templates/standard-element-package.json、skills/standard-element-extraction/templates/audit-rule-cards.csv：机器可读模板

## 状态

- 已完成：专家正文、schema、规则卡规范、引用/实验室文件方法、HJ 671 示范（39 张规则卡）、全量图谱（240 节点 / 260 边，62 条条款全覆盖）、交接契约、模板。
- 待补充：GB 11893、HJ/T 91、HJ/T 164 未上传；实验室 SOP/质控规程/仪器说明书未上传。示范中相关条目保留待上传状态，未填数值。
