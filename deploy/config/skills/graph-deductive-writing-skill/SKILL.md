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

## 核心工作流

按顺序执行，阶段产出物作为下一阶段的输入。用 todo 工具跟踪阶段进度。

### 阶段 0：载入并校验图谱

- 定位图谱 JSON（用户显式给出，或在工作区检索 `*_semantic_graph.json`）。
- 运行 `python3 scripts/validate_graph.py <graph.json>` 做确定性校验。
- 发现悬空引用、缺失必填字段、重复 id 时，先报告并（在用户确认后）修复图谱，再继续。
- 读取 `meta.title`、`meta.data_cutoff` 作为报告标题与数据截止口径。

### 阶段 1：建立推演计划

- 依据 `references/deduction-patterns.md` 构建依赖图（facts 为叶子，reasoning 为中间，
  claims 为高层），求拓扑序。
- 登记所有带 `conflict` 字段的节点为「污染节点」。
- 生成推演计划：要派生的结论、命中的冲突、要呈现的情景分支。

### 阶段 2：前向推演（派生结论）

- 沿拓扑序正向传播：facts 取值 → reasoning 按 formula 计算 → claims 聚合。
- 口径与单位校验：流量与存量不可直接相减；换算须绑定换算证据。命中冲突的结论降级为「待审」。
- 派生图谱未明示的新结论时，标注为「推演结论」，登记 `(结论文本, 依赖集合, 证据集合, 是否待审)`。
- 冲突一律「待审」呈现，绝不擅自改数字或补口径消除冲突。

### 阶段 3：校验与分层

- 用 `validations` 的 `status`（SUPPORT / PARTIAL_SUPPORT / CONTRADICT / CONTEXT /
  INSUFFICIENT）与 evidence 的 `kind`，为每条结论确定表述姿态（陈述式 / 限定式 / 条件式 / 待审 / 祈使式）。
- 必要时调用 `claim-validation-skill`、`conflict-detection-skill`、`claim-evidence-binding-skill`
  对推演结论做二次校验。

### 阶段 4：溯源写作（生成报告）

- 用 `plate_open`（title 取 `meta.title`）在右侧 Plate 编辑器打开报告，作为**主编辑面**。
- 写作前先做两次「右侧表单面板」交互（见下「交互层」）：
  1. 若 `instantiate` 有 `undefined_notes`，用 `content_open(kind:"spreadsheet")` 打开「遗漏补录表」
     （缺失字段 × 补充值），用户填后 `content_read` 读回，把补充事实追加进 `provided_facts` 重新装配。
  2. 用 `content_open(kind:"spreadsheet")` 打开「章节字数表」（章节 × 字数预算），用户一次性填写，
     读回后把字数注入写作提示词，作为 `plate_edit` 每章篇幅约束。
- 按 `assets/report-outline.md` 骨架逐章写作，用 `plate_edit` 分小批提交（每次提交完整 Slate JSON：
  标题 + 第一段 → 各章节，见 `references/provenance-writing.md`）。
- 遵循 `references/provenance-writing.md`：事实单源、论断级溯源标记（`〔CL3｜R5｜E1,E3〕`）、
  冲突显式「⚠ 待审」框、证据性质分层措辞。
- 每节起草后，调用 MCP 工具 `check_number_consistency(draft_md, facts)` 做数字一致性核对
  （`unbound` 数字、口径存疑一律「待审」，见 `references/provenance-writing.md` 第 6 节）。
- 版式与体裁规范遵循 `workdsh-word-design` skill。
- **定稿后**（用户在 Plate 编辑完成），用 `content_open` 生成 Word 并 `content_export` 导出真实 DOCX
  —— plate 本身不导出 docx，「docx 交付」走 content_* 这条轨（编辑在 plate、交付在 content）。

### 阶段 5：反向回读、二次判断与交付

- 用户在 Plate 编辑（删除/增加/前后调整）后，**手动触发**二次判断（用户说「检查一遍 / 核对 / 二次判断」时）：
  1. `plate_read` 读回最新内容，与上一版 diff，定位改动段落。
  2. `check_number_consistency(draft_md, facts)` 重新核对数字（改数字是否漂移 / 前后不一致）。
  3. 按 `references/provenance-writing.md` 第 5 节逐句回读：判断改动类别（改数字/改结论/增删论述/改建议），
     回写到对应图谱节点。
  4. 重新做前向推演与冲突检查，标注被改动「传染」的下游结论。
- 无法定位来源的改动显式标注「未溯源」，不得假装绑定。
- 定稿后（用户说「导出 / 交付」），用 `content_open` 生成 Word + `content_export` 导出真实 DOCX 交付。

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

**② 章节字数表**（每次写作前）：

| 章节 | 章节名 | 字数预算 |
|------|-------|---------|
| §1 | 执行摘要 | （用户填） |
| §2 | 事实与现状 | （用户填） |
| … | … | … |

用户一次性填写后，读回的字数预算注入写作提示词，作为 `plate_edit` 每章篇幅约束。
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

