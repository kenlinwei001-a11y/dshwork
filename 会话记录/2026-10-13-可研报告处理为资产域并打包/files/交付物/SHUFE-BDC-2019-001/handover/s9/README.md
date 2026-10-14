# 环节 s9 交接说明（README）

- 脚本：`s_sop_selfaudit.py`　退出码：0　耗时：1.15s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/decision_tickets.md`（313 B）
- `SHUFE-BDC-2019-001/quality/trigger_cards.md`（221 B）
- `SHUFE-BDC-2019-001/quality/trigger_cards.yaml`（446 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/decision_tickets.md", "SHUFE-BDC-2019-001/quality/trigger_cards.md", "SHUFE-BDC-2019-001/quality/trigger_cards.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：{
  "tickets": 0,
  "L1": 0,
  "L2": 0
}
{"in_chain": true, "note": "链内仅导出卡片；权威 L0 判定在链尾执行"}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
