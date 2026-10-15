# Skill · extraction-quality-audit-skill

## 名称与定位

- **名称**：`extraction-quality-audit-skill`
- **一句话**：对抽取结果执行结构完整性、证据覆盖、关系合法性、跨项目污染和孤立节点等质量审计。

## 角色

七道工序**第 6 道「质量登记」**的审计通道：对图谱做五维审计，产出待审清单，是 QG2 语义完整性关口与 gate_report 的上游输入。

## 输入

语义图谱（或各抽取通道输出）

## 输出

审计报告：
- 结构完整性（必填字段、类型合法）
- 证据覆盖（Fact/Claim 有无证据、证据有无来源）
- 关系合法性（from/to 存在、type 合法）
- 跨项目污染（项目专属事实混入通用资产）
- 孤立节点（无引用、无来源）

## 执行规则

- 审计项显式列出（节点 id + 问题 + 建议），不静默忽略。
- 结果写 quality 报告，供 gate_check / run_quality_gates 引用。
- 审计不修改数据（只登记）。

## 关系

上游：semantic-graph-compilation-skill；下游：conflict-detection-skill、quality 登记（QG2）、review.py 状态机（draft→validated）。
