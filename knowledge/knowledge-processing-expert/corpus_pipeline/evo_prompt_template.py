# -*- coding: utf-8 -*-
"""evo_prompt_template —— 把「带值提示词」重构成「含槽位模板」。

输入：
  提示词-还原-119节全量.md        （形态/规则/证据/契约/文本事实）
  SHUFE-BDC-2019-001/source/normalized.md （完整原文，按标题名称抽取）
  GRAPH-新项目-华东理工AI研究院-merged.json（只用于推断槽位来源类型与单位）

输出：
  prompt-templates/<节号>.md      模板（0 个项目值；⓿b 全部是 {{槽位}}）
  prompt-templates/_slots-<节号>.json  槽位元数据
  prompt-templates/_index.json    索引

纪律：
  - 不把「缺失」写成 0；
  - 不把上财原始值写进模板；
  - 表格按「行名·列义」命名槽位，散文按语义上下文命名；
  - 只新建文件，不改已有脚本。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from .evo_slot_common import (
        GraphIndex, canonical_name, canon_col, citations, eval_expr, format_value,
        load_aliases, norm, split_table_slot, strip_markdown, to_number,
        unit_from_header, unit_of_value_text,
    )
    from .evo_devalue_rules import (
        apply_qualitative_devalue, protect_placeholders, restore_placeholders,
    )
except ImportError:  # 直接以脚本运行
    from evo_slot_common import (
        GraphIndex, canonical_name, canon_col, citations, eval_expr, format_value,
        load_aliases, norm, split_table_slot, strip_markdown, to_number,
        unit_from_header, unit_of_value_text,
    )
    from evo_devalue_rules import (
        apply_qualitative_devalue, protect_placeholders, restore_placeholders,
    )


# ================================================================ 常量

# 原文里必须保留的「形」引用：表号/图号/标准号/百分比/文号
KEEP_RE = re.compile(
    r"表\s*\d+(?:\s*[-—–]\s*\d+)?|图\s*\d+(?:\s*[-—–]\s*\d+)?|"
    r"第\s*\d+\s*[章节条]|GB\s*/?\s*T?\s*\d+(?:[-.]\d+)*|DGJ\s*\d+(?:[-.]\d+)*|"
    r"JGJ\s*\d+(?:[-.]\d+)*|建标\s*\d+(?:[-.]\d+)?|"
    r"〔[^〕]*〕(?:\s*\d+号)?|\d+(?:\.\d+)?\s*%"
)
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
STRUCT_CELL_RE = re.compile(r"^(?:[一二三四五六七八九十]+|（[一二三四五六七八九十]+）|\d+(?:\.\d+)*)$")

PROJECT_NAME_REPLACEMENTS = [
    ("上海财经大学中山北一路校区大数据研究中心", "项目名称"),
    ("上海财经大学", "建设单位"),
    ("中山北一路校区", "校区"),
    ("大数据研究中心", "项目名称"),
]

# 上财专有的机构/建筑名：不是数值，但同样不能跨项目复用
PHRASE_REPLACEMENTS = [
    ("管理科学与量化信息研究中心、理论计算机研究中心、应用统计研究中心、数据科研与统计研究院",
     "科研机构列表"),
    ("第五教学楼", "原有建筑"),
]

# 散文数值槽位：上下文 → 槽位名。顺序从具体到宽泛。
CONTEXT_RULES = [
    (r"项目总投资|总投资", "总投资"),
    (r"建安工程费用|建筑安装工程费用|建安费", "建安工程费用"),
    (r"工程建设其他费用|工程建设其他费|二类费", "工程建设其他费用"),
    (r"基本预备费|预备费", "预备费"),
    (r"原建筑拆除费用|拆除费用|拆除费", "原建筑拆除费用"),
    (r"拆除面积", "拆除面积"),
    (r"地上建筑面积", "地上建筑面积"),
    (r"地下建筑面积", "地下建筑面积"),
    (r"新建总建筑面积|总建筑面积", "本项目建筑面积"),
    (r"年总用水量|年用水量", "年总用水量"),
    (r"年总耗电量|年用电量|年耗电量", "年总耗电量"),
    (r"建设工期|工期", "建设工期"),
    (r"单位建筑面积电耗", "单位建筑面积电耗"),
    (r"单位造价", "单位造价（总投资口径）"),
    (r"综合能耗", "综合能耗（当量值）"),
    (r"冷负荷", "冷负荷"),
    (r"热负荷", "热负荷"),
    (r"科研人员规划人数", "科研人员规划人数"),
    (r"研究生|博士生|访问学者", "研究生博士生访问学者规划人数"),
    (r"公共服务配套用房", "公共服务配套用房建筑面积"),
    (r"科研用房", "科研用房"),
    (r"项目名称", "项目名称"),
    (r"建设单位", "建设单位"),
    (r"建设地点|项目地址|地址", "建设地点"),
    (r"编制单位", "编制单位"),
    (r"编制时间", "编制时间"),
    (r"项目编号|项目代码", "项目编号"),
    (r"依据大纲|编制依据", "依据大纲"),
    (r"总投资", "总投资"),
    (r"投资", "投资"),
    (r"面积", "面积"),
    (r"人数", "人数"),
    (r"比例|占比", "比例"),
    (r"费率", "费率"),
]

# 表头语义 → 来源类型（仅在图中没有事实时使用）
STD_COLS = {
    "用水定额", "用电指标", "需要系数", "同时使用系数",
    "日均工作小时数", "年工作天数", "折标系数", "折标煤", "比例",
}
COMPUTED_COLS = {"单价", "年用水量", "年用电量", "日用水量"}
CUSTOMER_COLS = {"合价", "数量"}

SOURCE_TYPE_CN = {
    "CUSTOMER": "CUSTOMER", "CUSTOMER_PRIMARY": "CUSTOMER",
    "STANDARD": "STANDARD", "COMPUTED": "COMPUTED",
    "UNREGISTERED": "JUDGMENT", "FORM": "FORM", "JUDGMENT": "JUDGMENT",
}

FALLBACK = {
    "CUSTOMER": "问客户",
    "STANDARD": "去标准库查（建标191/行业惯例）",
    "COMPUTED": "由 ② 算式计算",
    "JUDGMENT": "提示用户决策",
    "FORM": "沿用原文形态",
}


# ================================================================ 槽位

@dataclass
class Slot:
    name: str
    label: str = ""
    source_type: str = "CUSTOMER"
    unit: str = ""
    places: list = field(default_factory=list)
    node_role: str = ""
    table: str = ""
    col: str = ""
    canonical: str = ""
    note: str = ""
    value_text: str = ""

    def as_dict(self):
        return {
            "name": self.name, "label": self.label or self.name,
            "source_type": self.source_type, "unit": self.unit,
            "places": list(self.places), "node_role": self.node_role,
            "table": self.table, "col": self.col,
            "canonical": self.canonical, "note": self.note,
        }


class SlotRegistry:
    def __init__(self, aliases):
        self.slots: dict[str, Slot] = {}
        self.order: list[str] = []
        self.alias_to_canon = aliases

    def add(self, name: str, *, place: str = "", **kw) -> Slot:
        key = str(name or "").strip()
        if not key or not re.search(r"[一-龥A-Za-z0-9]", key):
            return None
        if key not in self.slots:
            self.slots[key] = Slot(name=key, **{k: v for k, v in kw.items() if v not in (None, "")})
            self.order.append(key)
        s = self.slots[key]
        if place and place not in s.places:
            s.places.append(place)
        for k, v in kw.items():
            if v not in (None, "") and not getattr(s, k, None):
                setattr(s, k, v)
        if not s.canonical:
            s.canonical = canonical_name(key, self.alias_to_canon)
        return s


# ================================================================ 提示词解析

SECTION_RE = re.compile(r"(?m)^## §([0-9]+(?:\.[0-9]+)*)\s+(.+?)\s*$")
BLOCK_RE = re.compile(r"(?m)^###\s+(⓿b?|①|②|③|④|⑤|⑥|⑦|⑧|⑨)\s*(.*?)\s*$")


def parse_prompt_file(path):
    text = Path(path).read_text(encoding="utf-8")
    sections = []
    matches = list(SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        sec_id = m.group(1)
        title = m.group(2).strip()
        body = text[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        blocks = {}
        bm = list(BLOCK_RE.finditer(body))
        for j, b in enumerate(bm):
            key = b.group(1)
            start = b.end()
            end = bm[j + 1].start() if j + 1 < len(bm) else len(body)
            blocks[key] = body[start:end].strip("\n")
        header = body[:bm[0].start()].strip("\n") if bm else body.strip("\n")
        sections.append({
            "id": sec_id, "title": title, "header": header,
            "blocks": blocks, "raw": body,
        })
    return sections


def parse_form_columns(form_text):
    cols = []
    for line in form_text.splitlines():
        s = line.strip()
        if s.startswith("- 列：") or s.startswith("- **列**："):
            part = s.split("：", 1)[1] if "：" in s else s
            arr = [x.strip() for x in re.split(r"[｜|]", part) if x.strip()]
            if arr:
                cols.append(arr)
    return cols


def parse_shape_nodes(block_text, aliases):
    """解析 ① 形节点表 → [{role,name,state,value_text,node_id,unit}]。"""
    rows = []
    if not block_text:
        return rows
    in_table = False
    for line in block_text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 4:
            continue
        if cells[0] in ("角色", "---") or set(cells[0]) <= {"-", ":", " "}:
            in_table = True
            continue
        if not in_table:
            continue
        role, var, state, value = cells[0], cells[1], cells[2], "|".join(cells[3:])
        name = strip_markdown(var).replace("`alias`", "").strip()
        name = re.sub(r"\s*alias\s*$", "", name)
        if not name or name in ("…", "...", "—", "-", "合计"):
            continue
        if not re.search(r"[一-龥A-Za-z0-9]", name):
            continue
        nid = citations(value)
        value_wo_cite = re.sub(r"〔[^〕]+〕", "", value)
        rows.append({
            "role": role.strip(), "name": name,
            "state": state.strip(), "value_text": value.strip(),
            "node_id": nid[0] if nid else "",
            "unit": unit_of_value_text(value_wo_cite),
        })
    return rows


def parse_rules(block_text):
    rules = []
    if not block_text:
        return rules
    lines = block_text.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        m = re.match(r"-\s*\*\*(R-[^*]+)\*\*\s*→\s*`([^`]+)`", s)
        if m:
            rid, target = m.group(1).strip(), m.group(2).strip()
            expr = ""
            for j in range(i + 1, min(i + 4, len(lines))):
                m2 = re.match(r"\s*-\s*`(.+)`\s*$", lines[j])
                if m2:
                    expr = m2.group(1).strip()
                    break
            rules.append({"rule": rid, "target": target, "expr": expr})
            continue
        m = re.match(r"([^=]+?)\s*=\s*(.+)$", s)
        if m and "round(" in m.group(2):
            rules.append({"rule": "", "target": m.group(1).strip(), "expr": m.group(2).strip()})
    # 去重（同 rule 保留第一个）
    seen = set()
    out = []
    for r in rules:
        k = (r["rule"], r["target"], r["expr"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def parse_must_cover(block_text):
    out = []
    for line in (block_text or "").splitlines():
        s = line.strip()
        if re.match(r"^\d+\.\s+", s):
            out.append(re.sub(r"^\d+\.\s+", "", s))
        elif s.startswith("- 表"):
            out.append(s[2:].strip())
    return out


def parse_text_facts(block_text):
    rows = []
    if not block_text:
        return rows
    for line in block_text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("变量", "---"):
            continue
        if set(cells[0]) <= {"-", ":", " "}:
            continue
        name = strip_markdown(cells[0])
        nid = citations(cells[2])
        rows.append({"name": name, "value": cells[1], "node_id": nid[0] if nid else ""})
    return rows


def parse_conflicts(block_text):
    out = []
    for line in (block_text or "").splitlines():
        s = line.strip()
        if s.startswith("- **CF") or s.startswith("- **"):
            out.append(s[2:].strip())
    return out


# ================================================================ 原文抽取 / 表头修复


def collect_stop_titles(prompt_sections, md_text):
    titles = set()
    for sec in prompt_sections:
        t = re.sub(r"^[0-9.]+\s+", "", sec["title"]).strip()
        if t:
            titles.add(t)
            titles.add(t.replace("{建设单位}", "上海财经大学")
                           .replace("{校区}", "中山北一路校区")
                           .replace("{项目名称}", "上海财经大学中山北一路校区大数据研究中心"))
    for m in re.finditer(r"(?m)^(#{1,6})\s+(.*)$", md_text or ""):
        titles.add(m.group(2).strip())
    return titles


def extract_sources(md_text, prompt_sections):
    try:
        from .evo_source_section import extract_section
    except ImportError:
        from evo_source_section import extract_section
    stop = collect_stop_titles(prompt_sections, md_text)
    out = {}
    for sec in prompt_sections:
        title = re.sub(r"^[0-9.]+\s+", "", sec["title"]).strip()
        cands = [
            title,
            title.replace("{建设单位}", "上海财经大学")
                 .replace("{校区}", "中山北一路校区")
                 .replace("{项目名称}", "上海财经大学中山北一路校区大数据研究中心"),
        ]
        got = None
        for c in cands:
            if not c:
                continue
            r = extract_section(md_text, c, stop_titles=stop)
            if r.get("found"):
                got = r
                break
        out[sec["id"]] = got
    return out


def repair_table(sec_id, title, table, form_cols=None):
    """修复合并表头导致的列数不一致；保留原始全部数据格。"""
    hdr = [strip_markdown(c) for c in (table.get("cols") or [])]
    rows = [list(r) for r in (table.get("rows_data") or [])]
    n = max([len(r) for r in rows] + [len(hdr), 0])
    cols = hdr
    hdr_join = " ".join(hdr)
    if n == len(hdr):
        cols = hdr
    elif form_cols and len(form_cols) == n:
        cols = form_cols
    elif "用水定额" in hdr_join and "日用水量" in hdr_join:
        # 源表头漏了「用水定额单位」一列；数据行是 9 格
        cols = ["序号", "名称", "用水定额", "用水定额·单位", "数量", "数量·单位",
                "日用水量(m³/d)", "用水天数(d)", "年用水量(万m³)"]
    elif "能源消耗" in hdr_join and "折标煤" in hdr_join:
        cols = ["序号", "名称", "能源消耗", "能源消耗·单位", "折标系数",
                "折标系数·单位", "折标煤（tce）", "比例"]
    elif n > len(hdr):
        cols = hdr + ["列%d" % (i + 1) for i in range(len(hdr), n)]
    # 补齐行
    rows = [r + [""] * (len(cols) - len(r)) for r in rows]
    return {"cols": cols, "rows_data": rows, "nest": table.get("nest", 1)}


def table_chars(table):
    return len(re.sub(r"\s", "", " ".join(
        " ".join(str(c) for c in r) for r in (table.get("rows_data") or []))))


# ================================================================ 去值 → 槽位


def _last_noun(prefix: str) -> str:
    p = str(prefix or "")
    # 最后一个句子/分句边界之后
    p = re.split(r"[。；;，,：:！？\n]", p)[-1]
    p = re.sub(r"^\s*(?:[-*]|\d+[.)、])\s*", "", p)
    # 去掉尾部连接词
    p = re.sub(r"(?:为人民币|为|达到|约为|约|共计|合计|分别是|其中|是|有|按|人民币|元|平方米|万元|"
               r"万m³|万千瓦时|m³|㎡|个月|年|月|日|个)\s*$", "", p)
    m = re.search(r"([一-龥A-Za-z0-9（）()·/]+)$", p)
    if not m:
        return ""
    cand = m.group(1).strip()
    cand = re.sub(r"^(?:其中|新建|本项目|项目|该)", "", cand)
    if len(cand) < 2:
        return ""
    return cand


def prose_slot_name(prefix, suffix, sentence, para_idx, occ, aliases):
    # 只看当前分句，避免前文「项目总投资」污染后文所有数值
    ctx = re.split(r"[。；;，,：:！？\n]", str(prefix or ""))[-1]
    follow = re.split(r"[。；;，,！？\n]", str(suffix or ""))[0]
    # 日期 / 工期：看数值之后的分句，先判竣工再判开工
    if follow.startswith("年"):
        if "竣工" in follow:
            return "竣工年份"
        if "开工" in follow:
            return "开工年份"
        return "年份"
    if follow.startswith("月"):
        if "竣工" in follow:
            return "竣工月份"
        if "开工" in follow:
            return "开工月份"
        return "月份"
    if follow.startswith("个月") or re.search(r"工期[^。；]{0,8}$", ctx):
        return "建设工期"
    # 标准文号（计价格/沪价费/发改价格/财建/建标）
    if re.search(r"(?:计价格|沪价费|发改价格|财建|建标)[（(]?$", ctx):
        return "标准文号"
    for pat, name in CONTEXT_RULES:
        if re.search(pat, ctx):
            return canonical_name(name, aliases)
    cand = _last_noun(ctx)
    if cand:
        return canonical_name(cand, aliases)
    return "本节值%d_%d" % (para_idx, occ)


def _protect(text, store):
    def hold(m):
        store.append(m.group(0))
        return chr(0xE100 + len(store) - 1)
    return KEEP_RE.sub(hold, text)


def _restore(text, store):
    for i, v in enumerate(store):
        text = text.replace(chr(0xE100 + i), v)
    return text


def devalue_prose(text, *, section, para_idx, registry):
    t = str(text or "")
    # 0) 定性值 → 槽位（方位/四至/配套/资金来源/拆除对象/相邻建筑）
    #    必须在数字和专名之前：整段四至先换成一个槽位，避免被拆碎。
    t = apply_qualitative_devalue(t, registry=registry,
                                  place="⓿b段%d" % para_idx,
                                  section=section)
    # 已有槽位全程保护：槽位名可能含数字（资金来源1/相邻建筑2），
    # 不能被后面的 NUM_RE 当成项目数值二次替换。
    t, slot_tokens = protect_placeholders(t)
    # 1) 专名 → 槽位（长串优先）
    for name, slot in PROJECT_NAME_REPLACEMENTS + PHRASE_REPLACEMENTS:
        if name and name in t:
            registry.add(slot, place="⓿b段%d" % para_idx, label=slot,
                         source_type="CUSTOMER")
            t = t.replace(name, "{{%s}}" % slot)
    # 2) 保护表号/标准号/百分比
    keep = []
    t = _protect(t, keep)
    # 3) 逐个数 → 语义槽位
    sentence = _restore(t, keep)
    out = []
    last = 0
    occ = 0
    for m in NUM_RE.finditer(t):
        out.append(t[last:m.start()])
        prefix = _restore(t[max(0, m.start() - 80):m.start()], keep)
        suffix = _restore(t[m.end():m.end() + 24], keep)
        sent = _restore(t[:m.end() + 40], keep)
        occ += 1
        slot = prose_slot_name(prefix, suffix, sent, para_idx + 1, occ, registry.alias_to_canon)
        registry.add(slot, place="⓿b段%d" % (para_idx + 1),
                     label=slot, source_type="JUDGMENT")
        out.append("{{%s}}" % slot)
        last = m.end()
    out.append(t[last:])
    return restore_placeholders(_restore("".join(out), keep), slot_tokens)


def _clean_row_label(s):
    t = strip_markdown(s)
    t = re.sub(r"^其中[：:]?", "", t)
    t = re.sub(r"^\d+(?:\.\d+)*[.、]?\s*", "", t)
    t = t.strip(" ：:")
    if not t or STRUCT_CELL_RE.fullmatch(t):
        return ""
    return t


def aggregate_slot(sec_id, col):
    if sec_id.startswith("13.3"):
        if col == "合价":
            return "总投资"
        if col == "数量":
            return "本项目建筑面积"
        if col == "单价":
            return "单位造价（总投资口径）"
    if sec_id.startswith("7.2.2"):
        if col == "年用水量":
            return "年总用水量"
        if col == "年用电量":
            return "年总耗电量"
    return ""


def devalue_table(cols, rows, *, sec_id, table_idx, registry):
    # 行名所在列
    row_idx = None
    for i, h in enumerate(cols):
        if canon_col(h) == "序号":
            continue
        if any(k in h for k in ("名称", "工程和费用", "指标名称", "费用名称", "项目")):
            row_idx = i
            break
    if row_idx is None:
        row_idx = next((i for i, h in enumerate(cols) if canon_col(h) != "序号"), 0)

    new_rows = []
    for ri, row in enumerate(rows):
        row = list(row) + [""] * (len(cols) - len(row))
        row_label = ""
        for j in range(row_idx, len(cols)):
            c = _clean_row_label(row[j])
            if c:
                row_label = c
                break
        if not row_label:
            row_label = "行%d" % (ri + 1)
        out = []
        for ci, cell in enumerate(row):
            raw = str(cell if cell is not None else "")
            col = canon_col(cols[ci])
            hdr = cols[ci]
            # 序号 / 单位列保留原样（单位是形，不是值）
            if col == "序号" or (col == "单位" and "造价" not in hdr and "单价" not in hdr):
                out.append(raw)
                continue
            if col in ("用水定额·单位", "数量·单位", "能源消耗·单位", "折标系数·单位"):
                out.append(raw)
                continue
            if not NUM_RE.search(raw):
                out.append(raw)
                continue
            # 槽位命名：只有「总计/合计」行才聚合到本节总量
            is_total = bool(re.fullmatch(r"(?:总计|合计|总合计|共计)", row_label))
            if col == "备注":
                base = "%s·备注" % row_label
            elif is_total and aggregate_slot(sec_id, col):
                base = aggregate_slot(sec_id, col)
            else:
                base = "%s·%s" % (row_label, col)
            # 定额/数量列的「单位」在相邻的 ×·单位 列
            unit = unit_from_header(hdr)
            if ci + 1 < len(cols) and (cols[ci + 1].endswith("·单位") or cols[ci + 1].endswith("单位")):
                unit = strip_markdown(row[ci + 1]) or unit
            keep = []
            prot = _protect(raw, keep)
            pieces = []
            last = 0
            n = 0
            for m in NUM_RE.finditer(prot):
                pieces.append(prot[last:m.start()])
                n += 1
                slot = base if n == 1 else "%s%d" % (base, n)
                registry.add(
                    slot, place="⓿b表%d" % table_idx,
                    label=("%s %s" % (row_label, col)).strip(),
                    source_type=("STANDARD" if col in STD_COLS else
                                 "COMPUTED" if col in COMPUTED_COLS else
                                 "CUSTOMER" if col in CUSTOMER_COLS else "JUDGMENT"),
                    unit=unit, table="表%d" % table_idx, col=col,
                )
                pieces.append("{{%s}}" % slot)
                last = m.end()
            pieces.append(prot[last:])
            out.append(_restore("".join(pieces), keep))
        new_rows.append(out)
    return new_rows


# ================================================================ 槽位元数据


def infer_source_type(name, slot, graph, rules):
    """按图事实 → 规则目标 → 表列语义 → 名称语义的顺序判定。"""
    if graph:
        fact, alts = graph.find(name)
        if fact and fact.get("value") is not None:
            st = SOURCE_TYPE_CN.get(str(fact.get("source_type") or ""), "")
            if st:
                return st
    # 直接规则目标
    if graph:
        rr = graph.find_rule_for_target(name)
        if rr:
            return "COMPUTED"
    n = norm(name)
    for r in rules or []:
        if norm(r.get("target")) == n or norm(r.get("rule")) == n:
            return "COMPUTED"
    col = slot.col if slot else ""
    if col in COMPUTED_COLS:
        return "COMPUTED"
    if col in STD_COLS:
        return "STANDARD"
    if col in CUSTOMER_COLS:
        return "CUSTOMER"
    if col == "备注":
        return "JUDGMENT"
    if name in ("校区", "科研机构列表", "原有建筑"):
        return "CUSTOMER"
    if re.search(r"(费率|定额|指标|系数|标准|规范)", name):
        return "STANDARD"
    if re.search(r"(时间|年份|月份|工期|名称|地点|编号|单位|电话|地址|列表)", name):
        return "CUSTOMER"
    if re.search(r"(投资|费用|金额|面积|人数|水量|电量|负荷|造价|比例|占比)", name):
        return "CUSTOMER"
    return "JUDGMENT"


def infer_unit(name, slot, graph):
    if slot and slot.unit:
        return slot.unit
    if graph:
        fact, alts = graph.find(name)
        if fact and fact.get("unit"):
            return str(fact.get("unit")).strip()
    n = str(name)
    if re.search(r"(占比|比例|费率|率)$", n):
        return "%"
    if "单位面积冷负荷指标" in n or "单位面积热负荷指标" in n:
        return "W/㎡"
    if "单位建筑面积电耗" in n:
        return "kWh/㎡"
    if "单位造价" in n:
        return "元/㎡"
    if "面积" in n:
        return "㎡"
    if re.search(r"(投资|费用|金额|合价)", n):
        return "万元"
    if "水量" in n:
        return "万m³"
    if "电量" in n:
        return "万千瓦时"
    if "负荷" in n:
        return "kW"
    if "人数" in n:
        return "人"
    if "工期" in n:
        return "个月"
    return ""


def enrich_slots(registry, graph, rules, aliases):
    for name in registry.order:
        s = registry.slots[name]
        s.canonical = s.canonical or canonical_name(name, aliases)
        if not s.label:
            s.label = name
        s.source_type = infer_source_type(name, s, graph, rules)
        s.unit = infer_unit(name, s, graph)
        if not s.note:
            s.note = FALLBACK.get(s.source_type, "提示用户决策")


# ================================================================ 模板渲染


def fix_guidance(text, *, paras, para_chars, tables):
    t = str(text or "")
    t = re.sub(r"\d+\s*段叙述", "%d 段叙述" % paras, t)
    total = para_chars + sum(table_chars(tb) for tb in tables)
    t = re.sub(r"总字数\s*\d+\s*[–-]\s*\d+\s*字",
               "总字数 %d–%d 字" % (total, total * 3), t)
    if tables:
        tb = tables[0]
        t = re.sub(r"\d+\s*列\s*×\s*约?\s*\d+\s*行",
                   "%d 列 × 约 %d 行" % (len(tb["cols"]), len(tb["rows_data"])), t)
        t = re.sub(r"（列：[^）]*）", "（列：%s）" % "/".join(tb["cols"]), t)
    return t


def rewrite_form_block(form_text, *, sec_id, tables, paras, para_chars, char_tables=None):
    lines = str(form_text or "").splitlines()
    out = []
    table_i = 0
    for line in lines:
        s = line.strip()
        if s.startswith("- **表 "):
            if table_i < len(tables):
                tb = tables[table_i]
                m = re.match(r"(- \*\*表\s*\d+\*\*：)(.*)$", s)
                prefix = m.group(1) if m else "- **表 %d**：" % (table_i + 1)
                out.append("%s%d 列 × %d 行，嵌套 %d 层"
                           % (prefix, len(tb["cols"]), len(tb["rows_data"]), tb.get("nest", 1)))
            else:
                out.append(line)
            table_i += 1
            continue
        if s.startswith("- 列：") and table_i > 0 and table_i <= len(tables):
            out.append("- 列：" + " ｜ ".join(tables[table_i - 1]["cols"]))
            continue
        if s.startswith("- 样例行：") and table_i > 0 and table_i <= len(tables):
            tb = tables[table_i - 1]
            first = tb["rows_data"][0] if tb["rows_data"] else []
            out.append("- 样例行：`%s`" % " ｜ ".join(first))
            continue
        if "总字数" in s or "段叙述" in s:
            out.append(fix_guidance(line, paras=paras, para_chars=para_chars,
                                    tables=char_tables or tables))
            continue
        out.append(line)
    return "\n".join(out)


def render_slot_table(registry, *, filled=False, results=None):
    head = ("| 槽位 | 含义 | 来源类型 | 单位 | 出现位置 | 填不上时 |"
            if not filled else
            "| 槽位 | 含义 | 状态 | 值 | 单位 | 节点ID | 说明 |")
    sep = ("|---|---|---|---|---|---|" if not filled else "|---|---|---|---|---|---|---|")
    lines = [head, sep]
    results = results or {}
    for name in registry.order:
        s = registry.slots[name]
        if not filled:
            lines.append("| `{{%s}}` | %s | %s | %s | %s | %s |" % (
                name, s.label or name, s.source_type, s.unit or "—",
                "、".join(s.places) or "①", s.note or FALLBACK.get(s.source_type, "")))
        else:
            r = results.get(name) or {}
            st = r.get("status", "unfilled")
            mark = {"filled": "✓ 已填", "computed": "✓ 已算",
                    "missing_customer": "◐ 缺客户", "missing_standard": "✗ 待标准",
                    "unfilled": "? 待确认"}.get(st, st)
            val = r.get("display") or r.get("value") or ""
            if isinstance(val, list):
                val = " / ".join(str(x) for x in val)
            nid = r.get("node_id") or ""
            lines.append("| `{{%s}}` | %s | %s | %s | %s | %s | %s |" % (
                name, s.label or name, mark, val if val not in (None, "") else "—",
                s.unit or r.get("unit") or "—", nid or "—",
                r.get("reason") or s.note or ""))
    return "\n".join(lines)


def render_template(sec, source, *, graph=None, rules=None, aliases=None):
    registry = SlotRegistry(aliases or {})
    blocks = sec["blocks"]
    title = sec["title"]
    sec_id = sec["id"]

    # ---- 原文
    paras = list((source or {}).get("paras") or [])
    raw_tables = list((source or {}).get("tables") or [])
    if not paras and not raw_tables:
        # 兜底：从旧提示词的 ⓿b 取
        body = blocks.get("⓿b") or ""
        paras = [re.sub(r"^\d+\.\s*", "", l).strip()
                 for l in body.splitlines()
                 if re.match(r"^\d+\.\s+", l.strip())]
        raw_tables = []

    form_cols = parse_form_columns(blocks.get("⓿") or "")
    tables = []
    for i, tb in enumerate(raw_tables, 1):
        tables.append(repair_table(sec_id, title, tb,
                                   form_cols[i - 1] if i - 1 < len(form_cols) else None))

    # ---- 去值
    dv_paras = []
    for pi, pa in enumerate(paras):
        dv_paras.append(devalue_prose(pa, section=sec_id, para_idx=pi, registry=registry))
    dv_tables = []
    for ti, tb in enumerate(tables, 1):
        rows = devalue_table(tb["cols"], tb["rows_data"], sec_id=sec_id,
                             table_idx=ti, registry=registry)
        dv_tables.append({"cols": tb["cols"], "rows_data": rows, "nest": tb.get("nest", 1)})

    # ---- ① 形节点（本节点槽位）
    shape_nodes = parse_shape_nodes(blocks.get("①") or "", aliases or {})
    for n in shape_nodes:
        s = registry.add(n["name"], place="①", label=n["name"],
                         node_role=n["role"], unit=n["unit"],
                         source_type="JUDGMENT")
        if n.get("value_text"):
            s.value_text = n["value_text"]
        if n.get("node_id") and not s.note:
            s.note = ""

    # ---- ② 规则
    rules = parse_rules(blocks.get("②") or "")
    # 用 ① 里的规则 ID 补全 target/expr（旧提示词的 ② 已足够，这里只兜底）
    rule_by_id = {}
    for r in (rules or []):
        if r.get("rule"):
            rule_by_id[r["rule"]] = r

    # ---- 槽位元数据
    enrich_slots(registry, graph, rules or [], aliases or {})

    # ---- ⓿ 形态
    form_text = blocks.get("⓿") or ""
    form_text = re.sub(r"^###\s*⓿[^\n]*\n?", "", form_text).strip("\n")
    form_text = rewrite_form_block(form_text, sec_id=sec_id, tables=dv_tables,
                                   paras=len(paras), para_chars=(source or {}).get("para_chars", 0),
                                   char_tables=tables)

    # ---- ⓿b
    b = ["### ⓿b 本节原文（去值后的范文，跨项目固定）", ""]
    b.append("> 下面是从原报告还原的**完整本节内容**，**值已全部替换为槽位**。"
             "请严格照此结构、详略与措辞习惯还原；槽位由 `evo_fill_slots` 填入新项目值。")
    b.append("")
    b.append("**原文段落（%d 段 / %d 字）：**" % (len(paras), (source or {}).get("para_chars", 0)))
    b.append("")
    for i, pa in enumerate(dv_paras, 1):
        b.append("%d. %s" % (i, pa))
    b.append("")
    for ti, tb in enumerate(dv_tables, 1):
        b.append("**原文表 %d：%d 列 × %d 行，嵌套 %d 层**"
                 % (ti, len(tb["cols"]), len(tb["rows_data"]), tb.get("nest", 1)))
        b.append("")
        b.append("| " + " | ".join(tb["cols"]) + " |")
        b.append("|" + "---|" * len(tb["cols"]))
        for row in tb["rows_data"]:
            b.append("| " + " | ".join(row) + " |")
        b.append("")
    b.append("**还原纪律（基于原文，不是基于形包）：**")
    b.append("1. **结构照原文**：原文几段就几段，原文一张表就一张表，不增不减。")
    b.append("2. **详略照原文**：原文某段只有一句话，还原也不要扩写成三段。")
    b.append("3. **措辞照原文**：沿用原文的句式与小标题前缀。")
    b.append("4. **只换值不换形**：把槽位换成新项目数据，结构与逻辑不动。")
    b.append("5. **原文有表就更表**：表格列、行层级、备注都要保留，不得拆成多个小节。")
    b.append("")
    b.append("**仿照参考**：⓿b 本节原文就是仿照参考 —— 结构、详略、措辞的唯一权威。")

    # ---- 组装
    L = []
    L.append("# 提示词模板 · §%s %s" % (sec_id, title))
    L.append("")
    L.append("> 模板 ID：T-%s ｜ 来源：上财 §%s（跨项目固定形） ｜ 值槽位：%d 个"
             % (sec_id, sec_id, len(registry.order)))
    L.append("> 本文件**不含任何项目值**；用 `evo_fill_slots.fill_slots()` 填入新项目值后生成 `prompt-filled/%s.md`。"
             % sec_id)
    L.append("")
    if sec.get("header"):
        L.append(sec["header"].strip())
        L.append("")
    L.append("### ⓿ 本节原文形态（来自上财 §%s，跨项目固定）" % sec_id)
    L.append("")
    L.append(form_text.strip("\n"))
    L.append("")
    L.append("\n".join(b))
    L.append("")
    L.append("### ① 形节点（本节槽位清单，%d 个）" % len(registry.order))
    L.append("")
    L.append("> 本节所有必须填的节点。`来源类型` 决定填不上时该找谁："
             "CUSTOMER=问客户，STANDARD=去标准库查，COMPUTED=按 ② 算式算，JUDGMENT=提示用户决策。")
    L.append("")
    L.append(render_slot_table(registry, filled=False))
    L.append("")
    L.append("**槽位统计**：总数 %d；⓿b 内出现 %d；仅节点表/规则出现 %d。"
             % (len(registry.order),
                sum(1 for n in registry.order if any(p.startswith("⓿b") for p in registry.slots[n].places)),
                sum(1 for n in registry.order if not any(p.startswith("⓿b") for p in registry.slots[n].places))))
    L.append("")
    L.append("### ② 必须写的算式（形，跨项目固定）")
    L.append("")
    rule_text = (blocks.get("②") or "").strip()
    rule_text = re.sub(r"^###\s*②[^\n]*\n?", "", rule_text).strip("\n")
    L.append(rule_text if rule_text else "_（本节无计算规则；按原文表格关系复算。）_")
    L.append("")
    L.append("### ③ 本节必须覆盖（from must_cover，跨项目固定）")
    L.append("")
    cover = parse_must_cover(blocks.get("⑧") or "")
    if cover:
        for i, x in enumerate(cover, 1):
            L.append("%d. %s" % (i, x))
    else:
        L.append("1. 按 ⓿b 的 %d 段与 %d 张表逐项覆盖，不漏段、不漏表。" % (len(paras), len(tables)))
    L.append("")
    L.append("### ④ 证据要求（跨项目固定）")
    L.append("")
    ev = (blocks.get("③") or "").strip()
    ev = re.sub(r"^###\s*③[^\n]*\n?", "", ev).strip("\n")
    L.append(ev if ev else "fact×0（按原文证据要求；E1 注明提供方与日期，E2 带标准号+条款号）")
    L.append("")
    L.append("### ⑤ 篇幅（跨项目固定）")
    L.append("")
    ln = (blocks.get("④") or "").strip()
    ln = re.sub(r"^###\s*④[^\n]*\n?", "", ln).strip("\n")
    L.append(ln if ln else "按本节内容项数决定篇幅，每项 150-300 字。")
    L.append("")
    L.append("### ⑥ 返回契约（跨项目固定）")
    L.append("")
    ct = (blocks.get("⑥") or "").strip()
    ct = re.sub(r"^###\s*⑥[^\n]*\n?", "", ct).strip("\n")
    L.append(ct if ct else '```json\n{"body":"Markdown，每数写〔P-xxx〕","node_mentions":[],"new_claims":[],"unresolved":[]}\n```')
    L.append("")
    L.append("> 模板结束。本文件不含任何项目值；所有槽位由 `evo_fill_slots` 填充。")
    L.append("")
    return "\n".join(L), registry


# ================================================================ 批量


def build_templates(prompt_path, normalized_path, out_dir, *, graph_path=None,
                    aliases_path=None, rules_path=None, only_ids=None):
    prompt_sections = parse_prompt_file(prompt_path)
    md = Path(normalized_path).read_text(encoding="utf-8") if normalized_path and Path(normalized_path).exists() else ""
    sources = extract_sources(md, prompt_sections) if md else {}
    graph = None
    if graph_path and Path(graph_path).exists():
        graph = GraphIndex(json.loads(Path(graph_path).read_text(encoding="utf-8")),
                           aliases_path=aliases_path, rules_path=rules_path)
    canon_aliases, alias_to_canon = load_aliases(aliases_path)
    rules = (graph.rules if graph else {})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for sec in prompt_sections:
        if only_ids and sec["id"] not in only_ids:
            continue
        src = sources.get(sec["id"])
        if not src or not src.get("found"):
            index.append({"id": sec["id"], "title": sec["title"], "template": None,
                          "error": "源原文未找到（按标题名称）"})
            continue
        text, registry = render_template(sec, src, graph=graph,
                                         rules=[], aliases=alias_to_canon)
        fp = out / ("%s.md" % sec["id"])
        fp.write_text(text, encoding="utf-8")
        slots = [registry.slots[n].as_dict() for n in registry.order]
        (out / ("_slots-%s.json" % sec["id"])).write_text(
            json.dumps({"section": sec["id"], "title": sec["title"],
                        "slots": slots}, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append({"id": sec["id"], "title": sec["title"], "template": fp.name,
                      "slots": len(slots), "paras": len(src.get("paras") or []),
                      "tables": len(src.get("tables") or [])})
    (out / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    return index


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成含槽位的提示词模板")
    ap.add_argument("--prompt", default="提示词-还原-119节全量.md")
    ap.add_argument("--normalized", default="SHUFE-BDC-2019-001/source/normalized.md")
    ap.add_argument("--out", default="prompt-templates")
    ap.add_argument("--graph", default="GRAPH-新项目-华东理工AI研究院-merged.json")
    ap.add_argument("--aliases", default="形-可复用知识资产-v1.0/ontology/fact-aliases.yaml")
    ap.add_argument("--rules", default="形-可复用知识资产-v1.0/functions/derivation_templates.yaml")
    ap.add_argument("--sections", default="", help="逗号分隔节号，如 1.1,7.2.2,13.3")
    args = ap.parse_args(argv)
    only = [s.strip() for s in args.sections.split(",") if s.strip()] or None
    idx = build_templates(args.prompt, args.normalized, args.out,
                          graph_path=args.graph, aliases_path=args.aliases,
                          rules_path=args.rules, only_ids=only)
    for x in idx:
        print("%-8s %-40s slots=%s paras=%s tables=%s %s" % (
            x.get("id"), x.get("title", "")[:38], x.get("slots"),
            x.get("paras"), x.get("tables"), x.get("error", "")))


if __name__ == "__main__":
    main()
