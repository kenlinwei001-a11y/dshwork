# 环节 s6 交接说明（README）

- 脚本：`s6_domains.py`　退出码：0　耗时：0.83s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/reuse/domains.yaml`（54955 B）
- `SHUFE-BDC-2019-001/reuse/domains/01-ontology.yaml`（8030 B）
- `SHUFE-BDC-2019-001/reuse/domains/02-argument_chain.yaml`（7502 B）
- `SHUFE-BDC-2019-001/reuse/domains/03-scenario.yaml`（10560 B）
- `SHUFE-BDC-2019-001/reuse/domains/04-variable.yaml`（14459 B）
- `SHUFE-BDC-2019-001/reuse/domains/05-task_dag.yaml`（4821 B）
- `SHUFE-BDC-2019-001/reuse/domains/06-function.yaml`（7975 B）
- `SHUFE-BDC-2019-001/reuse/domains/07-rule.yaml`（7845 B）
- `SHUFE-BDC-2019-001/reuse/domains/08-invariant.yaml`（14831 B）
- `SHUFE-BDC-2019-001/reuse/domains/09-skill.yaml`（5963 B）
- `SHUFE-BDC-2019-001/reuse/domains/10-report_structure.yaml`（6139 B）
- `SHUFE-BDC-2019-001/reuse/domains/11-report_form.yaml`（6476 B）
- `SHUFE-BDC-2019-001/reuse/domains/12-prompt.yaml`（4790 B）
- `SHUFE-BDC-2019-001/reuse/domains/13-quality_gate.yaml`（17074 B）
- `SHUFE-BDC-2019-001/reuse/domains/14-reuse_strategy.yaml`（9806 B）
- `SHUFE-BDC-2019-001/reuse/domains/15-entity_relation.yaml`（5482 B）
- `SHUFE-BDC-2019-001/reuse/domains/16-cost_risk.yaml`（9126 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/reuse/domains.yaml", "SHUFE-BDC-2019-001/reuse/domains/*.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：悬空 — 悬空 0 条
  [FAIL] 关系合法（只用十类关系） — 非法 81 条 / 共 553 条
  [FAIL] 孤立节点 — 449/959 个节点未出现在任何关系中（多为源数据类气象/水文参数）
  [PASS] 跨项目污染：未注入产线类领域规则 — 建库时显式不传 doc_type，避免 kp 内置「新增生产线数量/合格产能」规格注入本域
  [PASS] 报告技术函数与外部依据的绑定完整（每条绑定有 role 与 why） — 15 条绑定；角色分布 {"benchmark": 5, "constrains": 6, "driver": 1, "warrants": 3}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
