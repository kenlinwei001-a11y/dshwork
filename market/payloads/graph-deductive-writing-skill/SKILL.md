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

- 用 `content_open` 打开 Word 实时文档（`source: "new"` + `title`，不设 `kind`），标题取 `meta.title`。
- 按 `assets/report-outline.md` 骨架逐章写作：执行摘要（结论先行）→ 事实与现状（单源事实表）
  → 推演过程（推理链）→ 情景分析 → 风险清单 → 建议 → 待审事项 → 证据附录。
- 遵循 `references/provenance-writing.md`：事实单源、论断级溯源标记（`〔CL3｜R5｜E1,E3〕`）、
  冲突显式「⚠ 待审」框、证据性质分层措辞。
- 版式与体裁规范遵循 `workdsh-word-design` skill；分小批提交 content_edit，避免一次性倾倒。
- 完成后 `content_read` 复核，`content_export` 导出真实 DOCX。

### 阶段 5：反向回读与交付

- 客户改稿后，按 `references/provenance-writing.md` 第 5 节逐句回读：定位溯源标记，
  判断改动类别（改数字/改结论/增删论述/改建议），回写到对应图谱节点。
- 回读后重新做前向推演与冲突检查，标注被改动「传染」的下游结论。
- 无法定位来源的改动显式标注「未溯源」，不得假装绑定。

## 与既有 skill 的组合

- **上游**（建图，不在本 skill 内）：document-parsing-skill → sentence-segmentation-skill →
  entity/fact/relation/claim/reasoning/evidence-extraction-skill → ontology-resolution-skill →
  semantic-graph-compilation-skill。
- **本 skill 编排**：claim-validation-skill、conflict-detection-skill、claim-evidence-binding-skill、
  provenance-binding-skill 用于推演校验与溯源。
- **下游**：workdsh-word-design（版式与体裁）、content_*（实时写作与导出 DOCX）。
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
- `references/worked-example.md` — PX-2026-001 完整端到端示例。
- `assets/report-outline.md` — 推演式分析报告骨架模板。
