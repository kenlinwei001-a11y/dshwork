# -*- coding: utf-8 -*-
"""kp_toolkit.normalize —— 命名归一化 + 跨写法别名表。

背景（实测）：规则写「通风空调工程」，原文表写「通风、空调工程」——
差一个顿号就判「缺依赖」，一次误报 3 条。

对外：
    norm(s)                       去顿号/逗号/括号/空格
    load_aliases(path)            读别名表
    resolve(name, aliases)        别名 → 规范名
    add_alias(path, canon, variant) 追加别名（遇到新写法就补）
    match_row(cells, name, aliases) 在表格行里找匹配的单元格
"""
from __future__ import annotations
import json
import pathlib
import re

PUNCT = re.compile(r"[、,，\s（）()·]")


def norm(s):
    """归一：去掉顿号、逗号、中英文括号、空格、间隔号。"""
    return PUNCT.sub("", str(s or ""))


def load_aliases(path=None):
    """读别名表。默认 公共标准库/aliases.yaml"""
    if path is None:
        return {}
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    try:
        import yaml
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        d = json.load(open(p, encoding="utf-8"))
    return d.get("aliases") or d


def resolve(name, aliases):
    """把任意写法解析成规范名。找不到就返回原名。"""
    ns = norm(name)
    for canon, variants in (aliases or {}).items():
        if norm(canon) == ns:
            return canon
        if any(norm(v) == ns for v in (variants or [])):
            return canon
    return name


def add_alias(path, canon, variant):
    """追加一条别名（幂等）。遇到新写法就补，别名表是跨项目资产。"""
    import yaml
    p = pathlib.Path(path)
    d = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {"aliases": {}}
    d.setdefault("aliases", {}).setdefault(canon, [])
    if variant not in d["aliases"][canon] and variant != canon:
        d["aliases"][canon].append(variant)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=True, width=200),
                 encoding="utf-8")
    return d["aliases"][canon]


def match_row(cells, name, aliases=None):
    """在一行表格单元里找与 name 等价的单元，返回索引或 None。

    优先精确（归一后），其次别名，最后取「归一后包含」且最长的。
    """
    ns = norm(name)
    cands = []
    for i, c in enumerate(cells or []):
        nc = norm(c)
        if not nc:
            continue
        if nc == ns:
            return i
        if any(norm(v) == nc for v in ((aliases or {}).get(name) or [])):
            return i
        if len(nc) >= 3 and (ns in nc or nc in ns):
            cands.append((len(nc), i))
    if cands:
        cands.sort(reverse=True)
        return cands[0][1]
    return None


# 本项目已实测的别名（可直接写进 公共标准库/aliases.yaml）
SEED = {
    "aliases": {
        "通风空调工程": ["通风、空调工程", "通风空调", "空调通风", "通风与空调工程"],
        "道路广场硬地铺装": ["道路、广场、硬地、铺装", "道路广场", "室外道路", "硬地铺装"],
        "绿化景观": ["绿化、景观", "绿化", "景观绿化"],
        "建筑安装工程费用": ["建筑安装工程费", "建安工程费", "建安费"],
        "工程建设其他费": ["工程建设其他费用"],
        "基本预备费": ["预备费"],
        "原建筑拆除费用": ["拆除费", "原建筑拆除费"],
        "高位消防水箱有效容积": ["高位消防水箱容积", "消防水箱有效容积"],
        "单位面积冷负荷指标": ["单位面积冷负荷", "冷负荷指标"],
        "单位面积热负荷指标": ["单位面积热负荷", "热负荷指标"],
    }
}
