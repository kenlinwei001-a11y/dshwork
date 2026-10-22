# 技能：claim-evidence-binding-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | claim-evidence-binding-skill |
| description | 判断 Evidence 与 Claim 的关系：SUPPORT、PARTIAL_SUPPORT、CONTRADICT、CONTEXT 或 INSUFFICIENT。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/claim-evidence-binding-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 2.9 KB |
| 被忽略文件 | SKILL.md.bak.anchor.20261015175558（编辑器备份/系统文件，不进入副本） |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家、推演写作专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、推演写作专家（expert-a0a771c8b0da）、知识处理专家 副本（expert-131e1b3979fe）、检测报告审核专家（expert-42bd48d396a6）、过程文档审核专家（expert-86f3e846af69）、推演式报告写作专家（expert-97703554b311）、审核裁定专家（expert-bad4a0f42fda）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: claim-evidence-binding-skill
description: "判断 Evidence 与 Claim 的关系：SUPPORT、PARTIAL_SUPPORT、CONTRADICT、CONTEXT 或 INSUFFICIENT。"
---

# Claim Evidence Binding Skill

## Skill ID
SK-09

## Purpose
判断 Evidence 与 Claim 的关系：SUPPORT、PARTIAL_SUPPORT、CONTRADICT、CONTEXT 或 INSUFFICIENT。

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

## 位置锚与重绑（identity ≠ position）

**claim/evidence/node 一律携带 `anchor`**：
```yaml
anchor:
  doc_span: [起始, 结束]     # 主锚：文档绝对偏移（与切块/分句无关）
  quote: "逐字引文"          # 主锚：重绑抓手
  sentence_id: c-xxxx-S001   # 索引：可重建
  slice_id: c-xxxx           # 代指：当前这一代（**不是身份**）
  order: 3                   # 同一切片内次序
  locatable: true
  precision: exact|slice     # 精度分级
  position_status: ok|UNLOCATED|DANGLING
```

**重绑 `rebind_positions()`**：
- 触发：**重切块 / 重分句 / 客户改稿**后
- 做法：用 `doc_span`/`quote` 在当前正文里**重新定位**，回填**当前这一代**的 `slice_id`/`sentence_id`
- **铁律**：**逻辑对象 ID 不变**（只改锚）；重绑不到 ⇒ `position_status: DANGLING` **待审**，不静默、不清零
- 实证：本项目 4 条 claim 位置悬空（切片已不存在）⇒ 重绑**修复 2 条**（ID 未变），2 条为概括句、诚实保持待审


## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 2070 | a464a84bd385b029 |
| prompts/system.md | 167 | 3c7ef331f57425ca |
| schema/output.json | 385 | 49a21f7072d1ab92 |
| tests/expected.json | 45 | a1dacbe5e304b77c |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/claim-evidence-binding-skill/`（未改写；已用 SHA-256 复算校验）。
