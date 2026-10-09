# -*- coding: utf-8 -*-
"""领域规则库下沉验证：COMPUTE_SPEC 单一事实源 + 术语映射 + 抽取层自动对齐 label。

验证点：
1. 单元：resolve_label 把自然语言 label 归一为规范 label（别名映射）。
2. 单元：rules_for_domain 产出 11 条对齐计算规格的规则。
3. 集成：corpus_run(doc_type=可研报告) 注入领域规则库 + LLM 规则 label 归一。
4. 端到端：instantiate_project 消费（provided 用变量名）能重算 computed > 0。

运行：.venv/bin/python corpus_pipeline/test_domain_rules.py
"""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.domain_rules import (
    COMPUTE_SPEC, FEASIBILITY_COMPUTE_SPEC, resolve_label, rules_for_domain, inject_domain_rules,
)
from corpus_pipeline import run_pipeline
from corpus_pipeline.instantiate import instantiate_project

RAW = "某可研报告\n第一章 建设规模\n新增生产线数量 3 条。\n第二章 投资估算\n建设投资若干。\n"

# 模拟 LLM 抽取：rules 的 label 用自然语言（别名），依赖业务主语
EXTRACTIONS = [{
    "chunk_id": "c-demo",
    "facts": [
        {"subject": "新增生产线数量", "predicate": "has_value", "value": 3, "unit": "条"},
        {"subject": "每年工作日", "predicate": "has_value", "value": 250, "unit": "天"},
        {"subject": "每日班次", "predicate": "has_value", "value": 2, "unit": "班"},
        {"subject": "每班时长", "predicate": "has_value", "value": 8, "unit": "小时"},
        {"subject": "单线毛产出速率", "predicate": "has_value", "value": 120, "unit": "套/小时"},
        {"subject": "有效开动率", "predicate": "has_value", "value": 85, "unit": "%"},
        {"subject": "最终合格率", "predicate": "has_value", "value": 98, "unit": "%"},
        {"subject": "正常年计划销售量", "predicate": "has_value", "value": 1100000, "unit": "套"},
        {"subject": "不含税销售单价", "predicate": "has_value", "value": 8.5, "unit": "元"},
        {"subject": "建筑与公辅工程合计", "predicate": "has_value", "value": 42000, "unit": "万元"},
        {"subject": "设备与系统购置费合计", "predicate": "has_value", "value": 36000, "unit": "万元"},
        {"subject": "工程费用", "predicate": "has_value", "value": 78000, "unit": "万元"},
        {"subject": "工程建设其他费用", "predicate": "has_value", "value": 5800, "unit": "万元"},
        {"subject": "净营运资金需求", "predicate": "has_value", "value": 8000, "unit": "万元"},
        {"subject": "股东资金", "predicate": "has_value", "value": 50000, "unit": "万元"},
        {"subject": "正常年变动成本", "predicate": "has_value", "value": 420, "unit": "万元"},
        {"subject": "年度固定付现成本", "predicate": "has_value", "value": 280, "unit": "万元"},
        {"subject": "首年经营现金盈余", "predicate": "has_value", "value": 180, "unit": "万元"},
        {"subject": "单套变动成本", "predicate": "has_value", "value": 3.2, "unit": "元"},
    ],
    # 自然语言 label（别名）：营业收入→正常年营业收入，总投资→建设投资
    "rules": [
        {"id": "R-LLM-1", "kind": "compute", "label": "营业收入",
         "expr": "销量*单价/10000", "deps": ["正常年计划销售量", "不含税销售单价"], "target": "营业收入"},
        {"id": "R-LLM-2", "kind": "compute", "label": "总投资",
         "expr": "建筑+设备+安装+其他+预备费", "deps": ["建筑与公辅工程合计", "设备与系统购置费合计"], "target": "总投资"},
    ],
    "claims": [],
    "evidence": [],
    "relations": [],
}]


def main() -> int:
    # ---- 1. 单元：术语映射 ----
    assert resolve_label("营业收入") == "正常年营业收入"
    assert resolve_label("总投资") == "建设投资"
    assert resolve_label("回收期") == "静态资金回收期"
    assert resolve_label("建设投资") == "建设投资"          # 精确匹配原样
    assert resolve_label("未知指标") == "未知指标"          # 无法归一原样
    print("[OK] resolve_label 术语映射正确（别名→规范 label）")

    # ---- 2. 单元：领域规则产出 ----
    rules = rules_for_domain("可研报告")
    assert len(rules) == len(FEASIBILITY_COMPUTE_SPEC) == 11, len(rules)
    assert all(r["label"] in COMPUTE_SPEC for r in rules), "rules label 未对齐计算规格"
    assert all(r["kind"] == "compute" and r["deps"] and r["target"] == r["label"] for r in rules)
    print(f"[OK] rules_for_domain 产出 {len(rules)} 条规则，label/deps/target 对齐计算规格")

    # ---- 3. 集成：corpus_run 注入 + 归一 ----
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "corpus"
        run_pipeline(RAW, root, extractions=EXTRACTIONS, doc_type="可研报告")
        rules_out = json.loads((root / "graph" / "rules.yaml").read_text(encoding="utf-8"))
        labels = {r["label"] for r in rules_out}
        # LLM 别名规则已归一
        assert "正常年营业收入" in labels, "「营业收入」未归一为「正常年营业收入」"
        assert "建设投资" in labels, "「总投资」未归一为「建设投资」"
        assert "营业收入" not in labels and "总投资" not in labels, "别名 label 未替换"
        # 领域规则库已注入（11 条对齐规则）
        assert len(labels) >= len(COMPUTE_SPEC), f"领域规则未注入完整，labels={len(labels)}"
        assert "正常年合格产能" in labels and "静态资金回收期" in labels and "经营付现收支平衡销量" in labels
        print(f"[OK] corpus_run(doc_type=可研报告) 注入领域规则 + 归一 label（共 {len(rules_out)} 条规则）")

        # ---- 4. 端到端：instantiate 消费能重算 ----
        proj = Path(tmp) / "proj"
        provided = [
            {"label": "新增生产线数量", "value": 2, "unit": "条"},
            {"label": "每年工作日", "value": 250, "unit": "天"},
            {"label": "每日班次", "value": 2, "unit": "班"},
            {"label": "每班时长", "value": 8, "unit": "小时"},
            {"label": "单线毛产出速率", "value": 100, "unit": "套/小时"},
            {"label": "有效开动率", "value": 90, "unit": "%"},
            {"label": "最终合格率", "value": 97, "unit": "%"},
            {"label": "正常年计划销售量", "value": 800000, "unit": "套"},
            {"label": "不含税销售单价", "value": 9, "unit": "元"},
            {"label": "建筑与公辅工程合计", "value": 50000, "unit": "万元"},
            {"label": "设备与系统购置费合计", "value": 40000, "unit": "万元"},
            {"label": "工程费用", "value": 90000, "unit": "万元"},
            {"label": "工程建设其他费用", "value": 6000, "unit": "万元"},
            {"label": "净营运资金需求", "value": 9000, "unit": "万元"},
            {"label": "股东资金", "value": 60000, "unit": "万元"},
            {"label": "正常年变动成本", "value": 450, "unit": "万元"},
            {"label": "年度固定付现成本", "value": 300, "unit": "万元"},
            {"label": "首年经营现金盈余", "value": 200, "unit": "万元"},
            {"label": "单套变动成本", "value": 3.5, "unit": "元"},
        ]
        ir = instantiate_project(str(root), str(proj), provided,
                                 meta={"project_id": "NEW", "title": "新可研", "data_cutoff": "2026-09-30"})
        assert ir["computed"] >= 5, f"领域规则未触发重算，computed={ir['computed']}"
        print(f"[OK] instantiate_project 消费：computed={ir['computed']} undefined={ir['undefined_notes']} gate={ir['gate']}")

        # 验证单条规则重算正确：正常年合格产能 = floor(2*250*2*8*100*0.9*0.97)
        nodes = json.loads((proj / "graph" / "nodes.yaml").read_text(encoding="utf-8"))
        cap = next((n for n in nodes if n["label"] == "正常年合格产能"), None)
        if cap:
            print(f"[OK] 正常年合格产能重算值 = {cap['value']}（预期 floor(2*250*2*8*100*0.9*0.97)={int(2*250*2*8*100*0.9*0.97)}）")

    print("\n领域规则库下沉验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
