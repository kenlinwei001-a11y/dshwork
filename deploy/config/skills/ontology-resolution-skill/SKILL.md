---
name: ontology-resolution-skill
description: "将候选 Entity 映射到项目 Ontology Registry 中的标准类型、属性和约束。"
---

# Ontology Resolution Skill

## Skill ID
SK-04

## Purpose
将候选 Entity 映射到项目 Ontology Registry 中的标准类型、属性和约束。

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

## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。


## 数值实体与判断实体的类型映射

| 抽到的实体 | 映射到 Ontology 的哪个类型 | 必填属性 |
|---|---|---|
| 数值实体（总建筑面积=18319㎡） | `Quantity` / `Measurement` | `subject` `value` `unit` `section` |
| 设备参数（泵 H=75m） | `DeviceParameter` | `device_model` `param_name` `value` `unit` |
| **规范要求**（候梯厅>1.8m） | `NormRequirement`（**不是 Quantity**） | `standard` `clause` `limit` |
| 判断对象（建设必要性） | `JudgmentSubject` | `judgment_type` `claim_ref` |
| 判断主体（编制方/评审方） | `JudgmentMaker` | `role` |
| 判断依据（政策文件） | `Reference` | `doc_number` `effective_state` |

**关键区分**：

> **规范要求 ≠ 项目取值。**
> 「候梯厅深度 >1.8m」是标准的要求（`NormRequirement.limit`），
> 「本项目候梯厅 2.2m」是项目的取值（`Quantity.value`）。
> 映射错会让下游把「要求」当「设计值」判合规。

## 三条校验

| 检查 | 判据 |
|---|---|
| 数值实体完整性 | `subject` + `value` + `unit` 三者非空 |
| 规范要求定性 | 若上下文含「应/不应/不应小于/必须」，映射为 `NormRequirement` 而非 `Quantity` |
| 判断实体有据 | `JudgmentSubject` 必须挂 `claim_ref`，且该 claim 的 `evidence_refs` 尽量非空 |

## 工序（四段式）

**契约**

```json
{"mapping": {"required": ["candidate", "standard_type", "required_props"],
             "standard_type": {"description": "Ontology Registry 里的类型"}}}
```

**执行**

```python
def map_type(ent) -> dict:
    t = lookup_ontology(ent)                       # 先查 Registry
    if not t:
        return {"candidate": ent, "standard_type": None, "reason": "Registry 无匹配，需扩展"}
    missing = [p for p in t.required if not ent.get(p)]
    return {"candidate": ent, "standard_type": t.name,
            "required_props": t.required, "missing": missing}
```

**门禁 P6 · 映射合规**

```
每个实体映射到标准类型；必填属性缺失要列出；Registry 无匹配标「需扩展」不硬塞
```

**代价（实测）**

```
「规范要求」当成「项目取值」映射 → 12 条无障碍尺寸误判
→ 新增映射规则：NormRequirement 与 Quantity 必须分开
```
