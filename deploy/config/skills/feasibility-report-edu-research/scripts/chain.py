#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推演链核验：每个推演值是否都追得到源数据。

图上分两类节点：
    given    源数据。客户给的、素材里抽的、规范查表得的。必须带 from
    derived  推演值。必须有一条 rule，rule 的每个输入都要在图上存在

**凡推演值，输入链必须一路追到 given。** 追不到的不是推演值，是拍的。

这个检查看起来简单，实际拦的是可研里最难查的一类错。断链的表现形式
不是「算错了」——算错能被复算发现——而是**中间少了一步，结果直接写出来**。
上一份真实报告里就有三处：给了用电指标 70 W/㎡、给了结果 952 kW，
没给中间的需要系数；给了最高日用水量 95.04，没给定额、人数口径、变化系数。
正文读起来完全正常，评审问一句「这个数怎么来的」就答不上。

所以本脚本报三种状态，且**不合并**：

    closed                  每个输入都追到了 given 或 norm
    closed_with_placeholder 有输入是反算值或替代值，已标 is_placeholder
    broken                  有输入缺失，无法复算，必须写 broken_reason

**反算不算闭合。** 由结果反解一个系数，能让链在形式上闭合、复算能对上、
检查器报绿——但它证明的只是「用这个系数能倒推回那个结果」，
不是「这个结果是对的」。这是编造穿了推演的外衣，比直接填一个数更难发现。

用法：
  chain.py project.yaml            核验全图
  chain.py project.yaml --node X   只看某个节点的推演链
"""

import sys
import argparse
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assets import guard  # noqa: E402
from schema import _refs_in_formula  # noqa: E402

OK = {"closed", "closed_with_placeholder", "broken"}
UNKNOWN_VALUES = {None, "", "UNKNOWN", "unknown", "TBD"}


def rule_index(proj):
    idx = {}
    for r in (proj.get("rules") or []):
        if isinstance(r, dict) and r.get("target"):
            idx[r["target"]] = r
    return idx


def declared_inputs(rule):
    """规则声明的输入。优先用 inputs 字段，没有就从公式里抽引用。

    两者都要看：inputs 是人写的、带角色和状态；公式里的引用是机器抽的。
    **对不上就是问题**——公式里用了但没在 inputs 里声明的，多半是被忘了，
    而被忘的那个往往正是缺失的那个。
    """
    declared = rule.get("inputs") or {}
    if isinstance(declared, list):
        declared = {x: {} for x in declared}
    # 比选型推演没有 formula——结论是选出来的，不是算出来的。
    # 这里空着不是缺陷，缺陷是 inputs 也空着。
    expr = (rule.get("formula") or "").strip()
    try:
        from_formula = set(_refs_in_formula(expr)) if expr else set()
    except SyntaxError:
        from_formula = set()
    return declared, from_formula


def trace(proj, node, rules, seen=None, depth=0):
    """一个节点的推演链。返回 (状态, 叶子源数据集合, 问题清单)。"""
    seen = seen or set()
    if node in seen:
        return "cycle", set(), [f"{node}：推演回环"]
    seen = seen | {node}
    nodes = proj.get("nodes") or {}
    spec = nodes.get(node)
    if spec is None:
        return "missing", set(), [f"{node}：图上没有这个节点"]

    tier = spec.get("tier") or ("derived" if node in rules else "given")
    if tier != "derived":
        if spec.get("value") in UNKNOWN_VALUES:
            return "unknown", set(), [f"{node}：源数据为 UNKNOWN"]
        if spec.get("is_placeholder"):
            return "placeholder", {node}, []
        if not spec.get("from") and (spec.get("provenance") or "").startswith("E1"):
            # 客户给的值必须指得回具体材料的具体页，否则 C8 无从查起
            return "closed", {node}, [f"{node}：给定值缺 from（指不回素材出处）"]
        return "closed", {node}, []

    rule = rules.get(node)
    if not rule:
        return "broken", set(), [f"{node}：标为 derived 却没有对应规则"]

    declared, from_formula = declared_inputs(rule)
    problems = []
    undeclared = from_formula - set(declared)
    if declared and undeclared:
        problems.append(f"{rule['id']}：公式用了 {sorted(undeclared)} 但 inputs 里没声明")

    leaves, worst = set(), "closed"
    order = {"closed": 0, "placeholder": 1, "unknown": 2, "broken": 3,
             "missing": 3, "cycle": 3}
    for dep in (set(declared) | from_formula):
        st, lv, pr = trace(proj, dep, rules, seen, depth + 1)
        leaves |= lv
        problems += pr
        if order.get(st, 3) > order.get(worst, 0):
            worst = st
    status = {"closed": "closed", "placeholder": "closed_with_placeholder"}.get(
        worst, "broken")

    claimed = rule.get("chain_status")
    if claimed and claimed in OK and claimed != status:
        problems.append(
            f"{rule['id']}：声明 chain_status={claimed}，实际核验为 {status}")
    if status == "broken" and not rule.get("broken_reason"):
        problems.append(f"{rule['id']}：链已断但没写 broken_reason")
    for f in ("method", "warrant"):
        if not rule.get(f):
            problems.append(f"{rule['id']}：缺 {f}（推演逻辑不完整，C22）")
    return status, leaves, problems


def render(proj, only=None):
    rules = rule_index(proj)
    nodes = proj.get("nodes") or {}
    derived = [n for n, s in nodes.items()
               if (s.get("tier") or ("derived" if n in rules else "given")) == "derived"]
    if only:
        derived = [n for n in derived if n == only]

    L = ["=" * 74, "推演链核验", "=" * 74, ""]
    given = [n for n in nodes if n not in derived]
    unknown = [n for n in given if (nodes[n].get("value") in UNKNOWN_VALUES)]
    L.append(f"节点 {len(nodes)}　源数据 {len(given)}（其中 UNKNOWN {len(unknown)}）"
             f"　推演值 {len(derived)}")
    L.append("")

    tally, allprob = {}, []
    for n in sorted(derived):
        st, leaves, prob = trace(proj, n, rules)
        tally[st] = tally.get(st, 0) + 1
        allprob += prob
        mark = {"closed": "✓", "closed_with_placeholder": "◐"}.get(st, "✗")
        r = rules.get(n) or {}
        L.append(f"{mark} {n}　[{r.get('method', '?')}]　{st}")
        L.append(f"    式：{r.get('formula', '—')}")
        if r.get("warrant"):
            L.append(f"    凭什么：{str(r['warrant'])[:88]}")
        ins = r.get("inputs") or {}
        if isinstance(ins, dict) and ins:
            for k, v in ins.items():
                s = (v or {}).get("status", "")
                flag = "  ✗缺" if s == "UNKNOWN" else ("  ◐" if s in
                                                      ("placeholder", "待核") else "")
                L.append(f"      ← {k}　（{(v or {}).get('role', '')}"
                         f"／{(v or {}).get('source', '')}）{flag}")
        for a in (r.get("assumptions") or []):
            L.append(f"    口径：{a.get('text')}　→ 换成「"
                     f"{'／'.join(a.get('alternatives') or ['—'])}」：{a.get('impact')}")
        if st == "broken":
            for ln in str(r.get("broken_reason", "")).strip().splitlines()[:3]:
                L.append(f"    ✗ {ln}")
        else:
            L.append(f"    源数据：{sorted(leaves)}")
        L.append("")

    L.append("-" * 74)
    L.append("　".join(f"{k} {v}" for k, v in sorted(tally.items())) or "没有推演值")
    if allprob:
        L.append("")
        L.append(f"结构问题 {len(allprob)} 条：")
        for p in sorted(set(allprob)):
            L.append(f"  · {p}")
    L.append("")
    L.append("断链不是可以容忍的中间状态，是**这一处推演没人能复核**。")
    L.append("正确处置是回查原始计算书或向客户求证，**不是反算**——")
    L.append("由结果反解系数能让链在形式上闭合，检查器也报绿，")
    L.append("但它证明的只是「用这个系数能倒推回那个结果」。")
    return "\n".join(L), tally, allprob


def table(proj):
    """把「哪些推演说不清楚」列成一张表。

    正文里的断链是看不见的——每一段都通顺。摊成表之后，
    「这个结论没有源数据」就变成了一行字，可以直接拿去追料或问客户。
    """
    rules, nodes = rule_index(proj), proj.get("nodes") or {}
    derived = [n for n, s in nodes.items()
               if (s.get("tier") or ("derived" if n in rules else "given")) == "derived"]
    L = ["| 推演项 | 结论 | 方法 | 依据 | 源数据 | 缺什么 | 后果 |",
         "|---|---|---|---|---|---|---|"]
    rows = 0
    for n in sorted(derived):
        st, leaves, _ = trace(proj, n, rules)
        r = rules.get(n) or {}
        ins = r.get("inputs") or {}
        miss = [k for k, v in ins.items()
                if (v or {}).get("status") in ("UNKNOWN", "broken")]
        if st == "closed" and not miss:
            continue                      # 说得清楚的不进表，进表的都是要处理的
        rows += 1
        val = str(nodes[n].get("value", "—"))[:24]
        basis = r.get("basis") or ("—" if r.get("operator") == "select" else "**无**")
        src = {"closed_with_placeholder": "◐ 含替代值", "broken": "✗ 不全"}.get(st, "✓")
        if r.get("operator") == "select" and not miss:
            miss_s = "比选矩阵与选择理由" if r.get("rationale") in (None, "报告未说明") else "—"
        else:
            miss_s = "、".join(miss) or "—"
        why = str(r.get("broken_reason") or r.get("note") or "").strip().splitlines()
        why = (why[0] if why else "—").replace("**", "")[:44]
        L.append(f"| `{n}` | {val} | {r.get('method', '?')} | {basis} | {src} | {miss_s} | {why} |")
    L.append("")
    L.append(f"共 {rows} 项说不清楚（推演值合计 {len(derived)} 项）。")
    return "\n".join(L)


@guard
def main(argv):
    ap = argparse.ArgumentParser(description="推演链核验：推演值是否都追得到源数据")
    ap.add_argument("project")
    ap.add_argument("--node", help="只看某个节点")
    ap.add_argument("--table", action="store_true", help="只输出「说不清楚的推演」表格")
    a = ap.parse_args(argv[1:])
    proj = yaml.safe_load(Path(a.project).read_text(encoding="utf-8")) or {}
    if a.table:
        print(table(proj))
        return 0
    txt, tally, prob = render(proj, a.node)
    print(txt)
    return 1 if (tally.get("broken") or prob) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
