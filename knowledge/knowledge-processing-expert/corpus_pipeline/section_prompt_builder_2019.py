# -*- coding: utf-8 -*-
"""section_prompt_builder_2019 —— 用上财 119 节的「形」还原新项目报告（零 LLM）。

## 与 2023 版的根本区别

**2023 版**：以「2023 法定 41 节」为骨架，需要跨骨架映射（节号/题目）→ **复杂且易错**
**本模块**：以「上财 119 节」为骨架 —— **形就是从这里抽的，不需要映射**

## 还原链路（不经过任何章节映射）

    上财某节 §X
      ↓ 它的 rules_required（如 R-总投资构成）
    规则 expr / deps_required（变量名，如 总投资 / 建安工程费用 / 预备费）
      ↓ 按变量名匹配（不是按章节）
    新项目 facts（subject 同名）→ 值 + 节点 ID
      ↓
    提示词：结构 + 算式 + 已填值 + 缺值

## 状态五态

  ✓ 已填 / ○ 可算 / ◐ 缺输入（要客户）/ ✗ 需检索 / ▣ 无规则(纯写作)
"""
from __future__ import annotations
import re
from pathlib import Path

import yaml

VAR = re.compile(r"\{([^}]+)\}")

# 原文里必须保留的「形」引用（表号/图号/标准号/百分比/文号），不能当值替换
_KEEP = re.compile(
    r"表\s*\d+(?:\s*[-—–]\s*\d+)?|图\s*\d+(?:\s*[-—–]\s*\d+)?|"
    r"第\s*\d+\s*[章节条]|GB\s*/?\s*T?\s*\d+(?:[-.]\d+)*|DGJ\s*\d+(?:[-.]\d+)*|"
    r"建标\s*\d+(?:[-.]\d+)?|〔[^〕]*〕(?:\s*\d+号)?|\d+(?:\.\d+)?\s*%"
)
_STRUCT_CELL = re.compile(r"^(?:[一二三四五六七八九十]+|（[一二三四五六七八九十]+）|\d+(?:\.\d+)*)$")
_GLOBAL_TEXT = {"项目名称", "项目编号", "建设单位", "建设地点", "编制单位", "编制时间", "依据大纲"}


def _devalue(text: str) -> str:
    """原文去值：项目专名与数字 → 占位符，保留句式、结构与表号/标准号/百分比。"""
    t = str(text or "")
    t = t.replace("上海财经大学中山北一路校区大数据研究中心", "{项目名称}")
    t = t.replace("上海财经大学", "{建设单位}")
    t = t.replace("中山北一路校区", "{校区}")
    t = t.replace("大数据研究中心", "{项目名称}")
    keep = []

    def _hold(m):
        keep.append(m.group(0))
        # 占位符不得含数字，否则会被下面的数字正则二次替换（旧实现 bug）
        return chr(0xE100 + len(keep) - 1)

    t = _KEEP.sub(_hold, t)
    t = re.sub(r"\d[\d,]*(?:\.\d+)?", "{原值}", t)
    for i, v in enumerate(keep):
        t = t.replace(chr(0xE100 + i), v)
    return t


def _devalue_cell(c) -> str:
    """表格单元格去值；仅「序号」列的结构编号（一 / （一） / 1.1）原样保留。"""
    s = str(c if c is not None else "").strip()
    if not s or _STRUCT_CELL.fullmatch(s):
        return s
    return _devalue(s)


def _devalue_row(cells, cols) -> list:
    """按列语义去值：首列是序号时保留层级编号，其余列（含纯数字）全部去值。"""
    keep_seq = bool(cols) and ("序号" in str(cols[0]) or "编号" in str(cols[0]))
    out = []
    for ci, c in enumerate((cells or [])[:len(cols)]):
        s = str(c if c is not None else "").strip()
        if keep_seq and ci == 0 and _STRUCT_CELL.fullmatch(s):
            out.append(s)
        else:
            out.append(_devalue(s))
    return out


def _is_text_fact(f: dict) -> bool:
    if f.get("fact_kind") == "text":
        return True
    v = f.get("value")
    if v is None:
        return False
    try:
        float(str(v).replace(",", ""))
        return False
    except (TypeError, ValueError):
        return True


def _text_facts(facts: dict, ex: dict | None) -> list:
    """本节可用的文本事实：全局项目元数据 + 原文中出现的文本变量。"""
    src = "\n".join((ex or {}).get("paras") or [])
    out = []
    for sub, f in facts.items():
        if not _is_text_fact(f):
            continue
        if sub in _GLOBAL_TEXT or (src and sub in src):
            out.append(f)
    return out


def _find_pkg() -> Path:
    for c in [Path.cwd()/"形-可复用知识资产-v1.0",
              Path(__file__).resolve().parents[1]/"形-可复用知识资产-v1.0"]:
        if (c/"templates"/"section-writing-guide.yaml").exists():
            return c
    base = Path.home()/"workdsh/.test-runtime/preview/workdsh-projects"
    if base.is_dir():
        for sub in base.iterdir():
            c = sub/"形-可复用知识资产-v1.0"
            if (c/"templates"/"section-writing-guide.yaml").exists():
                return c
    return Path.cwd()/"形-可复用知识资产-v1.0"


_YAML_CACHE: dict = {}


def _y(p):
    """带缓存读 yaml —— 119 节 × 多个文件，不缓存会慢几十倍。"""
    key = str(p)
    if key in _YAML_CACHE:
        return _YAML_CACHE[key]
    d = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    _YAML_CACHE[key] = d
    return d


_FORMS_CACHE = {}


def _load_forms(pkg) -> dict:
    """加载章节形态形（templates/section-form.yaml）。"""
    key = str(pkg)
    if key in _FORMS_CACHE:
        return _FORMS_CACHE[key]
    d = _y(pkg / "templates" / "section-form.yaml")
    f = d.get("forms") or {}
    _FORMS_CACHE[key] = f
    return f


def _guide19(pkg):
    return _y(pkg/"templates"/"section-writing-guide.yaml").get("sections") or {}


def _rules(pkg):
    return _y(pkg/"functions"/"derivation_templates.yaml").get("rules") or {}


def _fsm(pkg):
    return {f.get("fact"): f
            for f in (_y(pkg/"ontology"/"fact_source_map.yaml").get("facts") or [])
            if f.get("fact")}


def _facts(graph):
    """subject → fact（全图，不按章节）"""
    out = {}
    for f in (graph.get("items", {}).get("facts") or []):
        s = str(f.get("subject") or "").strip()
        if s and s not in out:
            out[s] = f
    return out


def _match_var(var: str, facts: dict, aliases: dict | None = None):
    """变量名 → fact。**走 evo_match 的三层匹配**（exact / alias / similar）。"""
    try:
        from corpus_pipeline.evo_match import match_var as _mv
    except ImportError:
        _mv = None
    if _mv is not None:
        f, method, score = _mv(var, facts, aliases or {})
        if f is not None:
            f = dict(f)
            f["_match_method"] = method
            f["_match_score"] = score
        return f
    # 退化：精确 + 前后缀
    v = str(var or "").strip()
    if not v:
        return None
    if v in facts:
        return facts[v]
    cands = []
    for s, f in facts.items():
        if s.startswith(v) or s.endswith(v) or v.startswith(s) or v.endswith(s):
            cands.append((abs(len(s) - len(v)), f))
    if cands:
        cands.sort(key=lambda x: x[0])
        if cands[0][0] <= 4:
            return cands[0][1]
    return None


def _fmt(f):
    if not f:
        return "（缺）"
    v, u = f.get("value"), f.get("unit") or ""
    if v is None:
        return "（缺）"
    try:
        fv = float(v)
        s = f"{int(fv):,}" if fv == int(fv) else f"{fv:,}"
    except (TypeError, ValueError):
        s = str(v)
    return f"{s} {u}".strip()


def _aliases(pkg):
    try:
        from corpus_pipeline.evo_match import load_aliases
        return load_aliases(pkg)
    except Exception:
        return {}


def build_section(graph: dict, *, sec_id: str, pkg=None, chunks=None,
                  source_md=None, tags=None, extra_notes: str = "") -> dict:
    pkg = Path(pkg) if pkg else _find_pkg()
    AL = _aliases(pkg)
    g19 = _guide19(pkg)
    v = g19.get(sec_id) or {}
    rules_all = _rules(pkg)
    fsm = _fsm(pkg)
    facts = _facts(graph)

    title = str(v.get("title") or "")
    path = " > ".join(v.get("path") or [])
    rr = v.get("rules_required") or []
    forms = _load_forms(pkg)
    form = forms.get(title) or forms.get(str(v.get("title") or "")) or {}

    # ★ 原文优先：按「标题名称」从 normalized.md 取完整本节；chunks 仅兜底。
    #   旧实现只从 chunks 取，边界错误会把本节最后一句划给下一节
    #   （7.2.2 的「因此，项目年总耗电量…」就被丢了）。
    ex = None
    if source_md:
        try:
            from corpus_pipeline.evo_source_section import extract_section
            md_text = Path(source_md).read_text(encoding="utf-8")
            stop_titles = [str(x.get("title")) for x in g19.values() if x.get("title")]
            # 形包 title 是抽象名（子系统A/{校区}/{建设单位}），
            # 原文是实名；raw_sections + 占位符替换提供别名，名称仍是第一优先级。
            candidates = [title]
            candidates += [str(x) for x in (form.get("raw_sections") or [])]
            candidates.append(title.replace("{校区}", "中山北一路校区")
                                      .replace("{建设单位}", "上海财经大学"))
            seen = set()
            for cand in candidates:
                cand = str(cand or "").strip()
                if not cand or cand in seen:
                    continue
                seen.add(cand)
                ex = extract_section(md_text, cand, stop_titles=stop_titles)
                if ex.get("found"):
                    break
        except Exception:
            ex = None
    if (not ex or not ex.get("found")) and chunks:
        try:
            from corpus_pipeline.evo_source_excerpt import excerpt
            ex = excerpt(chunks, title, pkg=pkg)
        except Exception:
            ex = None

    # 形包未收录的节：用 normalized.md 实测形态补 form，
    # 不能退回「形包未收录 → 自行组织结构」（那会丢掉原文的形）。
    if not form and ex and (ex.get("paras") or ex.get("tables")):
        tchars = 0
        for tb in ex.get("tables") or []:
            tchars += len(re.sub(r"\s", "", " ".join(
                " ".join(str(c) for c in r) for r in (tb.get("rows_data") or []))))
        total = ex.get("para_chars", 0) + tchars
        form = {
            "style": "table_dominant" if tchars > ex.get("para_chars", 0) * 3 else "prose_dominant",
            "paras": len(ex.get("paras") or []),
            "para_chars": ex.get("para_chars", 0),
            "tables": ex.get("tables") or [],
            "table_chars": tchars,
            "total_chars": total,
            "target_chars": [total, total * 3],
            "guidance": "按原文实测形态还原：%d 段 / %d 字 / %d 表。"
                        % (len(ex.get("paras") or []), ex.get("para_chars", 0),
                           len(ex.get("tables") or [])),
            "_source": "normalized.md（形包未收录，按原文实测补形）",
        }

    # ① 规则 → 变量 → 值
    rows, exprs = [], []
    seen_vars = set()
    for rid in rr:
        rv = rules_all.get(rid) or {}
        expr = str(rv.get("expr") or "")
        tgt = str(rv.get("target") or "")
        deps = [str(d) for d in (rv.get("deps_required") or [])]
        exprs.append({"rule": rid, "expr": expr, "target": tgt, "deps": deps})
        # 目标变量
        if tgt and tgt not in seen_vars:
            seen_vars.add(tgt)
            f = _match_var(tgt, facts, AL)
            st = "have" if (f and f.get("value") is not None) else "derive"
            rows.append({"var": tgt, "role": "结果", "rule": rid,
                         "state": st, "fact": f})
        # 依赖变量
        for d in deps:
            if d in seen_vars:
                continue
            seen_vars.add(d)
            f = _match_var(d, facts, AL)
            if f and f.get("value") is not None:
                rows.append({"var": d, "role": "输入", "rule": rid,
                             "state": "have", "fact": f})
            else:
                src = (fsm.get(d) or {}).get("source_type")
                st = "web" if src == "STANDARD" else "missing"
                rows.append({"var": d, "role": "输入", "rule": rid,
                             "state": st, "fact": None})

    # ② 本节无规则 → 纯写作节（用 must_cover 或标题展开）
    no_rule = not rr

    stats = {"have": 0, "derive": 0, "missing": 0, "web": 0}
    for r in rows:
        stats[r["state"]] = stats.get(r["state"], 0) + 1

    # 组装
    L = [f"## §{sec_id} {title}", ""]
    L.append(f"**路径**：{path} ｜ **层级** {v.get('level') or 2}")
    if v.get("project_tags"):
        L.append(f"**上财这节的标签**：{' · '.join(v['project_tags'][:8])}")
    if tags:
        L.append(f"**本项目标签**：{' · '.join(tags)}")
    L.append("")
    L.append("> 还原链路：上财本节「形」（形态 + 规则）→ 新项目值。**不经过章节映射。**")
    L.append("")

    # ★ 原文形态（根因修复：让 LLM 照着原文的形态产出，而不是自由发挥）
    if form:
        L += ["### ⓿ 本节原文形态（**必须照此产出**）", ""]
        L.append("- **文体**：%s" % form.get("style"))
        # 原文实测优先：形包统计来自旧 chunks，可能已过时
        # （实测 1.1 形包记 4 段，normalized.md 原文实为 6 段）。
        e_paras = ex.get("paras") if ex and ex.get("found") else None
        e_tables = ex.get("tables") if ex and ex.get("found") else None
        n_paras = len(e_paras) if e_paras is not None else form.get("paras", 0)
        para_chars = ex.get("para_chars", 0) if e_paras is not None else form.get("para_chars", 0)
        L.append("- **段落**：%d 段（%d 字）" % (n_paras, para_chars))
        if e_paras is not None and (n_paras != form.get("paras") or para_chars != form.get("para_chars")):
            L.append("  - ⚠ 形包旧统计为 %d 段 / %d 字（来自旧 chunks，已废弃；以原文实测为准）"
                     % (form.get("paras", 0), form.get("para_chars", 0)))
        if e_paras is None and form.get("para_roles"):
            L.append("  - 角色：%s" % ("、".join(form.get("para_roles") or []) or "—"))
        tl = e_tables if e_tables is not None else (form.get("tables") or [])
        if tl:
            for i, tb in enumerate(tl, 1):
                cols = tb.get("cols") or []
                rows_n = tb.get("rows", 0) or len(tb.get("rows_data") or [])
                L.append("- **表 %d**：%d 列 × %d 行，嵌套 %d 层"
                         % (i, len(cols), rows_n, tb.get("nest", 1)))
                L.append("  - 列：%s" % " ｜ ".join(cols))
                sample = tb.get("sample_rows") or (tb.get("rows_data") or [])[:1]
                if sample:
                    L.append("  - 样例行：`%s`"
                             % " ｜ ".join(_devalue_row(sample[0], cols)))
        else:
            L.append("- **表**：无（本节不使用表格）")
        # 目标字数 = 原文段落+表格总字数 的 1–3 倍（评分器的篇幅口径）
        tchars = 0
        for tb in (e_tables or []):
            tchars += len(re.sub(r"\s", "", " ".join(
                " ".join(str(c) for c in r) for r in (tb.get("rows_data") or []))))
        total_ref = para_chars + (tchars if e_tables is not None else form.get("table_chars", 0))
        L.append("- **目标字数**：%d – %d 字（原文实测 %d 字）"
                 % (total_ref, total_ref * 3, total_ref))
        L.append("")
        L.append("**形态纪律**：")
        L.append("1. %s" % (form.get("guidance") or ""))
        L.append("2. **不得改变文体**：原文表格为主 → 必须以表格为主体，不得改成多小节散文。")
        L.append("3. **不得减少列**：原文的每一列都要出现（可改名，不可删除）。")
        L.append("4. **不得拆表**：原文一张表，还原也必须是一张表；分项用「序号」列分层，不拆小节。")
        L.append("5. **过程优先于结果**：原文有「数量 × 单价 = 合价」的，还原必须三列齐全。")
        L.append("")
    else:
        L += ["### ⓿ 本节原文形态", "", "_（形包未收录本节形态，按标题语义自行组织结构）_", ""]

    # ★★ 原文全文（架构修正：提示词基于完整原文，不基于形包）
    if ex and (ex.get("paras") or ex.get("tables")):
        L += ["### ⓿b 本节原文（**写法与详略的唯一权威**）", ""]
        L.append("> 下面是从原报告 `normalized.md` 按标题「%s」抽取的**完整本节内容**；"
                 "原文数值已替换为 `{原值}`（去值留形）。"
                 "**请严格照此结构、详略与措辞习惯还原**，只把值换成本项目数据。" % title)
        L.append("")
        L.append("**原文段落（%d 段 / %d 字）：**"
                 % (len(ex["paras"]), ex.get("para_chars", 0)))
        L.append("")
        for i, pa in enumerate(ex["paras"], 1):
            L.append("%d. %s" % (i, _devalue(pa)))
        L.append("")
        for ti, tb in enumerate(ex["tables"], 1):
            cols = tb.get("cols") or []
            rows_data = tb.get("rows_data") or []
            L.append("**原文表 %d：%d 列 × %d 行，嵌套 %d 层**"
                     % (ti, len(cols), len(rows_data) or tb.get("rows", 0), tb.get("nest", 1)))
            L.append("")
            if cols:
                L.append("| " + " | ".join(cols) + " |")
                L.append("|" + "---|" * len(cols))
                for r in rows_data[:80]:
                    L.append("| " + " | ".join(_devalue_row(r, cols)) + " |")
                if len(rows_data) > 80:
                    L.append("| … | 共 %d 行 |" % len(rows_data))
            L.append("")
        if ex.get("quotes"):
            L.append("**原文引用块（公式/规范原文，%d 条）：**" % len(ex["quotes"]))
            L.append("")
            for q in ex["quotes"][:5]:
                L.append("- `%s`" % q[:160])
            L.append("")
        L.append("**还原纪律（基于原文，不是基于形包）：**")
        L.append("1. **结构照原文**：原文几段就几段，原文一张表就一张表，不增不减。")
        L.append("2. **详略照原文**：原文某段只有一句话，还原也不要扩写成三段。")
        L.append("3. **措辞照原文**：沿用原文的句式与小标题前缀（如「建设地点及建设条件：」）。")
        L.append("4. **只换值不换形**：把原文的项目名/金额/面积换成新项目数据，结构与逻辑不动。")
        L.append("5. **原文有表就更表**：表格列、行层级、备注都要保留，不得拆成多个小节。")
        L.append("")
        L.append("**仿照参考**：⓿b 本节原文就是仿照参考 —— 结构、详略、措辞的唯一权威。")
        L.append("")


    if no_rule:
        # 无计算规则的节也必须有「形节点」：段落节点 + 表格节点来自原文，
        # 不能因为 0 条规则就让提示词只剩一句「自行组织」。
        L += ["### ① 形节点（0 条计算规则；原文形节点如下）", ""]
        shape_rows = []
        for i, pa in enumerate((ex or {}).get("paras") or [], 1):
            p = _devalue(pa).strip()
            if "：" in p[:28]:
                label = p.split("：", 1)[0].lstrip("-•· ").strip()
            else:
                label = p.lstrip("-•· ").strip()
                if len(label) > 36:
                    label = label[:36] + "…"
            shape_rows.append(("段落", label))
        for ti, tb in enumerate((ex or {}).get("tables") or [], 1):
            shape_rows.append(("表格", "表 %d：%d 列 × %d 行（嵌套 %d 层）"
                               % (ti, len(tb.get("cols") or []),
                                  len(tb.get("rows_data") or tb.get("rows") or []),
                                  tb.get("nest", 1))))
        if shape_rows:
            L += ["| 角色 | 形节点 | 状态 |", "|---|---|---|"]
            for role, label in shape_rows:
                L.append("| %s | **%s** | ✓ 已填（原文） |" % (role, label))
            L.append("")
        else:
            L += ["按标题语义组织内容；涉及数值时从其他节的规则取值，或标「需检索/需客户」。", ""]
        L += ["**算式说明**：本节数值关系必须逐行复算，不得凭记忆。", "",
              "```text", "数量 × 单位造价 = 合价", "```", ""]
        L += ["### ⓘ 本节无预定义计算规则", "",
              "按 ⓿b 原文的结构写作；涉及数值时从其他节规则取值，或标「需检索/需客户」。", ""]
    else:
        L += [f"### ① 形节点（{len(rows)} 个，来自 {len(rr)} 条规则）", ""]
        L += ["| 角色 | 变量 | 状态 | 值 / 节点ID |", "|---|---|---|---|"]
        ICON = {"have": "✓ 已填", "derive": "○ 可算",
                "missing": "◐ 缺输入", "web": "✗ 需检索"}
        for r in rows:
            cell = (f"{_fmt(r['fact'])} 〔{r['fact'].get('id')}〕"
                    if r["fact"] else
                    ("**去 web 检索**" if r["state"] == "web" else "**向客户索取**"))
            mm = (r["fact"] or {}).get("_match_method", "")
            tag = "" if mm in ("exact", "") else " `%s`" % mm
            L.append(f"| {r['role']} | **{r['var']}**{tag} | {ICON[r['state']]} | {cell} |")
        L.append("")
        L.append(f"**合计**：已填 {stats['have']} / 可算 {stats['derive']} / "
                 f"缺输入 {stats['missing']} / 需检索 {stats['web']}")
        L.append("")

        if exprs:
            L += [f"### ② 必须写的算式（{len(exprs)} 条）", ""]
            for e in exprs:
                L.append(f"- **{e['rule']}** → `{e['target']}`")
                L.append(f"  - `{e['expr']}`")
                if "未预见系数}/100" in str(e.get("expr") or ""):
                    L += [
                        "  - ⚠ **口径冲突（不得裁决）**：`{未预见系数}=1.15` 与公式 "
                        "`*({未预见系数}/100)` 语义不一致。正文必须并列呈现三种口径并与客户值对比：",
                        "    ① **×1.15（系数语义）**：总用水量 = 基数 × 1.15（未预见增量 = 基数 × 15%）；",
                        "    ② **×1.15%（公式字面）**：第三项 = 基数 × 1.15 ÷ 100；",
                        "    ③ **×10%（上财原文口径）**：不可预计用水量按总用水量的 10% 计算。",
                        "    三种口径的结果、与客户值（① 形节点表）的差额都要写出，标「待审」，不得只选一种。",
                    ]
            # 完整算式块：给写作侧一个可直接复算的 text 块，
            # 也覆盖「纯加法/round((」等不被单条正则识别的公式形态。
            L += ["```text"]
            for e in exprs:
                L.append("%s = %s" % (e.get("target") or "", e.get("expr") or ""))
            L += ["```", ""]
        else:
            L += ["### ② 必须写的算式（0 条）", "",
                  "```text",
                  "本节无显式公式；数值必须来自 ⑦ 文本事实或 ① 形节点，不得自行推算。",
                  "```", ""]

    # ⑦ 文本事实：补「项目名称/建设单位/建设地点/编制单位」等，禁止反向索取
    tfacts = _text_facts(facts, ex)
    if tfacts:
        L += ["### ⑦ 本节文本事实（客户已提供，禁止再向客户索取）", "",
              "| 变量 | 值 | 节点ID |", "|---|---|---|"]
        for f in tfacts:
            L.append("| **%s** | %s | 〔%s〕 |"
                     % (f.get("subject"), f.get("value"), f.get("id")))
        L.append("")

    # ⑧ 必须覆盖的形节点（原文段落标签 + 表格），防止漏段/漏表
    if ex and (ex.get("paras") or ex.get("tables")):
        L += ["### ⑧ 本节必须覆盖（按原文的形节点，不得漏项）", ""]
        for i, pa in enumerate(ex["paras"], 1):
            p = _devalue(pa).strip()
            if "：" in p[:28]:
                label = p.split("：", 1)[0].lstrip("-•· ").strip()
            else:
                label = p.lstrip("-•· ").strip()
                if len(label) > 36:
                    label = label[:36] + "…"
            L.append("%d. %s" % (i, label))
        for ti, tb in enumerate(ex["tables"], 1):
            L.append("- 表 %d：%d 列 × %d 行（嵌套 %d 层）"
                     % (ti, len(tb.get("cols") or []),
                        len(tb.get("rows_data") or tb.get("rows") or []), tb.get("nest", 1)))
        L.append("")

    # ⑨ 已知冲突：图谱里已登记的冲突，必须两侧都写、标待审、不裁决
    conflicts = (graph.get("items", {}) or {}).get("conflicts") or []
    if conflicts:
        sec_ids = {str(r["fact"].get("id")) for r in rows if r.get("fact")}
        keys = {str(r["var"]) for r in rows} | {str(e.get("target")) for e in exprs if e.get("target")}
        picked = []
        for c in conflicts:
            desc = str(c.get("description") or "")
            inv = {str(x) for x in (c.get("involved") or [])}
            if (inv & sec_ids) or any(k and k in desc for k in keys):
                picked.append(c)
        if picked:
            L += ["### ⑨ 已知冲突（两侧都写，不裁决）", ""]
            for c in picked:
                L.append("- **%s（%s）**：%s"
                         % (c.get("id"), c.get("status") or "待审", c.get("description") or ""))
            L.append("")

    if v.get("evidence_requirements"):
        L += ["### ③ 证据要求", "", str(v["evidence_requirements"]), ""]
    if v.get("detail_hint"):
        L += ["### ④ 篇幅", "", str(v["detail_hint"]), ""]
    if extra_notes:
        L += ["### ⑤ 项目补充", "", extra_notes, ""]

    L += ["### ⑥ 返回契约", "", "```json",
          '{"body":"Markdown，每数写〔P-xxx〕", "node_mentions":["id"],',
          ' "new_claims":[], "unresolved":[{"kind","detail","blocks"}]}',
          "```", "",
          "**硬要求**：数值只写〔节点ID〕；◐ 向客户索取不猜；✗ 去 web 检索；"
          "算式必须写出并复算；冲突两侧都写不裁决。"]

    prompt = "\n".join(L)
    return {"sec_id": sec_id, "title": title, "path": path,
            "prompt": prompt, "rows": rows, "exprs": exprs,
            "stats": {**stats, "nodes": len(rows), "rules": len(rr),
                      "chars": len(prompt), "no_rule": no_rule}}


def build_all(graph: dict, *, pkg=None, chunks=None, source_md=None,
              tags=None, verbose=False) -> list:
    """生成全部 119 节。facts / aliases / rules 只算一次，避免逐节重算。"""
    pkg = Path(pkg) if pkg else _find_pkg()
    g19 = _guide19(pkg)
    keys = sorted(g19, key=lambda x: [int(y) if y.isdigit() else 99 for y in x.split(".")])
    out = []
    for i, k in enumerate(keys, 1):
        out.append(build_section(graph, sec_id=k, pkg=pkg, chunks=chunks,
                                 source_md=source_md, tags=tags))
        if verbose and i % 20 == 0:
            print("    %d/%d" % (i, len(keys)), flush=True)
    return out
