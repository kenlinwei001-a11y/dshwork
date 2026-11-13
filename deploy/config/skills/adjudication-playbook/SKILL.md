---
name: adjudication-playbook
description: 合并报告审核与过程文档审核的判定，做跨文档一致性、方法 mismatch、缺证/冲突处理与假通过复核，输出最终审核结论、问题清单与整改建议。判定来自 eval_slots，本 skill 不重判规则。
---

> **agent 入口是脚本，不是本文。** `python3 skills/adjudication-playbook/scripts/adjudicate.py --dir <产出目录> [--check|--verify]`
> 本文供人阅读：说明脚本在做什么、口径为什么这样。执行以脚本退出码为准，md 不作为判据。
> **脚本实际位置**：`skill-update-audit/skills/adjudication-playbook/scripts/adjudicate.py`
> 全局技能只承载本文档，**不上传 scripts/**；执行请用上面的仓库内路径。

# 审核裁定 playbook（v2）

## 定位

**不重判规则，只做四件事**：合并（按优先级）、跨文档一致性、方法 mismatch、假通过复核。

规则判定由抽取侧 `eval_slots` 的 `audit_results.json` 提供，本 skill 只对结果做**升级**处理与一致性裁定。

## 输入（只读 `machine/` 与库）

| 文件 | 用途 |
|---|---|
| `machine/report_findings.json` | 报告线（C1/C6）结论 |
| `machine/process_findings.json` | 过程线（C2–C5/C7）结论 |
| `machine/audit_results.json` | eval_slots 原始判定 |
| `machine/ses.json` | 方法族、rule_set_id、gaps.pending_class |
| `library/standards.db` | 规则与节点（`graph_lookup` 查，不读整份 JSON） |

## 脚本做了什么（确定性）

1. 合并两线结论，同一 `rule_id` 只计一次；
2. **只升不降**：禁止把 FAIL / UNVERIFIABLE 改成 PASS；
3. **假通过降级**：PASS 无 span、无 basis、或定性卡给 PASS 的，全部降 `UNVERIFIABLE`；
4. 每条 `UNVERIFIABLE` 必须有 `pending_class` 与**对得上的 owner**；
5. `counts` 由明细派生，不手填。

## 模型只补四件

- **方法 mismatch**：报告声明的方法 vs 报告实际条件 vs 规则集，三者是否一致；
- **跨文档一致性**：报告值 ↔ 流转单 ↔ 前处理记录 ↔ 仪器记录；
- **两线结论打架**：并列，不裁决；
- **整改建议**：按 owner 分组，写可执行动作。

## 裁定口径

- **只能升不能降**，唯一例外是假通过纠正（PASS → UNVERIFIABLE）。
- 要改动脚本已定的 verdict，必须写 `override{from,to,reason,evidence}`，`reason` 说明是升级还是纠正错判。
- `CONFLICT_PENDING` 一律交人裁，不给结论。
- owner 按 `pending_class` 派：PENDING_DATA / PENDING_DOC → 实验室；PENDING_REF → 标准归口或用户；LAB_POLICY → 实验室技术负责人；PENDING_USER → 用户。

## 输出

`machine/adjudication.json`（脚本）+ `machine/adjudication_final.json`（补判后）：

```json
{"verdict":"PASS|FAIL|UNVERIFIABLE|CONFLICT_PENDING",
 "items":[{"rule_id":"...","verdict":"...","line":"report|process","basis":"...","owner":"..."}],
 "conflicts":[],"method_mismatch":[],"actions":[],"owners":{},"counts":{},
 "overrides":[{"rule_id":"...","from":"...","to":"...","reason":"...","evidence":"..."}]}
```

## 校验（`--verify`）

没有把 FAIL/UNVERIFIABLE 降成 PASS；假通过已全部降级；每条 `UNVERIFIABLE` 有 `pending_class` 与对得上的 owner；`counts` 与明细一致且两套来源不重复计入。不通过 exit 1。

## 交付边界

本 skill 出**审核结论与整改清单**，不代签检测报告合规结论，也不替代实验室方法验证与不确定度评定。
