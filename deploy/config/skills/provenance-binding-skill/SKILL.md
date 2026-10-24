---
name: provenance-binding-skill
description: "建立对象之间的来源链，使 Decision 可以反向追溯到 Claim、Reasoning、Fact、Evidence、Sentence、Chunk 和 Document。"
---

# Provenance Binding Skill

## Skill ID
SK-16

## Purpose
建立对象之间的来源链，使 Decision 可以反向追溯到 Claim、Reasoning、Fact、Evidence、Sentence、Chunk 和 Document。

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

## 两层分离：物理从属 vs 逻辑引用

```
┌─ 物理层（**从属** / containment）────────────────────────────┐
│  章节ID → 子章节ID → 切片ID → 句子ID                          │
│  · ID 编码**路径/位置**；**随切分策略而变是它的职责**（可重建）    │
└─────────────────────────────────────────────────────────────┘
                    ▲  锚（anchor）＝**引用，不是从属**
                    │  可重绑 · 可多值 · 可空 · 失效须待审
┌─ 逻辑层（**引用** / reference）──────────────────────────────┐
│  claim · evidence · node · rule · relation · reasoning        │
│  · ID 由**语义/内容**决定，**永不因重切块/重分句而变**            │
│  · **扁平注册表**，不得嵌在物理对象里                            │
└─────────────────────────────────────────────────────────────┘
```

**三条判据（可当检查项）**：
1. **扁平性**：逻辑对象不得作为物理对象的子节点存储
2. **无物化**：逻辑对象不得缓存物理路径（`_chapter`/`_path`/`section`）
3. **锚可重绑**：锚目标必须**可重建**

**锚的选层（关键）**：锚**不选切片 ID**（那是"策略产物"），而选**文档固有坐标**：
```
主锚  doc_span + quote   文档绝对字符偏移 + 逐字引文 —— **与切块/分句都无关**
索引  sentence_id        覆盖该坐标的句子（可重建）
代指  slice_id           当前这一代切片的索引（**不是身份**，可重算）
```
**精度分级**（不得混淆）：`exact`（逐字定位）· `slice`（仅知所在切片）· `UNLOCATED`（天生无逐字引文）· `DANGLING`（**仅表示重绑失败**）。

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

## 工序（四段式）

**契约**

```json
{"chain": {"required": ["object", "path"],
           "path": {"description": "Decision→Claim→Reasoning→Fact→Evidence→Sentence→Chunk→Document"}}}
```

**执行**

```python
def build_chain(obj, graph) -> list:
    path, cur = [obj], obj
    while True:
        up = graph.upstream(cur)        # 沿依赖关系向上
        if not up: break
        path.append(up)
        cur = up
        if len(path) > 20: raise RuntimeError("溯源链超过 20 层，可能有环")
    return path

assert all(p["id"] for p in chain), "链上每环必须可寻址"
```

**门禁 P14 · 溯源可追**

```
任意 Decision 可追到 Document；链上每环有 id；无环
```

**代价（实测）**

```
悬空关系 106 条 → 补 source 后降到 0
但「有 source」不等于「指向存在的节点」→ 必须同时校验端点
```


## 镜像证据：不需要判定强度（V3.0 实测）

### 什么是镜像证据

```
ev-N-xxx  →  N-xxx
同一个 id，前缀 ev- 表示「该事实的原文摘录节点」
```

**它不是「另一条证据」，是这个事实自己的原文锚点。**

### 之前报「410 条 supports 缺 strength」，其中 338 条是假的

| 构成 | 数量 | 该不该要 strength |
|---|---|---|
| `ev-N-xxx → N-xxx` | **338** | ❌ **恒为 strong，判定无意义** |
| `EV-规范-* → claim` | 49 | ❌ 错挂（见 claim-evidence-binding）|
| `EV-主体-* → claim` | 23 | ✅ 需要判定 |
| `CL-* → CL-*` | 8 | ✅ 需要判定 |

**「必填」定义过严，产生了 338 条形式主义告警。**

### 修法：relation_types.yaml 加豁免

```yaml
supports:
  payload: [strength]
  payload_exempt:
    mirror: 镜像证据（ev-N-xxx → N-xxx）强度恒为 strong，不需判定
```

**校验时先查 exempt 再查 required**：

```python
if (exempt.get(r["type"]) or {}) and p.get("mirror"):
    continue                    # 豁免，不算缺
if any(p.get(k) in (None, "") for k in required):
    bad += 1
```

### 判据：哪些必填是真必填

| 必填字段 | 是真必填吗 | 理由 |
|---|---|---|
| `cites.ref_title` | ✅ | 说不出引用哪份文件就是空引用 |
| `bounded_by.clause` | ✅ | 说不出哪条就无法判合规 |
| `supports.strength` | ⚠️ **分情况** | 镜像证据恒 strong，判定无意义 |
| `computed_from.rule_id` | ✅ | 说不出算式就是黑箱 |

### 一条铁律

> **「必填」的定义本身要能通过假缺四问的第④问：设计上真的该有吗？**
>
> 338 条告警如果全填 `strong`，等于没判定 —— 形式主义的必填字段是有害的。
