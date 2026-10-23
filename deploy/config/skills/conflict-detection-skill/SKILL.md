---
name: conflict-detection-skill
description: "检测数字、时间、实体、Claim 和版本之间的冲突，并输出待审状态而非自动裁决。"
---

# Conflict Detection Skill

## Skill ID
SK-13

## Purpose
检测数字、时间、实体、Claim 和版本之间的冲突，并输出待审状态而非自动裁决。

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


## 冲突类型与因果链（V2.8）

### 三分类（本轮实测 16 条）

| 类型 | 条数 | 谁处理 |
|---|---|---|
| `resolved` | 9 | 系统已判定，无需甲方 |
| `report_fix` | 5 | 报告需修正（引用旧版、名称过时） |
| `open` | 2 | **需甲方澄清** |

### evidence_strength 决定冲突强度

| strength | 含义 | 例子 |
|---|---|---|
| `strong` | 有计算支撑，只需确认 | 建筑高度 49（算得） vs 60（原文写） |
| `weak` | 两种解释都成立 | 办公用水定额 50 vs 35（给排水口径 vs 节能口径） |
| `none` | 无依据 | — |

**strong 类可以直接给建议值，weak 类必须转甲方。**

### 因果链：冲突不是一个一个解决的

```
建筑高度 60 vs 49   ← 根因
    ├─CAUSED→ 耐火等级 二级 vs 一级
    └─CAUSED→ 消防水箱 18 vs 36 m³
```

**三个冲突共用一个根因** —— 不建因果边，清单里是三条并列的待审，
看不出「解决建筑高度，另两条自动消解」。

### 建因果边的判据

| 判据 | 例子 |
|---|---|
| A 的取值决定 B 的判据 | 高度 >50m → 一类高层 → 耐火等级变 |
| A 和 B 共同决定同一输出 | 定额 × 人数 → 日用水量 |
| A 是 B 的计算输入 | 面积 → 造价 |

**边要带 `why`，不能凭主题相似建。**

### 边类型（Semantica 枚举）

```
CAUSES / CAUSED / INFLUENCES / INFLUENCED
PRECEDES / PRECEDENT_FOR / LEADS_TO / LEAD_TO / SUPPORTS / SUPPORT
```

**大小写不敏感**（内部 `.upper()`），但必须在这个集合内。

### 一条铁律

> **冲突只标「待审」，不擅自裁决。**
> **但可以指出「哪条是根因」** —— 这是分析，不是裁决。

## 工序（四段式）

**契约**

```json
{"conflict": {"required": ["id", "subject", "values", "evidence_strength", "status"],
              "evidence_strength": {"enum": ["strong", "weak", "none"]},
              "status": {"enum": ["resolved", "report_fix", "open"]}}}
```

**执行**

```python
def detect(graph) -> list[dict]:
    out = []
    for subj, vals in group_by_subject(graph.facts).items():
        if len({v.value for v in vals}) <= 1: continue
        out.append({"subject": subj, "values": [v.value for v in vals],
                    "evidence_strength": strength_of(vals),
                    "status": "open"})      # 默认待审，不裁决
    return out

assert all(c["status"] in ("resolved", "report_fix", "open") for c in out)
```

**门禁 P16 · 冲突待审**

```
多值必须登记；strong 可给建议值，weak 必须转甲方；不许静默裁决
```

**代价（实测）**

```
16 条冲突：9 resolved / 5 report_fix / 2 open
建筑高度 49(算得) vs 60(原文写) → strong，只需确认
办公用水 50 vs 35 → weak（给排水口径 vs 节能口径），必须转甲方
```
