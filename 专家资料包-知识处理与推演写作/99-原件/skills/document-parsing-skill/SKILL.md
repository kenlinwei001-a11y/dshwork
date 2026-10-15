---
name: document-parsing-skill
description: "将 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，并保留页码、段落、表格和原文定位信息。"
---

# Document Parsing Skill

## Skill ID
SK-00

## Purpose
将 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，并保留页码、段落、表格和原文定位信息。

## Input
- `project_id`
- `document_id`
- `version_id`
- 上游 Skill 输出
- 原文或结构化中间结果

## Output
输出必须包含稳定 ID、来源定位（provenance）以及与上下游对象的关联字段。

## Execution Rules
1. 不编造输入中不存在的事实。
2. 所有抽取结果必须尽可能绑定 `project_id`、`document_id`、`version_id`。
3. 涉及事实、Claim、Evidence、Reasoning 时必须保留来源链。
4. 发现冲突时标记冲突，不擅自选择一个版本作为真值。
5. 项目专属数据不得在没有明确复用策略时跨项目复制。

## Validation
执行 `tests/golden.json` 与 `tests/expected.json` 中定义的基础验收。
