# Skill · knowledge-generalization-skill

## 名称与定位

- **名称**：`knowledge-generalization-skill`
- **一句话**：从历史项目中提取可复用 Ontology、Reasoning Pattern、Claim Pattern、分析框架和规则，同时隔离项目专属事实。

## 角色

资产发布的沉淀通道：把项目图谱中的**通用方法**（本体/推理模式/Claim 模式/框架/规则）与**项目专属事实**分离，前者进可复用资产库，后者留在项目内。两个专家都绑定。

## 输入

历史项目语义图谱 + 项目边界信息

## 输出

- 可复用资产：Ontology 片段、Reasoning Pattern、Claim Pattern、分析框架、规则
- 隔离声明：哪些是项目专属事实（不进通用库）
- 复用血缘（ReuseLineage）

## 执行规则

- 只提炼「可复用」部分（借形不借值：模式留下、数值隔离）。
- 项目专属事实绝不跨项目复制。
- 提炼结果经三质量关口（QG3 可复用性）后方可发布。
- 与「知识≠能力」一致：只有报告只能归纳候选方法（induced）；有代码/配置/执行记录才能登记真实能力（registered）。

## 关系

上游：语义图谱（各项目）；下游：library_publish（发布到历史资产库）、library_find_analog（写新项目时检索复用）。
