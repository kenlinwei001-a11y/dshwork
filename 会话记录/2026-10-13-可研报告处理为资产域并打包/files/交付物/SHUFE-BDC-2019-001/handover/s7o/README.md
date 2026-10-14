# 环节 s7o 交接说明（README）

- 脚本：`calibrate_handover_c.py`　退出码：0　耗时：2.55s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/calibration_handover_c.json`（687 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/calibration_handover_c.json"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：eline": 0.0,
  "verdict": "NOT_CALIBRATED"
}
  ✅ 基线（未注入）                                        期望 不命中                      实际 0
  ❌ 注入：manifest=validated 且 verdict=blocked        期望 命中 C_internal_contradiction 实际 0
  ❌ 注入：产物自述 count 偏 +7                             期望 命中 C_self_inconsistent   实际 0

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
