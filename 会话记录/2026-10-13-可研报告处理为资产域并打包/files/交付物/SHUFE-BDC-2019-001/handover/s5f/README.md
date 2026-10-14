# 环节 s5f 交接说明（README）

- 脚本：`gt29_toolkit.py`　退出码：0　耗时：0.52s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/chunks/sentences.jsonl`（511636 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/chunks/sentences.jsonl"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：{
  "sentences": 1923,
  "avg_len": 33.9,
  "sum_sentence_chars": 61588,
  "sum_chunk_chars": 61602,
  "diff": 14,
  "fake_gaps_removed": 0,
  "entity_names": 555,
  "entity_groups": 554,
  "merged_groups": 1,
  "out": "交付物/报告/质量门控工具需求.md"
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
