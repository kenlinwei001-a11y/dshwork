# -*- coding: utf-8 -*-
"""端到端对齐验证：corpus_run 真实产出 → 推演写作侧消费。

验证点：
1. 格式对齐：nodes/rules/derivation/manifest/style/reuse 六处字段符合推演写作消费契约。
2. 内容对齐：可研规则（label 对应 instantiate.COMPUTE_SPEC）→ instantiate_project 能重算。

运行：.venv/bin/python corpus_pipeline/test_pipeline_alignment.py
"""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline import run_pipeline
from corpus_pipeline.instantiate import instantiate_project

RAW = """某新材料生产基地扩产项目可行性研究报告

第一章 建设规模
新增生产线数量 3 条，每年工作日 250 天，每日班次 2 班，每班时长 8 小时，单线毛产出速率 120 套/小时，有效开动率 85%，最终合格率 98%。正常年计划销售量 110 万套，不含税销售单价 8.5 元。

第二章 投资估算
建筑与公辅工程合计 42000 万元，设备与系统购置费合计 36000 万元，工程建设其他费用 5800 万元，净营运资金需求 8000 万元，股东资金 50000 万元。

第三章 财务
正常年变动成本 420 万元，年度固定付现成本 280 万元，首年经营现金盈余 180 万元，单套变动成本 3.2 元。
"""

# 模拟 LLM 抽取（语义层），rules 的 label/deps 用业务主语（对应 COMPUTE_SPEC 的 key）
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
    "rules": [
        {"id": "R-产能", "kind": "compute", "label": "正常年合格产能",
         "expr": "floor({新增生产线数量}*{每年工作日}*{每日班次}*{每班时长}*{单线毛产出速率}*({有效开动率}/100)*({最终合格率}/100))",
         "deps": ["新增生产线数量", "每年工作日", "每日班次", "每班时长", "单线毛产出速率", "有效开动率", "最终合格率"], "target": "正常年合格产能"},
        {"id": "R-建设投资", "kind": "compute", "label": "建设投资",
         "expr": "round({建筑与公辅工程合计}+{设备与系统购置费合计}+{安装集成费}+{工程建设其他费用}+{基本预备费}, 2)",
         "deps": ["建筑与公辅工程合计", "设备与系统购置费合计", "安装集成费", "工程建设其他费用", "基本预备费"], "target": "建设投资"},
        {"id": "R-回收期", "kind": "compute", "label": "静态资金回收期",
         "expr": "round(2+({融资前项目资金需求}-{首年经营现金盈余})/{正常年经营现金盈余}, 2)",
         "deps": ["融资前项目资金需求", "首年经营现金盈余", "正常年经营现金盈余"], "target": "静态资金回收期"},
    ],
    "claims": [],
    "evidence": [],
    "relations": [],
}]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "corpus-demo"
        res = run_pipeline(RAW, root, extractions=EXTRACTIONS)

        # ---- 1. 格式对齐校验 ----
        nodes = json.loads((root / "graph" / "nodes.yaml").read_text(encoding="utf-8"))
        assert nodes and all({"id", "subject", "kind", "value", "unit", "caliber", "inheritable"} <= set(n) for n in nodes), "nodes 字段缺"
        assert any(n["kind"] == "quantity" for n in nodes), "kind 未归一化"
        print(f"[OK] nodes.yaml 格式对齐：{len(nodes)} 个节点，含 kind/unit/caliber/inheritable")

        rules = json.loads((root / "graph" / "rules.yaml").read_text(encoding="utf-8"))
        assert rules and all({"id", "kind", "expr", "deps", "target", "label", "guard"} <= set(r) for r in rules), "rules 字段缺"
        assert all(r["kind"] in ("compute", "select") for r in rules)
        print(f"[OK] rules.yaml 格式对齐：{len(rules)} 条规则，含 kind/deps/target/label/guard")

        deriv = json.loads((root / "reasoning" / "derivation.yaml").read_text(encoding="utf-8"))
        assert "nodes" in deriv and all("narrative_zh" in d for d in deriv["nodes"]), "derivation 缺 nodes/narrative_zh"
        print(f"[OK] derivation.yaml 格式对齐：{len(deriv['nodes'])} 条推演，含 narrative_zh")

        manifest = json.loads((root / "manifest.yaml").read_text(encoding="utf-8"))
        assert {"corpus_id", "version", "source_fingerprint", "constraints"} <= set(manifest), "manifest 字段缺"
        print(f"[OK] manifest.yaml 格式对齐：corpus_id={manifest['corpus_id']}")

        style = json.loads((root / "style" / "style_profile.yaml").read_text(encoding="utf-8"))
        assert {"number_format", "terminology", "forbidden", "citation_style", "table_caption", "person"} <= set(style), "style 字段缺"
        print("[OK] style_profile.yaml 格式对齐：完整风格字段")

        reuse = json.loads((root / "reuse" / "domains.yaml").read_text(encoding="utf-8"))
        assert len(reuse["domains"]) == 16, len(reuse["domains"])
        assert all({"core_domain", "assembly_method", "reusable_form"} <= set(d) for d in reuse["domains"])
        print(f"[OK] reuse/domains.yaml 格式对齐：16 资产域")

        # ---- 2. 内容对齐校验：instantiate_project 消费 ----
        proj = Path(tmp) / "new-project"
        provided = [
            {"label": "新增生产线数量", "value": 2, "unit": "条", "kind": "quantity"},
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
        ]
        ir = instantiate_project(str(root), str(proj), provided,
                                 meta={"project_id": "NEW-001", "title": "新项目可研", "data_cutoff": "2026-09-30"})
        assert ir["provided"] == 18, ir
        # R-产能 应重算（正常年合格产能）；R-建设投资/R-回收期 因缺中间量而 undefined（缺值守卫正常）
        assert ir["computed"] >= 1, ir
        print(f"[OK] instantiate_project 消费：provided={ir['provided']} computed={ir['computed']} "
              f"undefined={ir['undefined_notes']} gate={ir['gate']}")

        # 借形不借值：新图无历史数值泄漏
        raw_nodes = (proj / "graph" / "nodes.yaml").read_text(encoding="utf-8")
        assert "92664" not in raw_nodes and "1199520" not in raw_nodes, "历史数值泄漏"
        print("[OK] 借形不借值：新项目图库不含历史原值")

    print("\n全部对齐验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
