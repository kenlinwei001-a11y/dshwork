---
name: report-audit-playbook
description: 按 C1 方法适用性与 C6 数据计算规则审核检测报告，标出方法与标准不一致，给出带报告原文位置的逐条判定。谓词判定采信 eval_slots，本 skill 只判定性卡、冲突与假通过，不重算规则。
---

> **agent 入口是脚本，不是本文。** `python3 toolchain/run.py ra.report_audit --out <产出目录> [--check|--verify]`
> 本文供人阅读：说明脚本在做什么、口径为什么这样。执行以脚本退出码为准，md 不作为判据。
> **脚本实际位置**：`skill-update-audit/skills/report-audit-playbook/scripts/report_audit.py`
> 全局技能只承载本文档，**不上传 scripts/**；执行请用上面的仓库内路径。

# 报告审核 playbook（v1）

## 定位

**只审报告这一侧**，管 C1（方法适用性）与 C6（数据与计算）。C2–C5/C7（样品流转、前处理、仪器、试剂、操作、质控）归过程文档审核。

本 skill **不重算规则**：谓词类结论由 `eval_slots` 确定性给出；这里只做三件事——

1. 采信并落地判定：`audit_results.json` 里每条规则的 verdict 直接采用，附上报告侧定位。
2. 判定"判定器判不了"的：定性卡（`qualitative=true`）、方法号 mismatch、计算方法与标准声明不一致。
3. 拦假通过：PASS 但没有报告 span、或 PASS 但没有条款依据的，一律降级。

## 输入（只读 `machine/`，禁读 `human/`）

| 文件 | 用途 |
|---|---|
| `machine/audit_tasks.jsonl` | 槽位任务；只取 `category` ∈ {C1, C6} |
| `machine/report_slots.json` / `report_spans.json` | 报告侧取值与定位（证据抽取产物） |
| `machine/audit_results.json` | eval_slots 的确定性判定 |
| `machine/ses.json` | 标准上下文、适用域、方法族 |
| `library/standards.db` | 规则原文与条款锚（`graph_lookup --rule` 查节点，**不要读整份 JSON**） |

## 判定口径

### 1. C1 方法适用性（只判三件）

- **基质**：报告声明的样品类型是否落在标准适用域内。不在 → FAIL（规则卡 C1 首条）。
- **量程**：结果值是否在方法测定范围内；超范围必须能看到稀释倍数且稀释后仍在范围内，否则 UNVERIFIABLE。
- **方法号一致性**：报告写的方法标准号与本轮 `rule_set_id` 对应标准是否**逐字一致**（含年号）。不一致直接 FAIL，并写明两个号——这是最常见的假通过来源。

### 2. C6 数据与计算（只判三件）

- **计算链**：`ρ=(y−a)/b×f` 的 a、b、f、y 是否都能在报告或原始记录里找到；缺一 → UNVERIFIABLE。
- **校准有效性**：相关系数、校准点数、空白是否满足规则阈值（谓词判定，采信 eval_slots）。
- **修约与结果表示**：小数位/有效数字是否按标准分档；修约错误一律 FAIL，并给出应写值。

### 3. 定性卡三档

定性卡（无谓词）只能落到三档，**不许给 PASS**：

| 档 | 条件 |
|---|---|
| 符合 | 报告原文有明确、可引用的对应表述 |
| 不符合 | 报告有明确相反表述 |
| 缺证 | 报告未提及，或提及不可辨 |

定性卡的 `verdict_ceiling` 是 `NO_PASS`，出现 PASS 即视为判定越权，降回 UNVERIFIABLE。

### 4. 假通过复核（必做）

三条降级规则，命中任一条即改判 `UNVERIFIABLE`：

1. verdict=PASS 但 `report_spans[slot].quote` 为空。
2. verdict=PASS 但 `basis` 为空（无条款依据）。
3. verdict=PASS 但规则 `qualitative=true`（定性卡）。

## 输出

写 `machine/report_findings.json`：

```json
{"standard_id":"...","report_id":"...",
 "items":[{"rule_id":"ARC-C1-1-01","category":"C1","slot":"S001",
           "verdict":"PASS|FAIL|UNVERIFIABLE|NOT_APPLICABLE|CONFLICT_PENDING",
           "message":"一句话结论",
           "report_span":{"page":2,"quote":"样品类型：地表水","method":"table_cell"},
           "std_anchor":{"clause":"1","page":4,"quote":"本标准适用于地表水…"},
           "basis":"采信 eval_slots / 定性判定 / 假通过降级",
           "pending_class":null}],
 "counts":{"PASS":0,"FAIL":0,"UNVERIFIABLE":0,"NOT_APPLICABLE":0,"CONFLICT_PENDING":0},
 "downgraded":[{"rule_id":"...","from":"PASS","reason":"no_span"}]}
```

## 硬约束

- **缺证 ≠ 不合格**：没有证据只能判 `UNVERIFIABLE`，不得判 FAIL。
- **只升不降**：可以因假通过把 PASS 降到 UNVERIFIABLE；不得把 FAIL 改成 PASS。
- **不重算**：谓词结论一律采信 `eval_slots`，自己算一遍等于引入第二个口径。
- **每条都要能回指**：`rule_id` + `std_anchor.clause` + `report_span.quote` 三者缺一，该条不得进结论。
- **方法不混用**：报告声明哪个方法就用那个规则集；参数不跨方法套用。

## 定位契约

- 报告侧位置用 `report_span`（page + quote + method）；`quote` 必须能在报告原文检索命中。
- 命中不了标 `"unlocated": true` 并写 `match_hints` 试过的关键词，**不许标到别处**。
- 标准侧位置用 `std_anchor`（clause + page + quote），取自库，不手打。
