#!/usr/bin/env python3
"""Load one standard SES package into the standards database.

Usage:
  python3 load_standard.py --db ../standards.db --ses ../ses/HJ671-2013.ses.json
"""
import argparse
import json
import pathlib
import sqlite3


def dump(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--ses", required=True)
    parser.add_argument("--schema", default=None)
    args = parser.parse_args()

    ses_path = pathlib.Path(args.ses).resolve()
    with ses_path.open("r", encoding="utf-8") as fh:
        ses = json.load(fh)

    schema_path = pathlib.Path(args.schema) if args.schema else pathlib.Path(__file__).resolve().parent.parent / "schema.sqlite.sql"
    db = sqlite3.connect(args.db)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(schema_path.read_text(encoding="utf-8"))

    sid = ses["standard_id"]
    status = ses.get("status") or {}
    fingerprint = ses.get("source_fingerprint") or {}
    rule_sets = ses.get("rule_sets") or []

    for rs in rule_sets:
        db.execute("DELETE FROM rule_set_member WHERE rule_set_id = ?", (rs["rule_set_id"],))
    for table in ["edge", "node", "element", "rule", "doc_field",
                  "reference_doc", "gap", "method", "graph_view", "clause", "rule_set"]:
        db.execute("DELETE FROM " + table + " WHERE standard_id = ?", (sid,))
    db.execute("DELETE FROM standard_package WHERE standard_id = ?", (sid,))
    db.execute("DELETE FROM standard WHERE standard_id = ?", (sid,))

    db.execute(
        "INSERT INTO standard (standard_id, title, published, effective, superseded_by, status, sha256_12, pages, contract_version, source_json_path, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (sid, ses.get("title"), status.get("published"), status.get("effective"), status.get("superseded_by"),
         "IMPORTED", fingerprint.get("sha256_12"), fingerprint.get("pages"), ses.get("schema_version"), str(ses_path)),
    )

    graph = {
        "nodes": ses.get("nodes", []),
        "edges": ses.get("edges", []),
        "views": ses.get("views", []),
        "stats": ses.get("stats", {}),
    }
    db.execute(
        "INSERT INTO standard_package (standard_id, ses_json, graph_json, stats_json) VALUES (?, ?, ?, ?)",
        (sid, dump(ses), dump(graph), dump(ses.get("stats"))),
    )

    for c in ses.get("clauses", []):
        db.execute(
            "INSERT INTO clause (standard_id, clause, title, page, printed_page, clause_type, obligation, section_heading, quote, quote_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, c.get("clause"), c.get("title"), c.get("page"), c.get("printed_page"), c.get("clause_type"),
             c.get("obligation"), 1 if c.get("section_heading") else 0, c.get("quote"), c.get("quote_status")),
        )

    for n in ses.get("nodes", []):
        db.execute(
            "INSERT INTO node (standard_id, node_id, node_type, label, clause, page, attrs_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, n["id"], n["type"], n.get("label") or n.get("title") or n.get("standard"), n.get("clause"),
             n.get("page"), dump(n)),
        )

    for e in ses.get("edges", []):
        db.execute(
            "INSERT INTO edge (standard_id, edge_id, from_id, to_id, operator, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (sid, e["id"], e["from"], e["to"], e["operator"], dump(e)),
        )

    for e in ses.get("elements", []):
        db.execute(
            "INSERT INTO element (standard_id, element_id, family, clause, statement, params_json, obligation, source_layer, origin, anchor_page, anchor_quote, detail_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, e["element_id"], e.get("family"), e.get("clause"), e.get("statement"), dump(e.get("params")),
             e.get("obligation"), e.get("source_layer"), e.get("origin"), e.get("anchor_page"), e.get("anchor_quote"),
             e.get("detail_status")),
        )

    for r in ses.get("rules", []):
        db.execute(
            "INSERT INTO rule (standard_id, rule_id, category, clause, title, requirement, predicate_json, applicability, evidence_json, check_target_json, check_target_text, on_missing, on_fail, source_layer, anchor_page, anchor_quote, anchor_level, locator_hint, detail_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, r["rule_id"], r["category"], r.get("clause"), r.get("title"), r.get("requirement"),
             dump(r.get("predicate")), r.get("applicability"), dump(r.get("evidence_required")),
             dump(r.get("check_target")), r.get("check_target_text"), r.get("on_missing"), r.get("on_fail"),
             r.get("source_layer"), r.get("anchor_page"), r.get("anchor_quote"), r.get("anchor_level"),
             r.get("locator_hint"), r.get("detail_status")),
        )

    for d in ses.get("doc_fields", []):
        db.execute(
            "INSERT INTO doc_field (standard_id, doc_field_id, doc_type, field, target_type, locator_json) VALUES (?, ?, ?, ?, ?, ?)",
            (sid, d["doc_field_id"], d.get("doc_type"), d.get("field"), d.get("target_type"), dump(d.get("locator"))),
        )

    for ref in ses.get("references", []):
        db.execute(
            "INSERT INTO reference_doc (standard_id, ref_id, standard_no, title, status, referenced_by_json, scope, affected_rules_json, depth) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, ref["ref_id"], ref.get("standard_no"), ref.get("title"), ref.get("status"),
             dump(ref.get("referenced_by")), ref.get("scope"), dump(ref.get("affected_rules")), ref.get("depth", 1)),
        )

    for g in ses.get("gaps", []):
        db.execute(
            "INSERT INTO gap (standard_id, gap_id, gap_type, description, clause, rule_id, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, g["gap_id"], g.get("gap_type"), g.get("description"), g.get("clause"), g.get("rule_id"), g.get("status", "OPEN")),
        )

    for m in ses.get("methods", []):
        db.execute(
            "INSERT INTO method (standard_id, method_id, standard_no, method_name, status, rule_set_id, analyte, dl, range_text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, m["method_id"], m.get("standard_no"), m.get("method_name"), m.get("status"),
             m.get("rule_set_id"), m.get("analyte"), m.get("dl"), m.get("range_text")),
        )

    for rs in rule_sets:
        db.execute("INSERT INTO rule_set (rule_set_id, standard_id, name) VALUES (?, ?, ?)",
                   (rs["rule_set_id"], sid, rs.get("name")))
        members = [x["from"] for x in ses.get("edges", []) if x.get("operator") == "contains" and x.get("from") == rs["rule_set_id"]]
        if not members:
            members = [r["rule_id"] for r in ses.get("rules", [])]
        for rule_id in members:
            db.execute("INSERT OR IGNORE INTO rule_set_member (rule_set_id, rule_id) VALUES (?, ?)",
                       (rs["rule_set_id"], rule_id))

    for v in ses.get("views", []):
        db.execute(
            "INSERT INTO graph_view (standard_id, view_id, title, node_ids_json) VALUES (?, ?, ?, ?)",
            (sid, v["view_id"], v.get("title"), dump(v.get("node_ids"))),
        )

    db.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('contract_version', ?)", (ses.get("schema_version"),))
    db.commit()

    counts = {}
    for table, key in [("clause", "clauses"), ("node", "nodes"), ("edge", "edges"), ("element", "elements"),
                       ("rule", "rules"), ("doc_field", "doc_fields"), ("reference_doc", "references"),
                       ("gap", "gaps"), ("method", "methods"), ("graph_view", "views")]:
        counts[key] = db.execute("SELECT COUNT(*) FROM " + table + " WHERE standard_id = ?", (sid,)).fetchone()[0]
    db.close()
    print("loaded", sid, json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
