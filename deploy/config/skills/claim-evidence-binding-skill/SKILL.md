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


## 三级证据判定：190 条误报降到 2 条（V2.8）

### 原问题

一个可研项目报「关系缺证据 190 条」，实际只有 **2 条真缺**。

原因：只查 `relation.source`，但**依据可能在别处**。

### 三级判定

```
① 关系自带 source.quote / source.standard   → 有依据
② 依据在别处：
     cites        → 引用目标本身即依据
     supports     → 证据节点本身即依据
     computed_from → 算式即依据
     bounded_by   → 条款即依据
     depends_on/causes → 起点论断的 cites
③ 端点 anchor → 有依据
④ 都没有 → 真缺
```

### 实测结果

```
quote     212 条   关系自带原文
self       97 条   依据在别处
missing     5 条   真缺
────────────────
可溯源率 98.4%
```

**从 22.8% 提到 98.4%** —— 不是补了数据，是**判定逻辑对了**。

### 五级判决（原有，不变）

| 判决 | 含义 |
|---|---|
| SUPPORT | 证据直接支撑论断 |
| PARTIAL_SUPPORT | 部分支撑 |
| CONTRADICT | 证据与论断矛盾 |
| CONTEXT | 仅是背景，不支撑 |
| INSUFFICIENT | 不足 |

### 一条铁律

> **「缺证据」这个词要慎用。**
>
> 先查三级，确认依据不在别处，才能说「真缺」。
> 否则报 190 条，编制方会认为系统在乱报。

## 工序（四段式）

**契约**

```json
{"binding": {"required": ["claim", "evidence", "verdict"],
             "verdict": {"enum": ["SUPPORT", "PARTIAL_SUPPORT", "CONTRADICT",
                                  "CONTEXT", "INSUFFICIENT"]}}}
```

**执行**

```python
def judge(claim, evidence) -> str:
    if any(contradicts(e, claim) for e in evidence):  return "CONTRADICT"
    if all(supports(e, claim) for e in claim.premises): return "SUPPORT"
    if any(supports(e, claim) for e in claim.premises): return "PARTIAL_SUPPORT"
    if evidence:                                      return "CONTEXT"
    return "INSUFFICIENT"

# 三级判定找依据（实测 190 → 2）
def find_evidence(rel, graph):
    if rel.get("source"):                    return "quote"    # ① 自带
    for t in ("cites", "supports", "computed_from", "bounded_by"):
        if has_neighbor(rel, t):             return "self"     # ② 在别处
    if endpoint_has_anchor(rel):             return "anchor"   # ③ 端点
    return "missing"
```

**门禁 P12 · 判决五级**

```
每条论断有判决；SUPPORT/PARTIAL 才算有依据；报「缺证据」前必须过三级判定
```

**代价（实测）**

```
只查 relation.source → 报「缺证据 190 条」
三级判定后 → 真缺 2 条，可溯源率 22.8% → 98.4%
```
