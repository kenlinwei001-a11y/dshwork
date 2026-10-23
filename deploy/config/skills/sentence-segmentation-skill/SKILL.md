---
name: sentence-segmentation-skill
description: "将 Chunk 切分为 Sentence，并生成稳定的 Sentence ID，支撑 Claim 追踪和 Semantic Diff。"
---

# Sentence Segmentation Skill

## Skill ID
SK-02

## Purpose
将 Chunk 切分为 Sentence，并生成稳定的 Sentence ID，支撑 Claim 追踪和 Semantic Diff。

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
{"sentence": {"required": ["id", "text", "chunk_id", "span"],
              "id": {"description": "稳定 ID，同输入必同 ID"}}}
```

**执行**

```python
def segment(chunk) -> list[dict]:
    sents = split_sentences(chunk.text)          # 按 。；！？ 且处理英文缩写
    for i, s in enumerate(sents, 1):
        sents[i-1] = {"id": f"{chunk.id}-S{i:03d}", "text": s,
                      "chunk_id": chunk.id, "span": locate(s, chunk)}
    assert sum(len(s["text"]) for s in sents) >= 0.98 * len(chunk.text), "分句丢失超过 2%"
    return sents
```

**门禁 P2 · 分句闭环**

```
Σsentence 字符 ≈ Σchunk 字符（标点归并可解释）；ID 稳定可复现
```

**代价（实测）**

```
按句号硬切 → 「1.5m」「GB50016-2014」被切断
→ 分句后长度对不上，S2 门禁报警
```
