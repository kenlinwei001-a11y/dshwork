# 环节 s1a 交接说明（README）

- 脚本：`s3a_extract.py`　退出码：0　耗时：0.14s
- 是否产生变更：否（幂等）　must_change：False

## 我产出了什么（自报，见 manifest_A.json）
- `build/extractions-clean/P1.json`（33881 B）
- `build/extractions-clean/P2.json`（18497 B）
- `build/extractions-clean/P3.json`（31360 B）

## 给下游的说明
- 声明的产物 glob：["build/extractions-clean/P1.json", "build/extractions-clean/P2.json", "build/extractions-clean/P3.json"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：P1 extracted: facts=52 rules=2 claims=5 evidence=16 relations=20
P2 extracted: facts=11 rules=0 claims=6 evidence=12 relations=16
P3 extracted: facts=51 rules=5 claims=2 evidence=11 relations=15

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
