# 技能：reasoning-extraction-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:44:08Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | reasoning-extraction-skill |
| description | 识别公式、规则、多步推导与中间结论，形成 Reasoning 节点及输入输出依赖。触发：把推导过程抽出来、整理公式与规则、还原推理链。不适用：抽取结论 Claim、生成新的推导。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/reasoning-extraction-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.7 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、标准要素抽取专家（expert-131e1b3979fe）、检测报告审核专家（expert-42bd48d396a6）、水常规元素检测报告质控专家团（expert-755a41921517）、过程文档审核专家（expert-86f3e846af69）、推演式报告写作专家（expert-97703554b311）、审核裁定专家（expert-bad4a0f42fda）、顾合规（member-15195635ad3f）、甄定论（member-23260ee44d09）、严留痕（member-353690f3265e）、严留痕（member-4840a182856c）、顾合规（member-6794455cd9c5）、甄定论（member-b05d63f23313）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: reasoning-extraction-skill
description: "识别公式、规则、多步推导与中间结论，形成 Reasoning 节点及输入输出依赖。触发：把推导过程抽出来、整理公式与规则、还原推理链。不适用：抽取结论 Claim、生成新的推导。"
---

# Reasoning Extraction Skill

## Skill ID
SK-10

## Purpose
识别公式、规则、多步推导和中间结论，形成 Reasoning 节点及输入输出依赖。

## 何时使用

调用条件：已有含公式、规则或多步推导的原文。
- 典型请求：把推导过程抽出来｜整理公式与规则｜还原推理链
- 不要在此调用：抽取结论 Claim、生成新的推导
## 边界与不适用

- 不做：不补写缺失步骤、不替作者合理化跳跃
- 不做：无法复原的环节标 GAP，不虚构
- 缺输入：先有包含公式或规则步骤的原文
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 880 | a1460df6a2440228 |
| prompts/system.md | 163 | 7fb0bbcfb56d4275 |
| schema/output.json | 383 | 98212a06cec8aded |
| tests/expected.json | 45 | d97e6810f903b7d1 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/reasoning-extraction-skill/`（未改写；已用 SHA-256 复算校验）。
