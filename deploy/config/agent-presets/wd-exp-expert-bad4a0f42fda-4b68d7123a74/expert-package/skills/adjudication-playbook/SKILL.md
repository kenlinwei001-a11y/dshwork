---
name: adjudication-playbook
description: 合并报告审核与过程文档审核的判定，做跨文档一致性、方法 mismatch、缺证/冲突处理与假通过复核，输出最终审核结论、问题清单与整改建议。判定来自 eval_slots，本 skill 不重判规则。
---

# 审核裁定 playbook（v2，对接标准要素抽取新契约）

## 定位

**不重判规则，只做四件事**：合并（按优先级）、跨文档一致性、方法 mismatch、假通过复核。
规则判定由抽取侧 `eval_slots` 产出的 `audit_results.json` 提供，本 skill 只对结果做**升级**处理与一致性裁定。

## 输入（只读 machine/ 与库）

| 文件 | 用途 |
|---|---|
| `machine/audit_results.json` | 每条规则的确定性判定（rule_id / slot / verdict / message / basis / anchor） |
| `machine/ses.json` | 标准上下文：method_family、rule_set_id、gaps（含 pending_class） |
| `machine/sop-graph.json` | 节点 `basis`（论证依据）、`invalidates`（失效传播） |
| `machine/span_refs.json` + 切片库 `spans.db` | 条款锚 → `span_id` → 原文 |
| 报告侧证据 | 报告 `span`（page/quote）与槽值 |

**禁止**读 `human/` 下的 md（那是叙述，不是判据）。

## 输出

`adjudication.json`（唯一交付）：

```json
{"report_id":"R-...","standards":["..."],"verdict":"FAIL|CONFLICT_PENDING|UNVERIFIABLE|PASS",
 "counts":{},"findings":[{"rule_id","std_span_id","report_span","verdict","message","basis","owner","reason"}],
 "method_mismatch":[],"conflicts":[],"missing":[],"override_policy":{"mode":"escalate_only"}}
```

每条 finding 必须带 `rule_id + std_span_id + report_span`；缺一标「未定位」，不得静默丢弃。

## 硬口径

1. **优先级**：`FAIL > CONFLICT_PENDING > UNVERIFIABLE > NOT_APPLICABLE > PASS`；不得平均、不得多数票。
2. **只能升级不能降级**：`PASS → UNVERIFIABLE/FAIL` 允许（假通过复核）；`FAIL → PASS` 仅在附新证据时允许，且必须写 `override_reason`。
3. **假通过信号**（命中即降为 UNVERIFIABLE）：PASS 但无报告位置、无 basis、用错方法规则、ND 当 0、同条款他处证据冲突。
4. **方法 mismatch**：报告声明方法不在 `ses.method_family(PROVIDED)` → 该标准不参与合格判定，单列。
5. **缺证不等于不合格**：按 `pending_class` 分派责任——`PENDING_DATA`→送样方/检测室，`PENDING_REF`→标准归口，`LAB_POLICY`→实验室，`PENDING_USER`→用户裁决。
6. **结论三段式**：哪里不合规 + 缺什么 + 依据（`basis`，来自论证节点）。

## 执行

```
python3 scripts/adjudicate.py --dir <run目录> --report <report_id> --report-spans spans.json
python3 scripts/adjudicate.py --dir <run目录> --verify
```

`--check` 打印必做项；`--trail <step> --exit <code>` 写 `trail.jsonl`；**没有 verify 记录不得标完成**。

## 与抽取侧的分工

| 谁 | 做什么 |
|---|---|
| 抽取侧 `eval_slots` | 算：按 op/value 比较，产出 PASS/FAIL/UNVERIFIABLE |
| 本 skill | 判：合并、假通过、一致性、方法、责任分派 |
| 页面 | 只渲染：按 `span_id` 取原文，贴结论 |

## 资料

- `references/adjudication-contract.md`：合并规则、假通过清单、责任分派、页面契约
- `templates/adjudication.json`：输出模板
