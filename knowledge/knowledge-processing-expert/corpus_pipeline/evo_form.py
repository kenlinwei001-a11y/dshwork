# -*- coding: utf-8 -*-
"""evo_form —— 从语料抽「章节形态」（确定性，零 LLM）。

## 为什么这是根因修复

还原质量差，根因不是「值填错」，而是**提示词从来没告诉 LLM「这一节原文长什么样」**。
只给规则清单，LLM 只能自由发挥 → 原文 1 段 94 字 + 1 张 47 行表，
被写成 19 段 4,059 字 + 3 张小表。

「形态」= 段落数 / 段落角色 / 表格列定义 / 行数 / 嵌套层级 / 文体（表格为主 or 散文为主）。
**它和规则一样是「形」，必须被抽取、存储、注入提示词。**

## 抽什么

每节输出：
    paras          段落数
    para_chars     段落总字数
    para_roles     每段角色（引导 / 结论 / 说明 / 清单）
    tables         表格列表，每张含 cols / rows / nest / header / sample_rows
    table_chars    表格总字数
    style          table_dominant（表格为主）/ prose_dominant（散文为主）/ mixed
    target_chars   还原建议字数区间 = [原文总字 × 1.0, 原文总字 × 2.0]（允许更详细）

## 文体判据

    table_dominant : table_chars > para_chars * 2
    prose_dominant : para_chars > table_chars * 2
    mixed          : 其余
"""
from __future__ import annotations
import json
import re
from pathlib import Path


def _chars(s: str) -> int:
    return len(re.sub(r"\s", "", s or ""))


def _parse_md_table(lines: list) -> dict:
    """md 表格行 → {cols, rows, nest, sample_rows}。"""
    def cells(l):
        return [c.strip() for c in l.strip("|").split("|")]

    if len(lines) < 3:
        return {}
    h1 = cells(lines[0])
    # lines[1] 是分隔线；子表头在 lines[2]（若它像列名而非数据）
    separated = bool(re.fullmatch(r"[\s\-:|]+", lines[1].strip()))
    sub = cells(lines[2]) if separated and len(lines) > 2 else []
    body_start = 3 if separated else 2
    # 子表头判据：含量词/单位类词，且数字极少
    sub_is_header = bool(sub) and any(
        x in " ".join(sub) for x in ("数量", "单位", "合价", "单位造价", "定额", "天数", "单价")
    ) and sum(1 for c in sub if re.fullmatch(r"[\d,.]+", c or "")) <= 1
    if not sub_is_header:
        sub = []
        body_start = 2 if separated else 1
    body = [cells(l) for l in lines[body_start:]]
    # ★ 按数据行语义推断列（表头错位时不靠表头）
    if body and len(body[0]) >= 6:
        col0 = [r[0] if len(r) > 0 else "" for r in body]
        c2 = [r[2] if len(r) > 2 else "" for r in body]
        c3 = [r[3] if len(r) > 3 else "" for r in body]
        c4 = [r[4] if len(r) > 4 else "" for r in body]
        c5 = [r[5] if len(r) > 5 else "" for r in body]

        def _isnum(x):
            return bool(re.fullmatch(r"[\d,]+(?:\.\d+)?", (x or "").replace(" ", "")))

        def _isunit(x):
            return (x or "").strip() in ("㎡", "m2", "m", "部", "项", "台", "个", "间", "人", "kW", "m³", "万元")

        if (sum(1 for x in c3 if _isunit(x)) >= max(2, len(c3) // 2)
                and sum(1 for x in c2 if _isnum(x)) >= max(2, len(c2) // 2)
                and sum(1 for x in c5 if _isnum(x)) >= max(2, len(c5) // 2)):
            # 判定：列2=数量 列3=单位 列4=单价 列5=合价 列6=备注
            cols = ["序号", "工程和费用名称", "技术经济指标·数量", "技术经济指标·单位",
                    "技术经济指标·单位造价", "估算金额·合价", "备注"]
            nest = 1
            for x in col0:
                if re.fullmatch(r"[一二三四五六七八九十]+", x): nest = max(nest, 1)
                elif re.fullmatch(r"（[一二三四五六七八九十]+）", x): nest = max(nest, 2)
                elif re.fullmatch(r"\d+", x): nest = max(nest, 3)
                elif re.fullmatch(r"\d+\.\d+", x): nest = max(nest, 4)
            return {"cols": cols, "rows": len(body), "nest": nest,
                    "sample_rows": body[:3], "inferred": "按数据行语义"}

    # 复合表头：技术经济指标跨列 → 数量/单位；估算金额 → 合价
    if sub_is_header:
        cols = []
        for i, h in enumerate(h1):
            s = sub[i] if i < len(sub) else ""
            cols.append(("%s·%s" % (h, s)).strip("·") if s and s != h else h)
    else:
        cols = h1
    # 嵌套层级：看首列的编号形态
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
    return {"cols": [c for c in cols if c], "rows": len(body), "nest": nest,
            "sample_rows": body[:3]}


def _para_role(text: str, idx: int, total: int) -> str:
    """判段落角色。"""
    t = str(text or "").strip()
    if idx == 0 and ("如下表" in t or "详见" in t or "见表" in t):
        return "引导（引出表格）"
    if t.startswith("因此") or t.startswith("故") or "合计为" in t or "为1." in t or "为 1." in t:
        return "结论（表后小结）"
    if re.match(r"^[一二三四五六七八九十]+、|^\d+[.、]", t):
        return "清单"
    if len(t) < 60:
        return "短说明"
    return "说明"


def _load_substitution(pkg) -> tuple:
    """读 org_substitution：源语料包的具体名 → 形里的抽象名。"""
    import yaml as _y
    from pathlib import Path as _P
    try:
        d = _y.safe_load((_P(pkg)/"ontology"/"fact-aliases.yaml").read_text(encoding="utf-8")) or {}
        org = d.get("org_substitution") or {}
        srcs = [str(x) for x in (org.get("source_names") or [])]
        # 子系统A/B/C/D
        letters = ["A", "B", "C", "D", "E", "F"]
        m = {s: "子系统%s" % letters[i] for i, s in enumerate(srcs) if i < len(letters)}
        return m, {"校区名": None}
    except Exception:
        return {}, {}


def _normalize_sec(sec: str, sub: dict) -> str:
    """把原文的具体章节名归一到「形」里的抽象名。

    - 「管理科学与量化信息研究中心」→「子系统A」
    - 「改善中山北一路校区设施条件，建立良好科研环境的需要」
      →「改善{校区}设施条件，建立良好科研环境的需要」
    """
    s = str(sec or "").strip()
    if not s:
        return s
    # ① 分中心名 → 子系统N
    if s in sub:
        return sub[s]
    for k, v in sub.items():
        if k and k in s:
            return s.replace(k, v)
    # ② 校区/校名脱敏（形里用 {校区} / {建设单位}）
    import re as _re
    VERBS = ("改善", "提升", "优化", "完善", "满足", "保障", "推进", "加强", "建设", "改建", "扩建")
    # 定位：某动词之后、以「校区」结尾的地名短语（含「校区」两字）→ {校区}
    CAMPUS = r"[\u4e00-\u9fa5]{2,10}校区的?(?=设施|条件|东部|环境|周边)?"
    s2 = s
    for v in VERBS:
        if s2.startswith(v):
            rest = s2[len(v):]
            rest = _re.sub(r"^" + CAMPUS, "{校区}", rest)
            s2 = v + rest
            break
    else:
        s2 = _re.sub(r"^" + CAMPUS, "{校区}", s2)
    # 「提升X校园形象」→「提升{建设单位}校园形象」
    s2 = _re.sub(r"(?<=提升)[\u4e00-\u9fa5]{4,10}(?=校园形象)", "{建设单位}", s2)
    return s2


def extract(chunks_path, *, section_field="section", pkg=None) -> dict:
    """从 chunks.jsonl 抽全部章节形态。"""
    rows = [json.loads(l) for l in Path(chunks_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    sub, _ = _load_substitution(pkg) if pkg else ({}, {})
    by_sec = {}
    raw2norm = {}
    for r in rows:
        sec = str(r.get(section_field) or "").strip()
        if not sec:
            continue
        norm = _normalize_sec(sec, sub)
        raw2norm[sec] = norm
        by_sec.setdefault(norm, []).append(r)

    out = {}
    for sec, items in by_sec.items():
        paras, tables = [], []
        for r in items:
            if r.get("type") == "paragraph":
                paras.append(r.get("text") or "")
            elif r.get("type") == "table":
                lines = [l for l in (r.get("text") or "").splitlines() if l.strip().startswith("|")]
                t = _parse_md_table(lines)
                if t:
                    t["chunk_id"] = r.get("id")
                    t["chars"] = _chars(" ".join(lines))
                    tables.append(t)
        pc = sum(_chars(p) for p in paras)
        tc = sum(t["chars"] for t in tables)
        if tc > pc * 2:
            style = "table_dominant"
        elif pc > tc * 2:
            style = "prose_dominant"
        else:
            style = "mixed"
        total = pc + tc
        out[sec] = {
            "raw_sections": sorted({k for k, v in raw2norm.items() if v == sec}),
            "paras": len(paras),
            "para_chars": pc,
            "para_roles": [_para_role(p, i, len(paras)) for i, p in enumerate(paras)],
            "tables": tables,
            "table_chars": tc,
            "total_chars": total,
            "style": style,
            "target_chars": [total, int(total * 2.0)] if total else [0, 0],
            "guidance": _guidance(style, len(paras), len(tables), tables, total),
        }
    return out


def _guidance(style, n_paras, n_tables, tables, total) -> str:
    """给 LLM 的一句话形态指令。"""
    if style == "table_dominant" and n_tables:
        t = tables[0]
        cols = "/".join(t["cols"][:7])
        return ("**表格为主**：先写 1 段引导文字（陈述结论、引出下表），"
                "再出一张 %d 列 × 约 %d 行的表（列：%s），嵌套 %d 层；"
                "表后可有补充说明，但**不得把表格拆成多个小节**。总字数 %d–%d 字。"
                % (len(t["cols"]), t["rows"], cols, t["nest"], total, int(total * 2)))
    if style == "prose_dominant":
        return ("**散文为主**：%d 段叙述（%s），无表格或少表。总字数 %d–%d 字。"
                % (n_paras, "、".join(["引导/说明/结论"]), total, int(total * 2)))
    return ("**图文混排**：%d 段文字 + %d 张表。总字数 %d–%d 字。"
            % (n_paras, n_tables, total, int(total * 2)))
