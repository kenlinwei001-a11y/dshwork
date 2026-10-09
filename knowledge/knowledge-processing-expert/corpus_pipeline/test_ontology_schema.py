# -*- coding: utf-8 -*-
"""本体管理接入点验证（对齐 Semantica OWL/SHACL/SKOS）。

验证：export/import round-trip、bootstrap_claim_ontology（自动扩展本体执行层）。

运行：.venv/bin/python corpus_pipeline/test_ontology_schema.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.ontology_schema import (
    export_ontology_schema, import_ontology_schema, bootstrap_claim_ontology,
)
from corpus_pipeline.semantic_model import build_concepts
from corpus_pipeline.schema_diff import diff_schemas


def test_export_structure():
    schema = export_ontology_schema()
    # OWL 类：Claim/Metric/Attribute/Entity
    class_names = {c["name"] for c in schema["classes"]}
    assert {"Claim", "Metric", "Attribute", "Entity"} <= class_names
    # OWL 属性：十类关系 + Claim 数据属性
    prop_names = {p["name"] for p in schema["properties"]}
    assert {"has_value", "depends_on", "supports", "contradicts"} <= prop_names
    assert {"claim_type", "status", "has_evidence", "has_premise"} <= prop_names
    # SHACL 约束：ClaimShape
    assert any(c["shape"] == "ClaimShape" for c in schema["constraints"])
    # SKOS 词表：概念 prefLabel + altLabels
    assert schema["vocabulary"], "词表为空"
    assert any(v["prefLabel"] == "正常年营业收入" and "营业收入" in v["altLabels"] for v in schema["vocabulary"])
    print(f"[OK] export：{len(schema['classes'])} 类 + {len(schema['properties'])} 属性 + "
          f"{len(schema['constraints'])} 约束 + {len(schema['vocabulary'])} 词表概念")


def test_import_roundtrip():
    concepts = build_concepts()
    schema = export_ontology_schema(concepts)
    back = import_ontology_schema(schema)
    # round-trip：概念的 canonical_name + aliases 保留
    assert "正常年营业收入" in back and back["正常年营业收入"]["canonical_name"] == "正常年营业收入"
    assert "营业收入" in back["正常年营业收入"]["aliases"]
    assert "建设投资" in back and back["建设投资"]["kind"] == "metric"
    print(f"[OK] round-trip：{len(back)} 个概念，canonical_name/aliases/kind 保留")


def test_bootstrap_claim():
    diffs = diff_schemas({"facts": {"type": "array"}}, {"facts": {"type": "array"}, "claims": {"type": "array"}})
    r = bootstrap_claim_ontology(diffs)
    assert r["bootstrapped"] is True and r["source"] == "deterministic"
    onto = r["ontology"]
    assert any(c["name"] == "Claim" for c in onto["classes"])
    assert any(p["name"] == "has_evidence" for p in onto["properties"])
    assert any(c["shape"] == "ClaimShape" for c in onto["constraints"])
    print("[OK] bootstrap：Claim 新增 → 诱导 Claim 类 + has_evidence/has_premise 属性 + ClaimShape 约束")


def test_bootstrap_no_claim():
    diffs = diff_schemas({"facts": {"type": "array"}}, {"facts": {"type": "array"}, "unit_price": {"type": "number"}})
    r = bootstrap_claim_ontology(diffs)
    assert r["bootstrapped"] is False
    print("[OK] bootstrap：无 Claim 新增 → 不扩展本体")


def main() -> int:
    test_export_structure()
    test_import_roundtrip()
    test_bootstrap_claim()
    test_bootstrap_no_claim()
    print("\n本体管理接入点验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
