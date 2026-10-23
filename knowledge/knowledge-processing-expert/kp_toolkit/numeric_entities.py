# -*- coding: utf-8 -*-
"""kp_toolkit.numeric_entities —— 数值实体与判断句实体的确定性抽取（零 LLM）

两件事：
  ① scan_numeric(chunks)    数值实体（主体+数值+单位三者可核验）
  ② scan_judgment(chunks)   判断句里的实体（判断主体/对象/依据）

核心判据：
  · 数值实体不是「有数字就算」，而是「主体+数值+单位三者可核验才算」
  · 章节号/条款号/年份/序号都是数字，但都不是实体
  · 规范要求（应/不应/不应小于）≠ 项目取值

对外：
    scan_numeric(chunks, existing_nodes=None)   -> {items, invalid, stats}
    scan_judgment(chunks)                        -> {items, stats}
    classify_nature(text)                        -> "norm" | "value" | "unknown"
"""
import re

# ══════════════════════════════════════════════════════════
# 一、数值实体
# ══════════════════════════════════════════════════════════

UNITS = ["平方米", "立方米每小时", "立方米", "个月", "年", "天", "小时",
         "㎡/人", "㎡", "m²", "m³/d", "m³/h", "m³",
         "kN/m²", "kN/m2", "W/㎡", "W/m2", "kW·h", "kWh", "kW", "kVA",
         "L/min·㎡", "L/人·日", "L/生·日", "L/人·d", "L/生·d", "L/s", "L",
         "万元", "元/㎡", "元", "万人", "人", "台", "套", "间", "个",
         "米", "m", "层", "度", "%", "‰", "d", "天", "小时", "h", "年"]
_UNIT_RE = "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))
NUM_RE = re.compile(r"(?<![\d\.\-])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(" + _UNIT_RE + r")")

# 时间点 vs 时长
TIMEPOINT = re.compile(r"(19|20)\d{2}\s*年|\d{1,2}\s*月\s*\d{1,2}\s*日")
DURATION = re.compile(r"(工期|使用年限|设计年限|寿命|周期|年限|期限|工作天数|延续时间|小时数|施工期)")
# 规范要求标志
NORM_WORDS = ("应", "不应", "不应低于", "不应小于", "不应大于", "必须", "不得", "不宜")
NORM_REF = re.compile(r"(GB\s*/?\s*T?\s*\d{4,5}|JGJ\s*\d+|DGJ\s*[\dA-Z]+|建标\s*\d+)")
# 引用/章节标志
CITE_CTX = re.compile(r"(第\s*\d|章节|条款|见表|见附表|附录|式\s*\(|编号)")


def classify_nature(text):
    """判断一段文字里的数值是「规范要求」还是「项目取值」。

    规范要求 → NormRequirement（不建 Quantity）
    项目取值 → Quantity
    """
    t = str(text or "")
    req = [w for w in NORM_WORDS if w in t]
    ref = NORM_REF.findall(t)
    if req and (ref or "规范" in t or "标准" in t):
        return "norm"
    # 「应/不应」出现在数值前且无第一人称 → 也是要求
    if req and re.search(r"(应|不应|必须|不得)[^。]{0,12}\d", t):
        return "norm"
    # 比较词 + 数值：规范常用「大于/不小于/不大于」，本项目不会这么写
    if re.search(r"(大于|小于|不小于|不大于|高于|低于|宽于|深于|不少于|不超过)[^。]{0,12}\d", t):
        if not re.search(r"(本项目|本工程|本设计|设计为|取)", t):
            return "norm"
    # 规范语境词
    if re.search(r"(无障碍|防火|抗震|节能|规范|标准|条)", t) and re.search(r"\d", t):
        if not re.search(r"(本项目|本工程|设计为)", t):
            return "norm"
    if re.search(r"\d", t):
        return "value"
    return "unknown"


def invalid_reason(num, unit, ctx):
    """返回无效原因；None 表示有效。"""
    s = str(num)
    # ① 时间点
    if unit in ("年", "月", "日") and not DURATION.search(ctx):
        return "时间点（年/月/日）不是可计算数值"
    # ② 4 位年份无单位
    if not unit and re.fullmatch(r"\d{4}", s) and 1900 <= int(s) <= 2100:
        return "年份"
    # ③ 无单位小整数
    if not unit and re.fullmatch(r"\d{1,2}", s):
        return "无单位小整数（疑序号）"
    # ④ 引用上下文
    if CITE_CTX.search(ctx[-20:]):
        return "上下文为章节/表格/公式引用"
    # ⑤ 章节号形态
    if not unit and re.search(r"^\d+\.\d+\.\d+", s):
        return "章节号"
    # ⑥ 标准编号 / 文号
    if re.match(r"^(GB|JGJ|DGJ|CJJ|建标)", s) or s.startswith("〔"):
        return "标准编号/文号"
    return None


def scan_numeric(chunks, existing_nodes=None, with_invalid=True):
    """扫描数值实体。

    chunks: [{"id","text","section_struct_no"}]
    existing_nodes: 现有节点（用于判漏抽），[{id,value,unit,kind}]
    返回 {items, invalid, stats}
    """
    have = set()
    for n in (existing_nodes or []):
        if n.get("kind") not in ("quantity", "text", "fact"): continue
        have.add((str(n.get("value")), str(n.get("unit") or "")))
        have.add((str(n.get("value")), ""))

    items, invalid = [], []
    for c in chunks:
        t = str(c.get("text") or "")
        sec = str(c.get("section_struct_no") or "")
        if not t or sec in ("META", ""): continue
        for m in NUM_RE.finditer(t):
            num, unit = m.group(1).replace(",", ""), m.group(2)
            ctx = t[max(0, m.start() - 40):m.end() + 20].replace("\n", " ")
            bad = invalid_reason(num, unit, ctx)
            if bad:
                if with_invalid:
                    invalid.append({"sec": sec, "value": num, "unit": unit,
                                    "reason": bad, "ctx": ctx[:80]})
                continue
            pre = t[max(0, m.start() - 30):m.start()]
            pre = re.split(r"[。；;，,\n]", pre)[-1].strip()
            subj = re.sub(r"(为|是|取|约|按|共|达到|=|:|：)\s*$", "", pre).strip()[-24:]
            nature = classify_nature(ctx)
            rec = {"sec": sec, "chunk": c["id"], "subject": subj,
                   "value": num, "unit": unit, "nature": nature,
                   "ctx": ctx[:100]}
            if existing_nodes is not None:
                rec["covered"] = (num, unit) in have or (num, "") in have
            items.append(rec)

    stats = {
        "scanned": len(items) + len(invalid),
        "valid": len(items),
        "invalid": len(invalid),
        "invalid_by_reason": {},
        "by_nature": {},
    }
    for x in invalid:
        stats["invalid_by_reason"][x["reason"]] = stats["invalid_by_reason"].get(x["reason"], 0) + 1
    for x in items:
        stats["by_nature"][x["nature"]] = stats["by_nature"].get(x["nature"], 0) + 1
    if existing_nodes is not None:
        stats["covered"] = sum(1 for x in items if x.get("covered"))
        stats["missing"] = sum(1 for x in items if not x.get("covered"))
    return {"items": items, "invalid": invalid, "stats": stats}


# ══════════════════════════════════════════════════════════
# 二、判断句实体
# ══════════════════════════════════════════════════════════

JUDGE = {
    "conclusion": ("充分", "合理", "必要", "可行", "良好", "有利", "显著", "可控",
                   "有保障", "的需要", "不可或缺", "优于", "不足", "有待"),
    "recommendation": ("建议", "宜采用", "宜设", "应优先", "推荐"),
    "hypothesis": ("可能", "预计", "力争", "将达", "有望", "预估", "届时"),
    "inference": ("由于", "导致", "从而", "因此", "由此", "进而", "致使"),
}
# 判断对象提取模板：判断词前后各取一段
OBJ_RE = re.compile(r"([\u4e00-\u9fa5A-Za-z]{2,14})\s*(充分|合理|必要|可行|良好|有利|显著|可控|有保障)")


def scan_judgment(chunks):
    """扫描判断句里的实体。

    每句输出：
      subject     判断主体（隐含则记「编制方（隐含）」）
      object      判断对象（从判断词前的名词短语提取）
      judge_type  conclusion / recommendation / hypothesis / inference
      judge_word  命中的判断词
      falsifiable_by  什么能推翻它
      has_basis   句内是否含引用（cites 线索）
    """
    FB = {
        "conclusion": "找到一条证据表明该判断不成立",
        "recommendation": "找出更优方案或证明该建议不可行",
        "hypothesis": "实际结果与预测不符",
        "inference": "证明前提成立但结论不成立，或存在其他原因",
    }
    items = []
    for c in chunks:
        t = str(c.get("text") or "")
        sec = str(c.get("section_struct_no") or c.get("structure_no")
                  or c.get("section") or "")
        if not t: continue
        for sent in re.split(r"[。；;\n]", t):
            s = sent.strip()
            if len(s) < 8: continue
            # 过滤目录行与标题行（不是判断句）
            if re.search(r"(\t|\u3000){2,}", s): continue          # 目录（多制表符）
            if re.search(r"\.{3,}\s*\d+$", s): continue            # 目录（......页码）
            if re.match(r"^[\d\s\.]+[\u4e00-\u9fa5]{2,20}\s+\d+$", s): continue  # 目录（章节+页码）
            if len(s) < 12 and re.fullmatch(r"[\u4e00-\u9fa5、，。]{0,20}", s): continue  # 纯标题
            if re.match(r"^#{1,6}\s", s): continue                    # markdown 标题
            if s.count("|") >= 2 and s.count("|") > len(s) / 12: continue  # 表头/表格行
            if re.search(r"\d{1,2}\.\d{1,2}\s+[\u4e00-\u9fa5]{2,20}\s+\d+\s*$", s): continue  # 章节+标题+页码
            if re.fullmatch(r"[\u4e00-\u9fa5（）()]{2,10}", s): continue  # 极短纯标题
            hit_type, hit_words = None, []
            for jt in ("recommendation", "hypothesis", "inference", "conclusion"):
                h = [w for w in JUDGE[jt] if w in s]
                if h:
                    hit_type, hit_words = jt, h
                    break
            if not hit_type: continue
            mo = OBJ_RE.search(s)
            obj = mo.group(1) if mo else ""
            basis = NORM_REF.findall(s) or re.findall(r"《[^》]{4,40}》", s)
            items.append({
                "sec": sec, "chunk": c["id"], "sentence": s[:120],
                "judge_type": hit_type, "judge_word": hit_words[:3],
                "object": obj[:24],
                "subject": "编制方（隐含）" if "本项目" in s or not mo else obj[:10],
                "falsifiable_by": FB[hit_type],
                "has_basis": bool(basis), "basis": basis[:3],
            })
    stats = {
        "sentences": len(items),
        "by_type": {},
        "without_basis": sum(1 for x in items if not x["has_basis"]),
        "with_object": sum(1 for x in items if x["object"]),
    }
    for x in items:
        stats["by_type"][x["judge_type"]] = stats["by_type"].get(x["judge_type"], 0) + 1
    return {"items": items, "stats": stats}
