---
name: evidence-extraction-skill
description: "定位支持 Fact 或 Claim 的原始证据，包括文档、页码、章节、Chunk、Sentence 和文本范围。"
---

# Evidence Extraction Skill

## Skill ID
SK-08

## Purpose
定位支持 Fact 或 Claim 的原始证据，包括文档、页码、章节、Chunk、Sentence 和文本范围。

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


## 证据分级：新增 E0，31 条 E1 重分级（V2.8）

### 原问题

31 条标 `E1（客户给定）` 的证据，**全部缺 provider/provide_date/version**，
且其中大部分根本不是「客户给定」。

### 七级 + hypothesis

| kind | 含义 | verifiable | 责任方 | 必填 |
|---|---|---|---|---|
| **E0** | **编制方踏勘/调查** | true | 编制方 | survey_date / surveyor / basis |
| E1 | 客户给定 | false | 提供方 | provider / provide_date / version |
| E2 | 规范条文 | true | 标准发布机构 | 标准号 + 条款号 |
| E3 | 外部公开数据 | true | 发布机构 | 机构 / 日期 / URL |
| E4 | 图内派生 | true | 系统 | leaf_refs |
| E5 | 类比工程 | partial | 编制方 | 类比对象 + 可比性 |
| E6 | 专家判断 | false | 专家 | 专家身份 + 依据 |
| hypothesis | **预测性表述** | — | — | 不是证据 |

### 重分配实测（31 条 E1）

```
E0           7 条   场地四至、现状描述、措施方案
E1          15 条   校内决议、规划、财务数据
E3          15 条   年度统计（发表论文 87 篇）
E4           8 条   含算式的测算（1210㎡×0.55=2200㎡）
hypothesis   5 条   「到2025年力争…」「预计…」
```

### 判定顺序（关键）

```
① 含「将/力争/到X年」→ hypothesis（不是证据）
② 场地四至 / 现状描述 → E0
③ 含算式/合计/换算 → E4
④ 年度统计数 → E3
⑤ 校内文件/批文/财务 → E1（真客户给定）
```

### E1 的硬条件（缺一不可）

```python
if kind == "E1":
    assert provider and provide_date and version
    # 缺任何一项 → 降级或标 unknown
```

**实测：31 条 E1 全部缺这三项 → 说明标 E1 是默认值，不是判断结果。**

### 一条铁律

> **等级由「可核验性 + 责任方」决定，不由内容像什么决定。**
>
> 场地四至能复查 → E0；财务数据只能甲方给 → E1；
> 规范条文可查 → E2；算式可复算 → E4。

## 工序（四段式）

**契约**

```json
{"evidence": {"required": ["id", "kind", "quote"],
              "kind": {"enum": ["E0","E1","E2","E3","E4","E5","E6","hypothesis"]},
              "quote": {"minLength": 1, "description": "不许是 'None' 字符串"}}}
```

**执行**

```python
def assign_kind(ev) -> str:
    if has_future_word(ev):        return "hypothesis"   # ① 将/力争/预计
    if is_site_survey(ev):         return "E0"           # ② 场地四至/现状
    if has_formula(ev):            return "E4"           # ③ 含算式
    if is_annual_stat(ev):         return "E3"           # ④ 年度统计
    if is_internal_doc(ev):        return "E1"           # ⑤ 校内文件
    return "E6"

assert ev["kind"] in EVIDENCE_KINDS
assert str(ev["quote"]) not in ("None", "none", ""), "quote 不许是 None 字符串"
```

**门禁 P10 · 证据分级**

```
kind 在七级内；quote 非空且不是 'None' 字符串；E1 必须带 provider/date/version
```

**代价（实测）**

```
343 个 ev- 节点 quote 是字符串 'None' → 空证据
其中 317 个能在原文定位 → 补 quote 后 304 成功
31 条 E1 全部缺三要素 → 重分为 E0×7/E1×15/E3×15/E4×8/hypothesis×5
```
