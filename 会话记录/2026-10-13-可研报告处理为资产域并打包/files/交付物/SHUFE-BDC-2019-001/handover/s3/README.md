# 环节 s3 交接说明（README）

- 脚本：`s4_pipeline.py`　退出码：0　耗时：2.03s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/manifest.yaml`（5351 B）
- `SHUFE-BDC-2019-001/graph/nodes.yaml`（97896 B）
- `SHUFE-BDC-2019-001/chunks/chunks.jsonl`（279822 B）
- `SHUFE-BDC-2019-001/reasoning/trace.jsonl`（450 B）
- `SHUFE-BDC-2019-001/source/original.docx`（1123286 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/manifest.yaml", "SHUFE-BDC-2019-001/graph/nodes.yaml", "SHUFE-BDC-2019-001/chunks/chunks.jsonl", "SHUFE-BDC-2019-001/reasoning/trace.jsonl", "SHUFE-BDC-2019-001/source/original.docx"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：.md（由 build/source-original.docx 确定性重推）",
  "extractions_loaded": 95,
  "chunks": 1178,
  "facts": 358,
  "rules": 35,
  "claims": 28,
  "evidence": 127,
  "relations": 466,
  "conflicts": 2,
  "outline_missing_legal_items": 35,
  "gate": "REVIEW",
  "skeletons": 1178,
  "desensitized_nodes": 347
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
