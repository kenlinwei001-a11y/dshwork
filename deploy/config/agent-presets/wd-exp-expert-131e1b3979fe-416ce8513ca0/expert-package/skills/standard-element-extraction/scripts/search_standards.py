# -*- coding: utf-8 -*-
import argparse, sqlite3
ap = argparse.ArgumentParser()
ap.add_argument("--db", required=True)
ap.add_argument("--keyword", default="")
ap.add_argument("--list", action="store_true")
args = ap.parse_args()
db = sqlite3.connect(args.db)
db.row_factory = sqlite3.Row
base = """SELECT s.standard_id AS sid, s.title AS title,
 (SELECT COUNT(*) FROM rule r WHERE r.standard_id=s.standard_id) AS rules,
 (SELECT group_concat(m.method_name, '; ') FROM method m WHERE m.standard_id=s.standard_id) AS methods,
 d.file_name AS file_name, d.file_path AS file_path
 FROM standard s LEFT JOIN standard_db d ON d.standard_id=s.standard_id"""
if args.keyword and not args.list:
    like = "%" + args.keyword + "%"
    rows = db.execute(base + """ WHERE s.standard_id LIKE ? OR s.title LIKE ?
      OR EXISTS (SELECT 1 FROM method m WHERE m.standard_id=s.standard_id AND (m.method_name LIKE ? OR m.analyte LIKE ?))
      OR EXISTS (SELECT 1 FROM rule r WHERE r.standard_id=s.standard_id AND (r.title LIKE ? OR r.requirement LIKE ?))
      ORDER BY s.standard_id""", (like,like,like,like,like,like)).fetchall()
else:
    rows = db.execute(base + " ORDER BY s.standard_id").fetchall()
print("标准数:", len(rows))
for r in rows:
    print("-", r["sid"], "|", r["title"])
    print("  规则:", r["rules"], "方法:", r["methods"] or "-")
    print("  单标准库:", r["file_path"] or "未导出")
db.close()
