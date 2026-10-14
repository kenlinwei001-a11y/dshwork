# 环节 s5d 交接说明（README）

- 脚本：`s11_compliance.py`　退出码：0　耗时：0.43s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/external/compliance.yaml`（27064 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/external/compliance.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注："report": "引用标准名称"
    },
    {
      "binding": "B-13",
      "verdict": "合规",
      "report": "招标范围判定（表12-1）"
    },
    {
      "binding": "B-14",
      "verdict": "不合规",
      "report": "报告章节体系"
    },
    {
      "binding": "B-15",
      "verdict": "合规",
      "report": "引用标准时效"
    }
  ]
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
