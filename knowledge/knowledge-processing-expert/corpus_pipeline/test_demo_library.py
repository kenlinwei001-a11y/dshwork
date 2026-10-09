# -*- coding: utf-8 -*-
"""端到端验证：历史语料库样例 → library_* 工具 → instantiate_project（借形不借值）。

运行：.venv/bin/python corpus_pipeline/test_demo_library.py
"""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline import library as L
from corpus_pipeline.instantiate import instantiate_project

LIBRARY = str(Path(__file__).resolve().parent.parent / "corpus-library")


def main() -> int:
    # 1) 资产库盘点
    pkgs = L.list_packages(LIBRARY)
    assert len(pkgs) == 1, pkgs
    pkg = pkgs[0]["name"]
    assert pkg == "PX-2026-001-feasibility", pkg
    print("[OK] library_list_packages →", pkg)

    # 2) 16 资产域
    reuse = L.get_asset(LIBRARY, pkg, "reuse")
    domains = reuse["content"]["domains"]
    assert len(domains) == 16, len(domains)
    ids = [d["id"] for d in domains]
    for must in ("ontology", "argument_chain", "scenario", "variable", "task_dag", "function",
                 "rule", "invariant", "skill", "report_structure", "report_form", "prompt",
                 "quality_gate", "reuse_strategy", "entity_relation", "cost_risk"):
        assert must in ids, f"缺资产域 {must}"
    print("[OK] library_get_asset(reuse) → 16 资产域齐备")

    # 3) 大纲 / 规则资产
    outline = L.get_asset(LIBRARY, pkg, "outline")["content"]
    assert len(outline["sections"]) == 5, outline
    rules = L.get_asset(LIBRARY, pkg, "rules")["content"]
    assert any(r["label"] == "建设投资" for r in rules), "rules 缺建设投资"
    print("[OK] library_get_asset(outline/rules) 可借形")

    # 4) 找类比
    analog = L.find_analog(LIBRARY, doc_type="可研报告", query="建设投资")
    assert analog["best"] == pkg, analog
    print("[OK] library_find_analog →", analog["best"])

    # 5) instantiate_project（借形不借值 + 缺值守卫 + 回放检冲突）
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "new-project"
        provided = [
            {"label": "新增生产线数量", "value": 2, "unit": "条", "kind": "quantity"},
            {"label": "每年工作日", "value": 250, "unit": "天", "kind": "quantity"},
            {"label": "每日班次", "value": 2, "unit": "班", "kind": "quantity"},
            {"label": "每班时长", "value": 8, "unit": "小时", "kind": "quantity"},
            {"label": "单线毛产出速率", "value": 100, "unit": "套/小时", "kind": "quantity"},
            {"label": "有效开动率", "value": 90, "unit": "%", "kind": "quantity"},
            {"label": "最终合格率", "value": 97, "unit": "%", "kind": "quantity"},
            {"label": "正常年计划销售量", "value": 800000, "unit": "套", "kind": "quantity"},
            {"label": "不含税销售单价", "value": 9, "unit": "元", "kind": "quantity"},
            {"label": "建筑与公辅工程合计", "value": 50000, "unit": "万元", "kind": "quantity"},
            {"label": "设备与系统购置费合计", "value": 40000, "unit": "万元", "kind": "quantity"},
            {"label": "工程费用", "value": 90000, "unit": "万元", "kind": "quantity"},
            {"label": "工程建设其他费用", "value": 6000, "unit": "万元", "kind": "quantity"},
            {"label": "净营运资金需求", "value": 9000, "unit": "万元", "kind": "quantity"},
            {"label": "股东资金", "value": 60000, "unit": "万元", "kind": "quantity"},
            {"label": "正常年变动成本", "value": 450, "unit": "万元", "kind": "quantity"},
            {"label": "年度固定付现成本", "value": 300, "unit": "万元", "kind": "quantity"},
            {"label": "首年经营现金盈余", "value": 200, "unit": "万元", "kind": "quantity"},
            # 故意缺失「单套变动成本」→ 经营付现收支平衡销量 应 UNDEFINED（缺值守卫）
        ]
        res = instantiate_project(LIBRARY + "/" + pkg, str(proj), provided,
                                  meta={"project_id": "NEW-001", "title": "新项目可研", "data_cutoff": "2026-09-30"})
        assert res["provided"] == 18, res
        assert res["computed"] >= 8, res          # 多数规则应重算
        assert res["undefined_notes"] >= 1, res   # 缺值守卫触发
        print(f"[OK] instantiate_project → provided={res['provided']} computed={res['computed']} "
              f"undefined={res['undefined_notes']} gate={res['gate']}")

        nodes = json.loads((proj / "graph" / "nodes.yaml").read_text(encoding="utf-8"))
        # 借形不借值：新项目节点用新 id（P-），不含历史 N-xxxx；历史数值 92664 不得出现
        assert all(n["id"].startswith("P-") for n in nodes), "存在旧节点 id 泄漏"
        raw = json.dumps(nodes, ensure_ascii=False)
        assert "92664" not in raw, "历史建设投资原值 92664 泄漏到新图"
        # 缺值守卫：经营付现收支平衡销量 应为 undefined 且带 instruction
        undef = [n for n in nodes if n["status"] == "undefined"]
        assert any(n["label"] == "经营付现收支平衡销量" for n in undef), "缺值守卫未触发"
        assert all(n.get("instruction") for n in undef), "undefined 节点缺 instruction"
        print("[OK] 借形不借值 + 缺值守卫 验证通过；undefined 节点有 instruction")

        # 回放检冲突：提供与规则重算不一致的建设投资
        proj2 = Path(tmp) / "conflict-project"
        conflict_facts = provided + [{"label": "建设投资", "value": 999999, "unit": "万元", "kind": "quantity"}]
        res2 = instantiate_project(LIBRARY + "/" + pkg, str(proj2), conflict_facts,
                                   meta={"project_id": "NEW-002", "title": "冲突项目"})
        assert res2["replay_conflicts"] >= 1, res2
        assert res2["gate"] == "REVIEW", res2
        print(f"[OK] 回放检冲突 → conflicts={res2['replay_conflicts']} gate={res2['gate']}（待审不裁决）")

    print("\n全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
