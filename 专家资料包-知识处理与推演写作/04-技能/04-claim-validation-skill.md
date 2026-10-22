# 技能：claim-validation-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | claim-validation-skill |
| description | 验证 Claim 的证据支持、时间一致性、事实依赖、推理完整性和语义范围。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/claim-validation-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.8 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、知识处理专家 副本（expert-131e1b3979fe）、检测报告审核专家（expert-42bd48d396a6）、过程文档审核专家（expert-86f3e846af69）、推演式报告写作专家（expert-97703554b311）、审核裁定专家（expert-bad4a0f42fda）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: claim-validation-skill
description: "验证 Claim 的证据支持、时间一致性、事实依赖、推理完整性和语义范围。"
---

# Claim Validation Skill

## Skill ID
SK-12

## Purpose
验证 Claim 的证据支持、时间一致性、事实依赖、推理完整性和语义范围。

## Input
- `project_id`
- `document_id`
- `version_id`
- 上游 Skill 输出
- 原文或结构化中间结果

## Output
必须输出稳定 ID、结构化结果以及 provenance/来源关联字段。

## Execution Rules
1. 只使用输入中存在或可由明确规则推导的信息，不编造事实。
2. 所有结果尽可能绑定 `project_id`、`document_id`、`version_id`。
3. Fact、Claim、Evidence、Reasoning 必须保留来源链。
4. 发现冲突时输出冲突状态，不擅自裁决。
5. 不得在没有复用策略的情况下跨项目复制项目专属事实。

## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 980 | bfd05e00b31b0f1c |
| prompts/system.md | 155 | 413d8db0196bb8fe |
| schema/output.json | 379 | 1a57719dfc9bce77 |
| tests/expected.json | 45 | 4c48005e38236594 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/claim-validation-skill/`（未改写；已用 SHA-256 复算校验）。
