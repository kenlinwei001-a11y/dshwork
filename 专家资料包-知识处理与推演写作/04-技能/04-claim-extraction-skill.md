# 技能：claim-extraction-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:31:19Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | claim-extraction-skill |
| description | 识别判断、结论、风险、预测、因果与建议等 Claim，并建立依赖关系。触发：挑出结论和风险、区分事实与观点、整理因果链与中间结论。不适用：判定真伪（claim-validation）、定位原文出处（evidence-extraction）。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/claim-extraction-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.8 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、推演式报告写作专家（expert-97703554b311）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: claim-extraction-skill
description: "识别判断、结论、风险、预测、因果与建议等 Claim，并建立依赖关系。触发：挑出结论和风险、区分事实与观点、整理因果链与中间结论。不适用：判定真伪（claim-validation）、定位原文出处（evidence-extraction）。"
---

# Claim Extraction Skill

## Skill ID
SK-07

## Purpose
识别判断、结论、风险、预测、因果判断和建议等 Claim，并建立依赖关系。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：挑出结论和风险｜区分事实与观点｜整理因果链与中间结论
- 不要在此调用：判定真伪（claim-validation）、定位原文出处（evidence-extraction）
## 边界与不适用

- 不做：不判真伪、不改写原文措辞
- 不做：引述他人观点需标注归属，不算作者 Claim
- 缺输入：先有 Sentence 或 Chunk
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 961 | a00878f86d2cbba6 |
| prompts/system.md | 155 | ffcdfc228a26ad5c |
| schema/output.json | 379 | 9b8af7c0020d2b15 |
| tests/expected.json | 45 | a7bc3cc95962b0d7 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/claim-extraction-skill/`（未改写；已用 SHA-256 复算校验）。
