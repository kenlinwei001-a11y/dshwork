# 环节 s4c 交接说明（README）

- 脚本：`s4c_semantics.py`　退出码：0　耗时：0.25s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/semantic_dims.yaml`（855 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/semantic_dims.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：未命中规则，**不猜测**"
}
  object_role: [('unknown', 263), ('估算值', 53), ('指标值', 21), ('需求值', 17)]
  domain: [('unknown', 226), ('结构', 31), ('给排水', 28), ('暖通·冷负荷', 25)]
  caliber_direction: [('等于', 289), ('unknown', 58), ('区间', 13), ('下限', 6)]
  hierarchy_path: [('不适用', 317), ('unknown', 38), ('建安工程费', 15)]

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
