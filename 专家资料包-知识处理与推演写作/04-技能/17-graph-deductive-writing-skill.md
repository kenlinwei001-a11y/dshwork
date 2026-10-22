# 技能：graph-deductive-writing-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | graph-deductive-writing-skill |
| description | 基于语义图谱的推演式分析写作。输入 semantic-graph-compilation-skill 编译产出的语义图谱 JSON（含 entities / relations / facts / reasoning / claims / evidence / conflicts / validations），沿推理链前向推演派生新结论，并把每条论断写成绑定证据与溯源链的 Word 分析报告（.docx）。事实单源存储、跨章节自动传播、冲突以「待审」显式呈现、正文可反向回读为图谱节点。当用户要求「基于图谱的推演写作」「图谱驱动写报告」「把语义图谱写成分析报告」「推演式写作」「graph-based deductive writing」，或提供一份语义图谱 JSON / 本体图谱要求撰写、修改、审校、核查数字前后矛盾或反向回读时，应使用本 skill。上游建图（文档解析、实体/事实/关系抽取、图谱编译）由 document-parsing-skill、fact-extraction-skill、entity-extraction-skill、semantic-graph-compilation-skill 等负责，不在本 skill 范围内；本 skill 是 feasibility-report-edu-research 等特定领域报告的通用引擎。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/graph-deductive-writing-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 8 |
| 体积 | 57.9 KB |
| 被忽略文件 | SKILL.md.bak-cons-1854、SKILL.md.bak-deriv-1852、SKILL.md.bak-eng-1909、SKILL.md.bak-tag-1946、SKILL.md.bak.anchor.20261015175558（编辑器备份/系统文件，不进入副本） |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家、推演写作专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、推演写作专家（expert-a0a771c8b0da）、知识处理专家 副本（expert-131e1b3979fe）、推演式报告写作专家（expert-97703554b311）

## 4. SKILL.md 正文（全文）

~~~markdown
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
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 25666 | dfe891964aee83e4 |
| assets/report-outline.md | 1716 | 8dbb340414cb7920 |
| references/deduction-patterns.md | 3507 | de87999b91a8795d |
| references/historical-asset-reuse.md | 7078 | f0091bd27097356b |
| references/provenance-writing.md | 4083 | e49d7334dd92d100 |
| references/semantic-graph-schema.md | 7267 | 46d22825a88fe8fb |
| references/worked-example.md | 2973 | 3184b24eee62b473 |
| scripts/validate_graph.py | 7027 | e33be69df72fe13c |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/graph-deductive-writing-skill/`（未改写；已用 SHA-256 复算校验）。
