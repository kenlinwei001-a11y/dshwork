# -*- coding: utf-8 -*-
"""evo_source_section —— 从 normalized.md 按「标题名称」抽取某节完整原文。

## 为什么不用 chunks

chunks 是切片产物，边界可能把本节最后一句划给下一节
（实测 7.2.2 的「因此，项目年总耗电量…」被划到「能耗指标分析」）。
用户要求：提示词基于**完整原文**，且**章节/子章节名称是第一匹配优先级**。

## 匹配顺序

1. markdown 标题（#..######）的文本 == title → 取到下一个同级/更高级标题
2. 普通文本小标题（整行 == title，且不在表格/代码块内）→ 取到下一个已知节标题
3. 找不到 → 返回空

stop_titles: 形包里的全部节标题；用于普通小标题的右边界。
"""
from __future__ import annotations

import re


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(line: str) -> bool:
    return bool(re.fullmatch(r"[\s\-:|]+", line.strip()))


def _parse_table(table_lines: list) -> dict:
    """表格行 → {cols, rows_data, rows, nest}。复合表头的子表头并入 cols。"""
    lines = [l for l in table_lines if l.strip().startswith("|")]
    if len(lines) < 2:
        return {}
    h1 = _cells(lines[0])
    body_start = 2 if _is_sep(lines[1]) else 1
    body = [_cells(l) for l in lines[body_start:]]
    # 复合表头：第二行是子表头 → 并入列名，不进数据行
    sub = []
    if body:
        first = body[0]
        if (any(x in " ".join(first) for x in ("数量", "单位", "合价", "单位造价", "定额", "天数", "单价"))
                and sum(1 for c in first if re.fullmatch(r"[\d,.]+", c or "")) <= 1):
            sub = first
            body = body[1:]
    # 合并单元格在 markdown 拍平后位置信息会丢失（尾部空列 ≠ 跨列）。
    # 复用 evo_form._parse_md_table 的「按数据行语义推断列」，
    # 它能把 13.3 正确推成 7 列；推断不出时退回首行非空列。
    try:
        from corpus_pipeline.evo_form import _parse_md_table
        parsed = _parse_md_table(lines) or {}
    except Exception:
        parsed = {}
    cols = parsed.get("cols") or [c for c in h1 if c]
    nest = 1
    for r in body:
        c0 = r[0] if r else ""
        if re.fullmatch(r"[一二三四五六七八九十]+", c0):
            nest = max(nest, 1)
        elif re.fullmatch(r"（[一二三四五六七八九十]+）", c0):
            nest = max(nest, 2)
        elif re.fullmatch(r"\d+", c0):
            nest = max(nest, 3)
        elif re.fullmatch(r"\d+\.\d+", c0):
            nest = max(nest, 4)
    return {"cols": cols, "rows_data": body, "rows": len(body), "nest": nest}


def _blocks(lines: list) -> dict:
    paras, tables, quotes = [], [], []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("```"):
            lang = s[3:].strip().lower()
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            if lang == "table" or (buf and buf[0].strip().startswith("|")):
                t = _parse_table(buf)
                if t:
                    tables.append(t)
            elif buf:
                quotes.append("\n".join(buf).strip())
            i = j + 1
            continue
        if s.startswith("|"):
            j = i
            buf = []
            while j < len(lines) and lines[j].strip().startswith("|"):
                buf.append(lines[j])
                j += 1
            t = _parse_table(buf)
            if t:
                tables.append(t)
            i = j
            continue
        if s and not s.startswith("#") and not s.startswith(">") and not s.startswith("---"):
            paras.append(s)
        i += 1
    return {"paras": paras, "tables": tables, "quotes": quotes}


def extract_section(md_text: str, title: str, *, stop_titles=None) -> dict:
    """按名称抽取一节完整原文。"""
    lines = (md_text or "").splitlines()
    title = str(title or "").strip()
    stop = {str(t).strip() for t in (stop_titles or []) if str(t).strip()}
    stop.discard(title)

    start = end = None
    mode = None

    # ① markdown 标题
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m and m.group(2).strip() == title:
            level = len(m.group(1))
            start = i + 1
            mode = "heading"
            for j in range(start, len(lines)):
                sj = lines[j].strip()
                m2 = re.match(r"^(#{1,6})\s+", lines[j])
                if m2 and len(m2.group(1)) <= level:
                    end = j
                    break
                # 普通文本小标题也是边界：13.4 资金筹措必须在「学校财务状况」
                # （13.4.1）处停下，不能把 13.4.1/13.4.2 一并吞入。
                if sj in stop:
                    end = j
                    break
            break

    # ② 普通文本小标题（不在表格/代码块内）
    if start is None:
        in_code = False
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("```"):
                in_code = not in_code
                continue
            if in_code or s.startswith("|"):
                continue
            if s == title:
                start = i + 1
                mode = "plain"
                for j in range(start, len(lines)):
                    sj = lines[j].strip()
                    if sj.startswith("#") or sj in stop:
                        end = j
                        break
                break

    if start is None:
        return {"section": title, "paras": [], "tables": [], "quotes": [],
                "para_chars": 0, "found": False, "mode": None}

    body = lines[start:end if end is not None else len(lines)]
    b = _blocks(body)
    chars = len(re.sub(r"\s", "", "\n".join(b["paras"])))
    return {"section": title, "paras": b["paras"], "tables": b["tables"],
            "quotes": b["quotes"], "para_chars": chars, "found": True, "mode": mode}
