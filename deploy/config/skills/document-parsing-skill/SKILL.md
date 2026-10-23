---
name: document-parsing-skill
description: "将 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，并保留页码、段落、表格和原文定位信息。"
---

# Document Parsing Skill

## Skill ID
SK-00

## Purpose
将 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，并保留页码、段落、表格和原文定位信息。

## Input
- `project_id`
- `document_id`
- `version_id`
- 上游 Skill 输出
- 原文或结构化中间结果

## Output
输出必须包含稳定 ID、来源定位（provenance）以及与上下游对象的关联字段。

## Execution Rules
1. 不编造输入中不存在的事实。
2. 所有抽取结果必须尽可能绑定 `project_id`、`document_id`、`version_id`。
3. 涉及事实、Claim、Evidence、Reasoning 时必须保留来源链。
4. 发现冲突时标记冲突，不擅自选择一个版本作为真值。
5. 项目专属数据不得在没有明确复用策略时跨项目复制。

## Validation
执行 `tests/golden.json` 与 `tests/expected.json` 中定义的基础验收。

## 工序（四段式）

**契约**

```json
{"document_ir": {"required": ["blocks", "pages", "source_path"],
                 "blocks": {"items": {"required": ["type", "span", "page"]}},
                 "type": {"enum": ["paragraph", "table", "figure", "caption"]}}}
```

**执行**

```python
def parse(path) -> dict:
    blocks = []
    for b in iterate_blocks(path):
        blocks.append({"type": b.type, "span": b.span, "page": b.page,
                       "text": b.text, "grid": b.grid if b.type == "table" else None})
    assert blocks, "解析为空"
    assert all(b["span"] for b in blocks), "每个块必须有原文定位"
    return {"blocks": blocks, "pages": count_pages(path), "source_path": str(path)}
```

**门禁 P1 · 解析闭环**

```
每个块有 span 可回原文；表格块必须带 grid（二维结构），不许拍平成文本
```

**代价（实测）**

```
表格拍平成 markdown → 表头与数据行分离 → 列名永远关联不上
→ 40+ 财务节点 subject 退化成「2018」
```
