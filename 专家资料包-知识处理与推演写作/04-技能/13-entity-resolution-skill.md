# 技能：entity-resolution-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:44:08Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | entity-resolution-skill |
| description | 解决同义词、别名、简称与跨文档重复，并识别 NOT_SAME 与 AMBIGUOUS。触发：这两个名字是不是同一家、合并别名和简称、跨文档去重。不适用：新增实体、判定实体类型。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/entity-resolution-skill |
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
name: entity-resolution-skill
description: "解决同义词、别名、简称与跨文档重复，并识别 NOT_SAME 与 AMBIGUOUS。触发：这两个名字是不是同一家、合并别名和简称、跨文档去重。不适用：新增实体、判定实体类型。"
---

# Entity Resolution Skill

## Skill ID
SK-11

## Purpose
解决同义词、别名、简称和跨文档实体重复问题，并识别 NOT_SAME 与 AMBIGUOUS。

## 何时使用

调用条件：已有实体列表及各自的证据提及（mention）。
- 典型请求：这两个名字是不是同一家｜合并别名和简称｜跨文档去重
- 不要在此调用：新增实体、判定实体类型
## 边界与不适用

- 不做：证据不足时输出 AMBIGUOUS 或 NOT_SAME，不硬合并
- 不做：不改写实体描述与原文提及
- 缺输入：先有实体列表及各自的证据提及
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 879 | 2714f7e75758d933 |
| prompts/system.md | 157 | ee1d7d986902e558 |
| schema/output.json | 380 | 6e3827b1ced34d9c |
| tests/expected.json | 45 | 0cd03afa2219d615 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/entity-resolution-skill/`（未改写；已用 SHA-256 复算校验）。
