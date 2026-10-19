# -*- coding: utf-8 -*-
"""kp_toolkit.tables —— 宽表抽取（确定性，零 LLM）

可直接放入 kp_toolkit/tables.py。实现《表格抽取规则 v2》9 条规则。

对外两个函数：
  parse_docx_table_grid(docx_path) -> list[dict]     # 读 docx 的 gridSpan/vMerge，还原列结构
  extract_table_values(chunks, docx_tables, exist)  -> tuple[list[dict], list[dict]]

用法：
    from kp_toolkit.tables import parse_docx_table_grid, extract_table_values
    grids = parse_docx_table_grid("source/original.docx")
    nodes, skipped = extract_table_values(chunks, grids, exist_pairs)
"""
import re
import zipfile
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# ── 规则 ① 序号 / 年份 / 占位符 ──
NUM = re.compile(r"^\d+(?:\.\d+)?$")
SEQ = re.compile(r"^\d+(?:\.\d+)*$")
CNSEQ = re.compile(r"^[（(]?[一二三四五六七八九十]+[)）]?$")
YEAR = re.compile(r"^(19|20)\d{2}$")
PLACEHOLDER = ("/", "-", "—", "－", "无", "N/A", "n/a", "不适用", "待定")
SEP = re.compile(r"^\|[\s\-:|]+\|?$")
SUM = re.compile(r"^(合计|小计|总计|合\s*计)")

# ── 已知列角色（可扩展）──
ROLE = [
    ("合价", "合价", ("fixed", "万元")), ("单位造价", "单位造价", ("fixed", "元")),
    ("单价", "单价", ("fixed", "元")), ("用水定额", "用水定额", ("next", "")),
    ("日用水量", "日用水量", ("fixed", "m³/d")), ("年用水量", "年用水量", ("fixed", "万m³")),
    ("用水天数", "用水天数", ("fixed", "d")), ("建筑面积", "建筑面积", ("next", "")),
    ("最大允许面积", "最大允许面积", ("fixed", "㎡")),
    ("小计", "小计", ("fixed", "")), ("基本支出", "基本支出", ("fixed", "")),
    ("项目支出", "项目支出", ("fixed", "")), ("总支出", "总支出", ("fixed", "")),
    ("总收入", "总收入", ("fixed", "")), ("财政补助收入", "财政补助收入", ("fixed", "")),
    ("事业收入", "事业收入", ("fixed", "")), ("其他收入", "其他收入", ("fixed", "")),
    ("净资产", "净资产", ("fixed", "")), ("负债", "负债", ("fixed", "")), ("资产", "资产", ("fixed", "")),
]
VALUE_COLS = ("用水定额", "数量", "建筑面积", "最大允许面积", "规划人数", "面积指标", "定额")


def norm_num(x):
    """规则 ⑧ 全角归一化 + 去千分位"""
    t = str(x or "").translate(str.maketrans("０１２３４５６７８９．，", "0123456789.,"))
    return re.sub(r"[\s,]", "", t).strip()


def is_num(x):
    """规则 ⑦ 占位符返回 None（不计入统计），数字返回 True"""
    t = norm_num(x)
    if not t or t in PLACEHOLDER:
        return None
    return bool(NUM.match(t))


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def align_matrix(rows):
    """去掉「整列都为空」的首尾列，保留内部空单元格（双层表头靠它识别）"""
    mat = [split_row(r) for r in rows if not SEP.match(r.strip())]
    if not mat:
        return []
    n = max(len(r) for r in mat)
    mat = [r + [""] * (n - len(r)) for r in mat]
    empty = lambda i: all(not r[i] for r in mat)
    lo, hi = 0, n - 1
    while lo <= hi and empty(lo):
        lo += 1
    while hi >= lo and empty(hi):
        hi -= 1
    return [r[lo:hi + 1] for r in mat]


# ══════════ 规则 ⑥：docx 表格网格 ══════════
def parse_docx_table_grid(docx_path):
    """读 docx 的 <w:gridSpan>/<w:vMerge>，展开成定宽网格并合成表头（分组·子列）"""
    with zipfile.ZipFile(docx_path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")
    out = []
    for tbl in body.iter(W + "tbl"):
        grid = []
        for tr in tbl.findall(W + "tr"):
            row = []
            for tc in tr.findall(W + "tc"):
                pr = tc.find(W + "tcPr")
                span, vmerge = 1, None
                if pr is not None:
                    gs = pr.find(W + "gridSpan")
                    if gs is not None and gs.get(W + "val"):
                        span = int(gs.get(W + "val"))
                    vm = pr.find(W + "vMerge")
                    if vm is not None:
                        vmerge = vm.get(W + "val") or "continue"
                row.append({"text": "".join(t.text or "" for t in tc.iter(W + "t")).strip(),
                            "span": span, "vmerge": vmerge})
            grid.append(row)
        maxcols = max((sum(c["span"] for c in r) for r in grid), default=0)
        flat = []
        for r in grid:
            cells = []
            for c in r:
                cells.append(c["text"])
                cells.extend([None] * (c["span"] - 1))     # 被合并的列占位
            cells += [None] * (maxcols - len(cells))
            flat.append(cells)
        if not flat:
            continue
        out.append({"ncols": maxcols, "grid": flat,
                    "first_cell": flat[0][0] if flat[0] else "",
                    "rows": len(flat), "header": _build_header(flat)})
    return out


def _build_header(grid):
    """分组名向下继承 + 子列行合并 → ['年度','事业支出·小计',…]（规则 ③）"""
    if not grid:
        return []
    h1 = grid[0]
    g, last = [], ""
    for v in h1:
        if v:
            last = v
        g.append(last if v is None else v)
    if len(grid) == 1:
        return [x or "" for x in h1]
    h2 = grid[1]
    sub = sum(1 for x in h2 if x) >= 2 and all(not re.fullmatch(r"[\d,，.．]+", (x or "").strip())
                                               for x in h2 if x)
    if not sub:
        return [x or "" for x in h1]
    out = []
    for i in range(len(h1)):
        a, b = g[i] or "", h2[i] or ""
        out.append(f"{a}·{b}" if a and b and a != b else (b or a))
    return out


def docx_header(grids, first_cell, ncols, second=""):
    """(首格, 列数, 第 2 列名) 三元组匹配 —— 只靠前两个会在同形表上撞车"""
    fc = re.sub(r"\s", "", first_cell or "")[:10]
    ms = re.sub(r"\s", "", second or "")[:10]
    cands = [t for t in grids
             if t["ncols"] == ncols and re.sub(r"\s", "", str(t["first_cell"]) or "")[:10] == fc]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]["header"]
    for t in cands:
        g = t["grid"]
        if g and len(g[0]) > 1:
            d2 = re.sub(r"\s", "", str(g[0][1] or ""))[:10]
            if d2 and ms and (d2 == ms or d2 in ms or ms in d2):
                return t["header"]
    return cands[0]["header"]


# ══════════ 抽取主逻辑 ══════════
def extract_table_values(chunks, docx_grids, exist_pairs):
    """从 chunks 里的 ```table 块抽值节点。

    Args:
        chunks: [{"id","text","section_struct_no","section_path"}, ...]
        docx_grids: parse_docx_table_grid() 的结果
        exist_pairs: set[(subject, value)] 已存在的值，跳过不重复抽
    Returns:
        (nodes, skipped)
    """
    added, skipped = [], []

    def _fam(sub, pred, val, cid):
        return "N-" + hashlib.sha1(f"{sub}|{pred}|{val}|{cid}".encode()).hexdigest()[:12]

    for c in chunks:
        text = c.get("text") or ""
        if "```table" not in text:
            continue
        inb, rows = False, []
        for ln in text.split("\n"):
            s = ln.strip()
            if s.startswith("```table"):
                inb, rows = True, []
                continue
            if inb and s == "```":
                inb = False
                _handle(rows, c, added, skipped, exist_pairs, docx_grids, _fam)
                continue
            if inb and s.startswith("|"):
                rows.append(s)
    return added, skipped


def _handle(rows, c, added, skipped, exist_pairs, grids, nid):
    dr = [r for r in rows if not SEP.match(r.strip())]
    if len(dr) < 2:
        return
    mat = align_matrix(dr)
    if len(mat) < 2:
        return
    h1, r2 = mat[0], mat[1]
    sub = sum(1 for x in r2 if x) >= 2 and all(
        not re.fullmatch(r"[\d,，.．]+", (x or "").strip()) for x in r2 if x)
    header = r2 if sub else h1
    start = 2 if sub else 1
    body = mat[start:]
    if not body:
        return

    # 规则 ⑥：优先用 docx 还原的真实列结构
    nonempty = [x for x in header if x]
    dh = docx_header(grids, nonempty[0] if nonempty else "", len(body[0]),
                     nonempty[1] if len(nonempty) > 1 else "") if grids else None
    if dh and len(dh) == len(body[0]):
        header = dh
        if any("·" in x for x in dh) and len(mat) > 2:
            body = mat[2:]                    # 双层表头，数据从第 3 行起
        skipped.append({"chunk": c["id"], "reason": "A docx gridSpan 还原", "info": True})
    elif not sub:
        while len(header) > 1 and not header[0] and body[0] and body[0][0]:
            header = header[1:]

    # 规则 ⑤：值列自带单位 → 搬尾部空列补单位列
    def build_cm(hd):
        cm = []
        for i, hn in enumerate(hd):
            if not hn or hn == "（单位）":
                continue
            for kw, pred, usrc in ROLE:
                if kw in hn:
                    base = re.sub(r"[（(][^）)]*[）)]", "", hn).strip()
                    cm.append((i, base if 2 <= len(base) <= 12 else pred, usrc))
                    break
        return cm

    def check(hd, bd):
        cm = build_cm(hd)
        if not cm:
            return None, "表头没有可识别的值列"
        for ci, _p, _u in cm:
            if ci < len(hd) and hd[ci] == "（单位）":
                continue
            col = [(r[ci] if ci < len(r) else "") for r in bd]
            judged = [is_num(x) for x in col if x and is_num(x) is not None]
            if not judged:
                continue
            if sum(1 for j in judged if j) / len(judged) < 0.8:
                return None, f"列「{hd[ci][:16]}」只有 {round(100*sum(1 for j in judged if j)/len(judged))}% 是数字"
        return cm, None

    colmap, mis = check(header, body)
    if mis and not sub:
        for diff in (1, 2):
            nh = list(header)
            for _ in range(diff):
                hit = -1
                for i in range(len(nh) - 1):
                    if any(k in nh[i] for k in VALUE_COLS) and any(k in nh[i + 1] for k in VALUE_COLS):
                        colv = [r[i + 1] for r in body if i + 1 < len(r) and r[i + 1]]
                        if colv and sum(1 for x in colv if is_num(x)) / len(colv) < 0.5:
                            hit = i
                            break
                if hit < 0:
                    break
                nh = nh[:hit + 1] + ["（单位）"] + nh[hit + 1:]
                while nh and not nh[-1]:
                    nh = nh[:-1]
                if len(nh) < len(body[0]):
                    nh.append("")
            if len(nh) != len(body[0]):
                continue
            cm2, m2 = check(nh, body)
            if cm2:
                header, colmap, mis = nh, cm2, None
                skipped.append({"chunk": c["id"], "reason": f"⑤ 插 {diff} 个单位列", "info": True})
                break
    if colmap is None:
        skipped.append({"chunk": c["id"], "reason": mis or "无法对齐"})
        return

    for ri, cells in enumerate(body):
        first = cells[0] if cells else ""
        is_sum = bool(SUM.match(first)) or bool(SUM.match(cells[1] if len(cells) > 1 else ""))
        subj = ""
        for x in cells[:3]:
            if not x or len(x) > 24:
                continue
            if YEAR.fullmatch(x):
                subj = x
                break
            if SEQ.match(x) or CNSEQ.match(x) or is_num(x):
                continue
            if re.search(r"[，。；、]", x):
                continue
            if re.match(r"^\d[\d,.]*\s*(人|个|间|㎡|m|万元|元|%|m³|L)", x):
                continue
            subj = x
            break
        if not subj:
            continue
        for ci, pred, usrc in colmap:
            if ci >= len(cells):
                continue
            v = norm_num(cells[ci])
            if not NUM.match(v):
                continue
            unit = usrc[1] if usrc[0] == "fixed" else (
                cells[ci + 1] if ci + 1 < len(cells) and not NUM.match(cells[ci + 1] or "") else "")
            if is_sum:
                pred = "合计" if "合计" in "".join(cells[:2]) else "汇总"
            if (subj, v) in exist_pairs:
                continue
            added.append({"id": nid(subj, pred, v, c["id"]), "subject": subj, "predicate": pred,
                          "kind": "quantity", "value": v, "unit": unit,
                          "source": c["id"], "section": c.get("section_struct_no") or "",
                          "section_path": c.get("section_path") or [],
                          "anchor": {"doc_span": None, "quote": " | ".join(cells)[:120],
                                     "slice_id": c["id"], "table_row": ri},
                          "origin": "table_extraction_v2"})
