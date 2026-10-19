# -*- coding: utf-8 -*-
"""kp_toolkit.derivation —— 推演链（确定性，零 LLM）

把 rules.yaml 的设计变量绑定到实际节点，生成 computed_from 关系，并执行验证。

对外三个函数：
    bind_and_emit(nodes, rules, relations) -> (bindings, relations2, report)
    verify(bindings, nodes)               -> report
    safe_eval(expr)                       -> float

核心约定：
    输出值 --computed_from--> 输入值     payload{rule_id, expr, dep_var, dep_value}
"""
import re
from collections import Counter

STRICT_UNIT = [("人数", "人"), ("系数", "%"), ("天数", "d"), ("小时", "h")]


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def safe_eval(expr):
    """只允许数字与 + - * / ( ) round 的表达式求值"""
    if not re.fullmatch(r"[\d\.\+\-\*/\(\),\s round]*", expr):
        raise ValueError("表达式含非白名单字符")
    return eval(expr, {"__builtins__": {}}, {"round": round})


def _bind(nodes_num, dep, rules, rule):
    d = str(dep).strip()
    # ① 精确
    for n in nodes_num:
        if str(n.get("subject") or "").strip() == d:
            return n, "精确匹配"
    # ② 主体包含 + 单位精确
    for kw, u in STRICT_UNIT:
        if kw not in d:
            continue
        cand = [n for n in nodes_num
                if str(n.get("subject") or "").strip() in d
                and str(n.get("unit") or "").strip() == u]
        if len(cand) == 1:
            return cand[0], f"主体包含+{kw}单位精确"
        if len(cand) > 1:
            cand.sort(key=lambda x: -len(str(x.get("subject"))))
            return cand[0], f"主体包含+{kw}精确（多候选取最长）"
    # 定额：单位以 L/ 开头
    if "定额" in d:
        cand = [n for n in nodes_num
                if str(n.get("subject") or "").strip() in d
                and str(n.get("unit") or "").strip().startswith("L/")]
        if cand:
            cand.sort(key=lambda x: -len(str(x.get("subject"))))
            return cand[0], "主体包含+定额单位精确"
    # ③ 无名依赖（系数/天数）：按 target 章节 + 单位
    if ("系数" in d) or ("天数" in d):
        u = "%" if "系数" in d else "d"
        cand = [n for n in nodes_num if str(n.get("unit") or "").strip() == u]
        if cand:
            sec = None
            tgt = str(rule.get("target") or "")
            for n in nodes_num:
                if tgt and str(n.get("subject")).strip() == tgt:
                    sec = n.get("section"); break
            if not sec:
                # target 不在节点表 → 用本规则其他依赖「按主体包含」命中的章节（多数票）
                # 注意：这里不能递归调 _bind（会死循环），用简化匹配
                votes = Counter()
                for dep2 in (rule.get("deps") or []):
                    d2 = str(dep2).strip()
                    if d2 == d: continue
                    for n2 in nodes_num:
                        st2 = str(n2.get("subject") or "").strip()
                        if st2 and len(st2) >= 2 and st2 in d2 and n2.get("section"):
                            votes[n2["section"]] += 1
                            break
                if votes:
                    sec = votes.most_common(1)[0][0]
            same = [n for n in cand if str(n.get("section")) == sec]
            return (same or cand)[0], f"按单位+章节推断（{u}）"
    # ④ 主体包含（不校验单位，唯一候选才用）
    hit = [n for n in nodes_num if str(n.get("subject") or "").strip() and
           str(n.get("subject")).strip() in d]
    if len(hit) == 1:
        return hit[0], "主体包含（未校验单位）"
    return None, None


def bind_and_emit(nodes, rules, relations):
    """返回 (bindings, relations2, report)"""
    nodes_num = [n for n in nodes if _num(n.get("value")) is not None]
    bindings, stat = {}, Counter()
    for r in rules:
        binds = {}
        for dep in (r.get("deps") or []):
            n, how = _bind(nodes_num, dep, rules, r)
            if n:
                binds[str(dep)] = {"node": n["id"], "value": n.get("value"),
                                   "unit": n.get("unit") or "", "section": n.get("section") or "", "how": how}
                stat[how] += 1
            else:
                binds[str(dep)] = {"node": None, "how": "未绑定"}
                stat["未绑定"] += 1
        bindings[r["id"]] = {"target": r.get("target"), "kind": r.get("kind"), "expr": r.get("expr"),
                             "guard": r.get("guard"), "section": r.get("section"), "deps": binds,
                             "complete": all(v["node"] for v in binds.values())}

    def target_node(t, v):
        for n in nodes_num:
            if str(n.get("subject")).strip() == str(t).strip():
                return n
        e = v.get("expr") or ""
        for dep, b in (v.get("deps") or {}).items():
            x = _num(b.get("value"))
            if x is None: return None
            e = e.replace("{" + dep + "}", repr(x))
        try: got = safe_eval(e)
        except Exception: return None
        sec = next((b["section"] for b in (v.get("deps") or {}).values() if b.get("section")), None)
        cand = [n for n in nodes_num if abs(_num(n.get("value")) - got) <= max(0.02, abs(got) * 0.005)]
        same = [n for n in cand if str(n.get("section")) == sec]
        return (same or cand or [None])[0]

    exist = {(r.get("from"), r.get("type"), r.get("to")) for r in relations}
    added = []
    for rid, v in bindings.items():
        if not v["complete"]: continue
        out = target_node(v.get("target"), v)
        if not out: continue
        for dep, b in v["deps"].items():
            src = b["node"]
            if not src or src == out["id"]: continue
            key = (out["id"], "computed_from", src)
            if key in exist: continue
            exist.add(key)
            added.append({"from": out["id"], "to": src, "type": "computed_from", "family": "依据",
                          "payload": {"rule_id": rid, "expr": v.get("expr"), "dep_var": dep,
                                      "dep_value": b.get("value"), "dep_unit": b.get("unit"),
                                      "output_value": out.get("value"), "output_unit": out.get("unit")},
                          "operator": rid})
    rep = {"rules": len(bindings), "fully_bound": sum(1 for v in bindings.values() if v["complete"]),
           "deps_bound": dict(stat), "new_relations": len(added), "total_relations": len(relations) + len(added),
           "by_rule": dict(Counter(a["operator"] for a in added))}
    return bindings, relations + added, rep


def verify(bindings, nodes):
    """执行推演链并与原文值比对"""
    def find(t):
        for n in nodes:
            if str(n.get("subject")).strip() == str(t).strip() and _num(n.get("value")) is not None:
                return n
        return None
    rows = []
    for rid, v in bindings.items():
        if not v.get("expr"): continue
        vals = {}
        miss = []
        for dep, b in (v.get("deps") or {}).items():
            x = _num(b.get("value")) if b.get("node") else None
            if x is None: miss.append(dep)
            else: vals[dep] = x
        if miss:
            rows.append({"rule": rid, "target": v.get("target"), "status": "依赖缺失", "missing": miss}); continue
        e = v["expr"]
        for k, x in vals.items(): e = e.replace("{" + k + "}", repr(x))
        try: got = safe_eval(e)
        except Exception as ex:
            rows.append({"rule": rid, "target": v.get("target"), "status": "表达式错误", "err": str(ex)[:60]}); continue
        tn = find(v.get("target"))
        if tn and _num(tn["value"]) is not None:
            ok = abs(got - _num(tn["value"])) <= max(0.02, abs(_num(tn["value"])) * 0.005)
            rows.append({"rule": rid, "target": v.get("target"), "status": "对上" if ok else "不符",
                         "calc": round(got, 2), "orig": _num(tn["value"]), "unit": tn.get("unit") or ""})
        else:
            # target 名称对不上 → 按值在同章节找（对上就算通过）
            numn = [n for n in nodes if _num(n.get("value")) is not None]
            cand = [n for n in numn if abs(_num(n.get("value")) - got) <= max(0.02, abs(got) * 0.005)]
            sec = next((b.get("section") for b in (v.get("deps") or {}).values() if b.get("section")), None)
            same = [n for n in cand if str(n.get("section")) == sec]
            pick = same or cand
            if pick:
                n0 = pick[0]
                rows.append({"rule": rid, "target": v.get("target"), "status": "对上（按值匹配）",
                             "calc": round(got, 2), "orig": _num(n0.get("value")),
                             "unit": n0.get("unit") or "", "node": n0["id"]})
            else:
                rows.append({"rule": rid, "target": v.get("target"), "status": "原文无此值", "calc": round(got, 2)})
    c = Counter(r["status"] for r in rows)
    return {"summary": dict(c), "rows": rows}
