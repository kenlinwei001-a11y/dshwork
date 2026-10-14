# 环节 s7i 交接说明（README）

- 脚本：`opt27_objective.py`　退出码：0　耗时：1.08s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/objective_verify_workarea.yaml`（6086 B）
- `SHUFE-BDC-2019-001/quality/objective_criteria_workarea.yaml`（3661 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/objective_verify_workarea.yaml", "SHUFE-BDC-2019-001/quality/objective_criteria_workarea.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注："pass",
      0
    ],
    "K10": [
      "FAIL",
      29
    ],
    "K11": [
      "FAIL",
      2
    ],
    "K12": [
      "pass",
      0
    ]
  },
  "pass": 8,
  "judgment_required": [
    "还原稿「论证质量优于原稿」",
    "评估报告中的「影响度 高/中/低」",
    "「压缩过程性记述是可接受的取舍」"
  ],
  "out": "交付物/报告/客观verify标准.md"
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
