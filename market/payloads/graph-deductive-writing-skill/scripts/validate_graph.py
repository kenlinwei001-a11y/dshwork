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
    "claims":      ("id", "text", "type", "deps", "evidence"),
    "evidence":    ("id", "name", "date", "kind"),
    "conflicts":   ("id", "type", "severity", "status", "description", "involved"),
    "validations": ("claim", "status", "reason"),
}

# References whose value must point at a known id (dangling refs are errors).
# Each tuple is (field, tuple_of_valid_collections).
ID_REF_FIELDS = {
    "relations":   (("from", ("entities",)), ("to", ("entities",))),
    "reasoning":   (("inputs", ("facts", "reasoning")), ("output", ("facts",))),
    "claims":      (("deps", ("facts", "reasoning", "claims")), ("evidence", ("evidence",))),
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
