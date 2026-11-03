# 技能：entity-extraction-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-03T02:37:14Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | entity-extraction-skill |
| description | 抽取企业、基地、车间、产线、客户、材料、供应商等实体及其 mention。触发：把文中出现的公司和供应商列出来、有哪些产线与材料、抽取所有实体。不适用：同名消歧（entity-resolution）、本体类型归属（ontology-resolution）。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/entity-extraction-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 4.5 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、标准要素抽取专家（expert-131e1b3979fe）、实验室证据抽取专家（expert-46a04687c733）、推演式报告写作专家（expert-97703554b311）、沈证源（member-ac7b53fc37a5）、沈证源（member-b6167c0afc18）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: entity-extraction-skill
description: "抽取企业、基地、车间、产线、客户、材料、供应商等实体及其 mention。触发：把文中出现的公司和供应商列出来、有哪些产线与材料、抽取所有实体。不适用：同名消歧（entity-resolution）、本体类型归属（ontology-resolution）。"
---

# Entity Extraction Skill

## Skill ID
SK-03

## Purpose
从文本中抽取企业、基地、车间、产线、客户、材料、供应商等实体及其 mention。

## 何时使用

调用条件：已有 Sentence 或 Chunk 文本及其定位。
- 典型请求：把文中出现的公司和供应商列出来｜有哪些产线与材料｜抽取所有实体
- 不要在此调用：同名消歧（entity-resolution）、本体类型归属（ontology-resolution）
## 边界与不适用

- 不做：不推断文中未出现的实体
- 不做：不合并别名，保留 mention 原文与位置
- 缺输入：先有 Sentence 或 Chunk
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 981 | 6ff24920c11c100a |
| prompts/system.md | 2882 | 08d7a1f139e121ba |
| schema/output.json | 380 | 35d307b1ceba39be |
| tests/expected.json | 45 | ef9690da48c2d6a6 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/entity-extraction-skill/`（未改写；已用 SHA-256 复算校验）。
