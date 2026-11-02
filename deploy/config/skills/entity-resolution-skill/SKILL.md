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

> 关系合法性校验：引用 relation-extraction-skill 的关系族定义（七族开放词表），本 skill 不重复词表。
1. 只使用输入中存在或可由明确规则推导的信息，不编造事实。
2. 所有结果尽可能绑定 `project_id`、`document_id`、`version_id`。
3. Fact、Claim、Evidence、Reasoning 必须保留来源链。
4. 发现冲突时输出冲突状态，不擅自裁决。
5. 不得在没有复用策略的情况下跨项目复制项目专属事实。

## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。

## 工序（四段式）

**契约**

```json
{"resolution": {"required": ["candidates", "decision", "basis"],
                "decision": {"enum": ["SAME", "NOT_SAME", "AMBIGUOUS"]}}}
```

**执行**

```python
def resolve(name, candidates) -> dict:
    exact = [c for c in candidates if c.name == name]
    if len(exact) == 1: return {"decision": "SAME", "target": exact[0], "basis": "名称精确相同"}
    if len(exact) > 1:  return {"decision": "AMBIGUOUS", "basis": "同名多个，需人工"}
    return {"decision": "NOT_SAME", "basis": "无同名候选"}
```

**门禁 P5 · 消歧留痕**

```
每个消歧决策带 basis；AMBIGUOUS 必须保留原始候选，不许擅自合并
```

**代价（实测）**

```
「办公用水 35」判成「办公用水量」→ 实为「教师用水定额」
27 个主体自动修正，全部需留 subject_was + basis
```
