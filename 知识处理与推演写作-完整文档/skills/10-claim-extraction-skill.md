# Skill · claim-extraction-skill（SK-07）

## 名称与定位

- **名称**：`claim-extraction-skill`（Skill ID SK-07）
- **一句话**：识别判断、结论、风险、预测、因果判断和建议等 Claim，并建立依赖关系。

## 角色

七道工序**第 4 道「本体抽取」**的论断通道。Claim 是推演写作的核心单元——报告的每一条论断都对应一个 Claim 节点，绑定证据与推演依赖。

## 输入

Sentence/Chunk + 已抽取事实

## 输出

- Claim 列表：claim_id、类型（判断/结论/风险/预测/因果/建议）、文本、置信度
- 依赖关系：claims.deps（依赖的 fact/reasoning/其他 claim）
- 证据绑定（经 claim-evidence-binding-skill 判定）

## 执行规则（语义，LLM 结构化 + validator）

- 识别显式论断与隐含论断，标注判断类型。
- 建立依赖链：结论依赖哪些事实与推理。
- 预测/建议与事实分离，不把预测写成事实。

## 关系

上游：fact-extraction / reasoning-extraction；下游：claim-validation-skill、claim-evidence-binding-skill、graph-deductive-writing-skill（正文论断来源）。
