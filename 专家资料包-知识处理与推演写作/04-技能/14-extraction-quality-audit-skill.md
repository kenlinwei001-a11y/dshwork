# 技能：extraction-quality-audit-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | extraction-quality-audit-skill |
| description | 对抽取结果执行结构完整性、证据覆盖、关系合法性、跨项目污染和孤立节点等质量审计。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/extraction-quality-audit-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 6.4 KB |
| 被忽略文件 | SKILL.md.bak、SKILL.md.bak.20261015135039（编辑器备份/系统文件，不进入副本） |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、知识处理专家 副本（expert-131e1b3979fe）、检测报告审核专家（expert-42bd48d396a6）、实验室证据抽取专家（expert-46a04687c733）、过程文档审核专家（expert-86f3e846af69）、推演式报告写作专家（expert-97703554b311）、审核裁定专家（expert-bad4a0f42fda）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: extraction-quality-audit-skill
description: "对抽取结果执行结构完整性、证据覆盖、关系合法性、跨项目污染和孤立节点等质量审计。"
---

# Extraction Quality Audit Skill

## Skill ID
SK-17

## Purpose
对抽取结果执行结构完整性、证据覆盖、关系合法性、跨项目污染和孤立节点等质量审计。

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

## 关系类型（七族 · 开放词表）

权威定义：`relation_types.yaml`（**单点定义**，可用 MCP `relation_types` 读取）。
关系不是"边"，而是**能承载推理步的对象**；判据：**是否对应一个可执行算子**。

| 族 | 类型 | **必需载荷**（缺即不可判定） |
|---|---|---|
| **A 推理** | derives_from · entails · supports · contradicts · presupposes(=depends_on) · concludes · causes | 算子（operator/strength/prerequisite/conflict_type/mechanism） |
| **B 结构** | part_of · has_part · composes · located_in · temporal | **公理**（`axiom ∈ {sum,containment,membership}`；**sum 仅对可加量成立**） |
| **C 借用引用** | reuses · instantiates · fills · cites · sourced_from · declared_in · transfers_to · generalizes_to · supersedes · scoped_to | **范围** |
| **D 对齐锚定** | same_as · distinct_from · ambiguous_with | 消歧依据 |
| **E 资产治理** | depends_on_asset · gated_by · published_as · impacted_by | 状态与版本 |
| **F 规则**（**超边 n→1**） | computes · judges · selects | 输入/输出洞 + 类型约束 + guard |
| **G 约束** | bounds · requires · recommends · propagates_modality_to | 权威(名+条款+效力)+谓词+值域+模态+强度 |

**三条硬规则**：① 必需载荷缺一不可（缺则不可判定，不得提交）；② **`has_value` 不是关系**（节点字段，已弃用；实测曾占 77%，把 108 条真关系膨胀成 466 条）；③ 不符合七族者**不得丢弃、不得硬塞** —— 记入 `relation_candidates.yaml` 作为候选（抽取只能**归纳候选**，登记是受控动作）。

**扩充机制**：新类型过五条准入【有算子 / 有必需载荷 / 不同义 / 有实例 / 可迁移】；**同义按归约优先作别名**（如 `depends_on` → `presupposes`）；词表版本化，跨项目按版本解释。

**本 skill 的审计项（对七族逐项审计）**：
- **载荷完备率**：各类关系是否带齐必需载荷（缺载荷 ⇒ 该关系不可判定，计入不合格）
- **伪关系占比**：`has_value`/`has_attribute` 占关系层的比例（**>20% 即告警**；本项目实测 77%）
- **整族缺失**：是否出现族级空档（本项目实测 **C 借用引用 / F 规则 / G 约束 三族 0 条** ⇒ 可复用性、推演能力、合法性判据同时缺失）
- **超边丢形**：规则是否被压成二元边（应保持 n→1）
- **模态断链**：G 约束是否缺 `propagates_modality_to`（缺 ⇒ 「上限当最低需求」类错误必然发生）
- **死类型**：声明但零使用的类型须清理（如 `instance_of`/`has_attribute`）
- **候选积压**：`relation_candidates.yaml` 是否长期未审（只提议不登记 ⇒ 词表停滞）


## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。

<!-- kp-patch:v1 -->
## 闭环审计（对「完整性」的审计，而非仅「自洽性」）

本 skill 原有的审计维度（结构完整性、证据覆盖、关系合法性、跨项目污染、孤立节点）
检查的是**产物内部的自洽性**。它们**无法发现遗漏**——因为遗漏的东西不在被遍历的集合里。

补一层**闭环审计**：以源侧索引为基准做集合差。

| 闭环 | 判据 | 阈值 | 失败含义 |
|------|------|------|----------|
| C1 依据 | `原稿《》 − evidence − 豁免 = ∅` | 依据类缺口 = 0 | 报告引用的规范未登记，时效无法核查 |
| C2 关键取值 | `原稿「数字+单位」 − 节点值 − 量纲等价 = ∅` | 缺口 = 0 | 原稿有该数、图谱没建模 |
| C3 章节 | `原稿标题 − outline = ∅` | ≥ 98% | 抽取漏章 |
| C4 设备参数 | `原稿设备参数语句 − 设备节点 ≈ ∅` | ≥ 80% | 明细表无法重建 |
| C5 题注 | `原稿表/图题注 − 成稿 = ∅` | ≥ 60% | 表图未重出 |
| C6 装配 | `defined 且非明细节点 ∩ 成稿引用` | ≥ 95% | 抽到了没写进去 |
| C7 关系 | `应有 claim 关系 − 已有边 = ∅` | 各 100% | 关系词表缺类型 |

**两个必须遵守的细节**：

- **量纲归一**：不归一，「5000 万元」与「50000000 元」会被判成两个不同的数，产生**假缺口**；
  假缺口会磨损门禁可信度（报得太多，人就学会忽略）。
- **探针自证**：未过标定的探针，其判据输出 `invalid`，不得输出「无误」。

**输出契约**：`{id, name, total, covered, exempt, missing[], recall_pct, threshold, verdict}`
，`verdict ∈ {pass, FAIL, invalid}`。**不接受「看起来没问题」这类输出。**
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 5602 | 43929fc9134596fb |
| prompts/system.md | 171 | cc43f45d5671d64a |
| schema/output.json | 387 | ced80bb9082b37bc |
| tests/expected.json | 45 | 9d3c1739ec41bb79 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/extraction-quality-audit-skill/`（未改写；已用 SHA-256 复算校验）。
