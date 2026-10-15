#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
变更影响分析：改一个上游事实，算出它会牵动什么。

为什么必须有这个：客户随时会说"设计方案调了，总建面变成 26800"。
这是常态不是异常。没有影响分析，就只能靠人回忆哪些地方要跟着改——
而这正是「18319 写成 18219」那类事故的成因。

原则：**先给影响清单，再执行。** 让客户看见这一笔修改的真实代价，
而不是改完之后才发现要重写四章。

用法：
    python3 scripts/impact.py <project.yaml> --set scale.design_total=26800
    python3 scripts/impact.py <project.yaml> --set a=1 --set b=2 --json out.json
    python3 scripts/impact.py <project.yaml> --explain cost.total   只看某节点依赖谁
"""

import copy
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from schema import _refs_in_formula  # noqa: E402
import validators as V  # noqa: E402
from assets import load_l0, guard  # noqa: E402




class ImpactAnalyzer:

    def __init__(self, proj, core, argu, deriv):
        self.p = proj
        self.core, self.argu, self.deriv = core, argu, deriv
        self.rules = [r for r in (proj.get("rules") or []) if isinstance(r, dict)]
        self.sections = [s for s in (proj.get("sections") or []) if isinstance(s, dict)]
        self.claims = proj.get("claims") or {}

    # ------------------------------------------------------------------
    def _deps(self):
        """target → 直接依赖的节点。"""
        g = {}
        for r in self.rules:
            t, f = r.get("target"), r.get("formula")
            if t and f:
                try:
                    g.setdefault(t, set()).update(_refs_in_formula(f))
                except SyntaxError:
                    pass
        return g

    def _reverse(self):
        rev = {}
        for tgt, deps in self._deps().items():
            for d in deps:
                rev.setdefault(d, set()).add(tgt)
        return rev

    def downstream(self, nodes):
        """沿 derives / aggregates 边前向传播，返回受影响的派生节点。"""
        rev = self._reverse()
        out, frontier = set(), set(nodes)
        while frontier:
            nxt = set()
            for n in frontier:
                for t in rev.get(n, ()):
                    if t not in out:
                        out.add(t)
                        nxt.add(t)
            frontier = nxt
        return out

    def explain(self, node):
        """某节点由谁算出、依赖哪些叶子。"""
        deps = self._deps()
        rule = next((r for r in self.rules if r.get("target") == node), None)
        chain, seen, frontier = [], set(), {node}
        while frontier:
            nxt = set()
            for n in frontier:
                for d in deps.get(n, ()):
                    if d not in seen:
                        seen.add(d)
                        nxt.add(d)
                        chain.append((n, d))
            frontier = nxt
        leaves = sorted(seen - set(deps))
        return {"node": node,
                "rule": rule.get("id") if rule else None,
                "formula": rule.get("formula") if rule else None,
                "depends_on": sorted(seen),
                "leaves": leaves}

    # ------------------------------------------------------------------
    def _recompute(self, overrides):
        """在覆盖值之上重跑一遍派生，返回 {node: (old, new)} 与变更前的错误集。

        断链的推演节点没有 value（算不出来，也不该编一个）。以前这里假设
        每个节点都有 value，直接 KeyError 崩掉——而影响分析恰恰是
        「图上还有断链」的时候最需要跑的东西。
        """
        base = V.Validator(self.core, self.argu, self.deriv, self.p)
        base.run()
        # 断链的推演节点没有 value（它算不出来，也不该编一个）。
        # 以前这里直接 KeyError，整个影响分析崩掉——而影响分析恰恰是
        # 「图上还有断链」时最需要跑的东西。
        before = {k: v.get("value") for k, v in base.nodes.items()}
        self._errors_before = {(f.code, f.subject) for f in base.findings
                               if f.severity == "error"}

        p2 = copy.deepcopy(self.p)
        nodes2 = p2.setdefault("nodes", {})
        for k, val in overrides.items():
            if k in nodes2:
                nodes2[k] = dict(nodes2[k]); nodes2[k]["value"] = val
            else:
                nodes2[k] = {"value": val, "unit": "?", "provenance": "E1_given",
                             "source": "变更"}
        # 受影响的派生节点先清空声明值，让规则重新产生
        for n in self.downstream(set(overrides)):
            nodes2.pop(n, None)

        after_v = V.Validator(self.core, self.argu, self.deriv, p2)
        after_v.run()
        after = {k: v.get("value") for k, v in after_v.nodes.items()}

        delta = {}
        for k in set(before) | set(after):
            b, a = before.get(k), after.get(k)
            if b != a:
                delta[k] = (round(b, 4) if isinstance(b, float) else b,
                            round(a, 4) if isinstance(a, float) else a)
        return delta, after_v

    # ------------------------------------------------------------------
    def analyze(self, overrides):
        changed_nodes = set(overrides)
        derived = self.downstream(changed_nodes)
        delta, after_v = self._recompute(overrides)
        touched = changed_nodes | derived | set(delta)

        # 受影响章节：provides 或 restates 命中
        secs = []
        for s in self.sections:
            hit_nodes = sorted(set(s.get("provides") or []) & touched)
            hit_claims = []
            for ck in (s.get("restates") or []):
                c = self.claims.get(ck) or {}
                if self._claim_touches(c, touched):
                    hit_claims.append(ck)
            if hit_nodes or hit_claims:
                secs.append({"id": s.get("id"), "title": s.get("title"),
                             "nodes": hit_nodes, "claims": hit_claims,
                             "derived_only": bool(s.get("derived_only"))})

        # 受影响论断
        cl = []
        for k, c in self.claims.items():
            if self._claim_touches(c or {}, touched):
                arg = (c or {}).get("argument") or {}
                cl.append({"key": k, "serves": (c or {}).get("serves") or [],
                           "has_qualifier": bool(arg.get("qualifier")),
                           "has_robustness": bool(arg.get("robustness"))})

        # 只报**新增**的错误。把既有错误混进来会让客户误以为是这次改动造成的，
        # 从而不敢改——那就本末倒置了。
        new_findings = [f.to_dict() for f in after_v.findings
                        if f.severity == "error"
                        and (f.code, f.subject) not in self._errors_before]

        return {
            "overrides": overrides,
            "delta": {k: {"old": v[0], "new": v[1]} for k, v in sorted(delta.items())},
            "affected_sections": secs,
            "affected_claims": cl,
            "errors_after_change": new_findings,
        }

    def _claim_touches(self, claim, touched):
        """论断是否引用了受影响节点。保守判定：文本里出现节点名即算。"""
        blob = json.dumps(claim, ensure_ascii=False)
        return any(n in blob for n in touched)


def render(res):
    L = ["=" * 70, "变更影响分析", "=" * 70, ""]
    L.append("【本次变更】")
    for k, v in res["overrides"].items():
        L.append(f"  {k} → {v}")
    L.append("")

    d = res["delta"]
    L.append(f"【派生值变化】{len(d)} 项")
    if not d:
        L.append("  无——该节点没有下游派生，或规则未覆盖它")
    for k, v in d.items():
        L.append(f"  {k}: {v['old']} → {v['new']}")
    L.append("")

    secs = res["affected_sections"]
    L.append(f"【需重写的章节】{len(secs)} 章")
    for s in secs:
        tag = "（纯派生章，自动重生成）" if s["derived_only"] else "（含实质论述，需人工确认）"
        L.append(f"  {s['id']} {s.get('title') or ''} {tag}")
        if s["nodes"]:
            L.append(f"      涉及节点：{s['nodes']}")
        if s["claims"]:
            L.append(f"      涉及论断：{s['claims']}")
    L.append("")

    cl = res["affected_claims"]
    if cl:
        L.append(f"【需复核的论断】{len(cl)} 条")
        for c in cl:
            hints = []
            if c["has_qualifier"]:
                hints.append("限定条件可能失效")
            if c["has_robustness"]:
                hints.append("敏感性与临界值需重算")
            L.append(f"  {c['key']} [{'/'.join(c['serves']) or '-'}]"
                     + (f"  —— {'；'.join(hints)}" if hints else ""))
        L.append("")

    errs = res["errors_after_change"]
    if errs:
        L.append(f"【本次变更**新引入**的错误】{len(errs)} 项（既有问题不计）")
        for e in errs[:10]:
            L.append(f"  [{e['code']}] {e['subject']}：{e['message']}")
        if len(errs) > 10:
            L.append(f"  … 另 {len(errs) - 10} 项")
        L.append("")

    L.append("-" * 70)
    L.append("以上为影响清单。确认后才执行回写与重写——")
    L.append("先给清单再执行，是为了让客户看见这一笔修改的真实代价。")
    return "\n".join(L)


@guard
def main(argv):
    if len(argv) < 2:
        print("用法: impact.py <project.yaml> --set node=value [--set ...] [--json out]")
        print("      impact.py <project.yaml> --explain <node>")
        return 2
    core, argu, deriv = load_l0()
    proj = yaml.safe_load(Path(argv[1]).read_text(encoding="utf-8"))
    an = ImpactAnalyzer(proj, core, argu, deriv)

    if "--explain" in argv:
        node = argv[argv.index("--explain") + 1]
        info = an.explain(node)
        print(f"{node} 由规则 {info['rule']} 计算：")
        print(f"  {info['formula']}")
        print(f"  依赖 {len(info['depends_on'])} 个节点，其中叶子（需人工提供）：")
        for l in info["leaves"]:
            print(f"    · {l}")
        return 0

    overrides = {}
    for i, a in enumerate(argv):
        if a == "--set":
            k, _, v = argv[i + 1].partition("=")
            try:
                overrides[k] = float(v) if "." in v else int(v)
            except ValueError:
                overrides[k] = v
    if not overrides:
        print("需要至少一个 --set node=value")
        return 2

    res = an.analyze(overrides)
    print(render(res))
    if "--json" in argv:
        out = Path(argv[argv.index("--json") + 1])
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
