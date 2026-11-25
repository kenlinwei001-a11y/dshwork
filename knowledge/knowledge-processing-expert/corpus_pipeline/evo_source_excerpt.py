# -*- coding: utf-8 -*-
"""evo_source_excerpt —— 从原文 chunks 还原「某节的完整原文」（确定性，零 LLM）。

## 为什么需要

提示词不该只基于「形包」——形包是压缩产物，chunk 切碎、段落数虚低 50%。
提示词需要**该节的完整原文**，才能准确告诉 LLM「这一节原来长什么样、怎么写的」。

## 修复三个 chunk 缺陷

1. **一段塞多段**（55%）→ 按双空格（≥2）再拆
2. **边界不干净**（49%）→ 相邻 chunk 若上句未完、下句续接，则合并
3. **`$$...$$` 公式/引用块**（14 个）→ 单独识别为「引用块」，不混入正文

## 输出结构

    {
      "section": "投资估算",
      "paras": ["经测算，项目总投资为..."],          # 真实段落（已拆开）
      "tables": [{"cols": [...], "rows": [[...]], "nest": 4}],
      "quotes": ["$$ 参考《普通高等学校建筑面积指标》..."],  # 公式/规范引用块
      "prose_sample": "原文写法样例（前 300 字）",
      "chunk_ids": ["c-xxx", ...],                    # 溯源
    }
"""
from __future__ import annotations
import json
import re
from pathlib import Path


def _norm_sec(s: str, sub: dict) -> str:
    """章节名归一到形的抽象名（复用 evo_form 的逻辑）。"""
    try:
        from corpus_pipeline.evo_form import _normalize_sec
        return _normalize_sec(s, sub)
    except Exception:
        return str(s or "")


def _load_sub(pkg):
    try:
        from corpus_pipeline.evo_form import _load_substitution
        return _load_substitution(pkg)[0]
    except Exception:
        return {}


def _split_paras(text: str) -> list:
    """把 chunk 文本拆成真实段落。

    - `$$...$$` 取出为引用块（由调用方收集）
    - 双空格/双换行 → 分段
    - 保留原标点
    """
    t = str(text or "")
    # 抽 $$...$$ 引用块
    quotes = re.findall(r"\$\$(.+?)\$\$", t, re.S)
    t2 = re.sub(r"\$\$.+?\$\$", " ", t, flags=re.S)
    # 分段：双空格 / 双换行 / 中文句号后跟空格
    parts = re.split(r"(?:\s{2,}|\n+)", t2)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # 过滤 markdown 标题（属于下一节，不是本节正文）
        if re.match(r"^#{1,6}\s", p):
            continue
        # 结构标签（- 用水量计算 / - 用电量计算）必须独立成段，
        # 不能因为短就被合并进上一段 —— 它是原文的「形节点」。
        if len(p) >= 8 or re.match(r"^[-•·]\s*\S", p):
            out.append(p)
        elif out:
            out[-1] = out[-1] + p
        else:
            out.append(p)
    return out, [q.strip() for q in quotes if q.strip()]


def _merge_broken(paras: list) -> list:
    """只合并「明显被切断」的段落。

    判据（必须同时满足才合并）：
      ① 上段结尾**没有**任何句末标点（。；！？）】」』… . ）
      ② 上段结尾不是「：」（表格/列表引导符，后面本就该跟内容）
      ③ 下段开头是续接形态（小写字母/数字/逗号/顿号/括号内数字）
    **表格标题（表X-X）一律独立成段，不与前后合并。**
    """
    if not paras:
        return paras
    END = tuple("。；！？）】」』….:：")
    CONT = re.compile(r"^[a-z0-9,，、)）]|^（\d+）")
    TABCAP = re.compile(r"^表\s*\d")
    out = []
    for p in paras:
        if TABCAP.match(p):
            out.append(p)          # 表标题独立
            continue
        if out and out[-1] and not out[-1].endswith(END) and CONT.match(p):
            out[-1] = out[-1].rstrip() + p
        else:
            out.append(p)
    return out


def _parse_table(lines: list) -> dict:
    """复用 evo_form 的表格解析（含数据行语义推断）。"""
    try:
        from corpus_pipeline.evo_form import _parse_md_table
        return _parse_md_table(lines)
    except Exception:
        return {}


def excerpt(chunks_path, section: str, *, pkg=None) -> dict:
    """取某节的完整原文。

    chunks_path 既可以是 chunks.jsonl 路径，也可以是已加载的 chunk 列表
    —— 旧实现只接受路径，调用方传列表时异常被吞掉，导致 ⓿b 原文注入静默失效。
    """
    if isinstance(chunks_path, (list, tuple)):
        rows = list(chunks_path)
    else:
        rows = [json.loads(l) for l in Path(chunks_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    sub = _load_sub(pkg) if pkg else {}
    target = str(section or "").strip()

    hit = []
    for r in rows:
        sec = str(r.get("section") or "").strip()
        if not sec:
            continue
        if _norm_sec(sec, sub) == target or sec == target:
            hit.append(r)
    hit.sort(key=lambda r: r.get("index", 0))

    paras, quotes, tables, cids = [], [], [], []
    for r in hit:
        cids.append(r.get("id"))
        if r.get("type") == "table":
            lines = [l for l in (r.get("text") or "").splitlines() if l.strip().startswith("|")]
            t = _parse_table(lines)
            if t:
                # 保留完整行数据（不只 sample）
                body = []
                ll = [l for l in lines if l.strip().startswith("|")]
                if len(ll) >= 3:
                    body = [[c.strip() for c in l.strip("|").split("|")] for l in ll[2:]]
                # 复合表头：第二行是子表头（数量/单位/单位造价/合价）→ 已并入 cols，
                # 不能再当数据行（否则 13.3 会多出一行 47，而源表实际 46 行）。
                if body and any(x in " ".join(body[0]) for x in ("数量", "单位", "合价", "单位造价")) \
                        and sum(1 for c in body[0] if re.fullmatch(r"[\d,.]+", c or "")) <= 1:
                    body = body[1:]
                t["rows_data"] = body
                t["rows"] = len(body)
                tables.append(t)
        elif r.get("type") in ("paragraph", "heading"):
            ps, qs = _split_paras(r.get("text") or "")
            paras.extend(ps)
            quotes.extend(qs)

    paras = _merge_broken(paras)
    prose = "\n".join(paras)
    return {
        "section": target,
        "paras": paras,
        "tables": tables,
        "quotes": quotes,
        "prose_sample": prose[:400],
        "para_chars": len(re.sub(r"\s", "", prose)),
        "chunk_ids": cids,
        "chunk_count": len(hit),
    }
