"""kp_toolkit 确定性自测（同输入同输出、可复现）。"""
from kp_toolkit import (
    segment_sentences, segment_chunks,
    compile_graph, validate_graph,
    detect_numeric_conflicts, detect_time_conflicts,
    build_provenance, validate_schema,
)


def test_segment_deterministic():
    t = "2024年营收为100亿元。同比增长20%；净利润12.5亿元。"
    a = segment_sentences(t)
    b = segment_sentences(t)
    assert a == b, "同输入必须同输出"
    assert len(a) >= 2


def test_graph_validation():
    items = {
        "facts": [{"id": "f1", "subject": "营收", "predicate": "等于", "value": "100亿元"}],
        "claims": [{"id": "c1", "text": "营收增长", "evidence": ["f1"]}],
        "relations": [{"id": "r1", "from": "c1", "to": "ghost"}],  # 悬空引用
    }
    g = compile_graph(items, "p1", "v1")
    r = validate_graph(g)
    assert r["ok"] is False
    assert any("ghost" in e for e in r["errors"])


def test_numeric_conflict():
    facts = [
        {"id": "f1", "subject": "营收", "predicate": "等于", "value": "100亿元"},
        {"id": "f2", "subject": "营收", "predicate": "等于", "value": "120亿元"},
    ]
    c = detect_numeric_conflicts(facts)
    assert len(c) == 1 and c[0]["status"] == "待审"


def test_provenance():
    items = {
        "facts": [{"id": "f1", "source": "doc1:p3"}],
        "claims": [{"id": "c1", "evidence": ["f1"]}],
    }
    g = compile_graph(items, "p1", "v1")
    chain = build_provenance("c1", g)
    assert [c["id"] for c in chain] == ["c1", "f1"]


def test_schema():
    r = validate_schema([{"id": "e1", "name": "X"}], "entity")
    assert r["ok"] is False  # 缺 type


if __name__ == "__main__":
    test_segment_deterministic()
    test_graph_validation()
    test_numeric_conflict()
    test_provenance()
    test_schema()
    print("ALL TESTS PASSED")
