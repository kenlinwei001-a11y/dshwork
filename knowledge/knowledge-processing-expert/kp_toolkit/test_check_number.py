# -*- coding: utf-8 -*-
"""写作查数 check_number_consistency 验证。

覆盖：bound/unbound 核实、口径存疑（流量/存量）、node 引用剥离、前后不一致信号。

运行：.venv/bin/python kp_toolkit/test_check_number.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kp_toolkit import check_number_consistency

FACTS = [
    {"id": "F1", "subject": "有效月产能", "predicate": "has_value", "value": 36, "unit": "GWh/月"},
    {"id": "F2", "subject": "建设投资", "predicate": "has_value", "value": 92664, "unit": "万元"},
    {"id": "F3", "subject": "月均需求", "predicate": "has_value", "value": 39, "unit": "GWh/月"},
]


def test_bound_unbound():
    draft = "有效月产能 36 GWh/月，建设投资 92664 万元。"
    r = check_number_consistency(draft, FACTS)
    assert r["numbers_found"] == 2
    assert r["bound"] == 2 and r["unbound"] == 0
    print("[OK] bound/unbound：数字与事实源核实正确")


def test_unbound_signals_inconsistency():
    draft = "有效月产能 36 GWh/月，但另一处写产能 40 GWh/月。"
    r = check_number_consistency(draft, FACTS)
    assert r["unbound"] == 1
    assert "产能" in r["unbound_list"][0]["context"], r["unbound_list"][0]
    print("[OK] unbound 数字带上下文，标记前后不一致信号")


def test_caliber_issue():
    """CF1 例子：流量（GWh/月）vs 存量（GWh）口径混淆。"""
    draft = "月均需求 39 GWh/月，但另一处写月均需求 39 GWh。"
    r = check_number_consistency(draft, FACTS)
    assert len(r["caliber_issues"]) == 1
    issue = r["caliber_issues"][0]
    assert issue["subject"] == "月均需求" and set(issue["units"]) == {"GWh", "GWh/月"}
    assert issue["status"] == "待审"
    print("[OK] 口径存疑：月均需求 GWh vs GWh/月（流量/存量）标记待审")


def test_node_ref_stripped():
    """node 引用 {{node:...}} 不应被当字面数字。"""
    draft = "建设投资 {{node:N-0018}} 万元。"
    r = check_number_consistency(draft, FACTS)
    # {{node:N-0018}} 里的 0018 不算字面数字
    assert all("node" not in n["context"] for n in r["unbound_list"])
    print("[OK] node 引用被剥离，不误判为字面数字")


def main() -> int:
    test_bound_unbound()
    test_unbound_signals_inconsistency()
    test_caliber_issue()
    test_node_ref_stripped()
    print("\n写作查数验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
