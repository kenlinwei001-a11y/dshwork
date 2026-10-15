# Skill：claim-validation-skill

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。文中结论均可按 01-关系总览/02-数据来源与核对说明.md 复核。

## 1. 元数据（SKILL.md frontmatter）

| 字段 | 值 |
|---|---|
| name | claim-validation-skill |
| description | "验证 Claim 的证据支持、时间一致性、事实依赖、推理完整性和语义范围。" |

## 2. 职责与触发

- 中文职责：论断校验
- 能力简述：校验 Claim 的证据支持、时间一致性、事实依赖、推理完整性与语义范围。
- 配备专家：知识处理专家
- 资源规模：6 个文件，合计 1.8 KB

## 3. SKILL.md 正文（全文）

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

## 4. 资源清单

| 文件 | 字节 | 说明 |
|---|---|---|
| SKILL.md | 980 | 技能主文档 |
| prompts/system.md | 155 | LLM 提示词 |
| schema/output.json | 379 | 输出契约 |
| tests/expected.json | 45 | 测试样例 |
| tests/golden.json | 85 | 测试样例 |
| validators/validator.py | 223 | 确定性校验器 |

## 5. MCP 关联（文本取证）

未发现任何 mcp__<server>__ 调用或 kp_ 工具引用：该 Skill 只依赖自身脚本/文档与工作区文件。

## 6. 运行依赖与边界

- 依赖：输出需符合 schema 并可通过 validator 校验；无额外外部服务。
- 本包副本：`99-原件/skills/claim-validation-skill/`（逐字节复制，未改写）。
- 说明：本包只如实转述技能内容与资源，不对技能产出质量作任何承诺。
