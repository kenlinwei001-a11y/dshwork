#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
逐章起草简报：把「查」和「借鉴」合成一份提示词，再动笔。

起草某一章之前实际要凑齐三样东西，它们来自三个不同的地方：

    这一章要说的事实   ←  图谱切片（客户素材 + 推导 + 已确认外部证据）
    还差的外部事实     ←  该章法定内容项触发的检索（section-research.yaml）
    这一章该长什么样   ←  同类历史报告的形（corpus.py，已脱值）

以前这三样是分三次拿的，实际操作时就变成：先照着历史章节写一版，
再往里填数，再补查。这个顺序是套模板的标准路径——
先有了句子，事实就只能去迁就句子。

所以本脚本把三样一次性合成一份简报，并**固定顺序**：
事实先落地，检索补缺口，形最后才进来，而且只以「段落功能顺序、篇幅、
表栏」的形式进来——历史原文不进起草上下文。原文一旦进来，
写出来的东西就带着那份报告的骨相，脱不脱值都一样。

用法：
  section_brief.py project.yaml --section technical [--corpus corpus/]
                                [--subtype ST_WET_LAB]
"""

import sys
import argparse
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assets import guard, load_all  # noqa: E402


def _facets(proj):
    ctx = proj.get("project") or {}
    return {
        "vertical": ctx.get("vertical") or ctx.get("profile"),
        "subtype": None,
        "reporting_to": ctx.get("reporting_to"),
        "outline_version": ctx.get("outline_version"),
    }


def section_covers(proj, sec_key):
    for sec in (proj.get("sections") or []):
        if isinstance(sec, dict) and sec.get("id") == sec_key:
            return set(sec.get("covers") or [])
    return set()


def research_for_section(proj, core, sec_key, spec=None):
    """只留由**这一章**的法定内容项触发的检索任务。

    整篇的检索任务表有十几条，起草某一章时把整张表摆出来，
    实际结果是一条都不查。按章裁到三五条，才会真的去查。
    """
    import intake_gen as IG
    covers = section_covers(proj, sec_key)
    src = "骨架"
    if not covers and spec:
        # 骨架里还没绑内容项时退到章节提示的 covers——总比把整篇十几条摊开强
        covers = set((spec.get("section") or {}).get("covers") or [])
        src = "章节提示"
    tasks = IG.research_tasks(proj, core)
    if not covers:
        return tasks, None
    return [t for t in tasks if set(t.get("triggered_by") or []) & covers], src


# =============================================================================
# 段落级写作计划 —— 「这一章写 3000 字」没法执行，「这一段写 180 字」才能执行
# =============================================================================
# 历史文档定**形与篇幅**，图谱定**完整性**。两者冲突时以图谱为准：
# 宁可比历史多一段，不可少一项。反过来——为了凑够历史的段数而注水——
# 是这套计划最容易被用坏的方式，所以下面把「删段」写成了明示允许的动作。

_DEFAULT_SLOTS = [
    {"func": "定性说明", "paras": 2, "chars": 400},
    {"func": "依据引述", "paras": 2, "chars": 400},
    {"func": "定量陈述", "paras": 3, "chars": 900},
    {"func": "分项罗列", "paras": 2, "chars": 400},
    {"func": "结论判断", "paras": 1, "chars": 150},
]

_AFFINITY = {
    "依据引述": ("依据", "规范", "标准", "政策", "批复", "规划", "文件"),
    "定量陈述": ("规模", "指标", "面积", "投资", "估算", "取值", "数量",
                 "人数", "负荷", "造价", "工期", "参数"),
    "分项罗列": ("方案", "内容", "构成", "分项", "清单", "措施"),
    "结论判断": ("结论", "建议", "可行"),
}


def _pick_slot(item, units):
    """把必写项挂到对得上的写作单元。挂不上就**不硬挂**。

    第一版挂不上时一律塞进第一行，结果技术方案章的五条必写项全堆在
    「设计总说明」上——那不是计划，是把问题藏起来。挂不上的正确处置是
    如实说它跨单元，让人自己决定放哪。
    """
    for i, u in enumerate(units):
        lab = str(u.get("label") or "")
        if lab and (lab[:4] in item or any(w in lab for w in item[:6] if len(w) > 1)):
            return i
    for i, u in enumerate(units):
        for kw in _AFFINITY.get(str(u.get("hint") or "").split()[0], ()):
            if kw in item:
                return i
    return None


MAX_ROWS = 22


def _rollup(subs):
    """把下级小节卷到一个**能排成表**的层级上。

    设计方案章有四级小节，摊平了 89 行。取最粗的那一层（建筑设计 / 结构设计 /
    给排水设计…），把它下面的孙节并进来——写作单元就落回十来个，
    每个对应一次可交付的写作、一次可核对的事实闭合。

    分组逻辑与语料库切 chunk 用的是**同一个函数**，不是两份相似的代码：
    存的单元、检索的单元、写的单元必须是同一个，否则「参照这一节」
    和「写这一节」指的就不是一回事了。
    """
    import corpus as C
    groups = C.rollup_subs(subs)
    if not groups:
        return None
    rows = []
    for grp in groups:
        mix = {}
        for s in grp:
            for m in (s.get("mix") or []):
                k, _, n = m.rpartition(" ")
                mix[k] = mix.get(k, 0) + int(n or 0)
        rows.append({
            "label": grp[0]["title"],
            "paras": sum(s["paras"] for s in grp),
            "chars": sum(s["chars"] for s in grp),
            "hint": "、".join(f"{k} {v}" for k, v in
                              sorted(mix.items(), key=lambda x: -x[1])[:3]),
            "sub_titles": [s["title"] for s in grp[1:]][:8],
        })
    return rows


def _units(shape):
    """写作单元：优先用历史文档的**下级小节**，退到段落功能游程。

    第一版按自然段做计划，设计方案章排出 439 行——没人能执行这样一张表，
    实际结果是整张表被跳过。真正能执行的粒度是「建筑设计 / 结构设计 /
    给排水设计」这一级：它既对应一次可交付的写作，也对应一次可核对的事实闭合。
    """
    subs = (shape or {}).get("subs") or []
    if len(subs) >= 3:
        rolled = _rollup(subs)
        if rolled:
            return rolled, "小节"
    slots = (shape or {}).get("slots") or _DEFAULT_SLOTS
    if len(slots) > MAX_ROWS:                 # 没有小节又碎成几百段：只能给配比
        return None, None
    idx, rows = 1, []
    for s in slots:
        rows.append({
            "label": (f"第 {idx} 段" if s["paras"] == 1
                      else f"第 {idx}–{idx + s['paras'] - 1} 段"),
            "paras": s["paras"], "chars": s["chars"], "hint": s["func"]})
        idx += s["paras"]
    return rows, "段"


def paragraph_plan(shape, spec, budget_chars=None):
    """把「形」和「完整性清单」合成一张可逐段执行的表。"""
    units, gran = _units(shape)
    sec = (spec or {}).get("section") or {}
    items = list(sec.get("covers") or []) + [
        str(x).strip().splitlines()[0] for x in (sec.get("must_state") or [])]

    if units is None:                          # 退化：只给配比与总量，不排表
        return {"rows": None, "shape": shape, "items": items,
                "total": budget_chars or (shape or {}).get("char_count"),
                "from_history": True, "gran": None, "unplaced": items}

    hist_total = sum(u["chars"] for u in units) or 1
    target = budget_chars or (shape or {}).get("char_count") or hist_total
    scale = target / hist_total
    for u in units:
        u["target"] = max(80, int(round(u["chars"] * scale)))
        u["carry"] = []
    spread = []
    for it in items:
        i = _pick_slot(it, units)
        (units[i]["carry"] if i is not None else spread).append(it)

    return {"rows": units, "total": sum(u["target"] for u in units),
            "para_total": sum(u["paras"] for u in units), "items": items,
            "unplaced": spread, "gran": gran,
            "from_history": bool((shape or {}).get("subs") or (shape or {}).get("slots"))}


def render_plan(plan, sec_key):
    L = ["─" * 74, "四、逐段写作计划（形与篇幅来自历史，完整性来自图谱）", "─" * 74]
    if plan["rows"] is None:
        sh = plan["shape"] or {}
        L.append("历史样本这一章没有下级小节，且段落过碎，排不出可执行的表。")
        L.append(f"只给到量级：约 {sh.get('char_count')} 字 / {sh.get('para_count')} 段，"
                 f"成分配比 {sh.get('mix')}。")
        L.append("按图谱的必写项自行分节，每节写完即核——不要照着历史的段数走。")
        L.append(f"必写项：{plan['items']}")
        return "\n".join(L)
    if not plan["from_history"]:
        L.append("⚠ 没有可比历史样本，下面用的是通用段型。篇幅按 outline 的权重再调。")
    L.append(f"共 {len(plan['rows'])} 个写作单元（按{plan['gran']}），"
             f"合计约 {plan['total']} 字 / {plan['para_total']} 段")
    L.append("")
    L.append(f"{'写作单元':<26}{'段':<4}{'目标字数':<8}承载内容 / 成分")
    for r in plan["rows"]:
        carry = "；".join(r["carry"]) or r["hint"]
        lab = r["label"][:24]
        pad = 26 - sum(2 if ord(c) > 127 else 1 for c in lab)
        L.append(f"{lab}{' ' * max(pad, 1)}{r['paras']:<4}{r['target']:<8}{carry}")
        if r.get("sub_titles"):
            L.append(f"{' ' * 26}└ 下含：{'、'.join(r['sub_titles'])}")
    L.append("")
    if plan["unplaced"]:
        L.append("本章必写但跨单元（挂不到某一节上，写的时候自己认领，"
                 "全章写完逐条核销）：")
        for it in plan["unplaced"]:
            L.append(f"  □ {it}")
        L.append("  一条都不许剩。剩下的就是这一章漏写的法定内容。")
        L.append("")
    L.append("【怎么执行这张表】")
    L.append("  · **一段一交**。写完一段就停，核完再写下一段。")
    L.append("    整章写完再核，返工的是整章；而且成稿的外观会让人只改句子不补事实。")
    L.append("  · 每段写完核三件事：承载内容写到了没有；字数在目标 ±20% 内；")
    L.append("    段内每个数都是 {{节点名}} 而不是字面值。")
    L.append("  · **段数可以不等于历史。** 图谱里本章还有没写到的必写项就加段；")
    L.append("    历史有而本项目没有对应事实的，删段——不许为了凑段数注水。")
    L.append("  · 字数是目标不是配额。差得远说明事实不够，回去补事实，不要用形容词填。")
    return "\n".join(L)


def corpus_block(corpus_dir, sec_key, want):
    """返回 (展示文本, 最佳样本的 shape)。shape 用于下一节的逐段计划。"""
    if not corpus_dir:
        return None, None
    import corpus as C
    entries = C.load_corpus(corpus_dir)
    if not entries:
        return ("（语料库为空。没有参照不影响正确性，参照错了才影响——"
                "按上面的提示直接起草。）", None)
    hits = C.rank_entries(entries, sec_key, want)
    txt = C.render_retrieve(sec_key, hits, want, show_skeleton=False)
    shape = None
    if hits:
        sec = hits[0][1]["sections"][sec_key]
        shape = sec.get("shape") or C.distill(sec)
    return txt, shape


def logic_block(corpus_dir, sec_key, want):
    """从历史条目的图谱里取**推演逻辑**，脱值后作为模板给出。

    这是语料库里第二样可复用的东西，而且比「形」更值钱：
    同类报告这一章用了哪些推演、每个推演的方法与保证、输入是哪几类、
    口径怎么取——这些跨项目稳定。**变的是值，不变的是逻辑。**

    所以这里只发方法、保证、输入的角色与来源、分步、口径假设，
    **一个数都不发**。历史项目的 315 人、18319 ㎡ 与新项目无关，
    「用水量 = 定额 × 人数 × 日变化系数，人数口径要与规模测算一致」有关。
    """
    if not corpus_dir:
        return None
    import corpus as C
    best, bestscore = None, -1
    for e in C.load_corpus(corpus_dir):
        if sec_key not in (e.get("sections") or {}):
            continue
        s = C.rank_entries([e], sec_key, want)
        if s and s[0][0] > bestscore:
            best, bestscore = e, s[0][0]
    if not best:
        return None
    gp = Path(best.get("_dir", "")) / "graph.yaml"
    if not gp.exists():
        return ("该条目没有配套图谱（graph.yaml），只能参照形，参照不到推演逻辑。\n"
                "补图谱是提升语料价值最大的一步——没有它，"
                "「这个数怎么来的」这类知识留不下来。")
    g = yaml.safe_load(gp.read_text(encoding="utf-8")) or {}
    prefixes = _SECTION_PREFIX.get(sec_key)
    rules = []
    for r in (g.get("rules") or []):
        tgt = str(r.get("target") or "")
        if prefixes and not tgt.startswith(tuple(prefixes)):
            continue
        rules.append(r)
    if not rules:
        return None

    L = [f"同类报告这一章用到的推演（{len(rules)} 条，已脱值——只有逻辑，没有数）：", ""]
    for r in rules:
        st = r.get("chain_status", "?")
        mark = {"closed": "✓", "closed_with_placeholder": "◐"}.get(st, "✗")
        L.append(f"{mark} {r.get('target')}　[{r.get('method', '?')}]")
        if r.get("formula"):
            L.append(f"    式：{r['formula']}")
        if r.get("alternatives"):
            L.append(f"    候选：{r['alternatives']}　维度：{r.get('criteria')}")
        if r.get("warrant"):
            L.append(f"    凭什么：{r['warrant']}")
        for k, v in (r.get("inputs") or {}).items():
            L.append(f"      ← {k}（{(v or {}).get('role', '')}／"
                     f"{(v or {}).get('source', '')}）")
        for s in (r.get("steps") or [])[:6]:
            L.append(f"    · {s}")
        for a in (r.get("assumptions") or []):
            L.append(f"    ⚠ 口径：{a.get('text')}　换成「"
                     f"{'／'.join(a.get('alternatives') or ['—'])}」：{a.get('impact')}")
        if st == "broken":
            rsn = str(r.get("broken_reason", "")).strip().splitlines()
            L.append(f"    ✗ 那份报告这里就没说清楚：{rsn[0] if rsn else ''}")
            L.append("      **本项目不要重复**——把缺的输入列进追料清单")
        L.append("")
    L.append("用法：逻辑照搬，值一个都不搬。历史项目的数与本项目无关，")
    L.append("「用水量 = 定额 × 人数 × 日变化系数、人数口径须与规模测算一致」才是要带走的。")
    return "\n".join(L)


# 章节 → 节点前缀。用于从历史图谱里挑出属于这一章的推演。
_SECTION_PREFIX = {
    "scale": ["scale.", "program."],
    "technical": ["arch.", "stru.", "water.", "load.", "elec.", "hvac.",
                  "fire.", "storm.", "site.", "geo."],
    "investment": ["cost.", "funding."],
    "energy_env": ["energy.", "env."],
    "site": ["site.", "geo."],
}


def _budget(proj, sec_key):
    """本章字数预算：总预算 × 该章篇幅权重。没设就返回 None，走历史篇幅。"""
    ty = (proj.get("typography") or {}) if isinstance(proj.get("typography"), dict) else {}
    total = ty.get("total_chars") or (proj.get("project") or {}).get("total_chars")
    if not total:
        return None
    weights = {}
    for sec in (proj.get("sections") or []):
        if isinstance(sec, dict) and sec.get("length_weight"):
            weights[sec.get("id")] = float(sec["length_weight"])
    if sec_key not in weights:
        return None
    s = sum(weights.values()) or 1
    return int(total * weights[sec_key] / s)


def build(proj, sec_key, corpus_dir=None, subtype=None):
    core, argu, deriv, norms = load_all()
    import claim_derive as CD

    L = ["=" * 74, f"起草简报 · {sec_key}", "=" * 74, "",
         "顺序是硬的：**先把事实定下来，再考虑怎么表述。**",
         "反过来做——先照着同类报告的写法起个稿再往里填数——是套模板的标准路径。", ""]

    # ---- 一、事实：本章图谱切片与起草前置 ----------------------------------
    spec = CD.section_prompt(sec_key)
    L.append("─" * 74)
    L.append("一、本章要说的事实（图谱切片）")
    L.append("─" * 74)
    L.append(CD.render_prompt(sec_key, spec))
    L.append("")

    # ---- 二、检索：这一章的法定内容项触发了什么 ----------------------------
    tasks, scoped = research_for_section(proj, core, sec_key, spec)
    L.append("─" * 74)
    L.append("二、还要查什么（本章法定内容项触发）")
    L.append("─" * 74)
    if scoped == "章节提示":
        L.append("（骨架里这一章还没绑法定内容项，按章节提示的 covers 裁剪。）")
    elif scoped is None:
        L.append("⚠ 这一章找不到法定内容项，无法按章裁剪，下面是整篇的检索任务。")
    if not tasks:
        L.append("这一章没有触发外部检索——所需事实全部来自客户素材与推导。")
    for t in tasks:
        L.append(f"· {t['id']}　{t['cn']}　（由「{'、'.join(t['triggered_by'])}」触发）")
        if t.get("blocked"):
            L.append(f"    ✗ 检索式不成立：{t['blocked']}")
        for q in (t.get("queries") or [])[:4]:
            L.append(f"    查：{q}")
        if t.get("must_confirm"):
            L.append("    ⚠ 查回来的每一句都以客户的名义在说——**必须先交客户核对**，"
                     "核对前不得写进正文")
        if t.get("trap"):
            L.append(f"    坑：{str(t['trap']).strip().splitlines()[0]}")
        if t.get("if_not_found"):
            L.append(f"    查不到：{t['if_not_found']}")
    L.append("")
    L.append("检索结果不直接采信：候选先过 fit_rank.py 的硬否决与六维打分，")
    L.append("交客户勾选后才落图，证据等级按实际来源记，**不许记成 E1_given**。")
    L.append("")

    # ---- 三、借鉴：同类报告的形 -------------------------------------------
    want = _facets(proj)
    if subtype:
        want["subtype"] = subtype
    L.append("─" * 74)
    L.append("三、这一章该长什么样（同类报告的形，非原文）")
    L.append("─" * 74)
    blk, shape = corpus_block(corpus_dir, sec_key, want)
    if blk is None:
        L.append("未指定语料库（--corpus）。没有同类参照时按上面两节直接起草，")
        L.append("篇幅按 outline 的篇幅权重分配即可。")
    else:
        L.append(blk)
    L.append("")

    # ---- 三·二、推演逻辑：语料库里比「形」更值钱的一半 --------------------
    lg = logic_block(corpus_dir, sec_key, want)
    if lg:
        L.append("─" * 74)
        L.append("三·二、这一章的推演该怎么做（同类报告的逻辑，已脱值）")
        L.append("─" * 74)
        L.append(lg)
        L.append("")

    # ---- 四、逐段计划 ------------------------------------------------------
    L.append(render_plan(paragraph_plan(shape, spec, _budget(proj, sec_key)), sec_key))
    L.append("")

    L.append("=" * 74)
    L.append("动笔前最后确认三条：")
    L.append("  1 本章 requires 的节点已全部满足，图上没有 error（C18）。")
    L.append("  2 第二节里 must_confirm 的检索结果，客户已经核对过。")
    L.append("  3 第三节只用来定形。任何一个数、一条政策、一个规范编号，")
    L.append("    都不得来自第三节——它们只能来自图谱（C19a / C19b）。")
    return "\n".join(L)


@guard
def main(argv):
    ap = argparse.ArgumentParser(description="逐章起草简报：查 + 借鉴 + 图谱切片")
    ap.add_argument("project")
    ap.add_argument("--section", required=True)
    ap.add_argument("--corpus", help="历史报告语料库目录（可选）")
    ap.add_argument("--subtype", help="本项目子类，用于语料库适配性排序")
    a = ap.parse_args(argv[1:])
    proj = yaml.safe_load(Path(a.project).read_text(encoding="utf-8")) or {}
    print(build(proj, a.section, a.corpus, a.subtype))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
