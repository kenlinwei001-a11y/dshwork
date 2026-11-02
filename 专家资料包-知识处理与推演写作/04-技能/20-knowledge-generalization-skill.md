# 技能：knowledge-generalization-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:31:19Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | knowledge-generalization-skill |
| description | 从历史项目提炼可复用 Ontology、推理模式、Claim 模式、分析框架与规则，同时隔离项目专属事实。触发：沉淀方法论、把经验抽成可复用规则、做成模板给下个项目用。不适用：搬运项目数值与专有事实。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/knowledge-generalization-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.9 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家、推演写作专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、推演写作专家（expert-a0a771c8b0da）、标准要素抽取专家（expert-131e1b3979fe）、推演式报告写作专家（expert-97703554b311）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: knowledge-generalization-skill
description: "从历史项目提炼可复用 Ontology、推理模式、Claim 模式、分析框架与规则，同时隔离项目专属事实。触发：沉淀方法论、把经验抽成可复用规则、做成模板给下个项目用。不适用：搬运项目数值与专有事实。"
---

# Knowledge Generalization Skill

## Skill ID
SK-14

## Purpose
从历史项目中提取可复用 Ontology、Reasoning Pattern、Claim Pattern、分析框架和规则，同时隔离项目专属事实。

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：沉淀方法论｜把经验抽成可复用规则｜做成模板给下个项目用
- 不要在此调用：搬运项目数值与专有事实
## 边界与不适用

- 不做：绝不跨项目复制项目专属事实与数值
- 不做：区分形与值：只复用结构与规则
- 不做：没有明确复用策略时不落地
- 缺输入：先有已完成的项目资产与复用边界说明
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 1038 | d3a3e6b8d38d6176 |
| prompts/system.md | 171 | 95a778660ab66036 |
| schema/output.json | 387 | fdd35a6d27f7ba63 |
| tests/expected.json | 45 | 2c1ce3b7ed8b667a |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/knowledge-generalization-skill/`（未改写；已用 SHA-256 复算校验）。
