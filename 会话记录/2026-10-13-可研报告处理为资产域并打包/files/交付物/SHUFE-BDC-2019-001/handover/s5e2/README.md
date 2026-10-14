# 环节 s5e2 交接说明（README）

- 脚本：`s32_external_docs_merge.py`　退出码：0　耗时：0.33s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/documents.yaml`（9129 B）
- `SHUFE-BDC-2019-001/quality/external_merge_report.yaml`（312 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/documents.yaml", "SHUFE-BDC-2019-001/quality/external_merge_report.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：{
  "documents": 21,
  "clause_nodes": 22,
  "constraint_nodes": 17,
  "evidence": 39,
  "nodes_total": 959
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
