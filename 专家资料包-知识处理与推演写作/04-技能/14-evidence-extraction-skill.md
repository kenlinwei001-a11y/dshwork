# 技能：evidence-extraction-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T11:27:23Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | evidence-extraction-skill |
| description | 定位支撑 Fact 或 Claim 的原始证据（文档、页码、章节、Chunk、Sentence、文本范围）。触发：找出处和页码、给结论配原文、定位到具体段落。不适用：评价证据强弱与关系类别（claim-evidence-binding）。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/evidence-extraction-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.8 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家、推演写作专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、推演写作专家（expert-a0a771c8b0da）、标准要素抽取专家（expert-131e1b3979fe）、实验室证据抽取专家（expert-46a04687c733）、推演式报告写作专家（expert-97703554b311）、沈证源（member-ac7b53fc37a5）、沈证源（member-b6167c0afc18）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: evidence-extraction-skill
description: "定位支撑 Fact 或 Claim 的原始证据（文档、页码、章节、Chunk、Sentence、文本范围）。触发：找出处和页码、给结论配原文、定位到具体段落。不适用：评价证据强弱与关系类别（claim-evidence-binding）。"
---

# Evidence Extraction Skill

## Skill ID
SK-08

## Purpose
定位支持 Fact 或 Claim 的原始证据，包括文档、页码、章节、Chunk、Sentence 和文本范围。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：找出处和页码｜给结论配原文｜定位到具体段落
- 不要在此调用：评价证据强弱与关系类别（claim-evidence-binding）
## 边界与不适用

- 不做：不生成不存在的引用
- 不做：找不到时输出缺失，不用相近段落冒充
- 缺输入：先有 Fact/Claim 与原文 IR
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 924 | d2eca340fba4fed7 |
| prompts/system.md | 161 | 2ebe5a6fb7225d9f |
| schema/output.json | 382 | 2af549c6c7a53189 |
| tests/expected.json | 45 | 33c34269b70b8dfe |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/evidence-extraction-skill/`（未改写；已用 SHA-256 复算校验）。
