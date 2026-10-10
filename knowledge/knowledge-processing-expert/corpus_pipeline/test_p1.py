# -*- coding: utf-8 -*-
"""P1 验证：资产依赖图（影响传播）+ 三质量关口（QG1/QG2/QG3）。

运行：.venv/bin/python corpus_pipeline/test_p1.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.dependencies import (
    ASSET_DEPENDENCIES, impacted_assets, dependents_of, dependency_closure, check_cycles,
)
from corpus_pipeline.quality_gates import gate_qg1, gate_qg2, gate_qg3, run_all_gates

CORPUS = str(Path(__file__).resolve().parent.parent / "corpus-library" / "PX-2026-001-feasibility")


def test_dependency_graph_complete():
    assert len(ASSET_DEPENDENCIES) == 16
    assert check_cycles() == []  # 无环
    print("[OK] 依赖图：16 域齐全 + 无环")


def test_impacted_ontology():
    # ontology 是根，变更传播到全部 16 域
    impacted = impacted_assets("ontology")
    assert len(impacted) == 16, impacted
    print(f"[OK] ontology 变更 → 传播到全部 {len(impacted)} 域（根的影响覆盖全局）")


def test_impacted_variable():
    # variable 变更：直接影响 rule/invariant/scenario/function/cost_risk，间接影响 skill/task_dag/quality_gate/reuse_strategy/prompt
    impacted = impacted_assets("variable")
    assert "rule" in impacted and "function" in impacted and "cost_risk" in impacted
    assert "skill" in impacted and "task_dag" in impacted  # 间接传播
    assert "report_structure" not in impacted  # 报告结构不依赖变量
    print(f"[OK] variable 变更 → 影响 {len(impacted)} 域（含间接传播 skill/task_dag），不误伤 report_structure")


def test_dependency_closure():
    # task_dag 的依赖闭包
    closure = dependency_closure("task_dag")
    assert "ontology" in closure and "rule" in closure and "skill" in closure and "function" in closure
    print(f"[OK] task_dag 依赖闭包：{closure}")


def test_gate_qg1():
    r = gate_qg1(CORPUS)
    assert r["gate"] == "QG1" and r["passed"] is True
    print("[OK] QG1 来源可信度：demo 语料包通过（版本/指纹/锚点齐全）")


def test_gate_qg2():
    r = gate_qg2(CORPUS)
    assert r["gate"] == "QG2"
    print(f"[OK] QG2 语义完整性：passed={r['passed']}（Claim/关系/证据结构检查）")


def test_gate_qg3():
    r = gate_qg3(CORPUS)
    assert r["gate"] == "QG3" and r["passed"] is True
    print("[OK] QG3 资产可复用性：16 域齐全 + 依赖图无环 + 约束存在")


def test_run_all_gates():
    r = run_all_gates(CORPUS)
    assert len(r["gates"]) == 3
    assert r["all_passed"] is True, r["failed"]
    print(f"[OK] 三关口汇总：all_passed={r['all_passed']}")


def main() -> int:
    test_dependency_graph_complete()
    test_impacted_ontology()
    test_impacted_variable()
    test_dependency_closure()
    test_gate_qg1()
    test_gate_qg2()
    test_gate_qg3()
    test_run_all_gates()
    print("\nP1 验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
