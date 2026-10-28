# -*- coding: utf-8 -*-
"""label_enrichment —— 第八道工序：给节点补「新规范标签」（确定性，零 LLM）。

七道工序与轻量路径产出的节点都缺下游要用的标签；本模块用**结构性判据**补齐，
不改任何原字段、不调 LLM。

    role            INPUT / INTERMEDIATE / DERIVED_LEAF
    constraint_type HARD_INPUT / SOFT_INPUT / DERIVED / JUDGMENT / RETRIEVABLE
    source_type     CUSTOMER / CUSTOMER_PRIMARY / COMPUTED / STANDARD / JUDGMENT
    standard_id     依据标准号（带版本年）
    solve_direction SOFT_INPUT 才有：FORWARD / BACKWARD / BOTH

用法：
    from corpus_pipeline.label_enrichment import enrich
    stats = enrich("<目录>")              # 原地写 graph/nodes.yaml
    nodes = enrich("<目录>", dry_run=True)
"""
from __future__ import annotations
import json
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

_JUDGE = ("等级", "类别", "是否", "判定", "符合性")
_COEF = ("率", "系数", "指标")


def _load(p: Path):
    if not p.exists():
        return None
    raw = p.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return yaml.safe_load(raw) if yaml else None


def _dump(p: Path, obj):
    p.write_text(yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, width=200),
                 encoding="utf-8")


def _std_code(s):
    m = re.search(r"((?:GB/T|GB|JGJ/T|JGJ|DGJ\d*|CJJ|CECS|建标)\s*[\d\-—.]*\d\s*[-—]\s*\d{4})",
                  str(s))
    return re.sub(r"\s+", "", m.group(1)).replace("—", "-") if m else None


def enrich(target_dir, *, dry_run=False):
    d = Path(target_dir)
    np_ = d / "graph" / "nodes.yaml"
    nodes = _load(np_) or []
    rules = _load(d / "graph" / "rules.yaml") or []
    rels = _load(d / "graph" / "relations.yaml") or []
    if not isinstance(nodes, list) or not nodes:
        return {"error": "no nodes", "dir": str(d)}

    as_dep, as_target = set(), set()
    for r in (rules if isinstance(rules, list) else []):
        if str(r.get("kind")) not in ("compute", "select", "condition"):
            continue
        for x in (r.get("deps") or []):
            as_dep.add(str(x))
        t = r.get("target_label") or r.get("target") or r.get("label")
        if t:
            as_target.add(str(t))

    std_of, range_known = {}, {}
    for r in (rels if isinstance(rels, list) else []):
        if str(r.get("type")) != "bounded_by":
            continue
        subj = r.get("subject")
        if not subj and isinstance(r.get("to"), str):
            subj = r.get("to")
        pl = r.get("payload") or {}
        src = r.get("source") or {}
        code = pl.get("standard_id") or _std_code(src.get("standard") or pl.get("clause") or "")
        if subj and code:
            std_of[str(subj)] = code
            range_known[str(subj)] = bool(pl.get("range_known"))

    by_role, by_constraint, by_source = {}, {}, {}
    for n in nodes:
        lab = str(n.get("subject") or n.get("label") or "")
        if not lab:
            continue
        if lab in as_target and lab in as_dep:
            role = "INTERMEDIATE"
        elif lab in as_target:
            role = "DERIVED_LEAF"
        else:
            role = "INPUT"
        if role == "INTERMEDIATE":
            ctype = "SOFT_INPUT"
        elif role == "DERIVED_LEAF":
            ctype = "DERIVED"
        elif lab in std_of and not range_known.get(lab, True):
            ctype = "RETRIEVABLE"
        elif any(k in lab for k in _JUDGE):
            ctype = "JUDGMENT"
        else:
            ctype = "HARD_INPUT"
        stype = {"HARD_INPUT": "CUSTOMER", "SOFT_INPUT": "CUSTOMER_PRIMARY",
                 "DERIVED": "COMPUTED", "JUDGMENT": "JUDGMENT",
                 "RETRIEVABLE": "STANDARD"}[ctype]
        if ctype == "SOFT_INPUT":
            n["solve_direction"] = "BOTH"
            n["direction_note"] = "双向：客户可直给，也可由分项加总校验"
        n["role"] = role
        n["constraint_type"] = ctype
        n["source_type"] = stype
        if lab in std_of:
            n["standard_id"] = std_of[lab]
            n["range_known"] = range_known.get(lab, False)
        by_role[role] = by_role.get(role, 0) + 1
        by_constraint[ctype] = by_constraint.get(ctype, 0) + 1
        by_source[stype] = by_source.get(stype, 0) + 1

    if not dry_run:
        _dump(np_, nodes)
    return {"dir": str(d), "labeled": len(nodes),
            "by_role": by_role, "by_constraint": by_constraint, "by_source": by_source,
            "with_standard": len(std_of), "dry_run": dry_run}
