# 技能：semantic-graph-compilation-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-03T02:37:14Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | semantic-graph-compilation-skill |
| description | 把 Entity、Fact、Claim、Evidence、Reasoning、Scenario、Decision 编译成统一 Semantic Graph。触发：合成语义图谱、把抽取结果连成图、生成 semantic graph JSON。不适用：新增事实或判断、图数据库运维。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/semantic-graph-compilation-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.8 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家、推演写作专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、推演写作专家（expert-a0a771c8b0da）、标准要素抽取专家（expert-131e1b3979fe）、推演式报告写作专家（expert-97703554b311）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: semantic-graph-compilation-skill
description: "把 Entity、Fact、Claim、Evidence、Reasoning、Scenario、Decision 编译成统一 Semantic Graph。触发：合成语义图谱、把抽取结果连成图、生成 semantic graph JSON。不适用：新增事实或判断、图数据库运维。"
---

# Semantic Graph Compilation Skill

## Skill ID
SK-15

## Purpose
将 Entity、Fact、Claim、Evidence、Reasoning、Scenario、Decision 等编译成统一 Semantic Graph。

## 何时使用

调用条件：已有各类抽取产物（Entity/Fact/Claim/Evidence/Reasoning/Scenario/Decision）。
- 典型请求：合成语义图谱｜把抽取结果连成图｜生成 semantic graph JSON
- 不要在此调用：新增事实或判断、图数据库运维
## 边界与不适用

- 不做：只编译不新增内容
- 不做：引用关系词表而不复制；非法引用报错，不静默丢弃
- 缺输入：先有各类抽取产物
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 943 | c25a8ebb67f91aaf |
| prompts/system.md | 175 | 0aacb19b78c35a48 |
| schema/output.json | 389 | 2811cb6282535b1d |
| tests/expected.json | 45 | 7309ac8cfaa021db |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/semantic-graph-compilation-skill/`（未改写；已用 SHA-256 复算校验）。
