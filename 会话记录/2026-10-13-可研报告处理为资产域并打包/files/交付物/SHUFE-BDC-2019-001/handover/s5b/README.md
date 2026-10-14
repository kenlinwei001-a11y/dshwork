# 环节 s5b 交接说明（README）

- 脚本：`s7_anchors.py`　退出码：0　耗时：0.46s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/chunks/chunks.jsonl`（849892 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/chunks/chunks.jsonl"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：{
  "chunks": 1178,
  "skeletons": 1178,
  "anchored": 1178,
  "document_ids": [
    "SHUFE-BDC-2019-001"
  ],
  "distinct_sections": 145,
  "sample": {
    "id": "c-68e7c6cb89b3",
    "section_path": [
      "项目规划设计方案",
      "结构设计",
      "装配率及典型节点"
    ]
  }
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
