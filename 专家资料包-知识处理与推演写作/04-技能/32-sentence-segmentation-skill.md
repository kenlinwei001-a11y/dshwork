# 技能：sentence-segmentation-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | sentence-segmentation-skill |
| description | 将 Chunk 切分为 Sentence，并生成稳定的 Sentence ID，支撑 Claim 追踪和 Semantic Diff。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/sentence-segmentation-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.9 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、知识处理专家 副本（expert-131e1b3979fe）、实验室证据抽取专家（expert-46a04687c733）、推演式报告写作专家（expert-97703554b311）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: sentence-segmentation-skill
description: "将 Chunk 切分为 Sentence，并生成稳定的 Sentence ID，支撑 Claim 追踪和 Semantic Diff。"
---

# Sentence Segmentation Skill

## Skill ID
SK-02

## Purpose
将 Chunk 切分为 Sentence，并生成稳定的 Sentence ID，支撑 Claim 追踪和 Semantic Diff。

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
| SKILL.md | 1002 | 083495f95555c921 |
| prompts/system.md | 165 | e722e80b4310eb74 |
| schema/output.json | 384 | 9aa89972c75cd9ef |
| tests/expected.json | 45 | 7888fce2fc51a4bc |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/sentence-segmentation-skill/`（未改写；已用 SHA-256 复算校验）。
