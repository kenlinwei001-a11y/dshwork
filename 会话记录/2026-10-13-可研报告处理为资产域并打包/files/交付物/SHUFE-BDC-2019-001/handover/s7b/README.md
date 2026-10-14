# 环节 s7b 交接说明（README）

- 脚本：`s12_bundle_md.py`　退出码：0　耗时：0.25s
- 是否产生变更：否（幂等）　must_change：False

## 我产出了什么（自报，见 manifest_A.json）
- `交付物/装配输入包-报告还原.md`（270995 B）

## 给下游的说明
- 声明的产物 glob：["交付物/装配输入包-报告还原.md"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：{
  "file": "交付物/装配输入包-报告还原.md",
  "bytes": 270995,
  "lines": 3118,
  "facts": 959,
  "rules": 35,
  "claims": 37,
  "curated_evidence": 128,
  "auto_evidence": 436,
  "mandates": 22,
  "bindings": 15,
  "chapters": 16,
  "conflicts": 15,
  "gaps": 9
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
