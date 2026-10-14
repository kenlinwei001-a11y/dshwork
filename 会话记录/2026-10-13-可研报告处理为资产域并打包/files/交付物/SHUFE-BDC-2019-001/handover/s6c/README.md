# 环节 s6c 交接说明（README）

- 脚本：`s13_assets_ext.py`　退出码：0　耗时：0.37s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/style/section_prompts.yaml`（57587 B）
- `SHUFE-BDC-2019-001/reuse/regulatory_dependency.yaml`（7182 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/style/section_prompts.yaml", "SHUFE-BDC-2019-001/reuse/regulatory_dependency.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：[
      "note",
      "per_section_count",
      "per_section_file",
      "see_also"
    ],
    "quality_gate": [
      "basis_availability_grading",
      "mandatory_counts_separately",
      "see_also"
    ],
    "reuse_strategy": [
      "see_also",
      "soft_constraint_protocol"
    ]
  }
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
