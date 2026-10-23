---
name: graph-deductive-writing-skill
description: 基于语义图谱的推演式分析写作。输入 semantic-graph-compilation-skill 编译产出的语义图谱 JSON（含 entities / relations / facts / reasoning / claims / evidence / conflicts / validations），沿推理链前向推演派生新结论，并把每条论断写成绑定证据与溯源链的 Word 分析报告（.docx）。事实单源存储、跨章节自动传播、冲突以「待审」显式呈现、正文可反向回读为图谱节点。当用户要求「基于图谱的推演写作」「图谱驱动写报告」「把语义图谱写成分析报告」「推演式写作」「graph-based deductive writing」，或提供一份语义图谱 JSON / 本体图谱要求撰写、修改、审校、核查数字前后矛盾或反向回读时，应使用本 skill。上游建图（文档解析、实体/事实/关系抽取、图谱编译）由 document-parsing-skill、fact-extraction-skill、entity-extraction-skill、semantic-graph-compilation-skill 等负责，不在本 skill 范围内；本 skill 是 feasibility-report-edu-research 等特定领域报告的通用引擎。
---

# 基于图谱的推演写作（Graph Deductive Writing）

## 概述

把一份**已编译的语义图谱**展开为可读、可溯源的推演式分析报告。核心主张：正文不是自由
写作，而是沿图谱依赖链**前向推演**派生结论，再把每个论断**绑定证据与溯源链**写成文档；
事实单源存储、冲突显式待审、客户改稿可反向回读。

## 何时使用

- 输入是 `semantic-graph-compilation-skill` 的编译产物（语义图谱 JSON，含八类节点）。
- 用户要求「基于图谱的推演写作」「图谱驱动写报告」「把语义图谱写成分析报告」。
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

### 阶段 0 · 载入并校验图谱

**契约**

```json
{
  "graph": {
    "required": ["project_id", "version_id", "items"],
    "items": {"required": ["entities", "relations", "facts", "reasoning",
                            "claims", "evidence", "conflicts", "validations"]}
  },
  "claim": {"required": ["id", "text", "claim_type", "falsifiable_by"],
            "claim_type": {"enum": ["conclusion", "recommendation", "hypothesis", "inference"]}},
  "evidence": {"required": ["id", "kind"],
               "kind": {"enum": ["E0","E1","E2","E3","E4","E5","E6","hypothesis","fact"]}},
  "bounded_by": {"required": ["range_known"],
                 "status": {"enum": ["", "部分可核"]}}
}
```

**执行**

```python
# scripts/validate_graph.py（已实现，234 行）
def check_v28_semantics(items):
    for c in items["claims"]:
        assert c["claim_type"] in CLAIM_TYPES,  f"{c['id']} claim_type 越界"
        if not c.get("falsifiable_by"):
            warn(f"{c['id']} 缺 falsifiable_by → 视为口号，不应用")
    for e in items["evidence"]:
        assert e["kind"] in EVIDENCE_KINDS,     f"{e['id']} kind 越界"
    for r in items["relations"]:
        if r["type"] == "bounded_by" and r["payload"].get("range_known") is False:
            if r["payload"].get("status") != "部分可核":
                warn(f"{r['id']} range_known=false → 写作时禁止说「符合」")
```

**门禁 G0 · 图谱契约**

```bash
python scripts/validate_graph.py graph.json
# 退出 0 = 可用；非 0 = 拒绝写作
```

**代价（实测）**

```
不校验 claim_type → 把 hypothesis 写成「将影响师生出行」（应「若…则可能…」）
不校验 range_known=false → 63 条无原文限值的约束被写成「符合规范」
```

---

### 阶段 1 · 建推演计划

**契约**

```json
{
  "plan": {"required": ["sections", "why"],
           "sections": {"items": {"required": ["no", "title", "facts", "rules", "conflicts"]}}}
}
```

**执行**

```python
def build_plan(graph, outline):
    for sec in outline:
        yield {
            "no": sec.no,
            "facts": [f for f in graph.facts if f.section == sec.no],
            "rules": [r for r in graph.reasoning if r.section == sec.no],
            "conflicts": [c for c in graph.conflicts if sec.no in c.involved_sections],
            "claims": [c for c in graph.claims if c.section == sec.no],
            "norm_refs": [b for b in graph.bounded_by if b.section == sec.no],
        }
```

**门禁 G1 · 计划完整性**

```
每节至少有一类内容（facts / rules / claims / conflicts 任一非空）
空节必须标「本节无图谱内容，按体裁写」
```

**代价**

```
不建计划直接写 → 119 节里 49 节无内容可写，产出大量「待补充」
```

---

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

### 阶段 5 · 反向回读与交付

**契约**

```json
{
  "readback": {"required": ["section_no", "node_mentions", "new_claims", "unresolved"],
               "new_claims": {"description": "正文里新出现的判断，需回写图谱或标待审"}}
}
```

**执行**

```python
def readback(md, graph):
    mentions = extract_ids(md)                       # 〔N-xxx〕
    missing = [m for m in mentions if m not in graph.nodes]
    new_claims = detect_new_judgements(md, graph.claims)
    for c in new_claims:
        assert c.get("source_doc"), "新论断必须标来源（第几稿/谁加）"
    return {"node_mentions": mentions, "missing": missing, "new_claims": new_claims}
```

**门禁 G5 · 回读闭环**

```
正文提到的节点必须都存在（否则是臆造）
新论断必须标来源并进待审，不得直接进正式图谱
```

**代价（实测）**

```
客户改稿新增论断不标来源 → 下一轮无法判断「这句是谁加的」
正文引用了不存在的节点 ID → 反向回读失败，溯源链断
```

---

## 五个阶段的依赖与门禁

```
G0 载入校验
    ↓
G1 建计划 → G2 前向推演 → G3 论断分级
                              ↓
                        G4 溯源写作
                              ↓
                        G5 反向回读
```

| 门禁 | 不通过的后果 |
|---|---|
| G0 图谱契约 | 分类错，全文句式错 |
| G1 计划 | 空节大量出现 |
| G2 派生 | 数值无来源，读者以为算过 |
| G3 分级 | 无依据的论断写成结论 |
| G4 写作 | 数值无锚点，不可回读 |
| G5 回读 | 溯源链断，无法审计 |

## 写新项目：复用历史项目资产

当任务是**写一个新项目**（而非沿用已编译图谱）时，先借历史资产再建图，然后才进入上面的
推演写作工作流。完整工具用法与「借形不借值」硬约束见 `references/historical-asset-reuse.md`。要点：

1. `library_find_analog(doc_type, query)` → 找最相似历史语料包。
2. `library_get_asset(package, asset)` → 借形：outline / templates / style / terms / claims / rules / skeleton。
3. `instantiate_project(corpus_dir=best, project_dir, provided_facts, meta)` → 建新项目图库。
4. 进入推演写作（阶段 0–5）。

这四个 `library_*` 工具由 `kp-library` MCP server 提供（知识处理专家的工具层，按域拆分的 5 个 MCP 之一）；前置条件是
`kp-library` 已连接且历史语料资产库已就绪。**借形不借值**：可继承结构与规则，绝不继承数值/单位/
实体/结论；新项目事实只来自用户提供的 `provided_facts`。

## MCP 工具分布（5 组，取代旧单一 kp-mcp）

本 skill 用到的 MCP 工具按权限域分布在 5 个 MCP：

- **kp-processing**（写作期取骨架/节点/证据）：graph_get_node / graph_query / graph_explain / graph_why / graph_impact / corpus_search / corpus_get_chunk / corpus_get_skeleton / corpus_where_used / evidence_get
- **kp-assembly**（建图/组包/闸门/查数/验证）：schema_diff / decide_reuse / instantiate_project / build_work_package / gate_check_draft / check_number_consistency / check_requirements / sensitivity_analysis / validate_shacl / project_where_written / wp_get_facts
- **kp-library**（历史资产复用）：library_list_packages / library_search / library_find_analog / library_get_asset / library_status / library_promote / library_publish
- **kp-semantic**（语义对齐，可选）：resolve_concept / ossie_import / ossie_export / semantic_classify / ontology_export / ontology_import
- **kp-reserved**（预留，一般不调用）：semantic_search / asset_rerank / solve_constraint / graph_db_query / store_object / llm_invoke

## 交互层：右侧表单面板（补录 + 字数）

写作期需要用户交互的两处，用右侧 `content_open(kind:"spreadsheet")` 打开独立表单面板（Excel 表格），
用户填写后 `content_read` 读回：

**① 遗漏补录表**（`instantiate` 返回 `undefined_notes` 非空时）：

| 缺失字段 | 含义 / instruction | 补充值 | 单位 |
|---------|-------------------|-------|------|
| （每个 undefined 节点一行） | 缺值守卫的 instruction | （用户填） | （用户填） |

用户填完补充值后，把「缺失字段 → 补充值」追加进 `provided_facts`，**重新跑 `instantiate_project`**
（缺值守卫消除，原本 UNDEFINED 的派生节点变为可计算）。

**② 章节字数表**（每次写作前）—— **按章节调整目标字数（用户可自定义）**

**表的 7 列**（由后端生成，界面原样展示；`默认字数(实测)` 是事实列**不得改**）：
`#` · `章节路径` · `默认字数(实测)` · **`目标字数(可改)`** · **`角色(可改)`** · `提示词摘要` · `来源`

| # | 章节路径 | 默认字数(实测) | 目标字数(可改) | 角色(可改) | 提示词摘要 | 来源 |
|---|---|---|---|---|---|---|
| 1 | 总论 / 项目概况 | 392 | 392 | 科研建筑可行性研究编制工程师（可行性研究） | 先给依据再推导 | default(实测) |
| 6 | 学校简介 / 学科体系 | 978 | 1500 | … | … | user |
| … | …（共 N 行，覆盖章/节/子节三级） | | | | | |

**两段式后端动作**（确定性，零 LLM）：
```bash
# 生成表（供 content_open 打开为界面表单）
python build/s24_set_section_budget.py --emit-table <表文件>
# 回读用户编辑后的表（content_read 的结果）⇒ 写 section_budget.user.yaml
python build/s24_set_section_budget.py --ingest <表文件>
```

**数据与优先级**：
```
style/section_budget.user.yaml   ★ 用户自定义（**优先**；留空/删除即回默认）
style/section_budget.yaml        默认 target_chars = **知识抽取阶段实测值**
                                  （target_source: default(抽取阶段实测)）
```
**⇒ 用户未调整 ⇒ 沿用抽取阶段实测值 ⇒ 无需扩写**（产出 = 抽取内容的重组，确定性）。

**调整后的生效链（必须按序）**：
```
① s24 --emit-table → 界面编辑 → content_read → s24 --ingest    ⇒ 写 section_budget.user.yaml
② build/s22_inject_section_contract.py                         ⇒ 注入提示词
   （注入 target_chars(汉字) + expand_by + role(已填充) + operator + 不变量）
③ build/s23_evidence_expand.py                                 ⇒ 按新目标执行
   · 目标 > 实测 ⇒ **受预算约束的证据驱动扩写**：
       每个新增句子须可追溯到给定证据（〔E编号〕标注）；
       追溯不到的句子**剔除**并在 unbound_removed 留因；含禁用词 ⇒ validator 失败
   · 目标 < 实测 ⇒ 压缩（只保留有证据支撑的内容）
④ 阶段 4 其余步骤（plate_edit 逐章写作 / check_number_consistency / content_export）
```

**纪律**：字数口径 = **汉字数**（与"去空白字符数"不同）· 扩写来源仅限「缺口检索台账」与
「原文已有依据的论证展开」，**不得引入新事实** · 无证据不写（不静默、不编造）。
字数只是**提示词参数**，不是业务事实，不进入图谱。

## 与既有 skill 的组合

- **上游**（建图，不在本 skill 内）：document-parsing-skill → sentence-segmentation-skill →
  entity/fact/relation/claim/reasoning/evidence-extraction-skill → ontology-resolution-skill →
  semantic-graph-compilation-skill。
- **本 skill 编排**：claim-validation-skill、conflict-detection-skill、claim-evidence-binding-skill、
  provenance-binding-skill 用于推演校验与溯源。
- **下游**：workdsh-word-design（版式与体裁）、plate_*（实时编辑）、content_*（DOCX 导出）。
- **领域引擎**：feasibility-report-edu-research 等特定领域报告是本 skill 的领域化实例；本 skill 是通用引擎。

## 边界与禁忌

- 不负责建图/抽取：输入必须是已编译的语义图谱；图谱缺失时告知用户先走建图 pipeline。
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


## 客户改稿：diff → 分类 → action（写作期回读协议）

**核心**：`ID 是身份，锚是位置`。**位置变了不改 ID；文本变了才动语义对象。**
分类**零 LLM、可复现**（工具承载：`change_classify.py`，输出 `changes[{action,id,anchor_before,anchor_after,…}]`）。

| diff 形态 | 锚映射 | **action** | **ID 处理** |
|---|---|---|---|
| 位置变了、内容相同 | 同一锚 | **move** | ★ **不分配新 ID，只改 anchor** |
| 内容新增、旧稿中不存在 | 无 | **add** | 分配**新** ID（状态 draft/candidate） |
| 内容消失、新稿中不出现（且非被搬走） | 锚失效 | **delete** | 标 deprecated，**ID 不回收** |
| 数值变 | 同一锚 | **edit_number** | ID 不变；更新 fact 并**重算依赖** |
| 文本变、数值未变（相似度低） | 同一锚 | **edit_claim** | ID 不变；复查 `premise_refs`/`derived_from`/证据 |
| 归一化后相同（相似度高） | 同一锚 | **edit_wording** | 不动图谱 |
| 无法配对 | 无锚可依 | **untraced** | **显式标注「未溯源」，不得默认归因** |

**每条 change 的后续**：
- `move` / `edit_number` / `edit_claim` ⇒ `need_replay: true` ⇒ **重放受影响的推演链与叙述顺序**，并把传染到的下游结论标注出来
- `delete` ⇒ 其 `premise_refs`/`derived_from` 的下游**同步降级**（依赖它的结论转为待审）
- `add` ⇒ 新对象只入 draft/candidate，**过校验后才进正式图谱**；须绑证据
- `untraced` ⇒ 列进 `unresolved`，向客户**明确列出**，不得静默吸收

**diff 的确定性判据**：用**结构 diff（difflib）**判"多了/少了/变了"，用**锚**判"是同一对象的移动还是新对象"——
**不是**按位置比对（位置本身最不可靠）。

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



## 数值推演：沿 computed_from 反查计算链

### 输入里必须有的

语义图谱的 relations 里要有 `computed_from` 边（知识处理侧产出）。没有的话：

```
图谱只有「最高日用水量 = 95.04」
→ 写作时无法说明这个数怎么来的
→ 审稿问「95.04 依据是什么」时只能回指原文，无法展示计算
```

### 怎么用

**① 正文写数值时，附计算依据**

```
本项目最高日用水量为 95.04 m³/d〔N-c67295c8a345〕，
由科研学生用水 1800 人×40 L/生·日、办公用水 288 人×50 L/人·日，
按未预见系数 10% 计取（规则 R-最高日用水量）。
```

**② 复算校验**：沿 computed_from 拿到全部输入值，代入 expr 重算，与原文值比对

```python
# 输入：N-d33295e7e784 = 1800, N-3f1810ee3a33 = 40, ...
# expr: round(({人数}*{定额}+...)/1000*(1+{系数}/100), 2)
# 算出 95.04 == 原文 95.04  → 链条可信
# 算出 ≠ 原文 → 标为待审，不得直接引用
```

**③ 冲突归因**：两个章节的同一个数不一致时，沿链看是**输入不同**还是**公式不同**

```
6.4.2 的 95.04 vs 7.2.2 的 1.74万m³/年
  → 沿 computed_from 查：是不同口径（日 vs 年），不是错误
```

**④ 换项目重算**：只替换 computed_from 指向的输入节点，输出值全部重算，不要手改结果

### 三条铁律

| 铁律 | 说明 |
|---|---|
| 不许绕过链 | 正文里的数值必须能沿 computed_from 找到 rule_id 与全部输入 |
| 不许反算 | 从结论倒推中间量（如已知 95.04 反推 1800 人）视为无效 |
| 缺链即标注 | computed_from 缺失的值，正文写「计算依据待补」并挂缺口，不得写成算出来的 |

### 和 derives_from 的分工

- `computed_from` → 数值怎么算的（可复算、有公式）
- `derives_from` → 论断怎么推的（有推理规则、无公式）

混用会导致：写作时拿不到公式（把数值计算记成论断推导），或审计时找不到推理依据。


## 合规表述：bounded_by 的 range_known 决定能不能说「符合」

### 判据

写「符合规范」「满足要求」之前，先沿 `bounded_by` 检查：

```
range_known == true  且  取值落在 [lower, upper] 内
    → 可以写「满足 XX 规范 X.X 条要求」

range_known == false
    → 只能写「取值 16㎡/人，依据 建标191-2018 相关指标，限值待核」
    → 禁止写「符合规范」
```

### 反例（本项目真实情况）

```
图谱里：N-7c3d781cf6f1(18040㎡) --bounded_by--> 建标191-2018 人均面积指标
        payload.range_known = false
        payload.note = "本次未取到条款限值原文，不得据此判定符合规范"

❌ 错误写法：本项目科研人员用房人均 16㎡/人，符合建标191-2018 要求。
✅ 正确写法：本项目科研人员用房人均 16㎡/人，取值参考建标191-2018 相关指标；
             该条款限值原文尚未取到，合规性待核。
```

### 三类别混

| 关系 | 给写作提供什么 |
|---|---|
| `computed_from` | 数值的计算过程（可复算） |
| `bounded_by` | 数值的合规边界（能否说符合） |
| `cites` | 论述的文件依据（不判数值） |

缺 `bounded_by` 时：不知道边界 → 一律不写「符合」。


## 工程章节写作：每个数都要能说出"怎么来的/合不合规"

### 三类数值的写法

| 数值来源 | 写法 | 例子 |
|---|---|---|
| 推演得出（有 computed_from） | 数值 + 计算式 + 规则号 | "冷负荷 2473 kW（建筑面积 18319 ㎡ × 135 W/㎡）" |
| 受约束（有 bounded_by） | 数值 + 条款 + 状态 | "室外计算干球温度 34.4℃（依 GB50736 附录A，现行版本待核）" |
| 两者都无 | 明写"设计给定"+ 缺口 | "总计算负荷 952 kW 为设计给定值，计算过程原文未列" |

### 禁止

- ❌ 只写结果不写算式："冷负荷 2473 kW"（读者无法验证）
- ❌ 把推导值当原文引用：`{{node:N-ch6-xxx}}` 是推导来的，不是原文写的
- ❌ 设计参数不挂规范："夏季空调 34.4℃"（没说依据哪版规范）

### 覆盖率自查

写完一章，数一下：

```
本章出现的数值 N 个
其中能给出"计算式或条款依据"的 M 个
M / N 就是这章的可审计度 —— 低于 50% 说明图谱关系没建全，
不要用文字去补（那样更不可信），回上游补 relation。
```

### 第六章实测（可作为对照基线）

```
118 个数值节点
  15 个有推演输出（2473 kW 冷负荷 / 288 m³ 消防水量 / 1980 kW 设备产能 …）
  23 个被用作输入（18319 ㎡ / 135 W/㎡ / 40 L/s …）
  40 个受规范约束（气象参数 / 荷载 / 耐火等级 …）
  44 个孤立（设备铭牌 / 建筑尺寸 / 缺明细 / 只给结果）
覆盖率 63%
```


## 找依据：先按标签筛条款，别按章节猜

### 顺序

```
① 看数值节点的 primary_tag（专业域.主题）
② 沿 bounded_by 找它挂的条款
③ 若没挂上，用 tag_query 按同标签检索公共库
④ 同标签但主题不同 → 不是同一件事，不要硬挂
```

### 例子：写抗震段落

```
节点 N-25ae699e50ec   设计基本地震加速度 = 0.1g
     primary_tag = 结构.地震参数

查 tag_query(domain="结构", topic="地震参数")
     → GB50011-2010 附录A-3「烈度 7 度 / 加速度 0.10g / 第一组：上海(…)」

正文写：本项目设计基本地震加速度 0.10g，抗震设防烈度 7 度，
       设计地震第一组（GB50011-2010 附录A）。
```

### 反例

```
❌ 因为节点在 §6.3.2「主要荷载取值」，就把全章 8 个值都挂到「抗震设防分类」
   —— 那一章里还有风荷载、雪荷载，不是一回事
✅ 逐值看 primary_tag：风荷载体型系数→结构.荷载；0.1g→结构.地震参数
```

### 报表里呈现项目标签

写报告时把项目标签写在文首，读者才知道这是什么类型的项目：

```
项目标签：科研 · 建筑 · 中型 · 可研 · 高层 · 抗震 · 消防
```

同类项目对比时，用「同用途 + 同类型 + 同规模」筛出可比案例。


## 论断强度：claim_type 与 falsifiable_by 决定怎么写

V2.4 起 claim 必须带 `claim_type`（四类）与 `falsifiable_by`（什么能推翻它）。
写作时按类型选句式，**不能所有论断都用「充分/合理」**。

| claim_type | 含义 | 写作句式 | 禁用 |
|---|---|---|---|
| `conclusion` | 归纳结论 | 「综上，…（依据前 N 条）」 | 不许无前提的「显然」 |
| `recommendation` | 建议 | 「建议…（条件：…）」 | 不许写成已定事项 |
| `hypothesis` | 预测 | 「预计…（前提：…）」「若…则…」 | **不许写成既成事实** |
| `inference` | 因果推理 | 「由于…，因此…」 | 不许因果倒置 |

### falsifiable_by 是写作的「证据检查清单」

```
claim.falsifiable_by = "找到一条证据表明该判断不成立（如必要性不足的反证）"
    → 写作时必须能说出「我查过了，没找到反证」或「有反证，见 X」
    → 说不出的，这条论断要降级或删

claim.falsifiable_by = "实际结果与预测不符"
    → hypothesis 类，必须写清「前提假设」与「若前提变化会怎样」
```

### 本项目实例（19 条 claim）

```
CL-结论-01  [conclusion]     建设必要性充分：…
             falsifiable_by: 找到一条证据表明该判断不成立
             → 写作时要能列出 4 条必要性前提 + 各自依据（已有 3/4）

CL-建议-01  [recommendation] 建议有关部门尽早批复
             → 不能写成「本项目将获批复」

CL-风险-02  [hypothesis]     施工车辆可能影响师生出行
             → 必须写「若施工组织不当则…」，不能写「将影响」
```

## 证据等级：E0~E6 决定这条论断能不能写

V2.6 起证据分七级（原 E1~E6，新增 E0）。写作时按等级判断可信度。

| 等级 | 含义 | 可核验 | 写作要求 |
|---|---|---|---|
| **E0** | 编制方踏勘/调查 | ✔ | 注明「经现场踏勘」「经调查」 |
| **E1** | 客户给定 | ✘ | **必须注明提供方与日期**；关键项要签认 |
| **E2** | 规范条文 | ✔ | 必须带标准号 + 条款号 + 版本 |
| E3 | 外部公开数据 | ✔ | 注明发布机构/日期/URL |
| E4 | 图内派生 | ✔ | 注明算式与输入（可复算） |
| E5 | 类比工程 | 部分 | 注明类比对象与可比性 |
| E6 | 专家判断 | ✘ | 注明专家身份与依据 |

### 写作时的三条硬规则

```
① E1 没写提供方的 → 不能写成「据甲方提供」，只能写「据项目资料」
② E2 没给标准号的 → 不能写「符合规范」（见下节「模糊引用」）
③ E5 没有可比性说明的 → 不能写「参照同类项目」当依据
```

### 本项目实例（470 条证据重分级后）

```
E0  7 条   场地四至、现状描述、措施方案（原误标 E1）
E1 15 条   校内决议、规划、财务数据（原 31 条）
E2 59 条   规范条文
E3 15 条   统计年鉴、公开数据
E4  8 条   面积汇总、造价合计（原误标 E1）
E5 16 条   类比工程
E6  2 条   专家判断
hypothesis 5 条  预测性表述（原误标 E1）
```

**误标 E1 的 16 条，写作时必须改口径。**

## 模糊引用：不能只写「符合规范」

V2.6 新增扫描：只写「基于 GB」「符合规范」不给编号的，是真缺陷。

### 判据

```
写了「符合规范/相关规范/规范要求」但没给标准号 + 条款号
    → 不能作为合规依据
    → 必须补编号，或改写为「依据某标准，限值待核」
```

### 本项目实测 4 条真缺陷

```
§7.3.3  「风量的选取满足相关规范的要求」          ← 哪个规范？
§7.3.3  「风量耗功率Ws符合规范要求」              ← 哪条？
§9.3.2  「风量的取值标准符合相关规范的规定」      ← 哪个？
```

**排除 44 处误报**（警示语 29 / 同句有编号 8 / 后接书名号 4 / 规范内部互引 3）。

### 写作时的处理

```
遇到模糊引用：
  ✗ 照抄「满足相关规范要求」
  ✓ 「按《XX规范》GBxxxx-20xx 第 X.X 条（条款原文待核）」—— 若确实不知道是哪条，写「相关规范要求，具体条款待补充」
```

## 部分可核：比 range_known 二值更细的状态

`range_known` 只有 true/false，但实际有第三种：**部分参数可核、部分不可核**。

### 本项目实例（风荷载体型系数 1.3）

```yaml
payload:
  range_known: false
  status: 部分可核
  verified_parts:
    mu_z: "表8.2.1 B类 49m 插值 ≈1.61  ✅ 可核"
    w0:   "表E.5 上海 R=50 = 0.55    ✅ 可核"
    mu_s: "表8.3.1 为图片未转录；1.3 = 迎风0.8+背风0.5 属常规，⚠️ 无法逐项核对"
```

### 写作句式

```
✗ 「风荷载体型系数取 1.3，符合 GB50009 要求」
✓ 「风荷载体型系数取 1.3（迎风 0.8 + 背风 0.5），属封闭式矩形平面建筑常规取值；
   风压高度变化系数按表8.2.1 B类 49m 取 1.61、基本风压按表E.5 上海取 0.55；
   **体型系数表8.3.1 原文为图示，逐项核对待补**」
```

**「部分可核」要拆开写清哪个核了、哪个没核。**

## 因果链：一个根因三个表象，写作要按根因组织

V2.7 起可用 `semantica_causal_chain` 追因果。

### 本项目实测链条

```
建筑高度 60m vs 49m   ← 根因（可算出 49）
    ├─CAUSED→ 耐火等级 二级 vs 一级
    └─CAUSED→ 消防水箱 18 m³ vs 36 m³
```

### 写作时的组织方式

```
✗ 三个冲突并列写（读者看不出先解决哪个）：
   「本项目存在三个待审：建筑高度、耐火等级、消防水箱」

✓ 按根因组织：
   「本项目建筑高度两处口径不一致：§6.2.2 写 60m，按 §6.2.4 的 12层/5m/4m 计算为 49m。
    该差异连带影响两项判定：
      · 若按 60m（>50m）→ 属一类高层公共建筑 → 耐火等级不应低于一级（现填二级）
      · 若按 49m（≤50m）→ 属二类高层 → 耐火等级二级成立、消防水箱 18m³ 成立
    建议先核定建筑高度，再定另两项。」
```

### 判定条件

**只有存在 `CAUSED` / `INFLUENCED` 边时才这么写**，不能凭主题相似自己编因果。

## 写作提示词：119 节已经生成，直接用

V2.2 起产出 `写作输入/section-prompts.yaml`（119 节），每节提示词含六块：

| 块 | 内容 |
|---|---|
| 项目标签 | 科研·建筑·中型·可研·高层·抗震·消防… |
| 篇幅参考 | 原文 N 字符 / M 切片，据此控制详略 |
| **事实清单** | N 条，每条带 `描述 + 变量标签 + 用途 + 约束 + 节点ID` |
| **算式** | 规则的可执行表达式，要求写作时复算 |
| **规范约束** | 带 `range_known`，明确「不得说符合」 |
| **待审冲突** | 该章涉及的，明确「不得裁决、不得两值并存」 |

### 用法

```
取 section-prompts.yaml 里对应章节的 prompt
→ 投喂写作模型
→ 返回 Markdown 正文（数值写〔节点ID〕引用）+ node_mentions + new_claims + unresolved
```

**提示词里的节点 ID 是锚点，正文里必须保留** —— 这是可反向回读的前提。

## 五个 Semantica 工具在写作期的用法

| 工具 | 写作期用途 |
|---|---|
| `semantica_query(mode=search)` | 模糊找「和这个话题相关的所有节点」，比 grep 全 |
| `semantica_query(mode=neighbors, depth=2)` | 找「依赖这个数值的所有节点」，判断影响面 |
| `semantica_query(relationship_types=[bounded_by])` | 只抽合规约束，写合规段落用 |
| `semantica_causal_chain` | 找冲突根因，按根因组织段落 |
| `semantica_precedents` | 找同类冲突以前怎么处理的，定写作口径 |
| `semantica_analytics` | pagerank 找最被依赖的节点，决定详略 |

### 三个坑（写作时容易踩）

```
① ID 必须完整 32 位（前缀匹配不上）
② 因果边类型必须 CAUSED/INFLUENCED（小写 causes 无效）
③ scenario 为 None 的 decision 只能用 UUID 定位
```

## 一条铁律

> **写作不是「把图谱翻译成中文」，而是「按证据强度选择句式」。**
>
> claim_type 决定句式（结论/建议/预测/推理）
> 证据等级决定可信度（E0~E6，E1 缺提供方要改口径）
> range_known 决定能不能说「符合」（false 只能说「待核」）
> 部分可核要拆开写（哪个核了、哪个没核）
> 因果链决定段落组织（按根因，不按表象并列）


## 写作前的三个自检（V2.9）

这三个自检对应上游 77% 假缺率的教训 —— **如果上游报了假缺，写作时会照着假缺写。**

### 自检一：引用的每个「缺」是否带 searched 证据

```
✗ 提示词说「本章缺 X 依据」→ 直接写「依据待补」
✓ 先查缺的 why_real 字段：搜过节点表吗？搜过原文吗？查过量纲吗？
```

**实测**：上游报「关系缺证据 190 条」，实际只有 2 条真缺。
如果照 190 条写，正文会有 188 处无谓的「待补」。

### 自检二：数值是否复算过

```
✗ 照抄图谱里的 value
✓ 用 expr 复算一遍，与图谱比对
```

**实测**：

```
R-总投资构成 = 11188+1171+618+55 = 13032 ✓
若绑定错（10135 招标估算）= 11979 ✗ 差 1053
```

**写作时复算，能发现上游的绑定错误。**

### 自检三：冲突是否已找到根因

```
✗ 「本项目存在三个待审：建筑高度、耐火等级、消防水箱」
✓ 先跑 semantica_causal_chain，看有没有 CAUSED 边
```

**实测**：三条冲突共用一个根因（建筑高度 60 vs 49），
按根因写能让读者知道**先解决哪个**。

### 一条铁律

> **上游报的缺，写作时要复核；上游报的数，写作时要复算。**
>
> 不全信上游 —— 因为上游也会假缺（实测 77%）。

## 三份专家 skill 的分工边界

本项目涉及三个 skill，容易混：

| skill | 管什么 | 不管什么 |
|---|---|---|
| **knowledge-processing** | 从原始文档到语义图谱（七道工序） | 不管怎么写报告 |
| **standard-regulation-extraction** | 外部规范文件到条款库 | 不管项目内稿件 |
| **graph-deductive-writing-skill** | 图谱到 Word 报告（推演写作） | 不管建图 |
| **feasibility-report-edu-research** | 高校科研用房可研的**体裁规范** | 不管建图与推演 |

### 什么时候用哪个

```
拿到 docx → knowledge-processing（建图）
要引标准 → standard-regulation-extraction（建条款库）
有图谱要写报告 → graph-deductive-writing-skill（推演写作）
写的是高校科研用房可研 → 追加 feasibility-report-edu-research（体裁与法定章节）
```

### 共享的判定标准（必须一致）

| 标准 | 定义在 | 谁要用 |
|---|---|---|
| `claim_type` 四类 | claim-extraction | claim-validation / writing / feasibility |
| 证据 E0~E6 | evidence-extraction | writing / feasibility |
| `range_known` 三态 | provenance-binding | writing / feasibility |
| 关系 14 类 | knowledge-processing 的 `relation_types.yaml` | 全部 |

**改一处必须同步，否则口径不一致。**

### 实测踩过的口径不一致

```
上游 claims.yaml 19 条（复判后）
但某处还写着 68 条（复判前）→ 写作时按 68 条算，多写 49 条 fact 当论断
```

**共享判定标准必须有单一真理源，且改动时全链同步。**
