# -*- coding: utf-8 -*-
"""6 类装配产物验证（P1）。

验证 instantiate_project 输出：
  assembly_manifest / schema_diff / asset_patch / reuse_lineage / project_asset_bundle / validation_report。

运行：.venv/bin/python corpus_pipeline/test_assembly_artifacts.py
"""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.instantiate import instantiate_project

CORPUS = str(Path(__file__).resolve().parent.parent / "corpus-library" / "PX-2026-001-feasibility")

PROVIDED = [
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
]

# 模拟 Schema 演化：历史模板 vs 新项目输入
#   总投资 → 建设投资（概念字典内，触发 renamed）；evidence → evidence_items（元数据类，added+removed）；claims 新增
OLD_SCHEMA = {"project_name": {"type": "string"}, "objective": {"type": "string"},
              "facts": {"type": "array"}, "evidence": {"type": "array"}, "总投资": {"type": "number"}}
NEW_SCHEMA = {"project_name": {"type": "string"}, "objective": {"type": "string"},
              "facts": {"type": "array"}, "evidence_items": {"type": "array"}, "建设投资": {"type": "number"},
              "claims": {"type": "array"}}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "new-project"
        res = instantiate_project(CORPUS, str(proj), PROVIDED,
                                  meta={"project_id": "NEW-001", "title": "新项目可研", "data_cutoff": "2026-09-30"},
                                  old_schema=OLD_SCHEMA, new_schema=NEW_SCHEMA)

        # ① assembly_manifest：复用清单
        am = json.loads((proj / "assembly_manifest.yaml").read_text(encoding="utf-8"))
        assert am["project_id"] == "NEW-001" and am["reuse_mode"] == "借形不借值"
        assert am["based_on"]["corpus_id"] == "PX-2026-001"
        assert any(a["asset"] == "rules" and a["mode"] == "rebind" for a in am["reused_assets"])
        print("[OK] ① assembly_manifest：复用清单 + 复用方式 + 版本")

        # ② schema_diff：差异清单（含改名 + 新增）
        sd = json.loads((proj / "schema_diff.yaml").read_text(encoding="utf-8"))
        assert "claims" in sd["summary"]["added_fields"]
        renamed = [(d["from"], d["field"]) for d in sd["diffs"] if d["kind"] == "renamed"]
        assert ("总投资", "建设投资") in renamed, renamed  # 概念字典内改名
        assert "evidence" in sd["summary"]["removed_fields"] and "evidence_items" in sd["summary"]["added_fields"]
        print("[OK] ② schema_diff：总投资→建设投资(改名) + claims(新增) + evidence→evidence_items(元数据类 added/removed)")

        # ③ asset_patch：带 operation + base_version 的变更集（文档 AssetPatch 契约）
        ap = json.loads((proj / "asset_patch.yaml").read_text(encoding="utf-8"))
        assert ap["base_version"] and ap["patches"]
        ops = {p["operation"] for p in ap["patches"]}
        assert {"PARAMETERIZE", "ADD", "REUSE"} <= ops, ops
        assert all("base_version" in p and "target_asset" in p for p in ap["patches"])
        print(f"[OK] ③ asset_patch：{len(ap['patches'])} 个带 operation+base_version 的 patch（{sorted(ops)}）")

        # ③b bundle：版本固化（version + content_hash）
        b = json.loads((proj / "bundle.yaml").read_text(encoding="utf-8"))
        assert b["version"] == "1.0" and b["content_hash"] and b["published"] is False
        assert b["based_on"]["corpus_id"] == "PX-2026-001"
        print(f"[OK] ③b bundle：version={b['version']}，content_hash 前 12 位 {b['content_hash'][:12]}，未发布")

        # ④ reuse_lineage：溯源链
        rl = json.loads((proj / "reuse_lineage.yaml").read_text(encoding="utf-8"))
        assert rl["lineage"] and all({"corpus_node_id", "project_node_id", "status"} <= set(x) for x in rl["lineage"])
        print(f"[OK] ④ reuse_lineage：{len(rl['lineage'])} 条溯源（corpus→project→status）")

        # ⑤ project_asset_bundle：项目资产集合（nodes/rules/derivation/bindings）
        assert (proj / "graph" / "nodes.yaml").exists() and (proj / "graph" / "rules.yaml").exists()
        assert (proj / "bindings.yaml").exists()
        print("[OK] ⑤ project_asset_bundle：nodes/rules/derivation/bindings")

        # ⑥ validation_report：校验报告
        vr = json.loads((proj / "quality" / "gate_report.yaml").read_text(encoding="utf-8"))
        assert "gate" in vr and "undefined" in vr
        print(f"[OK] ⑥ validation_report：gate={vr['gate']}，undefined={len(vr['undefined'])}")

    print("\n6 类装配产物验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
