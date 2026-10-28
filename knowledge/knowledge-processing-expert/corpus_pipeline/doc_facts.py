# -*- coding: utf-8 -*-
"""doc_facts —— 把客户给的各种格式材料转成 instantiate_project 要的 provided_facts。

支持：.md .txt .docx .xlsx .xlsm .pdf .csv

硬规矩（不可协商）：
  ① **表格必须读原生结构**（docx <w:tbl> grid / xlsx cell grid / pdf 表格对象），
     绝不把表格拍平成 markdown 再用正则猜列——拍平会丢列对应关系（实测 110 个 subject 错乱）。
  ② 值不是数字且不像文本事实 -> 不产出，转 candidates 交 LLM 二次抽取。
  ③ 同名多次出现且值不同 -> 产出 conflicts，不取其一、不裁决。
  ④ 单位缺失 -> unit 置 ""，记 warning。
  ⑤ 单位与规则口径不一致（如 m³ vs 万m³）-> 显式换算并记录 unit_conversion。

用法：
    from corpus_pipeline.doc_facts import to_provided_facts
    r = to_provided_facts("客户材料.docx", as_of="2026-03-15")
    # r = {provided_facts, conflicts, warnings, candidates, stats}
"""
from __future__ import annotations
import csv
import re
from pathlib import Path

_NUM = r"[+-]?\d[\d,]*(?:\.\d+)?"
_UNITS = [
    "万元", "亿元", "元", "㎡", "m²", "m2", "平方米", "m³", "m3", "立方米", "m", "米", "mm",
    "cm²", "km²", "万㎡", "万m²", "kW", "kWh", "kVA", "W", "L/s", "L/d", "L/人·日", "L/人日",
    "L/生·日", "L/生·d", "人/日", "人/d", "m³/d", "m3/d", "t/d",
    "kg/㎡", "kg/m²", "kN/㎡", "kN/m²", "kgce/㎡", "元/㎡",
    "人", "台", "层", "个", "处", "项",
    "%", "d", "h", "吨标煤", "吨", "万kWh", "万m³", "万m3", "万立方米",
]
_UNIT_RE = "|".join(re.escape(u) for u in sorted(_UNITS, key=len, reverse=True))
# 兜底：未在白名单里的常见「单位形态」（短、含单位符号/汉字/斜杠），避免真实单位被丢
_UNIT_LOOSE = re.compile(r"^[A-Za-z\u4e00-\u9fa5%·²³/（）()\-\.]{1,12}$")
_TREE = re.compile(r"^[\s\u2500-\u257F\u2502\u251C\u2514\u2518\u2510\u250C\u2550\u2551\-\*·]+")

ALIAS = {
    "工程建设其他费": "工程建设其他费用", "建安工程费": "建安工程费用", "建安费": "建安工程费用",
    "总建筑面积": "本项目建筑面积", "建筑面积": "本项目建筑面积",
    "年用电量": "年总耗电量", "年耗电量": "年总耗电量", "年用水量": "年总用水量",
    "冷负荷指标": "单位面积冷负荷指标", "热负荷指标": "单位面积热负荷指标",
    "公共服务配套用房": "公共服务配套用房建筑面积",
    "科研用房需求系数": "科研用房需要系数", "需求系数": "需要系数", "同期系数": "同时使用系数",
    "其他费用": "工程建设其他费用", "二类费": "工程建设其他费用",
    "基本预备费": "预备费",
    "本项目总投资": "总投资", "工程总投资": "总投资", "项目总投资": "总投资",
    "本项目建设面积": "本项目建筑面积", "拟建建筑面积": "本项目建筑面积",
    "科研人员数": "科研人员规划人数", "研究人员数": "科研人员规划人数",
    "研究生数": "研究生博士生访问学者规划人数",
}


def _norm_label(s: str) -> str:
    """去掉「数字/英文」与「中文」之间的空格：30HP 机组 → 30HP机组。
    不动纯中文内部的空格（如「科研 用房」这种可能是排版差异，保留原样以免误合）。"""
    s = re.sub(r"([0-9A-Za-z])\s+([\u4e00-\u9fa5])", r"\1\2", s)
    s = re.sub(r"([\u4e00-\u9fa5])\s+([0-9A-Za-z])", r"\1\2", s)
    return s



def _clean(s) -> str:
    s = str(s if s is not None else "").strip()
    s = _TREE.sub("", s).strip()
    # 去序号前缀，但**不能误伤小数**：
    #   "（1）项目概况" / "1) 概况"  → 去前缀
    #   "1、概况"                    → 去前缀
    #   "1. 项目概况"                → 去前缀（点后必须有空白）
    #   "0.8" / "1.15"              → **保留**（点后紧跟数字，是小数不是序号）
    s = re.sub(r"^[（(]\d{1,2}[）)]\s*", "", s)
    s = re.sub(r"^\d{1,2}[）、]\s*", "", s)
    s = re.sub(r"^\d{1,2}\.\s+(?=\S)", "", s)
    s = s.strip("*：: ").strip()
    return _norm_label(s)


def _num(v):
    s = str(v).replace(",", "").replace("，", "").strip()
    if not s:
        return None
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return None


def _align_unit(val, unit):
    """单位与规则口径归一。"""
    u = _clean(unit)
    if u in ("m3", "m³", "立方米") and isinstance(val, (int, float)) and abs(val) > 1000:
        return round(val / 10000, 2), "万m³", "原单位 m³，按规则口径换算为万m³"
    if u in ("kWh", "千瓦时") and isinstance(val, (int, float)) and abs(val) > 10000:
        return round(val / 10000, 2), "万kWh", "原单位 kWh，按规则口径换算为万kWh"
    return val, u, ""


# ---------------------------------------------------------------- 读取各格式
def read_docx(path: Path):
    """返回 (text, rows, meta)。表格按 <w:tbl> 原生 grid 读，不拍平。"""
    from docx import Document
    doc = Document(str(path))
    paras = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    rows = []
    for ti, tbl in enumerate(doc.tables):
        grid = [[_clean(c.text) for c in row.cells] for row in tbl.rows]
        for ri, g in enumerate(grid):
            rows.append({"table": ti, "row": ri, "cells": g, "raw": " | ".join(g)})
    return "\n".join(paras), rows, {"paragraphs": len(paras), "tables": len(doc.tables)}


def read_xlsx(path: Path):
    """返回 (text, rows, meta)。按 cell grid 读，保留 sheet 名。"""
    from openpyxl import load_workbook
    wb = load_workbook(str(path), data_only=True, read_only=True)
    rows, texts = [], []
    for ws in wb.worksheets:
        for ri, row in enumerate(ws.iter_rows(values_only=True), start=1):
            cells = ["" if c is None else _clean(c) for c in row]
            if not any(cells):
                continue
            rows.append({"sheet": ws.title, "row": ri, "cells": cells, "raw": " | ".join(cells)})
            texts.append("%s\t%s" % (ws.title, " | ".join(cells)))
    return "\n".join(texts), rows, {"sheets": len(wb.worksheets)}


def read_pdf(path: Path):
    """返回 (text, rows, meta)。优先用 find_tables() 拿原生表格，取不到则只用文本。"""
    import fitz
    doc = fitz.open(str(path))
    texts, rows = [], []
    for pno, page in enumerate(doc, start=1):
        texts.append(page.get_text("text"))
        try:
            for tbl in (page.find_tables() or []):
                data = tbl.extract() or []
                for ri, g in enumerate(data):
                    cells = ["" if c is None else _clean(c) for c in g]
                    if any(cells):
                        rows.append({"page": pno, "row": ri, "cells": cells, "raw": " | ".join(cells)})
        except Exception:
            pass
    return "\n".join(texts), rows, {"pages": len(doc)}


def read_csv(path: Path):
    rows, texts = [], []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for ri, row in enumerate(csv.reader(f), start=1):
            cells = [_clean(c) for c in row]
            if any(cells):
                rows.append({"row": ri, "cells": cells, "raw": " | ".join(cells)})
                texts.append(" | ".join(cells))
    return "\n".join(texts), rows, {}


def read_any(path: str | Path):
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".docx",):
        return (*read_docx(p), "docx")
    if ext in (".xlsx", ".xlsm"):
        return (*read_xlsx(p), "xlsx")
    if ext in (".pdf",):
        return (*read_pdf(p), "pdf")
    if ext in (".csv",):
        return (*read_csv(p), "csv")
    if ext in (".md", ".txt", ".markdown"):
        from .cli import read_document
        t, k = read_document(str(p))
        # markdown 表格也要读成原生 rows（不拍平、按 | 切分保列序）
        rows = []
        for li, line in enumerate((t or "").splitlines(), start=1):
            s = line.strip()
            if not s.startswith("|"):
                continue
            cells = [_clean(c) for c in s.strip("|").split("|")]
            if not any(cells) or all(re.fullmatch(r"[\s\-:—–]*", c) for c in cells):
                continue
            rows.append({"row": li, "cells": cells, "raw": s[:140]})
        return t, rows, {"md_table_rows": len(rows)}, k
    raise ValueError("不支持的格式：%s（支持 .md .txt .docx .xlsx .pdf .csv）" % ext)


# ---------------------------------------------------------------- 表格 → 事实
def facts_from_rows(rows):
    """从原生表格行提 (label, value, unit)。支持三列式与多列扫描式。"""
    out = []
    for r in rows:
        # 不依赖上游是否清洗：这里再过一次 _clean（幂等）
        cells = [_clean(c) for c in (r.get("cells") or [])]
        if len(cells) < 2:
            continue
        label = cells[0]
        if not label or re.fullmatch(r"[\s\-:—–]+", label):
            continue
        # 从第 2 列起找第一个纯数字单元格
        for i in range(1, len(cells)):
            v = _num(cells[i])
            if v is None:
                continue
            unit = ""
            if i + 1 < len(cells) and (re.fullmatch(_UNIT_RE, cells[i + 1] or "")
                                       or _UNIT_LOOSE.fullmatch(cells[i + 1] or "")):
                unit = cells[i + 1]
            elif re.fullmatch(_UNIT_RE, cells[i] or "") and i > 1:
                unit = cells[i]
            out.append({"label": label, "value": v, "unit": unit,
                        "form": "table", "where": r.get("raw", "")[:120]})
            break
    return out


def facts_from_text(text):
    """从叙述文本提「X 为/=/： Y 单位」（中文）+「X: Y unit」（英文/PDF 常见）。"""
    out = []
    # 英文/混合：Label: 1234 unit  /  Label 1234 unit
    en = re.compile(
        r"([A-Za-z][A-Za-z0-9 /_\-]{2,40}?)\s*(?::|\bis\b|\bof\b)?\s*(" + _NUM + r")\s*"
        r"(万元|亿元|元|㎡|m2|sqm|m3|m³|m|kW|kWh|kVA|W|persons?|staff|units?)?", re.I)
    for m in en.finditer(text or ""):
        label = _clean(m.group(1))
        if len(label) < 3 or label.lower() in ("page", "total"):
            continue
        out.append({"label": label, "value": _num(m.group(2)),
                    "unit": (m.group(3) or "").strip(), "form": "inline_en",
                    "where": text[max(0, m.start() - 15):m.end() + 10].replace("\n", " ")})
    pat = re.compile(
        r"([\u4e00-\u9fa5A-Za-z0-9·\-（）()/]{2,28}?)\s*(?:为|=|：|:)\s*\**(" + _NUM + r")\**\s*(" + _UNIT_RE + r")?"
    )
    for m in pat.finditer(text or ""):
        label = _clean(m.group(1))
        if len(label) < 2 or label.startswith(("#", ">", "|", "-")):
            continue
        out.append({"label": label, "value": _num(m.group(2)),
                    "unit": (m.group(3) or "").strip(), "form": "inline",
                    "where": (text[max(0, m.start() - 20):m.end() + 10]).replace("\n", " ")})
    return out


# ---------------------------------------------------------------- 主入口
def to_provided_facts(path: str | Path, *, as_of: str = "",
                      default_caliber: str = "客户提供") -> dict:
    text, rows, meta, kind = read_any(path)
    tf = facts_from_rows(rows)
    inf = facts_from_text(text)
    allf = tf + inf

    by_label: dict[str, list] = {}
    for f in allf:
        by_label.setdefault(ALIAS.get(f["label"], f["label"]), []).append(f)

    provided, conflicts, warnings = [], [], []
    for lab, items in by_label.items():
        vals = {str(i["value"]) for i in items}
        if len(vals) > 1:
            conflicts.append({"subject": lab, "values": sorted(vals), "status": "待审",
                              "reason": "同一名称出现多个值，不取其一",
                              "where": [i.get("where", "")[:80] for i in items]})
            continue
        it = items[0]
        v2, u2, note = _align_unit(it["value"], it["unit"])
        if not u2:
            warnings.append({"label": lab, "issue": "单位缺失", "where": it.get("where", "")[:80]})
        rec = {"label": lab, "value": v2, "unit": u2, "caliber": default_caliber,
               "as_of": as_of, "kind": "provided"}
        if note:
            rec["unit_conversion"] = note
        provided.append(rec)

    return {
        "provided_facts": provided,
        "conflicts": conflicts,
        "warnings": warnings,
        "stats": {"source_kind": kind, "chars": len(text or ""),
                  "native_rows": len(rows), "table_facts": len(tf), "inline_facts": len(inf),
                  "unique_labels": len(by_label), "provided": len(provided),
                  "conflicts": len(conflicts), "warnings": len(warnings),
                  "meta": meta},
    }

# ---------------------------------------------------------------- 自检（防正则回归）
# DF9 教训：去序号前缀的正则曾把 0.8 吃成 8，不报错不告警，只有回放冲突才暴露。
# 根因在代码，所以防线建在代码层——反例优先，assert 失败即 raise（退出码非 0）。
_CLEAN_CASES = [
    # —— 反例优先：这些**不能**被改写 ——
    ("0.8", "0.8"), ("1.15", "1.15"), ("0.857", "0.857"), ("1.229", "1.229"),
    ("0.5", "0.5"), ("0.55", "0.55"), ("0.75", "0.75"), ("0.6", "0.6"),
    ("3.4.2", "3.4.2"),                        # 条款号不能被吃成 4.2
    ("GB50016-2014", "GB50016-2014"),          # 标准号不能被吃
    ("建标191-2018", "建标191-2018"),
    ("DGJ08-107-2015", "DGJ08-107-2015"),
    ("科研用房", "科研用房"),                    # 普通中文名不动
    # —— 正例：这些**应该**被改写 ——
    ("（1）项目概况", "项目概况"), ("1、概况", "概况"), ("1. 项目概况", "项目概况"),
    ("├ 桩基工程", "桩基工程"), ("│ └ 土建工程", "土建工程"),
    ("30HP 机组", "30HP机组"),                  # 数字/英文与中文间空格该合
    ("**总投资**", "总投资"),
    ("总投资：", "总投资"),
]

_NUM_CASES = [
    ("1,056", 1056), ("18,900", 18900), ("0.8", 0.8), ("1.15", 1.15),
    ("90", 90), ("", None), ("abc", None),
]


def self_test(verbose: bool = False) -> bool:
    """反例优先的正则回归测试。失败即抛 AssertionError（退出码非 0）。

    覆盖 DF9（数字被吃）+ 三类同源陷阱（条款号、标准号、括号专名）。
    """
    fails = []
    for inp, want in _CLEAN_CASES:
        got = _clean(inp)
        if got != want:
            fails.append(("_clean", inp, got, want))
    for inp, want in _NUM_CASES:
        got = _num(inp)
        if want is None:
            if got is not None:
                fails.append(("_num", inp, got, want))
        elif got is None or abs(float(got) - float(want)) > 1e-9:
            fails.append(("_num", inp, got, want))
    # 表格行 / 句式 的端到端自检
    rows = [{"row": 1, "cells": ["30HP 机组台数", "14", "台"], "raw": "| 30HP 机组台数 | 14 | 台 |"},
            {"row": 2, "cells": ["公共服务配套用房综合平面利用系数", "0.8", "", ""], "raw": ""}]
    fs = facts_from_rows(rows)
    got = {f["label"]: f["value"] for f in fs}
    if got.get("30HP机组台数") != 14:
        fails.append(("facts_from_rows", "30HP机组台数", got.get("30HP机组台数"), 14))
    if abs(float(got.get("公共服务配套用房综合平面利用系数", 0)) - 0.8) > 1e-9:
        fails.append(("facts_from_rows", "系数", got.get("公共服务配套用房综合平面利用系数"), 0.8))

    if fails:
        msg = "\n".join("  [FAIL] %s(%r) → %r，期望 %r" % f for f in fails)
        raise AssertionError("doc_facts 自检失败（%d 项）：\n%s" % (len(fails), msg))
    if verbose:
        print("doc_facts 自检通过：_clean %d 例 / _num %d 例 / 表格行 2 例"
              % (len(_CLEAN_CASES), len(_NUM_CASES)))
    return True
