# -*- coding: utf-8 -*-
"""表格层（通用入库器）：整表入库 + 键值索引 + 窄接口 + 入库校验

架构：**一个通用入库器，多个构建器**
  构建器（builder）把"标准/报告里的表"转成通用 spec；
  ingest_cells 只管 spec → 库，与来源无关（标准表、报告表、记录表同一条路径）。

spec 两种写法：
  A 显式单元格
    {"table_id":"表1","page":4,"title":"...","unit":"mg/L",
     "cells":[{"row":0,"col":0,"row_label":"F⁻","col_label":"方法检出限","value":"0.006","source":"IMAGE"}]}
  B 矩阵简写（推荐）
    {"table_id":"表4","row_labels":["F⁻",...],"col_labels":["点1",...],
     "matrix":[["0.00","0.10",...],...],"source":"IMAGE",
     "index_rule":{"param_from":"col_label","only_numeric":true}}

校验两层：
  通用层：空值 / 来源标注 / 声明格数
  模式层：按列名触发的算术规则（如「方法检出限+测定下限 ⇒ LOQ=4×DL」），与具体标准无关

用法：
  table_store.py init    --db tables.db
  table_store.py ingest-cells --db tables.db --spec cells.json
  table_store.py ingest  --db tables.db --ses <ses.json> --appendix <apx.json>   # HJ84 构建器
  table_store.py verify  --db tables.db
  table_store.py lookup|row|col|render|stats ...
"""
import argparse, json, os, sqlite3, sys

DDL = """
CREATE TABLE IF NOT EXISTS table_meta(
  table_id TEXT PRIMARY KEY, standard_id TEXT, clause TEXT, page INT,
  title TEXT, unit TEXT, note TEXT, n_rows INT, n_cols INT, src TEXT, expect_cells INT);
CREATE TABLE IF NOT EXISTS table_cell(
  table_id TEXT, row_i INT, col_i INT, row_label TEXT, col_label TEXT,
  value_raw TEXT, value_num REAL, unit TEXT, value_source TEXT, cell_ref TEXT,
  PRIMARY KEY(table_id, row_i, col_i));
CREATE TABLE IF NOT EXISTS param_index(
  param TEXT, row_key TEXT, standard_id TEXT, value_raw TEXT, value_num REAL,
  unit TEXT, table_id TEXT, row_i INT, col_i INT, page INT,
  PRIMARY KEY(param, row_key, standard_id));
CREATE INDEX IF NOT EXISTS idx_param    ON param_index(row_key, param);
CREATE INDEX IF NOT EXISTS idx_cell_row ON table_cell(table_id, row_i);
CREATE INDEX IF NOT EXISTS idx_cell_col ON table_cell(table_id, col_i);
DROP VIEW IF EXISTS v_param;
CREATE VIEW v_param AS
  SELECT row_key AS ion, param, value_num, unit, table_id, page, row_i, col_i, value_raw
  FROM param_index;
"""

def connect(db):
    c = sqlite3.connect(db); c.row_factory = sqlite3.Row
    c.executescript(DDL); return c

def num(s):
    try:
        t = str(s).replace("<", "").replace(">", "").replace("～", "").replace("%", "").strip()
        return float(t)
    except Exception:
        return None

# ---------------------------------------------------------------- 通用入库
def expand(spec):
    out = []
    if "cells" in spec:
        for c in spec["cells"]:
            out.append({"row": c["row"], "col": c["col"],
                        "row_label": c.get("row_label"), "col_label": c.get("col_label"),
                        "value": c["value"], "source": c.get("source", spec.get("source", "IMAGE"))})
    else:
        rl, cl = spec["row_labels"], spec["col_labels"]
        for i, r in enumerate(spec["matrix"]):
            for j, v in enumerate(r):
                out.append({"row": i, "col": j,
                            "row_label": rl[i] if i < len(rl) else None,
                            "col_label": cl[j] if j < len(cl) else None,
                            "value": v, "source": spec.get("source", "IMAGE")})
    return out

def ingest_cells(db, spec):
    tid = spec["table_id"]; std = spec.get("standard_id", "?")
    cells = expand(spec)
    n_rows = len({c["row"] for c in cells}); n_cols = len({c["col"] for c in cells})
    db.execute("INSERT OR REPLACE INTO table_meta VALUES (?,?,?,?,?,?,?,?,?,?,?)",
               (tid, std, spec.get("clause", tid), spec.get("page"), spec.get("title", ""),
                spec.get("unit", ""), spec.get("note"), n_rows, n_cols,
                spec.get("src", "generic"), spec.get("expect_cells")))
    db.execute("DELETE FROM table_cell WHERE table_id=?", (tid,))
    for c in cells:
        db.execute("INSERT OR REPLACE INTO table_cell VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (tid, c["row"], c["col"], c["row_label"], c["col_label"],
                    str(c["value"]), num(c["value"]), spec.get("unit", ""), c["source"],
                    f"{tid}!R{c['row']+1}C{c['col']+1}"))
    db.execute("DELETE FROM param_index WHERE table_id=?", (tid,))
    rule = spec.get("index_rule")
    if rule:
        for c in cells:
            if rule.get("only_numeric") and num(c["value"]) is None:
                continue
            param, key = c["col_label"], c["row_label"]
            if rule.get("param_from") == "row_label":
                param, key = c["row_label"], c["col_label"]
            if not param or key is None:
                continue
            db.execute("INSERT OR REPLACE INTO param_index VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (param, key, std, str(c["value"]), num(c["value"]),
                        spec.get("unit", ""), tid, c["row"], c["col"], spec.get("page")))
    db.commit()
    return {"table_id": tid, "cells": len(cells), "rows": n_rows, "cols": n_cols}

# ---------------------------------------------------------------- 校验
def grid(db, tid):
    return db.execute("SELECT * FROM table_cell WHERE table_id=? ORDER BY row_i,col_i", (tid,)).fetchall()

def verify_table(db, tid):
    rs = grid(db, tid)
    meta = db.execute("SELECT * FROM table_meta WHERE table_id=?", (tid,)).fetchone()
    out = []
    empt = [r["cell_ref"] for r in rs if r["value_raw"] in (None, "")]
    out.append({"table": tid, "check": "无空单元格", "result": "PASS" if not empt else "FAIL", "detail": empt[:3]})
    nosrc = [r["cell_ref"] for r in rs if r["value_source"] not in ("IMAGE", "OCR", "TEXT")]
    out.append({"table": tid, "check": "每格标注取值来源", "result": "PASS" if not nosrc else "FAIL", "detail": nosrc[:3]})
    if meta["expect_cells"]:
        ok = len(rs) == meta["expect_cells"]
        out.append({"table": tid, "check": f"声明格数 = {meta['expect_cells']}",
                    "result": "PASS" if ok else "FAIL", "detail": len(rs)})
    cols = {r["col_label"] for r in rs}
    col_list = [r["col_label"] for r in db.execute(
        "SELECT DISTINCT col_i, col_label FROM table_cell WHERE table_id=? ORDER BY col_i", (tid,))]
    if "方法检出限" in cols and "测定下限" in cols:
        bad = []
        for i in sorted({r["row_i"] for r in rs}):
            dl = next((num(r["value_raw"]) for r in rs if r["row_i"] == i and r["col_label"] == "方法检出限"), None)
            loq = next((num(r["value_raw"]) for r in rs if r["row_i"] == i and r["col_label"] == "测定下限"), None)
            if dl and loq and abs(loq - 4 * dl) > 1e-6:
                bad.append(f"R{i+1}: {dl}→{loq}")
        out.append({"table": tid, "check": "模式规则：测定下限 = 4 × 检出限",
                    "result": "PASS" if not bad else "FAIL", "detail": bad[:3]})
    if col_list and all(str(c).startswith("点") for c in col_list) and len(col_list) >= 3:
        bad = []
        for i in sorted({r["row_i"] for r in rs}):
            vals = [num(r["value_raw"]) for r in sorted(rs, key=lambda x: x["col_i"]) if r["row_i"] == i]
            vals = [v for v in vals if v is not None]
            if not vals: continue
            if abs(vals[0]) > 1e-9: bad.append(f"R{i+1}: 首点≠0")
            if any(b <= a for a, b in zip(vals, vals[1:])): bad.append(f"R{i+1}: 非单调递增")
        out.append({"table": tid, "check": "模式规则：标准系列（首点 0、单调递增）",
                    "result": "PASS" if not bad else "FAIL", "detail": bad[:3]})
    return out

def verify_all(db):
    res = []
    for r in db.execute("SELECT table_id FROM table_meta ORDER BY table_id"):
        res += verify_table(db, r["table_id"])
    n = db.execute("SELECT COUNT(*) FROM param_index").fetchone()[0]
    res.append({"table": "ALL", "check": "参数索引非空", "result": "PASS" if n else "WARN", "detail": n})
    return res

# ---------------------------------------------------------------- 接口
def lookup(db, key, param):
    r = db.execute("SELECT * FROM param_index WHERE row_key=? AND param=?", (key, param)).fetchone()
    if not r:
        return {"found": False, "key": key, "param": param}
    return {"found": True, "key": key, "param": param, "value": r["value_num"],
            "value_raw": r["value_raw"], "unit": r["unit"],
            "provenance": {"table": r["table_id"], "page": r["page"],
                           "row": r["row_i"] + 1, "col": r["col_i"] + 1},
            "quote": f"{r['table_id']} R{r['row_i']+1}C{r['col_i']+1} = {r['value_raw']} {r['unit']}".strip()}

def row(db, tid, label):
    return [{"col": r["col_label"], "value": r["value_raw"], "source": r["value_source"]}
            for r in db.execute("SELECT * FROM table_cell WHERE table_id=? AND row_label=? ORDER BY col_i", (tid, label))]

def col(db, tid, label):
    return [{"row": r["row_label"], "value": r["value_raw"]}
            for r in db.execute("SELECT * FROM table_cell WHERE table_id=? AND col_label=? ORDER BY row_i", (tid, label))]

def render(db, tid):
    meta = db.execute("SELECT * FROM table_meta WHERE table_id=?", (tid,)).fetchone()
    if not meta: return "（无此表）"
    rs = grid(db, tid)
    rows = sorted({r["row_i"] for r in rs}); cols = sorted({r["col_i"] for r in rs})
    g = {(r["row_i"], r["col_i"]): r["value_raw"] for r in rs}
    rl = {r["row_i"]: r["row_label"] for r in rs}; cl = {r["col_i"]: r["col_label"] for r in rs}
    out = [f"### {tid} {meta['title']}（p{meta['page']}，{meta['unit']}）"]
    if meta["note"]: out.append(f"> {meta['note']}")
    out.append("| 行 | " + " | ".join(str(cl[c]) for c in cols) + " |")
    out.append("|---|" + "---|" * len(cols))
    for r in rows:
        out.append(f"| {rl[r]} | " + " | ".join(str(g.get((r, c), "")) for c in cols) + " |")
    return "\n".join(out)

# ---------------------------------------------------------------- HJ84 构建器
def build_hj84(ses_path, apx_path):
    S = json.load(open(ses_path, encoding="utf-8")); A = json.load(open(apx_path, encoding="utf-8"))
    std = S["standard_id"]; P = {p["ion"]: p for p in S["ion_parameters"]}
    ions = [p["ion"] for p in S["ion_parameters"]]
    specs = [
      {"standard_id": std, "table_id": "表1", "clause": "表1", "page": 4,
       "title": "方法检出限和测定下限", "unit": "mg/L", "src": "pdf p4 图像核读",
       "expect_cells": 16, "source": "IMAGE", "row_labels": ions,
       "col_labels": ["方法检出限", "测定下限"],
       "matrix": [[P[i]["dl_mg_L"], P[i]["loq_mg_L"]] for i in ions],
       "index_rule": {"param_from": "col_label", "only_numeric": True}},
      {"standard_id": std, "table_id": "表2", "clause": "表2", "page": 7,
       "title": "水样的保存条件和要求", "unit": "天", "src": "pdf p7 图像核读",
       "expect_cells": 16, "source": "IMAGE", "row_labels": ions,
       "col_labels": ["盛放容器的材质", "保存时间"],
       "matrix": [[P[i]["container"], f"{P[i]['storage_days']} 天"] for i in ions],
       "index_rule": {"param_from": "col_label", "only_numeric": True}},
      {"standard_id": std, "table_id": "表3", "clause": "表3", "page": 8,
       "title": "氢氧根淋洗液梯度程序分析条件", "unit": "%", "src": "pdf p8 图像核读",
       "expect_cells": 8, "source": "IMAGE",
       "row_labels": ["0 min", "25 min", "25.1 min", "30 min"],
       "col_labels": ["A(H₂O)", "B(100 mmol/L NaOH)"],
       "matrix": [["90%", "10%"], ["40%", "60%"], ["90%", "10%"], ["90%", "10%"]]},
      {"standard_id": std, "table_id": "表4", "clause": "表4", "page": 8,
       "title": "阴离子标准系列质量浓度", "unit": "mg/L", "src": "pdf p8 图像核读",
       "expect_cells": 48, "source": "IMAGE", "row_labels": ions,
       "col_labels": [f"点{j+1}" for j in range(6)],
       "matrix": [list(P[i].get("series_text") or [str(v) for v in P[i]["series_mg_L"]]) for i in ions],
       "index_rule": {"param_from": "col_label", "only_numeric": True}},
    ]
    mA1 = ["平均值", "室内RSD", "室间RSD", "r", "R"]
    rl, mat = [], []
    for ion in ions:
        for lv in A["tableA1"]["rows"]:
            if lv["ion"] != ion: continue
            for k, level in enumerate(lv["levels"]):
                rl.append(f"{ion}-L{k+1}")
                mat.append([level[x] for x in ["平均值", "室内RSD", "室间RSD", "r", "R"]])
    specs.append({"standard_id": std, "table_id": "表A.1", "clause": "表A.1", "page": 11,
                  "title": "方法的精密度", "unit": "混合", "src": "pdf p11 图像核读",
                  "note": "资料性：reference_only，不得作判定阈值", "expect_cells": 120,
                  "source": "IMAGE", "row_labels": rl, "col_labels": mA1, "matrix": mat})
    mA2 = A["tableA2"]["columns"][1:]
    rl2, mat2 = [], []
    for ion in ions:
        for blk in A["tableA2"]["rows"]:
            if blk["ion"] != ion: continue
            for s in blk["samples"]:
                rl2.append(f"{ion}-{s['样品类型']}")
                mat2.append([s["原样浓度"], s["加标量"], s["回收率区间"], s["最终值"]])
    specs.append({"standard_id": std, "table_id": "表A.2", "clause": "表A.2", "page": 12,
                  "title": "方法的准确度", "unit": "混合", "src": "pdf p12 图像核读",
                  "note": "资料性：reference_only；ND 表示未检出", "expect_cells": 128,
                  "source": "IMAGE", "row_labels": rl2, "col_labels": mA2, "matrix": mat2})
    return specs

# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("--db", required=True)
    s = sub.add_parser("ingest-cells"); s.add_argument("--db", required=True); s.add_argument("--spec", required=True)
    s = sub.add_parser("ingest"); s.add_argument("--db", required=True)
    s.add_argument("--ses"); s.add_argument("--appendix")
    s = sub.add_parser("stats"); s.add_argument("--db", required=True)
    s = sub.add_parser("verify"); s.add_argument("--db", required=True)
    s = sub.add_parser("lookup"); s.add_argument("--db", required=True); s.add_argument("--ion"); s.add_argument("--param")
    s = sub.add_parser("row"); s.add_argument("--db", required=True); s.add_argument("--table"); s.add_argument("--label")
    s = sub.add_parser("col"); s.add_argument("--db", required=True); s.add_argument("--table"); s.add_argument("--label")
    s = sub.add_parser("render"); s.add_argument("--db", required=True); s.add_argument("--table")
    a = ap.parse_args()

    if a.cmd == "init":
        connect(a.db); print("initialized", a.db)
    elif a.cmd == "ingest-cells":
        db = connect(a.db); spec = json.load(open(a.spec, encoding="utf-8"))
        for sp in (spec["tables"] if "tables" in spec else [spec]):
            print(" ", ingest_cells(db, sp))
    elif a.cmd == "ingest":
        db = connect(a.db)
        for sp in build_hj84(a.ses, a.appendix):
            print(" ", ingest_cells(db, sp))
    elif a.cmd == "stats":
        db = connect(a.db)
        for r in db.execute("SELECT * FROM table_meta ORDER BY table_id"):
            print(f"  {r['table_id']:8s} {r['n_rows']:>3} × {r['n_cols']}   {r['title']}")
        print(f"  单元格 {db.execute('SELECT COUNT(*) FROM table_cell').fetchone()[0]}"
              f"；索引 {db.execute('SELECT COUNT(*) FROM param_index').fetchone()[0]}")
    elif a.cmd == "verify":
        res = verify_all(connect(a.db))
        for r in res:
            d = f"   {r['detail']}" if r["result"] != "PASS" else ""
            print(f"  [{r['result']}] {r['table']:8s} {r['check']}{d}")
        sys.exit(0 if all(r["result"] in ("PASS", "WARN") for r in res) else 1)
    elif a.cmd == "lookup":
        print(json.dumps(lookup(connect(a.db), a.ion, a.param), ensure_ascii=False, indent=2))
    elif a.cmd == "row":
        for x in row(connect(a.db), a.table, a.label): print(" ", x)
    elif a.cmd == "col":
        for x in col(connect(a.db), a.table, a.label): print(" ", x)
    elif a.cmd == "render":
        print(render(connect(a.db), a.table))

if __name__ == "__main__":
    main()
