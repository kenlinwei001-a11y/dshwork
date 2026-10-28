# -*- coding: utf-8 -*-
"""md_facts —— 把「客户提供的 MD」转成 instantiate_project 要的 provided_facts。

设计原则（工具 + LLM 分层）：
  · 表格行、编号列表这类**结构明确**的 -> 确定性正则抽取，零 LLM；
  · 散落在正文叙述里的事实 -> 输出 candidates 供 LLM 二次抽取，脚本不猜。

输出 schema（与 instantiate_project 对齐）：
  [{label, value, unit, caliber, as_of, kind}]

拒绝行为：
  · 值不是数字且不像日期/文本 -> 不产出；
  · 同名多次出现且值不同 -> 产出 conflicts，不取其一；
  · 单位缺失 -> unit 置 ""，并在 warnings 记录。
"""
from __future__ import annotations
import re
from pathlib import Path

_NUM = r"[+-]?\d[\d,]*(?:\.\d+)?"
_UNIT = r"(?:万元|亿元|元|㎡|m2|平方米|m³|m3|立方米|m|米|mm|kW|kWh|kVA|W|L/s|L/人·日|L/人日|"
_UNIT += r"人|台|层|个|处|项|%|d|h|吨标煤|吨|万\s*kWh|万\s*m³|kgce/㎡|元/㎡)"


def _norm(v: str) -> float | str:
    s = str(v).replace(",", "").strip()
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return s


_TREE = re.compile(r"^[\s\u2500-\u257F\u2502\u251C\u2514\u2518\u2510\u250C\u2550\u2551]+")


def _clean_label(s: str) -> str:
    """去掉表格树形前缀（├ │ └ ─ ──）与序号前缀（1. 2、 (1)）。"""
    s = _TREE.sub("", s).strip()
    s = re.sub(r"^[（(]?\d+[）).、]\s*", "", s).strip()
    return s.strip("*：: ").strip()


def parse_tables(text: str) -> list[dict]:
    """从 markdown 表格提取 | 名称 | 数值 | 单位 | 形态的行。"""
    out = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip().strip("*").strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        label = _clean_label(cells[0])
        if not label or set(label) <= {"-", ":", " "}:
            continue
        # 找第一个形如数字的单元格
        for i, c in enumerate(cells[1:], start=1):
            m = re.fullmatch(_NUM, c.replace("*", "").strip())
            if m:
                unit = ""
                if i + 1 < len(cells):
                    u = cells[i + 1].replace("*", "").strip()
                    if re.fullmatch(_UNIT, u):
                        unit = u
                out.append({"label": label, "value": _norm(c.replace("*", "").strip()),
                            "unit": unit, "form": "table_row", "raw": line.strip()[:120]})
                break
    return out


def parse_inline(text: str) -> list[dict]:
    """从正文提取「X 为 Y 单位」/「X = Y 单位」句式。"""
    out = []
    pat = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9·\-（）()]{2,24}?)\s*(?:为|=|：|:)\s*\**(" + _NUM + r")\**\s*(" + _UNIT + r")?")
    for m in pat.finditer(text):
        label = m.group(1).strip("* ").strip()
        if len(label) < 2 or label.startswith(("#", ">", "-", "|")):
            continue
        out.append({"label": label, "value": _norm(m.group(2)),
                    "unit": (m.group(3) or "").strip(), "form": "inline",
                    "raw": text[max(0, m.start() - 20):m.end() + 10].replace("\n", " ")})
    return out


def to_provided_facts(md_path: str | Path, *, default_caliber: str = "客户提供",
                      as_of: str = "") -> dict:
    """主入口。返回 {provided_facts, conflicts, warnings, stats}。"""
    from .cli import read_document
    text, kind = read_document(str(md_path))
    rows = parse_tables(text)
    inl = parse_inline(text)
    allf = rows + inl

    # 别名归一（复用 ontology/fact-aliases.yaml 的概念，这里内置最小集）
    alias = {
        "工程建设其他费": "工程建设其他费用",
        "建安工程费": "建安工程费用", "建安费": "建安工程费用",
        "总建筑面积": "本项目建筑面积", "建筑面积": "本项目建筑面积",
        "年用电量": "年总耗电量", "年耗电量": "年总耗电量",
        "年用水量": "年总用水量", "冷负荷指标": "单位面积冷负荷指标",
        "热负荷指标": "单位面积热负荷指标", "科研用房需求系数": "科研用房需要系数",
    }

    # 单位归一：把同一量纲的不同写法收敛，供规则按固定单位计算
    unit_norm = {
        "m3": "万m³", "m³": "万m³", "立方米": "万m³",
        "kWh": "万kWh", "万kWh": "万kWh", "万千瓦时": "万kWh",
    }
    # 若某值明显是「绝对量」而规则口径是「万」，则换算
    def _align_unit(lab, val, unit):
        if unit in ("m³", "m3", "立方米") and isinstance(val, (int, float)) and val > 1000:
            return round(val / 10000, 2), "万m³", "原值单位为 m³，按规则口径换算为万m³"
        if unit in ("kWh",) and isinstance(val, (int, float)) and val > 10000:
            return round(val / 10000, 2), "万kWh", "原值单位为 kWh，按规则口径换算为万kWh"
        return val, unit_norm.get(unit, unit), ""

    by_label: dict[str, list] = {}
    for f in allf:
        lab = alias.get(f["label"], f["label"])
        by_label.setdefault(lab, []).append(f)

    provided, conflicts, warnings = [], [], []
    for lab, items in by_label.items():
        vals = {str(i["value"]) for i in items}
        if len(vals) > 1:
            conflicts.append({"subject": lab, "values": sorted(vals),
                              "status": "待审", "reason": "同一名称出现多个值，不取其一",
                              "sources": [i["form"] for i in items]})
            continue
        it = items[0]
        if not it["unit"]:
            warnings.append({"label": lab, "issue": "单位缺失", "raw": it["raw"]})
        v2, u2, note = _align_unit(lab, it["value"], it["unit"])
        rec = {"label": lab, "value": v2, "unit": u2,
               "caliber": default_caliber, "as_of": as_of, "kind": "provided"}
        if note:
            rec["unit_conversion"] = note
            warnings.append({"label": lab, "issue": "单位已换算", "detail": note})
        provided.append(rec)

    return {"provided_facts": provided, "conflicts": conflicts, "warnings": warnings,
            "stats": {"source_kind": kind, "chars": len(text),
                      "table_rows": len(rows), "inline": len(inl),
                      "unique_labels": len(by_label), "provided": len(provided),
                      "conflicts": len(conflicts), "warnings": len(warnings)}}
