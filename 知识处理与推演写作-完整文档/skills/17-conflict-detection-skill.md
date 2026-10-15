# Skill · conflict-detection-skill

## 名称与定位

- **名称**：`conflict-detection-skill`
- **一句话**：检测数字、时间、实体、Claim 和版本之间的冲突，并输出待审状态而非自动裁决。

## 角色

七道工序**第 6 道「质量登记」**的冲突通道。确定性工具 detect_numeric_conflicts / detect_time_conflicts 给硬冲突，本技能覆盖实体/Claim/版本等语义冲突。两个专家都绑定。

## 输入

图谱（facts/claims/entities/版本信息）

## 输出

conflicts 节点：
- 类型（数字/时间/实体/Claim/版本）
- 描述（原样转述冲突双方）、涉及节点、核实方向
- 状态：一律「待审」（不裁决、不改数字、不补口径）

## 执行规则

- 冲突描述原样呈现双方证据，不偏向任何一方。
- 下游受影响结论同步降级（传染标记）。
- 回放检出（重算与原值不一致）同样进待审。

## 关系

上游：fact/claim/entity 抽取 + 推演回放；下游：graph-deductive-writing-skill（⚠ 待审框呈现）、gate_check（闸门检查冲突未决项）。
