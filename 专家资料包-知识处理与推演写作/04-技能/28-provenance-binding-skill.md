# 技能：provenance-binding-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:31:19Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | provenance-binding-skill |
| description | 建立对象间来源链，使 Decision 可反向追溯到 Claim、Reasoning、Fact、Evidence、Sentence、Chunk 与 Document。触发：给结论挂溯源链、检查引用是否悬空、决策能不能倒查到原文。不适用：判断内容真假、补造来源。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/provenance-binding-skill |
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
name: provenance-binding-skill
description: "建立对象间来源链，使 Decision 可反向追溯到 Claim、Reasoning、Fact、Evidence、Sentence、Chunk 与 Document。触发：给结论挂溯源链、检查引用是否悬空、决策能不能倒查到原文。不适用：判断内容真假、补造来源。"
---

# Provenance Binding Skill

## Skill ID
SK-16

## Purpose
建立对象之间的来源链，使 Decision 可以反向追溯到 Claim、Reasoning、Fact、Evidence、Sentence、Chunk 和 Document。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：给结论挂溯源链｜检查引用是否悬空｜决策能不能倒查到原文
- 不要在此调用：判断内容真假、补造来源
## 边界与不适用

- 不做：只建链不造链
- 不做：悬空引用显式标记，不静默删除
- 缺输入：先有上下游对象及其定位信息
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 936 | 1745ef2909324e2a |
| prompts/system.md | 159 | b1f310ee1ae36f3b |
| schema/output.json | 381 | 81916098068b2d5f |
| tests/expected.json | 45 | e00fd84a1c59c5b0 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/provenance-binding-skill/`（未改写；已用 SHA-256 复算校验）。
