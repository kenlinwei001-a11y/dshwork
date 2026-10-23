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

### 5. claims — 论断（独立论证对象，非普通文本字段）

```json
{"id": "CL1", "text": "维护后基地有效月产能约35 GWh",
 "claim_type": "conclusion", "type": "结论", "status": "supported",
 "section": "§5", "deps": ["R3"], "evidence_refs": ["E6", "E7"],
 "premise_refs": [], "derived_from": [], "confidence": 0.9,
 "conflict": null, "valid_time": {"start": null, "end": null}}
```

字段分三类（严格区分「输入 / 推演 / 治理」，与抽取契约 `ontology.py` 的 `CLAIM_*_FIELDS` 一致）：

| 类别 | 字段 | 含义 |
|------|------|------|
| 输入 | `id` | 论断 id（`CL*`） |
| 输入 | `text` | 论断原文 |
| 输入 | `claim_type` | 论证类型：fact / hypothesis / inference / conclusion / recommendation |
| 输入 | `type` | 论断性质（旧，向后兼容）：结论 / 判断 / 风险 / 预测 / 因果判断 / 建议 |
| 输入 | `section` | 所属章节 |
| 输入 | `deps` | 依赖，**可引用 facts / reasoning / claims**（如 `["F14"]`、`["R3"]`、`["CL3"]`） |
| 推演 | `status` | 验证状态：unverified / supported / contradicted / verified（**缺省 unverified，不得伪装已证**） |
| 推演 | `evidence_refs` | 证据关联 id 列表（`E*`；旧字段 `evidence` 为其别名） |
| 推演 | `premise_refs` | 前提 claim id 列表 |
| 推演 | `derived_from` | 推导来源 claim id 列表 |
| 推演 | `confidence` | 置信度（number 或 null） |
| 治理 | `valid_time` | 生效时间范围 `{start, end}`（可 null） |
| 治理 | `conflict` | 关联冲突 id（可选） |

`claim_type` + `status` 决定写作姿态：`conclusion`+`supported` 可陈述式；`hypothesis`/`unverified`
须条件式「待验证」；`contradicted` 转冲突待审，不得陈述为事实；`recommendation` 进行动项；
「风险」性质进风险清单。「推演字段」非原始输入，若缺失须由系统产生并标记 `unverified`，不得由模型推断后伪装成用户提供的事实。

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

所有跨节点引用（relations.from/to、reasoning.inputs/output、claims.deps/evidence_refs/premise_refs/derived_from、
conflicts.involved、validations.claim）都必须指向存在的节点 id。`scripts/validate_graph.py`
在写作前对此做确定性检查，发现悬空引用或缺失必填字段即报错，应先修复图谱再写作。


## V2.8 新增字段（本轮实证）

以下字段是 2019ZX054 项目实证后加入契约的。**写作前必须检查，缺了就不能按老口径写。**

### claims 新增 `falsifiable_by`

```json
{
  "id": "CL-结论-01",
  "text": "建设必要性充分：…",
  "claim_type": "conclusion",
  "falsifiable_by": "找到一条证据表明该判断不成立（如必要性不足的反证）",
  "status": "unverified",
  "evidence_refs": ["REF:《中共中央关于制定...》"]
}
```

| 字段 | 必填 | 含义 | 缺了怎么办 |
|---|---|---|---|
| `claim_type` | ✓ | `conclusion` / `recommendation` / `hypothesis` / `inference` | 不能写（无法选句式） |
| `falsifiable_by` | ✓ | 什么能推翻它 | **视为「不是论断，是口号」，不写** |

**实测**：68 个原 judgment 节点复判后只剩 19 条真 claim —— 49 条是 fact（参数、规范转述、编号）。**写作时必须按 claim_type 核实数量，不能照抄旧的 68 条。**

### evidence 新增 `kind`（E0~E6 + hypothesis）

```json
{
  "id": "EV-选址-01",
  "kind": "E0",
  "quote": "西侧为校园绿地，东侧临近现有建筑教育中心…",
  "verifiable": true,
  "survey_date": "unknown",
  "surveyor": "unknown",
  "classify_basis": "场地四至属编制方可复查的现场情况，不是甲方给定值"
}
```

| kind | 含义 | verifiable | 必填附加字段 |
|---|---|---|---|
| `E0` | **编制方踏勘/调查** | true | `survey_date` `surveyor` `basis` |
| `E1` | 客户给定 | false | `provider` `provide_date` `version` |
| `E2` | 规范条文 | true | 标准号 `code` + 条款号 `clause_no` |
| `E3` | 外部公开数据 | true | 发布机构 / 日期 / URL |
| `E4` | 图内派生 | true | `leaf_refs`（可追溯输入） |
| `E5` | 类比工程 | partial | 类比对象 + 可比性 |
| `E6` | 专家判断 | false | 专家身份 + 依据 |
| `hypothesis` | **预测性表述** | — | 不是证据，是 claim 的子类 |

**实测重分配**：31 条原标 E1 的证据，实际是 E0×7 / E1×15 / E3×15 / E4×8 / hypothesis×5。

### bounded_by 新增 `status: 部分可核`

```json
{
  "type": "bounded_by",
  "from": "N-1b1549fc44f9",
  "to": "MC-X-GB50009",
  "payload": {
    "clause": "GB50009-2012 8.3.1 表8.3.1（体型系数）",
    "range_known": false,
    "status": "部分可核",
    "verified_parts": {
      "mu_z": "表8.2.1 B类 49m 插值 ≈1.61 ✅ 可核",
      "w0":   "表E.5 上海 R=50 = 0.55 ✅ 可核",
      "mu_s": "表8.3.1 为图片未转录；1.3 = 迎风0.8+背风0.5 属常规，⚠️ 无法逐项核对"
    }
  }
}
```

**三种状态**：

| `range_known` | `status` | 写作要求 |
|---|---|---|
| `true` | — | 可写「满足 XX 规范 X.X 条」 |
| `false` | 为空 | 只能写「依据 XX，限值待核」 |
| `false` | **`部分可核`** | **拆开写：哪个参数核了、哪个没核** |

### relations 新增因果边类型

```json
{
  "type": "CAUSED",
  "from": "f6c1337ea1c517f29f14fd6a3629accf",
  "to": "6d5791f8-ef5c-4b1d-8a38-006dc7483557",
  "properties": {
    "why": "建筑高度 >50m 属一类高层公共建筑，耐火等级不应低于一级",
    "basis": "项目内实测因果（不是推断）"
  }
}
```

**允许的因果边类型（大小写敏感）**：

```
CAUSES / CAUSED / INFLUENCES / INFLUENCED
PRECEDES / PRECEDENT_FOR / LEADS_TO / LEAD_TO / SUPPORTS / SUPPORT
```

**小写 `causes` 不生效** —— 实测踩过。

### 章节级写作输入（可选）

```json
{
  "section_no": "6.4.2",
  "prompt": "依据脱敏骨架撰写《室外给水排水工程》一节…",
  "project_tags": ["科研","建筑","中型","可研","高层"],
  "facts_count": 23,
  "rules": ["R-最高日用水量","R-排水量"],
  "norm_refs": [{"standard":"GB50555-2010","clause":"表3.1.7","range_known":false}],
  "conflicts": [{"subject":"办公（教师）用水定额","values":["50","35"],"strength":"strong"}],
  "return_contract": "正文 Markdown + node_mentions + new_claims + unresolved"
}
```

**本项目已产出 119 节**（`写作输入/section-prompts.yaml`），可直接投喂。

## 校验

```bash
python scripts/validate_graph.py <graph.json>
```

V2.8 起校验项增加：
- `claim_type` 必须在四类枚举内
- `falsifiable_by` 缺失 → warn（视为口号）
- `evidence.kind` 必须在 E0~E6/hypothesis 内
- `bounded_by.range_known == false` 且 `status != 部分可核` → 写作时禁止说「符合」
