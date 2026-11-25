# -*- coding: utf-8 -*-
"""evo_slot_schema —— 可研报告提示词模板的槽位分层与自检。

本模块解决两个根因问题：

1. **槽位粒度**：不是按「数字/非数字」分层，而是按「值是否唯一」分层。
   - L1n  数值单值：一个数、一个单位、一个口径，可闭合/可复算。
   - L1t  文本单值：一个实体/名称/地址/日期/标准号，值唯一。
   - L2   项级占位：数量或结构不定（0..N），只规定必须覆盖什么。
   - L3   论证占位：需要推理/检索，规定论证目标、证据要求、禁止借用。
   `{{X}}` 只允许 L1；`【X】` 用于 L2/L3。

2. **模板纯净度**：模板只能借「形」，不能借「值」。
   本模块的 validate 会检查项目真值泄漏、数量不定却做成 L1、
   L2/L3 缺少三句契约、正文里的裸数字/算式等问题。

用法：
    python -I evo_slot_schema.py validate path/to/1.1.md
    python -I evo_slot_schema.py validate path/to/1.1.md --json
    python -I evo_slot_schema.py classify path/to/section.md --title 项目概况
    python -I evo_slot_schema.py selftest

设计原则：
- 只做确定性检查，不读网络、不调 LLM、不写死项目值。
- 检查项可解释：每个 issue 带 code / line / detail。
- 失败时返回非 0，可直接进 CI。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = "2.0"

# ---------------------------------------------------------------------------
# 分层常量
# ---------------------------------------------------------------------------

LAYER_L1N = "L1n"   # 数值单值
LAYER_L1T = "L1t"   # 文本单值
LAYER_L2 = "L2"     # 项级占位（数量/结构不定）
LAYER_L3 = "L3"     # 论证占位（推理/检索）
LAYER_L0 = "L0"     # 结构骨架（非槽位）

VALID_LAYERS = {LAYER_L1N, LAYER_L1T, LAYER_L2, LAYER_L3, LAYER_L0}

CONTENT_TYPES = {
    "A": "数值节：数字、可计算、有闭合关系",
    "B": "清单节：列举，数量不定",
    "C": "叙述节：描述性文字，结构不固定",
    "D": "论证节：论点+论据，需推理",
    "E": "流程节：步骤/时序/组织/措施",
    "F": "法规节：引用条款/标准/依据",
    "G": "容器节：只含子节或导语，不单独出模板",
}

UNIVERSALITY = {
    "U0": "法定/体裁：2023 法定大纲或体裁决策逻辑直接要求，单样本即可确认",
    "U1": "体裁推定：大纲未逐字列出，但可研决策逻辑必需，单样本可推定",
    "U2": "类通用候选：与项目类型绑定，需 >=3 份同类样本确认；单样本只标待验证",
    "U3": "项目专属：具体名称/数值/方位/日期/机构，不进模板",
}

# ---------------------------------------------------------------------------
# 项目真值黑名单（上财 2019）
# 说明：模板里出现这些词/数，说明「借形」变成了「借值」。
# ---------------------------------------------------------------------------

PROJECT_TRUTH_TERMS: Dict[str, Sequence[str]] = {
    "number": (
        "13032", "13,032", "18319", "18,319", "11188", "11,188",
        "1171", "1,171", "618", "2758", "2,758", "7793", "7,793",
        "18000", "18,000", "319", "6000", "6,000", "7032", "7,032",
        "55万元", "24个月", "2020年7月", "2022年06月", "2022年6月",
    ),
    "direction": ("东部", "西侧", "北侧", "南侧", "东侧"),
    "building": ("第五教学楼", "教育中心", "便利店", "下沉式广场", "图书馆"),
    "funding_source": ("国拨资金", "学校自筹"),
    "organization": (
        "上海财经大学", "中山北一路", "大数据研究中心", "统计与管理学院",
        "管理科学与量化信息研究中心", "理论计算机研究中心",
        "应用统计研究中心", "数据科研与统计研究院",
    ),
    "place": ("虹口区", "赤峰路", "广秀路", "广灵一路", "广灵二路", "广灵二路"),
}

# L1 名称里出现这些词，说明它大概率不是单值（数量/结构不定）。
L1_MULTI_PATTERNS: Sequence[Tuple[str, str]] = (
    (r"[0-9]+$", "名称带序号（如 相邻建筑1 / 资金来源1），数量不定"),
    (r"[0-9]+\s*[.．、~～-]\s*[0-9Nn]", "名称是区间/序列（如 1..N），数量不定"),
    (r"列表|清单|构成|来源|相邻|各|若干|多个|系列|明细", "名称表示集合/列举，数量不定"),
    (r"描述", "名称表示结构不定的描述段落"),
    (r"对象$", "对象可能是 0..N 个，应按 L2 处理"),
    (r"内容$", "内容通常是清单/段落集合，应按 L2 处理"),
    (r"机构$", "机构通常是 0..N 个，应按 L2 处理"),
)

# 这些 L1 名称即使“看起来是单值”，也不应单独做槽位：
# 它们是「借值高风险」字段，必须放进 L2/L3 的覆盖要求里。
L1_BORROW_SENSITIVE = {
    "方位": "方位是位置描述的一部分，应放进【项目位置】L2，且禁止借用其他项目方位",
    "四至": "四至是结构不定的描述，应放进【项目位置】L2",
    "四至描述": "四至描述结构不定，应放进【项目位置】L2",
    "相邻建筑": "相邻建筑数量不定，应放进【项目位置】L2",
    "配套条件": "配套条件是项集，应放进【周边配套条件】L2",
    "配套条件描述": "配套条件描述结构不定，应放进【周边配套条件】L2",
    "拆除对象": "拆除对象可能是 0..N 个，应放进【拆除工程】L2",
    "资金来源": "资金来源数量不定，应放进【资金来源构成】L2",
}

# L2/L3 定义块必须出现的行（C4 三句 + 层级）。
REQUIRED_L2_LINES = ("层级", "本项须覆盖", "禁止", "若客户未给")
REQUIRED_L3_EXTRA = ("证据要求",)
L3_SEARCH_HINTS = ("检索", "推理")

# 正文骨架中不允许出现的算式/裸数字（校验规则区不算正文）。
BODY_FORMULA_MARKERS = ("=", "round(", "×", "÷", "＋", "＝")
BODY_BARE_NUMBER_RE = re.compile(r"(?<![\w{〔【])\d[\d,]{2,}(?:\.\d+)?")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    code: str
    message: str
    line: int = 0
    detail: str = ""
    severity: str = "error"  # error | warning

    def as_dict(self):
        return asdict(self)


@dataclass
class ValidationResult:
    path: str
    issues: List[Issue] = field(default_factory=list)
    l1_count: int = 0
    l2_count: int = 0
    l3_count: int = 0
    slot_names: List[str] = field(default_factory=list)
    placeholder_names: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def as_dict(self):
        return {
            "path": self.path,
            "ok": self.ok,
            "schema_version": SCHEMA_VERSION,
            "l1_count": self.l1_count,
            "l2_count": self.l2_count,
            "l3_count": self.l3_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "slot_names": self.slot_names,
            "placeholder_names": self.placeholder_names,
            "issues": [i.as_dict() for i in self.issues],
        }


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def _read(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _iter_lines(text: str) -> Iterable[Tuple[int, str]]:
    for i, line in enumerate(text.splitlines(), 1):
        yield i, line


def _split_table_row(line: str) -> List[str]:
    s = line.strip()
    if not s.startswith("|"):
        return []
    return [c.strip() for c in s.strip("|").split("|")]


def _is_table_sep(line: str) -> bool:
    s = line.strip()
    return bool(re.match(r"^\|[\s\-:|]+\|$", s))


def _clean_md(s: str) -> str:
    s = re.sub(r"`", "", s)
    s = re.sub(r"\*\*", "", s)
    return s.strip()


def _line_of(text: str, needle: str) -> int:
    for i, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return i
    return 0


# ---------------------------------------------------------------------------
# 模板解析
# ---------------------------------------------------------------------------

SLOT_RE = re.compile(r"\{\{([^{}\n]+?)\}\}")
PLACEHOLDER_RE = re.compile(r"【([^【】\n]+?)】")
DEF_HEAD_RE = re.compile(r"^###\s+【([^】]+)】\s*$")

# 模板里用来解释语法的元示例，不是真实槽位。
META_TOKENS = {"X", "L2", "L3", "槽位", "字段名", "占位名"}


def extract_slots(text: str) -> List[Tuple[int, str, str]]:
    """返回 [(line, name, context)]，跳过表格行和定义标题行。"""
    out = []
    for ln, line in _iter_lines(text):
        if line.strip().startswith("|"):
            continue
        if DEF_HEAD_RE.match(line.strip()):
            continue
        for m in SLOT_RE.finditer(line):
            name = m.group(1).strip()
            if name in META_TOKENS:
                continue
            out.append((ln, name, line.strip()[:220]))
    return out


def extract_placeholders(text: str) -> List[Tuple[int, str, str]]:
    """返回 [(line, name, context)]，跳过表格行和定义标题行。"""
    out = []
    for ln, line in _iter_lines(text):
        if line.strip().startswith("|"):
            continue
        if DEF_HEAD_RE.match(line.strip()):
            continue
        for m in PLACEHOLDER_RE.finditer(line):
            name = m.group(1).strip()
            if name in META_TOKENS:
                continue
            out.append((ln, name, line.strip()[:220]))
    return out


def parse_l1_table(text: str) -> Dict[str, Dict[str, str]]:
    """解析 L1 槽位表。

    表头必须含「槽位」「层」；首列形如 `{{项目名称}}`。
    返回 {name: {layer, unit, source, closure, condition, missing, line}}。
    """
    rows: Dict[str, Dict[str, str]] = {}
    lines = text.splitlines()
    in_table = False
    header: List[str] = []
    for idx, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("|") and "槽位" in s and "层" in s:
            in_table = True
            header = [_clean_md(c) for c in _split_table_row(s)]
            continue
        if in_table:
            if not s.startswith("|"):
                in_table = False
                header = []
                continue
            if _is_table_sep(s):
                continue
            cells = [_clean_md(c) for c in _split_table_row(s)]
            if not cells:
                continue
            m = SLOT_RE.search(cells[0])
            if not m:
                continue
            name = m.group(1).strip()
            row = {"line": str(idx)}
            for j, key in enumerate(header[1:], 1):
                if j < len(cells):
                    row[key] = cells[j]
            # 兼容英文/中文列名
            row["layer"] = row.get("层") or row.get("层级") or row.get("layer", "")
            row["unit"] = row.get("单位") or row.get("unit", "")
            row["source"] = row.get("来源") or row.get("source", "")
            row["closure"] = row.get("闭合/校验") or row.get("闭合") or row.get("校验") or ""
            row["condition"] = row.get("适用条件") or row.get("条件") or ""
            row["missing"] = row.get("若缺") or row.get("缺失") or ""
            rows[name] = row
    return rows


def parse_placeholder_blocks(text: str) -> Dict[str, Dict[str, object]]:
    """解析 `### 【名称】` 定义块及其后的 `>` 引用行。"""
    blocks: Dict[str, Dict[str, object]] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = DEF_HEAD_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        name = m.group(1).strip()
        start_line = i + 1
        body: List[str] = []
        j = i + 1
        while j < len(lines):
            s = lines[j].strip()
            if s.startswith(">"):
                body.append(s.lstrip(">").strip())
                j += 1
                continue
            if s == "":
                j += 1
                # 允许一个空行，但遇到下一个标题/正文即停
                if j < len(lines) and (lines[j].strip().startswith("#") or not lines[j].strip().startswith(">")):
                    break
                continue
            break
        layer_raw = _extract_field(body, "层级")
        lm = re.match(r"(L[0-3][a-z]?)", layer_raw)
        blocks[name] = {
            "line": start_line,
            "lines": body,
            "layer_raw": layer_raw,
            "layer": lm.group(1) if lm else layer_raw,
            "cover": _extract_field(body, "本项须覆盖"),
            "forbidden": _extract_field(body, "禁止"),
            "missing": _extract_field(body, "若客户未给"),
            "evidence": _extract_field(body, "证据要求"),
            "search": _extract_field(body, "检索要求") or _extract_field(body, "检索") or _extract_field(body, "推理要求"),
            "raw": "\n".join(body),
        }
        i = j
    return blocks


def _extract_field(body: Sequence[str], key: str) -> str:
    for s in body:
        # 允许 **层级**：L2 / 层级：L2 / - 层级：L2
        t = re.sub(r"^[\-\*\s]+", "", s)
        t = re.sub(r"\*\*", "", t)
        if t.startswith(key):
            return t[len(key):].lstrip("：: ").strip()
    return ""


def body_fence(text: str) -> str:
    """取「正文骨架」下的第一个 markdown 代码块；找不到则取第一个代码块。"""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if "正文骨架" in line:
            start = i
            break
    if start is None:
        start = 0
    in_fence = False
    buf: List[str] = []
    for line in lines[start:]:
        if line.strip().startswith("```"):
            if not in_fence:
                in_fence = True
                buf = []
                continue
            else:
                return "\n".join(buf)
        if in_fence:
            buf.append(line)
    return "\n".join(buf)


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def check_project_truths(text: str) -> List[Issue]:
    issues: List[Issue] = []
    seen = set()
    for category, terms in PROJECT_TRUTH_TERMS.items():
        for term in terms:
            if term in seen:
                continue
            for ln, line in _iter_lines(text):
                if term in line:
                    issues.append(Issue(
                        code="PROJECT_TRUTH",
                        message=f"模板出现上财项目真值（{category}）：{term}",
                        line=ln,
                        detail=line.strip()[:220],
                    ))
                    seen.add(term)
                    break
    return issues


def check_l1_names(name: str, line: int) -> List[Issue]:
    issues: List[Issue] = []
    if not name:
        issues.append(Issue("L1_EMPTY", "L1 槽位名为空", line))
        return issues
    for prefix, why in L1_BORROW_SENSITIVE.items():
        if name == prefix or name.startswith(prefix):
            issues.append(Issue(
                "L1_BORROW_SENSITIVE",
                f"`{{{{{name}}}}}` 是借值高风险字段：{why}",
                line,
            ))
            break
    for pat, why in L1_MULTI_PATTERNS:
        if re.search(pat, name):
            issues.append(Issue(
                "L1_MULTI",
                f"`{{{{{name}}}}}` 数量/结构不定，不应做 L1：{why}",
                line,
            ))
            break
    return issues


def check_body(body: str) -> List[Issue]:
    issues: List[Issue] = []
    for ln, line in _iter_lines(body):
        s = line.strip()
        if not s:
            continue
        # 只检查正文行（允许引用行说明）
        if s.startswith(">"):
            continue
        if any(marker in s for marker in BODY_FORMULA_MARKERS):
            issues.append(Issue(
                "BODY_FORMULA",
                "正文骨架出现算式/等号；算式应放在「校验规则（不写入正文）」",
                ln,
                s[:220],
            ))
        # 去除槽位后再找裸数字
        stripped = SLOT_RE.sub("", s)
        for m in BODY_BARE_NUMBER_RE.finditer(stripped):
            issues.append(Issue(
                "BODY_BARE_NUMBER",
                f"正文骨架出现裸数字 `{m.group(0)}`；数据值必须走 L1 槽位",
                ln,
                s[:220],
            ))
            break
    return issues


def validate_template(path: str | Path) -> ValidationResult:
    text = _read(path)
    res = ValidationResult(path=str(path))

    # 0) 版本标记（warning，不阻断）
    if "evo-slot-schema" not in text:
        res.issues.append(Issue(
            "SCHEMA_MARKER_MISSING",
            "缺少 `<!-- evo-slot-schema: v2 -->` 标记，无法确认模板版本",
            severity="warning",
        ))

    # 1) 项目真值
    res.issues.extend(check_project_truths(text))

    # 2) L1 表 + 声明
    l1_table = parse_l1_table(text)
    res.l1_count = len(l1_table)
    slot_occ = extract_slots(text)
    slot_names = []
    for ln, name, ctx in slot_occ:
        if name not in slot_names:
            slot_names.append(name)
        if name not in l1_table:
            res.issues.append(Issue(
                "L1_UNDECLARED",
                f"`{{{{{name}}}}}` 未在「L1 单值槽位」表中声明",
                ln,
                ctx,
            ))
        res.issues.extend(check_l1_names(name, ln))
    res.slot_names = slot_names
    for name, row in l1_table.items():
        layer = (row.get("layer") or "").strip()
        if layer not in (LAYER_L1N, LAYER_L1T):
            res.issues.append(Issue(
                "L1_LAYER_INVALID",
                f"`{{{{{name}}}}}` 的层是 `{layer}`，L1 只能是 L1n/L1t",
                int(row.get("line", 0)),
            ))
        if layer == LAYER_L1N and not (row.get("unit") or "").strip():
            res.issues.append(Issue(
                "L1_UNIT_MISSING",
                f"`{{{{{name}}}}}` 是 L1n 但单位为空",
                int(row.get("line", 0)),
            ))

    # 3) L2/L3 定义块
    blocks = parse_placeholder_blocks(text)
    placeholder_occ = extract_placeholders(text)
    pnames = []
    for ln, name, ctx in placeholder_occ:
        if name not in pnames:
            pnames.append(name)
        if name not in blocks:
            res.issues.append(Issue(
                "L2_UNDECLARED",
                f"`【{name}】` 未找到 `### 【{name}】` 定义块",
                ln,
                ctx,
            ))
        if name in l1_table:
            res.issues.append(Issue(
                "L2_SHOULD_BE_L1",
                f"`【{name}】` 是单值，应该用 `{{{{{name}}}}}`（L1）",
                ln,
                ctx,
            ))
    res.placeholder_names = pnames

    for name, block in blocks.items():
        layer = str(block.get("layer") or "").strip()
        ln = int(block.get("line", 0))
        if layer not in (LAYER_L2, LAYER_L3):
            res.issues.append(Issue(
                "L2_LAYER_INVALID",
                f"`【{name}】` 的层是 `{layer}`，L2/L3 定义块只能是 L2 或 L3",
                ln,
            ))
        if layer == LAYER_L2:
            res.l2_count += 1
        elif layer == LAYER_L3:
            res.l3_count += 1
        for label, key in (
            ("层级", "layer"),
            ("本项须覆盖", "cover"),
            ("禁止", "forbidden"),
            ("若客户未给", "missing"),
        ):
            if not str(block.get(key) or "").strip():
                res.issues.append(Issue(
                    "L2_CONTRACT_MISSING",
                    f"`【{name}】` 缺少「{label}」",
                    ln,
                ))
        if layer == LAYER_L3:
            for label, key in (("证据要求", "evidence"),):
                if not str(block.get(key) or "").strip():
                    res.issues.append(Issue(
                        "L3_EVIDENCE_MISSING",
                        f"`【{name}】` 是 L3，缺少「{label}」",
                        ln,
                    ))
            search = str(block.get("search") or "")
            if not search:
                res.issues.append(Issue(
                    "L3_SEARCH_MISSING",
                    f"`【{name}】` 是 L3，缺少「检索要求」/「推理要求」",
                    ln,
                ))
            elif not any(h in search for h in L3_SEARCH_HINTS):
                res.issues.append(Issue(
                    "L3_SEARCH_WEAK",
                    f"`【{name}】` 的检索要求未出现「检索」或「推理」",
                    ln,
                ))

    # 4) 正文骨架：算式/裸数字
    body = body_fence(text)
    if body.strip():
        res.issues.extend(check_body(body))
    else:
        res.issues.append(Issue(
            "BODY_MISSING",
            "未找到「正文骨架」代码块",
            severity="warning",
        ))

    # 5) 重复槽位名
    dup = {n for n in slot_names if slot_names.count(n) > 1}
    # 重复出现是正常的（正文多次引用），只在 L1 表内重复才算错
    # 这里检查 L1 表解析是否覆盖了所有名称；重复出现不报。

    return res


# ---------------------------------------------------------------------------
# 内容类型分类器（供「识别新报告」流程使用）
# ---------------------------------------------------------------------------

_CALC_MARKERS = (
    "合计", "总计", "经测算", "计算", "折算", "单位造价", "负荷", "指标",
    "占比", "占", "率", "万元", "㎡", "kWh", "kW", "估算", "投资",
)
_ARG_MARKERS = (
    "必要性", "合理性", "可行性", "论证", "分析", "结论", "建议", "效益",
    "风险", "影响", "评价", "意义", "作用", "有利于", "因此", "由于",
    "鉴于", "综上", "依据", "证明",
)
_PROC_MARKERS = (
    "进度", "实施", "组织", "管理", "招标", "流程", "阶段", "程序", "措施",
    "方案", "计划", "工期", "建设期", "运营期", "施工期", "步骤",
)
_DESC_MARKERS = (
    "概况", "简介", "沿革", "条件", "设计", "布局", "系统", "采用", "设置",
    "位于", "包括", "主要为", "分别为", "本项目",
)
_TITLE_PRIORS = {
    "A": ("技术经济指标", "主要技术指标", "投资估算", "资金筹措", "能耗指标",
          "负荷估算", "财务状况", "估算说明", "规模分析", "等级判断"),
    "B": ("主要设备", "主要材料", "招标范围", "附件", "清单", "子系统",
          "公共服务配套", "建设内容"),
    "D": ("必要性", "结论", "建议", "风险", "效益", "影响", "评价",
          "节能效果", "合理性"),
    "E": ("实施进度", "组织管理", "过程管理", "运营期管理", "招标组织",
          "招标方式", "节能措施", "保护措施", "防范措施", "卫生防疫"),
    "F": ("编制依据", "设计依据", "用能标准", "评价标准", "设计总说明"),
    "C": ("概况", "简介", "沿革", "条件", "设计", "选址", "布局", "系统"),
}


def _features(text: str) -> Dict[str, float]:
    plain = re.sub(r"```.*?```", "", text, flags=re.S)
    chars = len(re.sub(r"\s", "", plain))
    digits = re.findall(r"\d[\d,]*(?:\.\d+)?", plain)
    nd100 = len(digits) / max(chars, 1) * 100
    ntab = rows = numcells = cells = 0
    for block in re.findall(r"```table\n(.*?)```", text, re.S):
        ntab += 1
        for ln in block.splitlines():
            s = ln.strip()
            if not s.startswith("|") or re.match(r"^\|[\s\-:|]+\|$", s):
                continue
            cs = [c.strip() for c in s.strip("|").split("|")]
            rows += 1
            for c in cs:
                cells += 1
                if re.match(
                    r"^[-+]?\d[\d,]*(?:\.\d+)?\s*(?:%|㎡|m2|m²|万元|元|kW|kWh|m|mm|t|吨|人|部|个|项|年|月|天|小时|h)?$",
                    c,
                ):
                    numcells += 1
    lines = [x for x in plain.splitlines() if x.strip()]
    listlines = len(re.findall(r"^\s*(?:[-*·]|\d+[.、．]|（\d+）|\(\d+\))\s*", plain, re.M))
    cites = re.findall(r"《[^》]{2,40}》", plain)
    codes = re.findall(
        r"(?:GB(?:/T)?|GBJ|JGJ|CJJ|DB\d*|DGJ|HJ|建标|计价格|发改价格|财建|沪价费)\s*[〔\[(]?\d",
        plain,
    )
    return {
        "chars": chars,
        "digits": len(digits),
        "nd100": round(nd100, 2),
        "tables": ntab,
        "rows": rows,
        "numcell_ratio": round(numcells / max(cells, 1), 3),
        "list_ratio": round(listlines / max(len(lines), 1), 3),
        "cites": len(cites),
        "codes": len(codes),
        "arg": len(re.findall("|".join(_ARG_MARKERS), plain)),
        "proc": len(re.findall("|".join(_PROC_MARKERS), plain)),
        "desc": len(re.findall("|".join(_DESC_MARKERS), plain)),
    }


def classify_section(text: str, title: str = "", is_container: bool = False) -> Dict[str, object]:
    """把一节内容分成 A/B/C/D/E/F/G，返回主类型、兼有类型、分数与证据。

    判据是「可执行的特征分」，不是感觉：
    - A 数值：数字密度、数值表比例、计算/闭合词。
    - B 清单：列表行比例、表行数、清单词。
    - D 论证：论证词密度。
    - E 流程：流程词密度。
    - F 法规：标准/条款引用数。
    - C 叙述：描述词密度（默认项）。
    - G 容器：显式 is_container。
    """
    f = _features(text)
    scores = {"A": 0.0, "B": 0.0, "C": 0.9, "D": 0.0, "E": 0.0, "F": 0.0}
    reasons: Dict[str, List[str]] = {k: [] for k in scores}

    # A 数值节
    if f["nd100"] >= 4:
        scores["A"] += 2.0; reasons["A"].append(f"数字密度 {f['nd100']}/100字")
    if f["nd100"] >= 8:
        scores["A"] += 1.0; reasons["A"].append("数字密度 >=8")
    if f["numcell_ratio"] >= 0.35 and f["tables"] >= 1:
        scores["A"] += 2.0; reasons["A"].append(f"数值表比例 {f['numcell_ratio']}")
    if f["rows"] >= 8:
        scores["A"] += 1.0; reasons["A"].append(f"表行数 {f['rows']}")
    if any(m in text for m in _CALC_MARKERS):
        scores["A"] += 1.0; reasons["A"].append("出现计算/合计/指标词")

    # B 清单节
    scores["B"] += min(3.0, f["list_ratio"] * 3.0)
    if f["list_ratio"] >= 0.5:
        reasons["B"].append(f"列表行比例 {f['list_ratio']}")
    if f["rows"] >= 8:
        scores["B"] += 1.0; reasons["B"].append(f"表行数 {f['rows']}")
    if any(k in title for k in _TITLE_PRIORS["B"]):
        scores["B"] += 2.0; reasons["B"].append("标题含清单/设备/范围词")

    # D 论证节
    scores["D"] += min(4.0, f["arg"] / 4.0)
    if f["arg"] >= 4:
        reasons["D"].append(f"论证词 {f['arg']}")
    if any(k in title for k in _TITLE_PRIORS["D"]):
        scores["D"] += 3.0; reasons["D"].append("标题含必要性/结论/风险/效益词")

    # E 流程节
    scores["E"] += min(4.0, f["proc"] / 5.0)
    if f["proc"] >= 5:
        reasons["E"].append(f"流程词 {f['proc']}")
    if any(k in title for k in _TITLE_PRIORS["E"]):
        scores["E"] += 3.0; reasons["E"].append("标题含措施/管理/进度/招标词")

    # F 法规节
    scores["F"] += min(3.0, f["cites"] / 2.0) + min(2.0, f["codes"] / 2.0)
    if f["cites"] >= 2 or f["codes"] >= 2:
        reasons["F"].append(f"引用 {f['cites']} / 标准号 {f['codes']}")
    if any(k in title for k in _TITLE_PRIORS["F"]):
        scores["F"] += 3.0; reasons["F"].append("标题含依据/标准/规范词")

    # C 叙述
    scores["C"] += min(2.0, f["desc"] / 12.0)
    if f["desc"] >= 6:
        reasons["C"].append(f"描述词 {f['desc']}")

    # 标题先验补分（A/C）
    if any(k in title for k in _TITLE_PRIORS["A"]):
        scores["A"] += 2.0; reasons["A"].append("标题含投资/指标/负荷/财务词")
    if any(k in title for k in _TITLE_PRIORS["C"]):
        scores["C"] += 1.0; reasons["C"].append("标题含概况/条件/设计/选址词")

    # 纯容器
    if is_container:
        return {
            "primary": "G",
            "secondary": [],
            "scores": {k: round(v, 2) for k, v in scores.items()},
            "features": f,
            "reasons": {"G": ["章节级容器，含子节或仅为导语"]},
            "confidence": "high",
        }

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    primary, top = ranked[0]
    second, second_score = ranked[1]
    # 兼有：分数达到主类型 70% 且 >=2.5
    secondary = []
    for k, v in ranked[1:]:
        if v >= max(2.5, top * 0.7):
            secondary.append(k)
    margin = top - second_score
    confidence = "high" if margin >= 1.5 else ("medium" if margin >= 0.6 else "low")
    return {
        "primary": primary,
        "secondary": secondary[:2],
        "scores": {k: round(v, 2) for k, v in scores.items()},
        "features": f,
        "reasons": {k: v for k, v in reasons.items() if v},
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_validate(args) -> int:
    res = validate_template(args.path)
    if args.json:
        print(json.dumps(res.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"模板：{res.path}")
        print(f"L1={res.l1_count}  L2={res.l2_count}  L3={res.l3_count}  "
              f"errors={res.error_count}  warnings={res.warning_count}")
        if res.ok:
            print("结果：PASS")
        else:
            print("结果：FAIL")
        for i in res.issues:
            loc = f" line {i.line}" if i.line else ""
            print(f"  [{i.severity.upper()}] {i.code}{loc}: {i.message}")
            if i.detail:
                print(f"        {i.detail}")
    return 0 if res.ok else 1


def _cmd_classify(args) -> int:
    text = _read(args.path)
    result = classify_section(text, title=args.title, is_container=args.container)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_selftest(args) -> int:
    """内置三组反例，确认校验器能抓住最常见的三类错误。"""
    import tempfile

    bad = {
        "bad_multi_slot.md": """<!-- evo-slot-schema: v2 -->
# bad
## 正文骨架
```markdown
本项目相邻建筑为{{相邻建筑1}}。
```
## L1 单值槽位
| 槽位 | 层 | 单位 | 来源 | 闭合/校验 | 适用条件 | 若缺 |
|---|---|---|---|---|---|---|
| {{相邻建筑1}} | L1t | — | 客户 | 单值 | 所有 | 待客户 |
""",
        "bad_direction.md": """<!-- evo-slot-schema: v2 -->
# bad
## 正文骨架
```markdown
本项目位于校区东部。
```
""",
        "bad_funding.md": """<!-- evo-slot-schema: v2 -->
# bad
## 正文骨架
```markdown
建设资金由{{资金来源1}}解决。
```
## L1 单值槽位
| 槽位 | 层 | 单位 | 来源 | 闭合/校验 | 适用条件 | 若缺 |
|---|---|---|---|---|---|---|
| {{资金来源1}} | L1n | 万元 | 客户 | 单值 | 所有 | 待客户 |
""",
    }
    tmp = Path(tempfile.mkdtemp(prefix="evo-slot-selftest-"))
    failed = 0
    expect = {
        "bad_multi_slot.md": ("L1_MULTI", "L1_BORROW_SENSITIVE"),
        "bad_direction.md": ("PROJECT_TRUTH",),
        "bad_funding.md": ("L1_MULTI",),
    }
    for fn, body in bad.items():
        p = tmp / fn
        p.write_text(body, encoding="utf-8")
        res = validate_template(p)
        codes = {i.code for i in res.issues}
        ok = all(c in codes for c in expect[fn])
        print(f"{fn}: {'PASS' if ok else 'FAIL'}  issues={sorted(codes)}")
        if not ok:
            failed += 1
    print(f"selftest: {'PASS' if failed == 0 else 'FAIL'} ({len(bad) - failed}/{len(bad)})")
    return 0 if failed == 0 else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="可研模板槽位分层与自检")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate", help="校验模板")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("classify", help="给一节文本分类 A/B/C/D/E/F/G")
    p.add_argument("path")
    p.add_argument("--title", default="")
    p.add_argument("--container", action="store_true")
    p.set_defaults(func=_cmd_classify)

    p = sub.add_parser("selftest", help="跑内置反例")
    p.set_defaults(func=_cmd_selftest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
