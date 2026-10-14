# 环节 s6f 交接说明（README）

- 脚本：`fix30_remediate.py`　退出码：0　耗时：0.32s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/waivers.yaml`（1321 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/waivers.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：{
  "asset_slot": 12,
  "func_restore": 5,
  "ledger_entries": 4,
  "relations_added": 21,
  "registered": {
    "conflicts_added": 10,
    "rules_registered": 9,
    "warrant_filled": 1
  },
  "waivers": 14
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
