# 证据包交接（给审核专家）

## 1 交付物

- evidence pack JSON（schema 见 evidence-pack-schema.md）
- report_document / report_evidence 入库记录
- 缺失清单与 consistency_flags

## 2 审核专家怎么用

| 审核专家 | 读取 |
|---|---|
| 3 报告审核 | report、fields（报告字段/结果表）、methods、instruments、C1/C6 规则 |
| 4 过程文档审核 | records（calibration/blank/duplicate/spike/reagent/environment/instrument_run/sample_chain）、documents、C2–C5/C7 规则 |
| 5 一致性与裁定 | 全部 fields、records、missing、consistency_flags、3/4 的判定结果 |

## 3 定位契约

- 审核结果 target 引用 evidence 的 doc_id/page/block_id/char/quote；
- 证据包中的 UNLOCATED 字段不能作为 PASS/FAIL 的唯一依据；
- 同一字段多来源冲突时，审核专家按规则选主证据，选不了则 CONFLICT_PENDING。

## 4 禁止

- 审核专家不得重抽报告/记录，不得改写证据包；
- 证据包不得内含 PASS/FAIL 或规则 ID；
- 缺失项不得由审核专家“补做”后判通过。
