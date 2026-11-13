# -*- coding: utf-8 -*-
"""A1 表格抽取器：OCR 坐标 → 网格 → spec（供 table_store.ingest_cells 直接入库）

思路（确定性，零图像库）：
  1 取该页 OCR 行（含 x/y/w/h）
  2 按 y 中心聚类成「行」，按 x 中心聚类成「列」
  3 每个 OCR 行按中心点落入 (行,列) 单元格；同格多行合并
  4 首行/首列作为表头，其余为数据；输出 table_store 的矩阵 spec
  5 与已知值比对给出「结构一致率 / 取值一致率」，把 OCR 误差显式暴露

用法：
  python3 table_extract.py --tsv page-08.tsv --bbox 300,2330,2200,3100 \
      --table 表4 --page 8 --title "阴离子标准系列质量浓度" --unit mg/L \
      --expect-rows 8 --expect-cols 6 --out cells/t4.json
"""
import argparse, json, os, sys

def load(tsv, bbox=None):
    rows = []
    for line in open(tsv, encoding="utf-8"):
        if line.startswith("#") or not line.strip(): continue
        p = line.rstrip("\n").split("\t")
        if len(p) < 7: continue
        x, y, w, h = float(p[1]), float(p[2]), float(p[3]), float(p[4])
        if bbox:
            x0, y0, x1, y1 = bbox
            if not (x0 <= x + w / 2 <= x1 and y0 <= y + h / 2 <= y1): continue
        rows.append({"x": x, "y": y, "w": w, "h": h, "cx": x + w / 2, "cy": y + h / 2, "t": p[6]})
    return rows

def cluster(vals, gap):
    """一维聚类：相邻差 > gap 则断组；返回每项所属组号与组代表值"""
    idx = sorted(range(len(vals)), key=lambda i: vals[i])
    groups, cur, last = [], [], None
    for i in idx:
        if last is not None and vals[i] - last > gap:
            groups.append(cur); cur = []
        cur.append(i); last = vals[i]
    if cur: groups.append(cur)
    rep = {i: sum(vals[j] for j in g) / len(g) for g in groups for i in g}
    return {i: gi for gi, g in enumerate(groups) for i in g}, rep, len(groups)

def extract(items, gap_y=None, gap_x=None):
    ys = [it["cy"] for it in items]; xs = [it["cx"] for it in items]
    hy = sorted(it["h"] for it in items)[len(items)//2] if items else 20
    gap_y = gap_y or hy * 0.7
    gap_x = gap_x or hy * 1.2
    ry, _, nrow = cluster(ys, gap_y)
    rx, _, ncol = cluster(xs, gap_x)
    grid = {}
    for k, it in enumerate(items):
        key = (ry[k], rx[k])
        grid.setdefault(key, []).append(it)
    cells = {}
    for key, lst in grid.items():
        lst.sort(key=lambda z: (z["y"], z["x"]))
        cells[key] = " ".join(z["t"] for z in lst)
    return {"n_rows": nrow, "n_cols": ncol, "grid": {f"{r},{c}": v for (r, c), v in cells.items()},
            "cells": cells, "n_cells": len(cells)}

def to_spec(res, table_id, page, title, unit, nrow, ncol, standard="?", src=""):
    """以「首行为列头、首列为行头、其余为数据」生成矩阵 spec"""
    data = res["cells"]
    nrow, ncol = res["n_rows"], res["n_cols"]
    col_labels = [data.get((0, c), f"C{c+1}") for c in range(ncol)]
    row_labels = [data.get((r, 0), f"R{r+1}") for r in range(nrow)]
    matrix = []
    for r in range(1, nrow):
        row = [data.get((r, c), "") for c in range(1, ncol)]
        matrix.append(row)
    return {"standard_id": standard, "table_id": table_id, "page": page, "title": title,
            "unit": unit, "src": src or "ocr-grid", "source": "OCR",
            "expect_cells": (nrow - 1) * (ncol - 1),
            "row_labels": row_labels[1:], "col_labels": col_labels[1:], "matrix": matrix}

def compare(spec, expect):
    """与已知真值比对：结构一致率 + 取值一致率（忽略空白与千分位）"""
    got = spec["matrix"]; ok_cells = 0; tot = 0; diffs = []
    for i, row in enumerate(expect):
        for j, v in enumerate(row):
            tot += 1
            g = got[i][j] if i < len(got) and j < len(got[i]) else None
            if g is not None and str(g).replace(" ", "") == str(v).replace(" ", ""):
                ok_cells += 1
            else:
                diffs.append({"r": i + 1, "c": j + 1, "expect": v, "got": g})
    struct_ok = (len(got) == len(expect)) and all(len(a) == len(b) for a, b in zip(got, expect))
    return {"struct_ok": struct_ok, "rows": (len(got), len(expect)),
            "cols": (len(got[0]) if got else 0, len(expect[0]) if expect else 0),
            "cells_ok": ok_cells, "cells_total": tot,
            "value_accuracy": round(ok_cells / max(1, tot), 3), "diffs": diffs[:8]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True); ap.add_argument("--bbox")
    ap.add_argument("--table", required=True); ap.add_argument("--page", type=int)
    ap.add_argument("--title", default=""); ap.add_argument("--unit", default="")
    ap.add_argument("--standard", default="?"); ap.add_argument("--out")
    ap.add_argument("--expect-json", help="已知真值的矩阵 JSON（二维数组），用于验收")
    a = ap.parse_args()
    bbox = tuple(float(x) for x in a.bbox.split(",")) if a.bbox else None
    items = load(a.tsv, bbox)
    res = extract(items)
    spec = to_spec(res, a.table, a.page, a.title, a.unit, res["n_rows"], res["n_cols"], a.standard,
                   src=f"{os.path.basename(a.tsv)} bbox={a.bbox}")
    print(f"{a.table}: 检出网格 {res['n_rows']} 行 × {res['n_cols']} 列，非空单元格 {res['n_cells']}")
    if a.expect_json:
        exp = json.load(open(a.expect_json, encoding="utf-8"))
        cmp = compare(spec, exp)
        print(f"  结构一致: {cmp['struct_ok']}（{cmp['rows']} / {cmp['cols']}）")
        print(f"  取值一致: {cmp['cells_ok']}/{cmp['cells_total']}（{cmp['value_accuracy']:.0%}）")
        for d in cmp["diffs"][:6]:
            print(f"    R{d['r']}C{d['c']}: 期望 {d['expect']!r} 实得 {d['got']!r}")
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump(spec, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("  写出", a.out)

if __name__ == "__main__":
    main()
