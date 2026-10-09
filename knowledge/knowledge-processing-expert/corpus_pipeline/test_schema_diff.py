# -*- coding: utf-8 -*-
"""Schema Diff + 语义模型 验证。

覆盖：语义概念字典、结构比对（新增/缺失/类型变化）、语义对齐（改名/别名）、
语义分类（新变量/元数据/别名）。

运行：.venv/bin/python corpus_pipeline/test_schema_diff.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.semantic_model import build_concepts, resolve_concept
from corpus_pipeline.schema_diff import diff_schemas, summarize, DeterministicClassifier


def test_semantic_model():
    concepts = build_concepts()
    # metric 概念（计算指标）
    assert "正常年营业收入" in concepts and concepts["正常年营业收入"]["kind"] == "metric"
    assert concepts["正常年营业收入"]["unit"] == "万元"
    assert "基本预备费" in concepts["建设投资"]["deps"], "建设投资 deps 应从公式提取"
    # attribute 概念（输入变量）
    assert "新增生产线数量" in concepts and concepts["新增生产线数量"]["kind"] == "attribute"
    assert concepts["新增生产线数量"]["unit"] == "条"
    # 别名映射
    assert "营业收入" in concepts["正常年营业收入"]["aliases"]
    # resolve_concept
    c, via = resolve_concept("营业收入", concepts)
    assert via == "alias" and c["canonical_name"] == "正常年营业收入"
    c, via = resolve_concept("正常年营业收入", concepts)
    assert via == "canonical"
    c, via = resolve_concept("未知指标", concepts)
    assert c is None and via is None
    print(f"[OK] 语义模型：{len(concepts)} 个概念（metric + attribute），别名/规范名匹配正确")


def test_diff_added_claims():
    """文档第三节案例：新项目多一个 claims 字段。"""
    old = {"project_name": {"type": "string"}, "objective": {"type": "string"},
           "facts": {"type": "array"}, "evidence": {"type": "array"}}
    new = {**old, "claims": {"type": "array"}}
    diffs = diff_schemas(old, new)
    added = [d for d in diffs if d["kind"] == "added"]
    assert len(added) == 1 and added[0]["field"] == "claims"
    assert added[0]["semantic"]["kind"] == "new_variable", added[0]["semantic"]
    s = summarize(diffs)
    assert s["by_kind"].get("added") == 1 and s["by_kind"].get("removed", 0) == 0
    print("[OK] 新增 claims 字段识别为 added + new_variable")


def test_diff_renamed():
    old = {"总投资": {"type": "number"}}
    new = {"建设投资": {"type": "number"}}
    diffs = diff_schemas(old, new)
    renamed = [d for d in diffs if d["kind"] == "renamed"]
    assert len(renamed) == 1
    assert renamed[0]["from"] == "总投资" and renamed[0]["field"] == "建设投资" and renamed[0]["concept_id"] == "建设投资"
    print("[OK] 字段改名识别：总投资 → 建设投资（命中同一概念）")


def test_diff_type_changed():
    old = {"claims": {"type": "string"}}
    new = {"claims": {"type": "array"}}
    diffs = diff_schemas(old, new)
    assert any(d["kind"] == "type_changed" and d["field"] == "claims"
               and d["old_type"] == "string" and d["new_type"] == "array" for d in diffs)
    print("[OK] 类型变化识别：claims string→array")


def test_diff_alias_and_metadata():
    # 别名：营业收入 → 命中正常年营业收入概念
    diffs = diff_schemas({}, {"营业收入": {"type": "number"}})
    assert diffs[0]["semantic"]["kind"] == "alias_of_existing"
    assert diffs[0]["semantic"]["concept_id"] == "正常年营业收入"
    # 元数据：created_at → 元数据分类
    diffs = diff_schemas({}, {"created_at": {"type": "string"}})
    assert diffs[0]["semantic"]["kind"] == "metadata"
    print("[OK] 语义分类：别名→alias_of_existing，created_at→metadata")


def test_removed():
    old = {"facts": {"type": "array"}, "evidence": {"type": "array"}}
    new = {"facts": {"type": "array"}}
    diffs = diff_schemas(old, new)
    removed = [d for d in diffs if d["kind"] == "removed"]
    assert len(removed) == 1 and removed[0]["field"] == "evidence"
    print("[OK] 缺失字段识别：evidence removed")


def main() -> int:
    test_semantic_model()
    test_diff_added_claims()
    test_diff_renamed()
    test_diff_type_changed()
    test_diff_alias_and_metadata()
    test_removed()
    print("\nSchema Diff + 语义模型验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
