# 语义图谱 Schema（输入契约）

本文件定义「基于图谱的推演写作」所消费的语义图谱 JSON 结构。该结构是
`semantic-graph-compilation-skill` 的编译产物；写作前必须按此契约理解每个字段，
不得臆造字段或字段含义。可用 `scripts/validate_graph.py` 对输入做确定性校验。

## 顶层结构

| 字段 | 类型 | 含义 |
|------|------|------|
| `skill_id` | string | 产出该图谱的 skill 标识 |
| `skill_name` | string | 产出 skill 名称（如 `semantic-graph-compilation-skill`） |
| `project_id` | string | 项目/报告编号（如 `PX-2026-001`） |
| `document_id` | string | 源文档编号 |
| `version_id` | string | 图谱版本（如 `V1.0`） |
| `meta` | object | `title`（报告标题）、`data_cutoff`（数据截止日）、`compiled_at`（编译时间） |
| `items` | object | 八个节点集合，见下 |

## items 八类节点

### 1. entities — 实体

```json
{"id": "BASE", "name": "武汉基地", "type": "Base", "source": "§1"}
```

| 字段 | 含义 |
|------|------|
| `id` | 全局唯一实体 id |
| `name` | 实体名称 |
| `type` | 实体类型（Project / Organization / Base / Workshop / ProductionLine / Customer / Material / Supplier / Carrier 等，由项目 Ontology 定义） |
| `source` | 出处章节标记（`§N`） |

### 2. relations — 业务关系

```json
{"id": "RL1", "from": "ORG", "to": "BASE", "type": "owns", "source": "§1"}
```

| 字段 | 含义 |
|------|------|
| `id` | 关系 id |
| `from` / `to` | 有向关系的起点/终点，**必须指向 entities.id** |
| `type` | 关系类型（owns / has / contains / delivers_to / supplies / consumes / transports_for 等） |
| `source` | 出处章节 |

### 3. facts — 结构化事实（Subject-Predicate-Value-Time-Source）

```json
{"id": "F01", "subject": "A01线", "predicate": "有效月产能", "value": 20, "unit": "GWh/月", "source": "E1", "section": "§2"}
```

| 字段 | 含义 |
|------|------|
| `id` | 事实 id（`F*`） |
| `subject` | 主语 |
| `predicate` | 谓词/属性 |
| `value` | 值（**可为数字或字符串**，如 `20`、`"2 / 4"`、`"2026-08-18 / 36h"`） |
| `unit` | 单位（可为空字符串） |
| `source` | 证据 id（`E*`）或章节标记（`§N`、`§N未索引`） |
| `section` | 所属章节（可选） |

**口径纪律**：`value` 与 `unit` 必须一致；流量（`GWh/月`）与存量（`GWh`、`吨`）不可直接相减。这是推演中最常见的错误来源。

### 4. reasoning — 推理/推导节点

```json
{"id": "R1", "formula": "20 + 16", "result": "36 GWh/月", "desc": "当前有效产能",
 "inputs": ["F01", "F02"], "output": "F03", "section": "§5"}
```

| 字段 | 含义 |
|------|------|
| `id` | 推理 id（`R*`） |
| `formula` | 计算式/规则 |
| `result` | 结果 |
| `desc` | 推导说明 |
| `inputs` | 输入依赖，**可引用 facts 或其它 reasoning**（如 `["R2","F02"]`） |
| `output` | 输出的事实 id，或 `null` |
| `section` | 所属章节 |
| `conflict` | 关联冲突 id（可选，如 `"CF1"`） |

推理节点构成**有向依赖图**：`inputs → reasoning → output`。推演沿此图正向传播。

### 5. claims — 论断（判断/结论/风险/预测/因果/建议）

```json
{"id": "CL1", "text": "维护后基地有效月产能约35 GWh", "type": "结论",
 "section": "§5", "deps": ["R3"], "evidence": ["E6", "E7"]}
```

| 字段 | 含义 |
|------|------|
| `id` | 论断 id（`CL*`） |
| `text` | 论断原文 |
| `type` | 论断类型：结论 / 判断 / 风险 / 预测 / 因果判断 / 建议 |
| `section` | 所属章节 |
| `deps` | 依赖，**可引用 facts / reasoning / claims**（如 `["F14"]`、`["R3"]`、`["CL3"]`） |
| `evidence` | 支撑证据 id 列表（`E*`） |
| `conflict` | 关联冲突 id（可选） |

`type` 决定写作姿态：`结论`可陈述、`预测/情景`必须标注为情景而非既成事实、`风险`进入风险清单、`建议`进入行动项、`判断`须绑定理由。

### 6. evidence — 证据

```json
{"id": "E1", "name": "生产运营月报", "date": "2026-08-31", "page": "页3-5", "kind": "一手"}
```

| 字段 | 含义 |
|------|------|
| `id` | 证据 id（`E*`） |
| `name` | 证据名称 |
| `date` | 证据日期 |
| `page` | 页码/位置 |
| `kind` | 证据性质：一手 / 预测 / 承诺·未入库 / 计划 / 历史 / 协议 |

**证据性质决定论断的置信度**：`一手`证据强于`预测`与`承诺·未入库`；后者只能支撑判断，不能支撑结论性陈述。

### 7. conflicts — 冲突（待审，不自动裁决）

```json
{"id": "CF1", "type": "口径/单位", "severity": "高", "status": "待审",
 "description": "…", "involved": ["F13", "F08", "R6", "CL4"]}
```

| 字段 | 含义 |
|------|------|
| `id` | 冲突 id（`CF*`） |
| `type` | 冲突类型：口径/单位 / 数字 / 时间一致性 / 覆盖完整性 等 |
| `severity` | 严重度：高 / 中 / 低 |
| `status` | 状态，恒为 `待审`（写作时不得擅自裁决） |
| `description` | 冲突说明 |
| `involved` | 涉及的 facts / reasoning / claims id |

### 8. validations — 论断校验结果

```json
{"claim": "CL1", "status": "SUPPORT", "reason": "由R3(19+16=35)推导，依据E6/E7。"}
```

| 字段 | 含义 |
|------|------|
| `claim` | 被校验的 claim id（**validations 节点以 claim 为键，无 id 字段**） |
| `status` | SUPPORT / PARTIAL_SUPPORT / CONTRADICT / CONTEXT / INSUFFICIENT |
| `reason` | 校验理由 |

写作时：`SUPPORT` 可直接陈述；`PARTIAL_SUPPORT` 须带限定；`CONTRADICT` 不得作为事实陈述，须转冲突/待审；`CONTEXT`（建议/行动项）不判定真值。

## 引用完整性

所有跨节点引用（relations.from/to、reasoning.inputs/output、claims.deps/evidence、
conflicts.involved、validations.claim）都必须指向存在的节点 id。`scripts/validate_graph.py`
在写作前对此做确定性检查，发现悬空引用或缺失必填字段即报错，应先修复图谱再写作。
