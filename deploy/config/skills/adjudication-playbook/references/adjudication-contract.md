# 裁定契约 v2（对接抽取侧 machine/ 产物）

## 输入

- `machine/audit_results.json`：eval_slots 的确定性判定
- `machine/ses.json`：method_family、rule_set_id、gaps.pending_class
- `machine/sop-graph.json`：节点 basis（论证依据）、invalidates
- `machine/span_refs.json` + `spans.db`：clause → span_id → 原文
- 报告侧：report span（page/quote）与槽值

禁读 `human/`。

## 合并优先级

`FAIL > CONFLICT_PENDING > UNVERIFIABLE > NOT_APPLICABLE > PASS`

- 不得平均、不得多数票；
- 方法 mismatch → 该标准不参与合格判定，单列；
- 主审缺失 → 「未完成审核」，不得默认合格。

## 升级/降级

- **只能升级**：PASS → UNVERIFIABLE / FAIL；
- **降级需证据**：FAIL → PASS 仅在附新证据时，且写 `override_reason`；
- 假通过信号：PASS 无 report_span、无 basis、用错方法、ND 当 0、同条款他处冲突。

## 责任分派（按 pending_class）

| pending_class | owner |
|---|---|
| PENDING_DATA | 送样方/检测室 |
| PENDING_REF | 标准归口 |
| LAB_POLICY | 实验室 |
| PENDING_USER | 用户裁决 |
| 其他 | 未定 |

## 输出与页面契约

`adjudication.json`：每条 finding 带 `rule_id + std_span_id + report_span + verdict + message + basis + owner`。
页面按 `std_span_id` 取标准原文、按 `report_span` 贴结论；任一定位缺失标「未定位」，不得静默丢弃。

## 留痕

`adjudicate.py --trail <step> --exit 0` 写 `trail.jsonl`；`--verify` 校验 `adjudication.json` 并写 verify 记录；**无 verify 记录不得标完成**。
