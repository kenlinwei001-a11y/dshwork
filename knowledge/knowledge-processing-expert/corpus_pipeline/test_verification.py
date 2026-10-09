# -*- coding: utf-8 -*-
"""装配侧验证工具测试（空白 A 的三个 MCP 工具）。

覆盖：check_requirements（需求完备性）、sensitivity_analysis（敏感性）、validate_shacl（SHACL 约束）。

运行：.venv/bin/python corpus_pipeline/test_verification.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.verification import check_requirements, sensitivity_analysis, validate_shacl
from corpus_pipeline.domain_rules import FEASIBILITY_VARIABLES

CORPUS = str(Path(__file__).resolve().parent.parent / "corpus-library" / "PX-2026-001-feasibility")

# 敏感性分析用的小样本（避免跑全部 19 个变量 × 2 次装配）
SAMPLE_FACTS = [
    {"label": "新增生产线数量", "value": 2, "unit": "条"},
    {"label": "每年工作日", "value": 250, "unit": "天"},
    {"label": "单线毛产出速率", "value": 100, "unit": "套/小时"},
    {"label": "最终合格率", "value": 97, "unit": "%"},
]


def test_check_requirements():
    provided = [{"label": "新增生产线数量", "value": 2}]
    r = check_requirements(provided)
    assert r["complete"] is False
    assert r["total_required"] == len(FEASIBILITY_VARIABLES)
    # 缺失 = 总必需 - 已提供（"新增生产线数量" 提供了，其余缺）
    missing_fields = {m["field"] for m in r["missing"]}
    assert "每年工作日" in missing_fields and "新增生产线数量" not in missing_fields
    assert "project_goal" in missing_fields  # 无项目目标
    print(f"[OK] check_requirements：19 必需变量中缺 {len(r['missing'])} 项（含 project_goal）")

    # 全部提供 → complete
    full = [{"label": v} for v in FEASIBILITY_VARIABLES]
    r2 = check_requirements(full, project_goal="可研报告")
    assert r2["complete"] is True
    print("[OK] check_requirements：全部提供 + 目标 → complete")


def test_sensitivity_analysis():
    r = sensitivity_analysis(CORPUS, SAMPLE_FACTS, delta_ratio=0.1)
    assert "variables" in r and "sensitive_variables" in r
    # 每个变量都有 derived_changes（派生值变化）
    assert all("derived_changes" in v for v in r["variables"])
    # 至少有一个变量被标记（敏感或不敏感都合法，只验证结构）
    labels = {v["label"] for v in r["variables"]}
    assert labels == {f["label"] for f in SAMPLE_FACTS}
    print(f"[OK] sensitivity_analysis：{len(r['variables'])} 变量，敏感变量={r['sensitive_variables']}")


def test_validate_shacl():
    nodes = [
        {"id": "C1", "claim_type": "fact", "status": "unverified", "text": "合法"},
        {"id": "C2", "claim_type": "bogus", "status": "unverified", "text": "非法类型"},
        {"id": "C3", "claim_type": "hypothesis", "status": "unverified"},  # 缺 text
    ]
    r = validate_shacl(nodes)
    assert r["checked"] == 3 and r["valid"] is False
    viol = {(v["node"], v["property"]) for v in r["violations"]}
    assert ("C2", "claim_type") in viol and ("C3", "text") in viol
    assert ("C1", "claim_type") not in viol
    print(f"[OK] validate_shacl：3 节点，检出 {len(r['violations'])} 处违规（非法枚举 + 缺 text）")

    # 全合法 → valid
    good = [{"id": "C1", "claim_type": "fact", "status": "unverified", "text": "ok"}]
    assert validate_shacl(good)["valid"] is True
    print("[OK] validate_shacl：合法节点 → valid")


def main() -> int:
    test_check_requirements()
    test_sensitivity_analysis()
    test_validate_shacl()
    print("\n装配侧验证工具测试通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
