# 环节 s5i 交接说明（README）

- 脚本：`s34_prompt_reuse.py`　退出码：0　耗时：1.45s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/prompt_reuse.yaml`（7049 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/prompt_reuse.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：EPORT-01.fact_extraction: 1178/1178 片未调用（无 provider）",
    "EXT-00.claim_extraction: 14/14 片未调用（无 provider）",
    "EXT-00.fact_extraction: 14/14 片未调用（无 provider）",
    "EXT-01.claim_extraction: 144/144 片未调用（无 provider）"
  ],
  "reuse_ok": true,
  "note": "提示词复用与逐片记录；not_invoked ⇒ invalid（不得视为通过）"
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
