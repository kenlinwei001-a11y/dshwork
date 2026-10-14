# 环节 s6g 交接说明（README）

- 脚本：`fix32_final.py`　退出码：0　耗时：0.32s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/waivers.yaml`（3770 B）
- `SHUFE-BDC-2019-001/documents.yaml`（9129 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/waivers.yaml", "SHUFE-BDC-2019-001/documents.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注："ledger_entries": 4,
  "relations_added": 0,
  "registered": {
    "conflicts_added": 0,
    "rules_registered": 0,
    "warrant_filled": 0
  },
  "waivers": 14
}
{
  "evidence_filled": [
    "EV-规范-抗震-沪-02"
  ],
  "s10_aligned": "14-社会效益.json",
  "waivers_total": 12,
  "k10_table_filters": true
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
