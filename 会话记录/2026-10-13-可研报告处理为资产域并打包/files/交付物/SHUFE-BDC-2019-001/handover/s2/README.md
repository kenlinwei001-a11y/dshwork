# 环节 s2 交接说明（README）

- 脚本：`s0b_remap.py`　退出码：0　耗时：1.6s
- 是否产生变更：否（幂等）　must_change：False

## 我产出了什么（自报，见 manifest_A.json）
- `build/remap_report.json`（1195 B）

## 给下游的说明
- 声明的产物 glob：["build/remap_report.json"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：{
  "old_chunks": 1153,
  "new_chunks": 1178,
  "mapped": 1145,
  "unmatched": 8,
  "levels": {
    "L1": 569,
    "L2": 294,
    "L3": 282,
    "unmatched": 8
  },
  "cited_ids": 216,
  "cited_mapped": 216,
  "cited_dangling": []
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
