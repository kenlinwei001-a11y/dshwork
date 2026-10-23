# -*- coding: utf-8 -*-
"""标准/规范实体抽取器 —— 面向「规范」「标准」「规程」「法规」等引用实体。

## 为什么需要独立抽取器

标准引用有五种形态，普通正则覆盖不了：

| # | 形态 | 实例 | 难点 |
|---|---|---|---|
| ① | 正常 | `《建筑设计防火规范》GB50016-2014` | — |
| ② | 带版本年 | `GB50016-2014(2018年版)` | 括号内年份是修订版不是发布年 |
| ③ | 字母混数字 | `JGJI00-1998` | 是 `JGJ100-1998` 的笔误，`I`↔`1`、`O`↔`0` |
| ④ | 全角破折号 | `GB50034—2013` | `—`/`–`/`－`/`−` 四种写法 |
| ⑤ | 无标准号 | `根据《建筑物电子信息系统防雷技术规范》` | 只有书名，没编号 |

## 关键设计：不稳定编码要「纠正 + 标注」，不许静默丢弃

`JGJI00-1998` 若按严格正则丢弃，整条标准就丢了；
若直接改成 `JGJ100-1998` 又不声明，等于篡改原文。

正确做法：纠正 + 保留原文 + 标 `code_was` + 标 `code_suspect`。
"""
from __future__ import annotations
import re

# 标准代字（按长度降序，避免 GB 抢先匹配 GB/T）
_PREFIX = ["GB/T", "GB/Z", "GBJ", "GB", "JGJ/T", "JGJ", "CJJ/T", "CJJ",
           "CECS", "DGJ", "DGJ/T", "DB", "DBJ", "建标", "沪建", "SH", "AQ", "HJ",
           "TSG", "JT/T", "JT", "SL", "YB", "HG", "SH/T", "NB", "DL/T", "DL"]
_PREFIX_ALT = "|".join(re.escape(p) for p in sorted(_PREFIX, key=len, reverse=True))

_DASH = {"—": "-", "–": "-", "－": "-", "−": "-", "‐": "-", "–": "-"}
# 易混字符归一（仅用于「疑似笔误」纠正，不用于普通匹配）
_CONFUSE = {"I": "1", "l": "1", "|": "1", "O": "0", "o": "0"}


def _norm_dash(s: str) -> str:
    for a, b in _DASH.items():
        s = s.replace(a, b)
    return s


# 主体模式：代字 + 编号（允许含 I/O/l 等易混字符，放宽匹配后再标记可疑）
P_STD = re.compile(
    r"(?:《(?P<title1>[^》]{2,48})》\s*[（(]?)?"
    r"(?P<code>(?:" + _PREFIX_ALT + r")\s*[A-Z]?\s*[\dIOl|o.\-—–－−]{2,20}\d)"
    r"(?:\s*[（(](?P<edition>\d{4}\s*年?版?)[）)])?"
    r"(?:\s*《(?P<title2>[^》]{2,48})》)?",
    re.I)
# 只有书名、无编号
P_TITLE_ONLY = re.compile(r"《(?P<title>[^》]{4,48}(?:规范|标准|规程|条例|办法|规定|通知|意见|大纲|导则|细则|方案|法))》")


_PREFIX_SORTED = sorted(_PREFIX, key=len, reverse=True)


def _fix_confusables(code: str) -> tuple[str, bool]:
    """把代字后的易混字符纠正为数字。返回 (纠正后, 是否曾可疑)。

    代字必须按已知清单切 —— 不能把 `JGJI00` 的 `JGJI` 全当字母前缀
    （那样 `I` 就永远纠正不了，JGJI00-1998 会原样保留）。
    """
    head = ""
    for p in _PREFIX_SORTED:
        if code.upper().startswith(p.upper()):
            head = code[:len(p)]
            break
    if not head:
        m = re.match(r"^([A-Za-z/]+)(.*)$", code)
        if not m:
            return code, False
        head, tail = m.group(1), m.group(2)
    else:
        tail = code[len(head):]
    suspect = bool(re.search(r"[IOl|o]", tail))
    if not suspect:
        return code, False
    fixed = "".join(_CONFUSE.get(ch, ch) for ch in tail)
    return head + fixed, True


def extract_standards(text: str, own_standard_codes: set[str] | None = None) -> list[dict]:
    """从一段文本里抽标准/规范引用。

    返回 [{"title","code","code_was","code_suspect","edition","span","raw"}]
    """
    s = text or ""
    out, taken = [], []
    skip = own_standard_codes or set()

    for m in P_STD.finditer(s):
        span = m.span()
        if any(a < span[1] and span[0] < b for a, b in taken):
            continue
        raw_code = m.group("code").replace(" ", "")
        code = _norm_dash(raw_code)
        fixed, suspect = _fix_confusables(code)
        if fixed in skip or code in skip:
            continue
        title = (m.group("title1") or m.group("title2") or "").strip("《》")
        taken.append(span)
        out.append({
            "title": title,
            "code": fixed,
            "code_was": raw_code if (suspect or raw_code != fixed) else "",
            "code_suspect": suspect,
            "suspect_reason": ("标准号含易混字符（I↔1 / O↔0），已纠正；需与原文核对"
                               if suspect else ""),
            "edition": (m.group("edition") or "").strip(),
            "span": span,
            "raw": s[max(0, span[0] - 2):span[1] + 2],
        })

    # 只有书名无编号的（单独登记，标「无编号」而不是丢弃）
    for m in P_TITLE_ONLY.finditer(s):
        span = m.span()
        if any(a < span[1] and span[0] < b for a, b in taken):
            continue
        out.append({
            "title": m.group("title").strip("《》"),
            "code": "",
            "code_was": "",
            "code_suspect": False,
            "suspect_reason": "",
            "edition": "",
            "span": span,
            "raw": m.group(0),
            "no_code": True,
        })

    out.sort(key=lambda x: x["span"][0])
    return out


# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    CASES = [
        "《建筑设计防火规范》GB50016-2014(2018年版)",
        "《汽车库建筑设计规范》JGJI00-1998",           # 笔误：I00 应为 100
        "《民用建筑设计通则》GB50352-2005",
        "《建筑工程建筑面积计算规范》GB/T50353-2013",
        "照明标准…按照国家标准GB50034—2013《建筑照明标准》执行",
        "根据《建筑物电子信息系统防雷技术规范》，所有进出校区的缆线",
        "《公共建筑节能设计标准》DGJ08-107-2015",
        "《无障碍设计规范》GB5O763-2O12",              # 笔误：O 应为 0
    ]
    print("=" * 88)
    print("标准抽取器自测")
    print("=" * 88)
    for c in CASES:
        print("\n" + c[:66])
        for h in extract_standards(c):
            flag = ""
            if h["code_suspect"]:
                flag = "  ⚠ 原文=%s 已纠正" % h["code_was"]
            if h.get("no_code"):
                flag = "  （无编号）"
            print("   %-22s %-20s %s%s" % (
                (h["title"] or "—")[:22], h["code"] or "—", h["edition"], flag))
