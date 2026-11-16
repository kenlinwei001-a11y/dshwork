# 用 slots_candidate 做规则卡种子（29 条已带谓词）

## 这份文件解决什么

标准侧抽规则卡，原来是从条文里"读出"要求再"转成"谓词，两步都由模型做。
`contracts/derived/slots_candidate.jsonl` 已把这两步的人工对照固化：每条带
`standard / clause / doc_item / doc_type / requirement / predicate_hint / match_hints`。

**规则卡的 `requirement + predicate` 直接从这里取，模型只做校对，不做生成。**

## 怎么用（三步）

1. 按 `clause` 找到候选条目（与 `03-rules.json` 的 clause 对齐）；
2. 取 `requirement` 作规则卡的 `statement`；取 `predicate_hint` 作 `predicate`；
3. **校对三件事**——模态（应/宜/可/不应）、单位、适用域；对不上就标 GAP，不改候选。

## 已实测的数字

| 项 | 数量 |
|---|---|
| 候选总数 | 146 条 |
| **已带谓词** | **29 条**（`≥10%`、`≤10%`、`80%~120%` 这类） |
| 条款与图对齐 | HJ 84：23/23；HJ 671：16/16（**100% 落在图内**） |
| 原始记录侧脚本命中率 | 49.3%（阈值 3，行标签加权） |
| 检测报告侧脚本命中率 | **0%**（条目名无行标签，只能当查漏清单） |

## 硬口径

- **候选不是判据来源**：条款锚以 `01-clauses.json` 为准，候选只提供"应填什么"；
- **`predicate_hint` 是提示不是结论**：写进规则卡前必须回原文核对该数值与单位；
- **不得用候选生成条款**：条款清单来自标准正文，候选只补充"这条要求对应哪份文档"；
- 候选来自脱敏后的对应表，可跨报告复用；其中的具体实测值已全部删除。

## 与其它产物的关系

```
01-clauses.json（条款，唯一权威）
      │
      ├── slots_candidate.jsonl（本文件描述的种子：条款 → 应填要求 → 谓词）
      │
      └── 03-rules.json（规则卡：requirement + predicate + anchor + check_targets）
```

`check_targets` 的 `doc_type` 可以直接取候选的 `doc_type`；`match_hints` 取候选的
`match_hints`，但**报告类需人工补行标签**（自动抽的词太泛，实测 0%）。
