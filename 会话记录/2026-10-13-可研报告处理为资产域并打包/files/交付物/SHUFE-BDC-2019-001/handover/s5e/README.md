# 环节 s5e 交接说明（README）

- 脚本：`opt25.py`　退出码：0　耗时：0.72s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/source_ledger.json`（18292 B）
- `SHUFE-BDC-2019-001/graph/relations.yaml`（52262 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/source_ledger.json", "SHUFE-BDC-2019-001/graph/relations.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：,
    {
      "id": "C5",
      "verdict": "FAIL",
      "recall": 59.5,
      "missing": 17
    },
    {
      "id": "C6",
      "verdict": "pass",
      "recall": 96.7,
      "missing": 7
    },
    {
      "id": "C7",
      "verdict": "pass",
      "recall": 100.0,
      "missing": 0
    }
  ]
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
