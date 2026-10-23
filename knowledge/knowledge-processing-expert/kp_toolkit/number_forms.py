# -*- coding: utf-8 -*-
"""数值形态统一识别器 —— 六类形态一次识别，不逐类打补丁。

## 为什么需要它

逐案抽查暴露了 6 类漏抽，每类都是「我的正则先没想到」：

| # | 形态 | 实例 | 最初为什么漏 |
|---|---|---|---|
| 1 | 单位变体 | 2.5KN/m2 | 单位表只有 kN/m²（小写+上标） |
| 2 | 等级词 | 建筑耐火等级为二级 | 规则只认「数字+单位」 |
| 3 | 材料牌号 | 钢筋：HPB300，HRB400 | 同上，且合并值未拆 |
| 4 | 规格条件 | DN＜100 双卡压连接 | DN 不是普通单位；且条件是规则不是实体 |
| 5 | 允差型 | 64±4dB | 规则不认 ± |
| 6 | 标准引用 | GB50034—2013 | 全角破折号；且书名号回溯错 |

六类共用一件事：「这句话在说什么类型的信息」。
先判形态、再选抽取器 —— 比「一个正则覆盖所有」可靠。

## 用法

    from number_forms import recognize
    for hit in recognize("管径DN＜100双卡压连接"):
        print(hit["form"], hit["subject"], hit["value"])

## 契约

    {"form": "quantity|tolerance|grade|material|spec|standard",
     "subject": str, "value": str, "unit": str,
     "extra": dict, "span": (start, end), "raw": str}
"""
from __future__ import annotations
import re

_UNIT_RAW = {
    "kn/m2": "kN/m²", "kn/m²": "kN/m²", "kn/㎡": "kN/m²", "kn/m^2": "kN/m²",
    "w/m2": "W/m²", "w/m²": "W/m²", "w/㎡": "W/m²", "kw/m2": "kW/m²",
    "m2": "m²", "m²": "m²", "㎡": "m²", "m3": "m³", "m³": "m³", "立方米": "m³",
    "平方米": "m²", "m2/h": "m³/h", "m3/h": "m³/h", "m3/d": "m³/d", "m3/min": "m³/min",
    "kva": "kVA", "kw": "kW", "kv": "kV", "kpa": "kPa", "mpa": "MPa", "pa": "Pa",
    "kwh": "kW·h", "kw·h": "kW·h", "l/s": "L/s", "l/min": "L/min",
    "db": "dB", "lx": "lx", "lm": "lm", "cd": "cd", "hz": "Hz",
    "mm": "mm", "cm": "cm", "km": "km", "m": "m", "米": "m",
    "kg": "kg", "t": "t", "g": "g", "d": "d", "h": "h", "min": "min",
    "%": "%", "‰": "‰", "度": "度", "年": "年", "层": "层",
    "人": "人", "台": "台", "套": "套", "间": "间", "个": "个", "处": "处",
    "篇": "篇", "项": "项", "名": "名", "所": "所", "家": "家", "户": "户",
    "支": "支", "队": "队", "位": "位", "条": "条", "座": "座", "栋": "栋",
    "亩": "亩", "公顷": "公顷", "册": "册", "部": "部", "台套": "台套",
    "个专业": "个", "人次": "人次", "辆": "辆", "艘": "艘", "架": "架",
    "万元": "万元", "亿元": "亿元", "元": "元", "万元/年": "万元/年",
    "亿英镑": "亿英镑", "亿欧元": "亿欧元", "亿美元": "亿美元", "亿日元": "亿日元",
    "亿": "亿", "万亿": "万亿", "千元": "千元", "百万元": "百万元",
    "亩": "亩", "公顷": "公顷", "ha": "ha", "平方公里": "km²",
    "号": "号", "座": "座", "栋": "栋", "亩/人": "亩/人",
    "个月": "个月", "天/日": "天", "日历天": "日历天",
    "v": "V", "a": "A", "℃": "℃", "k": "K",
}
_UNIT_CANON = {k.lower().replace(" ", ""): v for k, v in _UNIT_RAW.items()}
_UNIT_ALT = "|".join(sorted((re.escape(k) for k in _UNIT_CANON), key=len, reverse=True))


def canon_unit(u):
    return _UNIT_CANON.get((u or "").lower().replace(" ", "").strip(), (u or "").strip())


_CMP = (r"不应小于|不宜小于|不小于|不应大于|不宜大于|不大于|大于|小于|"
        r"不超过|不低于|不高于|大于或等于|小于或等于|不少于|不多于|"
        r"≥|≤|＞|＜|>|<|最小|最大|最低|最高|最少|最多|约计|约|为|是|取")
P_QUANTITY = re.compile(
    r"(?P<subj>[\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9、：:\-·\s]{1,24}?)"
    r"\s*(?P<cmp>" + _CMP + r")?\s*"
    r"(?P<v>\d+(?:[,，]\d{3})*(?:\.\d+)?)"
    r"(?:\s*[-－~～]\s*(?P<v2>\d+(?:\.\d+)?))?"
    r"\s*(?P<u>" + _UNIT_ALT + r")", re.I)

# 「最小/最大」夹在主体与属性之间：踏步最小宽度0.28m / 最大高度0.15m
# 这类不能靠 _CMP（cmp 在 subj 之后，而「最小」在 subj 中间）
P_MINMAX = re.compile(
    r"(?P<pre>[\u4e00-\u9fa5A-Za-z]{0,6}?)"
    r"(?P<lim>最小|最大|最低|最高|最少|最多)\s*"
    r"(?P<attr>[\u4e00-\u9fa5A-Za-z]{1,10}?)\s*"
    r"(?P<v>\d+(?:\.\d+)?)\s*(?P<u>" + _UNIT_ALT + r")", re.I)

# ⑧ 无主体计数：括号/标点后的纯计数（（培育）4个国家级重点学科 / 吸引74支队伍）
# 这类主体在句首（学校拥有…），位置离数字很远，靠 subj 组抓不到
P_BARE_COUNT = re.compile(
    r"(?<![\d.])"
    r"(?P<v>\d+(?:[,，]\d{3})*(?:\.\d+)?)\s*"
    r"(?P<u>个|支|位|名|所|家|户|条|座|栋|册|部|辆|项|篇|人次|队)"
    r"(?P<rest>[\u4e00-\u9fa5]{0,10})", re.I)

P_TOLERANCE = re.compile(
    r"(?P<subj>[\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9、（）()：:\-·\s]{1,20}?)"
    r"\s*(?:为|是|=|:|：)?\s*"
    r"(?P<v>\d+(?:\.\d+)?)\s*(?:±|\+/-|\+-)\s*(?P<tol>\d+(?:\.\d+)?)\s*"
    r"(?P<u>" + _UNIT_ALT + r")", re.I)

_GRADE = (r"(?:一级|二级|三级|四级|特级|"
          r"一类|二类|三类|四类|"
          r"甲类|乙类|丙类|丁类|甲级|乙级|丙级|丁级|"
          r"一星|二星|三星|"
          r"A类|B类|C类|D类|"
          r"标准设防类|重点设防类|特殊设防类|适度设防类)")
P_GRADE = re.compile(
    r"(?P<subj>[\u4e00-\u9fa5]{2,16}?(?:等级|类别|类别等级|设防类别|粗糙度|星级|分类))"
    r"\s*(?::|：|为|是|按)?\s*(?P<val>" + _GRADE + r")(?:（(?P<extra>[^）]{1,12})）)?")

_MATERIAL_GRADE = (r"(?:HPB|HRB|HRBF|RRB)\d{3}[A-Z]?|"
                   r"C\d{2}(?:~C\d{2})?|"
                   r"Q\d{3}[A-Z]?|Q\d{2}[A-Z]?|"
                   r"MU\d+(?:\.\d+)?|"
                   r"M\d+(?:\.\d+)?|"
                   r"(?:YJV|VV|BV|KVV|NH-YJV|WDZ)[\d×x\s\.]*|"
                   r"(?:PPR|UPVC|PVC-U|HDPE|PE-RT|PB)")
# subj 可为空：纯牌号列表（HPB300，HRB400）由调用方沿用上一个主体
P_MATERIAL = re.compile(
    r"(?P<subj>(?:[\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9、（）()：:\-·\s]{0,20}?)??)"
    r"\s*(?:为|是|采用|选用|:|：)?\s*"
    r"(?P<val>(?:" + _MATERIAL_GRADE + r"))", re.I)

# 词序两种都要支持：
#   「管径DN＜100」 tag 在 cmp 前  ← 实际文本多是这种
#   「管径＜DN100」 cmp 在 tag 前
# 注意：整个 alternation 是**必选**的（不带 ?）。
# 曾写成 (?:...)? 导致 tag 可缺省 → 任意数字都被当成 DN（HPB300→DN300），
# 这是「放宽必填消除告警」的典型错误。
P_SPEC = re.compile(
    r"(?P<pre>管径|管道|管材|公称直径|直径|外径|内径)?\s*"
    r"(?:(?P<tag1>DN|De|Φ|φ)\s*(?P<cmp1>＜|≤|≥|＞|<|>|不大于|不小于|大于或等于|小于或等于|大于|小于)\s*"
    r"|(?P<cmp2>＜|≤|≥|＞|<|>|不大于|不小于|大于或等于|小于或等于|大于|小于)\s*(?P<tag2>DN|De|Φ|φ)\s*)"
    r"(?P<v>\d{2,5})", re.I)

_DASH = {"—": "-", "–": "-", "－": "-", "−": "-", "‐": "-"}
P_STANDARD = re.compile(
    r"(?:《(?P<title>[^》]{2,44})》\s*[（(]?)?"
    r"(?P<code>(?:GB/T|GB|JGJ/T|JGJ|DGJ\s*\d*|DB\d*|CJJ|CECS|建标|沪建|SH|AQ|HJ|TSG)"
    r"\s*[\d\-—–－−.]{2,20}\d)", re.I)


def _norm_dash(s):
    for a, b in _DASH.items():
        s = s.replace(a, b)
    return s


_PREFIX = re.compile(r"^(本项目|本工程|该|其|其中|本报告|上述|同时|此外)+")


# 「最小/最大」→ 比较符语义映射
_CMP_SEMANTIC = {
    "最小": ">=", "最少": ">=", "最低": ">=", "不小于": ">=", "不应小于": ">=",
    "不宜小于": ">=", "不低于": ">=", "大于或等于": ">=", "不少于": ">=",
    "最大": "<=", "最多": "<=", "最高": "<=", "不大于": "<=", "不应大于": "<=",
    "不宜大于": "<=", "不高于": "<=", "小于或等于": "<=", "不超过": "<=", "不多于": "<=",
    "大于": ">", "＞": ">", ">": ">",
    "小于": "<", "＜": "<", "<": "<",
    "≥": ">=", "≤": "<=",
}


def cmp_semantic(cmp_word: str) -> str:
    """把中文比较词转成可比较的符号。最小→>=，最大→<=。"""
    return _CMP_SEMANTIC.get((cmp_word or "").strip(), "=")


def _clean(s):
    s = re.sub(r"\s+", "", s or "")
    s = re.sub(r"^[\d\.\、\s）\)】\-]+", "", s)
    s = _PREFIX.sub("", s)
    s = re.sub(r"(按|为|是|取|约|即|达|共|计)$", "", s)   # 去尾部助词
    # 去主体里残留的「最小/最大」等限定词（它们已转为比较符语义）
    s = re.sub(r"^(最小|最大|最低|最高|最少|最多)", "", s)
    return s.strip(" ：:，,。、；;")


STOP = {"本项目", "本工程", "该", "其", "其中", "以上", "以下", "合计",
        "总计", "小计", "共", "全年", "目前", "截至", "同时", "此外"}


def recognize(sentence):
    """识别一句话里的所有数值形态（同一位置取最具体的一种）。"""
    s = (sentence or "").strip()
    if not s:
        return []
    hits, taken = [], []

    def push(form, m, subj, val, unit="", extra=None):
        span = (m.start(), m.end())
        if any(a < span[1] and span[0] < b for a, b in taken):
            return
        subj = _clean(subj)
        if len(subj) < 2 or subj in STOP:
            return
        taken.append(span)
        hits.append({"form": form, "subject": subj[:40], "value": val,
                     "unit": unit, "extra": extra or {}, "span": span,
                     "raw": m.group(0)[:120]})

    # ⑤b 最小/最大 + 属性（优先于普通数值）
    # 「踏步最小宽度0.28m，最大高度0.15m」→ 第二句的 pre 为空，
    # 需继承第一句的共同前缀（踏步），否则 subject 变成光秃秃的「高度」
    # pre 只允许「名词性前缀」：含动词/连词的一律丢弃（易于区分/用于/进行…）
    _PRE_STOP = ("易于", "区分", "用于", "进行", "采用", "设置", "设有", "应设",
                 "以及", "并且", "同时", "并", "和", "与")

    def _noun_pre(p):
        p = _clean(p)
        for w in _PRE_STOP:
            p = p.replace(w, "")
        return p if len(p) <= 4 else p[-4:]

    _minmax_base = ""
    for m in P_MINMAX.finditer(s):
        lim = m.group("lim")
        attr = _clean(m.group("attr"))
        pre = _noun_pre(m.group("pre"))
        if pre:
            _minmax_base = pre
            subj = pre + attr
        else:
            subj = (_minmax_base + attr) if _minmax_base else attr
        push("quantity", m, subj, m.group("v"), canon_unit(m.group("u")),
             {"op": cmp_semantic(lim), "cmp_word": lim, "norm": True,
              "attr": attr})

    for m in P_TOLERANCE.finditer(s):
        v, tol = float(m.group("v")), float(m.group("tol"))
        push("tolerance", m, m.group("subj"),
             "%s±%s%s" % (m.group("v"), m.group("tol"), canon_unit(m.group("u"))),
             canon_unit(m.group("u")),
             {"nominal": v, "tolerance": tol,
              "lower": round(v - tol, 4), "upper": round(v + tol, 4)})
    for m in P_SPEC.finditer(s):
        tag = (m.group("tag1") or m.group("tag2") or "DN").upper()
        cmp_ = (m.group("cmp1") or m.group("cmp2") or "").replace("＜", "<").replace("＞", ">")
        push("spec", m, (m.group("pre") or "管道"),
             "%s%s %s" % (cmp_, tag, m.group("v")), tag,
             {"tag": tag, "op": cmp_ or "=", "limit": m.group("v")})
    last_mat_subj = ""
    for m in P_MATERIAL.finditer(s):
        val = m.group("val").strip()
        if not re.search(r"\d", val):
            continue
        subj = _clean(m.group("subj")) or last_mat_subj
        if not subj:
            continue
        last_mat_subj = subj
        push("material", m, subj, val, "", {"grade": val})
    for m in P_GRADE.finditer(s):
        val = m.group("val") + (("（%s）" % m.group("extra")) if m.group("extra") else "")
        push("grade", m, m.group("subj"), val)
    for m in P_STANDARD.finditer(s):
        code = _norm_dash(m.group("code")).replace(" ", "")
        push("standard", m, (m.group("title") or code), code, "",
             {"code": code, "title": (m.group("title") or "").strip()})
    for m in P_QUANTITY.finditer(s):
        v = m.group("v").replace(",", "").replace("，", "")
        push("quantity", m, m.group("subj"), v, canon_unit(m.group("u")),
             {"op": cmp_semantic(m.group("cmp")),
              "cmp_word": m.group("cmp") or "",
              "v2": m.group("v2") or "",
              "norm": bool(m.group("cmp"))})

    # ⑧ 无主体计数（最低优先）：仅当前面各形态都没覆盖该位置时
    _known = {h["value"] for h in hits}
    for m in P_BARE_COUNT.finditer(s):
        v = m.group("v").replace(",", "").replace("，", "")
        if f"{v}{m.group('u')}" in _known:
            continue
        rest = m.group("rest") or ""
        subj = ("计数·" + rest) if rest else "计数"
        push("count", m, subj, v, m.group("u"),
             {"count_of": rest, "bare": True})

    hits.sort(key=lambda x: x["span"][0])
    return hits


if __name__ == "__main__":
    CASES = [
        ("科研用房 2.5KN/m2", 1),
        ("建筑耐火等级为二级。", 1),
        ("钢筋：HPB300，HRB400。", 2),
        ("钢材：Q235B、Q345B。", 2),
        ("管径DN＜100双卡压连接，DN≥100 沟槽式连接。", 2),
        ("系统输出口电平为64±4dB。", 1),
        ("照明标准：…按照国家标准GB50034—2013《建筑照明标准》执行", 1),
        ("工作压力为1.0MPa。", 1),
        ("本工程总建筑面积18319平方米，其中地上建筑面积18000平方米", 2),
        ("根据《建筑工程抗震设防分类标准》(GB50223-2008)，本工程抗震设防烈度按7度考虑。", 2),
    ]
    print("=" * 86)
    print("数值形态识别器自测")
    print("=" * 86)
    allok = True
    for sent, expect in CASES:
        hits = recognize(sent)
        ok = len(hits) >= expect
        allok = allok and ok
        print("\n%s %s（期望≥%d，实得 %d）" % ("✓" if ok else "✗", sent[:56], expect, len(hits)))
        for h in hits:
            ex = ""
            if h["form"] == "tolerance":
                ex = " [%s,%s]" % (h["extra"]["lower"], h["extra"]["upper"])
            print("    %-10s %-20s = %-14s %-5s%s" % (
                h["form"], h["subject"][:20], h["value"], h["unit"], ex))
        if not hits:
            print("    （无识别结果）")
    print()
    print("=" * 86)
    print("结果: %s" % ("✓ 全部通过" if allok else "✗ 有用例未达预期"))
