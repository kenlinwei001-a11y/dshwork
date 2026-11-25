# -*- coding: utf-8 -*-
"""evo_template_all —— 为 119 节批量生成「含槽位、无项目值」的提示词模板。

## 用户问题

- 旧 `prompt-templates/` 只有 3 节；
- `提示词-还原-119节全量.md` 里 `{{槽位}}` 数为 0（全是已填值）；
- 写作专家团要的是「含本节点槽位的模板」，且**不许残留上财真值**。
- 旧去值只覆盖「数字 + 专名」，漏掉方位/四至/配套/资金来源/拆除对象/
  相邻建筑名等定性值；这些值同样不得跨项目复用，规则见
  `evo_devalue_rules.py`。

## 做法（确定性，零 LLM 猜值）

1. 按 119 节目录顺序建立**唯一锚点**：
   - 普通 `#` 标题；
   - `normalized.md` 里没有 `#` 的纯文本节标题（7.2.x / 7.3.x / 8.2.x / 8.3.x /
     9.2.x / 9.3.x / 10.5.x / 13.4.x）；
   - 5.1–5.4 的匿名标题 `子系统A–D` 通过形包 `raw_sections` 映射到真实标题；
   - 重复标题（1.4 vs 9.4「结论及建议」、10.1 vs 12.1「编制依据」）用
     文档顺序 + cursor 消歧，不再首匹配串段。
2. 用 `evo_source_section._blocks` 抽本节完整原文，**实测**段落数/表格数
   （形包旧统计只作对照，不作准）。
3. 用 `evo_prompt_template.devalue_prose/devalue_table` 把数值换成槽位；
   再做一层上财专名替换（校区/道路/机构/标准名），确保跨项目不复用。
4. 槽位来源类型：客户事实 CUSTOMER、标准 STANDARD、算式 COMPUTED、
   判断 JUDGMENT；从图谱和 `derivation_templates.yaml` 推断。
5. 定性节若槽位 < 3，用 `must_cover` 与本节标题派生**判断槽位**（JUDGMENT），
   保证每节 ≥3 个槽位；这些槽位不会伪造数值。
6. 输出 `prompt-templates-all/<节号>.md` + `_slots-<节号>.json` + `_index.json`。

## 硬校验

- 119/119 生成；
- 每节 slots ≥ 3；
- 上财真值 0 残留（13032/18319/11188/1171/618/2758/7793/3034 + 动态带单位值）；
- 段落数/表格数与 `normalized.md` 实测一致；
- 反例：故意注入 `13032`，校验器必须报错。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

# 允许直接以脚本运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.evo_source_section import _blocks  # type: ignore
from corpus_pipeline.evo_prompt_template import (  # type: ignore
    FALLBACK,
    KEEP_RE,
    NUM_RE,
    GraphIndex,
    SlotRegistry,
    devalue_prose,
    devalue_table,
    enrich_slots,
    parse_must_cover,
    parse_prompt_file,
    parse_rules,
    repair_table,
)
from corpus_pipeline.evo_slot_common import load_aliases  # type: ignore
from corpus_pipeline.evo_devalue_rules import (  # type: ignore
    apply_qualitative_devalue, find_qualitative_residue,
)


# ================================================================ 常量

SHUFE_VALUES = [
    "13032", "18319", "11188", "1171", "618", "2758", "7793", "3034",
]

PLACEHOLDER_MAP = {
    "{校区}": "中山北一路校区",
    "{建设单位}": "上海财经大学",
    "{项目名称}": "上海财经大学中山北一路校区大数据研究中心",
}

# 上财专名 → 槽位。长串优先；这些不是数值，但同样不能跨项目复用。
PHRASE_SLOTS: list[tuple[str, str, str]] = [
    ("上海财经大学中山北一路校区", "校区", "CUSTOMER"),
    ("中山北一路校区", "校区", "CUSTOMER"),
    ("上海财经大学", "建设单位", "CUSTOMER"),
    ("大数据研究中心", "项目名称", "CUSTOMER"),
    ("第五教学楼", "原有建筑", "CUSTOMER"),
    ("管理科学与量化信息研究中心", "科研机构1", "CUSTOMER"),
    ("理论计算机研究中心", "科研机构2", "CUSTOMER"),
    ("应用统计研究中心", "科研机构3", "CUSTOMER"),
    ("数据科研与统计研究院", "科研机构4", "CUSTOMER"),
    ("上海市虹口区", "行政区", "CUSTOMER"),
    ("虹口校区", "校区", "CUSTOMER"),
    ("虹口区", "行政区", "CUSTOMER"),
    ("中山北一路", "校区道路", "CUSTOMER"),
    ("上海市", "城市", "CUSTOMER"),
    ("上海", "城市", "CUSTOMER"),
    ("浦东新区", "周边行政区1", "CUSTOMER"),
    ("黄浦区", "周边行政区2", "CUSTOMER"),
    ("闸北区", "周边行政区3", "CUSTOMER"),
    ("杨浦区", "周边行政区4", "CUSTOMER"),
    ("杨浦", "周边行政区4", "CUSTOMER"),
    ("宝山区", "周边行政区5", "CUSTOMER"),
    ("赤峰路", "周边道路1", "CUSTOMER"),
    ("广秀路", "周边道路2", "CUSTOMER"),
    ("广灵一路", "周边道路3", "CUSTOMER"),
    ("广灵二路", "周边道路4", "CUSTOMER"),
    ("建标191-2018", "建筑面积指标标准", "STANDARD"),
    ("建标191", "建筑面积指标标准", "STANDARD"),
    ("DGJ08-107-2012", "节能设计标准", "STANDARD"),
    ("DGJ08-107-2015", "节能设计标准", "STANDARD"),
]

DEFAULT_CHECKS = [
    "借形不借值：可用上财结构，不得继承上财数值。",
    "缺值守卫：missing_customer 项写定性措辞并挂 gap，不许按 0 算。",
    "不许反算：不得由结论倒推中间量；中间量必须来自客户事实或算式。",
    "引用即绑定：每处数值写〔P-xxx〕，无节点 ID 的数值不得写入正文。",
    "冲突待审：冲突两侧都写，标「待审」，不裁决。",
    "派生值必带 formula + inputs：正文或脚注给出算式与输入节点。",
]

VALUE_WITH_UNIT_RE = re.compile(
    r"(?<![\d.])(\d[\d,]*(?:\.\d+)?)\s*"
    r"(万元|亿元|平方米|㎡|m2|m²|人|个月|kW|kWh|吨|立方米|m³|万千瓦时|"
    r"万m³|万立方米|%|年|月|日|层|米|mm|MPa|kVA|kV)"
)

YEAR_VERSION_RE = re.compile(r"(?:19|20)\d{2}\s*年?版?")
# 规则系数，不是项目值：保留原样
PERCENT_FORM_WHITELIST = {"0.35", "0.5"}
PERCENT_DECIMAL_RE = re.compile(r"(?<![\d.])(\d+\.\d+)\s*%")
STRUCT_NUM_RE = re.compile(
    r"(?:GB|DGJ|JGJ|DBJ|CJJ|CECS|ISO|IEC|EN|ASTM|BS|DIN|JIS|建标)"
    r"\s*/?\s*T?\s*[-]?\s*$",
    re.IGNORECASE,
)


# ================================================================ 基础工具

def writer_for(section: str) -> str:
    """§1-6 → engineering-writer；§7-13 → investment-writer（用户指定）。"""
    try:
        major = int(str(section).split(".")[0])
    except Exception:
        return "engineering-writer"
    return "investment-writer" if major >= 7 else "engineering-writer"


def _replace_placeholders(text: str) -> str:
    for k, v in PLACEHOLDER_MAP.items():
        text = text.replace(k, v)
    return text


def _load_yaml(path: Path) -> dict:
    import yaml  # type: ignore
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_forms(shape_pack: str | Path) -> dict:
    p = Path(shape_pack) / "templates" / "section-form.yaml"
    return (_load_yaml(p).get("forms") or {})


def _load_pack_rules(shape_pack: str | Path) -> dict:
    p = Path(shape_pack) / "functions" / "derivation_templates.yaml"
    return (_load_yaml(p).get("rules") or {})


def _clean_item(s: str, maxlen: int = 28) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    s = s.strip("。；;：:，,、-— ")
    s = s.rstrip("…").strip()
    s = s.strip("。；;：:，,、-— ")
    if len(s) > maxlen:
        s = s[:maxlen].rstrip("。；;：:，,、-— ")
    return s


def _slot_safe(name: str) -> str:
    name = re.sub(r"[{}|`]", "", str(name or "")).strip()
    name = re.sub(r"\s+", "", name)
    return name or "本节判断项"


# ================================================================ 节元数据

def section_meta(prompt_path: str | Path, shape_pack: str | Path) -> list[dict]:
    secs = parse_prompt_file(prompt_path)
    forms = _load_forms(shape_pack)
    out = []
    for s in secs:
        form = forms.get(s["title"]) or {}
        raw = [_replace_placeholders(x) for x in (form.get("raw_sections") or [])]
        out.append({
            "id": s["id"],
            "title": s["title"],
            "title_resolved": _replace_placeholders(s["title"]),
            "raw_sections": raw,
            "form": form,
            "blocks": s.get("blocks") or {},
            "header": s.get("header") or "",
        })
    return out


# ================================================================ 锚点（核心修复）

def build_anchors(md_text: str, sections: list[dict]) -> list[dict]:
    """按文档顺序给 119 节各分配唯一锚点。

    返回的每项含 pos（0-indexed 标题行）、end（0-indexed 下一节/下一个标题行）。
    """
    lines = md_text.splitlines()
    headpos: dict[str, list[tuple[int, int]]] = {}
    plainpos: dict[str, list[int]] = {}
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            headpos.setdefault(m.group(2).strip(), []).append((i, len(m.group(1))))
            continue
        s = line.strip()
        if s and not s.startswith(("|", "```", ">")):
            plainpos.setdefault(s, []).append(i)

    known_titles: set[str] = set()
    for sec in sections:
        known_titles.add(sec["title_resolved"])
        for r in sec["raw_sections"]:
            known_titles.add(r)

    # 边界：所有 markdown 标题 + 所有已知纯文本节标题
    boundary: set[int] = {i for i, line in enumerate(lines)
                          if re.match(r"^#{1,6}\s+", line)}
    for t in known_titles:
        boundary.update(plainpos.get(t, []))
    boundary_sorted = sorted(boundary)

    anchors: list[dict] = []
    cursor = 0
    for sec in sections:
        cands = [sec["title_resolved"]] + [r for r in sec["raw_sections"]
                                           if r and r != sec["title_resolved"]]
        found = None
        for cand in cands:
            opts = [(i, "heading", lv) for i, lv in headpos.get(cand, []) if i >= cursor]
            opts += [(i, "plain", 0) for i in plainpos.get(cand, []) if i >= cursor]
            if opts:
                opts.sort()
                found = (opts[0][0], opts[0][1], opts[0][2], cand)
                break
        out_of_order = False
        if found is None:
            for cand in cands:
                opts = [(i, "heading", lv) for i, lv in headpos.get(cand, [])]
                opts += [(i, "plain", 0) for i in plainpos.get(cand, [])]
                if opts:
                    opts.sort()
                    found = (opts[0][0], opts[0][1], opts[0][2], cand)
                    out_of_order = True
                    break
        if found is None:
            anchors.append({"id": sec["id"], "title": sec["title"],
                            "pos": None, "end": None, "mode": "missing",
                            "level": 0, "used_title": None,
                            "out_of_order": False})
            continue
        pos, mode, level, used = found
        cursor = pos + 1
        anchors.append({"id": sec["id"], "title": sec["title"],
                        "pos": pos, "end": None, "mode": mode,
                        "level": level, "used_title": used,
                        "out_of_order": out_of_order})

    # 边界 = 下一个 boundary 行（含下一个锚点）
    import bisect
    for a in anchors:
        if a["pos"] is None:
            continue
        j = bisect.bisect_right(boundary_sorted, a["pos"])
        a["end"] = boundary_sorted[j] if j < len(boundary_sorted) else len(lines)
        # 至少包含一行
        if a["end"] <= a["pos"]:
            a["end"] = min(len(lines), a["pos"] + 1)
    return anchors


def _line_range(lines: list[str], start: int, end: int) -> tuple[int, int]:
    """返回 1-indexed 的 (标题行, 最后非空内容行)。"""
    last = end - 1
    while last > start and not lines[last].strip():
        last -= 1
    return start + 1, last + 1


# ================================================================ 去值

def _map_outside_slots(text: str, fn) -> str:
    """只对 {{...}} 之外的文本做替换，避免把槽位名改成嵌套槽位。"""
    parts = re.split(r"(\{\{[^{}]+\}\})", str(text or ""))
    for i, part in enumerate(parts):
        if part.startswith("{{") and part.endswith("}}"):
            continue
        parts[i] = fn(part)
    return "".join(parts)


def _replace_phrases(text: str, *, registry: SlotRegistry, place: str) -> str:
    def proc(part: str) -> str:
        for phrase, slot, source_type in PHRASE_SLOTS:
            if phrase and phrase in part:
                registry.add(slot, place=place, label=slot, source_type=source_type)
                part = part.replace(phrase, "{{%s}}" % slot)
        return part

    return _map_outside_slots(text, proc)


def _percent_slot_name(prefix: str, occ: int) -> str:
    p = str(prefix or "")
    if "占比" in p:
        return "占比"
    if "比例" in p:
        return "比例"
    m = re.search(r"([一-龥]{2,8})率\s*$", p)
    if m:
        return m.group(1) + "率"
    return "百分比%d" % occ if occ > 1 else "百分比"


def _devalue_percentages(text: str, *, registry: SlotRegistry,
                         place: str) -> str:
    """把项目特有的小数百分比换成槽位；规则系数（0.35%/0.5%）保留。"""
    occ = [0]

    def proc(part: str) -> str:
        out = []
        last = 0
        for m in PERCENT_DECIMAL_RE.finditer(part):
            num = m.group(1)
            if num in PERCENT_FORM_WHITELIST:
                continue
            occ[0] += 1
            out.append(part[last:m.start()])
            prefix = part[max(0, m.start() - 24):m.start()]
            base = _percent_slot_name(prefix, occ[0])
            name, i = base, 2
            while name in registry.slots:
                name = "%s%d" % (base, i)
                i += 1
            registry.add(name, place=place, label=name, source_type="COMPUTED")
            out.append("{{%s}}%%" % name)
            last = m.end()
        if not out:
            return part
        out.append(part[last:])
        return "".join(out)

    return _map_outside_slots(text, proc)


STD_DOC_RE = re.compile(r"(第\s*)(\d+)(\s*号)")
YEAR_DOC_RE = re.compile(r"(〔\s*)(\d{4})(\s*〕\s*)(\d+)(\s*号)")


def _protect_standard_numbers(text: str, *, registry: SlotRegistry,
                              place: str) -> str:
    """先把「第16号」「〔2023〕304号」换成标准文号槽位，避免被拆成怪槽位。"""
    def next_name() -> str:
        i = 1
        while True:
            name = "标准文号" if i == 1 else "标准文号%d" % i
            if name not in registry.slots:
                return name
            i += 1

    def repl_year(m):
        name = next_name()
        registry.add(name, place=place, label="标准文号", source_type="STANDARD")
        return "{{%s}}" % name

    def repl_no(m):
        name = next_name()
        registry.add(name, place=place, label="标准文号", source_type="STANDARD")
        return m.group(1) + "{{%s}}" % name + m.group(3)

    text = YEAR_DOC_RE.sub(repl_year, text)
    text = STD_DOC_RE.sub(repl_no, text)
    return text


LIST_MARKER_RE = re.compile(
    r"(^|\n)([ \t]*(?:[-*+]|\d{1,2}[.)、．](?!\d)|"
    r"[（(]?\d{1,2}[）)]))\s*"
)


def _protect_list_markers(text: str) -> tuple[str, list[str]]:
    """保护「1.」「（1）」等列表编号，别被 devalue_prose 当成项目值。"""
    store: list[str] = []

    def repl(m):
        marker = m.group(2)
        # 恢复时补一个空格，避免「-项目名称」「1.室外」黏连
        if not marker.endswith(("）", ")")):
            marker += " "
        store.append(marker)
        return m.group(1) + chr(0xE300 + len(store) - 1)

    return LIST_MARKER_RE.sub(repl, text), store


def _restore_list_markers(text: str, store: list[str]) -> str:
    for i, v in enumerate(store):
        text = text.replace(chr(0xE300 + i), v)
    return text


GLUED_YEAR_RE = re.compile(
    r"((?:表|图)\s*\d+(?:[-—–]\d+)?)((?:19|20)\d{2})(?=[-—–年])"
)


def _devalue_glued_years(text: str, *, registry: SlotRegistry,
                         place: str) -> str:
    """「表13-22016-2018年」：表号后的年份也是值，别漏。"""
    def proc(part: str) -> str:
        def repl(m):
            registry.add("年份", place=place, label="年份",
                         source_type="CUSTOMER")
            return m.group(1) + "{{年份}}"

        return GLUED_YEAR_RE.sub(repl, part)

    return _map_outside_slots(text, proc)


def _devalue_paragraph(pa: str, *, sec_id: str, idx: int,
                       registry: SlotRegistry) -> str:
    place = "⓿b段%d" % (idx + 1)
    t, markers = _protect_list_markers(str(pa or ""))
    t = _protect_standard_numbers(t, registry=registry, place=place)
    t = devalue_prose(t, section=sec_id, para_idx=idx, registry=registry)
    t = _replace_phrases(t, registry=registry, place=place)
    t = _devalue_percentages(t, registry=registry, place=place)
    t = _devalue_glued_years(t, registry=registry, place=place)
    # 「东北部/东北侧」被方位规则拆成 {{方位}}+部/侧，合并回一个槽位
    t = re.sub(r"\{\{方位\}\}(?:部|侧|面|角)?", "{{方位}}", t)
    return _restore_list_markers(t, markers)


def _repair_headerless_table(table: dict, section_text: str) -> dict:
    """修复「无表头」表格：原文 ```table 第一行就是数据，被 _parse_table 当表头。

    判据（确定性）：第一列是纯整数，且 rows_data 第一行的第一列也是纯整数。
    例：§5.1 的 `| 1 | 科研人员 | 65 |` 被误当表头。
    """
    cols = list(table.get("cols") or [])
    rows = [list(r) for r in (table.get("rows_data") or [])]
    if len(cols) < 2 or not rows:
        return table
    if not re.fullmatch(r"\d+", str(cols[0]).strip()):
        return table
    if not re.fullmatch(r"\d+", str(rows[0][0]).strip() if rows[0] else ""):
        return table
    n = len(cols)
    if n == 3:
        third = ("规划人数" if "规划人数" in section_text
                 else "人数" if "人数" in section_text else "数量")
        new_cols = ["序号", "项目", third]
    else:
        new_cols = ["序号", "项目"] + ["数值%d" % i for i in range(1, n - 1)]
    return {"cols": new_cols, "rows_data": [cols] + rows,
            "nest": table.get("nest", 1)}


def _mask_slots(text: str) -> str:
    """把 {{...}} 屏蔽成等长占位符，避免二次扫描改坏槽位名。"""
    return re.sub(r"\{\{[^{}]+\}\}",
                  lambda m: chr(0xE400) * len(m.group(0)), text)


def _is_placeholder_cell(s: str) -> bool:
    s = str(s or "")
    return (not s.strip() or "{{" in s or "}}" in s
            or any(0xE000 <= ord(ch) <= 0xF8FF for ch in s))


def _row_label(cols: list, row: list) -> str:
    for ci, h in enumerate(cols):
        if any(k in str(h or "") for k in
               ("名称", "项目", "工程和费用", "指标名称", "用水部门",
                "用房功能", "系统", "设备")):
            v = str(row[ci] if ci < len(row) else "").strip()
            if v and not _is_placeholder_cell(v):
                return v
    for v in row:
        s = str(v or "").strip()
        if s and not NUM_RE.fullmatch(s) and not _is_placeholder_cell(s):
            return s
    return ""


def _devalue_table_leftovers(table: dict, *, registry: SlotRegistry,
                             place: str) -> dict:
    """兜底：devalue_table 会跳过「单位」等列，导致 1800人/288人 残留。"""
    cols = list(table.get("cols") or [])
    rows = [list(r) for r in (table.get("rows_data") or [])]
    last_label = ""
    for row in rows:
        label = _row_label(cols, row)
        if label:
            last_label = label
        else:
            label = last_label or "行"
        for ci, cell in enumerate(row):
            s = str(cell or "")
            if ci >= len(cols):
                continue
            hdr = str(cols[ci] or "")
            if re.fullmatch(r"序号", hdr.strip()):
                continue
            masked = _mask_slots(s)
            if not NUM_RE.search(masked) or KEEP_RE.search(masked):
                continue
            base = "%s·%s" % (label, hdr) if hdr else "%s·数值" % label
            pieces, last, n = [], 0, 0
            for m in NUM_RE.finditer(masked):
                n += 1
                name = _slot_safe(base if n == 1 else "%s%d" % (base, n))
                registry.add(name, place=place, label=base,
                             source_type="JUDGMENT")
                pieces.append(s[last:m.start()])
                pieces.append("{{%s}}" % name)
                last = m.end()
            pieces.append(s[last:])
            row[ci] = "".join(pieces)
    return {"cols": cols, "rows_data": rows, "nest": table.get("nest", 1)}


SPEC_COL_RE = re.compile(r"(规格型号|设备型号|产品型号|型号)")


SUBHEADER_RE = re.compile(
    r"^(?:小计|合计|其中[：:]?.*|基本支出|项目支出|其他|"
    r"总[计额]|数量|单价|合价)$"
)


def _merge_subheader_row(table: dict) -> dict:
    """复合表头：第 1 行是「小计/其中：…」子表头，并入列名，别当数据行。"""
    cols = list(table.get("cols") or [])
    rows = [list(r) for r in (table.get("rows_data") or [])]
    if not rows or len(cols) < 2:
        return table
    first = [str(c or "").strip() for c in rows[0]]
    nonempty = [c for c in first if c]
    if not nonempty or len(nonempty) < 2:
        return table
    if not all(SUBHEADER_RE.match(c) for c in nonempty):
        return table
    if not any(("小计" in c or "其中" in c) for c in nonempty):
        return table
    new_cols = []
    last_h = ""
    for i, h in enumerate(cols):
        sub = first[i] if i < len(first) else ""
        h = str(h or "").strip()
        if h:
            last_h = h
        if sub:
            prefix = h or last_h
            new_cols.append(("%s·%s" % (prefix, sub)) if prefix else sub)
        else:
            new_cols.append(h or (last_h + "·列%d" % (i + 1) if last_h
                                  else "列%d" % (i + 1)))
    return {"cols": new_cols, "rows_data": rows[1:],
            "nest": table.get("nest", 1)}


def _fill_down_row_labels(table: dict) -> dict:
    """合并单元格表：名称列为空的行继承上一行名称，便于命名槽位。"""
    cols = list(table.get("cols") or [])
    rows = [list(r) for r in (table.get("rows_data") or [])]
    name_idx = None
    for ci, h in enumerate(cols):
        if any(k in str(h or "") for k in ("名称", "项目", "工程和费用", "指标名称",
                                          "用水部门", "用房功能")):
            name_idx = ci
            break
    if name_idx is None:
        return table
    last = ""
    for row in rows:
        if name_idx < len(row):
            v = str(row[name_idx] or "").strip()
            if v and not _is_placeholder_cell(v):
                last = v
            elif last:
                row[name_idx] = last
    return {"cols": cols, "rows_data": rows, "nest": table.get("nest", 1)}


def _collapse_spec_columns(table: dict, *, registry: SlotRegistry,
                           place: str) -> tuple[dict, dict[str, str]]:
    """规格型号列整格一个槽位，别把 AAB1.5-... 拆成 8 个数字槽位。"""
    cols = list(table.get("cols") or [])
    rows = [list(r) for r in (table.get("rows_data") or [])]
    mapping: dict[str, str] = {}
    for row in rows:
        label = _row_label(cols, row)
        for ci, h in enumerate(cols):
            if ci >= len(row) or not SPEC_COL_RE.search(str(h or "")):
                continue
            cell = str(row[ci] or "")
            if not re.search(r"\d", cell) or NUM_RE.fullmatch(cell.strip()):
                continue
            base = _slot_safe("%s·%s" % (label, h)) if len(label) <= 12 else "规格型号"
            base = base or "规格型号"
            name, i = base, 2
            while name in registry.slots:
                name = "%s%d" % (base, i)
                i += 1
            registry.add(name, place=place, label=base, source_type="CUSTOMER")
            token = chr(0xE500 + len(mapping))
            mapping[token] = name
            row[ci] = token
    return {"cols": cols, "rows_data": rows, "nest": table.get("nest", 1)}, mapping


def _devalue_table(table: dict, *, sec_id: str, idx: int,
                   registry: SlotRegistry) -> dict:
    # 只调用一次：devalue_table 会向 registry 注册槽位，重复调用会重复登记
    place = "⓿b表%d" % idx
    table = _merge_subheader_row(table)
    table = _fill_down_row_labels(table)
    table, spec_map = _collapse_spec_columns(table, registry=registry, place=place)
    fixed = []
    for row in devalue_table(table.get("cols") or [], table.get("rows_data") or [],
                             sec_id=sec_id, table_idx=idx, registry=registry):
        fixed.append([
            _devalue_percentages(
                _replace_phrases(str(c or ""), registry=registry, place=place),
                registry=registry, place=place)
            for c in row
        ])
    fixed = _devalue_table_leftovers(
        {"cols": table.get("cols") or [], "rows_data": fixed,
         "nest": table.get("nest", 1)},
        registry=registry, place=place)
    for row in fixed.get("rows_data") or []:
        for ci, cell in enumerate(row):
            s = str(cell or "")
            for token, name in spec_map.items():
                if token in s:
                    s = s.replace(token, "{{%s}}" % name)
            row[ci] = s
    fixed = _uniquify_table_slots(fixed, registry=registry, place=place)
    return fixed


def _uniquify_table_slots(table: dict, *, registry: SlotRegistry,
                          place: str) -> dict:
    """同一张表里重复的「行名·列名」按出现顺序加序号，避免填槽串值。"""
    rows = [list(r) for r in (table.get("rows_data") or [])]
    seen: dict[str, int] = {}
    slot_re = re.compile(r"\{\{([^{}]+)\}\}")
    for row in rows:
        for ci, cell in enumerate(row):
            s = str(cell or "")
            if "{{" not in s:
                continue

            def repl(m):
                name = m.group(1)
                seen[name] = seen.get(name, 0) + 1
                if seen[name] == 1:
                    return m.group(0)
                new = "%s%d" % (name, seen[name])
                old = registry.slots.get(name)
                registry.add(new, place=place,
                             label=(old.label if old else name),
                             source_type=(old.source_type if old else "JUDGMENT"),
                             unit=(old.unit if old else ""))
                return "{{%s}}" % new

            row[ci] = slot_re.sub(repl, s)
    return {"cols": table.get("cols") or [], "rows_data": rows,
            "nest": table.get("nest", 1)}


# ================================================================ 槽位名清洗

POLLUTED_UNIT_RE = re.compile(
    r"\d\s*(?:人|名|米|毫米|cm|mm|kW|kWh|吨|m3|m³|m2|m²|万元|亿元|"
    r"平方米|㎡|年|月|日|层|度|MPa|L|kVA|kV|m(?![\w]))"
)


def _slot_is_polluted(name: str, slot, originals: list[str] | None = None) -> bool:
    """槽位名里混进了项目数值/长句 → 必须改名。

    只看槽位名本身，不用原文反查：`周边行政区4` / `资金来源1` 的尾部数字
    是槽位序号，不是项目值；用原文反查会因原文别处的「4米」误伤。
    """
    if "{" in name or "}" in name:
        return True
    if any(0xE000 <= ord(ch) <= 0xF8FF for ch in name):
        return True
    if not re.search(r"\d", name):
        return False
    if len(name) > 24:
        return True
    if POLLUTED_UNIT_RE.search(name):
        return True
    if re.search(r"[（(，,、=]", name):
        return True
    # 首尾虚词/半截话 → 名字不完整，清洗掉
    if re.match(r"^(?:的|为|是|有|约|达|共|其中|按|在)", name):
        return True
    if re.search(r"(?:大致在|不低于|不小于|不超过|约为|为|是|在)$", name):
        return True
    return False


def _clean_slot_base(name: str, slot) -> str:
    col = str(getattr(slot, "col", "") or "").strip()
    if col and not re.search(r"\d", col) and col not in ("序号", "单位"):
        return _slot_safe(col)
    prefix = re.split(r"\d", str(name or ""))[0]
    prefix = re.sub(r"^(?:的|为|是|有|约|达|共|其中|按|在)", "", prefix)
    prefix = re.sub(r"(?:大致在|不低于|不小于|不超过|约为|为|是|在)$", "", prefix)
    prefix = re.sub(r"[（(，,、=：:·\s_\-]+$", "", prefix)
    return _slot_safe(prefix) if len(prefix) >= 2 else ""


def _rename_slot(registry: SlotRegistry, old: str, new: str) -> None:
    s = registry.slots.pop(old)
    s.name = new
    if not s.label or _slot_is_polluted(str(s.label or ""), s):
        s.label = new
    registry.slots[new] = s
    registry.order = [new if x == old else x for x in registry.order]


def _sanitize_slots(registry: SlotRegistry, texts: list[str],
                    originals: list[str]) -> list[str]:
    mapping: dict[str, str] = {}
    used = set(registry.slots)
    for name in list(registry.order):
        s = registry.slots[name]
        if not _slot_is_polluted(name, s, originals):
            continue
        base = _clean_slot_base(name, s) or "本节值"
        cand, i = base, 2
        while cand in used:
            cand = "%s%d" % (base, i)
            i += 1
        mapping[name] = cand
        used.add(cand)
    for old, new in mapping.items():
        _rename_slot(registry, old, new)
    for i, t in enumerate(texts):
        for old, new in mapping.items():
            t = t.replace("{{%s}}" % old, "{{%s}}" % new)
        texts[i] = t
    return texts


# ================================================================ 槽位补足

def _ensure_min_slots(registry: SlotRegistry, *, section: dict,
                      must_cover: list[str]) -> None:
    """定性节补判断槽位，保证每节至少 3 个槽位；不伪造数值。"""
    if len(registry.order) >= 3:
        return
    candidates: list[str] = []
    for item in must_cover:
        raw = _clean_item(item, 40)
        # 只把「名词性短项」当判断槽位；完整句子会产出怪槽位（如 9.4）
        if not raw or len(raw) < 2 or re.fullmatch(r"[\d.]+", raw):
            continue
        if len(raw) > 14 or re.search(r"[。；;]", raw):
            continue
        candidates.append(_clean_item(raw, 14))
    title = _clean_item(section.get("title_resolved") or section.get("title") or "", 18)
    if title:
        candidates += ["%s·方案要点" % title, "%s·项目适配" % title, "%s·结论" % title]
    candidates += ["项目现状判断", "方案选择判断", "结论与建议判断"]
    for c in candidates:
        if len(registry.order) >= 3:
            break
        name = _slot_safe(c)
        if name in registry.slots:
            continue
        s = registry.add(name, place="判断项（无原文锚点）", label=name,
                         source_type="JUDGMENT")
        s.note = "由写作成员按项目实际判断；不得照抄上财结论"
        s.synthetic = True  # type: ignore[attr-defined]


# ================================================================ 算式 / 覆盖 / 证据

def _deps_from_expr(expr: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\{([^{}]+)\}", str(expr or ""))))


def collect_formulas(sec_id: str, blocks: dict, pack_rules: dict,
                     slot_names: Iterable[str] | None = None) -> list[dict]:
    """本节算式。只取本节 section 命中的形包规则，避免把别节规则串进来。"""
    out: list[dict] = []
    for r in parse_rules(blocks.get("②") or ""):
        expr = str(r.get("expr") or "")
        out.append({
            "rule_id": r.get("rule") or "",
            "target": r.get("target") or "",
            "expr": expr,
            "deps": list(dict.fromkeys(_deps_from_expr(expr) +
                                       list(r.get("deps_required") or []))),
            "source": "prompt",
        })
    for rid, rv in pack_rules.items():
        if str(rv.get("section") or "") != str(sec_id):
            continue
        expr = str(rv.get("expr") or "")
        out.append({
            "rule_id": rid, "target": str(rv.get("target") or ""), "expr": expr,
            "deps": list(dict.fromkeys(_deps_from_expr(expr) +
                                       list(rv.get("deps_required") or []))),
            "source": "derivation_templates",
        })
    # 按 (target, expr) 去重；同式优先保留有 rule_id 的那条
    by_key: dict[tuple[str, str], dict] = {}
    for r in out:
        k = (r["target"], r["expr"])
        if not r["expr"]:
            continue
        if k in by_key and not by_key[k]["rule_id"] and r["rule_id"]:
            by_key[k] = r
        elif k not in by_key:
            by_key[k] = r
    return list(by_key.values())


def _clean_must_text(s: str) -> str:
    """覆盖清单也要去值：旧提示词 ⑧ 里常有 {原值}/{校区}/上财专名。"""
    t = str(s or "")
    t = (t.replace("{原值}", "〔数值〕")
          .replace("{校区}", "校区")
          .replace("{建设单位}", "建设单位")
          .replace("{项目名称}", "项目名称")
          .replace("上财委会", "学校党委会")
          .replace("上财", "学校"))
    # 去列表编号：{原值}. / （{原值}） / 1. / （1）
    t = re.sub(r"^\s*(?:〔数值〕\s*[.．、)）]?|"
               r"[（(]\s*〔数值〕\s*[）)]|\d{1,2}[.)、．](?!\d)|"
               r"[（(]?\d{1,2}[）)])\s*[.．、)）]?\s*", "", t)
    for phrase, slot, _ in PHRASE_SLOTS:
        if phrase:
            t = t.replace(phrase, slot)
    t = t.replace("原原有建筑", "原有建筑").replace("原有原有", "原有")
    # 方位/四至里的项目专名
    t = re.sub(r"(?:东北|东南|西北|西南|东部|西部|南部|北部|"
               r"东侧|西侧|南侧|北侧)", "〔方位〕", t)
    # 数字（含带单位）统一成占位提示
    t = VALUE_WITH_UNIT_RE.sub("〔数值〕", t)
    t = re.sub(r"\d[\d,]*(?:\.\d+)?", "〔数值〕", t)
    # 连续占位符折叠
    t = re.sub(r"(?:〔数值〕)(?:[、，,和及~～\-—\s]*〔数值〕)+", "〔数值〕", t)
    t = re.sub(r"[ \t]+", " ", t).strip()
    # 四至/配套长句在模板里没有保留价值，收成一条可检查的覆盖项
    if ("毗邻" in t or "四至" in t
            or ("周边道路" in t and len(t) > 24)):
        return "场地四至与周边条件"
    if ("配套" in t and len(t) > 24 and "齐全" in t):
        return "周边配套条件"
    return t[:120]


def collect_must_cover(blocks: dict, form: dict,
                       paras: list[str], tables: list[dict]) -> list[str]:
    items = [x for x in parse_must_cover(blocks.get("⑧") or "") if str(x).strip()]
    if items:
        out = []
        for x in items:
            c = _clean_must_text(x)
            if c and c not in out:
                out.append(c)
        return out
    # 兜底：从段落首句/小标题派生
    out = []
    for p in paras:
        c = _clean_item(p, 24)
        if c:
            out.append(c)
    if not out:
        out = ["按本节原文 %d 段与 %d 张表逐项覆盖，不漏段、不漏表。"
               % (len(paras), len(tables))]
    return out[:20]


def collect_evidence(blocks: dict) -> list[str]:
    raw = str(blocks.get("③") or "")
    raw = re.sub(r"^###\s*③[^\n]*\n?", "", raw).strip()
    lines = [x.strip() for x in raw.splitlines() if x.strip()]
    return lines or ["E1 必须注明提供方与日期；E2 必须带标准号+条款号；"
                     "无证据的数值不得写入正文。"]


# ================================================================ 节事实（图谱）

def _section_label_id(label: str) -> str | None:
    m = re.match(r"^§?\s*(\d+(?:\.\d+)*)", str(label or ""))
    return m.group(1) if m else None


def collect_graph_facts(graph_data: dict, sec_id: str,
                        slot_names: Iterable[str]) -> list[dict]:
    names = {str(n) for n in slot_names}
    out = []
    for f in (graph_data.get("items") or {}).get("facts") or []:
        subj = str(f.get("subject") or "")
        label_sec = _section_label_id(f.get("section") or "")
        if subj in names or label_sec == str(sec_id):
            out.append(f)
    # 去重，保留稳定顺序
    seen = set()
    deduped = []
    for f in out:
        fid = f.get("id")
        if fid in seen:
            continue
        seen.add(fid)
        deduped.append(f)
    return deduped


# ================================================================ 模板构建

def build_template(section: str, *, project_dir: str | Path,
                   source_md: str | Path, shape_pack: str | Path,
                   graph: str | Path | dict) -> dict:
    """为一节生成模板数据（dict），同时可渲染为 markdown。

    参数:
      section: 节号，如 "1.1" / "13.3"
      project_dir: 项目根目录（用于解析默认路径与 relative paths）
      source_md: normalized.md 路径，或 markdown 文本
      shape_pack: 形包目录
      graph: merged/clean 图谱路径，或已加载 dict
    """
    project_dir = Path(project_dir)
    shape_pack = Path(shape_pack)
    raw_source = str(source_md)
    # source_md 可能是路径，也可能是整篇 markdown 文本；
    # 文本长度可能超过文件系统上限，不能直接 Path(...).exists()。
    if "\n" not in raw_source and len(raw_source) < 4096:
        src_path = Path(raw_source)
        if src_path.exists() and src_path.is_file():
            md_text = src_path.read_text(encoding="utf-8")
            src_path_str = str(src_path)
        else:
            md_text = raw_source
            src_path_str = ""
    else:
        md_text = raw_source
        src_path_str = ""

    sections = section_meta(project_dir / "提示词-还原-119节全量.md", shape_pack) \
        if not Path("提示词-还原-119节全量.md").is_absolute() else []
    # 允许调用方只给单节：从项目目录的 119 节目录补齐元数据
    if not sections:
        prompt_path = project_dir / "提示词-还原-119节全量.md"
        sections = section_meta(prompt_path, shape_pack)
    meta = next((s for s in sections if s["id"] == str(section)), None)
    if meta is None:
        raise KeyError("未知节号：%s（应从 119 节目录中取）" % section)

    anchors = build_anchors(md_text, sections)
    anchor = next((a for a in anchors if a["id"] == str(section)), None)
    if anchor is None or anchor["pos"] is None:
        raise ValueError("本节在 normalized.md 中找不到锚点：%s %s"
                         % (section, meta["title"]))

    lines = md_text.splitlines()
    body_lines = lines[anchor["pos"] + 1:anchor["end"]]
    blocks = _blocks(body_lines)
    paras = list(blocks.get("paras") or [])
    raw_tables = list(blocks.get("tables") or [])
    line_start, line_end = _line_range(lines, anchor["pos"], anchor["end"])

    # 图谱
    graph_data = graph if isinstance(graph, dict) else json.loads(
        Path(graph).read_text(encoding="utf-8"))
    aliases_path = shape_pack / "ontology" / "fact-aliases.yaml"
    rules_path = shape_pack / "functions" / "derivation_templates.yaml"
    graph_index = GraphIndex(graph_data, aliases_path=str(aliases_path),
                             rules_path=str(rules_path))
    _, alias_to_canon = load_aliases(str(aliases_path))
    pack_rules = _load_pack_rules(shape_pack)

    # 槽位
    registry = SlotRegistry(alias_to_canon)
    dv_paras = [_devalue_paragraph(p, sec_id=str(section), idx=i,
                                   registry=registry)
                for i, p in enumerate(paras)]
    form_cols = []
    # 形包 guidance 里的列（若有）用于修表
    for line in str((meta["form"] or {}).get("guidance") or "").splitlines():
        pass
    section_text = "\n".join(paras)
    tables = []
    for i, tb in enumerate(raw_tables, 1):
        fixed = repair_table(str(section), meta["title"], tb,
                            form_cols[i - 1] if i - 1 < len(form_cols) else None)
        fixed = _repair_headerless_table(fixed, section_text)
        tables.append(fixed)
    dv_tables = [_devalue_table(tb, sec_id=str(section), idx=i, registry=registry)
                 for i, tb in enumerate(tables, 1)]

    # 清洗被 devalue 带进槽位名的项目值/长句（如 {{包括硕士生6151人…}}）
    originals = list(paras)
    for tb in tables:
        for row in tb.get("rows_data") or []:
            originals += [str(c or "") for c in row]
    texts = list(dv_paras)
    for tb in dv_tables:
        for row in tb.get("rows_data") or []:
            texts += [str(c or "") for c in row]
    texts = _sanitize_slots(registry, texts, originals)
    dv_paras = texts[:len(dv_paras)]
    k = len(dv_paras)
    for tb in dv_tables:
        for row in tb.get("rows_data") or []:
            for ci in range(len(row)):
                row[ci] = texts[k]
                k += 1

    # 来源类型/单位
    must_cover = collect_must_cover(meta["blocks"], meta["form"], paras, tables)
    # 「必须覆盖」也是模板正文，不能残留上财定性值/专名。
    must_cover = [
        _replace_phrases(
            apply_qualitative_devalue(
                x, registry=registry, place="③ 必须覆盖",
                section=str(section), sentence_level=False),
            registry=registry, place="③ 必须覆盖")
        for x in must_cover
    ]
    formulas = collect_formulas(str(section), meta["blocks"], pack_rules)
    # 算式目标/依赖也必须是槽位，否则 ② 引用了 ① 里不存在的节点
    for f in formulas:
        for dep in f.get("deps") or []:
            registry.add(dep, place="② 算式依赖", label=dep,
                         source_type="JUDGMENT")
        if f.get("target"):
            registry.add(f["target"], place="② 算式目标", label=f["target"],
                         source_type="COMPUTED")
    enrich_slots(registry, graph_index, list(pack_rules.values()), alias_to_canon)
    _ensure_min_slots(registry, section=meta, must_cover=must_cover)

    slots = []
    for name in registry.order:
        s = registry.slots[name]
        d = s.as_dict()
        d["meaning"] = s.label or name
        d["fallback"] = getattr(s, "note", "") or FALLBACK.get(s.source_type, "")
        d["synthetic"] = bool(getattr(s, "synthetic", False))
        slots.append(d)

    evidence = collect_evidence(meta["blocks"])

    para_chars = len(re.sub(r"\s", "", "\n".join(paras)))
    table_chars = sum(len(re.sub(r"\s", "", " ".join(
        " ".join(str(c) for c in row) for row in (tb.get("rows_data") or []))))
        for tb in tables)
    total_chars = para_chars + table_chars
    form_paras = (meta["form"] or {}).get("paras")
    form_tables = len((meta["form"] or {}).get("tables") or [])
    style = str((meta["form"] or {}).get("style") or
                ("table_dominant" if tables and not paras else
                 "prose_dominant" if paras else "mixed"))

    shape = {
        "paras": len(paras),
        "tables": len(tables),
        "style": style,
        "para_chars": para_chars,
        "table_chars": table_chars,
        "total_chars": total_chars,
        "word_budget": {"min": total_chars, "max": max(total_chars, total_chars * 2)},
        "source_outline": must_cover,
        "form_stats": {
            "paras": form_paras,
            "tables": form_tables,
            "para_chars": (meta["form"] or {}).get("para_chars"),
            "stale": (form_paras is not None and form_paras != len(paras)) or
                     (form_tables != len(tables)),
        },
        # 用去值/合并子表头后的列，确保「不得减少列」与模板表头一致
        "table_columns": [list(tb.get("cols") or []) for tb in dv_tables],
    }

    checks = list(DEFAULT_CHECKS)
    checks.append("形态实测：本节必须 %d 段、%d 张表（normalized.md 实测；"
                  "形包旧统计 %s/%s）。" % (len(paras), len(tables),
                                            form_paras, form_tables))
    if tables:
        checks.append("表格列不得减少：%s。" % "；".join(
            "表%d：%s" % (i, "/".join(tb.get("cols") or []))
            for i, tb in enumerate(tables, 1)))
    if any(x["synthetic"] for x in slots):
        checks.append("判断槽位按项目实际写，不得照抄上财结论。")
    # 注意：校验标准里不能写出禁止出现的具体数值，否则模板自身会被残留扫描命中。
    checks.append("上财真值与上财专名不得残留；禁用值清单见 "
                  "`prompt-templates-all/_validation.json` 的 `forbidden_values`。")

    title_resolved = meta["title_resolved"]
    # 5.1–5.4 的目录标题是匿名「子系统A–D」，上财真实标题在 anchor.used_title
    source_title = anchor.get("used_title") or title_resolved
    project_title = _project_title(str(section), title_resolved, graph_data)
    return {
        "section": str(section),
        "title": project_title,
        "source_title": source_title,
        # 模板抬头用「带占位符的原目录标题」：3.2.3/14.3 不能把上财校区名写进模板
        "source_title_display": meta["title"],
        "writer_role": writer_for(str(section)),
        "shape": shape,
        "source_skeleton": _render_skeleton(dv_paras, dv_tables),
        "slots": slots,
        "formulas": formulas,
        "must_cover": must_cover,
        "evidence_requirement": evidence,
        "checks": checks,
        "source_anchor": {
            "file": src_path_str or "normalized.md",
            "line_start": line_start,
            "line_end": line_end,
            "mode": anchor["mode"],
            "used_title": anchor["used_title"],
            "out_of_order": anchor["out_of_order"],
        },
        "graph_facts": collect_graph_facts(graph_data, str(section),
                                           [x["name"] for x in slots]),
        # 原始本节文本（含表格单元格），用于「上财值残留」动态校验；
        # 不能用去值后的文本，否则已经漏掉的值无法被发现。
        "source_text": "\n".join(originals),
        "_dv_paras": dv_paras,
        "_dv_tables": dv_tables,
    }


def _project_title(section: str, title: str, graph_data: dict) -> str:
    """新项目节标题：5.1–5.4 用图谱里的新子系统名，其余替换占位符。"""
    mapping = {"5.1": "子系统1名称", "5.2": "子系统2名称",
               "5.3": "子系统3名称", "5.4": "子系统4名称"}
    if section in mapping:
        for f in (graph_data.get("items") or {}).get("facts") or []:
            if f.get("subject") == mapping[section] and f.get("value"):
                return str(f["value"])
    return (title.replace("{校区}", "徐汇校区")
                 .replace("{建设单位}", "华东理工大学")
                 .replace("{项目名称}", "华东理工大学人工智能与智能制造研究院"))


LIST_PREFIX_RE = re.compile(
    r"^\s*(?:[-*+]|\d{1,2}[.)、．](?!\d)|[（(]?\d{1,2}[）)])"
)


def _render_skeleton(paras: list[str], tables: list[dict]) -> str:
    L = []
    has_lists = any(LIST_PREFIX_RE.match(p) for p in paras)
    for i, p in enumerate(paras, 1):
        # 原文已有列表编号/项目符号就保留，避免「1. 1.室外…」双重编号
        if LIST_PREFIX_RE.match(p):
            L.append(p)
        elif has_lists:
            L.append("- %s" % p)
        else:
            L.append("%d. %s" % (i, p))
    if paras and tables:
        L.append("")
    for ti, tb in enumerate(tables, 1):
        cols = tb.get("cols") or []
        L.append("**表 %d（%d 列 × %d 行）**" % (ti, len(cols),
                                              len(tb.get("rows_data") or [])))
        L.append("")
        L.append("| " + " | ".join(str(c) for c in cols) + " |")
        L.append("|" + "---|" * len(cols))
        for row in tb.get("rows_data") or []:
            L.append("| " + " | ".join(str(c) for c in row) + " |")
        L.append("")
    return "\n".join(L).strip()


# ================================================================ 渲染 markdown

def render_template_markdown(t: dict) -> str:
    s = t["shape"]
    L: list[str] = []
    L.append("# 提示词模板 · §%s %s" % (t["section"], t["title"]))
    L.append("")
    L.append("> 模板 ID：T-%s ｜ 写作成员：`%s` ｜ 槽位：%d 个  "
             % (t["section"], t["writer_role"], len(t["slots"])))
    L.append("> 上财对应节：§%s「%s」 ｜ 原文锚点：`%s` 第 %d–%d 行"
             % (t["section"], t.get("source_title_display") or t["source_title"],
                t["source_anchor"]["file"],
                t["source_anchor"]["line_start"], t["source_anchor"]["line_end"]))
    L.append("> 本文件**不含任何项目值**；所有 `{{槽位}}` 由写作成员按真实输入填写。")
    L.append("")
    L.append("## ⓿ 本节形态（normalized.md 实测）")
    L.append("")
    L.append("- **文体**：%s" % s["style"])
    L.append("- **段落**：%d 段（%d 字）" % (s["paras"], s["para_chars"]))
    L.append("- **表格**：%d 张（%d 字）" % (s["tables"], s["table_chars"]))
    L.append("- **目标字数**：%d – %d 字（原文实测 %d 字，按 2 倍上限）"
             % (s["word_budget"]["min"], s["word_budget"]["max"], s["total_chars"]))
    L.append("- **形包旧统计**：%s 段 / %s 张表%s"
             % (s["form_stats"].get("paras"), s["form_stats"].get("tables"),
                "（**已废弃，以实测为准**）" if s["form_stats"].get("stale") else ""))
    if s["table_columns"]:
        L.append("- **表格列（不得减少）**：")
        for i, cols in enumerate(s["table_columns"], 1):
            L.append("  - 表 %d：%s" % (i, " ｜ ".join(cols)))
    L.append("")
    L.append("**形态纪律**：")
    L.append("")
    L.append("1. **结构照原文**：原文 %d 段就写 %d 段，原文 %d 张表就出 %d 张表。"
             % (s["paras"], s["paras"], s["tables"], s["tables"]))
    L.append("2. **详略照原文**：原文某段只有一句话，不要扩写成三段。")
    L.append("3. **措辞照原文**：沿用原文句式与小标题前缀。")
    L.append("4. **只换值不换形**：把 `{{槽位}}` 换成新项目数据，结构与逻辑不动。")
    L.append("5. **不得拆表/减列**：表列、行层级、备注都要保留。")
    L.append("")
    L.append("## ⓿b 本节骨架（去值后，含槽位）")
    L.append("")
    L.append(t["source_skeleton"] or "_（本节无正文段落/表格；按 ③ 覆盖项写作。）_")
    L.append("")
    L.append("## ① 槽位清单（%d 个）" % len(t["slots"]))
    L.append("")
    L.append("| 槽位 | 含义 | 来源类型 | 单位 | 出现位置 | 填不上时 |")
    L.append("|---|---|---|---|---|---|")
    for x in t["slots"]:
        L.append("| `{{%s}}` | %s | %s | %s | %s | %s |" % (
            x["name"], x.get("meaning") or x["name"], x.get("source_type"),
            x.get("unit") or "—", "、".join(x.get("places") or []) or "判断项",
            x.get("fallback") or "—"))
    L.append("")
    synth = [x for x in t["slots"] if x.get("synthetic")]
    if synth:
        L.append("> 判断槽位 %d 个（无原文锚点，需写作成员按项目实际判断）：%s"
                 % (len(synth), "、".join("`{{%s}}`" % x["name"] for x in synth)))
        L.append("")
    L.append("## ② 必须写的算式")
    L.append("")
    if t["formulas"]:
        L.append("| 规则 | 目标 | 表达式 | 依赖 |")
        L.append("|---|---|---|---|")
        for f in t["formulas"]:
            L.append("| `%s` | `%s` | `%s` | %s |" % (
                f.get("rule_id") or "—", f.get("target") or "—",
                f.get("expr") or "—", "、".join("`%s`" % d for d in f.get("deps") or []) or "—"))
    else:
        L.append("_（本节无预定义计算规则；涉及数值时从其他节规则取值，或标「需检索/需客户」。）_")
    L.append("")
    L.append("## ③ 本节必须覆盖")
    L.append("")
    for i, x in enumerate(t["must_cover"], 1):
        L.append("%d. %s" % (i, x))
    L.append("")
    L.append("## ④ 证据要求")
    L.append("")
    for x in t["evidence_requirement"]:
        L.append("- %s" % x)
    L.append("")
    L.append("## ⑤ 篇幅")
    L.append("")
    L.append("目标 %d–%d 字；按本节 %d 段 / %d 张表的原文详略分配，不平均主义。"
             % (s["word_budget"]["min"], s["word_budget"]["max"],
                s["paras"], s["tables"]))
    L.append("")
    L.append("## ⑥ 返回契约（给「推演写作专家团」）")
    L.append("")
    L.append("```json")
    L.append(json.dumps({
        "body": "该节正文 Markdown，数值全部写〔P-xxx〕节点引用",
        "citations": [{
            "claim_text": "正文中的一句话",
            "evidence_ids": ["P-xxx"],
            "source_file": "normalized.md 或客户材料路径",
            "section": t["section"],
            "quote": "证据原文片段",
        }],
        "self_check": {
            "number_bound": True,
            "missing_handled": True,
            "conflicts_pending": False,
            "formula_shown": True,
        },
        "notes_for_reviewer": "审核要点：本节的形态/冲突/缺口/风险",
    }, ensure_ascii=False, indent=2))
    L.append("```")
    L.append("")
    L.append("> `self_check.formula_shown`：本节若命中 ② 中任一规则，必须为 true；"
             "若无规则，填 true 并在 notes 说明「本节无算式」。")
    L.append("")
    L.append("## ⑦ 检查标准")
    L.append("")
    for i, c in enumerate(t["checks"], 1):
        L.append("%d. %s" % (i, c))
    L.append("")
    L.append("## ⑧ 本节图谱事实（引用即绑定）")
    L.append("")
    facts = t.get("graph_facts") or []
    if facts:
        L.append("| 节点 | subject | value | unit | status | source_type | section |")
        L.append("|---|---|---|---|---|---|---|")
        for f in facts[:80]:
            L.append("| `%s` | %s | %s | %s | %s | %s | %s |" % (
                f.get("id"), f.get("subject"), f.get("value"),
                f.get("unit") or "—", f.get("status"),
                f.get("source_type") or "—", f.get("section") or "—"))
        if len(facts) > 80:
            L.append("")
            L.append("> 仅显示前 80 条，共 %d 条。" % len(facts))
    else:
        L.append("_（本节图谱无直接节点；数值引用见 handoff 的 facts 表。）_")
    L.append("")
    L.append("---")
    L.append("")
    L.append("> 模板结束。本文件不含任何上财项目值；所有槽位由写作成员按真实输入填充。")
    L.append("")
    return "\n".join(L)


# ================================================================ 校验

def _number_in_text(num: str, text: str) -> bool:
    return re.search(r"(?<![\d.])%s(?![\d.])" % re.escape(num), text) is not None


def _structural_context(text: str, start: int, end: int, num: str) -> bool:
    ctx = text[max(0, start - 24):min(len(text), end + 12)]
    if STRUCT_NUM_RE.search(text[max(0, start - 16):start]):
        return True
    if YEAR_VERSION_RE.search(ctx) and ("版" in ctx or "年" in ctx):
        return True
    if re.search(r"(?:表|图|第)\s*%s" % re.escape(num), ctx):
        return True
    # 表7-1年用水量 / 图4-1项目基地：数字是表号/图号的一部分
    if re.search(r"[表图]\s*\d+\s*[-—–]\s*$", text[max(0, start - 12):start]):
        return True
    if re.search(r"%s\s*[-—–]\s*\d" % re.escape(num), ctx):
        return True
    return False


def find_value_residue(template_text: str, source_text: str) -> list[dict]:
    """返回上财真值残留列表。explicit 8 值为硬失败；动态带单位值也硬失败。"""
    out: list[dict] = []
    for num in SHUFE_VALUES:
        if _number_in_text(num, template_text):
            i = template_text.find(num)
            out.append({"value": num, "kind": "explicit",
                        "context": template_text[max(0, i - 30):i + 30]})
    for m in VALUE_WITH_UNIT_RE.finditer(source_text or ""):
        num = m.group(1).replace(",", "")
        unit = m.group(2)
        # 百分比一律不作为动态硬失败：规则系数（10%/40%/5%/8%…）是形；
        # 项目特有小数百分比已在 _devalue_percentages 里换槽位。
        if unit == "%":
            continue
        # 必须「数值 + 单位」同时命中，避免 1 在 1.1 里被误报
        mm = re.search(r"(?<![\d.])%s\s*%s" % (re.escape(num), re.escape(unit)),
                       template_text)
        if not mm:
            continue
        if _structural_context(template_text, mm.start(),
                               mm.start() + len(num), num):
            continue
        out.append({"value": num, "kind": "dynamic",
                    "unit": unit,
                    "context": template_text[max(0, mm.start() - 30):mm.start() + 30]})
    # 定性值残留（方位/四至/配套/资金来源/拆除对象）
    for x in find_qualitative_residue(template_text):
        out.append({"value": x["value"],
                    "kind": "qualitative_%s" % x["kind"],
                    "context": x.get("context", "")})
    # 去重
    seen = set()
    deduped = []
    for x in out:
        k = (x["value"], x["kind"])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(x)
    return deduped


def negative_test(template_text: str, source_text: str) -> list[dict]:
    """反例：故意注入 13032，必须被 find_value_residue 抓出。"""
    bad = template_text + "\n\n反例注入：总投资为 13032 万元。\n"
    return find_value_residue(bad, source_text)


# ================================================================ 批量

def build_all(*, prompt_path: str | Path, normalized_path: str | Path,
              shape_pack: str | Path, graph_path: str | Path,
              out_dir: str | Path, project_dir: str | Path,
              only_ids: list[str] | None = None) -> dict:
    project_dir = Path(project_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sections = section_meta(prompt_path, shape_pack)
    md_text = Path(normalized_path).read_text(encoding="utf-8")
    graph_data = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    anchors = build_anchors(md_text, sections)
    anchor_by_id = {a["id"]: a for a in anchors}

    index = []
    residue = {}
    form_mismatch = []
    errors = []
    for sec in sections:
        sid = sec["id"]
        if only_ids and sid not in only_ids:
            continue
        try:
            t = build_template(
                sid, project_dir=project_dir, source_md=str(normalized_path),
                shape_pack=shape_pack, graph=graph_data,
            )
            md = render_template_markdown(t)
        except Exception as e:  # 显式失败，不静默
            errors.append({"id": sid, "title": sec["title"],
                           "error": "%s: %s" % (type(e).__name__, e)})
            index.append({"id": sid, "title": sec["title"], "template": None,
                          "error": errors[-1]["error"]})
            continue

        (out / ("%s.md" % sid)).write_text(md, encoding="utf-8")
        slots_payload = [{k: v for k, v in s.items() if not k.startswith("_")}
                         for s in t["slots"]]
        (out / ("_slots-%s.json" % sid)).write_text(json.dumps({
            "section": sid, "title": t["title"], "source_title": t["source_title"],
            "writer_role": t["writer_role"], "shape": t["shape"],
            "slots": slots_payload, "formulas": t["formulas"],
            "must_cover": t["must_cover"], "checks": t["checks"],
            "source_anchor": t["source_anchor"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        # 用原始本节文本（去值前）做动态值校验；去值后的文本会掩盖漏网值
        residues = find_value_residue(md, t.get("source_text") or "")
        if residues:
            residue[sid] = residues

        a = anchor_by_id.get(sid) or {}
        index.append({
            "id": sid, "title": t["title"], "source_title": t["source_title"],
            "writer_role": t["writer_role"], "template": "%s.md" % sid,
            "slots": len(t["slots"]),
            "synthetic_slots": sum(1 for s in t["slots"] if s.get("synthetic")),
            "paras": t["shape"]["paras"], "tables": t["shape"]["tables"],
            "form_paras": t["shape"]["form_stats"].get("paras"),
            "form_tables": t["shape"]["form_stats"].get("tables"),
            "line_start": a.get("pos", -1) + 1 if a.get("pos") is not None else None,
            "line_end": t["source_anchor"]["line_end"],
            "mode": t["source_anchor"]["mode"],
            "used_title": t["source_anchor"]["used_title"],
            "out_of_order": t["source_anchor"]["out_of_order"],
            "residue": len(residues),
        })
        if t["shape"]["form_stats"].get("stale"):
            form_mismatch.append({
                "id": sid, "title": t["title"],
                "actual": [t["shape"]["paras"], t["shape"]["tables"]],
                "form": [t["shape"]["form_stats"].get("paras"),
                         t["shape"]["form_stats"].get("tables")],
            })

    (out / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    summary = {
        "generated": len([x for x in index if x.get("template")]),
        "requested": len([x for x in sections if not only_ids or x["id"] in only_ids]),
        "total_sections": len(sections),
        "errors": errors,
        "slots_min": min([x.get("slots") or 0 for x in index], default=0),
        "slots_lt3": [x["id"] for x in index if (x.get("slots") or 0) < 3],
        "residue": residue,
        "residue_sections": sorted(residue),
        "forbidden_values": list(SHUFE_VALUES),
        "form_mismatch_count": len(form_mismatch),
        "form_mismatch": form_mismatch,
    }
    (out / "_validation.json").write_text(json.dumps(summary, ensure_ascii=False,
                                                    indent=2), encoding="utf-8")
    return {"index": index, "summary": summary,
            "form_mismatch": form_mismatch, "residue": residue}


def render_generation_report(result: dict, *, negative_ok: bool) -> str:
    s = result["summary"]
    L = ["# 模板生成报告（P0-3）", ""]
    L.append("> 输入：`提示词-还原-119节全量.md` + `SHUFE-BDC-2019-001/source/normalized.md` + 形包 + clean 图谱")
    L.append("")
    L.append("## 一、覆盖率")
    L.append("")
    L.append("| 指标 | 结果 |")
    L.append("|---|---|")
    L.append("| 生成节数 | **%d/119** |" % s["generated"])
    L.append("| 失败 | %d |" % len(s["errors"]))
    L.append("| slots 最小值 | %s |" % s["slots_min"])
    L.append("| slots < 3 的节 | %s |" % (", ".join(s["slots_lt3"]) or "无"))
    L.append("| 上财值残留节 | %s |" % (", ".join(s["residue_sections"]) or "无"))
    L.append("| 形包统计与实测不一致节 | %d |" % s["form_mismatch_count"])
    L.append("| 反例注入 13032 被抓 | %s |" % ("✅ 是" if negative_ok else "❌ 否"))
    L.append("")
    if s["errors"]:
        L.append("## 二、失败明细")
        L.append("")
        for e in s["errors"]:
            L.append("- `%s` %s：%s" % (e["id"], e["title"], e["error"]))
        L.append("")
    if s["residue"]:
        L.append("## 三、上财值残留明细")
        L.append("")
        for sid, items in s["residue"].items():
            L.append("- `%s`：" % sid)
            for x in items:
                L.append("  - `%s`（%s）…%s…" % (x["value"], x["kind"],
                                                 x.get("context", "").replace("\n", " ")))
        L.append("")
    L.append("## 四、形包旧统计 vs normalized.md 实测（不一致清单）")
    L.append("")
    if result["form_mismatch"]:
        L.append("| 节 | 标题 | 实测 段/表 | 形包 段/表 |")
        L.append("|---|---|---:|---:|")
        for x in result["form_mismatch"]:
            L.append("| %s | %s | %s / %s | %s / %s |" % (
                x["id"], x["title"], x["actual"][0], x["actual"][1],
                x["form"][0], x["form"][1]))
    else:
        L.append("无。")
    L.append("")
    L.append("## 五、纯文本节标题（无 # 标记）处理")
    L.append("")
    plain = [x for x in result["index"] if x.get("mode") == "plain"]
    L.append("共 **%d** 节通过纯文本标题锚点定位（用户提到 6 节，实测更多，"
             "因为 7.2.x/7.3.x/8.2.x/8.3.x/9.2.x/9.3.x/10.5.x/13.4.x 在原文中"
             "都是纯文本子标题）：" % len(plain))
    L.append("")
    L.append("| 节 | 标题 | 使用标题 | 行号 |")
    L.append("|---|---|---|---:|")
    for x in plain:
        L.append("| %s | %s | %s | %s |" % (x["id"], x["title"],
                                            x.get("used_title"), x.get("line_start")))
    L.append("")
    ooo = [x for x in result["index"] if x.get("out_of_order")]
    L.append("## 六、乱序/重复标题消歧")
    L.append("")
    if ooo:
        for x in ooo:
            L.append("- %s %s 使用 `%s`（乱序回退）" % (x["id"], x["title"], x.get("used_title")))
    else:
        L.append("无乱序回退；重复标题 1.4/9.4、10.1/12.1 已按文档顺序正确消歧。")
    L.append("")
    return "\n".join(L)


# ================================================================ CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="为 119 节批量生成含槽位模板")
    ap.add_argument("--prompt", default="提示词-还原-119节全量.md")
    ap.add_argument("--normalized", default="SHUFE-BDC-2019-001/source/normalized.md")
    ap.add_argument("--shape-pack", default="形-可复用知识资产-v1.0")
    ap.add_argument("--graph", default="GRAPH-新项目-华东理工AI研究院-clean.json")
    ap.add_argument("--out", default="prompt-templates-all")
    ap.add_argument("--project-dir", default=".")
    ap.add_argument("--sections", default="", help="逗号分隔节号，如 1.1,13.3")
    ap.add_argument("--report", default="template-generation-报告.md")
    ap.add_argument("--negative-test", action="store_true",
                    help="注入 13032 验证校验器能发现值污染")
    args = ap.parse_args(argv)

    only = [x.strip() for x in args.sections.split(",") if x.strip()] or None
    result = build_all(prompt_path=args.prompt, normalized_path=args.normalized,
                       shape_pack=args.shape_pack, graph_path=args.graph,
                       out_dir=args.out, project_dir=args.project_dir,
                       only_ids=only)

    negative_ok = False
    if args.negative_test:
        sample_id = (only or ["1.1"])[0]
        sample = Path(args.out) / ("%s.md" % sample_id)
        if sample.exists():
            src = Path(args.normalized).read_text(encoding="utf-8")
            violations = negative_test(sample.read_text(encoding="utf-8"), src)
            negative_ok = any(v.get("value") == "13032" for v in violations)
            print("negative test: injected 13032 -> %d violations; caught=%s"
                  % (len(violations), negative_ok))

    report = render_generation_report(result, negative_ok=negative_ok)
    Path(args.report).write_text(report, encoding="utf-8")

    s = result["summary"]
    print("generated %d/119; errors=%d; slots_min=%s; slots<3=%s; residue=%s; form_mismatch=%d"
          % (s["generated"], len(s["errors"]), s["slots_min"],
             s["slots_lt3"], s["residue_sections"], s["form_mismatch_count"]))
    if s["errors"]:
        for e in s["errors"]:
            print(" -", e)
        return 1
    if s["residue_sections"]:
        print("RESIDUE FOUND")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
