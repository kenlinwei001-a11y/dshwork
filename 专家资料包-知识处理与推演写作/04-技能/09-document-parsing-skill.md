# 技能：document-parsing-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | document-parsing-skill |
| description | 将 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，并保留页码、段落、表格和原文定位信息。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/document-parsing-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.9 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、知识处理专家 副本（expert-131e1b3979fe）、实验室证据抽取专家（expert-46a04687c733）、推演式报告写作专家（expert-97703554b311）

## 4. SKILL.md 正文（全文）

~~~markdown
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
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 1048 | 16a36e5450a1ac49 |
| prompts/system.md | 143 | dff84826558acecc |
| schema/output.json | 379 | f31b8026845fde1f |
| tests/expected.json | 45 | 7c0fb9ae3fca7352 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 280 | 35471886643f7c05 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/document-parsing-skill/`（未改写；已用 SHA-256 复算校验）。
