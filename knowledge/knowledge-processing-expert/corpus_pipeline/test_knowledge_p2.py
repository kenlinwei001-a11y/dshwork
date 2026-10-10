# -*- coding: utf-8 -*-
"""P2 验证：知识≠能力双路径 + 跨文档实体注册表 + SourceAnchor 精细化。

运行：.venv/bin/python corpus_pipeline/test_knowledge_p2.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.capability import (
    classify_origin, assess_capability, capability_summary, ASSET_ORIGIN,
)
from corpus_pipeline.entity_registry import (
    validate_source_anchor, EntityRegistry, SOURCE_ANCHOR_FIELDS,
)


def test_classify_origin():
    # 有可执行定义 → registered（真实能力）
    assert classify_origin({"id": "rule", "expr": "x+y", "formula": "..."}) == "registered"
    assert classify_origin({"id": "fn", "code": "def f():..."}) == "registered"
    # 只有描述/模式 → induced（候选方法）
    assert classify_origin({"id": "pattern", "description": "论证模式"}) == "induced"
    assert classify_origin({"id": "claim", "pattern": "目标→理由→证据"}) == "induced"
    assert len(ASSET_ORIGIN) == 2
    print("[OK] classify_origin：有 formula/code → registered；仅描述 → induced")


def test_assess_capability():
    domains = [
        {"id": "rule", "expr": "f(x)"},
        {"id": "argument_chain", "description": "论证模式", "pattern": "目标→理由"},
    ]
    assess = assess_capability(domains)
    assert assess["rule"]["origin"] == "registered" and assess["rule"]["actionable"] is True
    assert assess["argument_chain"]["origin"] == "induced" and assess["argument_chain"]["actionable"] is False
    s = capability_summary(assess)
    assert s["registered_count"] == 1 and s["induced_count"] == 1 and s["actionable"] is False
    print("[OK] assess_capability：区分「登记能力」与「候选方法」，含候选缺口时 actionable=False")


def test_source_anchor():
    # 完整锚点（含 table_cell）
    good = {"document_id": "D1", "table_cell": "B3", "section_path": "§5"}
    r = validate_source_anchor(good)
    assert r["ok"] and r["has_precise_loc"] is True
    # 缺 document_id
    bad = {"page": 3}
    assert validate_source_anchor(bad)["ok"] is False
    # 字段清单含 table_cell
    assert "table_cell" in SOURCE_ANCHOR_FIELDS
    print("[OK] SourceAnchor：table_cell 精确定位 + document_id 必填")


def test_entity_registry_resolve():
    reg = EntityRegistry()
    reg.register("E1", "生产基地", aliases=["基地", "新基地"])
    reg.register("E2", "物流中心", aliases=["中心"])
    # canonical 命中
    assert reg.resolve("生产基地")["resolved"] is True and reg.resolve("生产基地")["entity_id"] == "E1"
    # alias 命中
    assert reg.resolve("基地")["entity_id"] == "E1"
    # 未命中
    assert reg.resolve("不存在")["resolved"] is False
    print("[OK] EntityRegistry.resolve：canonical/alias 命中，未命中返回 resolved=False")


def test_entity_registry_cross_doc_mention():
    reg = EntityRegistry()
    reg.register("E1", "基地", aliases=["生产基地"])
    reg.add_mention("E1", "基地", "D1", {"document_id": "D1", "table_cell": "B3"})
    reg.add_mention("E1", "生产基地", "D2", {"document_id": "D2", "page": 5})
    e = reg.list_entities()[0]
    assert len(e["mentions"]) == 2  # 跨文档统一到同一实体
    assert {m["document_id"] for m in e["mentions"]} == {"D1", "D2"}
    print("[OK] 跨文档 mention：同一实体在不同文档的 mention 统一到一个 entity_id")


def test_entity_registry_ambiguous():
    reg = EntityRegistry()
    reg.register("E1", "基地", aliases=["A基地"])
    reg.register("E2", "基地分厂", aliases=["A基地"])  # 与 E1 共享 alias "A基地"
    r = reg.resolve("A基地")
    assert r["resolved"] is False and r.get("ambiguous") is True
    assert "A基地" in reg.ambiguous_surfaces()
    print("[OK] 歧义检测：同名 surface 命中多实体 → ambiguous，不强行映射")


def main() -> int:
    test_classify_origin()
    test_assess_capability()
    test_source_anchor()
    test_entity_registry_resolve()
    test_entity_registry_cross_doc_mention()
    test_entity_registry_ambiguous()
    print("\nP2（知识处理侧）验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
