# -*- coding: utf-8 -*-
"""s31 —— 用「更新后的知识处理专家」的门禁跑一遍（上游实现，非工作区副本）。

为什么单独一步：
  · 本工作区此前自带 opt25/26/27 的门禁实现（工作区副本）；
  · 更新后的 kp 工程已把这些机制并入上游（closure_verify / stage_gates /
    objective_criteria / verify_pipeline + providers_semantica）；
  · 本步改为**从上游导入并执行**，确保交付物里的门禁结论来自更新后的系统本体，
    而不是工作区副本——同时把 semantica provider 的能力证据一并落盘。

产出（均写入语料包 quality/）：
  verify_pipeline.yaml   合并判定
  closure_report.yaml    七道闭环
  stage_gates.yaml       S0–S11 分步门禁
  objective_verify.yaml  K1–K14 客观判据
  provider_probe.yaml    provider 能力来源（含 semantica 证据）
并调用 apply_manifest_gate 按状态机约束写 manifest.status。
"""
import json
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
ROOT = WS / "SHUFE-BDC-2019-001"
KP = Path("/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert")
sys.path.insert(0, str(KP))

from corpus_pipeline.verify_pipeline import apply_manifest_gate, verify_pipeline  # noqa: E402

DRAFT = WS / "交付物" / "报告" / "上海财经大学中山北一路校区大数据研究中心可行性研究报告（还原稿）.md"
SRC = WS / "build" / "doc-clean" / "大数据研究中心可研.md"
DOCX = WS / "build" / "source-original.docx"
man = json.loads((ROOT / "manifest.yaml").read_text(encoding="utf-8"))

res = verify_pipeline(
    str(ROOT),
    draft_path=str(DRAFT) if DRAFT.exists() else None,
    source_md=str(SRC) if SRC.exists() else None,
    source_docx=str(DOCX) if DOCX.exists() else None,
    compile_point="2019-08",
    declared_sha256=man.get("source_original_sha256", ""),
)
gate = apply_manifest_gate(str(ROOT), res)

print(json.dumps({"verdict": res["verdict"], "blocking": res["blocking_count"],
                  "invalid": res["invalid_count"],
                  "closure": res["closure"], "stage_gates": res["stage_gates"],
                  "objective": res["objective"], "manifest": gate},
                 ensure_ascii=False, indent=2))
