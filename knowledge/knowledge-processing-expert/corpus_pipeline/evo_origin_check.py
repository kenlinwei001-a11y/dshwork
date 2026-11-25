# -*- coding: utf-8 -*-
"""evo_origin_check —— 节点「原始输入 / 派生」属性的自洽判定（确定性，零 LLM）。

## 用户要解决的问题

    「如果一个节点本身标注应该是派生的，客户却直接给了，
      则需要通过图谱查询关系，是否存在部分节点的属性从客户输入的标签
      转化为派生属性，逻辑是否自洽」

    土建工程 就是典型：
      形包标注 R-土建工程（该是派生 = 七项加总）
      客户却直接给了 6780
      查子项：桩基420+基坑380+地下720+地上4860+装配式400+室内1650+外立面920 = 9350
      客户值 6780 ≠ 9350，规则值 9350 == 9350
      → 该节点确实是派生，客户值是对派生结果的异议，不是原始输入

## 四种属性归属（判定表）

| 形包有 rule | 客户有值 | 子项齐 | 三方关系 | 判定 origin | 处置 |
|---|---|---|---|---|---|
| ✗ | ✓ | — | — | **input** | 直接用客户值 |
| ✓ | ✗ | ✓ | — | **derived** | 用规则算 |
| ✓ | ✓ | ✓ | 客户值 == 子项加总 | **input**（属性转化） | 客户给的就是对的，规则值仅校验 |
| ✓ | ✓ | ✓ | 客户值 ≠ 子项加总，规则值 == 子项加总 | **derived** | 保持派生，客户值记为异议 |
| ✓ | ✓ | ✓ | 客户值 ≠ 子项，规则值 ≠ 子项 | **derived** | 三方都不自洽，标待审 |
| ✓ | ✓ | ✗ | — | **undetermined** | 补子项后再判 |

## 输出

每个节点一条：
    {subject, origin, evidence, conflict, action, ...}
汇总：
    {counts: {input, derived, undetermined}, items: [...], to_ask_customer: [...]}
"""
from __future__ import annotations

import json
import re
from pathlib import Path

EPS_ABS = 1.5      # 绝对容差（金额级）
EPS_REL = 0.01     # 相对容差 1%


def _close(a, b):
    """两数是否「相等」：相对 1% 或绝对 1.5，取严（更严格的那个）。

    反例：年总用水量 1.89 vs 1.17，差 0.72。若只用绝对容差 1.5 会误判相等，
          但相对差 (1.89-1.17)/1.89 = 38%，必须判不等。
    """
    if a is None or b is None:
        return False
    a, b = float(a), float(b)
    if a == b:
        return True
    scale = max(abs(a), abs(b), 1e-9)
    return abs(a - b) <= min(EPS_ABS, scale * EPS_REL)


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None




# ================================================================ 规则求值
# 「子项加总」只对求和型规则有效；乘法/除法型必须真的执行表达式。
# 复用 gate_engine 的 _Safe AST 白名单，不用 eval。

_PSEUDO = {"expr 已泛化", "expr泛化", "section_basis", "section"}


def _clean_deps(deps):
    """过滤伪依赖。"""
    return [d for d in deps if str(d).strip() and str(d).strip() not in _PSEUDO]


def _eval_rule(expr, env):
    """用 AST 白名单求值 expr。env: {中文变量名: 数值}。失败返回 None。

    做法：把 {中文变量} 换成 v0/v1/...，再交给 gate_engine._Safe(env).eval(expr_str)。
    """
    if not expr:
        return None
    import re as _re
    try:
        from corpus_pipeline.evo_gate_engine import _Safe
    except Exception:
        return None
    vars_ = list(dict.fromkeys(_re.findall(r"\{([^}]+)\}", str(expr))))
    if not vars_:
        return None
    e2, vmap = str(expr), {}
    for i, v in enumerate(vars_):
        key = "v%d" % i
        val = env.get(v)
        if val is None:
            return None
        vmap[key] = val
        e2 = e2.replace("{%s}" % v, key)
    try:
        return float(_Safe(vmap).eval(e2))
    except Exception:
        return None


def _is_pure_sum(expr):
    """判断表达式是否「纯求和」。

    先剥掉 round(...) / abs(...) 外壳，再看内部是否只有 {var} + {var} 形式。
    """
    import re as _re
    s = str(expr or "").strip()
    if not s:
        return False
    # 剥外层函数
    m = _re.fullmatch(r"(round|abs)\((.+?),\s*\d+\)", s)
    if m:
        s = m.group(2)
    # 内部只允许 {var} 与 + 
    core = _re.sub(r"\{[^}]+\}", "X", s)
    return bool(core) and "+" in core and not _re.search(r"[*/\-]", core)


def _load_graph(graph_path):
    g = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    items = g.get("items") or {}
    return g, items.get("facts") or [], items.get("reasoning") or [], items.get("conflicts") or []


def _rules_map(reasoning):
    """rule_id → {target, expr, deps}"""
    out = {}
    for r in reasoning:
        rid = r.get("rule_id") or r.get("id")
        if not rid:
            continue
        out[str(rid)] = {
            "target": str(r.get("target") or ""),
            "expr": str(r.get("expr") or r.get("formula") or ""),
            "deps": [str(d) for d in (r.get("deps_required") or r.get("deps_labels") or r.get("deps") or [])],
        }
    return out


def _by_subject(facts):
    out = {}
    for f in facts:
        s = str(f.get("subject") or "")
        if s:
            out.setdefault(s, []).append(f)
    return out


def _pick(facts, subject, status=None):
    for f in facts:
        if str(f.get("subject")) != subject:
            continue
        if status and f.get("status") != status:
            continue
        return f
    return None


def check(graph_path, *, rules_from_pack=None) -> dict:
    """对全图做「属性自洽」判定。

    rules_from_pack: 形包的 rules dict（{rule_id: {target, expr, deps_required}}）
                     用来判「形包是否要求该节点是派生」
    """
    g, facts, reasoning, conflicts = _load_graph(graph_path)
    by_sub = _by_subject(facts)
    rules = _rules_map(reasoning)
    pack_rules = rules_from_pack or {}

    # ---------- 建立「节点 → 该不该是派生」 ----------
    # ① 形包规则里作为 target 的
    pack_targets = {}       # subject → [rule_id]
    for rid, rv in pack_rules.items():
        t = str(rv.get("target") or "")
        if t:
            pack_targets.setdefault(t, []).append(rid)
    # ② 图里 reasoning 的 target
    for rid, rv in rules.items():
        t = rv["target"]
        if t:
            pack_targets.setdefault(t, []).append(rid)

    items = []
    for subject in sorted(by_sub):
        rows = by_sub[subject]
        prov = [f for f in rows if f.get("status") == "provided"]
        comp = [f for f in rows if f.get("status") == "computed"]
        rids = pack_targets.get(subject) or []

        should_derive = bool(rids)
        has_customer = bool(prov)
        has_rule_value = bool(comp)

        item = {"subject": subject, "rules": rids,
                "customer_value": _num(prov[0].get("value")) if prov else None,
                "customer_node": prov[0].get("id") if prov else None,
                "rule_value": _num(comp[0].get("value")) if comp else None,
                "rule_node": comp[0].get("id") if comp else None}

        # ---------- 情形 1：形包无 rule，客户有值 → input ----------
        if not should_derive:
            item.update(origin="input", evidence="形包无规则，客户直接给值",
                        conflict=None, action="直接用")
            items.append(item)
            continue

        # ---------- 形包有 rule ----------
        # 取规则的依赖项
        deps = []
        for rid in rids:
            rv = pack_rules.get(rid) or rules.get(rid) or {}
            deps += [str(d) for d in (rv.get("deps_required") or rv.get("deps") or [])]
        deps = list(dict.fromkeys(deps))

        # 过滤伪依赖
        deps = _clean_deps(deps)
        # 收集依赖值
        dep_vals, dep_missing = [], []
        for d in deps:
            f = _pick(facts, d)
            v = _num(f.get("value")) if f else None
            if v is None:
                dep_missing.append(d)
            else:
                dep_vals.append((d, v))
        env = {d: v for d, v in dep_vals}
        children_ready = bool(deps) and not dep_missing

        # ★ 关键：优先用规则表达式真算；只有纯求和才用「子项加总」
        expr = ""
        for rid in rids:
            rv = pack_rules.get(rid) or rules.get(rid) or {}
            if rv.get("expr"):
                expr = str(rv["expr"])
                break
        dep_sum = None
        if children_ready:
            if expr and not _is_pure_sum(expr):
                dep_sum = _eval_rule(expr, env)      # 乘法/除法型 → 真算
            else:
                dep_sum = round(sum(v for _, v in dep_vals), 2)  # 纯求和 → 加总

        item["deps"] = deps
        item["deps_ready"] = children_ready
        item["deps_missing"] = dep_missing
        item["deps_sum"] = dep_sum

        # ---------- 情形 6：子项不齐，无法验证 ----------
        if has_customer and not children_ready:
            item.update(origin="undetermined",
                        evidence="客户给了值，但依赖子项不齐（缺 %s），无法复算" % ("、".join(dep_missing[:3]) or "—"),
                        conflict=None, action="补子项后再判")
            items.append(item)
            continue

        # ---------- 情形 2：客户没给，子项齐 → derived ----------
        if not has_customer:
            item.update(origin="derived",
                        evidence="客户未给，子项齐（%d 项），由规则算出" % len(dep_vals),
                        conflict=None, action="用规则算")
            items.append(item)
            continue

        # ---------- 情形 3/4/5：客户给了，子项齐 → 三方比对 ----------
        cv, rv, ds = item["customer_value"], item["rule_value"], dep_sum
        if ds is None:
            item.update(origin="undetermined", evidence="无子项数据",
                        conflict=None, action="补子项")
            items.append(item)
            continue

        cust_ok = _close(cv, ds)
        rule_ok = _close(rv, ds)

        if cust_ok:
            # 情形 3：客户值自洽 → 属性转化为 input
            item.update(origin="input",
                        evidence="客户值 %s == 子项加总 %s（自洽），属性由派生转为原始输入" % (cv, ds),
                        conflict=None,
                        action="用客户值；规则值 %s 仅作校验" % rv)
        elif rule_ok:
            # 情形 4：规则值自洽 → 保持 derived，客户值记异议
            item.update(origin="derived",
                        evidence="客户值 %s ≠ 子项加总 %s；规则值 %s == 子项加总（%s）"
                                 % (cv, ds, rv, "规则自洽，客户值是对派生结果的异议"),
                        conflict={"customer": cv, "rule": rv, "children_sum": ds,
                                  "delta": round(cv - ds, 2) if cv is not None else None},
                        action="**保持派生**；客户值记为异议，标待审，不裁决")
        else:
            # 情形 5：三方都不自洽
            item.update(origin="derived",
                        evidence="客户值 %s ≠ 子项加总 %s，规则值 %s ≠ 子项加总（三方都不自洽）"
                                 % (cv, ds, rv),
                        conflict={"customer": cv, "rule": rv, "children_sum": ds},
                        action="标待审；数据缺失，需补分项")
        items.append(item)

    # ---------- 汇总 ----------
    from collections import Counter
    cnt = Counter(i["origin"] for i in items)
    conflicts_found = [i for i in items if i.get("conflict")]
    # 客户必须补的：origin=undetermined 或 missing
    to_ask = [i["subject"] for i in items
              if i["origin"] == "undetermined" and not i.get("deps_ready")]
    # 从派生转为原始输入的（属性转化）
    converted = [i for i in items
                 if i["origin"] == "input" and i.get("rules") and i.get("deps_sum") is not None]

    return {
        "counts": dict(cnt),
        "total": len(items),
        "items": items,
        "conflicts": conflicts_found,
        "conflict_count": len(conflicts_found),
        "converted_to_input": converted,
        "converted_count": len(converted),
        "to_ask_customer": sorted(set(to_ask)),
        "to_ask_count": len(set(to_ask)),
    }


def report(result: dict, out_path=None) -> str:
    """生成 markdown 报告。"""
    c = result["counts"]
    L = ["# 节点属性自洽检查（原始输入 vs 派生）", ""]
    L.append("## 总览")
    L.append("")
    L.append("| 属性 | 数量 | 含义 |")
    L.append("|---|---:|---|")
    L.append("| **input** | %d | 原始输入：客户给 / 标准库查 |" % c.get("input", 0))
    L.append("| **derived** | %d | 派生：由规则算出 |" % c.get("derived", 0))
    L.append("| **undetermined** | %d | 待定：依赖子项不全，无法验证 |" % c.get("undetermined", 0))
    L.append("| **合计** | %d | |" % result["total"])
    L.append("")

    if result["converted_count"]:
        L += ["## 属性转化：派生 → 原始输入（%d 个）" % result["converted_count"], ""]
        L.append("客户给的值与子项加总**自洽**，说明客户给的就是对的，规则值仅作校验。")
        L.append("")
        L += ["| 节点 | 客户值 | 子项加总 | 规则值 | 判定 |", "|---|---:|---:|---:|---|"]
        for i in result["converted_to_input"]:
            L.append("| %s | %s | %s | %s | 属性转为 input |"
                     % (i["subject"], i.get("customer_value"), i.get("deps_sum"), i.get("rule_value")))
        L.append("")

    if result["conflict_count"]:
        L += ["## 冲突：派生保持，客户值记异议（%d 个）" % result["conflict_count"], ""]
        L.append("客户给的值与自己给的分项对不上，而规则值对得上 —— **该节点确实是派生，客户是对派生结果有异议**。")
        L.append("")
        L += ["| 节点 | 客户值 | 规则值 | 子项加总 | 差额 | 属性 | 处置 |",
              "|---|---:|---:|---:|---:|---|---|"]
        for i in result["conflicts"]:
            cf = i["conflict"]
            L.append("| %s | %s | %s | %s | %s | **derived** | %s |"
                     % (i["subject"], cf.get("customer"), cf.get("rule"),
                        cf.get("children_sum"), cf.get("delta"), i["action"]))
        L.append("")

    if result["to_ask_count"]:
        L += ["## 待客户补充（%d 项，无法验证属性）" % result["to_ask_count"], ""]
        L.append("这些节点的依赖子项不全，客户给了值也验不了。需先补子项。")
        L.append("")
        for s in result["to_ask_customer"]:
            L.append("- %s" % s)
        L.append("")

    L += ["## 逐节点明细（前 40）", ""]
    L += ["| 节点 | 客户值 | 规则值 | 子项加总 | 属性 | 依据 |",
          "|---|---:|---:|---:|---|---|"]
    for i in result["items"][:40]:
        L.append("| %s | %s | %s | %s | **%s** | %s |"
                 % (i["subject"], i.get("customer_value"), i.get("rule_value"),
                    i.get("deps_sum"), i["origin"], str(i["evidence"])[:50]))
    L.append("")

    txt = "\n".join(L)
    if out_path:
        Path(out_path).write_text(txt, encoding="utf-8")
    return txt
