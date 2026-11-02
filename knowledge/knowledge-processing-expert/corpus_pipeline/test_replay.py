# -*- coding: utf-8 -*-
"""replay（改稿后推演链重放）回归测试。"""
from __future__ import annotations
from .replay import replay_changes, build_reverse_index, build_label_index, parse_added_facts, _recompute


def _graph():
    return {"items": {
        "facts": [
            {"id": "N-a", "subject": "人数", "value": 1800, "section": "§1"},
            {"id": "N-b", "subject": "定额", "value": 40, "section": "§1"},
            {"id": "N-c", "subject": "日用水量", "value": 72000, "section": "§2"},
            {"id": "N-d", "subject": "年用水量", "value": 26280, "section": "§3"},
        ],
        "reasoning": [
            {"id": "R1", "desc": "R1 → 日用水量", "formula": "{人数}*{定额}",
             "inputs": ["N-a", "N-b"], "output": "N-c", "section": "§2", "result": 72000},
            {"id": "R2", "desc": "R2 → 年用水量", "formula": "{日用水量}*365/1000",
             "inputs": ["N-c"], "output": "N-d", "section": "§3", "result": 26280},
        ],
        "entities": [], "relations": [], "claims": [], "evidence": [], "conflicts": [], "validations": [],
    }}


def _graph_missing_dep():
    """定额缺失（UNDEFINED）：R1 的 inputs 只绑了 N-a，deps_labels 标「定额」未绑定。"""
    return {"items": {
        "facts": [
            {"id": "N-a", "subject": "人数", "value": 1800, "section": "§1"},
            {"id": "N-c", "subject": "日用水量", "value": None, "status": "undefined", "section": "§2"},
        ],
        "reasoning": [
            {"id": "R1", "desc": "R1 → 日用水量", "formula": "{人数}*{定额}",
             "inputs": ["N-a"], "deps_labels": ["定额"], "output": "N-c", "section": "§2", "result": None},
        ],
        "entities": [], "relations": [], "claims": [], "evidence": [], "conflicts": [], "validations": [],
    }}


def test_reverse_index():
    rev = build_reverse_index(_graph()["items"])
    assert rev["N-a"] == [("R1", "N-c")], rev
    assert rev["N-c"] == [("R2", "N-d")], rev
    print("[OK] 反向依赖索引：N-a→R1、N-c→R2")


def test_label_index():
    lrev = build_label_index(_graph_missing_dep()["items"])
    assert lrev["定额"] == ["R1"], lrev
    assert lrev["人数"] == ["R1"], lrev
    print("[OK] 标签反向索引：定额/人数 → R1（含未绑定输入）")


def test_parse_added_facts():
    parsed = parse_added_facts([{"action": "add", "id": "X", "text": "学生用水定额为 40 L/生·日。"}])
    assert parsed and parsed[0]["subject"] == "学生用水定额" and parsed[0]["value"] == 40, parsed
    print(f"[OK] 新增文本解析 → {parsed[0]['subject']}={parsed[0]['value']}{parsed[0]['unit']}")


def test_recompute():
    facts = _graph()["items"]["facts"]
    v, missing = _recompute("{人数}*{定额}", facts, {"人数": 2000})
    assert v == 80000.0 and not missing, (v, missing)
    v2, m2 = _recompute("{人数}*{系数}", facts, {})
    assert v2 is None and "系数" in m2, (v2, m2)
    print("[OK] 重算：{标签}→v0/v1 约定 + 缺输入待补")


def test_edit_number_propagates():
    r = replay_changes(_graph(), [{"action": "edit_number", "id": "N-a", "value": 2000}])
    assert set(r["affected_sections"]) == {"§2", "§3"}, r
    assert len(r["replay_plan"]) == 2, r
    assert r["replay_plan"][0]["recomputed"] == 80000.0
    assert r["replay_plan"][1]["recomputed"] == 29200.0  # 链式：下游用重算后的新值
    assert all(p["note"] == "重算值与原文不一致 → 待审" for p in r["replay_plan"])
    print(f"[OK] 改数传播 → {r['summary']}")


def test_add_fact_fills_missing_dep():
    """新增事实补上规则缺的输入 → 该规则重算并传播下游（新节点有下游的典型场景）。"""
    r = replay_changes(_graph_missing_dep(),
                       [{"action": "add", "id": "N-new", "text": "学生用水定额为 40。"}])
    assert len(r["replay_plan"]) == 1, r
    p = r["replay_plan"][0]
    assert p["reasoning"] == "R1" and p["recomputed"] == 72000.0, p
    assert p["note"] == "重算一致" or "不一致" in p["note"], p
    assert "N-c" in r["affected_nodes"]
    print(f"[OK] 新增事实补缺 → R1 重算 {p['recomputed']} → {r['summary']}")


def test_delete_downgrades():
    r = replay_changes(_graph(), [{"action": "delete", "id": "N-b"}])
    assert len(r["downgraded"]) == 1 and r["downgraded"][0]["reasoning"] == "R1", r
    assert "§2" in r["affected_sections"]
    print(f"[OK] 删除降级 → {r['summary']}")


def test_move_reorders():
    r = replay_changes(_graph(), [{"action": "move_block", "id": "N-b",
                                   "anchor_before": {"line": 2}, "anchor_after": {"line": 20}}])
    assert any(p["kind"] == "叙述顺序重放" for p in r["replay_plan"]), r
    print(f"[OK] 移动位置 → {r['summary']}")


if __name__ == "__main__":
    test_reverse_index()
    test_label_index()
    test_parse_added_facts()
    test_recompute()
    test_edit_number_propagates()
    test_add_fact_fills_missing_dep()
    test_delete_downgrades()
    test_move_reorders()
    print("replay 全部通过 ✓")
