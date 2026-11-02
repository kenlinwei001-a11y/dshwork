# 技能：conflict-detection-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:44:08Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | conflict-detection-skill |
| description | 检测数字、时间、实体、Claim 与版本之间的冲突，并输出待审状态。触发：前后数字对不上、不同版本之间有矛盾、列出所有待审冲突。不适用：拍板选一个值（交人工或评审）。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/conflict-detection-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.8 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家、推演写作专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、推演写作专家（expert-a0a771c8b0da）、标准要素抽取专家（expert-131e1b3979fe）、检测报告审核专家（expert-42bd48d396a6）、实验室证据抽取专家（expert-46a04687c733）、水常规元素检测报告质控专家团（expert-755a41921517）、过程文档审核专家（expert-86f3e846af69）、推演式报告写作专家（expert-97703554b311）、审核裁定专家（expert-bad4a0f42fda）、顾合规（member-15195635ad3f）、甄定论（member-23260ee44d09）、严留痕（member-353690f3265e）、严留痕（member-4840a182856c）、顾合规（member-6794455cd9c5）、沈证源（member-ac7b53fc37a5）、甄定论（member-b05d63f23313）、沈证源（member-b6167c0afc18）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: conflict-detection-skill
description: "检测数字、时间、实体、Claim 与版本之间的冲突，并输出待审状态。触发：前后数字对不上、不同版本之间有矛盾、列出所有待审冲突。不适用：拍板选一个值（交人工或评审）。"
---

# Conflict Detection Skill

## Skill ID
SK-13

## Purpose
检测数字、时间、实体、Claim 和版本之间的冲突，并输出待审状态而非自动裁决。

## 何时使用

调用条件：已有可比数据（同一指标的多来源或多版本）。
- 典型请求：前后数字对不上｜不同版本之间有矛盾｜列出所有待审冲突
- 不要在此调用：拍板选一个值（交人工或评审）
## 边界与不适用

- 不做：绝不自动裁决或静默选值
- 不做：每条冲突给出双方出处与差异点
- 缺输入：先有可比数据（同指标多来源或多版本）
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 910 | e27dd96df946a87f |
| prompts/system.md | 159 | 963fe75f7b42a8ea |
| schema/output.json | 381 | dcf1d4f558af6060 |
| tests/expected.json | 45 | c84c8a4f6dddf3f7 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/conflict-detection-skill/`（未改写；已用 SHA-256 复算校验）。
