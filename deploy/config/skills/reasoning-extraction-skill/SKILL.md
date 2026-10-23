---
name: reasoning-extraction-skill
description: "识别公式、规则、多步推导和中间结论，形成 Reasoning 节点及输入输出依赖。"
---

# Reasoning Extraction Skill

## Skill ID
SK-10

## Purpose
识别公式、规则、多步推导和中间结论，形成 Reasoning 节点及输入输出依赖。

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

## 工序（四段式）

**契约**

```json
{"rule": {"required": ["id", "expr", "kind", "deps"],
          "kind": {"enum": ["compute", "condition"],
                   "description": "condition 是 A=>B；否则=>C 判定式"}},
 "binding": {"required": ["target", "expr", "deps"],
             "deps": {"items": {"required": ["node", "value"]}}}}
```

**执行**

```python
def bind(rule, nodes) -> dict:
    deps = {}
    for d in rule.deps:
        n = search_value_node(d, nodes, aliases)        # 三方式搜
        deps[d] = {"node": n["id"] if n else None,
                   "value": n["value"] if n else None,
                   "how": "精确/别名/包含" if n else "未绑定"}
    return {"target": rule.target, "expr": rule.expr, "kind": rule.kind, "deps": deps}

assert all(d["node"] or d["how"] == "未绑定" for d in deps.values())
```

**门禁 P11 · 绑定完整**

```
每个 dep 要么有 node、要么标「未绑定」并带 searched 证据；判定式不许用 eval
```

**代价（实测）**

```
「主体包含」匹配不校验量纲 → 费率绑到 618 万元 → 算出 76378（应 618）
判定式 A<=B => 合理；否则 => 待审 用 eval → 必然 SyntaxError
绑定表填 node 但不建 relations 边 → 输入节点成孤儿
```
