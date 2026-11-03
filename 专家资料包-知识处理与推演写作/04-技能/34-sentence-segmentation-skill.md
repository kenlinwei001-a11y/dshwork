# 技能：sentence-segmentation-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-03T02:37:14Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | sentence-segmentation-skill |
| description | 把 Chunk 切成 Sentence 并生成稳定的 Sentence ID。触发：给每句话编号、分句以便引用定位、准备 Claim 追踪的句子粒度。不适用：语义分块（semantic-chunking）、摘要改写。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/sentence-segmentation-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.7 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、标准要素抽取专家（expert-131e1b3979fe）、实验室证据抽取专家（expert-46a04687c733）、推演式报告写作专家（expert-97703554b311）、沈证源（member-ac7b53fc37a5）、沈证源（member-b6167c0afc18）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: sentence-segmentation-skill
description: "把 Chunk 切成 Sentence 并生成稳定的 Sentence ID。触发：给每句话编号、分句以便引用定位、准备 Claim 追踪的句子粒度。不适用：语义分块（semantic-chunking）、摘要改写。"
---

# Sentence Segmentation Skill

## Skill ID
SK-02

## Purpose
将 Chunk 切分为 Sentence，并生成稳定的 Sentence ID，支撑 Claim 追踪和 Semantic Diff。

## 何时使用

调用条件：已有 Chunk（含 chunk_id、所属文档与章节）。
- 典型请求：给每句话编号｜分句以便引用定位｜准备 Claim 追踪的句子粒度
- 不要在此调用：语义分块（semantic-chunking）、摘要改写
## 边界与不适用

- 不做：不改写句子、不做摘要
- 不做：ID 在同一修订内保持稳定，不因重跑重排
- 缺输入：先有 Chunk
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 865 | ab12f33f64cfbc84 |
| prompts/system.md | 165 | e722e80b4310eb74 |
| schema/output.json | 384 | 9aa89972c75cd9ef |
| tests/expected.json | 45 | 7888fce2fc51a4bc |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/sentence-segmentation-skill/`（未改写；已用 SHA-256 复算校验）。
