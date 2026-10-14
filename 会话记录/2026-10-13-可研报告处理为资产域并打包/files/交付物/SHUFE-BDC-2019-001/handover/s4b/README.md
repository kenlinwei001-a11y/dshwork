# 环节 s4b 交接说明（README）

- 脚本：`s4b_fill_dedup.py`　退出码：0　耗时：0.23s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/fill_dedup_report.json`（6439 B）
- `SHUFE-BDC-2019-001/graph/graph.yaml`（233810 B）
- `SHUFE-BDC-2019-001/graph/nodes.yaml`（103522 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/fill_dedup_report.json", "SHUFE-BDC-2019-001/graph/graph.yaml", "SHUFE-BDC-2019-001/graph/nodes.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：: "区间端点（该区间已建模为一条区间事实 0.5~1.5 米）",
      "1.5": "区间端点（该区间已建模为一条区间事实 0.5~1.5 米）",
      "0.06": "区间端点（该区间已建模为一条区间事实 0.06~0.08 米/昼夜）",
      "0.08": "区间端点（该区间已建模为一条区间事实 0.06~0.08 米/昼夜）",
      "0.04": "区间端点（该区间已建模为一条区间事实 0.04~0.11 米/昼夜）",
      "0.11": "区间端点（该区间已建模为一条区间事实 0.04~0.11 米/昼夜）"
    }
  }
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
