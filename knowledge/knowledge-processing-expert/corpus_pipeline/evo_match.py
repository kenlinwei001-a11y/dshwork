# -*- coding: utf-8 -*-
"""evo_match —— 形变量 ⇄ 新项目值的三层匹配 + 待确认清单（零 LLM）。

## 为什么要三层

新项目的用词和「形」不同是常态：
    形：总投资           新项目：项目总投资 / 投资总额 / 投资规模
    形：本项目建筑面积     新项目：总建筑面积 / 建筑规模

**字面精确匹配只能对上 60~70%**。剩下要靠别名和语义相似。

## 三层（逐层降级，每层标注 match_method）

    ① exact    字面完全相同
    ② alias    命中 fact-aliases.yaml 的 148 组别名
    ③ similar  字符集重叠 + 编辑距离 >= 阈值
    ④ unmatched 三层都不中 → **不猜，进待确认清单给用户决策**

## 两个待确认清单（用户决策用）

    A. 形有位置但无值   → 新项目的哪条数据能填它？
       （列出候选：相似度 top3）
    B. 新项目有数据但没被用 → 它可能填到形的哪个位置？
       （列出候选）
"""
from __future__ import annotations
import re
from difflib import SequenceMatcher
from pathlib import Path

import yaml

SIM_THRESHOLD = 0.62      # 相似度阈值（低于此不采纳）

# 维度词：出现不同维度词的两个名称**不是同一个东西**（如「费率」vs「费用」）
DIMENSION_WORDS = (
    ("费率", "率", "%"), ("费用", "费", "金额", "额"), ("数量", "数", "台数"),
    ("面积", "㎡", "平方米"), ("人数", "人数"), ("单价", "元/"),
    ("指标",), ("系数",), ("比例", "占比"),
)


def _dimension_of(s: str):
    """返回该名称命中的维度词集合。"""
    s = str(s or "")
    hits = set()
    for group in DIMENSION_WORDS:
        for w in group:
            if w in s:
                hits.add(group[0])   # 用组首作维度标识
                break
    return hits


def load_aliases(pkg) -> dict:
    """canonical → [别名...]，并自动生成「子系统N」↔「{子系统N}」别名。"""
    d = yaml.safe_load((Path(pkg)/"ontology"/"fact-aliases.yaml").read_text(encoding="utf-8"))
    al = d.get("aliases") or {}
    out = {}
    for k, v in al.items():
        out[str(k)] = [str(x) for x in (v or [])] + [str(k)]
    # org_substitution：源语料包的分中心名是项目专属；新项目用 {子系统N}
    org = d.get("org_substitution") or {}
    for i, src_name in enumerate(org.get("source_names") or [], 1):
        key = "%s·%%s" % src_name
        # 「子系统N·规划科研人员」的别名含「{子系统N}」
        for suffix in ("规划科研人员", "规划研究生博士生访问学者",
                       "规划人数", "科研人员", "研究生"):
            canon = "%s·%s" % ("{子系统%d}" % i, suffix)
            out.setdefault(canon, [])
            for a in ("{%s%d}" % ("子系统", i), "{%s%d}%s" % ("子系统", i, suffix)):
                if a not in out[canon]:
                    out[canon].append(a)
    return out


def _norm(s: str) -> str:
    """归一化：去中文括号内容、去空格/标点、去 {} 符号但保留内容。"""
    s = str(s or "")
    s = re.sub(r"[（(].*?[）)]", "", s)
    s = re.sub(r"[\s·、，,。：:；;/／]", "", s)
    s = s.replace("{", "").replace("}", "")
    return s.strip()


def _sim(a: str, b: str) -> float:
    """相似度：字符集重叠 0.5 + 序列相似 0.5。"""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    set_a, set_b = set(na), set(nb)
    jac = len(set_a & set_b) / max(len(set_a | set_b), 1)
    seq = SequenceMatcher(None, na, nb).ratio()
    return 0.5 * jac + 0.5 * seq


def match_var(var: str, facts: dict, aliases: dict) -> tuple:
    """返回 (fact|None, method, score)。"""
    v = str(var or "").strip()
    if not v:
        return None, "empty", 0.0

    # ① 精确 —— **有值才算**；无值则继续找有值的同义项
    if v in facts and facts[v].get("value") is not None:
        return facts[v], "exact", 1.0
    exact_novalue = facts.get(v)

    # ② 别名（含归一化相等）
    nv0 = _norm(v)
    for canonical, alist in aliases.items():
        group = set(alist) | {canonical}
        if v in group or any(_norm(x) == nv0 for x in group):
            # 该组的 canonical 或任一别名在 facts 里
            for cand in [canonical] + list(group):
                if cand in facts and facts[cand].get("value") is not None:
                    return facts[cand], "alias", 0.95
            # facts 里有无归一化后相同的
            nv = _norm(v)
            for s, f in facts.items():
                if _norm(s) in {_norm(x) for x in group}:
                    return f, "alias", 0.95

    # ③ 相似（要求：维度一致 + 有值）
    v_dim = _dimension_of(v)
    best, bestsc = None, 0.0
    for s, f in facts.items():
        # 维度冲突 → 跳过（「费率」不匹配「费用」）
        s_dim = _dimension_of(s)
        if v_dim and s_dim and v_dim != s_dim:
            continue
        sc = _sim(v, s)
        if f.get("value") is None:
            sc *= 0.75          # 无值的候选降权（优先有值的）
        if sc > bestsc:
            bestsc, best = sc, f
    if bestsc >= SIM_THRESHOLD:
        return best, "similar", round(bestsc, 3)

    if exact_novalue is not None:
        return exact_novalue, "exact_no_value", 1.0
    return None, "unmatched", round(bestsc, 3)


def pending_lists(vars_needed: list, facts: dict, aliases: dict) -> dict:
    """生成两个待确认清单。

    vars_needed: [(变量名, 来自哪条规则)] —— 形需要但可能没匹配上的
    """
    matched_ids = set()
    unmatched_vars = []
    for v, src in vars_needed:
        f, m, sc = match_var(v, facts, aliases)
        if f and f.get("value") is not None:
            matched_ids.add(str(f.get("id")))
        else:
            # 找候选：facts 里最像的 3 个
            cands = sorted(((_sim(v, s), s, f) for s, f in facts.items()),
                           key=lambda x: -x[0])[:3]
            unmatched_vars.append({
                "var": v, "from_rule": src, "best_score": sc,
                "candidates": [{"subject": s, "value": f.get("value"),
                                "unit": f.get("unit") or "",
                                "id": f.get("id"), "score": round(sc2, 3)}
                               for sc2, s, f in cands if sc2 >= 0.35],
            })

    unused = [{"subject": s, "value": f.get("value"), "unit": f.get("unit") or "",
               "id": f.get("id")}
              for s, f in facts.items() if str(f.get("id")) not in matched_ids]
    return {"unmatched_vars": unmatched_vars, "unused_facts": unused,
            "unmatched_count": len(unmatched_vars), "unused_count": len(unused)}
