# -*- coding: utf-8 -*-
"""规范性文件条款抽取器（确定性，零 LLM）。

五个抽取器 + 类型路由 + 质量评估。可直接 import 使用。

用法：
    from extractors import extract, judge_quality
    clauses = extract(chunks, kind="intensity")     # 或 "auto"
    rep = judge_quality(chunks, clauses)
"""
import re

# ══ 模式 ══
CL = re.compile(r"^\s*(\d+(?:\.\d+){1,3})\s*[\s　]*(\S.{3,})")
TB = re.compile(r"^\s*(表\s*\d+(?:\.\d+){1,3})\s*(.{0,80})")
AP = re.compile(r"^\s*(附录\s*[A-Z一二三四五六七八九十]+)\s*[\s　]*(.+)")
IT = re.compile(r"^\s*(\d+)\s*抗震设防烈度为\s*(\d+)\s*度[，,]\s*设计基本地震加速度值为\s*([\d.]+)\s*g")
GP = re.compile(r"^\s*(第[一二三四五六七八九十]组)\s*[：:]\s*(.+)")
A1 = re.compile(r"^\s*([一二三四五六七八九十]+)、\s*(.+)")
A2 = re.compile(r"^\s*[（(]([一二三四五六七八九十]+)[)）]\s*(.+)")
A3 = re.compile(r"^\s*(\d+)[.．、]\s*(\S.{3,})")
AR = re.compile(r"^\s*第([一二三四五六七八九十百]+)条\s*[\s　]*(.+)")
NOISE = re.compile(r"^(上一页|下一页|返回|下载|打印|分享|扫一扫|微信|微博|当前位置|首页|主办单位|版权|网站标识|>|»|\||-{3,})")

def force_level(t):
    if re.search(r"[必严]须|严禁|不应|不得", t): return "A（强制性）"
    if "应" in t: return "B（强）"
    if re.search(r"宜|可|不宜", t): return "C（推荐）"
    return "D（资料性）"

# ══ 抽取器 ══
def ex_gb(chunks, **kw):
    out = []
    for c in chunks:
        t = str(c.get("text") or "").strip()
        if not t or NOISE.match(t): continue
        m = CL.match(t) or TB.match(t)
        if m:
            out.append({"clause": m.group(1), "text": (m.group(2) or "")[:400],
                        "chunk": c.get("id"), "kind": "条款"})
    return out

def ex_intensity(chunks, **kw):
    out, cur = [], None
    for c in chunks:
        t = str(c.get("text") or "").strip()
        m = IT.match(t)
        if m:
            if cur: out.append(cur)
            cur = {"clause": f"附录A-{m.group(1)}", "intensity": m.group(2), "accel": m.group(3),
                   "groups": [], "chunk": c.get("id"), "kind": "烈度分区",
                   "text": f"烈度 {m.group(2)} 度，设计基本地震加速度值 {m.group(3)}g"}
            continue
        g = GP.match(t)
        if g and cur:
            cur["groups"].append({"group": g.group(1), "areas": g.group(2)[:300]})
            cur["text"] = (f"烈度 {cur['intensity']} 度 / 加速度 {cur['accel']}g / " +
                           "；".join(f"{x['group']}：{x['areas'][:60]}" for x in cur["groups"]))
    if cur: out.append(cur)
    return out

def ex_outline(chunks, **kw):
    out, l1, l2 = [], "", ""
    for c in chunks:
        t = str(c.get("text") or "").strip()
        if not t or NOISE.match(t): continue
        m1 = A1.match(t)
        if m1:
            l1, l2 = m1.group(1), ""
            out.append({"clause": f"{l1}、", "text": m1.group(2)[:300], "chunk": c.get("id"),
                        "kind": "章", "path": f"{l1}、"})
            continue
        m2 = A2.match(t)
        if m2:
            l2 = m2.group(1)
            out.append({"clause": f"{l1}、({l2})", "text": m2.group(2)[:300], "chunk": c.get("id"),
                        "kind": "节", "path": f"{l1}、({l2})"})
            continue
        m3 = A3.match(t)
        if m3 and l1:
            out.append({"clause": f"{l1}、({l2}){m3.group(1)}.", "text": m3.group(2)[:300],
                        "chunk": c.get("id"), "kind": "条", "path": f"{l1}、({l2}){m3.group(1)}."})
    return out

def ex_appendix(chunks, **kw):
    out, cur = [], None
    for c in chunks:
        t = str(c.get("text") or "").strip()
        if not t or NOISE.match(t): continue
        m = AP.match(t)
        if m:
            if cur: out.append(cur)
            cur = {"clause": m.group(1), "text": m.group(2)[:400], "chunk": c.get("id"), "kind": "附录"}
            continue
        if cur and len(t) >= 10 and len(cur["text"]) < 800:
            cur["text"] = (cur["text"] + " " + t)[:800]
    if cur: out.append(cur)
    return out

def ex_article(chunks, **kw):
    out, cur = [], None
    for c in chunks:
        t = str(c.get("text") or "").strip()
        if not t or NOISE.match(t): continue
        m = AR.match(t)
        if m:
            if cur: out.append(cur)
            cur = {"clause": f"第{m.group(1)}条", "text": m.group(2)[:400],
                   "chunk": c.get("id"), "kind": "条文"}
            continue
        if cur and len(t) >= 10 and len(cur["text"]) < 600:
            cur["text"] = (cur["text"] + " " + t)[:600]
    if cur: out.append(cur)
    return out

def ex_notice(chunks, **kw):
    """公告类：全文即一条"""
    body = " ".join(str(c.get("text") or "").strip() for c in chunks
                    if not NOISE.match(str(c.get("text") or "").strip()))
    body = re.sub(r"\s+", " ", body).strip()
    if len(body) < 20: return []
    return [{"clause": "全文", "text": body[:800], "chunk": chunks[0].get("id") if chunks else None,
             "kind": "公告"}]

PARSERS = {"gb": ex_gb, "intensity": ex_intensity, "outline": ex_outline,
           "appendix": ex_appendix, "article": ex_article, "notice": ex_notice}

# ══ 自动判类型 ══
def detect_kind(chunks):
    """逐段统计命中数。

    不能用「拼接后 findall」——本模块正则以 ^ 锚定，
    拼成一整串后 findall 最多只匹配开头一次，会把所有文件误判为 notice。
    """
    n = {"intensity": 0, "article": 0, "gb": 0, "appendix": 0, "outline": 0}
    for c in chunks[:120]:
        t = str(c.get("text") or "").strip()
        if not t: continue
        if IT.match(t): n["intensity"] += 1
        if AR.match(t): n["article"] += 1
        if CL.match(t) or TB.match(t): n["gb"] += 1
        if AP.match(t): n["appendix"] += 1
        if A1.match(t) or A2.match(t): n["outline"] += 1
    if n["intensity"] >= 2: return "intensity"
    if n["article"] >= 2: return "article"
    if n["gb"] >= 3: return "gb"
    if n["appendix"] >= 2: return "appendix"
    if n["outline"] >= 2: return "outline"
    return "notice"

def extract(chunks, kind="auto"):
    if kind == "auto": kind = detect_kind(chunks)
    cs = PARSERS.get(kind, ex_gb)(chunks)
    for i, c in enumerate(cs, 1):
        c.setdefault("id", f"SC-{i:03d}")
        c.setdefault("text", "")
        c["effect_level"] = force_level(c["text"])
    return cs

# ══ 质量评估 ══
def judge_quality(chunks, clauses):
    n, m = len(chunks), len(clauses)
    short = sum(1 for c in clauses if len(c.get("text") or "") < 25)
    seen, dup = set(), 0
    for c in clauses:
        k = c.get("clause")
        if k in seen: dup += 1
        seen.add(k)
    cov = 100.0 * m / n if n else 0
    return {
        "chunks": n, "clauses": m, "coverage_pct": round(cov, 1),
        "short_pct": round(100.0 * short / m, 1) if m else 0,
        "duplicate": dup,
        "pass": cov >= 10 and (100.0 * short / m if m else 0) < 5 and dup == 0,
        "verdict": ("达标" if cov >= 10 and dup == 0 else
                    ("覆盖率偏低（<10%），检查抽取模式" if cov < 10 else "有重复条款")),
    }
