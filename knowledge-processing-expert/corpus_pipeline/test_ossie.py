# -*- coding: utf-8 -*-
"""Ossie YAML 导入/导出适配器验证。

覆盖：导出→导入 round-trip 一致；外部 Ossie YAML 导入（synonyms→aliases、本地优先）。

运行：.venv/bin/python corpus_pipeline/test_ossie.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.semantic_model import (
    build_concepts, import_ossie_yaml, export_ossie_yaml, resolve_concept,
)

# 一个外部 Apache Ossie 语义模型（模拟 dbt/其他平台导出的格式）
EXTERNAL_OSSIE = """\
version: "0.2.0.dev0"
semantic_model:
  - name: sales
    datasets:
      - name: orders
        fields:
          - name: revenue
            synonyms: [营业收入, 总收入]
            datatype: DECIMAL
          - name: unit_price
            synonyms: [单价, 不含税单价]
    metrics:
      - name: total_sales
        synonyms: [总销售额, 销售额]
        description: 销售总额
        expression:
          dialects:
            - dialect: ANSI_SQL
              expression: SUM(orders.amount)
"""


def test_export_import_roundtrip():
    concepts = build_concepts()
    yaml_text = export_ossie_yaml(concepts, model_name="feasibility")
    back = import_ossie_yaml(yaml_text)

    # metric 概念 round-trip：name/aliases/kind/formula 保留
    for name in ("正常年营业收入", "建设投资", "静态资金回收期"):
        assert name in back, f"round-trip 丢失概念 {name}"
        assert back[name]["kind"] == "metric"
        assert back[name]["canonical_name"] == name
        assert back[name]["formula"], f"{name} 的 formula 未保留"
    # attribute 概念 round-trip
    assert "新增生产线数量" in back and back["新增生产线数量"]["kind"] == "attribute"
    # 别名 round-trip（营业收入 是 正常年营业收入 的别名）
    assert "营业收入" in back["正常年营业收入"]["aliases"]
    print(f"[OK] round-trip：{len(back)} 个概念，metric/attribute/aliases/formula 保留")


def test_import_external():
    concepts = import_ossie_yaml(EXTERNAL_OSSIE)
    # fields → attribute，synonyms → aliases
    assert concepts["revenue"]["kind"] == "attribute"
    assert "营业收入" in concepts["revenue"]["aliases"]
    assert "unit_price" in concepts and "单价" in concepts["unit_price"]["aliases"]
    # metrics → metric，expression → formula
    assert concepts["total_sales"]["kind"] == "metric"
    assert concepts["total_sales"]["formula"] == "SUM(orders.amount)"
    assert "总销售额" in concepts["total_sales"]["aliases"]
    # 语义对齐：外部 synonyms 能匹配概念
    c, via = resolve_concept("营业收入", concepts)
    assert c is not None and c["canonical_name"] == "revenue"
    print("[OK] 外部 Ossie 导入：fields→attribute、metrics→metric、synonyms→aliases")


def test_import_merge_local_priority():
    """merge_into 时本地概念优先，不被外部覆盖。"""
    local = build_concepts()
    before = local["建设投资"]["formula"]
    merged = import_ossie_yaml(EXTERNAL_OSSIE, merge_into=local)
    # 外部没有建设投资，本地保留
    assert merged["建设投资"]["formula"] == before
    # 外部概念被合并进来
    assert "total_sales" in merged
    print("[OK] merge_into：本地概念优先，外部概念合并进字典")


def main() -> int:
    test_export_import_roundtrip()
    test_import_external()
    test_import_merge_local_priority()
    print("\nOssie YAML 导入/导出适配器验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
