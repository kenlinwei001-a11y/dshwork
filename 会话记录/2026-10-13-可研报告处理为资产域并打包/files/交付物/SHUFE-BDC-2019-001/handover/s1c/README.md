# 环节 s1c 交接说明（README）

- 脚本：`s3c_extract.py`　退出码：0　耗时：0.15s
- 是否产生变更：否（幂等）　must_change：False

## 我产出了什么（自报，见 manifest_A.json）
- `build/extractions-clean/P6.json`（23398 B）
- `build/extractions-clean/P7.json`（46859 B）

## 给下游的说明
- 声明的产物 glob：["build/extractions-clean/P6.json", "build/extractions-clean/P7.json"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：P6 extracted: facts=19 rules=2 claims=6 evidence=19 relations=8
P7 extracted: facts=73 rules=12 claims=3 evidence=13 relations=33

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
