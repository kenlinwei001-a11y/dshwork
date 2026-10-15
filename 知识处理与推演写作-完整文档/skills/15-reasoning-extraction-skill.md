# Skill · reasoning-extraction-skill

## 名称与定位

- **名称**：`reasoning-extraction-skill`
- **一句话**：识别公式、规则、多步推导和中间结论，形成 Reasoning 节点及输入输出依赖。

## 角色

七道工序**第 5 道「推演回放」**的语义承载：把推导链结构化（公式/规则/步骤/中间结论），供确定性回放重算与推演写作前向传播。

## 输入

Sentence/Chunk + 已抽取事实（数值来源）

## 输出

- Reasoning 节点：reasoning_id、类型（公式/规则/推导）、narrative_zh（叙述句，供正文直用）
- 输入输出依赖：inputs / outputs（指向 fact 或中间结论）
- 公式表达式（formula/expr，供回放重算）

## 执行规则

- 推导链闭合：每个 output 依赖的 input 必须存在（缺失→UNDEFINED+instruction，缺值守卫）。
- 公式保留可执行形式（供确定性重算比对原值、检出矛盾）。
- 中间结论显式标注「推演结论」及依赖。

## 关系

上游：fact-extraction；下游：provenance-binding-skill、semantic-graph-compilation-skill、graph-deductive-writing-skill（graph_explain 推演链与 narrative_zh 直用）。
