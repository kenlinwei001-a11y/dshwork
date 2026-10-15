# Skill · provenance-binding-skill

## 名称与定位

- **名称**：`provenance-binding-skill`
- **一句话**：建立对象之间的来源链，使 Decision 可以反向追溯到 Claim、Reasoning、Fact、Evidence、Sentence、Chunk 和 Document。

## 角色

七道工序**第 4/5 道**的溯源通道：把图谱各节点串成完整来源链（build_provenance 的语义面），实现「正文 ↔ 图谱节点 ↔ 证据 ↔ 原文定位」全链可溯。

## 输入

图谱节点（Decision/Claim/Reasoning/Fact/Evidence/Sentence/Chunk/Document）

## 输出

- provenance 链：每节点记录 upstream/downstream 来源关系
- 反向追溯结果：任意节点 → 证据 → 原文定位
- 断链检测（缺失环节显式标记）

## 执行规则

- 来源链只连真实存在的节点 id（validator 校验悬空）。
- 断链不补造，显式标记「来源缺失」。
- 支持跨文档来源（跨项目复用血缘 ReuseLineage）。

## 关系

上游：各抽取技能；下游：conflict-detection-skill、graph-deductive-writing-skill（行内溯源标记 CL3｜R5｜E1,E3）、project_where_written（反向回读）。
