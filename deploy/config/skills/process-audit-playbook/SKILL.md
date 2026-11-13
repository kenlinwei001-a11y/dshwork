---
name: process-audit-playbook
description: 用 C2–C5/C7 规则审核过程文档：谓词判定消费 eval_slots 的确定性结果，本 skill 只判定性卡、记录冲突与缺证分类，输出带 record span 与 basis 的 findings。
---

> **agent 入口是脚本，不是本文。** `python3 skills/process-audit-playbook/scripts/process_audit.py --out <产出目录> [--check|--verify]`
> 本文供人阅读：说明脚本在做什么、口径为什么这样。执行以脚本退出码为准，md 不作为判据。
> **脚本实际位置**：`skill-update-proc/skills/process-audit-playbook/scripts/process_audit.py`
> 全局技能只承载本文档，**不上传 scripts/**；执行请用上面的仓库内路径。

# 过程文档审核 playbook（v2：只判定性，不重算）

## 定位

谓词已经由抽取侧的 `eval_slots` 算完。本 skill **只做三件事**：
① 定性卡（标准未给阈值）的人工三档判断；② 记录间冲突的并列；③ 缺证按 `pending_class` 分类。

**不重判谓词、不重算数值、不改报告。**

## 输入

| 文件 | 用途 |
|---|---|
| `machine/audit_tasks.jsonl` | 只筛 `category ∈ {C2,C3,C4,C5,C7}` 的任务 |
| `machine/audit_results.json` | eval_slots 的谓词判定（直接采信） |
| `machine/report_slots.json` / `report_spans.json` | 抽取侧填的值与位置 |
| `machine/consistency_flags.json` | 跨文档对账事实（只报事实，不判定） |
| `machine/ses.json` | gaps.pending_class（缺证分派依据） |

## 脚本做了什么（确定性，不叫模型）

1. 筛 C2–C5/C7 任务；
2. 采信 eval_slots 的谓词结论；
3. 缺证 → `UNVERIFIABLE` + `pending_class` + **owner**（按 doc_type 派，不问人）：

| pending_class | owner |
|---|---|
| PENDING_DATA | 实验室（补数据/补记录） |
| PENDING_DOC | 实验室（提交 SOP/说明书/记录模板） |
| PENDING_REF | 标准归口 / 用户（上传被引文件） |
| LAB_POLICY | 实验室技术负责人（内部规定） |
| PENDING_USER | 用户（只能人裁） |

4. 记录冲突 → `CONFLICT_PENDING`，**两侧都必须有 page+quote**；只有一侧就是缺证，不是冲突；
5. 列出 `pending_human`（定性卡）供模型补判。

## 模型只补两件

- 定性三档：符合 / 不符合 / 缺证；
- 冲突是否需要人裁、并列解释怎么写。

## 硬口径

- **缺证 ≠ 不合格**：没有证据判 `UNVERIFIABLE`，不判 FAIL。
- **只升不降**：不得把 FAIL 改成 PASS。
- **不许自行给 PASS**：定性卡 `ceiling=NO_PASS`。
- **冲突并列**：不许二选一，两侧原文都要在。
- **不重算**：谓词结论一律采信 `eval_slots`。

## 输出

`machine/process_findings.json`：

```json
{"items":[{"rule_id":"ARC-C7-11.2-01","category":"C7","slot":"S042","doc_type":"质控记录",
  "verdict":"PASS|FAIL|UNVERIFIABLE|CONFLICT_PENDING",
  "record_span":{"page":4,"quote":"空白 2 个"},"std_anchor":{"clause":"11.2","page":6},
  "basis":"eval_slots|missing_evidence|conflict",
  "pending_class":"PENDING_DATA","owner":"实验室（补数据/补记录）"}],
 "counts":{},"owners":{},"pending_human":[]}
```

## 校验（`--verify`）

每条有 `std_anchor.clause`；判定枚举合法；缺证必须有 `pending_class` 与派得出的 owner；冲突必须两侧都有 page+quote；`counts` 与明细一致。不通过 exit 1。
