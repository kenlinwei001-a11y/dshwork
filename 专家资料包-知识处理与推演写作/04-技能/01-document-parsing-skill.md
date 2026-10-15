# Skill：document-parsing-skill

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。文中结论均可按 01-关系总览/02-数据来源与核对说明.md 复核。

## 1. 元数据（SKILL.md frontmatter）

| 字段 | 值 |
|---|---|
| name | document-parsing-skill |
| description | "将 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，并保留页码、段落、表格和原文定位信息。" |

## 2. 职责与触发

- 中文职责：文档解析
- 能力简述：把 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，保留页码、段落、表格与原文定位。
- 配备专家：知识处理专家
- 资源规模：6 个文件，合计 1.9 KB

## 3. SKILL.md 正文（全文）

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

## 4. 资源清单

| 文件 | 字节 | 说明 |
|---|---|---|
| SKILL.md | 1048 | 技能主文档 |
| prompts/system.md | 143 | LLM 提示词 |
| schema/output.json | 379 | 输出契约 |
| tests/expected.json | 45 | 测试样例 |
| tests/golden.json | 85 | 测试样例 |
| validators/validator.py | 280 | 确定性校验器 |

## 5. MCP 关联（文本取证）

未发现任何 mcp__<server>__ 调用或 kp_ 工具引用：该 Skill 只依赖自身脚本/文档与工作区文件。

## 6. 运行依赖与边界

- 依赖：输出需符合 schema 并可通过 validator 校验；无额外外部服务。
- 本包副本：`99-原件/skills/document-parsing-skill/`（逐字节复制，未改写）。
- 说明：本包只如实转述技能内容与资源，不对技能产出质量作任何承诺。
