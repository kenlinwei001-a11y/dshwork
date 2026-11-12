# -*- coding: utf-8 -*-
import argparse, hashlib, json, os, shutil, sqlite3, datetime
ap = argparse.ArgumentParser()
ap.add_argument("--db", required=True)
ap.add_argument("--outdir", default="by-standard")
args = ap.parse_args()
os.makedirs(args.outdir, exist_ok=True)
src = sqlite3.connect(args.db)
src.row_factory = sqlite3.Row
src.execute("CREATE TABLE IF NOT EXISTS standard_db (standard_id TEXT PRIMARY KEY, file_name TEXT, file_path TEXT, sha256 TEXT, db_bytes INTEGER, exported_at TEXT)")
src.commit()
standards = [dict(r) for r in src.execute("SELECT standard_id,title FROM standard ORDER BY standard_id")]
catalog = []
clear_tables = ["project_standard","report_standard","report_document","report_evidence","audit_result","audit_run","report","lab_alignment","lab_document","lab","project"]
for s in standards:
    sid = s["standard_id"]
    fname = s["title"] + "（" + sid + "）.db"
    fpath = os.path.join(args.outdir, fname)
    tmp = fpath + ".tmp"
    shutil.copy2(args.db, tmp)
    con = sqlite3.connect(tmp)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for t in tables:
        cols = [r[1] for r in con.execute("PRAGMA table_info(" + t + ")")]
        if "standard_id" in cols:
            con.execute("DELETE FROM " + t + " WHERE standard_id <> ?", (sid,))
    con.execute("DELETE FROM rule_set WHERE standard_id <> ?", (sid,))
    con.execute("DELETE FROM rule_set_member WHERE rule_set_id NOT IN (SELECT rule_set_id FROM rule_set)")
    for t in clear_tables:
        if t in tables:
            con.execute("DELETE FROM " + t)
    con.execute("INSERT OR REPLACE INTO schema_meta (key,value) VALUES ('db_kind','single-standard')")
    con.execute("INSERT OR REPLACE INTO schema_meta (key,value) VALUES ('standard_id',?)", (sid,))
    con.execute("INSERT OR REPLACE INTO schema_meta (key,value) VALUES ('standard_title',?)", (s["title"],))
    con.execute("INSERT OR REPLACE INTO schema_meta (key,value) VALUES ('exported_at',?)", (datetime.datetime.now().isoformat(timespec="seconds"),))
    con.commit(); con.execute("VACUUM"); con.close(); os.replace(tmp, fpath)
    h = hashlib.sha256(open(fpath,"rb").read()).hexdigest()
    size = os.path.getsize(fpath)
    src.execute("INSERT OR REPLACE INTO standard_db (standard_id,file_name,file_path,sha256,db_bytes,exported_at) VALUES (?,?,?,?,?,datetime('now'))", (sid,fname,fpath,h,size))
    counts = {"clauses": src.execute("SELECT COUNT(*) FROM clause WHERE standard_id=?",(sid,)).fetchone()[0],
              "elements": src.execute("SELECT COUNT(*) FROM element WHERE standard_id=?",(sid,)).fetchone()[0],
              "rules": src.execute("SELECT COUNT(*) FROM rule WHERE standard_id=?",(sid,)).fetchone()[0],
              "methods": src.execute("SELECT COUNT(*) FROM method WHERE standard_id=?",(sid,)).fetchone()[0]}
    catalog.append({"standard_id":sid,"title":s["title"],"file_name":fname,"file_path":fpath,"sha256":h,"db_bytes":size,**counts})
    print("exported", fname, size, counts["rules"], "rules")
src.commit()
with open(os.path.join(args.outdir,"catalog.json"),"w",encoding="utf-8") as f:
    json.dump({"generated_at":datetime.datetime.now().isoformat(timespec="seconds"),"standards":catalog},f,ensure_ascii=False,indent=2); f.write("\n")
src.close(); print("catalog", len(catalog))
