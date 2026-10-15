# Skill · claim-evidence-binding-skill（SK-09）

## 名称与定位

- **名称**：`claim-evidence-binding-skill`（Skill ID SK-09）
- **一句话**：判断 Evidence 与 Claim 的关系：SUPPORT、PARTIAL_SUPPORT、CONTRADICT、CONTEXT 或 INSUFFICIENT。

## 角色

七道工序**第 4/6 道**的证据判定通道：为每条 Claim 判定证据充分性五级，直接决定正文措辞分层（一手证据→陈述式；不足→不硬撑结论）。两个专家都绑定。

## 输入

Claim + 候选 Evidence（来源/页码/文本范围）

## 输出

五级判定 + 理由：
- SUPPORT（充分支持）
- PARTIAL_SUPPORT（部分支持，列出缺口）
- CONTRADICT（矛盾，转 conflict-detection 待审）
- CONTEXT（仅提供上下文）
- INSUFFICIENT（证据不足，如实说明）

## 执行规则

- 判定附理由与证据定位，不拍脑袋。
- CONTRADICT 必须转冲突通道（待审），不裁决。
- INSUFFICIENT 的 Claim 不得作结论性陈述。

## 关系

上游：claim-extraction / evidence-extraction；下游：claim-validation-skill、conflict-detection-skill、graph-deductive-writing-skill（措辞分层依据）。
