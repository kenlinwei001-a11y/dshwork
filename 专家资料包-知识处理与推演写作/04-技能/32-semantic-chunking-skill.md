# 技能：semantic-chunking-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-03T02:37:14Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | semantic-chunking-skill |
| description | 按章节、主题和语义边界把 Document IR 切成稳定 Chunk。触发：把文档切成块、按章节分段、为抽取准备输入。不适用：分句与编号（sentence-segmentation）、改写润色。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/semantic-chunking-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.8 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、标准要素抽取专家（expert-131e1b3979fe）、实验室证据抽取专家（expert-46a04687c733）、推演式报告写作专家（expert-97703554b311）、沈证源（member-ac7b53fc37a5）、沈证源（member-b6167c0afc18）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: semantic-chunking-skill
description: "按章节、主题和语义边界把 Document IR 切成稳定 Chunk。触发：把文档切成块、按章节分段、为抽取准备输入。不适用：分句与编号（sentence-segmentation）、改写润色。"
---

# Semantic Chunking Skill

## Skill ID
SK-01

## Purpose
按照章节、主题和语义边界将 Document IR 切分为稳定的语义 Chunk，供后续抽取和检索使用。

## 何时使用

调用条件：已有 document-parsing-skill 产出的 Document IR（含页码、段落与原文定位）。
- 典型请求：把文档切成块｜按章节分段｜为抽取准备输入
- 不要在此调用：分句与编号（sentence-segmentation）、改写润色
## 边界与不适用

- 不做：只切块，不改写原文
- 不做：不跨章节强行合并；表格与代码整块保留
- 缺输入：先有 document-parsing-skill 产出的 Document IR
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 925 | 3caf3ccb6301cea0 |
| prompts/system.md | 157 | 7acd6bac8421e101 |
| schema/output.json | 380 | dbb32986ee9968fb |
| tests/expected.json | 45 | c768c657d9ae90ac |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/semantic-chunking-skill/`（未改写；已用 SHA-256 复算校验）。
