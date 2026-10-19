# -*- coding: utf-8 -*-
"""kp_toolkit.taxonomy —— 标签体系与检索（确定性，零 LLM）

两层标签：
  节点级  taxonomy.yaml           —— 一个值属于哪个专业域（域.主题）
  项目级  project_taxonomy.yaml   —— 一个项目是什么（用途/类型/规模/阶段/专项）

对外：
    load_taxonomy(path)                    -> {dom, {topic, [kws]}}
    tag_text(taxonomy, text, std_hint)     -> "域.主题" | None
    tag_by_unit(unit, value)               -> "域.主题" | None
    query(clauses, domain, topic, code, q) -> [clause]
"""
import re

# 标准编号 → 默认专业域（编号比关键词可靠：GB50016 正文也提"消防"，
# 但它是防火规范，不是消防给水；GB50974 才是消防给水）
STD2DOM = {
    "GB50016": ("消防", None), "GB50974": ("给排水", "消防给水"),
    "GB50084": ("给排水", "消防给水"), "GB50011": ("结构", None),
    "GB50223": ("结构", "抗震设防分类"), "GB50009": ("结构", "荷载"),
    "GB50352": ("建筑", None), "GB50736": ("暖通", None),
    "GB50378": ("绿建", None), "建标191": ("建筑", None),
    "304号": ("管理", None), "发改委令": ("管理", None),
}

# 量纲特征 → 标签（subject 常是"本项目"，只能靠单位判断）
UNIT2TAG = [
    ("度", "结构.地震参数"), ("层", "建筑.层高层数"), ("年", "建筑.使用年限"),
    ("kN/m²", "结构.荷载"), ("h-1", "暖通.室内参数"), ("℃", "暖通.室内参数"),
    ("W/㎡", "暖通.空调负荷"), ("L/s", "给排水.消防给水"), ("m³", "给排水.消防给水"),
    ("L/", "给排水.用水量"), ("㎡", "建筑"), ("m²", "建筑"), ("%", "结构.地震参数"),
]


def load_taxonomy(path):
    import yaml
    d = yaml.safe_load(open(path, encoding="utf-8"))
    return {dom: v["topics"] for dom, v in d["domains"].items()}


def _kw_index(taxonomy):
    idx = []
    for dom, topics in taxonomy.items():
        for topic, kws in topics.items():
            for k in kws: idx.append((k, dom, topic))
    idx.sort(key=lambda x: -len(x[0]))
    return idx


def tag_text(taxonomy, text, std_hint=None):
    """文本 → 标签。标准编号优先定域，关键词定 topic。"""
    idx = _kw_index(taxonomy)
    if std_hint:
        for code, (dom, fixed) in STD2DOM.items():
            if code in str(std_hint):
                if fixed: return f"{dom}.{fixed}"
                for kw, d2, topic in idx:
                    if d2 == dom and kw in text: return f"{dom}.{topic}"
                return None
    for kw, dom, topic in idx:
        if kw in text: return f"{dom}.{topic}"
    return None


def tag_by_unit(unit, value):
    v = str(value or "").strip()
    for uu, tag in UNIT2TAG:
        if uu in str(unit or ""):
            if uu == "度" and not (v.isdigit() and 5 <= int(v) <= 9):
                continue
            return tag
    return None


def query(clauses, domain=None, topic=None, code=None, q=None):
    """按标签/编号/关键词检索条款"""
    out = []
    for c in clauses:
        if domain and not any((t.get("domain") == domain) or
                              str(t.get("tag", "")).startswith(domain + ".")
                              for t in (c.get("tags") or [])):
            continue
        if topic and not any((t.get("topic") == topic) or
                             str(t.get("tag", "")).endswith("." + topic)
                             for t in (c.get("tags") or [])):
            continue
        if code and code not in str(c.get("standard") or c.get("code") or ""):
            continue
        if q and q not in (str(c.get("clause_text") or c.get("text") or "") +
                           str(c.get("clause") or "")):
            continue
        out.append(c)
    return out
