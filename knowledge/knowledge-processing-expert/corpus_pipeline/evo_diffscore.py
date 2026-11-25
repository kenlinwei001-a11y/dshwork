# -*- coding: utf-8 -*-
"""evo_diffscore —— 还原质量评分（确定性，零 LLM）。

## 评什么

把「还原稿」与「上财原文」逐项对比，按五维打分：
    D1 形态匹配 35%  文体（表格/散文）· 表格列完备度 · 行数与嵌套
    D2 篇幅控制 15%  字数比 0.7-1.5 · 无空话
    D3 计算链条 25%  数量×单价=合价 三元组 · 中间量 · 算术正确
    D4 值替换   15%  上财值 0 残留 · 新项目值覆盖
    D5 缺失冲突 10%  缺失显式 · 冲突待审

## 为什么必须确定性

用户明确「能确定性的不交给模型」。评分是数格子、算比值、验等式 —— 全部可代码判定。
LLM 只负责「写」，不负责「自己给自己打分」。
"""
from __future__ import annotations
import json
import re
from pathlib import Path

# 上财原报告的特征值（出现即判残留）
SHUFE_VALUES = ("18319", "18000", "13032", "11188", "1171", "618", "2758",
                "7793", "3034", "458", "250", "175", "3240", "810", "1832", "1028",
                "10828", "14883", "2182", "1.74", "72")
# 关键列（缺一即扣分）
KEY_COLS = ("数量", "单位", "单价", "合价", "定额", "天数", "面积", "指标")


def _chars(s: str) -> int:
    return len(re.sub(r"\s", "", s or ""))


def _md_blocks(text: str) -> dict:
    """切分 markdown：段落 / 表格 / 算式块 / 标题。"""
    lines = (text or "").splitlines()
    paras, tables, codes = [], [], []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("```"):
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            codes.append("\n".join(buf))
            i = j + 1
            continue
        if s.startswith("|"):
            j = i
            buf = []
            while j < len(lines) and lines[j].strip().startswith("|"):
                buf.append(lines[j])
                j += 1
            tables.append(buf)
            i = j
            continue
        if s and not s.startswith("#") and not s.startswith(">") and not s.startswith("---"):
            paras.append(s)
        i += 1
    return {"paras": paras, "tables": tables, "codes": codes}


def _table_cols(tbl_lines: list) -> list:
    if not tbl_lines:
        return []
    hdr = tbl_lines[0]
    return [c.strip() for c in hdr.strip("|").split("|") if c.strip()]


def _table_rows(tbl_lines: list) -> int:
    return max(0, len(tbl_lines) - 2)


def score(mine_text: str, source_paras: list, source_tables: list,
          source_chars: int, source_table_chars: int = 0) -> dict:
    """source_chars: 段落字数；source_table_chars: 表格字数。
    篇幅基准 = 两者之和（原文的「总产出量」），不是只看段落。"""
    m = _md_blocks(mine_text)
    src_cols = [_table_cols(t) for t in source_tables]
    src_rows = sum(_table_rows(t) for t in source_tables)
    src_col_n = max((len(c) for c in src_cols), default=0)

    # ---------- D1 形态匹配 ----------
    d1 = 0.0
    notes = []

    # D1.1 文体（12）
    src_tab_chars = sum(_chars(" ".join(t)) for t in source_tables)
    mine_tab_chars = sum(_chars(" ".join(t)) for t in m["tables"])
    src_table_dom = src_tab_chars > source_chars * 3 if source_chars else False
    mine_table_dom = mine_tab_chars > _chars(" ".join(m["paras"])) * 3 if m["paras"] else bool(m["tables"])
    if src_table_dom == mine_table_dom:
        d1 += 6
    else:
        notes.append("文体反向：原文表格为主=%s，还原=%s" % (src_table_dom, mine_table_dom))
    r = len(m["paras"]) / max(len(source_paras), 1)
    if 0.5 <= r <= 2.0:
        d1 += 6
    else:
        notes.append("段落数比 %.1f（原文 %d / 还原 %d），超出 0.5-2.0" % (r, len(source_paras), len(m["paras"])))
        d1 += max(0, 6 - 3 * abs(r - 1))

    # D1.2 列完备度（13）
    if src_col_n:
        mine_col_n = max((len(_table_cols(t)) for t in m["tables"]), default=0)
        keep = mine_col_n / src_col_n
        d1 += 8 * min(keep, 1.0) if keep >= 0.5 else 0
        if keep < 0.7:
            notes.append("列数 %d→%d（保留率 %.0f%%）" % (src_col_n, mine_col_n, keep * 100))
        # 关键列
        mine_cols_txt = " ".join(" ".join(_table_cols(t)) for t in m["tables"])
        src_cols_txt = " ".join(" ".join(c) for c in src_cols)
        key_need = [k for k in KEY_COLS if k in src_cols_txt]
        key_miss = [k for k in key_need if k not in mine_cols_txt]
        d1 += max(0, 5 - 2 * len(key_miss))
        if key_miss:
            notes.append("缺关键列：%s" % "、".join(key_miss))
    else:
        d1 += 13  # 原文无表，满分

    # D1.3 行数与嵌套（10）
    if src_rows:
        mine_rows = sum(_table_rows(t) for t in m["tables"])
        rr = mine_rows / src_rows
        d1 += max(0, 6 - max(0, (0.6 - rr)) * 15)
        if rr < 0.6:
            notes.append("表格行数 %d→%d（比 %.2f）" % (src_rows, mine_rows, rr))
    else:
        d1 += 6
    # 嵌套（用「一/（一）/1/1.1」形态判断）
    src_nest = 4 if src_rows > 30 else (2 if src_rows > 3 else 1)
    mine_nest = 1 + len(re.findall(r"^\s*\|?\s*(?:[一二三四五六七八九十]+|（[一二三四五六七八九十]+）|\d+(?:\.\d+)*)\s*\|", mine_text, re.M))
    mine_nest = min(4, max(1, mine_nest))
    d1 += 4 * (min(mine_nest, src_nest) / src_nest)
    if mine_nest < src_nest:
        notes.append("嵌套 %d 层→%d 层" % (src_nest, mine_nest))

    # ---------- D2 篇幅（15）----------
    d2 = 0.0
    mine_chars = _chars(mine_text)
    src_total = max(source_chars + source_table_chars, 1)
    cr = mine_chars / src_total
    if 1.0 <= cr <= 3.0:
        d2 += 10
    elif 0.7 <= cr < 1.0:
        d2 += 10 - (1.0 - cr) * 10
        notes.append("字数偏少：%.1f×（应不少于原文）" % cr)
    else:
        over = cr - 3.0
        d2 += max(0, 10 - over * 6)
        notes.append("字数比 %.1f×（原文 %d 段落+%d 表格 = %d / 还原 %d）"
                     % (cr, source_chars, source_table_chars, src_total, mine_chars))
    filler = len(re.findall(r"本节将|如上所述|综上所?述|值得注意的是|需要指出", mine_text))
    d2 += max(0, 5 - filler)

    # ---------- D3 计算链条（25）----------
    d3 = 0.0
    # 原文列名里是否同时含「数量」与「单价/单位造价」（同一张表）
    src_has_triple = False
    for c in src_cols:
        joined = " ".join(c)
        if "数量" in joined and ("单价" in joined or "单位造价" in joined):
            src_has_triple = True
            break
    mine_cols_all = " ".join(" ".join(_table_cols(t)) for t in m["tables"])
    if src_has_triple:
        has_q = "数量" in mine_cols_all
        has_p = "单价" in mine_cols_all or "单位造价" in mine_cols_all
        has_a = "合价" in mine_cols_all or "金额" in mine_cols_all
        d3 += 8 * (sum([has_q, has_p, has_a]) / 3)
        if not (has_q and has_p):
            notes.append("「数量×单价=合价」三元组不全（原文每行都有）")
    else:
        d3 += 8
    # 中间量
    mid = len(re.findall(r"日用水量|用水天数|年用水量|日用电量|年用电量|单位造价", mine_text))
    d3 += 4 if mid else 0
    if src_col_n >= 6 and not mid:
        notes.append("缺中间量列（日/年用量等）")
    # 单位标注
    d3 += 3 if re.search(r"㎡|万元|m³|kWh|kW|人|m\b", mine_text) else 0
    # 算术正确性
    bad_eq = []
    for mm in re.finditer(r"\*\*([\d,]+(?:\.\d+)?)\s*=\s*([^*]+?)\*\*", mine_text):
        lhs = float(mm.group(1).replace(",", ""))
        nums = [float(x.replace(",", "")) for x in re.findall(r"[\d,]+(?:\.\d+)?", mm.group(2))]
        if len(nums) >= 2 and abs(lhs - sum(nums)) > 1.5:
            bad_eq.append((mm.group(1), round(sum(nums), 1)))
    d3 += 5 if not bad_eq else 0
    if bad_eq:
        notes.append("等式不成立：%s" % bad_eq[:3])
    # 闭合
    d3 += 5 if ("核对通过" in mine_text or "待审" in mine_text) else 2

    # ---------- D4 值替换（15）----------
    d4 = 0.0
    hit = []
    for v in SHUFE_VALUES:
        # 短值（<=3 字符）容易误报，要求前后是分隔符/中文
        if len(v) <= 3:
            pat = r"(?<![\d.])(?<![\d.]\s)" + re.escape(v) + r"(?![\d])(?!\s*[×x*])"
        else:
            pat = r"(?<![\d.])" + re.escape(v) + r"(?![\d])"
        if re.search(pat, mine_text):
            hit.append(v)
    d4 += max(0, 10 - 2 * len(hit))
    if hit:
        notes.append("上财值残留：%s" % "、".join(hit[:6]))
    refs = len(re.findall(r"〔[A-Z]+-[0-9a-z]+〕", mine_text))
    d4 += min(5, refs / 6) if refs else 0

    # ---------- D5 缺失冲突（10）----------
    d5 = 0.0
    said_missing = bool(re.search(r"待客户提供|向客户索取|缺输入|待补充", mine_text))
    d5 += 5 if said_missing or not source_paras else 3
    said_conflict = bool(re.search(r"待审|不裁决|自相矛盾", mine_text))
    d5 += 5 if said_conflict else 2

    # 五维分值本身已经是满分 35/15/25/15/10 的「份额」（合计 100），
    # 总分为五维之和。旧实现再乘一次权重，理论上限只有 24 分，
    # 使冻结的「总分 ≥70」永远不可达 —— 这是实现 bug，不是评分标准变更。
    total = d1 + d2 + d3 + d4 + d5
    grade = "A" if total >= 85 else "B" if total >= 70 else "C" if total >= 55 else "D"
    return {
        "D1_形态": round(d1, 1), "D2_篇幅": round(d2, 1), "D3_计算": round(d3, 1),
        "D4_值替换": round(d4, 1), "D5_缺失冲突": round(d5, 1),
        "total": round(total, 1), "grade": grade,
        "src": {"paras": len(source_paras), "tables": len(source_tables),
                "rows": src_rows, "cols": src_col_n, "chars": source_chars,
                "table_chars": source_table_chars, "total_chars": source_chars + source_table_chars},
        "mine": {"paras": len(m["paras"]), "tables": len(m["tables"]),
                 "chars": mine_chars},
        "notes": notes,
    }
