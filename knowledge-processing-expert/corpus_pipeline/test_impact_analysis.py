# -*- coding: utf-8 -*-
"""16 域依赖联动扩展验证（P1 第二项）。

验证 analyze_schema_impact：Schema Diff → 16 资产域影响分析 + 装配动作。

运行：.venv/bin/python corpus_pipeline/test_impact_analysis.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.schema_diff import diff_schemas, analyze_schema_impact

# 16 域 id（与 full_emit.DOMAIN_SPECS 一致）
DOMAINS = ["ontology", "argument_chain", "scenario", "variable", "task_dag", "function",
           "rule", "invariant", "skill", "report_structure", "report_form", "prompt",
           "quality_gate", "reuse_strategy", "entity_relation", "cost_risk"]


def test_claim_addition_impact():
    """文档第三节案例：新项目多 claims 字段 → 触发跨域联动。"""
    old = {"project_name": {"type": "string"}, "facts": {"type": "array"}}
    new = {**old, "claims": {"type": "array"}}
    diffs = diff_schemas(old, new)
    impact = analyze_schema_impact(diffs)

    # 受影响（yes）的域
    yes_domains = {"ontology", "argument_chain", "task_dag", "rule", "skill",
                   "report_form", "prompt", "quality_gate", "reuse_strategy", "entity_relation"}
    # 视情况（conditional）的域
    cond_domains = {"scenario", "variable", "function", "invariant", "report_structure", "cost_risk"}

    for d in DOMAINS:
        assert d in impact, f"缺域 {d}"
        if d in yes_domains:
            assert impact[d]["affected"] == "yes", f"{d} 应为 yes，实际 {impact[d]['affected']}"
        elif d in cond_domains:
            assert impact[d]["affected"] == "conditional", f"{d} 应为 conditional，实际 {impact[d]['affected']}"
    # 装配动作非空
    assert all(impact[d]["action"] for d in yes_domains)
    print("[OK] Claim 新增：10 域 yes + 6 域 conditional，装配动作齐全")


def test_type_changed_impact():
    """无 Claim，仅类型变化：只影响 ontology/variable，不波及全部 16 域。"""
    diffs = diff_schemas({"claims": {"type": "string"}}, {"claims": {"type": "array"}})
    impact = analyze_schema_impact(diffs)
    assert impact["ontology"]["affected"] == "yes"       # 类型变化 → 兼容性检查
    assert impact["variable"]["affected"] == "yes"
    assert impact["report_form"]["affected"] == "no"     # 类型变化不等于新增字段
    # 不因类型变化判整个模板失效
    yes_count = sum(1 for d in DOMAINS if impact[d]["affected"] == "yes")
    assert yes_count == 2, f"类型变化只应影响 2 域，实际 {yes_count}"
    print("[OK] 类型变化：仅 ontology/variable 受影响，不判整模板失效")


def test_no_change():
    """无差异：16 域全部 no/conditional，不做无谓装配。"""
    diffs = diff_schemas({"facts": {"type": "array"}}, {"facts": {"type": "array"}})
    impact = analyze_schema_impact(diffs)
    assert not any(impact[d]["affected"] == "yes" for d in DOMAINS)
    print("[OK] 无差异：不触发任何 yes 装配")


def main() -> int:
    test_claim_addition_impact()
    test_type_changed_impact()
    test_no_change()
    print("\n16 域依赖联动扩展验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
