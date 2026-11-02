# 技能：ontology-resolution-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:31:19Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | ontology-resolution-skill |
| description | 把候选 Entity 映射到项目 Ontology Registry 的标准类型、属性与约束。触发：按本体归类、映射到标准类型、检查属性是否符合约束。不适用：创建或扩写本体（需人工评审）。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/ontology-resolution-skill |
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
name: ontology-resolution-skill
description: "把候选 Entity 映射到项目 Ontology Registry 的标准类型、属性与约束。触发：按本体归类、映射到标准类型、检查属性是否符合约束。不适用：创建或扩写本体（需人工评审）。"
---

# Ontology Resolution Skill

## Skill ID
SK-04

## Purpose
将候选 Entity 映射到项目 Ontology Registry 中的标准类型、属性和约束。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：按本体归类｜映射到标准类型｜检查属性是否符合约束
- 不要在此调用：创建或扩写本体（需人工评审）
## 边界与不适用

- 不做：不擅自新增类型或修改约束
- 不做：找不到合适类型时输出待评审候选，不硬塞
- 缺输入：先有 Ontology Registry 与待映射实体
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 885 | 9281c459456f7665 |
| prompts/system.md | 161 | d7512d3ee97365d0 |
| schema/output.json | 382 | 47932e1f9d1b57e2 |
| tests/expected.json | 45 | ecf16fc0c3a66bb2 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/ontology-resolution-skill/`（未改写；已用 SHA-256 复算校验）。
