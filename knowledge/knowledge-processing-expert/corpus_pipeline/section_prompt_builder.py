# -*- coding: utf-8 -*-
"""section_prompt_builder v2 —— 形节点树 + 值填充 + 推导传播（零 LLM）。

## 用户要的三层结构

  ① **形节点树**：本节该有哪些字段、谁是谁的父/子（结构，不含值）
  ② **值填充**：形节点 ← 具体值（带节点 ID，可反查）
  ③ **推导传播**：填了一个值，哪些节点能算出来；哪些节点缺依赖要向上找

## 「形节点」从哪来

- `derivation_templates.yaml` 的 `expr`：`{总投资} = {建安}+{其他}+...`
  → 变量名就是形节点名，父子关系从 expr 解析
- `fact_source_map.yaml` 的 `source_type`：决定该节点「客户给 / 标准查 / 算出来」
- `section-writing-guide-2023.yaml` 的 `must_cover`：本节必须出现的项

## 状态四态

  ✓ 已填    graph 里有值
  ○ 可算    expr 的依赖齐了，能推出来
  ◐ 缺输入  依赖缺 → 要客户给（或标出缺哪个）
  ✗ 需检索  行业/标准/政策信息，客户不会给
"""
from __future__ import annotations
import re
from pathlib import Path

import yaml


def _find_pkg() -> Path:
    cands = [Path.cwd()/"形-可复用知识资产-v1.0",
             Path(__file__).resolve().parents[1]/"形-可复用知识资产-v1.0"]
    for c in cands:
        if (c/"templates"/"section-writing-guide-2023.yaml").exists():
            return c
    base = Path.home()/"workdsh/.test-runtime/preview/workdsh-projects"
    if base.is_dir():
        for sub in base.iterdir():
            c = sub/"形-可复用知识资产-v1.0"
            if (c/"templates"/"section-writing-guide-2023.yaml").exists():
                return c
    return Path.cwd()/"形-可复用知识资产-v1.0"


def _y(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def _guide(pkg): return (_y(pkg/"templates"/"section-writing-guide-2023.yaml").get("sections") or {})


def _mapping(pkg) -> dict:
    """2023 节 → 2019 节 语义映射。"""
    d = _y(pkg/"skeleton"/"outline-mapping-2019-to-2023.yaml")
    return d.get("mapping") or {}


def _name_match(a: str, b: str) -> float:
    """两个章节名的相似度（0-1）。**不看节号，只看名称**。"""
    a, b = str(a or "").strip(), str(b or "").strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9
    # 字集重叠
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(len(sa), len(sb))


def _rules_via_2019(pkg, key: str, mapping: dict, title: str = "") -> tuple:
    """通过「2019 章节名」找回规则。**只用映射表里的精确名称，不做模糊匹配**。

    理由：模糊匹配会过度命中（「工程方案」误命中「子系统A」）。
    映射表是人工建的，值得信任；名称不一致时该修映射表，不是放宽匹配。

    返回 (rules, 命中的2019节名列表)
    """
    ent = mapping.get(key) or {}
    targets = set(str(x).strip() for x in (ent.get("skeleton_2019") or []))
    if not targets:
        return [], []
    g19 = _y(pkg/"templates"/"section-writing-guide.yaml").get("sections") or {}
    out, hits = [], []
    for k19, v19 in g19.items():
        t19 = str(v19.get("title") or "").strip()
        if t19 not in targets:
            continue
        rr = v19.get("rules_required") or []
        if rr:
            hits.append(t19)
            for r in rr:
                if r not in out:
                    out.append(r)
    return out, hits


def _find_reference(pkg, key: str, title: str, limit: int = 2) -> list:
    """从 119 节详版（上财原文）里找**内容**相近的节做仿照参考。

    **不能只按节号** —— 上财 2019 的 §1.2 是「研究内容和编制依据」，
    2023 的 §1.2 是「项目单位概况」，同号不同内容。
    判据：标题词重叠度 >= 0.34 才算相近；同节号只在标题也相近时才采纳。
    """
    d = _y(pkg/"templates"/"section-writing-guide.yaml").get("sections") or {}
    tt = str(title or "")
    cands = []
    for k, v in d.items():
        ti = str(v.get("title") or "")
        if not ti or not tt:
            continue
        ov = len(set(ti) & set(tt)) / max(len(set(tt)), 1)
        if ov >= 0.34:
            same_no = (k == key)
            cands.append((ov + (0.1 if same_no else 0), k, ti, ov, same_no))
    cands.sort(key=lambda x: -x[0])
    return [{"ref": k, "title": ti,
             "why": ("同节号+标题相近" if sn else "标题相近") + "（%.0f%%）" % (ov*100)}
            for _, k, ti, ov, sn in cands[:limit]]



VAR = re.compile(r"\{([^}]+)\}")

# 需 web 检索（公开可查，不该问客户）
WEB_HINTS = (
    "依据", "标准", "规范", "政策", "法律", "法规", "规划", "条例",
    "办法", "导则", "行业", "市场", "案例", "对标", "符合性",
    "节能", "绿建", "评价", "指标库", "定额",
    "性质", "组织机构", "组织架构", "隶属", "沿革", "院系", "学院设置",
    "资质", "荣誉", "简介", "概况", "成立时间", "办学层次",
    "区位", "交通", "市政配套", "产业基础", "上位规划", "控规",
)
# 项目专属（必须客户给）
PROJECT_SPECIFIC = (
    "本项目", "本工程", "拟建", "规划人数", "规划面积", "总投资额",
    "自筹", "国拨", "预备费", "拆除面积", "建设工期", "开工", "竣工",
)
# 论证性（用已有数据论证，不需新值）
ARGUE_HINTS = (
    "必要性", "可行性", "合理性", "充分性", "结论", "建议", "意义",
    "效益", "影响", "评价", "论证", "分析", "判断", "风险", "对策",
    "驱动", "导向", "战略", "需求", "背景", "优势", "问题",
)
# 结构性（章节小标题）
STRUCT_HINTS = (
    "估算依据", "分项估算", "编制依据", "依据说明", "概述", "说明",
    "概况", "结论", "建议",
)


def _rules(pkg):
    return _y(pkg/"functions"/"derivation_templates.yaml").get("rules") or {}


def _fsm(pkg):
    return {f.get("fact"): f
            for f in (_y(pkg/"ontology"/"fact_source_map.yaml").get("facts") or [])
            if f.get("fact")}


def _facts_by_sk(graph):
    out = {}
    for f in (graph.get("items", {}).get("facts") or []):
        keys = [str(x).lstrip("§") for x in (f.get("skeleton_section") or [])]
        if not keys:
            keys = [str(f.get("section") or "").lstrip("§")]
        for k in keys:
            if k:
                out.setdefault(k, []).append(f)
    return out


def _label_to_fact(facts, label):
    """var 名 → fact。精确优先，其次单向前后缀且长度差 <=4（避免串位）。"""
    lab = str(label or "").strip()
    if not lab:
        return None
    for f in facts:
        if str(f.get("subject") or "").strip() == lab:
            return f
    cands = []
    for f in facts:
        s = str(f.get("subject") or "").strip()
        if not s:
            continue
        if s.startswith(lab) or s.endswith(lab):
            cands.append((abs(len(s) - len(lab)), f))
    if cands:
        cands.sort(key=lambda x: x[0])
        if cands[0][0] <= 4:
            return cands[0][1]
    return None


def _fmt(fact):
    v, u = fact.get("value"), fact.get("unit") or ""
    if v is None:
        return "（缺）"
    try:
        fv = float(v)
        s = f"{int(fv):,}" if fv == int(fv) else f"{fv:,}"
    except (TypeError, ValueError):
        s = str(v)
    return f"{s} {u}".strip()


def _node_state(label, facts, rules, fsm, seen=None):
    """五+1 态：have / derive / missing / web / argue / struct"""
    lab = str(label or "")
    f = _label_to_fact(facts, lab)
    if f and f.get("value") is not None:
        return "have", _fmt(f)
    for rid, rv in rules.items():
        if str(rv.get("target") or "") == lab:
            deps = [str(d) for d in (rv.get("deps_required") or [])]
            missing = [d for d in deps
                       if not (_label_to_fact(facts, d) or {}).get("value")]
            if not missing:
                return "derive", f"由 {rid} 算出"
            return "missing", f"缺：{'、'.join(missing[:3])}"
    src = (fsm.get(lab) or {}).get("source_type")
    if src == "COMPUTED":
        return "missing", "应可算，但无规则"
    if src == "STANDARD":
        return "web", "标准/规范 → web 检索"
    if src in ("CUSTOMER", "CUSTOMER_PRIMARY"):
        return "missing", "向客户索取"
    if src == "JUDGMENT":
        return "missing", "需专业判断（客户声明 + 绑证据）"
    if any(h in lab for h in PROJECT_SPECIFIC):
        return "missing", "项目专属值 → 向客户索取"
    if any(h in lab for h in ARGUE_HINTS):
        return "argue", "论证生成（用已有数据推，不需新值）"
    if any(h in lab for h in STRUCT_HINTS) and len(lab) <= 8:
        return "struct", "结构性项（按骨架展开）"
    if any(h in lab for h in WEB_HINTS):
        return "web", "公开信息 → web 检索（官网/年报/政策文件）"
    return "missing", "来源未定 → 向客户确认"


def build_prompt(graph: dict, *, section: str, title: str = "", path: str = "",
                 level: int = 2, tags=None, pkg=None) -> dict:
    ICON = {"have": "✓ 已填", "derive": "○ 可算",
            "missing": "◐ 缺输入", "web": "✗ 需检索",
            "struct": "▤ 结构性", "argue": "◆ 论证生成"}
    key = str(section).lstrip("§")
    pkg = Path(pkg) if pkg else _find_pkg()
    gi = _guide(pkg).get(key) or {}
    rules_all, fsm = _rules(pkg), _fsm(pkg)
    ALL_FACTS = list(graph.get("items", {}).get("facts") or [])
    facts = _facts_by_sk(graph).get(key, [])
    # 跨节取值：本节没有的，去全图找（如 §7.1 要用 §3.2 的建筑面积）
    scope = facts + [f for f in ALL_FACTS if f not in facts]
    cover = gi.get("must_cover") or []
    rules_req = list(gi.get("rules_required") or [])
    # 2023 节没规则 → 通过 2019 映射找
    mp = _mapping(pkg)
    # 经 2019 名称映射补回（即使已有规则，也补充缺失的）
    via19, hit19 = _rules_via_2019(pkg, key, mp, title or gi.get("title") or "")
    added19 = [r for r in via19 if r not in rules_req]
    rules_req = rules_req + added19

    # ── ① 形节点树：从 rules_req 的 expr 解析父子
    tree = []          # [{label, state, detail, rule, deps, fact_id}]
    seen_labels = set()
    for rid in rules_req:
        rv = rules_all.get(rid) or {}
        tgt = str(rv.get("target") or "")
        expr = str(rv.get("expr") or "")
        vars_ = VAR.findall(expr)
        if not tgt: continue
        st, dt = _node_state(tgt, scope, rules_all, fsm)
        f = _label_to_fact(scope, tgt)
        tree.append({"label": tgt, "level": 0, "rule": rid, "expr": expr,
                     "state": st, "detail": dt,
                     "fact_id": f.get("id") if f else None})
        seen_labels.add(tgt)
        for v in vars_:
            if v in seen_labels: continue
            if v == tgt: continue
            seen_labels.add(v)
            st2, dt2 = _node_state(v, scope, rules_all, fsm)
            f2 = _label_to_fact(scope, v)
            tree.append({"label": v, "level": 1, "rule": None, "expr": None,
                         "state": st2, "detail": dt2,
                         "fact_id": f2.get("id") if f2 else None})

    # ── ② must_cover 里既不在树、也无值的 → 补进「缺项」
    extra_missing = []
    for it in cover:
        it = str(it)
        if any(it in t["label"] or t["label"] in it for t in tree): continue
        f = _label_to_fact(scope, it)
        if f and f.get("value") is not None: continue
        st, dt = _node_state(it, scope, rules_all, fsm)
        extra_missing.append({"item": it, "state": st, "detail": dt})

    stats = {"have": 0, "derive": 0, "missing": 0, "web": 0,
             "struct": 0, "argue": 0}
    for t in tree: stats[t["state"]] = stats.get(t["state"], 0) + 1
    for m in extra_missing: stats[m["state"]] = stats.get(m["state"], 0) + 1

    # ── 组装
    L = [f"## §{key} {title or gi.get('title') or ''}", ""]
    L.append(f"**位置**：{path or ' > '.join(gi.get('path') or [])} ｜ **层级** {level}")
    if tags: L.append(f"**项目标签**：{' · '.join(tags)}")
    L += ["", "> 本节有三层：**① 形节点树**（结构）→ **② 值填充** → **③ 推导传播**。", ""]

    # ① 形节点树
    L += [f"### ① 本节「形」节点（{len(tree)} 个）", ""]
    if tree:
        L += ["| 层级 | 形节点 | 状态 | 值 / 来源 |", "|---|---|---|---|"]
        for t in tree:
            lv = "根" if t["level"] == 0 else "├ 子项"
            L.append(f"| {lv} | **{t['label']}** | {ICON[t['state']]} | {t['detail'][:40]} |")
    else:
        L.append("_本节无预定义计算规则；按下述 must_cover 项逐项撰写。_")
    L.append("")

    # ② 值填充
    filled = [t for t in tree if t["state"] == "have"]
    L += [f"### ② 值填充（{len(filled)} 项已有值）", ""]
    if filled:
        L += ["| 形节点 | 值 | 节点 ID（正文必须引用） |", "|---|---|---|"]
        for t in filled:
            in_sec = any(str(g2.get("id")) == str(t["fact_id"]) for g2 in facts)
            mark = "" if in_sec else " *（他节）*"
            L.append(f"| {t['label']} | {t['detail']} | 〔{t['fact_id']}〕{mark} |")
    else:
        L.append("_本节尚无可填值。_")
    L.append("")

    # ③ 推导传播
    L += ["### ③ 推导传播（基于节点关系）", ""]
    if rules_req:
        for rid in rules_req:
            rv = rules_all.get(rid) or {}
            if not rv.get("expr"): continue
            L.append(f"- **{rid}** → `{rv.get('target')}`")
            L.append(f"  - 表达式：`{rv.get('expr')}`")
            deps = [str(d) for d in (rv.get("deps_required") or [])]
            ok = [d for d in deps if (_label_to_fact(scope, d) or {}).get("value") is not None]
            miss = [d for d in deps if d not in ok]
            if ok: L.append(f"  - 已备依赖：{'、'.join(ok[:6])}")
            if miss: L.append(f"  - **缺依赖：{'、'.join(miss[:6])}** → 缺则标 undefined，不许猜")
        L.append("")
    else:
        L.append("_本节无必须写的算式。_")
        L.append("")

    # ④ 缺什么、去哪找
    L += ["### ④ 缺项与补齐方式（只列真正缺的）", ""]
    miss_nodes = [t for t in tree if t["state"] in ("missing", "web")]
    if miss_nodes or extra_missing:
        L += ["| 缺项 | 状态 | 动作 |", "|---|---|---|"]
        for t in miss_nodes:
            act = "**去 web 检索**（标准/政策/行业）" if t["state"] == "web" \
                  else f"**向客户索取**（{t['detail'][:30]}）"
            L.append(f"| {t['label']} | {ICON[t['state']]} | {act} |")
        for m in extra_missing:
            act = "**去 web 检索**" if m["state"] == "web" else "**向客户索取**"
            L.append(f"| {m['item']} | {ICON[m['state']]} | {act} |")
    else:
        L.append("_本节数据齐备。_")
    L.append("")

    # ⑤ must_cover 全文
    # ④a 规则来源说明（若经 2019 映射找回）
    if added19:
        L += ["### ③b 规则补回（按章节**名称**匹配 2019，非节号）", ""]
        L.append(f"命中 2019 章节：{'、'.join(hit19[:6]) or '—'}")
        L.append("")
        L.append(f"补回 {len(added19)} 条规则：" + "、".join(f"`{r}`" for r in added19))
        L.append("")

    # ④b 仿照参考
    refs = _find_reference(pkg, key, title or gi.get("title") or "")
    if refs:
        L += ["### ④b 仿照参考（形包里的同类章节写法）", ""]
        for r in refs:
            L.append(f"- `§{r['ref']} {r['title']}` —— {r['why']}")
            rv = (_y(pkg/"templates"/"section-writing-guide.yaml").get("sections") or {}).get(r["ref"]) or {}
            if rv.get("detail_hint"):
                L.append(f"  - 篇幅：{str(rv['detail_hint'])[:100]}")
            if rv.get("evidence_requirements"):
                L.append(f"  - 证据：{str(rv['evidence_requirements'])[:80]}")
            if rv.get("writing_style"):
                L.append(f"  - 风格：{str(rv['writing_style'])[:80]}")
        L.append("")
        L.append("> **没有数据时**：先按上面参考节的写法搭结构，缺的信息去 web 检索"
                 "（学校官网/教育部/年报/政策文件），检索到的绑来源；检不到的才进 unresolved。")
        L.append("")

    if cover:
        L += [f"### ⑤ 本节必须覆盖（{len(cover)} 项，来自 2023 写作指引）", ""]
        for i, it in enumerate(cover, 1): L.append(f"{i}. {it}")
        L.append("")

    # ⑥ 证据/篇幅/契约
    if gi.get("evidence_requirements"):
        L += ["### ⑥ 证据要求", "", str(gi["evidence_requirements"]), ""]
    if gi.get("detail_hint"):
        L += ["### ⑦ 篇幅", "", str(gi["detail_hint"]), ""]
    L += ["### ⑧ 返回契约", "", "```json",
          '{"body":"Markdown，每数写〔P-xxx〕",',
          ' "node_mentions":["节点id"],',
          ' "new_claims":[{"text","claim_type","evidence_refs"}],',
          ' "unresolved":[{"kind":"missing_value|conflict|needs_web","detail","blocks"}]}',
          "```", "",
          "**硬要求**：数值只写〔节点ID〕；◐ 不许猜写「待客户提供」；✗ 去 web 检索；"
          "算式必须写出并复算；冲突不裁决两侧都写。"]

    prompt = "\n".join(L)
    return {"section": key, "title": title or gi.get("title") or "", "tags": tags,
            "prompt": prompt, "tree": tree, "missing_extra": extra_missing,
            "stats": {**stats, "nodes": len(tree), "rules": len(rules_req),
                      "facts": len(facts), "chars": len(prompt)},
            "contract": {"body": "Markdown，数值写〔P-xxx〕引用", "node_mentions": [],
                         "new_claims": [], "unresolved": []}}


def build_all(graph: dict, *, tags=None, pkg=None) -> list:
    pkg = Path(pkg) if pkg else _find_pkg()
    g = _guide(pkg)
    return [build_prompt(graph, section=k, title=v.get("title") or "",
                         path=" > ".join(v.get("path") or []),
                         level=v.get("level") or 2, tags=tags, pkg=pkg)
            for k, v in sorted(g.items(), key=lambda x: (len(x[0]), x[0]))]
