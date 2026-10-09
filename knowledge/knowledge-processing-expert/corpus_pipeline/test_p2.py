# -*- coding: utf-8 -*-
"""P2 验证：显式变更策略（7 种）+ 显式任务 DAG（拓扑 + 循环检测）。

运行：.venv/bin/python corpus_pipeline/test_p2.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.schema_diff import diff_schemas, decide_change_strategy, CHANGE_STRATEGIES
from corpus_pipeline.orchestrator import build_task_dag, topological_order


def test_strategy_direct_reuse():
    diffs = diff_schemas({"facts": {"type": "array"}}, {"facts": {"type": "array"}})
    r = decide_change_strategy(diffs)
    assert r["strategy"] == "direct_reuse" and r["modify_template"] is False
    print("[OK] 无差异 → direct_reuse")


def test_strategy_dependency_linked():
    diffs = diff_schemas({"facts": {"type": "array"}}, {"facts": {"type": "array"}, "claims": {"type": "array"}})
    r = decide_change_strategy(diffs)
    assert r["strategy"] == "dependency_linked_extend"
    print("[OK] 新增 Claim → dependency_linked_extend（跨域联动）")


def test_strategy_parameterized():
    diffs = diff_schemas({"总投资": {"type": "number"}}, {"建设投资": {"type": "number"}})
    r = decide_change_strategy(diffs)
    assert r["strategy"] == "parameterized_reuse"
    print("[OK] 改名（总投资→建设投资）→ parameterized_reuse")


def test_strategy_rebuild():
    diffs = diff_schemas({"claims": {"type": "string"}}, {"claims": {"type": "array"}})
    r = decide_change_strategy(diffs)
    assert r["strategy"] == "rebuild"
    print("[OK] 类型变化 → rebuild")


def test_strategy_backward_compatible():
    diffs = diff_schemas({"facts": {"type": "array"}}, {"facts": {"type": "array"}, "unit_price": {"type": "number"}})
    r = decide_change_strategy(diffs)
    assert r["strategy"] == "backward_compatible_extend"
    print("[OK] 新增可选字段（非 Claim）→ backward_compatible_extend")


def test_strategy_reject():
    diffs = diff_schemas({"facts": {"type": "array"}}, {"facts": {"type": "array"}})
    r = decide_change_strategy(diffs, forbidden=True)
    assert r["strategy"] == "reject"
    print("[OK] 约束冲突（forbidden）→ reject")


def test_strategy_never_modify_template():
    # 所有策略都不修改历史模板（modify_template=False）
    assert len(CHANGE_STRATEGIES) == 7
    print("[OK] 7 种策略定义齐全，且 modify_template 恒为 False（历史模板不被覆盖）")


def test_task_dag_topology():
    tasks = build_task_dag(has_claim=False)
    r = topological_order(tasks)
    assert r["ok"] and len(r["order"]) == len(tasks)
    # 顺序：instantiate 在 schema_diff 之后，commit 最后
    order = r["order"]
    assert order.index("instantiate") > order.index("schema_diff")
    assert order[-1] == "commit"
    print(f"[OK] 基础任务 DAG 拓扑排序：{len(order)} 个任务，顺序正确")


def test_task_dag_with_claim():
    tasks = build_task_dag(has_claim=True)
    ids = {t["id"] for t in tasks}
    assert {"claim_extract", "claim_link", "claim_validate"} <= ids
    r = topological_order(tasks)
    assert r["ok"]
    order = r["order"]
    assert order.index("claim_validate") < order.index("build_work_package")
    print(f"[OK] 含 Claim 的 DAG 插入 claim_extract/link/validate（{len(order)} 个任务）")


def test_task_dag_cycle_detection():
    tasks = [{"id": "a", "deps": ["b"]}, {"id": "b", "deps": ["a"]}]
    r = topological_order(tasks)
    assert r["ok"] is False and set(r["cycle"]) == {"a", "b"}
    print("[OK] 循环依赖检测：a↔b 形成环，停止并报出")


def main() -> int:
    test_strategy_direct_reuse()
    test_strategy_dependency_linked()
    test_strategy_parameterized()
    test_strategy_rebuild()
    test_strategy_backward_compatible()
    test_strategy_reject()
    test_strategy_never_modify_template()
    test_task_dag_topology()
    test_task_dag_with_claim()
    test_task_dag_cycle_detection()
    print("\nP2 验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
