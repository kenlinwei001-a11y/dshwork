# -*- coding: utf-8 -*-
"""Claim 语义模型扩展验证。

覆盖：三类字段（输入/推演/治理）、归一化（旧 type/evidence 兼容）、枚举校验、apply_extraction。

运行：.venv/bin/python corpus_pipeline/test_claim_schema.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.ontology import (
    CLAIM_INPUT_FIELDS, CLAIM_DERIVED_FIELDS, CLAIM_GOVERNANCE_FIELDS,
    CLAIM_TYPE_VALUES, CLAIM_STATUS_VALUES,
    _normalize_claim, validate_extraction, apply_extraction,
)


def test_field_categories():
    assert set(CLAIM_INPUT_FIELDS) == {"id", "text", "claim_type", "source"}
    assert {"status", "evidence_refs", "premise_refs", "derived_from", "confidence"} <= set(CLAIM_DERIVED_FIELDS)
    assert "valid_time" in CLAIM_GOVERNANCE_FIELDS
    assert set(CLAIM_TYPE_VALUES) == {"fact", "hypothesis", "inference", "conclusion", "recommendation"}
    assert set(CLAIM_STATUS_VALUES) == {"unverified", "supported", "contradicted", "verified"}
    print("[OK] 三类字段（输入/推演/治理）与枚举定义正确")


def test_normalize_old_fields():
    """旧字段兼容：type→claim_type、evidence→evidence_refs，推演字段补缺省。"""
    c = _normalize_claim({"id": "C1", "text": "x", "type": "suggestion", "evidence": ["E1"]})
    assert c["claim_type"] == "recommendation"   # suggestion → recommendation
    assert c["evidence_refs"] == ["E1"]          # evidence → evidence_refs
    assert c["status"] == "unverified"           # 推演字段缺省未验证
    assert c["confidence"] is None
    assert c["premise_refs"] == [] and c["derived_from"] == []
    print("[OK] 归一化：旧 type/evidence 兼容，推演字段缺省 unverified")


def test_normalize_new_fields():
    c = _normalize_claim({"id": "C1", "text": "x", "claim_type": "fact", "status": "supported", "confidence": 0.9})
    assert c["claim_type"] == "fact" and c["status"] == "supported" and c["confidence"] == 0.9
    print("[OK] 新字段（claim_type/status/confidence）原样保留")


def test_validate_claim_enum():
    ext = {"chunk_id": "c", "claims": [{"id": "C1", "text": "x", "claim_type": "bogus"}]}
    v = validate_extraction(ext)
    assert not v["ok"] and any("claim_type" in e for e in v["errors"])
    ext2 = {"chunk_id": "c", "claims": [{"id": "C1", "text": "x", "status": "bogus"}]}
    assert any("status" in e for e in validate_extraction(ext2)["errors"])
    print("[OK] 枚举校验：非法 claim_type/status 报错")


def test_apply_extraction_normalizes():
    ext = {"chunk_id": "c1", "facts": [], "rules": [],
           "claims": [{"id": "C1", "text": "项目基本可行", "type": "judgment", "evidence": ["E1"]}],
           "evidence": [], "relations": []}
    graph = apply_extraction([], [ext])
    c = graph["claims"][0]
    assert c["claim_type"] == "conclusion"       # judgment → conclusion
    assert c["evidence_refs"] == ["E1"]
    assert c["status"] == "unverified"
    print("[OK] apply_extraction：claims 归一化（judgment→conclusion、evidence→evidence_refs）")


def main() -> int:
    test_field_categories()
    test_normalize_old_fields()
    test_normalize_new_fields()
    test_validate_claim_enum()
    test_apply_extraction_normalizes()
    print("\nClaim 语义模型扩展验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
