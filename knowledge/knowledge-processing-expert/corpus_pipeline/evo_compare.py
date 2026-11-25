# -*- coding: utf-8 -*-
"""evo_compare —— 知识处理专家侧的比对器（不是写作专家自评）。

两个硬门（按用户目标）：

门 1 子章节对应
  * 段落数差 > 1 → fail
  * 表格数不一致 → fail
  * 原文表格缺 1 列 → fail
  * 表格行数差 > 1 → fail
  * must_cover 缺 1 项 → fail
  * 语义对位 avg < 0.4 → fail
  * 数值字面量未绑定 node → fail
  * 缺失项未进 unresolved → fail
  * 表格全是「待客户提供」/「—」→ fail

门 2 跨章节节点一致性
  * 正文引用的 node_id 必须存在
  * 同一 subject 出现不同值且未标待审 → fail
  * 同一 node_id 在多节填槽值不同且未标待审 → fail
  * new_claims 的数字必须有 supports 支撑
  * 与本节相关的冲突必须在正文/new_claims 中披露（CFx 或「待审」）

用法：
  python -m corpus_pipeline.evo_compare --section 1.1 \
      --writing ROOT/writing-output/1.1.json \
      --package ROOT/work-packages/1.1.json \
      --root ROOT --out ROOT/writing-output/1.1.compare.json
  python -m corpus_pipeline.evo_compare --self-test --root ROOT
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from .evo_corpus_api import (
        NODE_REF_RE,
        load_derived_nodes,
        load_graph,
        norm_section,
        project_root,
    )
    from .evo_work_package import build_work_package
except Exception:  # 直接脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from corpus_pipeline.evo_corpus_api import (  # type: ignore
        NODE_REF_RE,
        load_derived_nodes,
        load_graph,
        norm_section,
        project_root,
    )
    from corpus_pipeline.evo_work_package import build_work_package  # type: ignore

SIM_THRESHOLD = 0.4
PARA_DIFF = 1
ROW_DIFF = 1
COVERAGE_MIN = 0.4
PLACEHOLDER_WORDS = ("待客户提供", "待提供", "待定", "待补", "待查", "—", "-", "暂无")


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _load(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    p = Path(obj)
    return json.loads(p.read_text(encoding="utf-8"))


def _norm_text(s: Any) -> str:
    s = str(s or "")
    s = NODE_REF_RE.sub("", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"[\s\-—–•·*#>`]+", "", s)
    s = re.sub(r"[，。；：、！？,.;:!?（）()\[\]【】「」『』\"'“”‘’]+", "", s)
    return s


def _num(s: Any) -> Optional[float]:
    if isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s or "").strip().replace(",", "")
    if re.fullmatch(r"-?\d+(?:\.\d+)?", t):
        return float(t)
    return None


def _value_key(v: Any) -> str:
    n = _num(v)
    if n is None:
        return str(v or "").strip()
    return ("%.6f" % n).rstrip("0").rstrip(".")


def _similarity(a: Any, b: Any) -> float:
    return difflib.SequenceMatcher(None, _norm_text(a), _norm_text(b)).ratio()


def _numbers_in_text(s: Any) -> List[str]:
    """提取真正的数值字面量，排除 CF8 / P-xxx / 表13-1 这类标识符里的数字。"""
    t = str(s or "")
    t = re.sub(r"\b(?:CF|CL|CG|P|D|R)[-_]?[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*", " ", t)
    t = re.sub(r"表\s*\d+(?:\s*[-－]\s*\d+)?", " ", t)
    return [m.group(0) for m in re.finditer(r"-?\d[\d,]*(?:\.\d+)?", t)]


def _issue(gate: str, code: str, detail: str, severity: str = "fail") -> Dict[str, Any]:
    return {"gate": gate, "code": code, "detail": detail, "severity": severity}


def _parse_table(lines: List[str]) -> Dict[str, Any]:
    rows = []
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            continue
        rows.append([c.strip() for c in s.strip("|").split("|")])
    if not rows:
        return {}
    header = rows[0]
    data = rows[1:]
    if data and all(re.fullmatch(r":?-{2,}:?", c or "") for c in data[0]):
        data = data[1:]
    return {"cols": header, "col_count": len(header), "rows": len(data), "data_rows": data}


def split_body(body: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """把 Markdown 正文拆成（段落, 表格）。段落按空行/列表项/逐句行拆分。"""
    text = str(body or "").replace("\r\n", "\n")
    lines = text.split("\n")
    text_lines: List[str] = []
    tables: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            t = _parse_table(block)
            if t:
                tables.append(t)
            continue
        text_lines.append(lines[i])
        i += 1

    blocks: List[List[str]] = []
    cur: List[str] = []
    for line in text_lines:
        s = line.strip()
        if not s:
            if cur:
                blocks.append(cur)
                cur = []
            continue
        if s.startswith("#"):
            continue
        cur.append(s)
    if cur:
        blocks.append(cur)

    paras: List[str] = []
    for block in blocks:
        if len(block) > 1 and all(x.startswith(("-", "•", "·")) for x in block):
            paras.extend(block)
        elif len(block) > 1 and all(re.search(r"[。；！？]$", x) for x in block):
            paras.extend(block)
        else:
            paras.append(" ".join(block))
    return paras, tables


def _refs_in_body(body: str) -> List[Dict[str, Any]]:
    out = []
    for m in NODE_REF_RE.finditer(body):
        out.append({
            "node_id": m.group(1),
            "char_span": [m.start(), m.end()],
            "form": m.group(0),
        })
    return out


def _fact_index(graph: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(f.get("id")): f for f in (graph.get("items", {}).get("facts") or []) if f.get("id")}


def _fact_subject(fact: Dict[str, Any]) -> str:
    return str(fact.get("subject") or "")


def _base_subject(s: Any) -> str:
    return re.split(r"[·.]", str(s or ""))[0].strip()


def _conflict_status_for(node_id: str, wp: Dict[str, Any], graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """返回与该 node 相关、且图谱标待审的冲突。"""
    out = []
    fact = {str(f.get("node_id")): f for f in (wp.get("facts") or [])}.get(node_id, {})
    cids = set(fact.get("conflict_ids") or [])
    fbase = _base_subject(fact.get("subject"))
    for c in wp.get("conflicts") or []:
        cbase = _base_subject(c.get("subject"))
        related = (
            c.get("conflict_id") in cids
            or node_id in (c.get("involved") or [])
            or (cbase and cbase == fbase)
        )
        if related and str(c.get("status") or "") == "待审":
            out.append(c)
    # 图谱冲突兜底
    for c in graph.get("items", {}).get("conflicts") or []:
        if node_id in [str(x) for x in (c.get("involved") or [])]:
            if str(c.get("status") or "") == "待审" and c.get("id") not in {x.get("conflict_id") for x in out}:
                out.append({
                    "conflict_id": c.get("id"),
                    "subject": "",
                    "status": c.get("status"),
                    "reason": c.get("description", ""),
                    "involved": c.get("involved") or [],
                })
    return out


def _node_usage(root: Path) -> Dict[str, List[Dict[str, Any]]]:
    """扫描所有 _fill-*.json，得到 node_id → 多节使用记录。"""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for p in sorted((root / "prompt-filled").glob("_fill-*.json")):
        sec = p.stem.replace("_fill-", "")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for slot in d.get("slots") or []:
            nid = slot.get("node_id")
            if not nid:
                continue
            out.setdefault(str(nid), []).append({
                "section": sec,
                "slot": slot.get("name", ""),
                "value": slot.get("value"),
                "status": slot.get("status", ""),
            })
    return out


def _gap_covered(gap: Dict[str, Any], unresolved_text: str,
                 mentioned_facts: List[Dict[str, Any]]) -> bool:
    slot = str(gap.get("slot") or "")
    if not slot:
        return True
    if slot in unresolved_text:
        return True
    # 备注类允许按基名归组（如「设计费·备注」覆盖「设计费·备注2」）
    base = re.split(r"[·.]备注", slot)[0]
    if base and base != slot and base in unresolved_text:
        return True
    # 正文已用到同主体节点（说明缺项被客户值替代）
    for f in mentioned_facts:
        if slot == _fact_subject(f) or slot == _base_subject(_fact_subject(f)):
            return True
        if slot in (f.get("slot_names") or []):
            return True
    return False


# ---------------------------------------------------------------------------
# 门 1
# ---------------------------------------------------------------------------

def _gate1(
    section: str,
    body: str,
    paras: List[str],
    tables: List[Dict[str, Any]],
    wp: Dict[str, Any],
    issues: List[Dict[str, Any]],
) -> Dict[str, Any]:
    sk = wp.get("skeleton") or {}
    src_paras = sk.get("source_excerpt") or []
    src_n = len(src_paras) if src_paras else int(sk.get("paras") or 0)
    new_n = len(paras)
    checks: Dict[str, Any] = {}

    para_pass = abs(src_n - new_n) <= PARA_DIFF
    checks["para_count"] = {
        "source": src_n,
        "new": new_n,
        "diff": abs(src_n - new_n),
        "limit": PARA_DIFF,
        "pass": para_pass,
    }
    if not para_pass:
        issues.append(_issue(
            "gate1", "para_count_mismatch",
            "原文 %d 段，新正文 %d 段，差 %d > %d" % (src_n, new_n, abs(src_n - new_n), PARA_DIFF),
        ))

    src_tables = sk.get("tables") or []
    table_count_pass = len(src_tables) == len(tables)
    checks["table_count"] = {
        "source": len(src_tables),
        "new": len(tables),
        "pass": table_count_pass,
    }
    if not table_count_pass:
        issues.append(_issue(
            "gate1", "table_count_mismatch",
            "原文 %d 张表，新正文 %d 张表" % (len(src_tables), len(tables)),
        ))

    shape_results = []
    for i, st in enumerate(src_tables):
        if i >= len(tables):
            shape_results.append({"index": i, "pass": False, "reason": "缺表"})
            continue
        nt = tables[i]
        src_cols = st.get("cols") or []
        new_cols = nt.get("cols") or []
        norm_new = {_norm_text(c) for c in new_cols}
        missing_cols = [c for c in src_cols if _norm_text(c) not in norm_new]
        src_rows = int(st.get("rows") or st.get("row_count") or 0)
        new_rows = int(nt.get("rows") or 0)
        row_ok = abs(src_rows - new_rows) <= ROW_DIFF
        ok = not missing_cols and row_ok
        shape_results.append({
            "index": i,
            "source_cols": src_cols,
            "new_cols": new_cols,
            "missing_cols": missing_cols,
            "source_rows": src_rows,
            "new_rows": new_rows,
            "row_diff": abs(src_rows - new_rows),
            "pass": ok,
        })
        if missing_cols:
            issues.append(_issue(
                "gate1", "table_column_missing",
                "表 %d 缺列：%s" % (i + 1, "、".join(missing_cols)),
            ))
        if not row_ok:
            issues.append(_issue(
                "gate1", "table_row_count_mismatch",
                "表 %d 原文 %d 行，新表 %d 行，差 %d > %d" % (
                    i + 1, src_rows, new_rows, abs(src_rows - new_rows), ROW_DIFF
                ),
            ))
    checks["table_shapes"] = shape_results

    # must_cover
    fact_by_id = {str(f.get("node_id")): f for f in (wp.get("facts") or [])}
    body_norm = _norm_text(body)
    mentioned_ids = {x.get("node_id") for x in _refs_in_body(body)}
    missing_cover = []
    for item in wp.get("must_cover") or []:
        if _norm_text(item) in body_norm:
            continue
        covered = False
        for nid in mentioned_ids:
            f = fact_by_id.get(str(nid))
            if not f:
                continue
            if item == _fact_subject(f) or item == _base_subject(_fact_subject(f)) or item in (f.get("slot_names") or []):
                covered = True
                break
        if not covered:
            missing_cover.append(item)
    checks["must_cover"] = {
        "items": wp.get("must_cover") or [],
        "missing": missing_cover,
        "pass": not missing_cover,
    }
    if missing_cover:
        issues.append(_issue(
            "gate1", "must_cover_missing",
            "must_cover 缺 %d 项：%s" % (len(missing_cover), "、".join(missing_cover)),
        ))

    # 语义对位
    pairs = []
    scores = []
    for i, sp in enumerate(src_paras):
        best_j, best = -1, 0.0
        for j, np_ in enumerate(paras):
            r = _similarity(sp, np_)
            if r > best:
                best, best_j = r, j
        scores.append(best)
        pairs.append({
            "source_index": i,
            "best_new_index": best_j,
            "score": round(best, 4),
            "source": sp[:80],
        })
    avg = sum(scores) / len(scores) if scores else 1.0
    sem_pass = avg >= SIM_THRESHOLD
    checks["semantic_alignment"] = {
        "avg": round(avg, 4),
        "threshold": SIM_THRESHOLD,
        "pairs": pairs,
        "pass": sem_pass,
    }
    if not sem_pass and src_paras:
        issues.append(_issue(
            "gate1", "semantic_alignment_low",
            "语义对位 avg=%.3f < %.1f" % (avg, SIM_THRESHOLD),
        ))

    # 数据覆盖：正文必须实际引用本节节点
    expected = [
        f for f in (wp.get("facts") or [])
        if str(f.get("status") or "") != "undefined"
    ]
    expected_ids = {str(f.get("node_id")) for f in expected}
    hit = expected_ids & {str(x) for x in mentioned_ids}
    coverage = (len(hit) / len(expected_ids)) if expected_ids else 1.0
    data_pass = (coverage >= COVERAGE_MIN) and (bool(mentioned_ids) or not expected_ids)
    checks["data_coverage"] = {
        "expected_nodes": len(expected_ids),
        "mentioned_nodes": len(hit),
        "ratio": round(coverage, 4),
        "pass": data_pass,
    }
    if not data_pass:
        issues.append(_issue(
            "gate1", "data_coverage_low",
            "本节应有 %d 个节点，正文只引用 %d 个（ratio=%.2f），且 node_mentions=%d" % (
                len(expected_ids), len(hit), coverage, len(mentioned_ids)
            ),
        ))

    # 引用即绑定：所有 body 中的 {{node:...}} 必须在 node_mentions 中声明
    declared = {str(x.get("node_id")) for x in (wp.get("_writing_node_mentions") or [])}
    # 注：node_mentions 由调用方放入 wp["_writing_node_mentions"]，见 compare()
    ref_ids = {x.get("node_id") for x in _refs_in_body(body)}
    undeclared = sorted(ref_ids - declared) if ref_ids else []
    mention_pass = not undeclared
    checks["mentions"] = {
        "body_refs": len(ref_ids),
        "declared": len(declared),
        "undeclared": undeclared,
        "pass": mention_pass,
    }
    if undeclared:
        issues.append(_issue(
            "gate1", "undeclared_node_refs",
            "正文引用但 node_mentions 未声明：%s" % "、".join(undeclared),
        ))

    # 数值字面量：正文段落里不得写字面数字（表题除外）
    literal_tokens = []
    for p in paras:
        if re.match(r"^表\s*\d", p.strip()):
            continue
        cleaned = NODE_REF_RE.sub("", p)
        cleaned = re.sub(r"\{\{[^{}]*\}\}", "", cleaned)
        literal_tokens.extend(_numbers_in_text(cleaned))
    # 表格数值单元格：除序号列与备注列外，纯数字单元格必须写成 node 引用
    for t in tables:
        cols = t.get("cols") or []
        remark_idx = next((i for i, c in enumerate(cols) if "备注" in str(c)), None)
        for row in t.get("data_rows") or []:
            for j, cell in enumerate(row):
                if j == 0 or j == remark_idx:
                    continue
                c = str(cell or "").strip()
                if re.fullmatch(r"-?\d[\d,]*(?:\.\d+)?", c):
                    literal_tokens.append(c)
    literal_pass = not literal_tokens
    checks["literal_numbers"] = {
        "tokens": literal_tokens[:20],
        "count": len(literal_tokens),
        "pass": literal_pass,
    }
    if literal_tokens:
        issues.append(_issue(
            "gate1", "literal_numbers",
            "正文/表格出现未绑定 node 的字面数字：%s" % "、".join(literal_tokens[:10]),
        ))

    # 缺失项必须进 unresolved
    unresolved_text = "\n".join(
        "%s %s %s" % (u.get("what", ""), u.get("why", ""), u.get("need_from_client", ""))
        for u in (wp.get("_writing_unresolved") or [])
    )
    mentioned_facts = [fact_by_id[str(i)] for i in mentioned_ids if str(i) in fact_by_id]
    uncovered = []
    for gap in wp.get("gaps") or []:
        material = bool(gap.get("material")) or gap.get("kind") == "undefined"
        if not material:
            continue
        if not _gap_covered(gap, unresolved_text, mentioned_facts):
            uncovered.append(gap.get("slot"))
    unresolved_pass = not uncovered
    checks["unresolved_coverage"] = {
        "material_gaps": sum(
            1 for g in (wp.get("gaps") or [])
            if g.get("material") or g.get("kind") == "undefined"
        ),
        "uncovered": uncovered,
        "pass": unresolved_pass,
    }
    if uncovered:
        issues.append(_issue(
            "gate1", "unresolved_gap_missing",
            "缺失项未进 unresolved：%s" % "、".join(str(x) for x in uncovered),
        ))

    # 表格不能全是占位词
    table_data_ok = True
    if src_tables and tables:
        all_cells = []
        for t in tables:
            for row in t.get("data_rows") or []:
                # 序号列不算数据；否则 1..9 的序号会把「全行待客户提供」误判为有数据
                all_cells.extend([str(c or "").strip() for c in row[1:]])
        if all_cells:
            has_ref = any(NODE_REF_RE.search(c) for c in all_cells)
            has_number = any(_num(c) is not None for c in all_cells)
            non_placeholder = [
                c for c in all_cells
                if c and not any(w in c for w in PLACEHOLDER_WORDS)
            ]
            table_data_ok = has_ref or has_number or bool(non_placeholder)
        if not table_data_ok:
            issues.append(_issue(
                "gate1", "table_has_no_data",
                "表格所有数据单元格都是占位词（待客户提供/—），没有任何节点引用或数值",
            ))
    checks["table_data_presence"] = {"pass": table_data_ok}

    gate_pass = all(
        bool(checks[k].get("pass"))
        for k in ("para_count", "table_count", "must_cover", "semantic_alignment",
                  "data_coverage", "mentions", "literal_numbers", "unresolved_coverage",
                  "table_data_presence")
    ) and all(x.get("pass") for x in shape_results)
    return {"pass": gate_pass, "checks": checks}


# ---------------------------------------------------------------------------
# 门 2
# ---------------------------------------------------------------------------

def _gate2(
    section: str,
    body: str,
    wp: Dict[str, Any],
    graph: Dict[str, Any],
    root: Path,
    issues: List[Dict[str, Any]],
) -> Dict[str, Any]:
    fidx = _fact_index(graph)
    derived = load_derived_nodes(root)
    wp_facts = {str(f.get("node_id")): f for f in (wp.get("facts") or [])}
    mentions = list(wp.get("_writing_node_mentions") or [])
    body_refs = _refs_in_body(body)
    ids = list(dict.fromkeys(
        [str(x.get("node_id")) for x in mentions] + [x["node_id"] for x in body_refs]
    ))

    checks: Dict[str, Any] = {}
    unknown = [i for i in ids if i not in fidx and i not in derived]
    existence_pass = not unknown
    checks["node_existence"] = {"unknown": unknown, "pass": existence_pass}
    if unknown:
        issues.append(_issue("gate2", "unknown_node", "未知 node_id：%s" % "、".join(unknown)))

    # 同一 subject 不同值
    subject_index: Dict[str, List[Dict[str, Any]]] = {}
    for f in fidx.values():
        if f.get("status") == "undefined" or f.get("value") is None:
            continue
        subject_index.setdefault(_fact_subject(f), []).append(f)

    inconsistent = []
    under_review = []
    for nid in ids:
        f = fidx.get(nid)
        if not f:
            continue
        alts = [
            x for x in subject_index.get(_fact_subject(f), [])
            if str(x.get("id")) != nid and _value_key(x.get("value")) != _value_key(f.get("value"))
        ]
        if not alts:
            continue
        cs = _conflict_status_for(nid, wp, graph)
        if cs:
            under_review.append({
                "node_id": nid,
                "subject": _fact_subject(f),
                "value": f.get("value"),
                "conflicts": [c.get("conflict_id") for c in cs],
                "alternatives": [{"node_id": x.get("id"), "value": x.get("value")} for x in alts],
            })
        else:
            inconsistent.append({
                "node_id": nid,
                "subject": _fact_subject(f),
                "value": f.get("value"),
                "alternatives": [{"node_id": x.get("id"), "value": x.get("value")} for x in alts],
            })
    checks["same_subject_consistency"] = {
        "inconsistent": inconsistent,
        "under_review": under_review,
        "pass": not inconsistent,
    }
    for x in inconsistent:
        issues.append(_issue(
            "gate2", "unmarked_inconsistency",
            "节点 %s（%s=%s）与同主体节点值不一致且未标待审：%s" % (
                x["node_id"], x["subject"], x["value"],
                "、".join("%s=%s" % (a["node_id"], a["value"]) for a in x["alternatives"]),
            ),
        ))

    # 同一 node_id 跨节填槽值
    usage = _node_usage(root)
    cross_bad = []
    for nid in ids:
        recs = usage.get(nid) or []
        vals = {_value_key(r.get("value")) for r in recs if r.get("value") is not None}
        if len(vals) > 1:
            cs = _conflict_status_for(nid, wp, graph)
            item = {
                "node_id": nid,
                "values": {r.get("section"): r.get("value") for r in recs},
                "conflicts": [c.get("conflict_id") for c in cs],
            }
            if cs:
                under_review.append(item)
            else:
                cross_bad.append(item)
    checks["cross_section_consistency"] = {
        "inconsistent": cross_bad,
        "pass": not cross_bad,
    }
    for x in cross_bad:
        issues.append(_issue(
            "gate2", "cross_section_inconsistency",
            "节点 %s 在多节填槽值不同：%s" % (x["node_id"], json.dumps(x["values"], ensure_ascii=False)),
        ))

    # claims 支撑
    claim_bad = []
    for c in wp.get("_writing_new_claims") or []:
        supports = [str(x) for x in (c.get("supports") or [])]
        missing = [x for x in supports if x not in fidx and x not in derived]
        support_vals = set()
        for sid in supports:
            f = fidx.get(sid)
            if f:
                support_vals.add(_value_key(f.get("value")))
            d = derived.get(sid)
            if d:
                support_vals.add(_value_key(d.get("value")))
        nums = _numbers_in_text(c.get("text"))
        unbacked = [n for n in nums if _value_key(n) not in support_vals]
        if missing or unbacked:
            claim_bad.append({
                "text": str(c.get("text") or "")[:80],
                "missing_supports": missing,
                "unbacked_numbers": unbacked,
            })
    checks["claim_support"] = {"bad": claim_bad, "pass": not claim_bad}
    for x in claim_bad:
        issues.append(_issue(
            "gate2", "unbacked_claim",
            "claim 支撑不足：%s（missing=%s, unbacked=%s）" % (
                x["text"], x["missing_supports"], x["unbacked_numbers"]
            ),
        ))

    # 冲突披露
    unresolved_text = "\n".join(
        "%s %s %s" % (u.get("what", ""), u.get("why", ""), u.get("need_from_client", ""))
        for u in (wp.get("_writing_unresolved") or [])
    )
    claim_text = "\n".join(str(c.get("text") or "") for c in (wp.get("_writing_new_claims") or []))
    disclosure_text = body + "\n" + claim_text + "\n" + unresolved_text
    undisclosed = []
    for c in wp.get("conflicts") or []:
        cid = str(c.get("conflict_id") or "")
        involved = [str(x) for x in (c.get("involved") or [])]
        if not (set(involved) & set(ids)):
            continue
        if cid and cid in disclosure_text:
            continue
        if "待审" in disclosure_text:
            continue
        alt_vals = [a.get("value") for a in (c.get("alternatives") or []) if a.get("value") is not None]
        if any(_value_key(v) in disclosure_text for v in alt_vals):
            continue
        undisclosed.append(cid or c.get("subject"))
    checks["conflict_disclosure"] = {"undisclosed": undisclosed, "pass": not undisclosed}
    for cid in undisclosed:
        issues.append(_issue(
            "gate2", "conflict_not_disclosed",
            "本节使用了冲突相关节点，但正文/new_claims/unresolved 未披露 %s 或「待审」" % cid,
        ))

    gate_pass = all(
        bool(checks[k].get("pass"))
        for k in ("node_existence", "same_subject_consistency", "cross_section_consistency",
                  "claim_support", "conflict_disclosure")
    )
    return {"pass": gate_pass, "checks": checks}


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------

def compare(
    section: str,
    writing_output: Any,
    source_text: Any = None,
    work_package: Any = None,
    graph: Any = None,
    root: Any = None,
) -> Dict[str, Any]:
    """比对：新报告 vs 上财报告该节。

    参数
    ----
    writing_output : dict 或路径，含 body/node_mentions/new_claims/unresolved
    source_text    : 可传 wp.skeleton / 原文路径 / 原文文本；为空时用工作包骨架
    work_package   : dict 或路径（必须）
    """
    root = project_root(root)
    section = norm_section(section)
    wp = _load(work_package)
    w = _load(writing_output)
    g = load_graph(graph, root)

    body = str(w.get("body") or "")
    paras, tables = split_body(body)

    # 把写作输出挂到 wp 的私有键，供两个门使用（不污染工作包文件）
    wp = dict(wp)
    wp["_writing_node_mentions"] = w.get("node_mentions") or []
    wp["_writing_new_claims"] = w.get("new_claims") or []
    wp["_writing_unresolved"] = w.get("unresolved") or []

    issues: List[Dict[str, Any]] = []
    gate1 = _gate1(section, body, paras, tables, wp, issues)
    gate2 = _gate2(section, body, wp, g, root, issues)

    return {
        "section": section,
        "title": wp.get("title", ""),
        "gate1": gate1,
        "gate2": gate2,
        "pass": bool(gate1.get("pass") and gate2.get("pass")),
        "issues": issues,
        "stats": {
            "body_chars": len(re.sub(r"\s", "", body)),
            "paras": len(paras),
            "tables": len(tables),
            "node_refs": len(_refs_in_body(body)),
            "node_mentions": len(w.get("node_mentions") or []),
            "new_claims": len(w.get("new_claims") or []),
            "unresolved": len(w.get("unresolved") or []),
        },
        "compared_at": datetime.now().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# 自检反例
# ---------------------------------------------------------------------------

def _correct_writing_1_1(wp: Dict[str, Any]) -> Dict[str, Any]:
    """构造一个「正确还原」的写作输出（仅用于比对器自检，不是产品正文）。"""
    facts = wp.get("facts") or []
    by_subject: Dict[str, List[Dict[str, Any]]] = {}
    for f in facts:
        by_subject.setdefault(str(f.get("subject") or ""), []).append(f)

    gaps = wp.get("gaps") or []
    gap_slots = {str(g.get("slot")) for g in gaps}
    paras = []
    for src in (wp.get("skeleton") or {}).get("source_excerpt") or []:
        def repl(m):
            slot = m.group(1).strip()
            cands = by_subject.get(slot) or []
            # 选客户值（非冲突另一侧）
            cands = [c for c in cands if c.get("role_in_section") != "conflict_alternative"] or cands
            if cands:
                return "{{node:%s}}" % cands[0].get("node_id")
            return "（待客户提供）"
        paras.append(re.sub(r"\{\{([^{}]+)\}\}", repl, src))

    body = "\n\n".join(paras)
    mentions = []
    cursor = 0
    for m in NODE_REF_RE.finditer(body):
        mentions.append({
            "node_id": m.group(1),
            "char_span": [m.start(), m.end()],
            "form": m.group(0),
        })
    claims = [{
        "text": "建安工程费用采用客户提供口径；规则口径 10180 见冲突 CF8，待审。",
        "supports": ["P-d3694a2d25c1", "P-ee4a81c9edb7"],
        "evidence": ["E1"],
    }]
    unresolved = [
        {
            "what": g.get("slot"),
            "why": g.get("instruction") or "缺值",
            "need_from_client": g.get("slot") if g.get("need_from_client") else "",
        }
        for g in gaps
    ]
    return {
        "section": "1.1",
        "body": body,
        "node_mentions": mentions,
        "new_claims": claims,
        "unresolved": unresolved,
    }


def _placeholder_5_5(wp: Dict[str, Any]) -> Dict[str, Any]:
    """反例 2：§5.5 全行「待客户提供」。"""
    src_paras = (wp.get("skeleton") or {}).get("source_excerpt") or []
    paras = []
    for i, p in enumerate(src_paras):
        if re.match(r"^表\s*\d", p):
            paras.append(p)
        elif p.startswith("注："):
            paras.append(p)
        else:
            paras.append("公共服务配套用房规模需求待客户提供。")
    table = "| 序号 | 用房功能 | 数量（间） | 用房标准（㎡/间） | 面积需求（㎡） |\n|---|---|---|---|---|\n"
    rows = (wp.get("skeleton") or {}).get("tables") or []
    n = int(rows[0].get("rows") or 9) if rows else 9
    table += "\n".join("| %d | 待客户提供 | 待客户提供 | 待客户提供 | 待客户提供 |" % (i + 1) for i in range(n))
    body = "\n\n".join(paras) + "\n\n" + table
    return {
        "section": "5.5",
        "body": body,
        "node_mentions": [],
        "new_claims": [],
        "unresolved": [],
    }


def self_test(root: Any = None) -> Dict[str, Any]:
    root = project_root(root)
    wp11 = build_work_package("1.1", root=root)
    wp55 = build_work_package("5.5", root=root)

    ce1_body = (
        "本项目意义重大，建设十分必要。我们要高度重视，认真组织，确保各项工作顺利推进。"
        "通过本项目建设，将有效提升学校的科研能力与综合实力，为学校长远发展奠定坚实基础。"
        "各参建单位要通力合作，严格控制投资、进度和质量，确保项目按期建成并发挥效益。"
        "同时要加强安全管理，落实各项风险防控措施，创造良好的建设环境。"
    )[:120]
    ce1 = {
        "section": "1.1", "body": ce1_body,
        "node_mentions": [], "new_claims": [], "unresolved": [],
    }
    r1 = compare("1.1", ce1, None, wp11, root=root)

    ce2 = _placeholder_5_5(wp55)
    r2 = compare("5.5", ce2, None, wp55, root=root)

    ce3 = _correct_writing_1_1(wp11)
    r3 = compare("1.1", ce3, None, wp11, root=root)

    cases = [
        {"name": "反例1：120 字无关正文", "expect": "fail", "actual": "pass" if r1["pass"] else "fail", "result": r1},
        {"name": "反例2：§5.5 全行待客户提供", "expect": "fail", "actual": "pass" if r2["pass"] else "fail", "result": r2},
        {"name": "反例3：正确还原", "expect": "pass", "actual": "pass" if r3["pass"] else "fail", "result": r3},
    ]
    ok = all(c["expect"] == c["actual"] for c in cases)
    return {
        "pass": ok,
        "cases": [
            {
                "name": c["name"],
                "expect": c["expect"],
                "actual": c["actual"],
                "ok": c["expect"] == c["actual"],
                "gate1": c["result"]["gate1"]["pass"],
                "gate2": c["result"]["gate2"]["pass"],
                "issues": [i["code"] for i in c["result"]["issues"]],
            }
            for c in cases
        ],
        "details": {c["name"]: c["result"] for c in cases},
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="知识处理专家侧比对器（两硬门）")
    ap.add_argument("--section")
    ap.add_argument("--writing")
    ap.add_argument("--package")
    ap.add_argument("--root", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    root = project_root(args.root)
    if args.self_test:
        res = self_test(root)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["pass"] else 1

    if not (args.section and args.writing and args.package):
        ap.error("需要 --section/--writing/--package，或使用 --self-test")
    res = compare(args.section, args.writing, None, args.package, root=root)
    out = Path(args.out) if args.out else None
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.verbose:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({
            "section": res["section"],
            "pass": res["pass"],
            "gate1": res["gate1"]["pass"],
            "gate2": res["gate2"]["pass"],
            "issue_codes": [i["code"] for i in res["issues"]],
            "stats": res["stats"],
        }, ensure_ascii=False, indent=2))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
