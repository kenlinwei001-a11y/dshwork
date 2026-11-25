# -*- coding: utf-8 -*-
"""evo_devalue_rules —— 定性值去值规则（119 节通用）。

旧去值只覆盖「数字 + 专名」，漏掉定性值：
  - 方位（东部/西侧/北侧…）
  - 四至描述（西侧为绿地，东侧临近…）
  - 配套条件描述（周边供水、供电齐全…）
  - 资金来源（国拨资金及学校自筹）
  - 拆除对象专名（原有第五教学楼）
  - 相邻建筑名（教育中心/便利店/图书馆…）

本模块只做确定性替换：不调 LLM、不编值、不猜值。
替换后仍由 ``SlotRegistry`` 统一登记槽位，交给填槽器按
CUSTOMER / STANDARD / COMPUTED 判定。

用法::

    from corpus_pipeline.evo_devalue_rules import apply_qualitative_devalue
    text = apply_qualitative_devalue(text, registry=registry,
                                     place="⓿b段2", section="1.1")

``registry`` 只需提供 ``add(name, place=..., label=..., source_type=...)``。
"""
from __future__ import annotations

import re

# ================================================================ 规则目录

# 规则清单。`number_with_unit` 由 evo_prompt_template.devalue_prose 的
# NUM_RE 分支执行，这里保留在目录中，便于 119 节审计时一眼看全。
DEVALUE_RULES = [
    {
        "type": "number_with_unit",
        "pattern": r"\d[\d,.]*\s*(?:万?元|㎡|平方米|人|年|月|天|%)",
        "slot": "{概念名}",
        "handled_by": "evo_prompt_template.devalue_prose",
    },
    {
        "type": "direction",
        "pattern": r"(东北侧|西北侧|东南侧|西南侧|东面|西面|南面|北面|"
                   r"东部|西部|南部|北部|东南|西南|东北|西北|"
                   r"东侧|西侧|南侧|北侧)",
        "slot": "{{方位}}",
        "exclude": "「…地区」「西部大开发」「东北振兴」等政策区域名",
    },
    {
        "type": "surroundings",
        "pattern": r"(?:东|西|南|北)(?:侧|临|靠)[^。]{0,80}(?:绿地|建筑|广场|图书馆|便利店|道路)",
        "slot": "{{四至描述}}",
        "granularity": "子句后缀（保留「本项目位于…方位」前缀）",
    },
    {
        "type": "facilities",
        "pattern": r"(?:周边|供水|供电|配套设施|市政配套)[^。]{0,80}(?:齐全|良好|便捷|完善|平坦|成熟|通畅)",
        "slot": "{{配套条件描述}}",
        "granularity": "子句后缀",
    },
    {
        "type": "funding_source",
        "pattern": r"由([一-龥][^，。；]{1,19}?)(?:及|和|与)([一-龥][^，。；]{1,19}?)解决",
        "slot": "{{资金来源1}}及{{资金来源2}}",
        "granularity": "句内",
    },
    {
        "type": "building_name",
        "pattern": r"原(?:有)?([第]?[一二三四五六七八九十百0-9]+(?:教学楼|楼|馆|中心|厂房|仓库|宿舍|办公楼|实验室))",
        "slot": "{{拆除对象}}",
        "granularity": "句内",
    },
    {
        "type": "adjacent_building",
        "pattern": r"(?:现有|相邻|周边|附近|临近|毗邻|对面|靠近)的?([一-龥]{2,10}?(?:楼|馆|中心|大厦|广场|便利店|图书馆|医院|学校|食堂|宿舍))",
        "slot": "{{相邻建筑N}}",
        "granularity": "句内，N 按出现顺序递增",
    },
]

# 上财定性值专名：不是数字，但同样不能跨项目复用。
PHRASE_VALUE_REPLACEMENTS = [
    ("国拨资金", "资金来源1"),
    ("学校自筹资金", "资金来源2"),
    ("学校自筹", "资金来源2"),
    ("第五教学楼", "拆除对象"),
]

# 四至/配套识别词
_DIRECTION_MARKERS = (
    "东侧", "西侧", "南侧", "北侧", "东北侧", "西北侧", "东南侧", "西南侧",
    "东临", "西临", "南临", "北临", "东靠", "西靠", "南靠", "北靠",
    "东近", "西近", "南近", "北近", "东至", "西至", "南至", "北至",
    "东邻", "西邻", "南邻", "北邻", "东接", "西接", "南接", "北接",
    "东面", "西面", "南面", "北面", "四周", "四至", "周边", "邻近", "毗邻", "对面",
)
_LANDMARKS = (
    "绿地", "建筑", "广场", "图书馆", "便利店", "道路", "楼", "中心",
    "公园", "商场", "住宅", "校区", "场地", "河", "路", "食堂", "宿舍",
    "庭院", "景观",
)
_QUALITY_WORDS = (
    "齐全", "良好", "便捷", "完善", "平坦", "成熟", "通畅", "有保证", "具备",
)
_DIRECTION_WORDS = (
    "东北侧", "西北侧", "东南侧", "西南侧",
    "东面", "西面", "南面", "北面",
    "东部", "西部", "南部", "北部", "东南", "西南", "东北", "西北",
    "东侧", "西侧", "南侧", "北侧",
)
_DIRECTION_RE = re.compile("|".join(sorted(_DIRECTION_WORDS, key=len, reverse=True)))
_PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}")
_TOKEN_RE = re.compile("([a-z]+)")


# ================================================================ 占位符保护


def _idx_to_letters(n):
    """0 → a, 1 → b, …, 25 → z, 26 → aa。哨兵不含数字，避免被数字规则二次命中。"""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(97 + r) + s
    return s


def _letters_to_idx(s):
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - 97 + 1)
    return n - 1


def protect_placeholders(text):
    """把已有 {{槽位}} 换成不含数字的临时哨兵，供去值流程全程保护。"""
    tokens = []

    def repl(m):
        tokens.append(m.group(0))
        return "%s" % _idx_to_letters(len(tokens) - 1)

    return _PLACEHOLDER_RE.sub(repl, text), tokens


def restore_placeholders(text, tokens):
    return _TOKEN_RE.sub(
        lambda m: tokens[_letters_to_idx(m.group(1))], text)


_protect_placeholders = protect_placeholders
_restore_placeholders = restore_placeholders


# ================================================================ 判定


def _split_clauses(body):
    """按「，」「；」切子句，保留分隔符在子句末尾。"""
    return re.split(r"(?<=[，；])", body)


def _looks_like_surroundings(s):
    markers = sum(1 for k in _DIRECTION_MARKERS if k in s)
    landmarks = sum(1 for k in _LANDMARKS if k in s)
    return landmarks >= 2 and markers >= 2


def _looks_like_facilities(s):
    # 费用/投资口径句（如「大市政配套费」）不是场地配套描述，跳过。
    if any(k in s for k in ("配套费", "增容费", "费用", "投资估算", "工程费")):
        return False
    has_scope = (
        "周边" in s
        or ("供水" in s and "供电" in s)
        or "配套设施" in s
        or "市政配套" in s
    )
    quality = sum(1 for k in _QUALITY_WORDS if k in s)
    return has_scope and quality >= 1


def _replace_clause_suffix(body, predicate, slot, head_markers):
    """把满足判定的子句后缀整段换成槽位，保留前缀（如「本项目位于…」）。

    若首子句本身就是四至/配套描述（以方位词或「周边」开头），整句替换；
    否则从第 2 个子句起找「后缀成立、前缀不成立」的最早切分，
    避免把「本项目位于…东部，」这样的定位前缀一起吞掉。
    """
    parts = _split_clauses(body)
    first = parts[0].rstrip("，；").strip() if parts else ""
    if predicate(body) and any(first.startswith(k) for k in head_markers):
        return slot
    for i in range(1, len(parts)):
        suffix = "".join(parts[i:])
        prefix = "".join(parts[:i])
        if predicate(suffix) and not predicate(prefix):
            return prefix + slot
    if predicate(body):
        return slot
    return body


def _is_policy_direction(text, m):
    """政策区域名里的「东部/西部/东北…」不是项目值，不替换。"""
    word = m.group(0)
    after = text[m.end():m.end() + 3]
    before = text[max(0, m.start() - 2):m.start()]
    if after.startswith("地区"):
        return True
    if word in ("东部", "西部") and after.startswith("大开发"):
        return True
    if word in ("东北", "西北") and after.startswith("振兴"):
        return True
    if word in ("东部", "西部") and before.endswith("大"):
        return True
    return False


# ================================================================ 主函数


def apply_qualitative_devalue(text, *, registry, place="", section="",
                              sentence_level=True):
    """把定性值替换成槽位并登记；返回替换后的文本。

    顺序很重要：先整段/子句级（四至、配套），再句内（资金、建筑名），
    最后方位。这样「西侧为绿地，东侧临近…」不会被拆成多个 {{方位}}。

    ``sentence_level=False`` 时只做句内替换，不做四至/配套整段替换；
    适合「必须覆盖」这类检查清单，避免把一句话整段吞成 {{四至描述}}。
    """
    t = str(text or "")
    if not t:
        return t
    t, tokens = _protect_placeholders(t)

    def add(name, label, source_type="CUSTOMER", unit=""):
        if registry is not None and hasattr(registry, "add"):
            registry.add(name, place=place, label=label,
                         source_type=source_type, unit=unit)

    original = t
    used = set()

    # 逐句处理：四至 / 配套是「子句后缀」级，必须在方位之前。
    out_parts = []
    for sent in re.split(r"(?<=。)", t):
        if not sent.strip():
            out_parts.append(sent)
            continue
        body = sent[:-1] if sent.endswith("。") else sent
        tail = sent[len(body):]

        if sentence_level:
            before = body
            body = _replace_clause_suffix(body, _looks_like_surroundings,
                                          "{{四至描述}}", _DIRECTION_MARKERS)
            if body != before:
                add("四至描述", "场地四至现状（含相邻建筑）")
                used.add("四至描述")

            before = body
            body = _replace_clause_suffix(body, _looks_like_facilities,
                                          "{{配套条件描述}}",
                                          ("周边", "供水", "供电", "配套设施", "市政配套"))
            if body != before:
                add("配套条件描述", "周边配套条件")
                used.add("配套条件描述")

        # 资金来源：由 A 及 B 解决
        def repl_funding(m):
            add("资金来源1", "资金来源一", unit="万元")
            add("资金来源2", "资金来源二", unit="万元")
            used.update(("资金来源1", "资金来源2"))
            return "由{{资金来源1}}及{{资金来源2}}解决"

        body = re.sub(
            r"由([一-龥][^，。；]{1,19}?)(?:及|和|与)([一-龥][^，。；]{1,19}?)解决",
            repl_funding, body)

        # 拆除对象：原有第五教学楼 → 原有{{拆除对象}}
        def repl_building(m):
            add("拆除对象", "被拆除的原有建筑")
            used.add("拆除对象")
            return "原有{{拆除对象}}"

        body = re.sub(
            r"原(?:有)?([第]?[一二三四五六七八九十百0-9]+"
            r"(?:教学楼|楼|馆|中心|厂房|仓库|宿舍|办公楼|实验室))",
            repl_building, body)

        # 相邻建筑：按出现顺序编号
        counter = {"n": 0}

        def repl_adjacent(m):
            counter["n"] += 1
            name = "相邻建筑%d" % counter["n"]
            add(name, "周边相邻建筑%d" % counter["n"])
            used.add(name)
            return "{{%s}}" % name

        body = re.sub(
            r"(?:现有|相邻|周边|附近|临近|毗邻|对面|靠近)的?"
            r"([一-龥]{2,10}?(?:楼|馆|中心|大厦|广场|便利店|图书馆|医院|学校|食堂|宿舍))",
            repl_adjacent, body)

        out_parts.append(body + tail)

    t = "".join(out_parts)

    # 已知上财定性专名 → 槽位（兜底）
    for phrase, slot in PHRASE_VALUE_REPLACEMENTS:
        if phrase and phrase in t:
            add(slot, slot)
            used.add(slot)
            t = t.replace(phrase, "{{%s}}" % slot)

    # 方位：最后处理，避免把四至描述里的方位拆成多个槽位
    def repl_direction(m):
        if _is_policy_direction(t, m):
            return m.group(0)
        if "方位" not in used:
            add("方位", "项目在校区内的方位")
            used.add("方位")
        return "{{方位}}"

    t = _DIRECTION_RE.sub(repl_direction, t)

    return _restore_placeholders(t, tokens)


# ================================================================ 残留检测


def _is_prose_line(line):
    """只检查正文行；跳过标题、表格、引用、代码围栏和统计标签。"""
    s = line.strip()
    if not s:
        return False
    if s.startswith(("#", "|", ">", "```", "**槽位", "**原文", "**还原", "**仿照")):
        return False
    if re.match(r"^[-=]{3,}$", s):
        return False
    return True


def find_qualitative_residue(text):
    """返回定性值残留（供模板校验/反例自检）。

    只报「看起来仍是项目值」的片段：
      - 未替换的方位词（排除政策区域名）
      - 仍像四至/配套描述的整句
      - 未替换的「原有X楼/馆/中心」
      - 未替换的「由A及B解决」
    """
    t = str(text or "")
    t, tokens = _protect_placeholders(t)
    out = []

    prose_lines = [ln for ln in t.splitlines() if _is_prose_line(ln)]
    prose = "\n".join(prose_lines)

    for m in _DIRECTION_RE.finditer(prose):
        if _is_policy_direction(prose, m):
            continue
        out.append({
            "value": m.group(0),
            "kind": "direction",
            "context": prose[max(0, m.start() - 30):m.start() + 30],
        })

    for line in prose_lines:
        for sent in re.split(r"(?<=。)", line):
            body = sent[:-1] if sent.endswith("。") else sent
            if not body:
                continue
            if _looks_like_surroundings(body):
                out.append({"value": body[:80], "kind": "surroundings",
                            "context": body[:120]})
            if _looks_like_facilities(body):
                out.append({"value": body[:80], "kind": "facilities",
                            "context": body[:120]})

    for m in re.finditer(
            r"原(?:有)?([第]?[一二三四五六七八九十百0-9]+"
            r"(?:教学楼|楼|馆|中心|厂房|仓库|宿舍|办公楼|实验室))", prose):
        out.append({"value": m.group(0), "kind": "building_name",
                    "context": prose[max(0, m.start() - 30):m.end() + 30]})

    for m in re.finditer(
            r"由([一-龥][^，。；]{1,19}?)(?:及|和|与)([一-龥][^，。；]{1,19}?)解决", prose):
        out.append({"value": m.group(0), "kind": "funding_source",
                    "context": prose[max(0, m.start() - 30):m.end() + 30]})

    # 去重
    seen = set()
    deduped = []
    for x in out:
        key = (x["kind"], x["value"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(x)
    return deduped


__all__ = [
    "DEVALUE_RULES",
    "PHRASE_VALUE_REPLACEMENTS",
    "apply_qualitative_devalue",
    "find_qualitative_residue",
    "protect_placeholders",
    "restore_placeholders",
]
