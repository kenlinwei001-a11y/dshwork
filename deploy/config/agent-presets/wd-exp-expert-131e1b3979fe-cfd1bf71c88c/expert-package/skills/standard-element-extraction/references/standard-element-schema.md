# 标准要素包（SES）字段规范

本文件定义「标准执行规格」的字段、枚举、ID 与校验规则。所有产物按此 schema 输出 JSON，再由 validator 做确定性校验；人读版（Markdown/表格）从同一份 JSON 渲染，不手工维护第二份。

## 1. 顶层结构

~~~json
{
  "standard_id": "HJ 671-2013",
  "title": "水质 总磷的测定 流动注射-钼酸铵分光光度法",
  "source_fingerprint": { "sha256_12": "0e343ed5c506", "pages": 12 },
  "status": { "published": "2013-10-25", "effective": "2014-01-01", "superseded_by": null },
  "extraction": { "scope": "full", "date": "2026-10-20", "extractor": "standard-element-extraction", "schema_version": "1.0.0" },
  "clause_registry": [],
  "reference_register": [],
  "elements": [],
  "formula_cards": [],
  "procedure_graph": { "nodes": [], "edges": [] },
  "dependency_graph": { "nodes": [], "edges": [] },
  "lab_alignment": [],
  "method_family": [],
  "audit_rule_cards": [],
  "coverage_matrix": [],
  "gaps": []
}
~~~

必填：standard_id、source_fingerprint、clause_registry、elements、audit_rule_cards。
source_fingerprint 至少含文件 SHA-256 前 12 位与页数；同一份文件重跑必须得到同一指纹。

## 2. ID 方案（稳定、可读、可校验）

| 对象 | 格式 | 示例 | 规则 |
|---|---|---|---|
| 标准 | 标准号-年号 | HJ 671-2013 | 与封面一致，空格保留 |
| 条款 | 条款号 | 4.1 / 5.13 / 8.2.1 | 用标准自身的编号，不重编 |
| 要素 | SE-{族}-{条款号}-{序号} | SE-QC-11.2-01 | 同一条款下序号两位补零 |
| 规则 | ARC-{主分类}-{条款号}-{序号} | ARC-C6-11.2-01 | 主分类与 category 一致 |
| 引用 | REF-{序号} | REF-01 | 按首次出现顺序 |
| 锚 | {standard_id}§{clause} p{page} | HJ 671-2013§11.2 p6 | 锚是位置引用，不是身份 |

原则沿用「ID 是身份，锚是位置」：要素/规则 ID 由语义与条款决定，**不随机、不因重排而变**；锚失效标 DANGLING 待审。

## 3. clause_registry（条款登记册）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| clause | string | 是 | 条款号，如 11.2 |
| parent | string/null | 否 | 上级条款号，如 11 |
| heading | string | 否 | 条款标题，如 校准有效性检查 |
| page | int | 是 | PDF 页码（印刷页码另存 printed_page） |
| quote | string | 是 | 原文引文，≤200 字，可检索 |
| modality | enum | 是 | MUST / SHOULD / MAY / MUST_NOT / INFO |
| type | enum | 是 | normative / informative |
| note | string | 否 | 备注（如「图 1 图注」） |

覆盖率要求：所有编号条款都登记，包括「注」；informative 条款也要登记，但可不出要素。

## 4. reference_register（引用登记册）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| ref_id | string | 是 | REF-01 |
| standard_no | string | 是 | GB 11893 / HJ/T 91 |
| title | string | 是 | 标准名称（原文） |
| referenced_by | string[] | 是 | 引用它的条款号 |
| scope | string | 是 | 引用了什么内容（如「砷、铬、硫干扰的消除方法」） |
| status | enum | 是 | PROVIDED / PENDING_UPLOAD / UNRESOLVED |
| affected_clauses | string[] | 是 | 受影响的标准条款 |
| affected_rules | string[] | 是 | 受影响的规则 ID |
| depth | int | 是 | 引用层级，1 为直接引用 |
| request | string | 否 | 给用户的待上传提示语 |

规则：status 非 PROVIDED 时，受影响规则不得被标记为「可完整判定」；待上传项必须出现在 gaps 与交付说明里。

## 5. elements（要素包，SE-12）

通用字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| element_id | string | 是 | SE-{族}-{条款号}-{序号} |
| family | enum | 是 | META/SCOPE/PRIN/SAMP/PROC/APPA/MATL/INTR/CALC/QC/PERF/RISK |
| statement | string | 是 | 原文要求，保留数值与模态 |
| parameters | object[] | 否 | {name, value, unit, tolerance?, op?} |
| obligation | enum | 是 | MUST / SHOULD / MAY / MUST_NOT |
| applicability | string | 否 | 基质/浓度/仪器/批次条件 |
| evidence | string[] | 是 | 应出现的数据、记录或附件 |
| source_layer | enum | 是 | STANDARD / REF_STANDARD / LAB_SOP / QC_PROCEDURE / INSTRUMENT_MANUAL / CONVENTION |
| anchor | object | 是 | {standard, clause, page, quote} |
| origin | enum | 是 | verbatim / derived / convention |
| derive_from | string[] | 否 | derived/convention 必填：由哪些要素或公式推出 |
| related | string[] | 否 | 关联要素 ID |

各族补充字段（仅列关键项）：

- **META**：publisher、published、effective、replaces、replaced_by、drafting_units、verification_units。
- **SCOPE**：matrix[]、determinand、DL{value,unit,condition}、range{low,high,unit,condition}、not_applicable[]。
- **PRIN**：reaction_chain[]、conditions[]、detection{wavelength_nm, cell_mm}。
- **SAMP**：container、preservation、holding_time、temperature、notes。
- **PROC**：step_no、precondition、action、params、completion_criteria、branch、record。
- **APPA**：component、spec、precision、parameter、status_requirement。
- **MATL**：name、formula、grade、concentration、preparation、storage、shelf_life、degas。
- **INTR**：interferent、phenomenon、elimination、boundary、residual_risk。
- **CALC**：formula_id、symbols[]、applicability、rounding。
- **QC**：item、frequency、threshold、on_exceed、record。
- **PERF**：level、indicator、value、unit、source_table。
- **RISK**：risk、trigger、consequence、control。

## 6. formula_cards（公式卡）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| formula_id | string | 是 | F-1 / F-2，与标准式号对应 |
| clause | string | 是 | 如 9.1 |
| expression | string | 是 | 纯文本表达式，如 rho=(y-a)/b*f |
| latex | string | 否 | 便于渲染 |
| symbols | object[] | 是 | {symbol, meaning, unit, dimension} |
| applicability | string | 是 | 适用条件与区间 |
| rounding | string | 是 | 结果表示与修约规则 |
| self_check | object | 否 | {inputs, expected, computed, pass} 用标准数据或分子量反算 |
| anchor | object | 是 | 条款锚 |

符号表必须覆盖公式中每个符号；量纲检查必须通过（两侧同量纲）；不能出现未定义符号。

## 7. procedure_graph / dependency_graph（图）

节点：{id, type, label, clause, params?, evidence?}
边：{from, to, operator, payload}

operator 枚举与含义（graph schema 1.1）：

| 算子 | 方向 | 含义 | 必需载荷 |
|---|---|---|---|
| specifies | 条款 → 要素/规则 | 条款规定了该要素/规则 | 条款锚 |
| checks | 规则 → 字段 | 规则核对哪个报告/过程字段 | doc_type、field、定位策略 |
| gates | 规则 → 结果/批次 | 质控门约束有效性 | 阈值、超限后果 |
| bounds | 规则 → 结果 | 适用边界约束判定 | 区间、适用对象 |
| requires | 步骤 → 设备/试剂/前序 | 执行依赖 | 依赖对象、条件 |
| precedes | 步骤 → 步骤 | 先后顺序 | 顺序号 |
| computes | 公式 → 结果 | 公式产出结果 | 参数、量纲 |
| cites | 条款 → 引用文件 | 规范性引用 | 被引条款/范围 |
| affects | 引用/缺口 → 规则或条款 | 未上传或冲突的影响范围 | 状态、受影响对象 |
| applies | 方法 → 规则集 | 报告声明方法后选规则集 | 方法、版本 |
| contains | 规则集 → 规则 | 规则集成员 | rule_id |
| annotates | 注 → 条款 | 注对条款的补充 | 注 ID |
| invalidates | 失效 → 下游 | 失效传播 | 触发条件、范围 |
| traces | 对象 → 证据/锚 | 证据回指 | 文档类型、字段、锚 |
| aligns | 要求 ↔ 内部文件 | 标准与实验室文件对齐 | 对齐状态 |

每条边必须带 clause 与可执行解释；不能执行的边（纯描述）不进图。节点类型至少支持：clause / note / element / rule / doc_field / reference / method / ruleset / formula / result / gap。

## 8. lab_alignment（实验室文件对齐）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| alignment_id | string | 是 | LA-001 |
| requirement | string | 是 | 要素或规则 ID |
| requirement_text | string | 是 | 标准要求摘要 |
| lab_doc | string | 是 | 内部文件名与编号 |
| lab_doc_type | enum | 是 | SOP / QC_PROCEDURE / INSTRUMENT_MANUAL / RECORD_FORM |
| lab_clause | string | 否 | 内部文件条款号 |
| status | enum | 是 | IMPLEMENTS / STRICTER / LOOSER / CONFLICT / MISSING / EXTRA / PENDING_DOC |
| difference | string | 否 | 差异说明 |
| decision | string | 否 | 按哪个文件判、是否待审 |

PENDING_DOC 表示内部文件未上传；此时规则仍按标准判，并在交付说明中标「内部落地待核」。

## 9. audit_rule_cards（规则卡）

字段与语法见 audit-rule-card-spec.md。本 schema 只约束必填：rule_id、category（C1–C8）、clause、predicate 或 qualitative_check、evidence_required、check_targets、on_missing、source_layer、anchor。

## 10. coverage_matrix（覆盖矩阵）

行 = 条款，列 = 要素数 / 规则数 / 是否可判定 / 缺口 ID。允许「无规则」但必须写明理由（informative 或纯定性）。

## 11. gaps（缺口）

{ gap_id, type, description, affected_clauses[], affected_rules[], request, owner, severity?（不用） }
type 枚举：GAP-REF / GAP-AMB / GAP-DATA / GAP-CONFLICT / GAP-EXTERNAL / GAP-PERF。

## 12. validator 必检项

1. 所有 ID 唯一；要素/规则 ID 前缀与 family/category 一致。
2. 每条 element/rule 有 anchor，且 anchor.quote 能在原文检索命中（允许空白归一化）。
3. 所有 parameters 有 unit；数值型有 value。
4. 公式符号表覆盖 expression 中全部符号；量纲检查通过。
5. reference_register 覆盖第 2 章全部引用；status=PENDING_UPLOAD 的必须出现在 gaps。
6. 规则 category ∈ C1–C8；on_missing ∈ {UNVERIFIABLE, FAIL}；缺失策略不得为空。
7. 每条 normative 条款至少一个要素或登记「无需抽取」理由。
8. 结果表示规则的阈值与 SCOPE 量程端点一致（如 1.00 mg/L）。
9. 同一参数多处出现的数值/单位一致；不一致标 GAP-CONFLICT。
10. quote 与原文完全一致（去空白后），防止模型改写原文。

## 13. 命名与语言

- 数字用半角，单位用原文（mg/L、℃、nm、min、h、%）。
- 化学式与符号保留原文写法（K2S2O8、ρ、γ）。
- 条款标题用标准原文；自拟标题加「（自拟）」。
- 所有输出语言与用户一致；英文仅用于字段名与枚举。
