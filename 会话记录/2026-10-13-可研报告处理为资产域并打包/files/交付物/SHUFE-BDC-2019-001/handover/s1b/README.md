# 环节 s1b 交接说明（README）

- 脚本：`s3b_extract.py`　退出码：0　耗时：0.11s
- 是否产生变更：否（幂等）　must_change：False

## 我产出了什么（自报，见 manifest_A.json）
- `build/extractions-clean/P4a.json`（28213 B）
- `build/extractions-clean/P4b.json`（40570 B）
- `build/extractions-clean/P5.json`（22984 B）

## 给下游的说明
- 声明的产物 glob：["build/extractions-clean/P4a.json", "build/extractions-clean/P4b.json", "build/extractions-clean/P5.json"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：P4a extracted: facts=53 rules=1 claims=2 evidence=18 relations=0
P4b extracted: facts=70 rules=7 claims=2 evidence=23 relations=8
P5 extracted: facts=29 rules=6 claims=2 evidence=15 relations=8

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
