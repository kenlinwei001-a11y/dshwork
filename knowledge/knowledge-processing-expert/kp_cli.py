#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kp_cli —— 不依赖 MCP 的命令行入口。

MCP（kp-processing / kp-assembly / kp-library）在部分环境里未连接或需重启，
但底层 corpus_pipeline 模块始终可用。本 CLI 直接调这些模块，
用于「改代码后立即验证」和「无 MCP 环境下的建图」。

用法：
    python kp_cli.py facts  <材料路径> --as-of 2026-03-15 [-o provided.json]
    python kp_cli.py build  <项目目录> --corpus <语料包> --facts <provided.json> [--meta k=v ...]
    python kp_cli.py graph  <项目目录> [-o GRAPH.json]
    python kp_cli.py slots  <项目目录> --rules <rules.yaml> --fsm <fact_source_map.yaml>
    python kp_cli.py gates  <项目目录>

示例（一条龙）：
    python kp_cli.py facts 客户材料.docx -o /tmp/pf.json
    python kp_cli.py build /tmp/PROJ --corpus ~/SHUFE-BDC-2019-001 --facts /tmp/pf.json
    python kp_cli.py graph /tmp/PROJ -o /tmp/GRAPH.json
    python kp_cli.py gates /tmp/PROJ
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def cmd_facts(a):
    from corpus_pipeline.doc_facts import to_provided_facts
    r = to_provided_facts(a.path, as_of=a.as_of, default_caliber=a.caliber)
    if a.out:
        Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print("→ %s（%d 条 provided_facts）" % (a.out, len(r["provided_facts"])))
    print(json.dumps(r["stats"], ensure_ascii=False, indent=1))
    return 0


def cmd_build(a):
    from corpus_pipeline.instantiate import instantiate_project
    pf = json.loads(Path(a.facts).read_text(encoding="utf-8"))
    if isinstance(pf, dict):
        pf = pf.get("provided_facts") or []
    meta = {"project_id": a.project_id, "title": a.title, "data_cutoff": a.as_of}
    res = instantiate_project(corpus_dir=a.corpus, project_dir=a.project_dir,
                              provided_facts=pf, meta=meta)
    for k in ("provided", "computed", "undefined_notes", "replay_conflicts", "gate"):
        print("  %-18s %s" % (k, res.get(k)))
    return 0


def cmd_graph(a):
    from corpus_pipeline.graph_from_project import build_graph
    g = build_graph(a.project_dir, meta={"project_id": a.project_id,
                                         "title": a.title, "data_cutoff": a.as_of})
    out = a.out or str(Path(a.project_dir) / "GRAPH.json")
    Path(out).write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→ %s" % out)
    print(json.dumps(g["stats"], ensure_ascii=False, indent=1))
    return 0


def cmd_slots(a):
    import yaml
    from corpus_pipeline.slot_filling import build_slots, hard_constraints, render_ask_list
    gr = yaml.safe_load((Path(a.project_dir) / "quality" / "gate_report.yaml")
                        .read_text(encoding="utf-8")) or {}
    rules = yaml.safe_load(Path(a.rules).read_text(encoding="utf-8")) if a.rules else []
    fsm = {}
    if a.fsm:
        d = yaml.safe_load(Path(a.fsm).read_text(encoding="utf-8")) or {}
        fsm = {x["fact"]: x for x in (d.get("facts") or [])}
    slots = build_slots(gr.get("undefined") or [], rules, fsm)
    print(render_ask_list(hard_constraints(slots, fsm)))
    if a.out:
        Path(a.out).write_text(json.dumps({"slots": slots}, ensure_ascii=False, indent=1),
                               encoding="utf-8")
        print("→ %s" % a.out)
    return 0


def cmd_enrich(a):
    """第八道工序：给节点补 source_type / constraint_type / role / standard_id。"""
    from corpus_pipeline.label_enrichment import enrich
    r = enrich(a.project_dir, dry_run=a.dry_run)
    if r.get("error"):
        print("  ✗ %s" % r["error"], file=sys.stderr)
        return 1
    print("  已标注: %d 个节点%s" % (r["labeled"], "（dry-run，未写盘）" if r["dry_run"] else ""))
    for k in ("by_role", "by_constraint", "by_source"):
        print("  %-16s %s" % (k, r[k]))
    print("  with_standard    %d" % r["with_standard"])
    return 0


def cmd_selftest(a):
    """正则回归自检：反例优先，失败即退出码非 0（不阻断建图，但能挡住代码回归）。"""
    from corpus_pipeline.doc_facts import self_test
    try:
        self_test(verbose=True)
    except AssertionError as e:
        print(str(e), file=sys.stderr)
        return 1
    # 额外跑一遍 slot_filling 的分类自检
    from corpus_pipeline.slot_filling import classify_slot
    cases = [
        ("基本预备费费率", "CUSTOMER", "行业惯例 3-5%", "FILLABLE"),
        ("科研人员用房人均建筑面积指标", "STANDARD", "建标191-2018", "RETRIEVABLE"),
        ("科研人员规划人数", "CUSTOMER_PRIMARY", None, "UPSTREAM"),
        ("输出未提供且无计算规格", None, None, "PSEUDO"),
        ("建设地点", "CUSTOMER", None, "FILLABLE"),
    ]
    bad = 0
    for lab, st, basis, want in cases:
        got = classify_slot(lab, st, basis)
        if got != want:
            print("  [FAIL] classify_slot(%r) → %r，期望 %r" % (lab, got, want), file=sys.stderr)
            bad += 1
    if bad:
        return 1
    print("slot_filling 自检通过：%d 例" % len(cases))
    print("全部自检通过")
    return 0


def cmd_gates(a):
    from corpus_pipeline.quality_gates import run_all_gates
    r = run_all_gates(a.project_dir)
    for g in r.get("gates") or []:
        print("%s %s: %s" % (g["gate"], g["name"], "PASS" if g["passed"] else "FAIL"))
        for c in g.get("checks") or []:
            print("   %s %-32s %s" % ("✓" if c["passed"] else "✗", c["check"], c.get("detail", "")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kp_cli", description="知识处理专家 CLI（不依赖 MCP）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("facts", help="材料 → provided_facts")
    f.add_argument("path"); f.add_argument("--as-of", default="")
    f.add_argument("--caliber", default="客户提供"); f.add_argument("-o", "--out")
    f.set_defaults(fn=cmd_facts)

    b = sub.add_parser("build", help="借形 + 建项目图库")
    b.add_argument("project_dir"); b.add_argument("--corpus", required=True)
    b.add_argument("--facts", required=True)
    b.add_argument("--project-id", default="NEW-PROJECT"); b.add_argument("--title", default="")
    b.add_argument("--as-of", default="")
    b.set_defaults(fn=cmd_build)

    g = sub.add_parser("graph", help="项目图库 → graph.json")
    g.add_argument("project_dir"); g.add_argument("-o", "--out")
    g.add_argument("--project-id", default="NEW-PROJECT"); g.add_argument("--title", default="")
    g.add_argument("--as-of", default="")
    g.set_defaults(fn=cmd_graph)

    s = sub.add_parser("slots", help="填槽 + 硬约束清单")
    s.add_argument("project_dir"); s.add_argument("--rules"); s.add_argument("--fsm")
    s.add_argument("-o", "--out")
    s.set_defaults(fn=cmd_slots)

    en = sub.add_parser("enrich", help="第八道工序：给节点补新规范标签（确定性，零 LLM）")
    en.add_argument("project_dir")
    en.add_argument("--dry-run", action="store_true", help="只统计不写盘")
    en.set_defaults(fn=cmd_enrich)

    st = sub.add_parser("selftest", help="正则与分类回归自检（失败退出码非 0）")
    st.set_defaults(fn=cmd_selftest)

    t = sub.add_parser("gates", help="跑三质量关口")
    t.add_argument("project_dir")
    t.set_defaults(fn=cmd_gates)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
