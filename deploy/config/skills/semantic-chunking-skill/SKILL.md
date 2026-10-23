---
name: semantic-chunking-skill
description: "按照章节、主题和语义边界将 Document IR 切分为稳定的语义 Chunk，供后续抽取和检索使用。"
---

# Semantic Chunking Skill

## Skill ID
SK-01

## Purpose
按照章节、主题和语义边界将 Document IR 切分为稳定的语义 Chunk，供后续抽取和检索使用。

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
{"chunk": {"required": ["id", "text", "span", "section"],
           "span": {"required": ["start", "end"]}}}
```

**执行**

```python
def chunk(doc) -> list[dict]:
    out = []
    for sec in doc.sections:
        for seg in semantic_split(sec):            # 段落 / 表 / 图注 独立成块
            out.append({"id": stable_id(seg), "text": seg.text,
                        "span": seg.span, "section": sec.id})
    assert sum(len(c["text"]) for c in out) >= 0.85 * len(doc.text), "切块丢失超过 15%"
    return out
```

**门禁 P3 · 切块闭环**

```
Σchunk 去空白 ≈ 原稿（±15%）；每块 span 可回查；表格不按行切
```

**代价（实测）**

```
表格按行切块 → 每行独立成 chunk → 表头与数据永远分家
```
