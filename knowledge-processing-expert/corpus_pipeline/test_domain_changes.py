# -*- coding: utf-8 -*-
"""16 域自动装配变更集验证（P1 执行层）。

验证 assemble_domain_changes：对「新增 Claim」，为 10 个 yes 域生成具体变更内容，
6 个 conditional 域按条件（默认 None）。

运行：.venv/bin/python corpus_pipeline/test_domain_changes.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.ontology_schema import assemble_domain_changes
from corpus_pipeline.schema_diff import diff_schemas

DOMAINS = ["ontology", "argument_chain", "scenario", "variable", "task_dag", "function",
           "rule", "invariant", "skill", "report_structure", "report_form", "prompt",
           "quality_gate", "reuse_strategy", "entity_relation", "cost_risk"]

YES_DOMAINS = {"ontology", "argument_chain", "task_dag", "rule", "skill",
               "report_form", "prompt", "quality_gate", "reuse_strategy", "entity_relation"}
COND_DOMAINS = {"scenario", "variable", "function", "invariant", "report_structure", "cost_risk"}


def test_claim_changes_full_16_domains():
    diffs = diff_schemas({"facts": {"type": "array"}}, {"facts": {"type": "array"}, "claims": {"type": "array"}})
    r = assemble_domain_changes(diffs)
    assert r["changed"] is True
    changes = r["changes"]
    assert set(changes.keys()) == set(DOMAINS), "16 域不齐"
    # yes 域有具体内容（非 None），conditional 域为 None
    for d in YES_DOMAINS:
        assert changes[d] is not None, f"{d} 应有具体变更集"
    for d in COND_DOMAINS:
        assert changes[d] is None, f"{d} 应为 None（视情况）"
    print("[OK] 16 域齐备：10 个 yes 域有具体变更，6 个 conditional 域为 None")


def test_yes_domains_concrete():
    diffs = diff_schemas({"facts": {"type": "array"}}, {"facts": {"type": "array"}, "claims": {"type": "array"}})
    changes = assemble_domain_changes(diffs)["changes"]
    # 本体：Claim 类 + 属性 + 约束
    assert any(c["name"] == "Claim" for c in changes["ontology"]["classes"])
    assert any(p["name"] == "has_evidence" for p in changes["ontology"]["properties"])
    # 任务 DAG：3 个任务节点 + 依赖
    assert len(changes["task_dag"]["new_tasks"]) == 3
    assert changes["task_dag"]["new_tasks"][2]["deps"] == ["claim_link"]
    # 质量闸门：5 个校验项
    assert len(changes["quality_gate"]["new_checks"]) == 5
    # 规则库：3 条规则
    assert len(changes["rule"]["new_rules"]) == 3
    # 实体关系：Claim 实体 + 3 条关系
    assert "Claim" in changes["entity_relation"]["new_entities"]
    assert len(changes["entity_relation"]["new_relations"]) == 3
    # 复用策略：决策 + 原因
    assert changes["reuse_strategy"]["decision"] and changes["reuse_strategy"]["reason"]
    print("[OK] yes 域变更集是具体内容（任务节点/校验项/规则/关系），非动作描述")


def test_no_claim():
    diffs = diff_schemas({"facts": {"type": "array"}}, {"facts": {"type": "array"}, "unit_price": {"type": "number"}})
    r = assemble_domain_changes(diffs)
    assert r["changed"] is False
    print("[OK] 无 Claim 新增 → 不生成变更集")


def main() -> int:
    test_claim_changes_full_16_domains()
    test_yes_domains_concrete()
    test_no_claim()
    print("\n16 域自动装配变更集验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
