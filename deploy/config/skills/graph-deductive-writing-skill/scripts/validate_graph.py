#!/usr/bin/env python3
"""Validate a semantic-graph JSON against the graph-deductive-writing-skill contract.

The graph must be the compiled output of semantic-graph-compilation-skill, i.e. a
JSON object with `items` containing the eight node collections:

    entities, relations, facts, reasoning, claims, evidence, conflicts, validations

Usage:
    python3 validate_graph.py <graph.json> [--strict]

Exit codes:
    0  OK — no structural errors and no dangling references
    1  structural errors (missing required keys, wrong container types)
    2  dangling references (unknown ids referenced) — reported as warnings,
       upgraded to an error under --strict

This script uses only the Python standard library and never mutates the input.
"""
import json
import re
import sys
import argparse

ITEM_TYPES = (
    "entities", "relations", "facts", "reasoning",
    "claims", "evidence", "conflicts", "validations",
)

# Required keys per node collection. `value`/`section`/`unit` are intentionally
# lenient (values may be numbers or strings such as "2 / 4" or "2026-08-18 / 36h").
REQUIRED_KEYS = {
    "entities":    ("id", "name", "type", "source"),
    "relations":   ("id", "from", "to", "type", "source"),
    "facts":       ("id", "subject", "predicate", "value", "source"),
    "reasoning":   ("id", "formula", "result", "desc", "inputs", "output", "section"),
    "claims":      ("id", "text"),   # claim_type / falsifiable_by 由 NEW_CHECKS 单独处理
    "evidence":    ("id", "name", "date", "kind"),
    "conflicts":   ("id", "type", "severity", "status", "description", "involved"),
    "validations": ("claim", "status", "reason"),
}

# References whose value must point at a known id (dangling refs are errors).
# Each tuple is (field, tuple_of_valid_collections).
ID_REF_FIELDS = {
    "relations":   (("from", ("entities", "claims", "evidence", "facts", "reasoning")),
                    ("to",   ("entities", "claims", "evidence", "facts", "reasoning"))),
    "reasoning":   (("inputs", ("facts", "reasoning")), ("output", ("facts",))),
    "claims":      (("deps", ("facts", "reasoning", "claims")),
                    ("evidence_refs", ("evidence",)),
                    ("evidence", ("evidence",)),      # 旧字段别名，向后兼容
                    ("premise_refs", ("claims",)),
                    ("derived_from", ("claims",))),
    "conflicts":   (("involved", ("facts", "reasoning", "claims")),),
    "validations": (("claim", ("claims",)),),
}

# Identity key per collection. Most use `id`; `validations` nodes are keyed by
# `claim` (the id of the claim being validated) and have no `id` field.
ID_KEY = {"validations": "claim"}

EVIDENCE_ID_RE = re.compile(r"^E\d+$")


def load_graph(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _check_ref(ref, owner, col, field, target_cols, id_sets, errors):
    """Check a single reference id (str). Appends to errors on failure."""
    if not isinstance(ref, str):
        errors.append(f"{col} '{owner}'.{field} contains non-string reference {ref!r}")
        return
    if any(ref in id_sets[t] for t in target_cols):
        return
    errors.append(f"{col} '{owner}'.{field} references unknown id '{ref}'")


CLAIM_TYPES = ("conclusion", "recommendation", "hypothesis", "inference")
# fact 是合法的「事实级证据」（一条 fact 自带原文摘录时即为其证据）
EVIDENCE_KINDS = ("E0", "E1", "E2", "E3", "E4", "E5", "E6", "hypothesis", "fact")
# 与 Semantica context_graph._CAUSAL_TRAVERSAL_TYPES 保持一致
# 实际匹配逻辑：edge.edge_type.upper() in 这个集合（大小写不敏感）
CAUSAL_EDGE_TYPES = frozenset({
    "CAUSES", "CAUSED", "INFLUENCES", "INFLUENCED",
    "PRECEDES", "PRECEDENT_FOR", "LEADS_TO", "LEAD_TO",
    "SUPPORTS", "SUPPORT",
})


def check_v28_semantics(items):
    """V2.8 新增语义校验。返回 (errors, warnings)。

    · claim_type 必须在四类枚举内（错 → error）
    · falsifiable_by 缺失 → warning（视为口号，不阻断）
    · evidence.kind 必须在 E0~E6/hypothesis 内（错 → error）
    · 因果边类型必须命中枚举，小写 causes 会静默失效（错 → error）
    · bounded_by.range_known=false 且未标「部分可核」→ warning（写作时禁止说符合）
    """
    errs, warns = [], []
    for c in items.get("claims") or []:
        ct = c.get("claim_type")
        if ct and ct not in CLAIM_TYPES:
            errs.append("claims[%s].claim_type=%r 不在 %s 内" % (c.get("id"), ct, CLAIM_TYPES))
        if not c.get("falsifiable_by"):
            warns.append("claims[%s] 缺 falsifiable_by → 视为口号，写作时不应用" % c.get("id"))
    for e in items.get("evidence") or []:
        k = str(e.get("kind") or "")
        if k and k not in EVIDENCE_KINDS:
            errs.append("evidence[%s].kind=%r 不在 %s 内" % (e.get("id"), k, EVIDENCE_KINDS))
    for r in items.get("relations") or []:
        t = str(r.get("type") or "")
        # Semantica 内部是 edge.edge_type.upper() in _CAUSAL_TRAVERSAL_TYPES
        # → 大小写不敏感，小写 causes/supports 同样有效。只有不在枚举内才失效。
        if t and t.upper() not in CAUSAL_EDGE_TYPES and t.upper() in (
                "CAUSE", "CAUSES", "CAUSED", "INFLUENCE", "INFLUENCES", "INFLUENCED",
                "PRECEDE", "PRECEDES", "PRECEDENT_FOR", "LEAD_TO", "LEADS_TO",
                "SUPPORT", "SUPPORTS"):
            errs.append("relations[%s].type=%r 在因果语义族内但不在 Semantica 枚举"
                        "→ 因果链遍历会失效" % (r.get("id"), t))
        p = r.get("payload") or {}
        if r.get("type") == "bounded_by" and p.get("range_known") is False:
            if p.get("status") != "部分可核":
                warns.append("relations[%s] range_known=false 且未标「部分可核」"
                             "→ 写作时禁止说「符合」" % r.get("id"))
    return errs, warns


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", help="path to the semantic-graph JSON")
    parser.add_argument("--strict", action="store_true",
                        help="treat dangling references as errors (exit 1)")
    args = parser.parse_args(argv)

    try:
        data = load_graph(args.graph)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ERROR] cannot load graph: {exc}", file=sys.stderr)
        return 1

    errors, warnings = [], []

    # --- top-level contract -------------------------------------------------
    if not isinstance(data, dict):
        print("[ERROR] root must be a JSON object", file=sys.stderr)
        return 1
    for key in ("project_id", "version_id", "items"):
        if key not in data:
            errors.append(f"root is missing key '{key}'")
    items = data.get("items")
    if not isinstance(items, dict):
        print("[ERROR] 'items' must be an object", file=sys.stderr)
        return 1

    # --- per-collection structural checks -----------------------------------
    id_sets = {}
    for col in ITEM_TYPES:
        nodes = items.get(col)
        if nodes is None:
            errors.append(f"items is missing collection '{col}'")
            id_sets[col] = set()
            continue
        if not isinstance(nodes, list):
            errors.append(f"items.{col} must be a list, got {type(nodes).__name__}")
            id_sets[col] = set()
            continue
        seen = set()
        for i, node in enumerate(nodes):
            if not isinstance(node, dict):
                errors.append(f"{col}[{i}] is not an object")
                continue
            missing = [k for k in REQUIRED_KEYS[col] if k not in node]
            if missing:
                errors.append(f"{col}[{i}] missing keys: {missing}")
            id_key = ID_KEY.get(col, "id")
            nid = node.get(id_key)
            if nid in seen:
                errors.append(f"duplicate id '{nid}' in {col}")
            seen.add(nid)
        id_sets[col] = seen

    # --- dangling-reference checks -------------------------------------------
    for col, refs in ID_REF_FIELDS.items():
        for node in items.get(col, []):
            if not isinstance(node, dict):
                continue
            nid = node.get("id", "?")
            for field, target_cols in refs:
                if field not in node:
                    continue
                value = node[field]
                if value is None:
                    continue  # reasoning.output may be null
                if isinstance(value, list):
                    for ref in value:
                        _check_ref(ref, nid, col, field, target_cols, id_sets, errors)
                else:
                    _check_ref(value, nid, col, field, target_cols, id_sets, errors)

    # --- facts' `source` may be an evidence id (E*) or a section marker (§) --
    for node in items.get("facts", []):
        src = node.get("source", "")
        if isinstance(src, str) and EVIDENCE_ID_RE.match(src) and src not in id_sets["evidence"]:
            warnings.append(f"fact '{node.get('id')}' source '{src}' is not in evidence")

    # --- report ---------------------------------------------------------------
    print(f"graph: {data.get('project_id')} @ {data.get('version_id')}")
    for col in ITEM_TYPES:
        print(f"  {col:<12} {len(items.get(col, []))}")

    # V2.8 语义校验（必须在打印之前，否则结果不生效）
    _e28, _w28 = check_v28_semantics(items)
    errors.extend(_e28)
    warnings.extend(_w28)

    for w in warnings:
        print(f"[WARN] {w}")
    for e in errors:
        print(f"[ERROR] {e}")

    if errors:
        print(f"\nresult: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    if warnings and args.strict:
        print(f"\nresult: {len(warnings)} warning(s) upgraded to errors under --strict")
        return 1
    print(f"\nresult: OK ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
