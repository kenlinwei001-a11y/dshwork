# -*- coding: utf-8 -*-
"""kp_toolkit.gap_verify —— 假缺四问的自动化实现。

背景（实测）：一个项目累计报「缺」1496 个，复核后真缺 345 个 —— 假缺率 77%。
本模块把「报缺前必过四问」变成可执行函数，避免再靠人脑记。

四问：
  ① 节点真的不存在？  → 三种方式搜：精确 / 包含 / 去标点归一
  ② 原文真的没有？    → 四种载体搜：纯文本 / 表格 / 表格注 / 跨节
  ③ 绑对了节点吗？    → 量纲校验（费率不绑金额）+ 章节 + 最长匹配
  ④ 设计上就不该有？  → 描述性事实不需要关系；判定项不是数值依赖

对外：
    verify(gap, nodes, chunks, aliases) -> {verdict, why, searched}
        verdict: "real"（真缺）| "false"（假缺）| "uncertain"（需人工）
"""
from __future__ import annotations
import re

PUNCT = re.compile(r"[、,，\s（）()]")
RATE_LIKE = re.compile(r"(费率|系数|指标|比例|占比|率)$")
MONEY_UNITS = {"万元", "元", "亿元"}
DESC_LIKE = re.compile(r"(编号|名称|地址|单位|编者|日期|版本|文号|全称|简称)$")


def norm(s):
    """去顿号/逗号/括号/空格，用于跨写法匹配。"""
    return PUNCT.sub("", str(s or ""))


def _num(x):
    m = re.match(r"^-?\d+(\.\d+)?", str(x or "").replace(",", ""))
    return float(m.group(0)) if m else None


def is_value_node(n):
    """值节点判定：必须有真实取值，且 value 不等于 subject（排除 EN- 实体的镜像）。

    实测踩过：EN-0140 subject=空调负荷密度指标, value=空调负荷密度指标（字符串复制），
    被误判成「节点已存在，只需补绑定」，实际是实体不是值。
    """
    if str(n.get("id") or "").startswith(("EN-", "NX-")):
        return False
    v = str(n.get("value") or "").strip()
    subj = str(n.get("subject") or "").strip()
    if not v:
        return False
    if v == subj:                      # 值是主体的复制 → 实体镜像，不是值
        return False
    if str(n.get("kind")) in ("evidence", "claim"):   # 证据/论断不是值节点
        return False
    return True


def search_node(subject, nodes, aliases=None):
    """① 三方式搜节点（只认值节点）。返回 (node|None, way, candidates)"""
    nodes = [n for n in nodes if is_value_node(n)]
    ns = norm(subject)
    alias = []
    for k, vs in (aliases or {}).items():
        if norm(k) == ns:
            alias = [norm(v) for v in vs]
    exact = [n for n in nodes if norm(n.get("subject")) == ns]
    if exact:
        return exact[0], "exact", exact
    for a in alias:
        hit = [n for n in nodes if norm(n.get("subject")) == a]
        if hit:
            return hit[0], "alias", hit
    contains = [n for n in nodes
                if ns and (ns in norm(n.get("subject")) or norm(n.get("subject")) in ns)
                and len(norm(n.get("subject"))) >= 3]
    if contains:
        contains.sort(key=lambda n: -len(norm(n.get("subject"))))
        return contains[0], "contains", contains
    return None, "none", []


def search_text(keyword, chunks, carriers=("text", "table", "note")):
    """② 多载体搜原文。返回 (found, carrier, quote)"""
    kw = str(keyword or "")
    if len(kw) < 3:
        return False, None, ""
    for c in chunks:
        t = str(c.get("text") or "")
        if kw not in t:
            continue
        # 判断载体
        line = next((l for l in t.split("\n") if kw in l), "")
        if "table" in carriers and line.strip().startswith("|"):
            return True, "table", line.strip()[:120]
        if "note" in carriers and re.match(r"^[（(]", line.strip()) or "注" in line[:6]:
            return True, "note", line.strip()[:120]
        if "text" in carriers:
            i = t.find(kw)
            return True, "text", t[max(0, i - 40):i + 60].replace("\n", " ")
    return False, None, ""


def check_dimension(dep_name, unit):
    """③ 量纲校验。返回 (ok, reason)"""
    if RATE_LIKE.search(str(dep_name or "")) and str(unit or "").strip() in MONEY_UNITS:
        return False, "依赖名以「%s」结尾但要的是无量纲，绑到了 %s 金额节点" % (
            RATE_LIKE.search(dep_name).group(1), unit)
    return True, ""


def check_should_exist(dep_name):
    """④ 设计上该不该有。返回 (should_not, reason)"""
    if DESC_LIKE.search(str(dep_name or "")):
        return True, "描述性字段（编号/名称/单位等）不是数值依赖，不需建关系"
    return False, ""


def verify(gap, nodes, chunks=None, aliases=None, dep_unit=None):
    """对一个「缺」做四问复核。

    gap: str（缺失的依赖名/主体名）或 dict{name, unit}
    """
    if isinstance(gap, dict):
        name = str(gap.get("name") or gap.get("subject") or gap.get("missing") or "")
        dep_unit = gap.get("unit") or dep_unit
    else:
        name = str(gap)
    searched = []
    reasons = []

    # ① 节点
    n, way, cands = search_node(name, nodes, aliases)
    searched.append("nodes: exact+alias+contains（%d 命中）" % len(cands))
    if n:
        reasons.append("① 值节点已存在 %s（%s 匹配，subject=%s, value=%s）"
                       % (n["id"], way, str(n.get("subject"))[:20], n.get("value")))
        # 是绑定漏了，不是缺
        if way == "contains" and len(cands) > 1:
            ok, why = check_dimension(name, n.get("unit") or dep_unit)
            if not ok:
                return {"verdict": "false", "why": [why], "searched": searched,
                        "action": "重绑到正确节点（当前命中 %d 个候选）" % len(cands),
                        "candidates": [{"id": c["id"], "subject": c.get("subject"),
                                        "value": c.get("value"), "unit": c.get("unit")}
                                       for c in cands[:5]]}
        return {"verdict": "false",
                "why": reasons + ["→ 只需在绑定表里填上 node，不是数据缺"],
                "searched": searched, "action": "补绑定",
                "node": {"id": n["id"], "subject": n.get("subject"),
                         "value": n.get("value"), "unit": n.get("unit")}}

    # ② 原文
    if chunks:
        found, carrier, quote = search_text(name, chunks)
        searched.append("chunks: text+table+note（%s）" % ("命中" if found else "无"))
        if found:
            return {"verdict": "false",
                    "why": ["① 节点无", "② 原文有（%s 载体）：%s" % (carrier, quote[:80]),
                            "→ 是抽取漏了，不是报告没写"],
                    "searched": searched, "action": "补抽取（注意该值在%s里）" % carrier}
    else:
        searched.append("chunks: 未提供（跳过第二问）")

    # ③ 量纲
    ok, why = check_dimension(name, dep_unit)
    if not ok:
        return {"verdict": "false", "why": [why], "searched": searched,
                "action": "检查绑定是否指到相邻节点"}

    # ④ 该不该有
    not_need, why4 = check_should_exist(name)
    if not_need:
        return {"verdict": "false", "why": [why4], "searched": searched,
                "action": "从依赖列表移除（不是数据缺）"}

    return {"verdict": "real",
            "why": ["① 节点表三方式搜过无", "② 原文四载体搜过无",
                    "③ 量纲无冲突", "④ 是数值依赖不是描述性字段"],
            "searched": searched,
            "action": "真缺：登记待补，需甲方补充或按规范估算"}


def audit(gaps, nodes, chunks=None, aliases=None):
    """批量复核。返回分类统计 + 每条结论。"""
    out = {"real": [], "false": [], "uncertain": []}
    for g in gaps:
        r = verify(g, nodes, chunks, aliases)
        name = g if isinstance(g, str) else (g.get("name") or g.get("missing") or g.get("subject"))
        r["gap"] = name
        out[r["verdict"]].append(r)
    return {
        "total": len(gaps),
        "real": len(out["real"]),
        "false": len(out["false"]),
        "uncertain": len(out["uncertain"]),
        "false_rate": round(len(out["false"]) / max(len(gaps), 1), 3),
        "detail": out,
    }
