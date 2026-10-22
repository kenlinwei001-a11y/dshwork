# -*- coding: utf-8 -*-
"""kp_toolkit.citations —— 识别文档内引用的外部标准，生成待抓清单（确定性，零 LLM）

这是「自动触发检索」的第一步，也是最安全的一步：
  只做识别与分级，不擅自抓取、不擅自认定权威源。

对外：
    detect(chunks, library_codes=None)  -> {citations, names, missing}
    make_tasks(missing, tiers)          -> [{standard, tier, action}]
    STD_TYPES                           -> 标准类型判定（国标/行标/地标/团体/政策）

分级（按引用次数）：
    必抓  >= 3 次
    应抓  == 2 次
    暂缓  == 1 次
"""
import re
from collections import Counter, defaultdict

# ── 标准编号模式 ──
PAT = re.compile(
    r"(?:GB\s*/?\s*T?\s*\d{4,5}(?:[-—]\d{4})?|JGJ\s*\d+(?:[-—]\d{4})?|"
    r"DGJ\s*[\dA-Z]+(?:[-—]\d{4})?|CJJ\s*\d+(?:[-—]\d{4})?|"
    r"建标\s*[﹝〔\[]?\d{4}[﹞〕\]]?\s*\d+|"
    r"发改投资规〔\d{4}〕\d+号|国家发展改革委令第\s*\d+\s*号|发改委令第\s*\d+\s*号)")
NAME = re.compile(r"《[^》]{4,40}(?:规范|标准|指标|规定|办法|大纲|通则|规程)》")

# ── 标准类型判定（决定去哪抓、算不算权威）──
def std_type(code):
    c = re.sub(r"\s", "", str(code))
    if c.startswith("DGJ"):  return "地方标准（仅地方住建委官网权威）"
    if c.startswith("JGJ") or c.startswith("CJJ"): return "行业标准（住建部发布）"
    if c.startswith("GB/T"): return "国家推荐性标准"
    if c.startswith("GB"):   return "国家强制性标准"
    if c.startswith("建标"):  return "建设标准（住建部/发改委联合）"
    if "发改" in c or "令第" in c: return "政策文件（发改委发布）"
    return "未识别"


def normalize(code):
    m = re.match(r"(GB\s*/?\s*T?\s*\d{4,5}|JGJ\s*\d+|DGJ\s*[\dA-Z]+|CJJ\s*\d+|"
                 r"建标\s*[\d﹝〕]+|发改投资规|发改委令|国家发展改革委令)", str(code))
    return re.sub(r"\s", "", m.group(1)) if m else re.sub(r"\s", "", str(code))


def detect(chunks, library_codes=None):
    """识别 chunks 里引用的外部标准

    chunks: [{"id","text","section_struct_no",...}]
    library_codes: 公共标准库已有编号（用于判定缺什么）
    返回 {"citations": {...}, "names": {...}, "missing": [...]}
    """
    lib = {normalize(c) for c in (library_codes or [])}
    cites = defaultdict(lambda: {"count": 0, "secs": set(), "raw": Counter()})
    names = defaultdict(lambda: {"count": 0, "secs": set()})
    for c in chunks:
        t = str(c.get("text") or "")
        sec = str(c.get("section_struct_no") or "")
        for m in PAT.finditer(t):
            raw = m.group(0)
            k = normalize(raw)
            cites[k]["count"] += 1
            cites[k]["secs"].add(sec)
            cites[k]["raw"][re.sub(r"\s", "", raw)] += 1
        for m in NAME.finditer(t):
            k = re.sub(r"\s", "", m.group(0))
            names[k]["count"] += 1
            names[k]["secs"].add(sec)

    missing = []
    for k, v in cites.items():
        inlib = any(k[:6] == c[:6] for c in lib) if lib else False
        raw = v["raw"].most_common(1)[0][0]
        missing.append({
            "standard": k, "raw": raw, "mentions": v["count"],
            "sections": sorted(v["secs"]), "type": std_type(k),
            "in_library": inlib,
        })
    missing.sort(key=lambda x: -x["mentions"])
    return {"citations": dict(cites), "names": dict(names), "missing": missing}


def make_tasks(missing, must=3, should=2):
    """按引用次数分档，生成待抓清单"""
    out = []
    for m in missing:
        if m.get("in_library"): continue
        n = m["mentions"]
        tier = "必抓" if n >= must else ("应抓" if n >= should else "暂缓")
        out.append({
            "standard": m["standard"], "raw": m["raw"], "mentions": n,
            "tier": tier, "type": m["type"], "sections": m["sections"],
            "action": ("人工确认官方源后抓取" if tier == "必抓" else
                       ("批量抓取并抽查" if tier == "应抓" else "只登记引用，标注未抓原文")),
            "caution": ("地方标准仅地方住建委官网权威" if "地方" in m["type"] else
                        ("政策文件以发布机关公告为准" if "政策" in m["type"] else "以标准全文库或官方发布页为准")),
        })
    order = {"必抓": 0, "应抓": 1, "暂缓": 2}
    out.sort(key=lambda x: (order[x["tier"]], -x["mentions"]))
    return out


def summary(result, tasks):
    from collections import Counter
    return {
        "cited_standards": len(result["missing"]),
        "in_library": sum(1 for m in result["missing"] if m.get("in_library")),
        "missing": sum(1 for m in result["missing"] if not m.get("in_library")),
        "named_only": len(result["names"]),
        "tiers": dict(Counter(t["tier"] for t in tasks)),
    }
