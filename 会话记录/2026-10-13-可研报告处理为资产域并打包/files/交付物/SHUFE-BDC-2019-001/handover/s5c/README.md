# 环节 s5c 交接说明（README）

- 脚本：`s10_external.py`　退出码：0　耗时：0.6s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/external/documents.yaml`（13165 B）
- `SHUFE-BDC-2019-001/external/chunks.jsonl`（470087 B）
- `SHUFE-BDC-2019-001/external/mandates.yaml`（19272 B）
- `SHUFE-BDC-2019-001/external/constraints.yaml`（5750 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/external/documents.yaml", "SHUFE-BDC-2019-001/external/chunks.jsonl", "SHUFE-BDC-2019-001/external/mandates.yaml", "SHUFE-BDC-2019-001/external/constraints.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：963,
  "mandates": 22,
  "mandates_located": 19,
  "constraints": 17,
  "mandatory_constraints": 7,
  "bindings": 15,
  "edges": 38,
  "by_status": {
    "duplicate": 1,
    "failed_403": 1,
    "ok": 11,
    "ok_mislabeled": 2,
    "ok_partial": 1,
    "ok_raw_html": 1,
    "ok_secondary": 3
  }
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
