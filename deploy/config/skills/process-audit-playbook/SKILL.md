---
name: process-audit-playbook
description: 用 C2–C5/C7 规则审核过程文档：谓词判定消费 eval_slots 的确定性结果，本 skill 只判定性卡、记录冲突与缺证分类，输出带 report span 与 basis 的 findings。
---

> **agent 入口是脚本，不是本文。** `python3 toolchain/run.py pa.process_audit --out <产出目录> [--check|--verify]`
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
| `machine/audit_results.json` | eval_slots 的谓词判定（直接采信，除定性卡外不改） |
| `report_slots.json` / `report_spans.json` | 抽取专家填的值与位置 |
| `machine/ses.json` | gaps.pending_class（缺证分派依据） |
| `machine/sop-graph.json` | `basis`（论证依据）、`invalidates`（失效传播） |

## 输出

`process_findings.json`：

```json
{"findings":[{"rule_id":"ARC-C7-11.2-01","category":"C7","verdict":"PASS|FAIL|UNVERIFIABLE|CONFLICT_PENDING",
  "report_span":{"page":4,"quote":"空白 2 个"},"std_span_id":"sha:start-end",
  "message":"…","basis":"…","owner":"实验室"}]}
```

每条必须带 `rule_id + std_span_id + report_span`；缺任一项标 UNLOCATED。

## 执行顺序

1. 取任务单中 C2–C5/C7 的槽，逐槽看 `audit_results` 的判定。
2. 谓词卡：采信判定；只核对“值是否来自原文”（防假通过）。
3. 定性卡：按 `acceptable / needs_review / unacceptable` 三档判，`verdict_ceiling=NO_PASS` 的不得判 PASS。
4. 冲突：同一条款多处证据不一致 → `CONFLICT_PENDING`，并列原文，不选一个。
5. 缺证：按 gaps.pending_class 写 owner（PENDING_DATA→送样方/检测室，LAB_POLICY→实验室）。
6. 写 findings，跑 `--verify`。

## 硬口径

- 不重算、不重判谓词；对 eval_slots 的结论只能升级（PASS→UNVERIFIABLE）不能降级。
- 缺证不默认通过；记录冲突不选值。
- 方法 mismatch 的规则不参与判定，单列交裁定。
- 结论三段式：哪里不合规 + 缺什么 + 依据（basis）。

## 交接

输出 `process_findings.json` → 审核裁定专家合并（报告侧 C1/C6 findings 同格式）。
