# 环节 s4 交接说明（README）

- 脚本：`s5_replay.py`　退出码：0　耗时：0.14s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/reasoning/decisions.yaml`（8162 B）
- `SHUFE-BDC-2019-001/reasoning/derivation.yaml`（17578 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/reasoning/decisions.yaml", "SHUFE-BDC-2019-001/reasoning/derivation.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：阻塞依赖: 本项目建筑面积=18219/18319
  R-单位面积综合能耗                   阻塞依赖: 本项目建筑面积=18219/18319
  R-单位建筑面积电耗                   阻塞依赖: 本项目建筑面积=18219/18319
  R-单位造价                       阻塞依赖: 本项目建筑面积=18219/18319
--- 因缺事实而未解析的规则 ---
  R-总计算负荷                      缺: ['负荷估算面积口径']
--- 缺口登记 quality/gaps.yaml：13 条 ---

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
