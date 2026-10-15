# Skill · semantic-graph-compilation-skill（SK-15）

## 名称与定位

- **名称**：`semantic-graph-compilation-skill`（Skill ID SK-15）
- **一句话**：将 Entity、Fact、Claim、Evidence、Reasoning、Scenario、Decision 等编译成统一 Semantic Graph。

## 角色

七道工序**第 4 道的收口**：把各抽取通道的节点装配为统一语义图谱（八类节点 + 跨节点引用），是「知识处理」主题与「推演写作」主题的**交接面**。两个专家都绑定。

## 输入

- project_id、document_id、version_id
- 上游 Skill 输出（entities/relations/facts/claims/evidence/reasoning 等）
- 原文或结构化中间结果

## 输出

统一语义图谱 JSON：
- 顶层：project_id、version_id、meta（title/data_cutoff/compiled_at）、items
- items 八类节点：entities、relations、facts、reasoning、claims、evidence、conflicts、validations
- 跨节点引用（relations.from/to、reasoning.inputs/output、claims.deps/evidence、conflicts.involved、validations.claim）必须指向存在的节点 id

## 执行规则

1. 只使用输入中存在或可由明确规则推导的信息，不编造事实。
2. 所有结果绑定 project_id / document_id / version_id。
3. Fact、Claim、Evidence、Reasoning 必须保留来源链。
4. 发现冲突输出冲突状态，不擅自裁决。
5. 不得在没有复用策略的情况下跨项目复制项目专属事实。

## 关系

上游：全部抽取技能；下游：extraction-quality-audit-skill、graph-deductive-writing-skill（输入契约）、instantiate_project（借形来源）。
