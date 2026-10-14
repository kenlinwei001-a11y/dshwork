# -*- coding: utf-8 -*-
"""主体归一的【统一推理层】：事实构造 + 规则 + Semantica Reasoner 前向链。

硬要求：需要用 Semantica 的环节就必须用 Semantica。
本模块是归一判定的唯一推理入口；其他脚本只准调用它，不得再内置判定逻辑。

分工：
  本模块     只负责「把领域观察转成事实」与「定义规则」，推理交给 Semantica
  调用方     只负责「消费结论」（confidence 计算、与 LLM 判官合并、写清单）
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

sys_path_note = "调用方需先把本目录加入 sys.path"

CONTRAST = ["净", "名誉", "博士", "硕士", "干球", "湿球", "当量", "等价", "费率", "率",
            "地上", "地下", "室内", "室外", "冷", "热", "进", "出", "含", "不含", "暂定", "待核"]
OPTIONAL = ["用", "等", "约", "上限", "下限", "需求", "合计", "面积需求", "数", "量"]
SYNONYM_PAIRS = [("建设", "建筑安装"), ("费", "费用"), ("建筑面积", "需求建筑面积"),
                 ("使用面积", "面积需求合计"), ("天数", "工作天数"), ("招标估算金额", "费")]

ROLES = [
 # ── [kp 新增] 语义维度：对象角色 / 专业域 / 口径方向 ──────────────────────
 # 依据（客户反馈原文）：「数字都来自同一个事实源，还不足以保证报告正确；
 #   还必须保住数字的**对象、用途、单位和上下级关系**。」
 # 机制：ROLES 参与 `IF SameRole(?a,?b) AND DiffValue(?a,?b) THEN ConflictCandidate`，
 #   因此**新增角色即改变「什么算冲突」**——这是修复 ③⑤ 的正确位置。
 # 顺序敏感：role() 取首个命中，故本组置于表首，优先于 area/load/fee 等泛化词。
 ("role_control", ["高度控制", "控制高度", "限高", "控制值"]),          # ⑤ 控制值
 ("role_actual", ["层高", "推算", "实际", "现状值"]),                   # ⑤ 实际值
 ("role_design", ["设计值", "设计建筑面积", "拟建"]),                   # 设计值
 ("domain_hvac_cool", ["冷负荷", "制冷量", "制冷"]),                    # ③ 暖通·冷负荷
 ("domain_hvac_heat", ["热负荷", "制热量"]),                            # ③ 暖通·热负荷
 ("domain_electric", ["照明", "用电", "配电", "负荷密度", "变压器", "耗电"]),  # ③ 电气·电力
 ("domain_plumbing", ["给水", "排水", "消防水", "用水量", "水泵"]),      # 专业域
 ("domain_structure", ["荷载标准值", "抗震设防", "地基", "桩基"]),       # 专业域
 ("upper_bound", ["不超过", "不大于", "上限", "控制在"]),               # ④ 口径方向
 ("lower_bound", ["不小于", "不低于", "下限", "至少"]),                # ④ 口径方向
 # ── 原有角色（未改动）────────────────────────────────────────────────
 ("grade_fire", ["耐火等级"]), ("grade_safety", ["结构安全等级", "安全等级"]),
 ("grade_seismic", ["抗震设防", "抗震等级"]), ("role_person", ["名誉主任", "主任", "教授", "负责人", "导师"]),
 ("area", ["建筑面积", "使用面积", "面积"]), ("indicator", ["指标上限", "人均", "指标", "定额"]),
 ("standard", ["标准"]), ("fee", ["费用", "费", "金额", "造价"]), ("demand", ["需求", "合计"]),
 ("total", ["总额"]), ("count", ["人数", "数量", "条数", "篇数"]),
 ("period", ["天数", "工期", "时间", "日期", "年限"]), ("state", ["状态"]),
 ("award", ["特等奖", "一等奖", "奖"]), ("project", ["课题", "项目"]),
 ("fund", ["资金", "经费", "投资"]), ("load", ["负荷", "荷载"]), ("rate", ["率", "系数"])]

# 规则：负证据（不同概念）与正证据（同一概念）都声明出来；优先级在消费端按 DIFF > CONFLICT > SAME 解释
RULES = [
 "IF DiffStandardRef(?a,?b) THEN DifferentConcept(?a,?b)",
 "IF DiffYear(?a,?b) THEN DifferentConcept(?a,?b)",
 "IF DiffRole(?a,?b) THEN DifferentConcept(?a,?b)",
 "IF HasDigitDiff(?a,?b) THEN DifferentConcept(?a,?b)",
 "IF HasContrastDiff(?a,?b) THEN DifferentConcept(?a,?b)",
 "IF OptionalOnlyDiff(?a,?b) THEN SameConcept(?a,?b)",
 "IF KnownSynonym(?a,?b) THEN SameConcept(?a,?b)",
 "IF SameValue(?a,?b) AND SameRole(?a,?b) THEN SameConcept(?a,?b)",
 "IF DiffValue(?a,?b) AND SameRole(?a,?b) THEN ConflictCandidate(?a,?b)",
 "IF SameConcept(?a,?b) THEN HumanReview(?a,?b)",
 "IF ConflictCandidate(?a,?b) THEN HumanReview(?a,?b)",
]

def role(x: str) -> str:
    for name, kws in ROLES:
        if any(k in x for k in kws):
            return name
    return "other"

def year(x: str) -> str:
    m = re.search(r"(20\d{2})", x)
    return m.group(1) if m else ""

def stdref(x: str) -> str:
    m = re.search(r"(GB\s*/?\s*T?\s*\d+)", x, re.I)
    return re.sub(r"\s+", "", m.group(1)).upper() if m else ""

def frags(a: str, b: str):
    sm = difflib.SequenceMatcher(None, a, b)
    return [(a[i1:i2], b[j1:j2]) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]

def build_facts(a: str, b: str, sim: float, vals: dict) -> list:
    """把一个主体对转成逻辑事实（纯领域数据，不含判定）。"""
    f = []
    sa, sb = set(vals.get(a, [])), set(vals.get(b, []))
    if sa and sb:
        f.append(("SameValue" if sa == sb else "DiffValue") + "(" + a + "," + b + ")")
    ra, rb = role(a), role(b)
    f.append(("SameRole" if ra == rb and ra != "other" else "DiffRole") + "(" + a + "," + b + ")")
    ya, yb = year(a), year(b)
    if ya and yb and ya != yb:
        f.append("DiffYear(" + a + "," + b + ")")
    ga, gb = stdref(a), stdref(b)
    if ga and gb and ga != gb:
        f.append("DiffStandardRef(" + a + "," + b + ")")
    fa = frags(a, b)
    joined = "".join(x + y for x, y in fa)
    if fa:
        if re.search(r"\d", joined):
            f.append("HasDigitDiff(" + a + "," + b + ")")
        if any(t in joined for t in CONTRAST):
            f.append("HasContrastDiff(" + a + "," + b + ")")
        if all((not x or x in OPTIONAL) and (not y or y in OPTIONAL) for x, y in fa):
            f.append("OptionalOnlyDiff(" + a + "," + b + ")")
        if any((x in p and y in p) or (x in p or y in p) for p in SYNONYM_PAIRS for x, y in fa):
            f.append("KnownSynonym(" + a + "," + b + ")")
    f.append(("SimHigh" if sim >= 0.85 else "SimMid") + "(" + a + "," + b + ")")
    return f

def reason_pairs(pairs, vals, batch: int = 200):
    """调用 Semantica 官方 Reasoner 前向链；返回 (结论集合, 事实集合, 耗时秒, 事实条数)。"""
    import time
    from semantica.reasoning import Reasoner
    from semantica_workflow import semantica_call as _semantica_call
    derived, all_facts, t0, nf = set(), set(), time.time(), 0
    for i in range(0, len(pairs), batch):
        r = Reasoner()
        for a, b, sim in pairs[i:i + batch]:
            ff = build_facts(a, b, sim, vals)
            nf += len(ff)
            for x in ff:
                all_facts.add(x)
                r.add_fact(x)
        for ru in RULES:
            r.add_rule(ru)
        for ir in _semantica_call("reasoning.Reasoner.forward_chain", r.forward_chain):
            derived.add(getattr(ir, "conclusion", str(ir)))
        r.clear()
    return derived, all_facts, round(time.time() - t0, 1), nf

def verdict_from(derived, a: str, b: str) -> str:
    """消费端优先级：DIFF > CONFLICT > SAME > UNKNOWN。"""
    if "DifferentConcept(" + a + "," + b + ")" in derived:
        return "DIFF"
    if "ConflictCandidate(" + a + "," + b + ")" in derived:
        return "CONFLICT"
    if "SameConcept(" + a + "," + b + ")" in derived:
        return "SAME"
    return "UNKNOWN"

def basis_from(derived, facts, a: str, b: str) -> str:
    """依据优先取自【事实】（KnownSynonym/SameValue 等是事实，不是推导结论）。"""
    for tag, name in (("DiffStandardRef", "different_standard_ref"), ("DiffYear", "different_year"),
                      ("DiffRole", "different_role"), ("HasDigitDiff", "different_spec_number"),
                      ("HasContrastDiff", "contrast_token_diff"), ("OptionalOnlyDiff", "optional_suffix_diff"),
                      ("KnownSynonym", "known_synonym"), ("SameValue", "same_value"),
                      ("DiffValue", "diff_value")):
        if tag + "(" + a + "," + b + ")" in facts:  # 事实优先
            return name
    return "insufficient"
