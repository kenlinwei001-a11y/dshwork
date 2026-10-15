# Skill · claim-validation-skill（SK-12）

## 名称与定位

- **名称**：`claim-validation-skill`（Skill ID SK-12）
- **一句话**：验证 Claim 的证据支持、时间一致性、事实依赖、推理完整性和语义范围。

## 角色

七道工序**第 6 道「质量登记」**的 Claim 级验证通道：五维验证，产出验证标记（validations），供闸门与审计使用。

## 输入

Claim + 依赖事实/推理 + 证据

## 输出

五维验证结果：
- 证据支持（与 claim-evidence-binding 五级一致）
- 时间一致性（Claim 时点与事实时点不冲突）
- 事实依赖（deps 完整、无悬空）
- 推理完整性（推导链闭合）
- 语义范围（无过度泛化/偷换口径）

## 执行规则

- 每维输出通过/不通过 + 理由；不通过保留 unverified，不升级为事实。
- 时间冲突、口径偷换转冲突/审计通道。
- 校验结果写 validations 节点，供 gate_check 引用。

## 关系

上游：claim-extraction / claim-evidence-binding；下游：conflict-detection-skill、extraction-quality-audit-skill、semantic-graph-compilation-skill。
