# -*- coding: utf-8 -*-
"""A1 流水线：PDF 表格 → grid 工具（找线+逐格OCR）→ 后处理 → spec → 入库 → 校验

后处理解决两件事：
  1 合并表头：首行被表体竖线切碎 → 默认丢弃，列名用已知标签
  2 化学式标签 OCR 差：用离子词表做模糊匹配，匹配不上按表内既知顺序回填

用法：
  python3 table_from_pdf.py --pdf 标准.pdf --page 8 --clip 72,80,540,300 \
      --table 表4 --title "阴离子标准系列质量浓度" --unit mg/L \
      --row-labels F⁻,Cl⁻,NO₂⁻,Br⁻,NO₃⁻,PO₄³⁻,SO₃²⁻,SO₄²⁻ \
      --col-labels 点1,点2,点3,点4,点5,点6 --out cells/t4.json
"""
import argparse, json, os, subprocess, sys, difflib

HERE = os.path.dirname(os.path.abspath(__file__))

def grid_bin():
    """优先级：环境变量 TABLE_GRID_BIN → scripts/bin/grid"""
    cands = [os.environ.get("TABLE_GRID_BIN"), os.path.join(HERE, "bin", "grid"),
             os.path.join(HERE, "bin", "grid.exe")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    raise SystemExit("缺少表格网格工具：请先编译 bin/grid.swift，或设置 TABLE_GRID_BIN")

def run_grid(pdf, page, clip, out):
    cmd = [grid_bin(), pdf, str(page), out, "300"]
    if clip: cmd.append(clip)
    subprocess.run(cmd, check=True, capture_output=True)
    return json.load(open(out, encoding="utf-8"))

def label_ok(txt):
    return bool(txt) and txt.strip() not in ("·", "", "-")

def map_labels(raw, vocab):
    """模糊匹配 + 顺序回填"""
    out = [None] * len(raw)
    used = set()
    for i, t in enumerate(raw):
        if not label_ok(t): continue
        cand = difflib.get_close_matches(t.replace(" ", ""), vocab, n=1, cutoff=0.0)
        if cand and vocab.index(cand[0]) not in used:
            out[i] = cand[0]; used.add(vocab.index(cand[0]))
    rest = [v for i, v in enumerate(vocab) if i not in used]
    for i in range(len(out)):
        if out[i] is None and rest:
            out[i] = rest.pop(0)
    return out

def to_spec(g, vocab_rows, col_labels, table_id, page, title, unit, standard, src="grid"):
    nrow, ncol = g["n_rows"], g["n_cols"]
    grid = {(c["r"], c["c"]): c["text"].strip() for c in g["cells"]}
    drop_header = True                      # 首行是多列表头，丢弃
    r0 = 1 if drop_header else 0
    raw_rows = [grid.get((r, 0), "") for r in range(r0, nrow)]
    rows = map_labels(raw_rows, vocab_rows) if vocab_rows else raw_rows
    cols = col_labels or [f"点{c+1}" for c in range(1, ncol)]
    matrix = [[grid.get((r, c), "") for c in range(1, ncol)] for r in range(r0, nrow)]
    return {"standard_id": standard, "table_id": table_id, "page": page, "title": title,
            "unit": unit, "src": src, "source": "OCR",
            "expect_cells": len(matrix) * len(matrix[0]) if matrix else 0,
            "row_labels": rows, "col_labels": cols, "matrix": matrix}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True); ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--clip"); ap.add_argument("--table", required=True)
    ap.add_argument("--title", default=""); ap.add_argument("--unit", default="")
    ap.add_argument("--standard", default="?"); ap.add_argument("--out", required=True)
    ap.add_argument("--row-labels", default=""); ap.add_argument("--col-labels", default="")
    ap.add_argument("--ingest-db")
    a = ap.parse_args()
    grid_out = a.out.replace(".json", ".grid.json")
    g = run_grid(a.pdf, a.page, a.clip, grid_out)
    spec = to_spec(g, [x for x in a.row_labels.split(",") if x],
                   [x for x in a.col_labels.split(",") if x],
                   a.table, a.page, a.title, a.unit, a.standard,
                   src=f"grid:{os.path.basename(grid_out)} bbox={a.clip}")
    json.dump(spec, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{a.table}: 网格 {g['n_rows']}×{g['n_cols']} → spec {len(spec['matrix'])}行×"
          f"{len(spec['col_labels'])}列，单元格 {spec['expect_cells']}")
    for i, row in enumerate(spec["matrix"][:3]):
        print(f"  {spec['row_labels'][i]:8s} " + " ".join(f"{v:>6s}" for v in row))
    if a.ingest_db:
        sys.path.insert(0, HERE)
        from table_store import connect, ingest_cells, verify_table
        db = connect(a.ingest_db); ingest_cells(db, spec)
        for r in verify_table(db, a.table):
            print(f"  [{r['result']}] {r['check']}" + (f"  {r['detail']}" if r["result"] != "PASS" else ""))
