# -*- coding: utf-8 -*-
"""evo_split —— 用 Semantica 的 TextSplitter 切片（跨解释器，subprocess 调 worker）。

## 架构

    本项目 venv（3.9）                    semantica venv（3.11）
    evo_split.split_document()  ──stdin──►  _split_worker.py
        │                                   TextSplitter(method=…)
        └──────────── stdout JSON ◄─────────  chunks
    加：章节归属 / 表格整块 / span 重算

## 为什么 subprocess

semantica 装在 /Users/apple/.venvs/semantica（Py3.11），
本项目在 knowledge-processing-expert/.venv（Py3.9）。
不同解释器无法直接 import，只能 subprocess。

## 为什么分章节调用

整篇一次切会让 `structural` 把目录也当正文。按 markdown 标题先切章节，
再对每章正文调 worker，得到「章节归属 + 语义边界」双保险。

## 输出

与现有 chunks.jsonl 兼容，并新增：
    para_count   本 chunk 含几个真实段落（旧切片 55% 一段塞多段）
    method       用了哪种方法
    section_struct_no  章节结构号
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

SEM_PY = "/Users/apple/.venvs/semantica/bin/python"
WORKER = Path(__file__).resolve().parent / "_split_worker.py"


def available() -> dict:
    """探测 semantica venv + split 是否可用。"""
    try:
        r = subprocess.run(
            [SEM_PY, "-c",
             "from semantica.split import TextSplitter;print('ok')"],
            capture_output=True, text=True, timeout=60)
        ok = "ok" in (r.stdout or "")
        err = "" if ok else (r.stderr or "")[-300:]
    except Exception as e:
        ok, err = False, str(e)
    return {"available": ok, "error": err,
            "worker": str(WORKER), "sem_python": SEM_PY,
            "methods": ["recursive", "paragraph", "structural", "sentence", "token",
                        "word", "character", "sliding_window", "semantic_transformer",
                        "entity_aware", "relation_aware", "hierarchical"]}


def _cid(text: str, start: int) -> str:
    h = hashlib.sha256(("%d|%s" % (start, text[:80])).encode("utf-8")).hexdigest()
    return "c-" + h[:12]


def _split_sections(md: str) -> list:
    """按 markdown 标题切章节（保留层级与偏移）。"""
    lines = md.splitlines(keepends=True)
    offs = [0]
    for ln in lines:
        offs.append(offs[-1] + len(ln))
    heads = []
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", ln.rstrip("\n"))
        if m:
            heads.append({"level": len(m.group(1)), "title": m.group(2).strip(),
                          "start": offs[i]})
    # 目录/封面 不属于正文，跳过
    SKIP = ("目录", "封面与编制信息", "封面")
    out, stack = [], []
    for idx, h in enumerate(heads):
        while stack and stack[-1][0] >= h["level"]:
            stack.pop()
        stack.append((h["level"], h["title"]))
        end = heads[idx + 1]["start"] if idx + 1 < len(heads) else len(md)
        if any(s in h["title"] for s in SKIP):
            continue
        out.append({"title": h["title"], "path": [t for _, t in stack],
                    "level": h["level"], "start": h["start"],
                    "body": md[h["start"]:end]})
    return out


def _struct_no(sections: list) -> None:
    counters = {}
    for s in sections:
        lv = s["level"]
        counters[lv] = counters.get(lv, 0) + 1
        for k in list(counters):
            if k > lv:
                del counters[k]
        s["struct_no"] = ".".join(str(counters[k]) for k in sorted(counters))


_TBL = re.compile(r"^```table\s*$.*?^```\s*$", re.M | re.S)
_DOLLAR = re.compile(r"\$\$.+?\$\$", re.S)


def _atomic_blocks(body: str) -> list:
    """表格/公式块整块保留，返回 [(kind, start, end, text)]。"""
    marks = [("table", m.start(), m.end(), body[m.start():m.end()])
             for m in _TBL.finditer(body)]
    for m in _DOLLAR.finditer(body):
        if not any(a <= m.start() < b for _, a, b, _ in marks):
            marks.append(("quote", m.start(), m.end(), body[m.start():m.end()]))
    marks.sort(key=lambda x: x[1])
    return marks


def _call_worker_batch(segments: list, method: str, chunk_size: int,
                       chunk_overlap: int) -> dict:
    """一次 subprocess 处理全部段落。返回 {key: [chunks]}。

    为什么批量：按章节逐段起进程，几百次 Python 启动会超时（每次 2-3 秒）。
    """
    if not segments:
        return {}
    req = json.dumps({"method": method, "chunk_size": chunk_size,
                      "chunk_overlap": chunk_overlap,
                      "segments": segments}, ensure_ascii=False)
    try:
        r = subprocess.run([SEM_PY, str(WORKER)], input=req,
                           capture_output=True, text=True, timeout=1800)
        d = json.loads((r.stdout or "").strip() or "{}")
        if not d.get("ok"):
            return {}
        return {x["key"]: (x.get("chunks") or []) for x in (d.get("results") or [])}
    except Exception:
        return {}


def split_document(md_path, *, method="structural", chunk_size=1200,
                   chunk_overlap=120, min_chars=20) -> list:
    """按章节切 → 收集所有正文段落 → 批量调 worker → 组装回章节。

    两遍设计：先收集（可批量），后组装（保留章节归属）。
    """
    md = Path(md_path).read_text(encoding="utf-8")
    sections = _split_sections(md)
    if not sections:
        sections = [{"title": "", "path": [], "level": 0, "start": 0, "body": md}]
    _struct_no(sections)

    # ---- 第一遍：把每节切成「原子块」和「待切正文段」 ----
    plan = []          # [(sec, kind, abs_start, text, key_or_None)]
    batch = []         # [{key, text}]
    for si, sec in enumerate(sections):
        body, base = sec["body"], sec["start"]
        atomics = _atomic_blocks(body)
        pos = 0
        segs = []
        for kind, a, b, txt in atomics:
            if a > pos:
                segs.append(("prose", base + pos, body[pos:a]))
            segs.append((kind, base + a, txt))
            pos = b
        if pos < len(body):
            segs.append(("prose", base + pos, body[pos:]))

        for pi, (kind, abs_start, seg) in enumerate(segs):
            if not seg.strip() or len(seg.strip()) < min_chars:
                continue
            if kind in ("table", "quote"):
                plan.append((sec, kind, abs_start, seg, None))
            else:
                key = "s%d_%d" % (si, pi)
                batch.append({"key": key, "text": seg})
                plan.append((sec, "prose", abs_start, seg, key))

    # ---- 批量调 worker（只起一次进程）----
    got = _call_worker_batch(batch, method, chunk_size, chunk_overlap)

    # ---- 第二遍：组装 ----
    out, idx = [], 0
    for sec, kind, abs_start, seg, key in plan:
        if kind in ("table", "quote"):
            out.append({"id": _cid(seg, abs_start), "index": idx, "type": kind,
                        "span": [abs_start, abs_start + len(seg)], "text": seg,
                        "section": sec["title"], "section_path": sec["path"],
                        "section_struct_no": sec.get("struct_no", ""),
                        "method": "atomic", "para_count": 1,
                        "entities": [], "relationships": []})
            idx += 1
            continue

        cs = got.get(key) or []
        if not cs:
            for pa in re.split(r"\n{2,}", seg):
                if not pa.strip() or len(pa.strip()) < min_chars:
                    continue
                off = seg.find(pa)
                out.append({"id": _cid(pa, abs_start + max(off, 0)), "index": idx,
                            "type": "paragraph",
                            "span": [abs_start + max(off, 0),
                                     abs_start + max(off, 0) + len(pa)],
                            "text": pa.strip(), "section": sec["title"],
                            "section_path": sec["path"],
                            "section_struct_no": sec.get("struct_no", ""),
                            "method": "fallback_para", "para_count": 1,
                            "entities": [], "relationships": []})
                idx += 1
            continue

        for c in cs:
            txt = c.get("text") or ""
            if len(txt.strip()) < min_chars:
                continue
            st = c.get("start", 0) or 0
            out.append({"id": _cid(txt, abs_start + st), "index": idx,
                        "type": "paragraph",
                        "span": [abs_start + st, abs_start + st + len(txt)],
                        "text": txt, "section": sec["title"],
                        "section_path": sec["path"],
                        "section_struct_no": sec.get("struct_no", ""),
                        "method": c.get("method", method),
                        "para_count": c.get("para_count") or 1,
                        "elements": c.get("element_types"),
                        "entities": [], "relationships": []})
            idx += 1
    return out


def write_jsonl(chunks: list, out_path) -> dict:
    from collections import Counter
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return {"out": str(p), "count": len(chunks),
            "type": dict(Counter(c["type"] for c in chunks)),
            "method": dict(Counter(c["method"] for c in chunks)),
            "paras_total": sum(c.get("para_count", 1) for c in chunks),
            "chars": sum(len(c["text"]) for c in chunks),
            "sections": len({c["section"] for c in chunks})}


# ================================================================ 混合模式
# 章节归属用「原 chunks」（代码按 pStyle 切的，最准）
# 切分边界用 semantica（段落/表格/公式块识别最准）

def split_with_known_sections(md_path, sections_from_chunks,
                              *, method="structural", chunk_size=1200,
                              chunk_overlap=120, min_chars=20) -> list:
    """用「已知章节归属」+ semantica 切分。

    sections_from_chunks: [{"section","section_path","section_struct_no",
                            "start","end","text"}]
        —— 从既有 chunks.jsonl 按 section 聚合得到（含 span 范围）。

    为什么需要：normalized.md 的 markdown 标题只覆盖 145/151 节，
    部分节标题（如「各类能耗指标计算」）没转成 #，按 md 标题切会漏。
    而原 chunks 的 section 是代码按 docx pStyle 切的，覆盖完整。
    """
    md = Path(md_path).read_text(encoding="utf-8")
    plan, batch = [], []
    for si, sec in enumerate(sections_from_chunks):
        # 优先用章节自己的 span；没有则按 section 名在全文里找
        st = sec.get("start")
        en = sec.get("end")
        if st is None or en is None:
            name = str(sec.get("section") or "")
            if not name:
                continue
            pos = md.find(name)
            if pos < 0:
                continue
            st = pos
            en = min(len(md), pos + len(sec.get("text") or "") or pos + 5000)
        body = md[st:en]
        if not body.strip():
            continue
        atomics = _atomic_blocks(body)
        pos2 = 0
        segs = []
        for kind, a, b, txt in atomics:
            if a > pos2:
                segs.append(("prose", st + pos2, body[pos2:a]))
            segs.append((kind, st + a, txt))
            pos2 = b
        if pos2 < len(body):
            segs.append(("prose", st + pos2, body[pos2:]))

        for pi, (kind, abs_start, seg) in enumerate(segs):
            if not seg.strip() or len(seg.strip()) < min_chars:
                continue
            if kind in ("table", "quote"):
                plan.append((sec, kind, abs_start, seg, None))
            else:
                key = "s%d_%d" % (si, pi)
                batch.append({"key": key, "text": seg})
                plan.append((sec, "prose", abs_start, seg, key))

    got = _call_worker_batch(batch, method, chunk_size, chunk_overlap)

    out, idx = [], 0
    for sec, kind, abs_start, seg, key in plan:
        base = {"section": sec.get("section", ""),
                "section_path": sec.get("section_path") or [],
                "section_struct_no": sec.get("section_struct_no", "")}
        if kind in ("table", "quote"):
            out.append({"id": _cid(seg, abs_start), "index": idx, "type": kind,
                        "span": [abs_start, abs_start + len(seg)], "text": seg,
                        "method": "atomic", "para_count": 1,
                        "entities": [], "relationships": [], **base})
            idx += 1
            continue
        cs = got.get(key) or []
        if not cs:
            for pa in re.split(r"\n{2,}", seg):
                if not pa.strip() or len(pa.strip()) < min_chars:
                    continue
                off = seg.find(pa)
                out.append({"id": _cid(pa, abs_start + max(off, 0)), "index": idx,
                            "type": "paragraph",
                            "span": [abs_start + max(off, 0),
                                     abs_start + max(off, 0) + len(pa)],
                            "text": pa.strip(), "method": "fallback_para",
                            "para_count": 1, "entities": [], "relationships": [],
                            **base})
                idx += 1
            continue
        for c in cs:
            txt = c.get("text") or ""
            if len(txt.strip()) < min_chars:
                continue
            st2 = c.get("start", 0) or 0
            out.append({"id": _cid(txt, abs_start + st2), "index": idx,
                        "type": "paragraph",
                        "span": [abs_start + st2, abs_start + st2 + len(txt)],
                        "text": txt, "method": c.get("method", method),
                        "para_count": c.get("para_count") or 1,
                        "elements": c.get("element_types"),
                        "entities": [], "relationships": [], **base})
            idx += 1
    return out


def sections_from_jsonl(jsonl_path, md_path=None) -> list:
    """从既有 chunks.jsonl 聚合章节；**不用 span**（已知偏移不可靠）。

    若给 md_path，则按「section 名在 md 里的出现顺序」确定每节范围：
    第 i 节的起点 = 第 i 个 section 名首次出现位置；终点 = 第 i+1 节的起点。
    这样不依赖 span，也不会重复。
    """
    rows = [json.loads(l) for l in Path(jsonl_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    order, by = [], {}
    for r in rows:
        s = str(r.get("section") or "").strip()
        if not s:
            continue
        if s not in by:
            order.append(s)
            by[s] = {"section": s,
                     "section_path": r.get("section_path") or [],
                     "section_struct_no": r.get("section_struct_no", ""),
                     "text": ""}
        by[s]["text"] += (r.get("text") or "")

    if md_path:
        md = Path(md_path).read_text(encoding="utf-8")
        # 逐节找首次出现位置（从上一节之后开始找，保证顺序）
        cursor = 0
        starts = {}
        for s in order:
            pos = md.find(s, cursor)
            if pos < 0:
                pos = md.find(s)      # 回退：全局找
            starts[s] = pos
            if pos >= 0:
                cursor = pos + len(s)
        # 按起点排序后，终点 = 下一节起点
        ranked = sorted([(starts.get(s, -1), s) for s in order], key=lambda x: x[0])
        valid = [(p, s) for p, s in ranked if p >= 0]
        for i, (p, s) in enumerate(valid):
            e = valid[i + 1][0] if i + 1 < len(valid) else len(md)
            by[s]["start"] = p
            by[s]["end"] = e
        return [by[s] for s in order if by[s].get("start") is not None]

    return list(by.values())


# ================================================================ 补漏：无 # 的节标题
# normalized.md 有 6 个节标题没转成 markdown #（如「各类能耗指标计算」）。
# 这些标题在正文里是独立一行纯文本。用「已知节标题表」做补充锚点。

def _promote_plain_headings(md: str, known_titles: list) -> str:
    """把正文里「独立成行且等于已知节标题」的行升级成 ## 标题。

    只在「该行前后有空行 + 行长度 < 40 + 不以标点结尾」时升级，
    避免误伤正文里提到同一词语的句子。
    """
    lines = md.splitlines(keepends=True)
    out = []
    tset = {x.strip() for x in known_titles if x and len(x.strip()) <= 40}
    for i, ln in enumerate(lines):
        s = ln.strip()
        prev_blank = (i == 0) or (not lines[i-1].strip())
        next_blank = (i + 1 >= len(lines)) or (not lines[i+1].strip())
        if (s in tset and prev_blank and next_blank
                and not s.startswith(("#", "|", "-", "*", "$$"))
                and not s.endswith(("。", "；", "：", "，", ")", "）"))):
            out.append("## " + s + "\n")
        else:
            out.append(ln)
    return "".join(out)


def split_document_enhanced(md_path, known_section_titles=None, *,
                            method="structural", chunk_size=1200,
                            chunk_overlap=120, min_chars=20) -> list:
    """split_document 的增强版：先用已知节标题补 # 标记，再正常切。

    known_section_titles: 从 outline-*.yaml 或原 chunks 收集的节标题列表。
    """
    md = Path(md_path).read_text(encoding="utf-8")
    if known_section_titles:
        md2 = _promote_plain_headings(md, known_section_titles)
        tmp = Path("/tmp") / "_md_promoted.md"
        tmp.write_text(md2, encoding="utf-8")
        return split_document(tmp, method=method, chunk_size=chunk_size,
                              chunk_overlap=chunk_overlap, min_chars=min_chars)
    return split_document(md_path, method=method, chunk_size=chunk_size,
                          chunk_overlap=chunk_overlap, min_chars=min_chars)
