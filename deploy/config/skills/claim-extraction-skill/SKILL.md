---
name: claim-extraction-skill
description: "识别判断、结论、风险、预测、因果判断和建议等 Claim，并建立依赖关系。"
---

# Claim Extraction Skill

## Skill ID
SK-07

## Purpose
识别判断、结论、风险、预测、因果判断和建议等 Claim，并建立依赖关系。

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


## 确定性判据：claim 不是「看起来像判断」就算（V2.8）

### 为什么必须确定性

实测一个可研项目：68 个原 judgment 节点，复判后**只剩 19 条是真 claim**，
**49 条是 fact**（参数、规范转述、编号）。误差率 74%。

误差来源：抽取时按「章节倾向」给 kind，§6 技术方案整章被当成 claim，但里面全是参数。

### 四步判定（顺序不可换）

```
① 规范条文转述 → fact      含「应/不应/必须」+ 标准号
①b 三元组完整  → fact      主体-谓词-取值齐全且无强判断词
②  判断词分类  → claim     建议/预测/推理/结论四族
③  有值无判断词 → fact     数值型 或 文本型取值（二级/乙类/联锁/方位）
④  都没有      → None      不是知识节点
```

### 判断词四族（决定 claim_type）

| 族 | 词 | claim_type |
|---|---|---|
| 建议 | 建议、宜采用、推荐 | `recommendation` |
| 预测 | 可能、预计、力争、届时、将达 | `hypothesis` |
| 推理 | 由于、导致、从而、因此 | `inference` |
| 结论 | 充分、合理、必要、可行、良好、有利、显著、可控、的需要 | `conclusion` |

### 优先级规则（实测踩过的坑）

```
结论词多于推理词 → 结论优先
  「…有利于提升…因此具有良好的社会效益」
    ✗ 判 inference（因为含「因此」）
    ✓ 判 conclusion（结论词 2 个 > 推理词 1 个）
```

### 三条误判修正

| 误判 | 表现 | 修法 |
|---|---|---|
| 「保障」当判断词 | `后勤保障经费` 被判 claim | 改「有保障」 |
| 「因此」一律判推理 | 总结句被判 inference | 结论词占多数时结论优先 |
| 方位/分类值判 None | `二级`/`乙类`/`西侧为绿地` | 加 TEXT_VALUE + DIRECTION 词表 |

### 每条 claim 强制带 falsifiable_by

```yaml
claim:
  text: 建设必要性充分
  claim_type: conclusion
  falsifiable_by: 找到一条证据表明该判断不成立
```

**说不清「什么能推翻它」的，不是判断，是口号，不抽。**

### 工具

```bash
kp_toolkit/claim_classify.py
  classify(text, has_value, has_triple) → {kind, claim_type, falsifiable_by, why}
```

### 一条铁律

> **claim 判错的代价：写作时用错句式（把 hypothesis 写成既成事实）。**
> 判定必须确定性，不能靠 LLM 拍。

## 工序（四段式）

**契约**

```json
{"claim": {"required": ["id", "text", "claim_type", "falsifiable_by"],
           "claim_type": {"enum": ["conclusion", "recommendation", "hypothesis", "inference"]}}}
```

**执行**（`classify()` 的四步判定在上文「确定性判据：claim 不是『看起来像判断』就算」已详述，
本节只给可执行签名与断言，判定表不重复）

```python
def classify(text, has_value, has_triple) -> dict | None:
    """四步判定，顺序不可换"""
    if is_norm_restatement(text):                 return {"kind": "fact"}   # ①
    if has_triple and not has_judge(text):        return {"kind": "fact"}   # ①b
    ct = judge_family(text)                                                # ②
    if ct: return {"kind": "claim", "claim_type": ct}
    if has_value: return {"kind": "fact"}                                  # ③
    return None                                                            # ④

assert claim["claim_type"] in CLAIM_TYPES
assert claim.get("falsifiable_by"), "说不清什么能推翻它 = 口号，不抽"
```

**门禁 P9 · 论断可证伪**

```
claim_type 在四类内；falsifiable_by 非空；49 条改判的 fact 不得回流
```

**代价（实测）**

```
68 个 judgment 复判后只剩 19 条真 claim（误差 74%）
「因此」一律判 inference → 结论句被错分 → 结论词占多数时结论优先
「保障」当判断词 → 「后勤保障经费」被判 claim → 改「有保障」
```
