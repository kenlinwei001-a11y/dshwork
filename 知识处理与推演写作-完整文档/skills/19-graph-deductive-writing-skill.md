# Skill · graph-deductive-writing-skill

## 名称与定位

- **名称**：`graph-deductive-writing-skill`
- **一句话**：基于语义图谱的推演式分析写作——沿推理链前向推演派生新结论，把每条论断写成绑定证据与溯源链的 Word 分析报告（.docx）。

## 角色

**「推演写作」主题的核心引擎**。两个专家都绑定；同时是 feasibility-report-edu-research 等特定领域报告的通用引擎。

## 核心主张

正文不是自由写作，而是沿图谱依赖链**前向推演**派生结论，再把每个论断**绑定证据与溯源链**写成文档：事实单源存储、跨章节自动传播、冲突显式待审、客户改稿可反向回读。

## 输入契约

- 输入是 semantic-graph-compilation-skill 的编译产物（语义图谱 JSON，八类节点）。
- 完整字段定义见 `references/semantic-graph-schema.md`。
- 跨节点引用必须指向存在的节点 id。

## 触发条件

- 用户要求「基于图谱的推演写作」「图谱驱动写报告」「把语义图谱写成分析报告」
- 用户提供语义图谱/本体图谱，要求撰写、修改、审校、核查数字前后矛盾或反向回读
- 需要「结论先行、每句可溯源、冲突待审」的 Word 分析报告

不适用：图谱尚未构建（先走建图 pipeline）；非推演性自由写作（用 workdsh-word-design）。

## 关键纪律（与推演写作专家一致）

- 借形不借值、缺值守卫、不许反算、引用即绑定（四条硬约束）。
- 节点类型纪律：quantity 参与运算（核对 unit/caliber）；judgment 只引述不运算；undefined 不当数用。
- 冲突用「⚠ 待审」框原样转述，不裁决。
- 溯源标记行内绑定（CL3｜R5｜E1,E3）；改稿可反向回读（改数字→更新 fact 等）。
- 上游建图由 document-parsing / fact-extraction / entity-extraction / semantic-graph-compilation 等负责，不在本技能范围。
