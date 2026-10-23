---
name: knowledge-generalization-skill
description: "从历史项目中提取可复用 Ontology、Reasoning Pattern、Claim Pattern、分析框架和规则，同时隔离项目专属事实。"
---

# Knowledge Generalization Skill

## Skill ID
SK-14

## Purpose
从历史项目中提取可复用 Ontology、Reasoning Pattern、Claim Pattern、分析框架和规则，同时隔离项目专属事实。

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
{"asset": {"required": ["id", "kind", "source", "isolated_facts"],
           "kind": {"enum": ["induced", "registered"],
                    "description": "induced=从报告归纳的候选方法；registered=有代码/配置的真实能力"}},
 "status": {"enum": ["draft", "validated", "published"]}}
```

**执行**

```python
def generalize(project) -> list[dict]:
    assets = []
    for pat in extract_patterns(project):       # 本体/推理模式/Claim 模式
        assets.append({"id": pat.id, "kind": "induced",
                       "source": project.id,
                       "isolated_facts": separate_project_facts(pat)})
    assert all(a["isolated_facts"] is not None for a in assets), "项目专属事实必须隔离"
    return assets

assert all(a["status"] != "published" or a["kind"] == "registered"
           for a in assets), "仅报告只能归纳 induced，published 需 registered"
```

**门禁 P18 · 资产分级**

```
induced（归纳候选）与 registered（登记真实能力）必须分开；
draft → validated → published 单向；未过质量关不得发布
```

**代价（实测）**

```
把某次任务的答案写成永久规则 → 下个项目套错
仅凭报告就声明「具备某能力」→ 无代码/配置，无法复现
```
