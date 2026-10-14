# 环节 s5a 交接说明（README）

- 脚本：`s7b_desensitize.py`　退出码：0　耗时：0.32s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/chunks/skeletons.jsonl`（291253 B）
- `SHUFE-BDC-2019-001/quality/gaps_unmodeled_values.json`（259262 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/chunks/skeletons.jsonl", "SHUFE-BDC-2019-001/quality/gaps_unmodeled_values.json"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：{
  "chunks": 1178,
  "numeric_slots_replaced": 2192,
  "node_index_entries": 567,
  "nested_after_fix": 0,
  "malformed_after_fix": 0
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
