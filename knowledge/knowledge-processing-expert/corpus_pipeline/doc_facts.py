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
def _label_ok(label: str) -> bool:
    """label 合法性：必须是「名」不是「数」也不是算式。

    拒绝：
      - 纯数字 / 纯数字+单位（235 / 9,540）
      - 含 = + - × ÷ 的算式片段（9,540 + 320）
      - 注释标记开头（注：/ 说明：/ 合计：）
      - 长度 < 2
    """
    s = str(label or "").strip()
    if len(s) < 2:
        return False
    if re.fullmatch(r"[\d,\.\s%]+[A-Za-z㎡]{0,4}", s):
        return False
    if re.search(r"[=+×÷]|(?<!^)-\s*\d", s):
        return False
    if re.match(r"^(注|说明|合计|小计|备注|总计)[：: ]", s):
        return False
    # 至少要有一个中文或 2 个字母
    if not (re.search(r"[\u4e00-\u9fa5]", s) or re.search(r"[A-Za-z]{2,}", s)):
        return False
    return True


# 列名里的量词/语义 → 可作独立事实列的判据
_VALUE_COL_HINTS = ("人", "面积", "金额", "数量", "台数", "个数", "万元", "㎡", "比例",
                    "系数", "指标", "率", "容量", "负荷", "用量", "耗量")
# 纯描述列（不抽）
_DESC_COL_HINTS = ("名称", "说明", "备注", "用途", "编号", "序号", "备注")


def _multi_column_facts(rows, section_map=None):
    """表头感知的多列抽取（**全表扫描**，不只看前两行）。

    `| {子系统1} | 名称 | 85 | 320 |` → `{子系统1}·规划科研人员=85` + `{子系统1}·规划研究生...=320`

    ## 为什么

    原实现假设「rows[0] 是表头」，但工作簿/md 里有多张表，分中心表可能在几十行之后。
    只取前两行 → 复合表后续列全丢 → 下游报「缺输入」并去问用户（而数据其实已给）。

    ## 表头判据

    扫描每一行 i，若：
      - 该行 >= 3 列
      - 该行含 >= 1 个值列关键词（人/面积/金额/率/指标…），且非全描述列
      - 该行本身数字很少（不是数据行）
      - 下一行首列像标签（有内容、非纯数字）
    则把它当表头，收集后续连续数据行直到某行首列为空/合计/表头式。
    """
    import re as _re
    out = []
    if not rows:
        return out

    def _cells(r):
        return [_clean(c) for c in (r.get("cells") or [])] if isinstance(r, dict) \
               else [_clean(c) for c in (r if isinstance(r, list) else [])]

    def _value_cols(header):
        cols = []
        for i, h in enumerate(header):
            if i == 0 or not h:
                continue
            if any(d in h for d in _DESC_COL_HINTS):
                continue
            if any(v in h for v in _VALUE_COL_HINTS):
                cols.append(i)
        return cols

    n = len(rows)
    i = 0
    while i < n - 1:
        header = _cells(rows[i])
        if len(header) < 3:
            i += 1
            continue
        vc = _value_cols(header)
        # 表头不能是数据行：数字占比过高就跳过
        if not vc or sum(1 for c in header if _num(c) is not None) >= len(header) / 2:
            i += 1
            continue
        # 下一行首列必须像标签
        nxt = _cells(rows[i + 1])
        if not nxt or not nxt[0] or _num(nxt[0]) is not None:
            i += 1
            continue
        # 收集数据行
        j = i + 1
        consumed = 0
        while j < n:
            c = _cells(rows[j])
            if not c or not c[0] or len(c) <= max(vc):
                break
            head = c[0]
            if head.startswith("**合计") or head in ("合计", "小计", "总计"):
                j += 1
                continue
            if not _label_ok(head):
                break
            got = False
            for ci in vc:
                v = _num(c[ci])
                if v is None:
                    continue
                col = _re.sub(r"[（(].*?[）)]", "", header[ci]).strip()
                if not col:
                    continue
                out.append({"label": "%s·%s" % (head, col), "value": v, "unit": "",
                            "form": "table_multi",
                            "where": "| " + " | ".join(c[:4]) + " |",
                            "section": None})
                got = True
            if not got:
                break
            consumed += 1
            j += 1
        i = j if consumed else i + 1
    return out


def facts_from_rows(rows, section_map=None):
    """从原生表格行提 (label, value, unit)。支持三列式与多列扫描式。

    section_map: {row 号: 章节名}，给每条 fact 记章节归属（分片索引用）。
    """
    out = []
    for r in rows:
        # 不依赖上游是否清洗：这里再过一次 _clean（幂等）
        cells = [_clean(c) for c in (r.get("cells") or [])]
        # 注释/算式行不抽取（如「注：9,540 + 320 + 85 + 235 = 10,180」）
        if cells and not _label_ok(cells[0]):
            continue
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
                        "form": "table", "where": r.get("raw", "")[:120],
                        "section": (section_map or {}).get(r.get("row"))})
            break
    return out


def _line_sections(text):
    """返回 {line_no(1-based): section_name}，用 MD 标题行切分。"""
    m = {}
    cur = None
    for i, line in enumerate((text or "").splitlines(), start=1):
        s = line.strip()
        if s.startswith("#"):
            head = s.lstrip("#").strip()
            # 剥掉章节映射标注（如「一、项目基本信息　→ 骨架 **§1.1 项目概况**」）
            head = re.split(r"\s*→\s*骨架", head)[0]
            cur = _clean(head.strip())
        m[i] = cur
    return m


def _section_spans(text):
    """返回 [(start_offset, section_name)]，用于把 fact 归到所在章节。"""
    spans = []
    for m in re.finditer(r"^#{1,4}\s+(.+)$", text or "", re.M):
        head = re.split(r"\s*→\s*骨架", m.group(1))[0]
        spans.append((m.start(), _clean(head.strip())))
    return spans


def _section_at(spans, pos):
    cur = None
    for st, name in spans:
        if st <= pos:
            cur = name
        else:
            break
    return cur


def facts_from_text(text, want_section=True):
    """从叙述文本提「X 为/=/： Y 单位」（中文）+「X: Y unit」（英文/PDF 常见）。"""
    out = []
    spans = _section_spans(text) if want_section else []
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
                    "where": text[max(0, m.start() - 15):m.end() + 10].replace("\n", " "),
                    "section": _section_at(spans, m.start()) if want_section else None})
    pat = re.compile(
        r"([\u4e00-\u9fa5A-Za-z0-9·\-（）()/]{2,28}?)\s*(?:为|=|：|:)\s*\**(" + _NUM + r")\**\s*(" + _UNIT_RE + r")?"
    )
    for m in pat.finditer(text or ""):
        label = _clean(m.group(1))
        if len(label) < 2 or label.startswith(("#", ">", "|", "-")):
            continue
        out.append({"label": label, "value": _num(m.group(2)),
                    "unit": (m.group(3) or "").strip(), "form": "inline",
                    "where": (text[max(0, m.start() - 20):m.end() + 10]).replace("\n", " "),
                    "section": _section_at(spans, m.start()) if want_section else None})
    return out


# ---------------------------------------------------------------- 文本事实
# 旧实现只抽数字（facts_from_rows 找第一个数字单元格；facts_from_text 只匹配数字），
# 导致「项目名称/建设单位/建设地点/编制单位」等文本事实在抽取阶段就丢失，
# 下游误判为「客户未提供」并反向索取。下面三个分支专门补文本事实。
_TEXT_VALUE_SKIP = {"", "—", "-", "–", "见上文", "待计算", "待判定", "待补充", "待算",
                    "值", "数值", "单位", "说明", "备注", "无"}
_TEXT_LABEL_SKIP = {"项", "项目", "序号", "合计", "小计", "总计", "备注", "说明",
                    "指标", "内容", "名称", "事实位", "类别", "表头", "栏位"}
_TEXT_HDR_HINTS = ("名称", "依据", "方式", "来源", "地点", "时间", "编号", "类型",
                   "用途", "标准", "等级", "目标", "条款", "规范")
_TEXT_HDR_SKIP = ("序号", "说明", "备注", "单位")
# 元数据章节不是客户事实：事实位分类、章节映射、使用指引等
_META_SECTION_HINTS = ("章节映射", "导入后", "完整性自评", "事实位分类", "使用指引",
                       "规范派生", "纯客户输入", "纯推演", "需专业判断", "二维总表")
# markdown 残片 / 结构词，不是事实
_TEXT_LABEL_SKIP |= {"本文章节", "一句话", "注意", "用房类型", "读法", "说明"}
_NUM_WITH_UNIT = re.compile(r"^[\d,，.]+\s*[A-Za-z㎡m³%·/（）()一-龥]{0,16}$")


def _meta_section(sec) -> bool:
    s = str(sec or "")
    return any(h in s for h in _META_SECTION_HINTS)


def _looks_numeric_with_unit(v) -> bool:
    """「1,320 ㎡」「9,540万元」这类是数值事实的另一种写法，不重复当文本事实。"""
    s = str(v or "").strip()
    return bool(_NUM_WITH_UNIT.fullmatch(s)) and bool(re.search(r"\d", s))


def _is_unit_like(s: str) -> bool:
    s = str(s or "").strip()
    if not s:
        return False
    # 已知单位表优先
    if re.fullmatch(_UNIT_RE, s):
        return True
    # 宽松匹配只用于「含单位符号/斜杠/数字」的短串；
    # 纯中文短串（华东理工大学 / 上海同济工程咨询有限公司）是名称，不是单位。
    if re.search(r"[A-Za-z0-9%·²³/（）()]", s) and len(s) <= 12 and _UNIT_LOOSE.fullmatch(s):
        return True
    return False


def _text_clean(v) -> str:
    return _clean(v).replace("**", "").strip()


def _text_ok(v) -> bool:
    s = _text_clean(v)
    if not s or s in _TEXT_VALUE_SKIP:
        return False
    if _num(s) is not None or _looks_numeric_with_unit(s):
        return False
    if _is_unit_like(s):
        return False
    if s.startswith("**") or s.startswith("|"):
        return False
    if len(s) < 2 or len(s) > 100:
        return False
    return True


def facts_from_rows_text(rows, section_map=None):
    """从原生表格行抽文本事实（键值表 + 表头感知的文本属性列）。

    与 facts_from_rows 互补：后者只取数字，本函数只取非数字事实。
    """
    out = []
    rows = list(rows or [])

    def _cells(r):
        return [_clean(c) for c in (r.get("cells") or [])]

    # ① 表头感知的多列文本属性（如「名称」「依据」列）
    i = 0
    while i < len(rows) - 1:
        header = _cells(rows[i])
        if len(header) < 2:
            i += 1
            continue
        text_cols = [ci for ci, h in enumerate(header)
                     if ci > 0 and h and any(x in h for x in _TEXT_HDR_HINTS)
                     and not any(x in h for x in _TEXT_HDR_SKIP)]
        if not text_cols or sum(1 for c in header if _num(c) is not None) >= len(header) / 2:
            i += 1
            continue
        j = i + 1
        consumed = 0
        while j < len(rows):
            c = _cells(rows[j])
            if not c or not c[0] or len(c) <= max(text_cols):
                break
            head = c[0]
            if not _label_ok(head) or "`" in head:
                break
            if _meta_section((section_map or {}).get(rows[j].get("row"))):
                j += 1
                continue
            if head in ("合计", "小计", "总计") or head.startswith("**合计"):
                j += 1
                continue
            got = False
            for ci in text_cols:
                v = c[ci]
                if not _text_ok(v):
                    continue
                col = re.sub(r"[（(].*?[）)]", "", header[ci]).strip()
                if not col:
                    continue
                out.append({"label": "%s·%s" % (head, col), "value": _text_clean(v), "unit": "",
                            "form": "table_text_multi",
                            "where": rows[j].get("raw", "")[:120],
                            "section": (section_map or {}).get(rows[j].get("row"))})
                got = True
            if not got:
                break
            consumed += 1
            j += 1
        i = j if consumed else i + 1

    # ② 键值行：label | 文本值 [| 单位]
    for r in rows:
        cells = _cells(r)
        if len(cells) < 2:
            continue
        lab = cells[0]
        if not _label_ok(lab) or lab in _TEXT_LABEL_SKIP or "`" in lab:
            continue
        if _meta_section((section_map or {}).get(r.get("row"))):
            continue
        if len(cells) == 2:
            cand = cells[1]
        elif len(cells) == 3 and _is_unit_like(cells[2]):
            cand = cells[1]
        else:
            continue
        if not _text_ok(cand):
            continue
        out.append({"label": lab, "value": _text_clean(cand), "unit": "",
                    "form": "table_text_kv",
                    "where": r.get("raw", "")[:120],
                    "section": (section_map or {}).get(r.get("row"))})
    return out


def facts_from_text_values(text):
    """从叙述行抽「标签：文本值」（只取非数字值，避免与数字事实重复）。"""
    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith(("|", "#", ">", "```", "- `", "* ")):
            continue
        m = re.match(r"^\*{0,2}([一-龥A-Za-z0-9（）()·/\-]{2,24})\*{0,2}\s*[：:]\s*(\S.{0,80})$", s)
        if not m:
            continue
        lab, val = _clean(m.group(1)), _clean(m.group(2))
        if not _label_ok(lab) or lab in _TEXT_LABEL_SKIP or "`" in lab:
            continue
        if not _text_ok(val) or val == lab:
            continue
        out.append({"label": lab, "value": _text_clean(val), "unit": "",
                    "form": "inline_text", "where": s[:120], "section": None})
    return out


# ---------------------------------------------------------------- 主入口
def to_provided_facts(path: str | Path, *, as_of: str = "",
                      default_caliber: str = "客户提供") -> dict:
    text, rows, meta, kind = read_any(path)
    # 表格行 → 章节归属（MD/CSV 的 row 是文件行号；docx/xlsx/pdf 的 row 是表内行号，映射不到章节）
    _ls = _line_sections(text) if kind in ("md", "text", "txt", "markdown") else {}
    _sec_map = {r.get("row"): _ls.get(r.get("row")) for r in rows} if _ls else {}
    tf = facts_from_rows(rows, section_map=_sec_map)
    # 表头感知的多列抽取（复合表后续列不再丢）
    try:
        tf = tf + _multi_column_facts(rows, section_map=_sec_map)
    except Exception:
        pass
    inf = facts_from_text(text)
    # 文本事实：补「项目名称/建设单位/建设地点/编制单位」等非数字事实。
    text_tf = facts_from_rows_text(rows, section_map=_sec_map)
    text_inf = facts_from_text_values(text)
    allf = tf + inf

    # ★ 最外层兜底：label 不合法的一律丢弃（纯数字/算式/注释）
    dropped = [f for f in allf if not _label_ok(f.get("label"))]
    allf = [f for f in allf if _label_ok(f.get("label"))]
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
               "as_of": as_of, "kind": "provided",
               "section": it.get("section")}
        if note:
            rec["unit_conversion"] = note
        provided.append(rec)

    # 文本事实：同名以数值事实为准；label 仍走 ALIAS 归一。
    text_provided = []
    seen_text = set()
    for f in text_tf + text_inf:
        if not _label_ok(f.get("label")):
            continue
        lab = ALIAS.get(f["label"], f["label"])
        if lab in by_label or lab in seen_text:
            continue
        seen_text.add(lab)
        text_provided.append({
            "label": lab, "value": str(f["value"]), "unit": "",
            "caliber": default_caliber, "as_of": as_of,
            "kind": "provided_text", "form": f.get("form"),
            "section": f.get("section"), "where": f.get("where", "")[:120],
        })
    provided = provided + text_provided

    return {
        "provided_facts": provided,
        "conflicts": conflicts,
        "warnings": warnings,
        "stats": {"source_kind": kind, "chars": len(text or ""),
                  "native_rows": len(rows), "table_facts": len(tf), "inline_facts": len(inf),
                  "text_facts": len(text_provided),
                  "unique_labels": len(by_label), "provided": len(provided),
                  "dropped_bad_labels": len(dropped),
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
