---
name: report-audit-playbook
description: 按 C1 方法适用性与 C6 数据计算规则审核检测报告，标出方法与标准不一致，给出带报告原文位置的逐条判定。谓词判定采信 eval_slots，本 skill 只判定性卡、冲突与假通过，不重算规则。
---

> **agent 入口是脚本，不是本文。** `python3 skills/report-audit-playbook/scripts/report_audit.py --out <产出目录> [--check|--verify]`
> 本文供人阅读：说明脚本在做什么、口径为什么这样。执行以脚本退出码为准，md 不作为判据。
> **脚本实际位置**：`skill-update-audit/skills/report-audit-playbook/scripts/report_audit.py`
> 全局技能只承载本文档，**不上传 scripts/**；执行请用上面的仓库内路径。

# 报告审核 playbook（v1）

## 定位

**只审报告这一侧**，管 C1（方法适用性）与 C6（数据与计算）。C2–C5/C7 归过程文档审核。

本 skill **不重算规则**：谓词类结论由 `eval_slots` 确定性给出；这里只做三件事——

1. 采信并落地判定：直接采用 `audit_results.json` 的 verdict，附报告侧定位；
2. 判定“判定器判不了”的：定性卡（`qualitative`）、方法号 mismatch、计算方法与标准声明不一致；
3. 拦假通过：PASS 但没有报告 span、或 PASS 但没有条款依据的，一律降级。

## 输入（只读 `machine/`，禁读 `human/`）

| 文件 | 用途 |
|---|---|
| `machine/audit_tasks.jsonl` | 槽位任务；只取 `category ∈ {C1, C6}` |
| `machine/report_slots.json` / `report_spans.json` | 报告侧取值与定位 |
| `machine/audit_results.json` | eval_slots 的确定性判定 |
| `machine/ses.json` | 标准上下文、适用域、方法族 |

## 脚本做了什么（确定性，不叫模型）

1. 筛 C1/C6 任务；
2. 采信 eval_slots 谓词结论；
3. **三条假通过降级**，命中任一即改 `UNVERIFIABLE`：
   - verdict=PASS 但 `report_spans[slot].quote` 为空；
   - verdict=PASS 但 `std_anchor.clause` 为空（无条款依据）；
   - verdict=PASS 但属定性卡（`ceiling=NO_PASS`）；
4. 列出 `pending_human`（定性卡）供模型补判。

## 模型只补三件

- 定性卡三档：符合 / 不符合 / 缺证；
- 方法号 mismatch：报告写的方法标准号与本轮 `rule_set_id` 是否**逐字一致**（含年号）；
- 定性判断的表述（message）怎么写。

## 判定口径（人读参考）

| 类别 | 只判三件 |
|---|---|
| C1 方法适用性 | 基质是否落在适用域；结果是否在量程内且稀释后仍在内；方法号是否逐字一致 |
| C6 数据与计算 | 计算链 a/b/f/y 是否都能找到；校准有效性（相关系数/点数/空白）；修约与结果表示 |

## 硬口径

- **缺证 ≠ 不合格**：没有证据判 `UNVERIFIABLE`，不判 FAIL。
- **只升不降**：可以因假通过把 PASS 降到 UNVERIFIABLE；不得把 FAIL 改成 PASS。
- **不重算**：谓词结论一律采信 `eval_slots`。
- **每条都要能回指**：`rule_id` + `std_anchor.clause` + `report_span.quote` 三者缺一，该条不得进结论。
- **方法不混用**：报告声明哪个方法就用那个规则集。

## 输出

`machine/report_findings.json`：

```json
{"items":[{"rule_id":"ARC-C1-1-01","category":"C1","slot":"S001",
  "verdict":"PASS|FAIL|UNVERIFIABLE|NOT_APPLICABLE|CONFLICT_PENDING",
  "message":"一句话结论",
  "report_span":{"page":2,"quote":"样品类型：地表水","method":"table_cell"},
  "std_anchor":{"clause":"1","page":4,"quote":"本标准适用于地表水…"},
  "basis":"eval_slots|missing_evidence|downgrade_*"}],
 "counts":{},"downgraded":[{"rule_id":"...","from":"PASS","reason":"no_span"}],"pending_human":[]}
```

## 校验（`--verify`）

每条有 `std_anchor.clause`；PASS 必有 `report_span.quote`；判定枚举合法；`counts` 与明细一致；`downgraded` 每条都能对应到一个 `UNVERIFIABLE`。不通过 exit 1。

## 定位契约

- 报告侧位置用 `report_span`（page + quote + method）；`quote` 必须能在报告原文检索命中。
- 命中不了标 `"unlocated": true` 并写试过的 `match_hints`，**不许标到别处**。
- 标准侧位置用 `std_anchor`（clause + page + quote），取自库，不手打。
