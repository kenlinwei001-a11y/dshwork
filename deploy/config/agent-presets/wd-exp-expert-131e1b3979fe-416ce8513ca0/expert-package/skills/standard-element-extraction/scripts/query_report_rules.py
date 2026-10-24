#!/usr/bin/env python3
"""Show all rules of a report, across every linked standard."""
import argparse
import sqlite3

parser = argparse.ArgumentParser()
parser.add_argument("--db", required=True)
parser.add_argument("--report", required=True)
args = parser.parse_args()
db = sqlite3.connect(args.db)
db.row_factory = sqlite3.Row

report = db.execute("SELECT * FROM report WHERE report_id = ?", (args.report,)).fetchone()
if not report:
    print("report not found:", args.report)
    db.close()
    raise SystemExit(2)
print("REPORT", dict(report))
links = db.execute("SELECT * FROM report_standard WHERE report_id = ? ORDER BY standard_id", (args.report,)).fetchall()
print("STANDARDS", [dict(x) for x in links])
for link in links:
    sid = link["standard_id"]
    rows = db.execute("SELECT rule_id, category, clause, requirement, on_missing FROM rule WHERE standard_id = ? ORDER BY category, rule_id", (sid,)).fetchall()
    print("--", sid, "rules", len(rows))
    for r in rows:
        print(dict(r))
db.close()
