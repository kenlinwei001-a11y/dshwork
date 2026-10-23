---
name: fact-extraction-skill
description: "将文本中的可验证信息抽取为 Subject-Predicate-Value-Time-Source 结构化事实。"
---

# Fact Extraction Skill

## Skill ID
SK-06

## Purpose
将文本中的可验证信息抽取为 Subject-Predicate-Value-Time-Source 结构化事实。

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


## 与 claim 的边界：49 条 judgment 实为 fact（V2.8）

### 实测数据

一个可研项目 68 个 judgment 节点，**49 条实际是 fact**：

| 例子 | 为什么是 fact |
|---|---|
| `本报告编号 = 2019ZX054` | 编号，可查 |
| `建筑耐火等级 = 二级` | 参数，查图纸可验 |
| `各空调系统防火阀与风机联锁` | 规范要求转述（GB50016） |
| `人均面积指标应不超过 16㎡/人` | 规范要求转述（建标191） |
| `国拨 6000 万、自筹 7032 万` | 金额，查批复可验 |

### 判据（与 claim 的分工）

```
有具体取值 + 无判断词          → fact
含「应/不应/必须」+ 标准号      → fact（规范要求转述，不是本项目的判断）
主体-谓词-取值三元组齐全        → fact
含判断词（充分/合理/必要/可能）  → claim
```

### 改判不能删节点

改判为 fact 的节点**仍在图谱里**（`kind` 变了），只是移出 `claims.yaml`。

```python
# 正确：改 kind，保留节点与关系
n["kind"] = "fact"
n["reclassified_from"] = "judgment"
n["reclassified_claim_type"] = n.pop("claim_type")   # 保留痕迹

# 错误：删节点
# → 关系悬空
```

**实测坑**：改判后 `claim_type='fact'` 残留了 7 个节点，校验时报错。必须清掉并保留到 `reclassified_claim_type`。

### 规范要求 ≠ 项目取值

```
「无障碍电梯候梯厅深度 >1.8m」  → 这是 GB50763 的要求，不是本项目设计值
                              → 归 fact 但标 E2（规范条文），不标本项目取值
```

**实测 12 条无障碍尺寸被误当项目参数。**

## 工序（四段式）

**契约**

```json
{"fact": {"required": ["id", "subject", "predicate", "value", "section"],
          "value": {"description": "可为数字或字符串（'二级' / '2026-08-18/36h'）"}}
```

**执行**

```python
def extract(text, chunk) -> list[dict]:
    """与 claim 的边界：有具体取值+无判断词 → fact"""
    facts = []
    for m in SPO_PATTERN.finditer(text):
        if is_judge_sentence(m.group(0)):  continue      # 有判断词 → 去 claim
        if is_norm_restatement(m.group(0)):              # 规范转述 → fact 但标 E2
            facts.append({"subject": m["s"], "predicate": m["p"], "value": m["o"],
                          "kind": "fact", "evidence_kind": "E2"})
        else:
            facts.append({"subject": m["s"], "predicate": m["p"], "value": m["o"],
                          "kind": "fact", "evidence_kind": "E1"})
    return facts
```

**门禁 P7 · 事实完整**

```
每条有 主体-谓词-取值；规范转述标 E2（不是项目取值）；改判不删节点
```

**代价（实测）**

```
49 条 judgment 实为 fact（参数/规范转述/编号）
改判后 claim_type='fact' 残留 7 个节点 → 校验报错
→ 移到 reclassified_claim_type，保留改判痕迹
```
