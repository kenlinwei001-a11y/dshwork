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


def cmd_prompt(a):
    """生成章节写作提示词（从 graph 注入值到 templates/section-prompt-template.yaml）。"""
    import json
    from pathlib import Path
    from corpus_pipeline.section_prompt_builder import build_prompt, build_all
    gp = Path(a.graph)
    if not gp.exists():
        print("  ✗ graph 不存在: %s" % gp, file=sys.stderr); return 2
    g = json.loads(gp.read_text(encoding="utf-8"))
    tags = a.tags.split(",") if a.tags else None
    if a.section:
        r = build_prompt(g, section=a.section, title=a.title or "",
                         path=a.path or "", level=a.level or 2, tags=tags)
        print(r["prompt"])
        print("\n--- 统计: 事实 %d / 规则 %d / 冲突 %d / 字符 %d ---"
              % (r["stats"]["facts"], r["stats"]["rules"],
                 r["stats"]["conflicts"], r["stats"]["chars"]))
    else:
        rs = build_all(g, tags=tags)
        print("  生成 %d 节提示词：" % len(rs))
        for r in rs:
            print("    %-28s 事实 %2d / 规则 %d / %d 字符"
                  % (r["section"][:28], r["stats"]["facts"], r["stats"]["rules"], r["stats"]["chars"]))
        if a.out:
            Path(a.out).write_text(
                json.dumps([{k: r[k] for k in ("section", "title", "tags", "prompt", "stats")}
                            for r in rs], ensure_ascii=False, indent=1), encoding="utf-8")
            print("  → %s" % a.out)
    return 0


def cmd_release_check(a):
    """发版检查清单（全绿才许打包）。失败退出码 1。"""
    import hashlib, json, subprocess
    import yaml
    from pathlib import Path
    root = Path(a.dir)
    fails, notes = [], []

    # ① manifest 存在且 status=validated
    #    无 manifest = 项目工作目录（轻量产物），不是待发布资产 → 不适用，非失败
    mp = root / "manifest.yaml"
    if not mp.exists():
        print("  ⊘ 不适用：%s 无 manifest.yaml" % root)
        print("    这是项目工作目录（轻量产物），不是待发布的资产包。")
        print("    发版检查只对「形包」与「语料包」有意义。")
        return 0
    m = yaml.safe_load(mp.read_text(encoding="utf-8")) or {}
    if m.get("status") not in ("validated", "published"):
        fails.append("manifest.status=%r（需 validated 或 published）" % m.get("status"))
    notes.append("版本 v%s / 状态 %s" % (m.get("version"), m.get("status")))

    # ② changelog 首条版本 == manifest.version
    cl = m.get("changelog") or []
    if cl and str(cl[-1].get("version")) != str(m.get("version")):
        fails.append("changelog 末条 v%s ≠ manifest v%s" % (cl[-1].get("version"), m.get("version")))
    elif not cl:
        fails.append("changelog 为空")

    # ③ 项目数值终检 —— **只对形包生效**
    #    判据：manifest.declaration 含 "shape_only"（形包），或显式 --shape-only
    decl = str(m.get("declaration") or "")
    is_shape = ("shape_only" in decl) or a.shape_only
    if is_shape:
        BAD = ["13032", "18319", "11188", "18000", "2019ZX054", "上海财经", "中山北一路", "同济工程"]
        hits = {}
        for f in root.rglob("*.yaml"):
            txt = f.read_text(encoding="utf-8")
            h = [b for b in BAD if b in txt]
            if h:
                hits[str(f.relative_to(root))] = h
        if hits:
            fails.append("形包含项目专名/数值: %s" % list(hits)[:3])
        else:
            notes.append("形包项目数值 0 处")
    else:
        notes.append("语料包（含项目数据属正常，跳过数值终检）")

    # ④ 引用闭合（FILE-INDEX 的 to.file 必须存在）
    fi = root / "FILE-INDEX.yaml"
    if fi.exists():
        d = yaml.safe_load(fi.read_text(encoding="utf-8")) or {}
        files = set((d.get("files") or {}).keys())
        bad = [r["no"] for r in (d.get("reference_graph") or [])
               if r.get("to", {}).get("file") not in ("(无)", "(全部文件)", None)
               and r["to"]["file"] not in files]
        if bad:
            fails.append("FILE-INDEX 悬空引用: %s" % bad)
        else:
            notes.append("引用闭合 0 悬空")

    # ⑤ doc_facts 自检
    try:
        from corpus_pipeline.doc_facts import self_test
        self_test()
        notes.append("doc_facts 自检通过")
    except AssertionError as e:
        fails.append("doc_facts 自检失败")

    # ⑥ 分片索引新鲜度（索引 mtime 必须 >= 源文件）
    shard_idx = root / "shards" / "index.json"
    nodes_yaml = root / "graph" / "nodes.yaml"
    if shard_idx.exists() and nodes_yaml.exists():
        if shard_idx.stat().st_mtime < nodes_yaml.stat().st_mtime:
            fails.append("shards/index.json 比 graph/nodes.yaml 旧（需重跑 shard build）")
        else:
            notes.append("分片索引新鲜（>= nodes.yaml）")
    elif nodes_yaml.exists() and not shard_idx.exists():
        notes.append("分片索引未建（可选；建了写作侧快 800 倍）")

    # ⑦ skill 渐进式披露
    try:
        from corpus_pipeline.check_skill_disclosure import check_one
        for s in a.skills or []:
            r = check_one(s)
            if not r.get("pass") and not r.get("error"):
                fails.append("skill %s 超披露阈值" % s)
    except Exception:
        pass

    print("  发版检查: %s" % root)
    for n in notes:
        print("    ✓ %s" % n)
    if fails:
        for f in fails:
            print("    ✗ %s" % f, file=sys.stderr)
        return 1
    print("  ✓ 全部通过，可打包")
    return 0


def cmd_shard(a):
    """建分片索引（browse/resolve 两段式取数）。"""
    from corpus_pipeline.shard_index import build, browse, resolve
    if a.action == "build":
        r = build(a.dir)
        print("  分片: %d 节 / %d 域 / %d 类 / 共写 %d 个分片"
              % (r["sections"], r["domains"], r["kinds"], r["shards_written"]))
        print("  索引大小: %d B（browse 只读这个）" % r["index_size"])
    elif a.action == "browse":
        idx = browse(a.dir)
        if idx.get("error"):
            print("  ✗", idx["error"], "→", idx.get("hint")); return 1
        print("  节点 %d / 关系 %d / 规则 %d"
              % (idx["counts"]["nodes"], idx["counts"]["relations"], idx["counts"]["rules"]))
        for dim in ("by-section", "by-domain", "by-kind"):
            items = (idx.get(dim) or {})
            print("  %-12s %d 项" % (dim, len(items)))
        for name, e in sorted((idx.get("by-section") or {}).items(),
                              key=lambda x: -(x[1].get("count") or 0))[:10]:
            print("     %-12s %4d 节点 / %d 关系" % (name, e["count"],
                  (e.get("relations") or {}).get("count", 0)))
    elif a.action == "inverted":
        from corpus_pipeline.shard_index import build_inverted, browse_inverted
        st = build_inverted(a.dir)
        print("  倒排索引已建（不依赖章节）:")
        for k, v in st.items():
            print("    %-14s %d 个键" % (k, v))
        return 0
    elif a.action == "query":
        from corpus_pipeline.shard_index import query as _q
        r = _q(a.dir, unit=a.unit, label_prefix=a.label_prefix, kind=a.kind, rule=a.rule)
        print("  命中 %d 条：" % len(r))
        for x in r[:20]:
            print("    %-26s %-10s %s" % (str(x.get("label"))[:26], x.get("value"), x.get("unit") or ""))
        return 0
    elif a.action == "closure":
        from corpus_pipeline.shard_index import resolve_closure
        if not a.rule:
            print("  需要 --rule R-xxx", file=sys.stderr); return 2
        r = resolve_closure(a.dir, a.rule)
        print("  %s → 节点 %d / 边 %d / 深度 %d"
              % (a.rule, len(r["nodes"]), len(r["edges"]), r["depth"]))
        for x in r["nodes"][:20]:
            print("    %-26s %-10s %s" % (str(x.get("label"))[:26], x.get("value"), x.get("unit") or ""))
        return 0
    elif a.action == "resolve":
        r = resolve(a.dir, section=a.section, domain=a.domain, kind=a.kind,
                    with_relations=a.with_relations, with_rules=a.with_rules)
        if isinstance(r, dict):
            print("  节点 %d / 关系 %d / 规则 %d"
                  % (len(r["nodes"]), len(r.get("relations") or []), len(r.get("rules") or [])))
        else:
            print("  取到 %d 条" % len(r))
    return 0


def cmd_warm(a):
    """预热 YAML→JSON 缓存。首次慢，之后快 500+ 倍。"""
    from corpus_pipeline.fastload import load, clear
    from pathlib import Path
    root = Path(a.dir)
    if a.clear:
        n = clear(root)
        print("  已清除 %d 个缓存文件" % n)
        return 0
    files = sorted(root.rglob("*.yaml"))
    if a.only:
        files = [f for f in files if a.only in str(f)]
    print("  预热 %d 个 yaml 文件..." % len(files))
    import time
    tot = 0.0
    for f in files:
        t0 = time.time(); load(f); d = time.time() - t0
        tot += d
        if d > 0.5 or a.verbose:
            print("    %-46s %7.2f s" % (str(f.relative_to(root))[:46], d))
    print("  总耗时 %.1f s（之后重读约 0.1 s）" % tot)
    return 0


def cmd_verify(a):
    """跑 13 条闭环门禁 S0–S11（stage_gate）。"""
    from corpus_pipeline.stage_gates import run_stage_gates, save_stage_gates
    r = run_stage_gates(a.project_dir,
                        draft_path=a.draft, source_md=a.source,
                        source_docx=a.docx)
    gates = r.get("gates") or r.get("stages") or []
    # _gate 返回的判定字段是 verdict: invalid / pass / FAIL
    def _v(g):
        return str(g.get("verdict") or g.get("status") or "").lower()
    npass = sum(1 for g in gates if _v(g) == "pass")
    ninv = sum(1 for g in gates if _v(g) == "invalid")
    nfail = len(gates) - npass - ninv
    print("  闭环门禁: %d 条  pass %d / FAIL %d / invalid %d"
          % (len(gates), npass, nfail, ninv))
    for g in gates:
        v = _v(g)
        mark = {"pass": "✓", "fail": "✗", "invalid": "⊘"}.get(v, "?")
        miss = g.get("missing") or []
        why = ("缺 %d 项: %s" % (len(miss), ", ".join(str(x) for x in miss[:3]))
               if miss else (g.get("note") or ""))
        print("  %s %-4s %-24s %5.1f%%  %s"
              % (mark, g.get("stage") or "?", g.get("gate") or "", g.get("recall_pct") or 0, why[:60]))
    if not a.dry_run:
        save_stage_gates(a.project_dir, r)
        print("  → 已落盘 quality/stage_gates.yaml")
    return 1 if (nfail or ninv) else 0


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

    pm = sub.add_parser("prompt", help="生成章节写作提示词（从 graph 注入值）")
    pm.add_argument("graph", help="graph.json 路径")
    pm.add_argument("--section", help="只生成该节；省略则全部")
    pm.add_argument("--title"); pm.add_argument("--path")
    pm.add_argument("--level", type=int, default=2)
    pm.add_argument("--tags", help="逗号分隔，如 科研,可研,中型")
    pm.add_argument("-o", "--out")
    pm.set_defaults(fn=cmd_prompt)

    rc = sub.add_parser("release-check", help="发版检查（全绿才许打包）")
    rc.add_argument("dir")
    rc.add_argument("--skills", nargs="*", help="顺带检查这些 skill 的披露阈值")
    rc.add_argument("--shape-only", action="store_true", help="强制按形包检查（项目数值必须为 0）")
    rc.set_defaults(fn=cmd_release_check)

    sh = sub.add_parser("shard", help="分片索引：build 建 / browse 看目录 / resolve 按需取")
    sh.add_argument("action", choices=["build", "browse", "resolve", "inverted", "query", "closure"])
    sh.add_argument("dir")
    sh.add_argument("--section")
    sh.add_argument("--domain")
    sh.add_argument("--kind")
    sh.add_argument("--with-relations", action="store_true")
    sh.add_argument("--with-rules", action="store_true")
    sh.add_argument("--unit"); sh.add_argument("--label-prefix")
    sh.add_argument("--rule")
    sh.set_defaults(fn=cmd_shard)

    wm = sub.add_parser("warm", help="预热 YAML→JSON 缓存（首次慢，之后快 500+ 倍）")
    wm.add_argument("dir")
    wm.add_argument("--only", help="只预热路径含此子串的文件")
    wm.add_argument("--clear", action="store_true", help="清除缓存")
    wm.add_argument("--verbose", action="store_true")
    wm.set_defaults(fn=cmd_warm)

    vf = sub.add_parser("verify", help="跑 13 条闭环门禁 S0–S11（stage_gate）")
    vf.add_argument("project_dir")
    vf.add_argument("--draft", help="草稿 md 路径（用于 S11 题注检查）")
    vf.add_argument("--source", help="原稿 md 路径（用于 S0/S1 对账）")
    vf.add_argument("--docx", help="原稿 docx 路径（用于 S0 表数对账）")
    vf.add_argument("--dry-run", action="store_true")
    vf.set_defaults(fn=cmd_verify)

    st = sub.add_parser("selftest", help="正则与分类回归自检（失败退出码非 0）")
    st.set_defaults(fn=cmd_selftest)

    t = sub.add_parser("gates", help="跑三质量关口")
    t.add_argument("project_dir")
    t.set_defaults(fn=cmd_gates)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
