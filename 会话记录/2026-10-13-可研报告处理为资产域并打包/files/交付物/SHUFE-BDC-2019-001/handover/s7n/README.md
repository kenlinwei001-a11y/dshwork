# 环节 s7n 交接说明（README）

- 脚本：`s35_semantic_criteria.py`　退出码：0　耗时：0.73s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/semantic_criteria.yaml`（12424 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/semantic_criteria.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：命中 3
  ❌ K16 归属汇总一致（通用表内对账）               命中 5
  ❌ K17 口径方向（上限不得当最低需求）              命中 1
  ❌ K18 专业域匹配（跨域不得替代）                命中 1
  ✅ K19 对象角色区分与舍入等价                  命中 3
  ❌ K20 级联撤销（基础判据撤销则下游结论连带撤销）        命中 7
  ❌ K21 生成侧一致性（同节 prose 参数 vs 表格参数   命中 4
  ❌ K22 探针标定门禁（未标定不得采信）              命中 1

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
