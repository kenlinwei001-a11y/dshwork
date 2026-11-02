# 技能：relation-extraction-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:44:08Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | relation-extraction-skill |
| description | 抽取实体之间的业务语义关系，并绑定关系证据与来源 Sentence。触发：谁供应谁、产线和产品是什么关系、建立关系图谱。不适用：抽取属性事实（fact-extraction）、判定关系真假。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/relation-extraction-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 1.7 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、标准要素抽取专家（expert-131e1b3979fe）、推演式报告写作专家（expert-97703554b311）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: relation-extraction-skill
description: "抽取实体之间的业务语义关系，并绑定关系证据与来源 Sentence。触发：谁供应谁、产线和产品是什么关系、建立关系图谱。不适用：抽取属性事实（fact-extraction）、判定关系真假。"
---

# Relation Extraction Skill

## Skill ID
SK-05

## Purpose
抽取实体之间的业务语义关系，并绑定关系证据和来源 Sentence。

## 何时使用

调用条件：已有实体与承载关系的证据句。
- 典型请求：谁供应谁｜产线和产品是什么关系｜建立关系图谱
- 不要在此调用：抽取属性事实（fact-extraction）、判定关系真假
## 边界与不适用

- 不做：不发明关系类型，沿用本文档定义的七族开放词表
- 不做：每条关系必须有证据句，无证据不落库
- 缺输入：先有实体与证据句
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 885 | 1832f3c4bc6b7fbe |
| prompts/system.md | 161 | 490c15099aea4f05 |
| schema/output.json | 382 | 6509f816896870f8 |
| tests/expected.json | 45 | 668a592b56879bad |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/relation-extraction-skill/`（未改写；已用 SHA-256 复算校验）。
