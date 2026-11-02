---
name: standard-element-extraction
description: 把技术标准与流程文件解构为可执行要素、依赖图谱与分类审核规则卡，并给出报告文字定位线索。用于标准条款抽取、引用闭包、实验室文件对齐、审核规则化与方法族对照。
---

# 标准要素抽取（随包技能）

本技能是「标准要素抽取专家」随包携带的操作手册与模板库。专家正文负责判断与编排，本技能负责把步骤、字段和检查清单固定下来，保证不同标准、不同人执行时产出同一结构。

## 何时使用

- 要把一份标准（HJ/GB/JJF/ISO 或企业技术规范）变成可执行流程、设备清单、试剂配制、公式与质控阈值。
- 要生成能逐条判定检测报告或过程记录的审核规则卡。
- 要梳理标准的规范性引用、提醒补充未上传文件。
- 要把实验室 SOP、质控规程、仪器说明书与标准对齐。
- 要做同族方法标准对照、标准换版后的增量重抽。

## 执行顺序

1. 建档：standard_id、版本、发布/实施、现行性、来源指纹（SHA-256 前 12 位 + 页数）。
2. 条款登记：逐条登记条款号、页码、原文、模态（应/宜/可/不应）、normative/informative。
3. 引用闭包：第 2 章 + 正文引用 + 图注引用；递归展开；未上传列待上传清单（写明影响哪些规则）。
4. 要素抽取：META/SCOPE/PRIN/SAMP/PROC/APPA/MATL/INTR/CALC/QC/PERF/RISK 十二族，每条带条款锚与来源层。
5. 公式卡：符号表、量纲、适用域、修约、自检算例。
6. 图转拓扑：流程图节点、边、试剂通道；图注参数入节点。
7. 实验室对齐：IMPLEMENTS / STRICTER / LOOSER / CONFLICT / MISSING / EXTRA / PENDING_DOC。
8. 规则化：C1–C8 分类；谓词或定性判据；证据；缺失处置；check_targets 定位线索。
9. 审计：覆盖率、单位、区间、锚、防虚构、模态、定位可命中。
10. 交接：SES 包 + 规则卡 + 缺口 + 定位契约。
11. 双库落库：全局 standards.db 作为审核主库；同时按标准名称导出单标准库 by-standard/<标准名称>（<标准号>）.db，并更新 catalog.json，便于检索、分发与归档。

## 硬性口径

- 规则不分级，只分类（C1–C8）。
- 缺证不默认通过；on_missing 必须写死。
- 标准原文、推导、行业惯例三层分离（verbatim / derived / convention）。
- 未上传的引用文件不得凭记忆补全；未上传的实验室文件不得假设等效。
- 所有数值必须能在原文定位；所有规则必须能回指条款。
- 报告定位 quote 必须命中原文，命中不了标 UNLOCATED。

## 资料

- references/standard-element-schema.md：字段级 schema、ID 方案、validator 必检项。
- references/audit-rule-card-spec.md：规则卡字段、C1–C8、谓词语法、定位契约、反模式。
- references/reference-closure-and-lab-docs.md：引用闭包、待上传话术、实验室文件对齐、方法族。
- references/hj671-2013-worked-example.md：HJ 671—2013 端到端示范（含 39 张规则卡）。
- references/hj671-2013-graph.md：全量关系图谱说明与 4 个 Mermaid 视图。
- templates/hj671-2013-graph.json：全量图谱数据（240 节点 / 260 边 / 5 个页面视图）。
- references/standard-store.md：标准要素落库与多标准/多报告模型。
- scripts/init_db.py、scripts/load_standard.py、scripts/query_report_rules.py：建库、按 standard_id 导入、按报告展开多标准规则。
- scripts/export_per_standard_dbs.py：按标准名称导出单标准库并生成 catalog.json。
- scripts/search_standards.py：按标准号/名称/方法/规则关键词检索标准与单标准库路径。
- references/handoff-contract.md：审核专家与结果页面契约（结果记录、span、版本变更）。
- templates/standard-element-package.json：SES 包模板。
- templates/audit-rule-cards.csv：规则卡表格模板。

## 交付前检查

- 每条 normative 条款有着落（要素或说明为何不抽）。
- 引用清单与待上传提醒完整。
- 规则卡可执行、可定位、缺证口径明确。
- 缺口清单写明影响与最小补充请求。
- 方法族只填已上传标准，未上传不填数。
