---
name: semantic-graph-compilation-skill
description: "将 Entity、Fact、Claim、Evidence、Reasoning、Scenario、Decision 等编译成统一 Semantic Graph。"
---

# Semantic Graph Compilation Skill

## Skill ID
SK-15

## Purpose
将 Entity、Fact、Claim、Evidence、Reasoning、Scenario、Decision 等编译成统一 Semantic Graph。

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

## 关系类型（七族 · 开放词表）

权威定义：`relation_types.yaml`（**单点定义**，可用 MCP `relation_types` 读取）。
关系不是"边"，而是**能承载推理步的对象**；判据：**是否对应一个可执行算子**。

| 族 | 类型 | **必需载荷**（缺即不可判定） |
|---|---|---|
| **A 推理** | derives_from · entails · supports · contradicts · presupposes(=depends_on) · concludes · causes | 算子（operator/strength/prerequisite/conflict_type/mechanism） |
| **B 结构** | part_of · has_part · composes · located_in · temporal | **公理**（`axiom ∈ {sum,containment,membership}`；**sum 仅对可加量成立**） |
| **C 借用引用** | reuses · instantiates · fills · cites · sourced_from · declared_in · transfers_to · generalizes_to · supersedes · scoped_to | **范围** |
| **D 对齐锚定** | same_as · distinct_from · ambiguous_with | 消歧依据 |
| **E 资产治理** | depends_on_asset · gated_by · published_as · impacted_by | 状态与版本 |
| **F 规则**（**超边 n→1**） | computes · judges · selects | 输入/输出洞 + 类型约束 + guard |
| **G 约束** | bounds · requires · recommends · propagates_modality_to | 权威(名+条款+效力)+谓词+值域+模态+强度 |

**三条硬规则**：① 必需载荷缺一不可（缺则不可判定，不得提交）；② **`has_value` 不是关系**（节点字段，已弃用；实测曾占 77%，把 108 条真关系膨胀成 466 条）；③ 不符合七族者**不得丢弃、不得硬塞** —— 记入 `relation_candidates.yaml` 作为候选（抽取只能**归纳候选**，登记是受控动作）。

**扩充机制**：新类型过五条准入【有算子 / 有必需载荷 / 不同义 / 有实例 / 可迁移】；**同义按归约优先作别名**（如 `depends_on` → `presupposes`）；词表版本化，跨项目按版本解释。

**编译期强制（本 skill 的落点）**：
- 入图前逐条校验：**类型已登记**（非同义重复）→ **必需载荷齐备** → **非弃用**；不通过者进 `relation_candidates`，**不入正式关系层**
- 关系层只保留 A/B/F/G 等**可承载推理步**的边；纯属性（`has_value`/`has_attribute`）回归节点字段
- `part_of`/`has_part` 标 `axiom`；`axiom=sum` 时须确认**可加量**，否则改标 `containment`/`membership`
- **F 规则是超边（n→1）**：不得压成二元边；用「规则节点 + 入边 + 出边」建模，否则规则与节点脱钩（实测本项目规则 35 条旁挂 ⇒ 参与推导链的节点仅 4%）
- **G 约束必须同时落 `propagates_modality_to` 边**：否则上限口径派生量会被当成最低要求（客户错误④）


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


## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。

<!-- kp-patch:v1 -->
## 论断级关系词表（7 类扩展）

原 `TEN_RELATIONS`（has_value / has_attribute / instance_of / part_of / causes /
depends_on / supports / contradicts / temporal / located_in）覆盖的是**事实与实体**关系。
论断之间还需要 7 类，否则 `premise_refs` / `derived_from` 字段**无从填充**——
不是不想填，是**没有可填的语义槽**。

| 关系 | 语义 | 端 |
|------|------|----|
| `cites` | 这条结论依据哪条规范/文件 | claim → mandate |
| `restates` | 总论/结论复述各章结论 | claim → claim |
| `causes` | 因果链条 | claim → claim |
| `derives` | 显式推演派生 | claim → claim |
| `precedes` | 论证顺序/前置条件 | claim → claim |
| `quantifies` | 结论与其数值绑定 | claim → node |
| `specializes` | 通则落到本项目 | claim → mandate |

实现：`corpus_pipeline/relations_ext.py`（`CLAIM_RELATIONS` + `derive_expected_relations`）。

**「复述层」必须是节点层，不只是边**：可行性研究报告的「总论」与「结论」按体例是
**全篇论断的复述层**。若该层没有 claim 节点，`restates` 边无从建立，
后果是：①改一处漏三处无法被机检；②「结论章不得出现新数」无法机检。
因此编译时须保证总论/结论章**成层**（有 claim 节点），而不只是补边。



## 图库落地：推入后的三步验证

编译出的图谱最终要落到图库（本项目用 Semantica）。**推入成功不等于可用。**

### 三步验证（缺一不可）

| 步 | 验证什么 | 怎么验 | 不验的后果 |
|---|---|---|---|
| **① 节点数** | 节点/边数是否对上 | `get_graph_summary()` | 漏推不知道 |
| **② 可检索** | 关键词能否搜到节点 | `query_graph(mode=search, query="GB50016")` | **1301 节点推了但全搜不到** |
| **③ 可推理** | 因果/多跳能否跑通 | `get_causal_chain(...)` | 有边但追不出链 |

**实测踩过**：只验了第 ① 步（`node_count: 1310` 对上了），结果 `search_graph("GB50016")` 返回 **0 条** —— 推入时缺 `content` 字段。

### 节点必须有 content 字段

```python
# 错：只有业务字段
{"id": nid, "type": "fact",
 "properties": {"subject": "本项目", "value": "95.04", "unit": "m³/d"}}

# 对：加 content（图库的 search 只索引这个）
{"id": nid, "type": "fact",
 "properties": {"subject": "本项目", "value": "95.04", "unit": "m³/d",
                "content": "本项目 = 95.04 m³/d",
                "label": "本项目"}}
```

**不同图库的索引字段不同**，推送前必须查清：
- Semantica → `content`
- Neo4j → 需要显式建 `CREATE INDEX ON :Node(content)`

### 边的类型必须用图库的枚举

因果边不是随便写个 `causes` 就行：

```python
# Semantica 的 _CAUSAL_TRAVERSAL_TYPES（大小写敏感）
{"CAUSES", "CAUSED", "INFLUENCES", "INFLUENCED",
 "PRECEDES", "PRECEDENT_FOR", "LEADS_TO", "LEAD_TO", "SUPPORTS", "SUPPORT"}

# 我一开始用 "causes"（小写）→ chain 为空
```

### 建因果边的判据

不是所有节点之间都有因果。能建的条件：

| 判据 | 例子 |
|---|---|
| A 的取值决定 B 的判据 | 建筑高度 >50m → 一类高层 → 耐火等级要求变 |
| A 和 B 共同决定同一输出 | 定额 × 人数 → 日用水量 |
| A 是 B 的计算输入 | 总建筑面积 → 建安工程费 |

**不能建**：两条独立冲突、同章节、同主题。**边要带 `why` 说明理由。**

### 一个根因三个表象

```
建筑高度 60 vs 49   ← 根因（可算出 49）
    ├─CAUSED→ 耐火等级 二级 vs 一级
    └─CAUSED→ 消防水箱 18 vs 36 m³
```

**不建因果边，这三个冲突在清单里是并列的，看不出谁先解决。**

### 稀疏度诊断

```
community_count / node_count ≈ 1  → 图极稀疏，大部分节点孤立
```

本项目实测 `1037 / 1310 = 0.79` —— 说明 314 条边只覆盖了不到 300 个节点。

**这不是 bug，是抽取深度的真实反映**：值抽出得多，关系建得少。

### 一条铁律

> **推入 ≠ 可检索，检索到 ≠ 可推理。**
>
> 三步都要验证，只验节点数等于没验。

## 工序（四段式）

**契约**

```json
{"graph": {"required": ["project_id", "items"],
           "items": {"required": ["entities", "relations", "facts", "reasoning",
                                   "claims", "evidence", "conflicts", "validations"]}}
}
```

**执行**

```python
def compile_graph(parts) -> dict:
    g = {"project_id": parts.project_id, "items": {}}
    for col in ITEM_TYPES:
        g["items"][col] = parts.get(col, [])
    # 端点可寻址
    ids = {n["id"] for n in g["items"]["entities"]}
    dangling = [r for r in g["items"]["relations"]
                if r["from"] not in ids or r["to"] not in ids]
    assert not dangling, f"{len(dangling)} 条关系端点不存在"
    return g
```

**门禁 P15 · 编译闭环**

```
端点可寻址 + 无孤儿（或孤儿已分类合理）+ 关系类型闭环
```

**代价（实测）**

```
不校验端点 → 悬空关系 106 条，图查询走不通
新建泛化节点架空真实节点（NX-条款-GB50016 vs NX-条款-006）→ 合并 21 条、删 5 个
图库推入后缺 content 字段 → 1301 节点全搜不到
```
