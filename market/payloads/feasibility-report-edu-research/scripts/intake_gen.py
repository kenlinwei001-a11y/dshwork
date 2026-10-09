#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Intake 问题生成器：按阻塞度排序，把图上的空槽变成两份可执行清单。

interaction.yaml 里写了"按阻塞度降序提问"，但那只是一句话。
不实现的话，提问顺序取决于模型当时想到哪儿，客户会在第 5 章被反复问同类问题。

阻塞度 = 该空槽直接或间接阻塞的下游节点数 + 因它写不出的章节数。
先问总建筑面积（阻塞造价、负荷、能耗、进度四条链），
再问装修标准（只阻塞造价一条链）——顺序不是风格问题，是客户时间成本问题。

用法：
    python3 scripts/intake_gen.py <project.yaml>
    python3 scripts/intake_gen.py <project.yaml> --json out.json
    python3 scripts/intake_gen.py <project.yaml> --batch 5     只出下一批
"""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from schema import _refs_in_formula  # noqa: E402
import validators as V  # noqa: E402
from assets import load_l0, guard  # noqa: E402

MAX_PER_ROUND = 5





# =============================================================================
# 章节检索任务
# =============================================================================

def _load_research():
    f = ROOT / "references/section-research.yaml"
    if not f.exists():
        return {}
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


def research_tasks(proj, core):
    """由法定内容项触发的检索任务。

    这类内容不产生空节点——「科研工作及学术交流」写不写、写得实不实，
    图上看不出任何缺口。所以缺口分诊看不见它们，
    结果就是这几章被写成场面话，而那恰恰是评审判断
    「这份报告是不是认真做的」的第一印象来源。
    """
    spec = _load_research()
    tasks = spec.get("tasks") or {}
    if not tasks:
        return []
    ctx = proj.get("project") or {}
    org = ctx.get("owner") or ctx.get("org") or ctx.get("unit")
    facets = {
        "org": org,
        "location": ctx.get("location"),
        "industry": ctx.get("industry") or ctx.get("profile"),
        "scale": ctx.get("scale_hint"),
        "year": str(proj.get("as_of") or "")[:4],
    }
    # 骨架里已承载的法定内容项
    carried = set()
    for sec in (proj.get("sections") or []):
        if isinstance(sec, dict):
            carried |= set(sec.get("covers") or [])
    if not carried:
        cov = ((core.get("regulatory_anchor") or {}).get("mandatory_coverage") or {})
        for spec_ch in cov.values():
            carried |= set(spec_ch.get("items") or [])

    done = set(proj.get("research_done") or [])
    out = []
    for tid, t in tasks.items():
        trig = [x for x in (t.get("triggers") or []) if x in carried]
        if not trig:
            continue
        if tid in done:
            continue
        need_org = tid in ("RS1_org_profile", "RS2_org_academic",
                           "RS3_org_track_record", "RS4_org_credit")
        queries = []
        blocked = None
        if need_org and not org:
            blocked = ("缺建设单位全称，检索式无法成立。"
                       "不带单位名查出来的是行业综述，写进「单位概况」就是套话。"
                       "先向客户要单位全称。")
        else:
            for q in (t.get("query") or []):
                try:
                    queries.append(q.format(**{k: (v or "?") for k, v in facets.items()}))
                except Exception:
                    queries.append(q)
        out.append({
            "id": tid, "cn": t.get("cn"), "triggered_by": trig,
            "queries": queries, "blocked": blocked,
            "produces": t.get("produces"), "evidence": t.get("evidence"),
            "must_confirm": bool(t.get("must_confirm")),
            "trap": t.get("trap"), "if_not_found": t.get("if_not_found"),
            "pipeline": t.get("pipeline"),
        })
    out.sort(key=lambda x: (not x["must_confirm"], x["id"]))
    return out


def render_research(tasks):
    if not tasks:
        return ""
    L = ["", "=" * 70, f"章节检索任务（{len(tasks)} 项）—— 由法定内容项触发，不占客户时间", "=" * 70,
         "这类内容不产生空节点，缺口分诊看不见它们。不单列出来，", "就会被写成场面话。", ""]
    for i, t in enumerate(tasks, 1):
        mark = "【须客户核对】" if t["must_confirm"] else "【可直接用】"
        L.append(f"{i}. {mark} {t['cn']}  ← 触发自「{'、'.join(t['triggered_by'])}」")
        if t["blocked"]:
            L.append(f"   ⚠ 暂不可执行：{t['blocked']}")
        else:
            for q in t["queries"]:
                L.append(f"   检索式：{q}")
        L.append(f"   查到后写进：{t['produces']}　证据级别：{t['evidence']}")
        if t.get("pipeline"):
            L.append(f"   后续：{t['pipeline']}")
        if t.get("trap"):
            L.append(f"   注意：{' '.join(str(t['trap']).split())}")
        if t.get("if_not_found"):
            L.append(f"   检不到：{t['if_not_found']}")
        L.append("")
    if any(t["must_confirm"] for t in tasks):
        L.append("-" * 70)
        L.append("标「须客户核对」的，结果先呈客户确认再落笔。")
        L.append("写进单位概况的每一句都是**以客户的名义在说**——")
        L.append("同名单位、信息过时、宣传口径，三个坑都在这里。")
    return "\n".join(L)


class IntakeGenerator:

    def __init__(self, proj, core, argu, deriv):
        self.p = proj
        self.core, self.argu, self.deriv = core, argu, deriv
        self.dims = (argu.get("feasibility_frame") or {}).get("dimensions") or {}
        self.nodes = set((proj.get("nodes") or {}).keys())
        self.rules = [r for r in (proj.get("rules") or []) if isinstance(r, dict)]
        self.sections = [s for s in (proj.get("sections") or []) if isinstance(s, dict)]

    # ------------------------------------------------------------------
    def _dep_graph(self):
        """target → 它直接依赖的节点集合。"""
        g = {}
        for r in self.rules:
            t, f = r.get("target"), r.get("formula")
            if not t or not f:
                continue
            try:
                g.setdefault(t, set()).update(_refs_in_formula(f))
            except SyntaxError:
                pass
        return g

    def _blocking_degree(self, missing):
        """某个缺失节点阻塞了多少下游节点（传递闭包）+ 多少章节。"""
        g = self._dep_graph()
        reverse = {}
        for tgt, deps in g.items():
            for d in deps:
                reverse.setdefault(d, set()).add(tgt)

        blocked, frontier = set(), {missing}
        while frontier:
            nxt = set()
            for n in frontier:
                for t in reverse.get(n, ()):
                    if t not in blocked:
                        blocked.add(t)
                        nxt.add(t)
            frontier = nxt

        affected_sections = [
            s["id"] for s in self.sections
            if (set(s.get("provides") or []) & (blocked | {missing}))
        ]
        return len(blocked), blocked, affected_sections

    def _dims_of_node(self, node, blocked):
        ds = set()
        for r in self.rules:
            if r.get("target") in (blocked | {node}) or node in str(r.get("formula", "")):
                sv = r.get("serves")
                if isinstance(sv, str):
                    ds.add(sv)
                elif isinstance(sv, list):
                    ds.update(sv)
        return sorted(ds)

    # ------------------------------------------------------------------
    def missing_nodes(self):
        """公式引用了但图中没有的节点。"""
        missing = {}
        for r in self.rules:
            f = r.get("formula")
            if not f:
                continue
            try:
                refs = _refs_in_formula(f)
            except SyntaxError:
                continue
            targets = {x.get("target") for x in self.rules}
            for ref in refs:
                if ref not in self.nodes and ref not in targets:
                    missing.setdefault(ref, []).append(r.get("id"))
        return missing

    def evidence_gaps(self):
        """证据层缺口：分诊为客户提问还是 web 检索。"""
        gaps = []
        ev = self.p.get("evidence") or {}
        for eid, e in ev.items():
            if not isinstance(e, dict):
                continue
            pv = e.get("provenance")
            if pv == "E1_given" and not e.get("provider"):
                gaps.append(("ask", eid, "缺提供方，无法签认"))
            if pv == "E3_external":
                for f, cn in (("url", "URL"), ("published_at", "发布日期"),
                              ("retrieved_at", "检索日期")):
                    if not e.get(f):
                        gaps.append(("search", eid, f"缺{cn}，不可溯源"))
            if pv == "E6_administrative":
                for f, cn in (("doc_no", "文号"), ("issuer", "发文机关"),
                              ("approved_at", "批复日期"), ("valid_until", "有效期")):
                    if not e.get(f):
                        gaps.append(("ask", eid, f"缺{cn}"))
            if pv == "E5_analogical" and not e.get("comparability"):
                gaps.append(("ask", eid, "未说明可比性条件"))
        return gaps

    def argument_gaps(self):
        """论证层缺口：Toulmin 四项必填 + 维度覆盖。"""
        gaps = []
        claims = self.p.get("claims") or {}
        cn = {"claim": "论点", "grounds": "论据", "warrant": "保证", "backing": "支撑"}
        for k, c in claims.items():
            arg = (c or {}).get("argument") or {}
            for field, label in cn.items():
                if not arg.get(field):
                    who = "search" if field == "backing" else "ask"
                    gaps.append((who, k, f"论证缺「{label}」",
                                 (c.get("serves") or [None])[0]))
        covered = {d for c in claims.values() for d in ((c or {}).get("serves") or [])}
        na = self.p.get("not_applicable") or {}
        for d, spec in self.dims.items():
            if d in covered or d in na:
                continue
            expr = (spec.get("applicable_when") or "always").strip()
            if expr != "always":
                ctx = self.p.get("project") or {}
                key = expr.replace("not ", "").split(".")[-1].strip()
                val = bool(ctx.get(key, False))
                if expr.startswith("not "):
                    val = not val
                if not val:
                    continue
            gaps.append(("ask", d, f"维度「{spec.get('cn')}」尚无论证支撑", d))
        return gaps

    def coverage_gaps(self):
        """法定覆盖缺口。"""
        cov = ((self.core.get("regulatory_anchor") or {}).get("mandatory_coverage") or {})
        carried = set()
        for s in self.sections:
            carried |= set(s.get("covers") or [])
        out = []
        if not self.sections:
            return out
        for ch, spec in cov.items():
            miss = [i for i in (spec.get("items") or []) if i not in carried]
            if miss:
                out.append((ch, spec.get("title"), miss))
        return out

    # ------------------------------------------------------------------
    def build(self):
        ask, search = [], []

        for node, rule_ids in self.missing_nodes().items():
            deg, blocked, secs = self._blocking_degree(node)
            ask.append({
                "kind": "node",
                "subject": node,
                "blocking_degree": deg,
                "blocks_nodes": sorted(blocked),
                "blocks_sections": secs,
                "dimensions": self._dims_of_node(node, blocked),
                "used_by_rules": rule_ids,
                "question": f"请提供「{node}」的取值与单位。",
                "why": (f"它阻塞 {deg} 个下游派生值"
                        + (f"，导致 {len(secs)} 个章节无法起草：{secs}" if secs else "")),
            })

        for g in self.evidence_gaps():
            item = {"kind": "evidence", "subject": g[1], "blocking_degree": 1,
                    "question": f"证据 {g[1]}：{g[2]}",
                    "why": "证据不完整则该论断不可核查"}
            (ask if g[0] == "ask" else search).append(item)

        for g in self.argument_gaps():
            item = {"kind": "argument", "subject": g[1], "blocking_degree": 2,
                    "dimensions": [g[3]] if len(g) > 3 and g[3] else [],
                    "question": g[2],
                    "why": "论证不完整会在评审环节被追问"}
            (ask if g[0] == "ask" else search).append(item)

        for ch, title, miss in self.coverage_gaps():
            ask.append({
                "kind": "coverage", "subject": f"{ch} {title}",
                "blocking_degree": 3 + len(miss),
                "question": f"「{ch} {title}」缺法定内容：{miss}。请提供相关资料，或说明为何不适用。",
                "why": "发改投资规〔2023〕304号 的法定必备内容，缺失会在评审环节被打回",
            })

        ask.sort(key=lambda x: -x["blocking_degree"])
        search.sort(key=lambda x: -x.get("blocking_degree", 0))
        return ask, search


def render(ask, search, batch=None):
    lines = ["=" * 70, "Intake 缺口清单（按阻塞度降序）", "=" * 70, ""]
    shown = ask[:batch] if batch else ask
    lines.append(f"【本轮客户提问】{len(shown)} / 共 {len(ask)} 项")
    if batch and len(ask) > batch:
        lines.append(f"（每轮至多 {batch} 问，避免长问卷。剩余 {len(ask) - batch} 项下轮再问）")
    lines.append("")
    for i, q in enumerate(shown, 1):
        dims = "/".join(q.get("dimensions") or []) or "-"
        lines.append(f"{i}. [{dims}] {q['question']}")
        lines.append(f"   为什么现在问：{q['why']}")
        if q.get("blocks_nodes"):
            lines.append(f"   阻塞节点：{q['blocks_nodes']}")
        lines.append("")

    if search:
        lines.append("-" * 70)
        lines.append(f"【web 检索任务】{len(search)} 项（不占用客户时间，应批量前置执行）")
        lines.append("")
        for i, q in enumerate(search, 1):
            lines.append(f"{i}. {q['question']}")
            lines.append(f"   {q['why']}")
        lines.append("")
    return "\n".join(lines)


@guard
def main(argv):
    if len(argv) < 2:
        print("用法: intake_gen.py <project.yaml> [--json out.json] [--batch N]")
        return 2
    core, argu, deriv = load_l0()
    proj = yaml.safe_load(Path(argv[1]).read_text(encoding="utf-8"))
    gen = IntakeGenerator(proj, core, argu, deriv)
    ask, search = gen.build()

    batch = MAX_PER_ROUND
    if "--batch" in argv:
        batch = int(argv[argv.index("--batch") + 1])
    print(render(ask, search, batch))

    rt = research_tasks(proj, core)
    print(render_research(rt))

    if "--json" in argv:
        out = Path(argv[argv.index("--json") + 1])
        out.write_text(json.dumps({"ask": ask, "search": search, "research": rt},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
