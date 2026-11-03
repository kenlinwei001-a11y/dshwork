# 技能：claim-validation-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-03T02:37:14Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | claim-validation-skill |
| description | 校验 Claim 的证据支持、时间一致性、事实依赖、推理完整性与语义范围。触发：这条结论站不站得住、检查时间口径与依赖是否自洽、找出语义过宽或越界。不适用：修改 Claim 文本、替冲突下结论。 |

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
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、检测报告审核专家（expert-42bd48d396a6）、水常规元素检测报告质控专家团（expert-755a41921517）、过程文档审核专家（expert-86f3e846af69）、推演式报告写作专家（expert-97703554b311）、审核裁定专家（expert-bad4a0f42fda）、顾合规（member-15195635ad3f）、甄定论（member-23260ee44d09）、严留痕（member-353690f3265e）、严留痕（member-4840a182856c）、顾合规（member-6794455cd9c5）、甄定论（member-b05d63f23313）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: claim-validation-skill
description: "校验 Claim 的证据支持、时间一致性、事实依赖、推理完整性与语义范围。触发：这条结论站不站得住、检查时间口径与依赖是否自洽、找出语义过宽或越界。不适用：修改 Claim 文本、替冲突下结论。"
---

# Claim Validation Skill

## Skill ID
SK-12

## Purpose
验证 Claim 的证据支持、时间一致性、事实依赖、推理完整性和语义范围。

## 何时使用

调用条件：已有 Claim、支撑它的证据与相关事实（含时间口径）。
- 典型请求：这条结论站不站得住｜检查时间口径与依赖是否自洽｜找出语义过宽或越界
- 不要在此调用：修改 Claim 文本、替冲突下结论
## 边界与不适用

- 不做：只给问题与理由，不改写 Claim
- 不做：跨时点比较必须标注时间口径
- 缺输入：先有 Claim、证据与相关事实
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 934 | 210189c2795250e7 |
| prompts/system.md | 155 | 413d8db0196bb8fe |
| schema/output.json | 379 | 1a57719dfc9bce77 |
| tests/expected.json | 45 | 4c48005e38236594 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/claim-validation-skill/`（未改写；已用 SHA-256 复算校验）。
