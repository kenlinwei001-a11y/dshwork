# -*- coding: utf-8 -*-
"""evo_corpus_api —— 推演写作专家需要的三个只读查询接口。

本模块只做「知识处理专家 → 推演写作专家」的交接面，不写正文、不做评分。

三个接口
--------
* ``corpus_get_skeleton(section)`` —— 本节「形」：段落顺序、表格列结构、去值骨架。
* ``graph_query(section, kind)``      —— 本节「值」：节点（node_id/subject/value/status/origin/formula/inputs）。
* ``evidence_get(node_id)``           —— 节点证据：来源文件、章节/chunk、引文、hash、char_span。

数据根目录（项目工作区）默认取 ``DSH_PROJECT_ROOT``，否则取当前目录。
代码包本身位于 knowledge-processing-expert/corpus_pipeline。

设计纪律
--------
1. 借形不借值：``source_excerpt`` 一律来自 ``prompt-templates/<section>.md`` 的 ⓿b
   （已去值），没有模板时才从 ``normalized.md`` 兜底并把数字替换为 ``{{数值}}``。
2. 缺值守卫：``status=undefined`` / ``value=None`` 原样保留，绝不填 0。
3. 冲突不裁决：冲突双方都放进 facts/conflicts，``status`` 原样保留。
4. 引用即绑定：写作侧用 ``{{node:P-xxxx}}`` 引用节点；本模块不生成正文。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PACK_DIRNAME = "形-可复用知识资产-v1.0"
GRAPH_NAME = "GRAPH-新项目-华东理工AI研究院-merged.json"
SOURCE_DIRNAME = "SHUFE-BDC-2019-001"
TEMPLATE_DIRNAME = "prompt-templates"
FILL_DIRNAME = "prompt-filled"

QUOTE_PAD = 40
NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
NODE_REF_RE = re.compile(r"\{\{\s*node\s*:\s*([A-Za-z0-9_\-]+)\s*\}\}")
SLOT_RE = re.compile(r"\{\{([^{}]+)\}\}")
JUDGEMENT_WORDS = ("应", "须", "必须", "不得", "按", "标准", "目标", "≥", "≤", "满足", "采用", "符合")


# ---------------------------------------------------------------------------
# 基础 IO
# ---------------------------------------------------------------------------

def project_root(root: Optional[Any] = None) -> Path:
    """解析项目工作区（含形包 / 图谱 / 上财语料的目录）。"""
    if root:
        return Path(root).expanduser().resolve()
    env = os.environ.get("DSH_PROJECT_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd().resolve()
    if (cwd / GRAPH_NAME).exists() or (cwd / PACK_DIRNAME).exists():
        return cwd
    # 代码在 knowledge-processing-expert/corpus_pipeline/ 下；若从代码目录运行，
    # 尝试向上找到同时含形包与图谱的目录。
    for parent in [cwd] + list(cwd.parents):
        if (parent / GRAPH_NAME).exists() and (parent / PACK_DIRNAME).exists():
            return parent
    return cwd


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_yaml(path: Path, default: Any = None) -> Any:
    try:
        import yaml
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def norm_section(section: Any) -> str:
    s = str(section or "").strip()
    s = s.lstrip("§").strip()
    return s


def _between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = text.find(end, i)
    return text[i:j] if j >= 0 else text[i:]


def _search(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.M)
    return m.group(1).strip() if m else default


def _to_num(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
            try:
                return float(s)
            except ValueError:
                return None
    return None


def _is_numeric(value: Any) -> bool:
    return _to_num(value) is not None


def _fmt_value(value: Any) -> str:
    if value is None:
        return ""
    n = _to_num(value)
    if n is None:
        return str(value)
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return ("%g" % n)


# ---------------------------------------------------------------------------
# 形包 / 模板 / 填槽
# ---------------------------------------------------------------------------

def _pack_dir(root: Path) -> Path:
    return root / PACK_DIRNAME


def load_section_guide(root: Optional[Any] = None) -> Dict[str, Any]:
    root = project_root(root)
    data = _read_yaml(_pack_dir(root) / "templates" / "section-writing-guide.yaml", {}) or {}
    return data.get("sections") or {}


def load_section_forms(root: Optional[Any] = None) -> Dict[str, Any]:
    root = project_root(root)
    data = _read_yaml(_pack_dir(root) / "templates" / "section-form.yaml", {}) or {}
    return data.get("forms") or {}


def section_title(section: str, root: Optional[Any] = None) -> str:
    section = norm_section(section)
    guide = load_section_guide(root)
    if section in guide:
        return str(guide[section].get("title") or section)
    tpl = parse_prompt_template(section, root)
    if tpl:
        return tpl["title"]
    return section


def section_form(section: str, root: Optional[Any] = None) -> Dict[str, Any]:
    title = section_title(section, root)
    forms = load_section_forms(root)
    if title in forms:
        return dict(forms[title])
    # 兜底：按节号前缀匹配 raw_sections 不太可靠，直接返回空形。
    return {}


def _parse_md_table(lines: List[str]) -> Dict[str, Any]:
    rows = []
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        rows.append(cells)
    if not rows:
        return {}
    header = rows[0]
    data = rows[1:]
    if data and all(re.fullmatch(r":?-{2,}:?", c or "") for c in data[0]):
        data = data[1:]
    return {
        "cols": header,
        "col_count": len(header),
        "rows": len(data),
        "row_count": len(data),
        "data_rows": data,
    }


def parse_prompt_template(section: str, root: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """解析 ``prompt-templates/<section>.md`` 的 ⓿ / ⓿b 形。

    这是「已修正的原文形」：段落数以 ⓿b 的原文实测为准，不采用形包旧统计。
    """
    root = project_root(root)
    section = norm_section(section)
    path = root / TEMPLATE_DIRNAME / (section + ".md")
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")

    title = _search(r"^#\s*提示词模板\s*·\s*§\S+\s+(.+)$", text, section)
    block0 = _between(text, "### ⓿ 本节原文形态", "### ⓿b")
    blockb = _between(text, "### ⓿b", "**还原纪律")

    style = _search(r"\*\*文体\*\*：([A-Za-z_]+)", block0, "")
    paras_m = re.search(r"\*\*段落\*\*：(\d+)\s*段（([\d,]+)\s*字）", block0)
    form_paras = int(paras_m.group(1)) if paras_m else 0
    form_chars = int(paras_m.group(2).replace(",", "")) if paras_m else 0

    form_tables = []
    for m in re.finditer(
        r"\*\*表\s*(\d+)\*\*：(\d+)\s*列\s*×\s*(\d+)\s*行，嵌套\s*(\d+)\s*层", block0
    ):
        form_tables.append({
            "index": int(m.group(1)),
            "col_count": int(m.group(2)),
            "row_count": int(m.group(3)),
            "nest": int(m.group(4)),
        })
    cols_m = re.search(r"^- 列：(.+)$", block0, re.M)
    form_cols = [c.strip() for c in re.split(r"[｜|]", cols_m.group(1))] if cols_m else []

    # ⓿b 段落：编号行（表格行以 | 开头，不会命中）
    paras: List[str] = []
    for line in blockb.splitlines():
        m = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m and m.group(1).strip():
            paras.append(m.group(1).strip())
    # 只取「原文段落」标题之后、原文表之前的编号行
    para_hdr = re.search(r"\*\*原文段落（(\d+)\s*段\s*/\s*([\d,]+)\s*字）：\*\*", blockb)
    if para_hdr:
        head_end = para_hdr.end()
        table_hdr = re.search(r"\*\*原文表\s*\d+：", blockb[head_end:])
        tail = blockb[head_end:head_end + table_hdr.start()] if table_hdr else blockb[head_end:]
        paras = []
        for line in tail.splitlines():
            m = re.match(r"^\s*\d+\.\s+(.*)$", line)
            if m and m.group(1).strip():
                paras.append(m.group(1).strip())

    tables: List[Dict[str, Any]] = []
    for m in re.finditer(
        r"\*\*原文表\s*(\d+)：(\d+)\s*列\s*×\s*(\d+)\s*行，嵌套\s*(\d+)\s*层\*\*", blockb
    ):
        start = m.end()
        md_lines = []
        for line in blockb[start:].splitlines():
            if line.strip().startswith("|"):
                md_lines.append(line)
            elif md_lines:
                break
        t = _parse_md_table(md_lines)
        if t:
            t.update({
                "index": int(m.group(1)),
                "col_count": int(m.group(2)),
                "row_count": int(m.group(3)),
                "nest": int(m.group(4)),
            })
            tables.append(t)

    must_cover = _derive_must_cover(paras, tables, title)
    para_roles = _derive_para_roles(paras)

    return {
        "section": section,
        "title": title,
        "style": style or ("table_dominant" if tables else "prose_dominant"),
        "paras": paras,
        "para_count": len(paras),
        "para_roles": para_roles,
        "original_chars": int(para_hdr.group(2).replace(",", "")) if para_hdr else form_chars,
        "tables": tables,
        "table_count": len(tables),
        "form_table_cols": form_cols,
        "form_paras": form_paras,
        "form_chars": form_chars,
        "form_tables": form_tables,
        "must_cover": must_cover,
        "source_excerpt": paras,
        "raw_meta": {
            "template_path": str(path),
            "note": "段落/表以 ⓿b 原文实测为准；形包旧统计仅作对照",
        },
    }


def _derive_para_roles(paras: List[str]) -> List[str]:
    roles = []
    for p in paras:
        s = str(p or "").strip()
        if re.match(r"^表\s*\d", s):
            roles.append("表题")
        elif "如下表" in s or "详见下表" in s or "见下表" in s:
            roles.append("引导（引出表格）")
        elif s.startswith(("-", "•", "·")):
            roles.append("清单项")
        else:
            roles.append("说明")
    return roles


def _derive_must_cover(paras: List[str], tables: List[Dict[str, Any]], title: str) -> List[str]:
    labels = []
    for p in paras:
        m = re.match(r"^[-•·]\s*([^：:]{1,24})[：:]", p)
        if m:
            labels.append(m.group(1).strip())
    if len(labels) >= 2:
        return labels

    if tables:
        t = tables[0]
        cols = t.get("cols") or []
        data = t.get("data_rows") or []
        # 优先「工程和费用名称」/「用房功能」列
        name_idx = None
        for key in ("工程和费用名称", "用房功能", "名称", "项目"):
            if key in cols:
                name_idx = cols.index(key)
                break
        if name_idx is None and len(cols) >= 2:
            name_idx = 1
        rows_clean = []
        for row in data:
            if name_idx >= len(row):
                continue
            name = row[name_idx].strip()
            if not name or _is_numeric(name):
                continue
            seq = row[0].strip() if row else ""
            rows_clean.append((seq, name))

        # 有顶层中文序号（一/二/三/四/五）时，只取顶层；
        # 否则取全部功能项（如 5.5 公共服务配套用房）。
        has_top = any(re.fullmatch(r"[一二三四五六七八九十]+", seq) for seq, _ in rows_clean)
        out = [
            name for seq, name in rows_clean
            if (re.fullmatch(r"[一二三四五六七八九十]+", seq) if has_top else True)
        ]
        if out:
            out = list(dict.fromkeys(out))
            # 表题也属于必须覆盖的形
            caption = next((p for p in paras if re.match(r"^表\s*\d", p)), "")
            if caption:
                out.append(caption)
            return out
    return [title]


def _devalue_text(text: str) -> str:
    """兜底去值：数字串 → {{数值}}，保留结构。"""
    return NUM_RE.sub("{{数值}}", str(text or ""))


def _source_md_section(root: Path, title: str) -> Dict[str, Any]:
    """从 normalized.md 按标题取一节（兜底，用于没有模板的节）。"""
    path = root / SOURCE_DIRNAME / "source" / "normalized.md"
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    start = None
    level = 0
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m and m.group(2).strip() == title:
            start = i
            level = len(m.group(1))
            break
    if start is None:
        return {}
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = re.match(r"^(#{1,6})\s+", lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break

    paras: List[str] = []
    tables: List[Dict[str, Any]] = []
    buf: List[str] = []
    in_table = False
    table_lines: List[str] = []

    def flush_para():
        nonlocal buf
        if buf:
            s = " ".join(x.strip() for x in buf if x.strip())
            if s:
                paras.append(s)
            buf = []

    def flush_table():
        nonlocal table_lines
        if table_lines:
            t = _parse_md_table(table_lines)
            if t:
                t["nest"] = _infer_nest(t.get("data_rows") or [])
                tables.append(t)
            table_lines = []

    for line in lines[start + 1:end]:
        s = line.strip()
        if s.startswith("```"):
            if in_table:
                flush_table()
                in_table = False
            else:
                flush_para()
                in_table = True
            continue
        if in_table:
            if s.startswith("|"):
                table_lines.append(s)
            continue
        if not s:
            flush_para()
            continue
        if s.startswith("|"):
            flush_para()
            table_lines.append(s)
            continue
        buf.append(s)
    flush_para()
    flush_table()

    return {
        "title": title,
        "paras": paras,
        "tables": tables,
        "style": "table_dominant" if tables else "prose_dominant",
        "source_excerpt": [_devalue_text(p) for p in paras],
    }


def _infer_nest(rows: List[List[str]]) -> int:
    """按序号列推断嵌套层数。"""
    max_depth = 0
    for row in rows:
        seq = row[0].strip() if row else ""
        if re.fullmatch(r"\d+(?:\.\d+)*", seq):
            max_depth = max(max_depth, seq.count(".") + 1)
        elif re.fullmatch(r"[一二三四五六七八九十]+", seq):
            max_depth = max(max_depth, 1)
        elif seq.startswith("（"):
            max_depth = max(max_depth, 2)
    return max_depth


def corpus_get_skeleton(section: str, pkg: Optional[Any] = None, root: Optional[Any] = None) -> Dict[str, Any]:
    """返回本节骨架：段落顺序、表格列结构、去值原文。

    ``pkg`` 可传入形包目录（兼容旧调用）；不传则用 ``<root>/形-可复用知识资产-v1.0``。
    """
    root = project_root(root)
    section = norm_section(section)
    tpl = parse_prompt_template(section, root)
    form = section_form(section, root)
    title = (tpl or {}).get("title") or section_title(section, root)

    if tpl:
        paras = tpl["paras"]
        para_roles = tpl["para_roles"]
        tables = tpl["tables"]
        style = tpl["style"]
        source_excerpt = tpl["source_excerpt"]
        original_chars = tpl["original_chars"]
        must_cover = tpl["must_cover"]
        raw_meta = tpl["raw_meta"]
        form_note = {
            "form_paras": tpl.get("form_paras"),
            "form_chars": tpl.get("form_chars"),
            "corrected": tpl.get("form_paras") != len(paras) or tpl.get("form_chars") != original_chars,
        }
    else:
        fb = _source_md_section(root, title)
        paras = fb.get("paras") or []
        tables = fb.get("tables") or []
        style = fb.get("style") or form.get("style") or "prose_dominant"
        source_excerpt = fb.get("source_excerpt") or []
        original_chars = len(re.sub(r"\s", "", "".join(paras)))
        para_roles = _derive_para_roles(paras)
        must_cover = _derive_must_cover(paras, tables, title)
        raw_meta = {"source": "normalized.md", "note": "无提示词模板，按原文兜底去值"}
        form_note = {"fallback": True}

    target = form.get("target_chars") or [0, 0]
    if not isinstance(target, (list, tuple)) or len(target) != 2:
        target = [0, 0]
    word_budget = {"min": int(target[0] or 0), "max": int(target[1] or 0)}

    skeleton = {
        "section": section,
        "title": title,
        "paras": len(paras),
        "para_roles": para_roles,
        "tables": [
            {
                "cols": t.get("cols") or [],
                "col_count": t.get("col_count") or len(t.get("cols") or []),
                "rows": t.get("rows", t.get("row_count", 0)),
                "nest": t.get("nest", _infer_nest(t.get("data_rows") or [])),
                "template_rows": t.get("data_rows") or [],
            }
            for t in tables
        ],
        "style": style,
        "source_excerpt": source_excerpt,
        "original_chars": original_chars,
        "word_budget": word_budget,
        "must_cover": must_cover,
        "skeleton_pointer": "%s/templates/section-form.yaml#%s" % (PACK_DIRNAME, title),
        "form_key": title,
        "form_guidance": form.get("guidance", ""),
        "form_note": form_note,
        "raw_meta": raw_meta,
    }
    # 兼容：模板 ⓿b 的表可能没有 data_rows（解析失败）
    if not skeleton["tables"] and form.get("tables"):
        skeleton["tables"] = [
            {
                "cols": t.get("cols") or [],
                "col_count": len(t.get("cols") or []),
                "rows": t.get("rows", 0),
                "nest": t.get("nest", 0),
                "template_rows": t.get("sample_rows") or [],
                "from_form": True,
            }
            for t in form["tables"]
        ]
    return skeleton


# ---------------------------------------------------------------------------
# 图谱 / 填槽 / 派生节点
# ---------------------------------------------------------------------------

def load_graph(graph: Optional[Any] = None, root: Optional[Any] = None) -> Dict[str, Any]:
    if isinstance(graph, dict):
        return graph
    root = project_root(root)
    path = Path(graph) if graph else (root / GRAPH_NAME)
    data = _read_json(path, {})
    if not data:
        raise FileNotFoundError("找不到图谱：%s" % path)
    return data


def load_fill(section: str, root: Optional[Any] = None) -> Dict[str, Any]:
    root = project_root(root)
    section = norm_section(section)
    path = root / FILL_DIRNAME / ("_fill-%s.json" % section)
    return _read_json(path, {}) or {}


def load_derived_nodes(root: Optional[Any] = None) -> Dict[str, Any]:
    root = project_root(root)
    return _read_json(root / FILL_DIRNAME / "derived-nodes.json", {}) or {}


def load_origin_merged(root: Optional[Any] = None) -> Dict[str, Any]:
    root = project_root(root)
    return _read_json(root / FILL_DIRNAME / "_origin-merged.json", {}) or {}


def load_rules(root: Optional[Any] = None) -> Dict[str, Any]:
    root = project_root(root)
    data = _read_yaml(_pack_dir(root) / "functions" / "derivation_templates.yaml", {}) or {}
    return data.get("rules") or {}


def _rule_by_target(root: Optional[Any] = None) -> Dict[str, Dict[str, Any]]:
    out = {}
    for rid, rule in load_rules(root).items():
        if isinstance(rule, dict) and rule.get("target"):
            out[str(rule["target"])] = dict(rule, id=rid)
    return out


def _fact_index(graph: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(f.get("id")): f for f in (graph.get("items", {}).get("facts") or []) if f.get("id")}


def _fact_brief(f: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "node_id": f.get("id"),
        "subject": f.get("subject", ""),
        "value": f.get("value"),
        "unit": f.get("unit", ""),
        "status": f.get("status", ""),
        "origin": _origin_of_fact(f),
        "formula": f.get("formula", "") or "",
        "inputs": f.get("inputs", []) or [],
        "source_type": f.get("source_type", ""),
        "section": f.get("section", ""),
        "skeleton_section": f.get("skeleton_section", []) or [],
        "fact_kind": f.get("fact_kind", ""),
        "rule": f.get("rule", ""),
    }


def _origin_of_fact(f: Dict[str, Any]) -> str:
    if f.get("rule") or f.get("status") == "computed" or f.get("node_role") in (
        "DERIVED_LEAF", "INTERMEDIATE"
    ):
        return "derived"
    if f.get("status") == "undefined":
        return "undetermined"
    return "input"


def _section_match(fact_section: Any, section: str) -> bool:
    s = str(fact_section or "")
    return ("§" + section) in s or section in s


def _fill_records(section: str, root: Optional[Any], graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把本节 _fill-*.json 的槽位展开为节点记录（按 node_id 去重）。"""
    fill = load_fill(section, root)
    derived = load_derived_nodes(root)
    fidx = _fact_index(graph)
    rules_by_target = _rule_by_target(root)
    reasoning = graph.get("items", {}).get("reasoning") or []
    reason_by_output: Dict[str, Dict[str, Any]] = {}
    for r in reasoning:
        if r.get("output"):
            reason_by_output[str(r["output"])] = r

    slots = fill.get("slots") or []
    by_id: Dict[str, Dict[str, Any]] = {}
    for slot in slots:
        nid = slot.get("node_id")
        if not nid:
            continue
        nid = str(nid)
        g = fidx.get(nid, {})
        d = derived.get(nid, {})
        if nid in by_id:
            by_id[nid]["slot_names"].append(slot.get("name", ""))
            by_id[nid]["occurrences"] += 1
            # 同一节点同一值：保留；不同值：记录 variants，供比对器判冲突
            old = by_id[nid].get("value")
            new = slot.get("value")
            if _fmt_value(old) != _fmt_value(new):
                by_id[nid].setdefault("value_variants", []).append({
                    "slot": slot.get("name", ""),
                    "value": new,
                })
            continue

        value = slot.get("value")
        if value is None and g:
            value = g.get("value")
        status = g.get("status") or ("computed" if slot.get("status") == "computed" else "provided")
        if value is None and status != "undefined":
            status = "undefined"

        origin = slot.get("origin") or ("derived" if (d or g.get("rule")) else "input")
        formula = (
            slot.get("formula")
            or d.get("formula")
            or (rules_by_target.get(g.get("subject", ""), {}) or {}).get("expr", "")
        )
        inputs = slot.get("inputs") or d.get("inputs") or []
        if not inputs and nid in reason_by_output:
            inputs = reason_by_output[nid].get("inputs") or []

        rec = {
            "node_id": nid,
            "subject": slot.get("name") or g.get("subject") or d.get("slot") or "",
            "value": value,
            "unit": slot.get("unit") or g.get("unit", "") or d.get("unit", ""),
            "status": status,
            "origin": origin,
            "formula": formula,
            "inputs": inputs,
            "source_type": g.get("source_type") or slot.get("source") or "",
            "node_role": g.get("node_role", ""),
            "section": g.get("section", ""),
            "skeleton_section": g.get("skeleton_section", []) or [],
            "fact_kind": g.get("fact_kind", ""),
            "rule": g.get("rule", ""),
            "slot_names": [slot.get("name", "")],
            "occurrences": 1,
            "role_in_section": "slot",
            "conflict_ids": [],
        }
        if d:
            rec["derived_node"] = True
            rec["section"] = d.get("section", rec["section"])
        by_id[nid] = rec

    # 图谱里以 skeleton_section 明确挂到本节的节点（如 1.1 的 EC0）
    for f in graph.get("items", {}).get("facts") or []:
        nid = str(f.get("id"))
        if nid in by_id:
            continue
        sk = [str(x) for x in (f.get("skeleton_section") or [])]
        if section in sk:
            rec = _fact_brief(f)
            rec.update({
                "slot_names": [rec.get("subject", "")],
                "occurrences": 1,
                "role_in_section": "graph_section_tag",
                "conflict_ids": [],
            })
            by_id[nid] = rec

    # 本节派生节点（D-*），即使没有被某个槽位直接引用
    for nid, d in derived.items():
        if str(d.get("section")) != section or nid in by_id:
            continue
        rec = {
            "node_id": nid,
            "subject": d.get("slot", ""),
            "value": d.get("value"),
            "unit": d.get("unit", ""),
            "status": "computed",
            "origin": "derived",
            "formula": d.get("formula", ""),
            "inputs": d.get("inputs", []),
            "source_type": "COMPUTED",
            "node_role": "DERIVED_LEAF",
            "section": section,
            "skeleton_section": [],
            "fact_kind": "",
            "rule": "",
            "slot_names": [d.get("slot", "")],
            "occurrences": 1,
            "role_in_section": "derived",
            "conflict_ids": [],
            "derived_node": True,
        }
        by_id[nid] = rec

    return list(by_id.values())


def _conflict_subject(c: Dict[str, Any], fidx: Dict[str, Dict[str, Any]]) -> str:
    desc = str(c.get("description") or "")
    if "：" in desc:
        return desc.split("：", 1)[0].strip()
    if ":" in desc:
        return desc.split(":", 1)[0].strip()
    for nid in c.get("involved") or []:
        f = fidx.get(str(nid))
        if f:
            return str(f.get("subject") or "")
    return ""


def _subject_related(subject: str, subjects: Iterable[str]) -> bool:
    """严格主体匹配：全名相同，或去掉「·数量/·单价/·合价」后缀后相同。

    不做子串匹配 —— 「总建筑面积」不能因为出现在「地上总建筑面积需求」里
    就被判为同一主体，否则 1.1 会误挂 13.3 的冲突。
    """
    subject = str(subject or "").strip()
    if not subject:
        return False
    subj_base = re.split(r"[·.]", subject)[0].strip()
    for s in subjects:
        s = str(s or "").strip()
        if not s:
            continue
        if subject == s:
            return True
        base = re.split(r"[·.]", s)[0].strip()
        if subj_base and base and subj_base == base:
            return True
    return False


def _kind_of_fact(f: Dict[str, Any]) -> str:
    v = f.get("value")
    if f.get("status") == "undefined" or v is None:
        return "undefined"
    if _is_numeric(v):
        return "quantity"
    if f.get("unit"):
        return "quantity"
    s = str(v)
    if any(w in s for w in JUDGEMENT_WORDS):
        return "judgment"
    return "text"


def graph_query(
    section: str,
    kind: str = "all",
    graph: Optional[Any] = None,
    root: Optional[Any] = None,
) -> Dict[str, Any]:
    """返回本节节点。

    kind: ``all | quantity | judgment | text | undefined``
    * ``quantity``  数值节点（含单位）
    * ``judgment``  定性判断节点（含「应/须/按/标准/目标/≥/≤/满足」等）
    * ``text``      定性/文本节点（含 judgment）
    * ``undefined`` 缺值节点（value=None，永不按 0 计算）
    """
    root = project_root(root)
    section = norm_section(section)
    g = load_graph(graph, root)
    nodes = _fill_records(section, root, g)
    for n in nodes:
        n["kind"] = _kind_of_fact(n)

    counts = {"all": len(nodes)}
    for n in nodes:
        counts[n["kind"]] = counts.get(n["kind"], 0) + 1

    k = (kind or "all").strip()
    if k == "all":
        out = nodes
    elif k == "text":
        out = [n for n in nodes if n["kind"] in ("text", "judgment")]
    elif k in ("quantity", "judgment", "undefined"):
        out = [n for n in nodes if n["kind"] == k]
    else:
        raise ValueError("kind 必须是 all|quantity|judgment|text|undefined，收到：%r" % kind)

    return {
        "section": section,
        "kind": k,
        "count": len(out),
        "counts": counts,
        "nodes": out,
    }


# ---------------------------------------------------------------------------
# 冲突 / 缺口
# ---------------------------------------------------------------------------

def conflicts_for_section(
    section: str,
    facts: List[Dict[str, Any]],
    graph: Optional[Any] = None,
    root: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """只返回与本节点集合相关的冲突；双方都保留，不裁决。"""
    root = project_root(root)
    g = load_graph(graph, root)
    fidx = _fact_index(g)
    origin = load_origin_merged(root)
    origin_conflicts = {}
    for c in ((origin.get("node_level") or {}).get("conflicts") or []):
        if c.get("subject"):
            origin_conflicts[str(c["subject"])] = c

    # 相关性只看本节「原生」节点；冲突另一侧节点稍后再补，避免自证相关。
    primary = [f for f in facts if f.get("role_in_section") != "conflict_alternative"]
    subjects = [str(f.get("subject") or "") for f in primary]
    ids = {str(f.get("node_id")) for f in primary}
    out = []
    for c in g.get("items", {}).get("conflicts") or []:
        involved = [str(x) for x in (c.get("involved") or [])]
        subject = _conflict_subject(c, fidx)
        related = bool(set(involved) & ids) or _subject_related(subject, subjects)
        if not related:
            continue

        alternatives = []
        for nid in involved:
            f = fidx.get(nid)
            if not f:
                continue
            alternatives.append({
                "node_id": nid,
                "subject": f.get("subject", ""),
                "value": f.get("value"),
                "unit": f.get("unit", ""),
                "status": f.get("status", ""),
                "origin": _origin_of_fact(f),
                "rule": f.get("rule", ""),
            })

        values = []
        oc = origin_conflicts.get(subject)
        if oc:
            for v in (oc.get("customer_value"), oc.get("rule_value"), oc.get("deps_sum")):
                if v is not None:
                    values.append(v)
        for a in alternatives:
            if a["value"] is not None:
                values.append(a["value"])
        if not values:
            values = [float(x) for x in NUM_RE.findall(str(c.get("description") or ""))][:2]
        # 去重（保持顺序）
        uniq = []
        for v in values:
            if _fmt_value(v) not in {_fmt_value(x) for x in uniq}:
                uniq.append(v)

        out.append({
            "conflict_id": c.get("id"),
            "type": c.get("type", ""),
            "subject": subject,
            "values": uniq,
            "status": c.get("status", "待审"),
            "reason": c.get("description", ""),
            "severity": c.get("severity", ""),
            "involved": involved,
            "alternatives": alternatives,
            "resolution": "不裁决；保留双方并标待审，由后续人工/推演确认",
            "origin_merged": oc or None,
        })
    return out


def conflict_alternative_facts(
    facts: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
    graph: Optional[Any] = None,
    root: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """把已判定为「本节相关」的冲突另一侧节点补进 facts。"""
    root = project_root(root)
    g = load_graph(graph, root)
    fidx = _fact_index(g)
    have = {str(f.get("node_id")) for f in facts}
    out = list(facts)
    for c in conflicts:
        for nid in c.get("involved") or []:
            nid = str(nid)
            if nid in have or nid not in fidx:
                continue
            rec = _fact_brief(fidx[nid])
            rec.update({
                "slot_names": [rec.get("subject", "")],
                "occurrences": 1,
                "role_in_section": "conflict_alternative",
                "conflict_ids": [c.get("conflict_id")],
                "kind": _kind_of_fact(rec),
            })
            out.append(rec)
            have.add(nid)
    return out


def gaps_for_section(
    section: str,
    facts: List[Dict[str, Any]],
    graph: Optional[Any] = None,
    root: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """从 ``_fill-*.json`` 的 missing_* 与图谱 undefined 节点抽缺口。"""
    root = project_root(root)
    section = norm_section(section)
    fill = load_fill(section, root)
    seen: Dict[str, Dict[str, Any]] = {}
    for slot in fill.get("slots") or []:
        st = str(slot.get("status") or "")
        name = str(slot.get("name") or "")
        placeholder = str(slot.get("value") or "") in ("—", "-", "待定", "待提供", "")
        if st not in ("missing_customer", "missing_standard"):
            # 填槽器标成 filled、但没有 node 且值是占位符 —— 实际仍是缺值，
            # 不能因为 status=filled 就从 gaps 里消失（例如 13.3 的
            # 「新老建筑立面接口处理费·数量」）。
            if not (st == "filled" and not slot.get("node_id") and placeholder):
                continue
            st = "filled_no_node"
        if name in seen:
            seen[name]["occurrences"] += 1
            continue
        if st == "missing_customer":
            material, need_client, instruction = ("备注" not in name), True, "待客户提供「%s」" % name
        elif st == "missing_standard":
            material, need_client, instruction = False, False, "待查标准/规范「%s」" % name
        else:  # filled_no_node
            material, need_client, instruction = True, True, "填槽结果为「—」但无节点，待客户提供「%s」" % name
        seen[name] = {
            "slot": name,
            "kind": st,
            "status": st,
            "source_type": slot.get("source", ""),
            "unit": slot.get("unit", ""),
            "instruction": instruction,
            "need_from_client": need_client,
            "material": material,
            "occurrences": 1,
            "node_id": slot.get("node_id") or "",
        }

    # 图谱里本节 undefined 节点（严格匹配：节号，或与本节槽位同名/同基名）
    g = load_graph(graph, root)
    fact_subjects = {str(f.get("subject") or "") for f in facts}
    fact_bases = {re.split(r"[·.]", s)[0] for s in fact_subjects if s}
    for f in g.get("items", {}).get("facts") or []:
        if f.get("status") != "undefined":
            continue
        subj = str(f.get("subject") or "")
        subj_base = re.split(r"[·.]", subj)[0] if subj else ""
        if not (_section_match(f.get("section"), section)
                or subj in fact_subjects or subj_base in fact_bases):
            continue
        key = "undefined:" + str(f.get("id"))
        seen[key] = {
            "slot": subj,
            "kind": "undefined",
            "status": "undefined",
            "source_type": f.get("source_type", ""),
            "unit": f.get("unit", ""),
            "instruction": f.get("instruction") or ("「%s」缺输入，按规则不可评估" % subj),
            "need_from_client": True,
            "material": True,
            "occurrences": 1,
            "node_id": f.get("id", ""),
            "rule": f.get("rule", ""),
        }
    return list(seen.values())


# ---------------------------------------------------------------------------
# 证据
# ---------------------------------------------------------------------------

def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _make_locator(file: str, section: str, chunk_id: str, text: str, i: int, n: int,
                  base_span: Optional[List[int]] = None) -> Dict[str, Any]:
    a = max(0, i - QUOTE_PAD)
    b = min(len(text), i + n + QUOTE_PAD)
    quote = text[a:b]
    span = [a, b]
    if base_span:
        span = [int(base_span[0]) + a, int(base_span[0]) + b]
    return {
        "file": file,
        "section": section,
        "chunk_id": chunk_id,
        "quote": quote,
        "hash": _hash(quote),
        "char_span": span,
    }


def _search_text(text: str, candidates: List[str], *, file: str, section: str,
                 chunk_id: str, base_span: Optional[List[int]] = None) -> Optional[Dict[str, Any]]:
    for cand in candidates:
        cand = str(cand or "").strip()
        if len(cand) < 2:
            continue
        i = text.find(cand)
        if i >= 0:
            return _make_locator(file, section, chunk_id, text, i, len(cand), base_span)
    return None


def _load_chunks(root: Path) -> List[Dict[str, Any]]:
    path = root / SOURCE_DIRNAME / "chunks" / "chunks.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def evidence_get(
    node_id: str,
    with_excerpt: bool = True,
    graph: Optional[Any] = None,
    root: Optional[Any] = None,
) -> Dict[str, Any]:
    """返回节点证据：来源文件、章节/chunk、引文、hash、char_span。

    证据优先级：
    1. 新项目客户事实输入 ``事实输入-新项目-华东理工AI研究院-v2.md``（新值）
    2. 上财原文 chunks（形与来源）
    派生节点（D-*）没有直接原文，返回 formula + inputs。
    """
    root = project_root(root)
    node_id = str(node_id).strip()
    g = load_graph(graph, root)
    fidx = _fact_index(g)
    fact = fidx.get(node_id)
    derived = load_derived_nodes(root).get(node_id)

    if not fact and not derived:
        return {
            "node_id": node_id,
            "status": "not_found",
            "locator": None,
            "locators": [],
            "locator_status": "unlocatable",
            "error": "图谱与派生节点表中都没有该 node_id",
        }

    subject = (fact or {}).get("subject") or (derived or {}).get("slot") or ""
    value = (fact or {}).get("value")
    if value is None and derived:
        value = derived.get("value")
    unit = (fact or {}).get("unit") or (derived or {}).get("unit") or ""

    evidence_ref = (fact or {}).get("source", "")
    evidence_rec = None
    for e in g.get("items", {}).get("evidence") or []:
        if e.get("id") == evidence_ref:
            evidence_rec = e
            break

    candidates = [subject]
    if value is not None:
        candidates.extend([_fmt_value(value), str(value)])
    if derived and derived.get("slot"):
        candidates.append(derived["slot"])

    locators: List[Dict[str, Any]] = []

    # 1) 新项目事实输入
    for name in ("事实输入-新项目-华东理工AI研究院-v2.md",
                 "事实输入-新项目-华东理工AI研究院.md"):
        p = root / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        loc = _search_text(text, candidates, file=name, section="客户事实输入",
                           chunk_id="flat:%s" % name)
        if loc:
            locators.append(loc)
            break

    # 2) 上财 chunks
    for c in _load_chunks(root):
        text = str(c.get("text") or "")
        loc = _search_text(
            text, candidates,
            file=_chunk_doc_name(c),
            section=str(c.get("section") or c.get("section_struct_no") or ""),
            chunk_id=str(c.get("id") or ""),
            base_span=c.get("span"),
        )
        if loc:
            locators.append(loc)
            break

    if not with_excerpt:
        for loc in locators:
            loc["quote"] = None

    status = "derived" if (derived and not fact) else ("located" if locators else "unlocatable")
    out = {
        "node_id": node_id,
        "subject": subject,
        "value": value,
        "unit": unit,
        "status": (fact or {}).get("status") or ("computed" if derived else "provided"),
        "origin": _origin_of_fact(fact) if fact else "derived",
        "source": evidence_ref,
        "evidence": evidence_rec,
        "locator": locators[0] if locators else None,
        "locators": locators,
        "locator_status": status,
        "with_excerpt": with_excerpt,
    }
    if derived:
        out["derived_from"] = {
            "formula": derived.get("formula", ""),
            "inputs": derived.get("inputs", []),
        }
    if fact and fact.get("rule"):
        out["rule"] = fact.get("rule")
    return out


def _chunk_doc_name(chunk: Dict[str, Any]) -> str:
    for a in chunk.get("source_anchors") or []:
        if isinstance(a, dict) and a.get("document_name"):
            return a["document_name"]
    return str(chunk.get("document_id") or "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _dump(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="推演写作专家查询接口：skeleton / graph / evidence")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("skeleton", help="取本节骨架")
    p1.add_argument("--section", required=True)
    p1.add_argument("--root", default=None)

    p2 = sub.add_parser("graph", help="取本节节点")
    p2.add_argument("--section", required=True)
    p2.add_argument("--kind", default="all", choices=["all", "quantity", "judgment", "text", "undefined"])
    p2.add_argument("--root", default=None)

    p3 = sub.add_parser("evidence", help="取节点证据")
    p3.add_argument("--node", required=True)
    p3.add_argument("--no-excerpt", action="store_true")
    p3.add_argument("--root", default=None)

    args = ap.parse_args(argv)
    if args.cmd == "skeleton":
        _dump(corpus_get_skeleton(args.section, root=args.root))
    elif args.cmd == "graph":
        _dump(graph_query(args.section, args.kind, root=args.root))
    else:
        _dump(evidence_get(args.node, with_excerpt=not args.no_excerpt, root=args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
