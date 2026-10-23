---
name: relation-extraction-skill
description: "抽取实体之间的业务语义关系，并绑定关系证据和来源 Sentence。"
---

# Relation Extraction Skill

## Skill ID
SK-05

## Purpose
抽取实体之间的业务语义关系，并绑定关系证据和来源 Sentence。

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

权威定义：`<项目>/reuse/relation_types.yaml`。

| 族 | 类型 | **必需载荷**（缺即不可判定） |
|---|---|---|
| **A 推理** | derives_from · entails · supports · contradicts · presupposes(=depends_on) · concludes · causes | 算子（strength/prerequisite/conflict_type/mechanism 等） |
| **B 结构** | part_of · has_part · composes · located_in · temporal | **公理**（`axiom ∈ {sum,containment,membership}`；**sum 仅可加量**） |
| **C 借用引用** | reuses · instantiates · fills · cites · sourced_from · declared_in · transfers_to · generalizes_to · supersedes · scoped_to | **范围** |
| **D 对齐锚定** | same_as · distinct_from · ambiguous_with | 消歧依据 |
| **E 资产治理** | depends_on_asset · gated_by · published_as · impacted_by | 状态与版本 |
| **F 规则**（超边 n→1） | computes · judges · selects | 输入/输出洞 + 类型约束 + guard |
| **G 约束** | bounds · requires · recommends · propagates_modality_to | 权威(名+条款+效力) + 谓词 + 值域 + 模态 + 强度 |

**三条硬规则**：
1. **必需载荷缺一不可** —— 缺则该关系不可判定，**不得提交**
2. **`has_value` 不是关系**（它是节点字段）——已弃用，不得作为 relation 提交
3. **不符合七族者**：不得丢弃、不得硬塞 —— 记入 `relation_candidates.yaml` 作为**候选提议**
   （抽取只能**归纳候选**；登记是受控动作）

**扩充机制（词表是活件，七族为本轮快照，非闭集）**：
- 新类型须过五条准入：**有算子 / 有必需载荷 / 不同义 / 有实例 / 可迁移**
- **同义按归约优先作别名**（如 `depends_on` → `presupposes`），不新增类型
- 防线：严准入 · 归约优先 · 弃用清理 · 实例驱动（本项目 `instance_of`/`has_attribute` 是死类型前车之鉴）

**强制点**：构造器 `rel(f, t, ty, payload)` **在构造时**校验类型与载荷——不通过即报错，不进入图谱。

## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。


## 因果误判：删 6 条、改型 5 条（V2.8）

### 实测问题

一个可研项目 313 条关系里发现 12 条类型错误：

| 问题 | 条数 | 例子 |
|---|---|---|
| **因果不成立** | **6** | `CL-节能-01（满足节能标准）causes→ CL-风险-03（农民工风险）` |
| **方向反了** | 3 | `CL-结论-01 depends_on → CL-建议-01`（实际是结论支撑建议） |
| **并列误判为依赖** | 2 | `科研用房用电面积 depends_on 公共配套用电面积` |

### 判据：因果需要「机制」

```
✓ 建筑高度 >50m → 属一类高层 → 耐火等级要求变
    （有明确判定规则）

✗ 满足节能标准 → 农民工风险
    （毫无机制，只是同段共现）
```

**同段共现 ≠ 因果。** 抽取时把「同一段落里出现」当成了因果关系。

### 方向判据

```
A depends_on B  →  B 是 A 的前提（B 不成立，A 就不成立）
A supports B    →  A 支撑 B 的结论（A 成立，B 更有把握）
```

```
✗ 结论 depends_on 建议     （建议不成立不影响结论）
✓ 结论 supports 建议       （结论支撑建议的合理性）
```

### 改型要留痕

```python
r["relation_was"] = r["type"]
r["type"] = "supports"
r["payload"]["retyped_from"] = {
    "was": "depends_on", "now": "supports",
    "why": "结论支撑建议，不是建议依赖结论"
}
```

### 因果链的价值

补对因果边后，能用 `semantica_causal_chain` 追出：

```
建筑高度 60vs49 → 耐火等级 / 消防水箱
```

**一个根因三个表象，不建因果边看不出来。**

## 工序（四段式）

**契约**

```json
{"relation": {"required": ["id", "from", "to", "type"],
              "type": {"enum": "读 reuse/relation_types.yaml，不硬编码"},
              "payload": {"description": "因果类必须带 why"}}
```

**执行**

```python
def extract(entities) -> list[dict]:
    rels = []
    for pair in candidates:
        t = classify_relation(pair)
        if t == "causes":
            assert has_mechanism(pair), f"{pair} 无因果机制，不得判 causes"
        rels.append({"from": pair.a, "to": pair.b, "type": t,
                     "source": {"quote": pair.evidence}})
    return rels

assert all(r["type"] in REL_TYPES for r in rels), "关系类型越界"
```

**门禁 P8 · 关系合法**

```
类型在枚举内；causes 必须有机制（不是同段共现）；端点必须可寻址
```

**代价（实测）**

```
「满足节能标准 → 农民工风险」判成 causes → 毫无机制，只是同段共现
删 6 条误判因果、改型 5 条（结论 depends_on 建议 → 应为 supports）
```
