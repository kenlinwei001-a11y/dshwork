# 环节 s5g 交接说明（README）

- 脚本：`s7p_prompt_compile.py`　退出码：0　耗时：2.63s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/prompt_compile_report.yaml`（10193 B）
- `SHUFE-BDC-2019-001/prompts/DOC-REPORT-01.claim_extraction.json`（3801 B）
- `SHUFE-BDC-2019-001/prompts/DOC-REPORT-01.fact_extraction.json`（3717 B）
- `SHUFE-BDC-2019-001/prompts/EXT-00.claim_extraction.json`（3693 B）
- `SHUFE-BDC-2019-001/prompts/EXT-00.fact_extraction.json`（3609 B）
- `SHUFE-BDC-2019-001/prompts/EXT-01.claim_extraction.json`（3821 B）
- `SHUFE-BDC-2019-001/prompts/EXT-01.fact_extraction.json`（3737 B）
- `SHUFE-BDC-2019-001/prompts/EXT-02.claim_extraction.json`（3803 B）
- `SHUFE-BDC-2019-001/prompts/EXT-02.fact_extraction.json`（3719 B）
- `SHUFE-BDC-2019-001/prompts/EXT-03.claim_extraction.json`（3699 B）
- `SHUFE-BDC-2019-001/prompts/EXT-03.fact_extraction.json`（3615 B）
- `SHUFE-BDC-2019-001/prompts/EXT-04.claim_extraction.json`（3766 B）
- `SHUFE-BDC-2019-001/prompts/EXT-04.fact_extraction.json`（3682 B）
- `SHUFE-BDC-2019-001/prompts/EXT-05.claim_extraction.json`（3765 B）
- `SHUFE-BDC-2019-001/prompts/EXT-05.fact_extraction.json`（3681 B）
- `SHUFE-BDC-2019-001/prompts/EXT-06.claim_extraction.json`（3736 B）
- `SHUFE-BDC-2019-001/prompts/EXT-06.fact_extraction.json`（3652 B）
- `SHUFE-BDC-2019-001/prompts/EXT-07.claim_extraction.json`（3799 B）
- `SHUFE-BDC-2019-001/prompts/EXT-07.fact_extraction.json`（3715 B）
- `SHUFE-BDC-2019-001/prompts/EXT-08.claim_extraction.json`（3792 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/prompt_compile_report.yaml", "SHUFE-BDC-2019-001/prompts/*.json"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：{
  "documents": 21,
  "pass": 32,
  "FAIL": 10,
  "compiled": 42,
  "by_type": {
    "generic": 10,
    "national-standard": 26,
    "policy": 2,
    "feasibility-report": 4
  },
  "note": "识别不出类型的文档记 invalid 并落 generic —— 不猜；新增类型只需加 doc_types.yaml 条目与模板文件，不改代码"
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
