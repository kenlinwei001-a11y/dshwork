# 技能：claim-evidence-binding-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T11:27:23Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | claim-evidence-binding-skill |
| description | 判定 Evidence 与 Claim 的关系：SUPPORT、PARTIAL_SUPPORT、CONTRADICT、CONTEXT 或 INSUFFICIENT。触发：这条结论有没有证据支持、证据和说法是否矛盾、标出证据支持强度。不适用：最终裁决冲突（conflict-detection 只输出待审）、改写 Claim。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/claim-evidence-binding-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.9 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家、推演写作专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、推演写作专家（expert-a0a771c8b0da）、检测报告审核专家（expert-42bd48d396a6）、过程文档审核专家（expert-86f3e846af69）、推演式报告写作专家（expert-97703554b311）、审核裁定专家（expert-bad4a0f42fda）、顾合规（member-15195635ad3f）、甄定论（member-23260ee44d09）、严留痕（member-353690f3265e）、严留痕（member-4840a182856c）、顾合规（member-6794455cd9c5）、甄定论（member-b05d63f23313）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: claim-evidence-binding-skill
description: "判定 Evidence 与 Claim 的关系：SUPPORT、PARTIAL_SUPPORT、CONTRADICT、CONTEXT 或 INSUFFICIENT。触发：这条结论有没有证据支持、证据和说法是否矛盾、标出证据支持强度。不适用：最终裁决冲突（conflict-detection 只输出待审）、改写 Claim。"
---

# Claim Evidence Binding Skill

## Skill ID
SK-09

## Purpose
判断 Evidence 与 Claim 的关系：SUPPORT、PARTIAL_SUPPORT、CONTRADICT、CONTEXT 或 INSUFFICIENT。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：这条结论有没有证据支持｜证据和说法是否矛盾｜标出证据支持强度
- 不要在此调用：最终裁决冲突（conflict-detection 只输出待审）、改写 Claim
## 边界与不适用

- 不做：只判关系类别，不做最终裁决
- 不做：证据不足一律 INSUFFICIENT，不拔高为 SUPPORT
- 缺输入：先有 Claim 与候选证据
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 1009 | e0186a60a329399e |
| prompts/system.md | 167 | 3c7ef331f57425ca |
| schema/output.json | 385 | 49a21f7072d1ab92 |
| tests/expected.json | 45 | a1dacbe5e304b77c |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/claim-evidence-binding-skill/`（未改写；已用 SHA-256 复算校验）。
