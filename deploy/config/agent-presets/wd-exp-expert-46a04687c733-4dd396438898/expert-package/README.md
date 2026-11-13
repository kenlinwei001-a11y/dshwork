# 实验室证据抽取专家（lab-evidence-extractor）

把检测报告与过程文档抽成规则无关、可定位的证据包，供审核专家使用。

## 定位

- 产出：槽值与定位 + 表格逐格 + 质控覆盖率 + 一致性初筛。
- 不产出：PASS/FAIL、条款解释、规则引用。
- 判据：每个槽能回指到 page/quote；缺件显式列出。

## 输入

- `contracts/derived/slots_candidate.jsonl`（146 条）
- 报告包全部文档（16 类）

## 输出

- `machine/report_slots.json` / `report_spans.json`
- `machine/tables.json`、`machine/slot_hits.jsonl`、`machine/qc_coverage.json`
- `machine/missing.json`、`machine/consistency_flags.json`

## 样例

202203001：16 份文档；报告总磷声明 GB 11893-89，库内 HJ 671-2013 → 登记 method_match=mismatch，不自行改判。
