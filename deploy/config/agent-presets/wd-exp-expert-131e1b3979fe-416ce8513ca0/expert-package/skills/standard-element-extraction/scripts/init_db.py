#!/usr/bin/env python3
"""Create an empty standards database from schema.sqlite.sql."""
import argparse
import pathlib
import sqlite3

parser = argparse.ArgumentParser()
parser.add_argument("--db", required=True)
parser.add_argument("--schema", default=None)
args = parser.parse_args()
schema = pathlib.Path(args.schema) if args.schema else pathlib.Path(__file__).resolve().parent.parent / "schema.sqlite.sql"
db = sqlite3.connect(args.db)
db.executescript(schema.read_text(encoding="utf-8"))
db.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema', 'standards-v1.1')")
db.commit()
db.close()
print("initialized", args.db)
