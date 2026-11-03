# 技能：document-parsing-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-03T02:37:14Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | document-parsing-skill |
| description | 把 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，保留页码、段落、表格与原文定位。触发：解析这份 PDF/Word、把扫描件转成可检索文本、批量导入文档建库。不适用：抽取实体或事实（走 entity-extraction / fact-extraction）。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/document-parsing-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 2.0 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、标准要素抽取专家（expert-131e1b3979fe）、实验室证据抽取专家（expert-46a04687c733）、推演式报告写作专家（expert-97703554b311）、沈证源（member-ac7b53fc37a5）、沈证源（member-b6167c0afc18）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: document-parsing-skill
description: "把 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，保留页码、段落、表格与原文定位。触发：解析这份 PDF/Word、把扫描件转成可检索文本、批量导入文档建库。不适用：抽取实体或事实（走 entity-extraction / fact-extraction）。"
---

# Document Parsing Skill

## Skill ID
SK-00

## Purpose
将 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，并保留页码、段落、表格和原文定位信息。

## 何时使用

调用条件：已拿到原始文件（PDF/DOCX/XLSX/PPTX/扫描件）；没有文件先索取，不凭描述生成“解析结果”。
- 典型请求：解析这份 PDF/Word｜把扫描件转成可检索文本｜批量导入文档建库
- 不要在此调用：抽取实体或事实（走 entity-extraction / fact-extraction）
## 边界与不适用

- 不做：只产出 IR，不做切片、抽取或改写
- 不做：扫描件识别不清时标注置信度与页码，不猜字
- 缺输入：没有原始文件时先索取文件；不能凭描述生成"解析结果"
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 1105 | 3ab4f2fbb641c97f |
| prompts/system.md | 143 | dff84826558acecc |
| schema/output.json | 379 | f31b8026845fde1f |
| tests/expected.json | 45 | 7c0fb9ae3fca7352 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 280 | 35471886643f7c05 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/document-parsing-skill/`（未改写；已用 SHA-256 复算校验）。
