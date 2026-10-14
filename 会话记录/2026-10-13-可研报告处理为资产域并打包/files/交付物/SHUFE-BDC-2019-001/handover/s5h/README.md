# 环节 s5h 交接说明（README）

- 脚本：`s1d_extract_driven.py`　退出码：0　耗时：0.82s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/extraction_runs/_summary.json`（10028 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/DOC-REPORT-01.claim_extraction.jsonl`（426426 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/DOC-REPORT-01.fact_extraction.jsonl`（425248 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-00.claim_extraction.jsonl`（4830 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-00.fact_extraction.jsonl`（4816 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-01.claim_extraction.jsonl`（51347 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-01.fact_extraction.jsonl`（51203 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-02.claim_extraction.jsonl`（5329 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-02.fact_extraction.jsonl`（5314 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-03.claim_extraction.jsonl`（69041 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-03.fact_extraction.jsonl`（68841 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-04.claim_extraction.jsonl`（19899 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-04.fact_extraction.jsonl`（19843 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-05.claim_extraction.jsonl`（22385 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-05.fact_extraction.jsonl`（22322 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-06.claim_extraction.jsonl`（13459 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-06.fact_extraction.jsonl`（13420 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-07.claim_extraction.jsonl`（1776 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-07.fact_extraction.jsonl`（1771 B）
- `SHUFE-BDC-2019-001/quality/extraction_runs/EXT-08.claim_extraction.jsonl`（13496 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/extraction_runs/_summary.json", "SHUFE-BDC-2019-001/quality/extraction_runs/DOC-REPORT-01.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/DOC-REPORT-01.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-00.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-00.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-01.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-01.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-02.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-02.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-03.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-03.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-04.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-04.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-05.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-05.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-06.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-06.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-07.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-07.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-08.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-08.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-09.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-09.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-10.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-10.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-11.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-11.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-12.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-12.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-13.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-13.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-14.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-14.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-15.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-15.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-16.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-16.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-17.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-17.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-18.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-18.fact_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-19.claim_extraction.jsonl", "SHUFE-BDC-2019-001/quality/extraction_runs/EXT-19.fact_extraction.jsonl"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：: 14,
      "prompt_sha256": "ff34b6a8438428d9b41b55ad3299b3ab"
    },
    {
      "doc_id": "EXT-01",
      "task": "fact_extraction",
      "chunks": 144,
      "distinct_prompt_sha256": 1,
      "invoked": 0,
      "not_invoked": 144,
      "prompt_sha256": "c134312909496a3dd9eb9f83f9bf2d7e"

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
