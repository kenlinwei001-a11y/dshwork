---
name: graph-deductive-writing-skill
description: "基于语义图谱的推演式分析写作：输入图谱 JSON（entities/relations/facts/reasoning/claims/evidence/conflicts/validations），沿推理链前向推演派生结论，每条论断绑定证据与溯源链，输出可反向回读的 Word 报告（.docx）。事实单源存储、跨章节自动传播、冲突一律「待审」、客户改稿可反向回读。触发：基于图谱的推演写作/图谱驱动写报告/推演式写作、把语义图谱写成分析报告、或改稿回读与数字矛盾核查时。上游建图由 document-parsing / fact-extraction / semantic-graph-compilation 等 skill 完成。"
---

# 基于图谱的推演写作（Graph Deductive Writing）

## 概述

把一份**已编译的语义图谱**展开为可读、可溯源的推演式分析报告。核心主张：正文不是自由
写作，而是沿图谱依赖链**前向推演**派生结论，再把每个论断**绑定证据与溯源链**写成文档；
事实单源存储、冲突显式待审、客户改稿可反向回读。

## 何时使用

- 输入是 `semantic-graph-compilation-skill` 的编译产物（语义图谱 JSON，含八类节点）。
- 用户要求「基于图谱的推演写作」「图谱驱动写报告」「把语义图谱写成分析报告」。
- **用户直接给出 Word / Excel / PDF / Markdown 的项目材料**（尚未编译成图谱）——
  先执行「阶段 -1：从原始材料建图」，产出 graph.json 后进入阶段 0。
- 用户提供一份语义图谱 / 本体图谱，要求撰写、修改、审校、核查数字前后矛盾或反向回读。
- 需要一份「结论先行、每句可溯源、冲突待审」的 Word 分析报告。

不适用：图谱尚未构建（先走建图 pipeline）；非推演性的自由写作（用 workdsh-word-design 即可）。

## 输入契约

输入语义图谱的完整字段定义见 `references/semantic-graph-schema.md`。要点：

- 顶层含 `project_id`、`version_id`、`meta`（title / data_cutoff / compiled_at）、`items`。
- `items` 含八类节点：entities、relations、facts、reasoning、claims、evidence、conflicts、validations。
- 跨节点引用（relations.from/to、reasoning.inputs/output、claims.deps/evidence、
  conflicts.involved、validations.claim）必须指向存在的节点 id。

> **与 G0「图谱契约」段的区别**：
> 本节管**图谱顶层结构**（有哪些集合、字段名怎么写），
> G0 管**语义约束**（claim_type 必须四类之一、falsifiable_by 必须非空、range_known 三态）。
> 本节答「结构对不对」，G0 答「语义站不站得住」。

## 核心工作流（四段式：契约 / 执行 / 门禁 / 代价）

> **为什么不用自然语言写步骤**：实测「写作要按证据强度选句式」写在散文里，
> 结果 hypothesis 被写成既成事实、`range_known=false` 的数值写成「符合规范」。
> 写成 `validate_graph.py` 断言后，0 错 63 警立刻定位。
> **纪律靠提醒，机制靠退出码。**

---

### 阶段 0 · 载入并校验图谱（已下沉）

**完整步骤见 `references/阶段0-载入并校验图谱.md`（52 行）。**

摘要：读 graph.json → `validate_graph` 查悬空引用/重复 id →
确认八类节点齐全 → 不通过就停，不许边写边补。

### 阶段 1 · 建推演计划（已下沉）

见 `references/阶段1-建推演计划.md`。摘要：列出要推演的命题 → 标注依赖的
reasoning 链 → 确认每条链的 inputs 都有值（缺值先标 UNDEFINED，不许推）。

### 阶段 2 · 前向推演（派生结论）

**契约**

```json
{
  "derived": {"required": ["rule", "result", "inputs", "expr"],
              "inputs": {"items": {"required": ["node", "value"]}}}
}
```

**执行**

```python
def forward(rule, graph):
    """沿 computed_from 前向推演，禁止反算"""
    inputs = {d.name: graph.value(d.node) for d in rule.deps if d.node}
    if len(inputs) < len(rule.deps):
        return None, [d.name for d in rule.deps if not d.node]   # 显式阻塞
    result = eval_rule(rule.expr, inputs)
    return Derived(rule=rule.id, result=result, inputs=inputs, expr=rule.expr), None

assert not any(has_cycle(r) for r in rules), "推演链不得有环"
assert not backward_computed(rule),          "不许反算（用结果倒推输入）"
```

**门禁 G2 · 派生闭环（继承 P11 + 写作增量）**

```
判据继承 P11：要么闭合、要么显式阻塞，不得静默跳过
写作侧额外要求：阻塞的规则，正文必须写出「缺什么」，不许只写「待补」
```

**代价（实测）**

```
18 条规则因缺输入被静默跳过 → 读者以为算过，实际没算
反算（用 95.04 倒推定额）→ 得到自洽但无依据的数
```

---

### 阶段 3 · 校验与分层

**契约**

```json
{
  "validated_claim": {"required": ["id", "claim_type", "falsifiable_by", "evidence_strength"],
                      "evidence_strength": {"enum": ["SUPPORT", "PARTIAL_SUPPORT",
                                                     "CONTRADICT", "CONTEXT", "INSUFFICIENT"]}}
}
```

**执行**

```python
def classify(claim, evidence):
    if any(e in evidence for e in contradicting(claim)):  return "CONTRADICT"
    if all_premises_supported(claim):                     return "SUPPORT"
    if some_premises_supported(claim):                    return "PARTIAL_SUPPORT"
    if evidence:                                          return "CONTEXT"
    return "INSUFFICIENT"

# 必要性推导实测：3/4 前提有依据 → PARTIAL_SUPPORT
# 结论「综上所述…十分必要」只能写「其中第 X 条依据待补」
```

**门禁 G3 · 论断分级**

```
SUPPORT / PARTIAL_SUPPORT 可写成论断
CONTRADICT / INSUFFICIENT 只能写成「待核」，不得写成结论
```

**代价（实测）**

```
CL-必要性-03 无依据，但结论仍写「综上所述…十分必要」
→ 归纳有断点，评审一查即破
```

---

### 阶段 4 · 溯源写作（生成报告）

**契约**

```json
{
  "section_out": {"required": ["no", "markdown", "node_mentions", "unresolved"],
                  "node_mentions": {"description": "正文里 〔节点ID〕 的清单，用于反向回读"},
                  "unresolved": {"items": {"required": ["kind", "what"]}}}
}
```

**执行**

```python
def write_section(sec, plan, graph) -> dict:
    prompt = render_prompt(sec, plan)        # 已产出 119 节提示词
    md = llm(prompt)
    # 数值必须带节点锚点
    for num in numbers_in(md):
        assert f"〔{num.node}〕" in md, f"{num.value} 缺节点锚点"
    # 禁止句式的硬检查
    for c in plan["claims"]:
        if c["claim_type"] == "recommendation":
            assert "建议" in md, "recommendation 未写成建议句"
        if c["claim_type"] == "hypothesis":
            assert ("预计" in md or "若" in md), "hypothesis 写成了既成事实"
    # range_known=false 不许说符合
    for b in plan["norm_refs"]:
        if b["range_known"] is False and b["status"] != "部分可核":
            assert "符合" not in md, "无原文限值却说「符合」"
    return {"no": sec.no, "markdown": md, "node_mentions": extract_ids(md)}
```

**门禁 G4 · 溯源写作**

```python
{"stage": "G4", "gate": "正文可回读",
 "check": "每个数值带〔节点ID〕；recommendation 用建议句；hypothesis 用条件句；"
          "range_known=false 不说「符合」"}
```

**代价（实测）**

```
range_known=false 的 63 条约束 → 若都写「符合规范」，全部站不住
hypothesis 写成既成事实 → 「施工将影响师生出行」应为「若施工组织不当可能影响」
```

---

### 阶段 5 · 反向回读与交付（已下沉）

**完整步骤见 `references/阶段5-反向回读与交付.md`（92 行）。**

摘要：把正文逐段反查回图谱节点 → 检查每条论断是否绑证据 →
产出「正文 ↔ 节点 ↔ 证据 ↔ 原文」四层可追溯清单 → 交付。
**反查不到的内容必须删或标「无依据」**，不许留。

## 五个阶段的依赖与门禁（已下沉）

见 `references/五阶段依赖与门禁.md`。摘要：阶段 0→5 单向依赖，
**后一阶段不许回改前一阶段的输出**；每阶段有独立门禁，不过不进下一阶段。

## 与既有 skill 的组合

- **上游**（建图，不在本 skill 内）：document-parsing-skill → sentence-segmentation-skill →
  entity/fact/relation/claim/reasoning/evidence-extraction-skill → ontology-resolution-skill →
  semantic-graph-compilation-skill。
- **本 skill 编排**：claim-validation-skill、conflict-detection-skill、claim-evidence-binding-skill、
  provenance-binding-skill 用于推演校验与溯源。
- **下游**：workdsh-word-design（版式与体裁）、plate_*（实时编辑）、content_*（DOCX 导出）。
- **领域引擎**：feasibility-report-edu-research 等特定领域报告是本 skill 的领域化实例；本 skill 是通用引擎。

## 边界与禁忌

- **建图边界（已更新）**：本 skill 负责「原始材料 → 结构化事实 → 图谱」这一段的
  **工程化转换**（`doc_facts` / `instantiate_project` / `graph_from_project`），
  见「阶段 -1」。但**不做深度语义抽取**：长段落里的隐性事实、跨段推理、
  专名消歧仍应由 `document-parsing-skill` / `fact-extraction-skill` /
  `entity-resolution-skill` 完成，本 skill 不越界代劳。
- 不自动裁决冲突：conflicts 一律以「待审」呈现，不补数字、不改口径来「凑平」。
- 不捏造事实：只能重组/计算已有事实；派生结论必须能由 formula 反推并绑定证据。
- 不丢弃溯源：回读改稿时不得丢失溯源链，未溯源改动须显式标注。

## 资源清单

- `scripts/validate_graph.py` — 图谱确定性校验（结构 + 悬空引用），写作前必跑。
- `references/semantic-graph-schema.md` — 输入图谱完整字段契约。
- `references/deduction-patterns.md` — 前向推演范式与口径/冲突/情景处理。
- `references/provenance-writing.md` — 溯源写作与反向回读方法。
- `references/historical-asset-reuse.md` — 写新项目时复用历史语料资产（library_* MCP 工具 + 借形不借值）。
- `references/worked-example.md` — PX-2026-001 完整端到端示例。
- `assets/report-outline.md` — 推演式分析报告骨架模板。

<!-- kp-patch:v1 -->
### 返回契约（v1 增补字段）

原契约 4 个字段保留，**增补 1 个必填字段**：

    draft_md:           正文 Markdown；数值一律写 {{node:N-xxxxxxxxxxxx}}（含 node: 前缀）
    node_mentions:      [{node_id, char_span, form}]
    new_claims:         [{text, supports[], evidence[]}]
    unresolved:         [{what, why, need_from_client}]
    unreferenced_nodes: [{node_id, reason}]    # ← 新增，必填

**`unreferenced_nodes.reason` 只能取自固定枚举**（不得自由文本）：

| reason | 含义 |
|--------|------|
| `可省略·明细类` | 设备铭牌参数、财务明细等，按可研深度裁剪 |
| `有意留白·undefined` | 依赖缺失，正文已按 instruction 写定性措辞 |
| `有意并列·冲突项` | 数值冲突，已以「⚠ 待审」并列呈现 |
| `跨章已引` | 在本报告其它章节已引用 |
| `漏引` | **不应出现**；出现即视为装配缺陷 |

**为什么必须填**：门禁 C6/K10 用「defined 且非明细节点 → 成稿引用率 ≥ 95%」判定装配完整性。
没有这张表，机器无法区分「有意省略」与「漏了」——
本项目的实测是 12 个未引用节点中有 3 个是**真漏引**（表格里的数字被散文概括掉了）。

## 一条铁律（已下沉）

见 `references/一条铁律.md`。**核心：正文里每个数都要能反查回图谱节点，反查不到就不许写。**
## 写作前的三个自检（已下沉）

完整自检清单见 `references/写作前的三个自检.md`。**开始写正文前必读**，它列了三个「写完才发现错了」的典型错误。
## 三份专家 skill 的分工边界（已下沉）

完整边界见 `references/三份专家分工边界.md`。一句话：

**建图（knowledge-processing）→ 读包（knowledge-asset-consumption）→ 写作（本 skill）**，
三者不重叠；本文只负责「已编译图谱 → 正文」。

## 资源导航（阶段-1 建图、复用交互、写作深度规则已下沉 references/）

- `references/阶段-1建图.md` — 1 节
- `references/复用与交互.md` — 3 节
- `references/写作深度规则.md` — 13 节