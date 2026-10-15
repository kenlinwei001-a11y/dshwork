---
name: entity-resolution-skill
description: "解决同义词、别名、简称和跨文档实体重复问题，并识别 NOT_SAME 与 AMBIGUOUS。"
---

# Entity Resolution Skill

## Skill ID
SK-11

## Purpose
解决同义词、别名、简称和跨文档实体重复问题，并识别 NOT_SAME 与 AMBIGUOUS。

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

**本 skill 的关系落点**：
- **D 族（对齐锚定）**：`same_as` / `distinct_from` / `ambiguous_with` 必须**带消歧依据**并**以关系形式落图**，不能只写在字段里（字段无法被推演消费）
- **别名归约（防类型爆炸）**：同义概念按**归约优先**处理，并记录映射（如 `depends_on` → `presupposes`），不得作为新类型登记
- **C 族辅助**：跨文档同指用 `sourced_from` 锚定到原文位置（含 `table_cell`）；跨域借用参数用 `transfers_to` 并**必填越域理由**
- 消歧不确定时**不得假定同一概念**：标 `ambiguous_with`，下游暂不引用


## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。
