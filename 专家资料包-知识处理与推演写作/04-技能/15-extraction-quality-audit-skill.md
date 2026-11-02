# 技能：extraction-quality-audit-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:31:19Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | extraction-quality-audit-skill |
| description | 对抽取结果执行结构完整性、证据覆盖、关系合法性、跨项目污染与孤立节点审计。触发：检查抽取质量、有没有漏证据或悬空关系、有没有跨项目串数据。不适用：修复数据（本 skill 只出问题清单）。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/extraction-quality-audit-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 7 |
| 体积 | 12.5 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、标准要素抽取专家（expert-131e1b3979fe）、检测报告审核专家（expert-42bd48d396a6）、实验室证据抽取专家（expert-46a04687c733）、水常规元素检测报告质控专家团（expert-755a41921517）、过程文档审核专家（expert-86f3e846af69）、推演式报告写作专家（expert-97703554b311）、审核裁定专家（expert-bad4a0f42fda）、顾合规（member-15195635ad3f）、甄定论（member-23260ee44d09）、严留痕（member-353690f3265e）、严留痕（member-4840a182856c）、顾合规（member-6794455cd9c5）、沈证源（member-ac7b53fc37a5）、甄定论（member-b05d63f23313）、沈证源（member-b6167c0afc18）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: extraction-quality-audit-skill
description: "对抽取结果执行结构完整性、证据覆盖、关系合法性、跨项目污染与孤立节点审计。触发：检查抽取质量、有没有漏证据或悬空关系、有没有跨项目串数据。不适用：修复数据（本 skill 只出问题清单）。"
---

# Extraction Quality Audit Skill

## Skill ID
SK-17

## Purpose
对抽取结果执行结构完整性、证据覆盖、关系合法性、跨项目污染和孤立节点等质量审计。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：检查抽取质量｜有没有漏证据或悬空关系｜有没有跨项目串数据
- 不要在此调用：修复数据（本 skill 只出问题清单）
## 边界与不适用

- 不做：只审计不改数据
- 不做：问题按严重度分级并附样例 ID
- 缺输入：先有抽取结果与图谱
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 932 | c9c954f32f1a09f0 |
| prompts/system.md | 171 | cc43f45d5671d64a |
| references/门禁与案例.md | 10938 | ab77fe0cb4476819 |
| schema/output.json | 387 | ced80bb9082b37bc |
| tests/expected.json | 45 | 9d3c1739ec41bb79 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

正文或资源中出现：`kp_toolkit`。对应连接见 `06-MCP/`。

## 7. 副本

逐字节副本：`99-原件/skills/extraction-quality-audit-skill/`（未改写；已用 SHA-256 复算校验）。
