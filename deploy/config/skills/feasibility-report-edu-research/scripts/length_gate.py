#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
篇幅门禁：每章字数是**输入**，不达标不出稿。

以前篇幅核对只是提示。提示的问题是没有强制力——某章被一笔带过，
报告照样出得来，然后在评审那里被指出来。所以改成门禁：
声明了字数要求的章，达不到就不放行。

但门禁只解决「不放行」，不解决「怎么补」。**差 800 字时正确的动作
不是「再写点」，是把图上还没写进这一章的东西找出来。**
所以本脚本的主要产出不是判定，是缺口清单：

    本章还有哪几个节点没写进正文
    本章的必写项还有哪几条没核销
    本章触发的检索还有哪几项没做
    本章的取值点还有哪几个空着

每条给一个字数估算——估算常数是从一份真实报告量出来的（见 YIELD），
不是拍的。清单加起来仍然不够，说明目标定高了，出口是请客户书面
下调目标，**不是注水**。

用法：
  length_gate.py project.yaml content.yaml [--outline outline.yaml] [--pages N]
退出码：0 全部达标 / 1 有章未达标 / 2 有章超上限
"""

import re
import sys
import argparse
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assets import guard, load_all  # noqa: E402
from render import _cjk_len  # noqa: E402

# 从一份 5.4 万字的真实高校可研量得的段均字数。用它把「还缺什么」
# 换算成「大约能补多少字」——量级参照，不是精确预测。
YIELD = {
    "node": 83,          # 一条定量陈述（一个节点写进正文）段均 83 字
    "norm": 53,          # 一条规范/政策依据引述段均 53 字
    "must_state": 200,   # 一条必写项展开通常是两三段
    "research": 260,     # 一项检索落地后写成的段落
    "probe": 83,         # 一个取值点落地 = 一条定量陈述
    "argue": 300,        # 一条论点展开成的定性论证段
}

# 论证型章节（风险、卫生防疫、招投标、社会效益、结论）不产出数值，
# 缺口清单里前五类几乎都为空，于是门禁只会说「补不上，请客户下调目标」——
# 其实是估算漏了这一类。这类章的缺口要按未展开的论点数估。

TOL_LO = 0.9             # 硬门禁：低于目标的 90% 不放行
TOL_WARN = 0.97          # 软提示：逼近下限，提醒但不拦
TOL_HI = 1.6             # 超上限：目标的 160%

# 全篇总量的门禁比下限更严：逐章都擦着 90% 过，全篇就只有 90%。
TOTAL_LO = 0.98

# 分散度：某章相对语料库配比的偏离超过这个区间就提示。
# 单章达标不等于配比合理——一章写成 4 倍、另一章 0.6 倍，
# 总量可能正好，读者却会觉得这份报告没有主次。
SPREAD_LO, SPREAD_HI = 0.6, 1.8

# 字数口径。三处必须用同一把尺子：语料库入库、篇幅门禁、交付前自查。
# 口径不统一时最典型的事故是「我们算达标，客户用 Word 一数不达标」。
COUNT_MODES = {
    "nows": "不计空格字符数（等同 Word「字符数(不计空格)」，与语料库入库口径一致）",
    "han":  "纯汉字数（剔除标点、数字与拉丁字母，最严）",
    "cjk":  "折算字数（中文按字计，英文数字每 2 字符折 1 字）",
}
DEFAULT_COUNT_MODE = "nows"


def count_chars(text, mode=DEFAULT_COUNT_MODE):
    """按声明的口径数字。口径必须随判定结果一起输出，不能只报数字。"""
    if mode == "han":
        return len(re.findall(r"[\u4e00-\u9fff]", text))
    if mode == "cjk":
        return _cjk_len(text)
    return len(re.sub(r"\s", "", text))


def corpus_profile(entry_dir):
    """从语料库条目的索引里取逐章篇幅配比。

    这是「形」的一部分，本来就该复用：同垂类历史报告各章实际写了多少字，
    比大纲里那套全垂类通用的权重贴切得多。返回 {section_key: chars}。
    只取字数与占比，**不取任何值**——与语料库的其他用法同一条边界。
    """
    ix = Path(entry_dir) / "index.yaml"
    if not ix.exists():
        return {}
    try:
        doc = yaml.safe_load(ix.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    prof = {}
    for ck in doc.get("chunks") or []:
        k = ck.get("section")
        if k:
            prof[k] = prof.get(k, 0) + int(ck.get("chars") or 0)
    return prof


def targets(proj, outline_path=None, total_pages=None, counts=None,
            corpus_dir=None, sec_key=None):
    """每章目标字数，四个来源按优先级取。

    客户明确给的分章字数优先级最高——这是**客户的输入**，
    不是我们算出来的建议值，不该被权重覆盖掉。
    其次是同垂类语料库的实测配比；最后才是大纲权重折算。
    """
    out, src = {}, {}
    for sec in (proj.get("sections") or []):
        if isinstance(sec, dict) and sec.get("length_target"):
            out[sec["id"]] = int(sec["length_target"])
            src[sec["id"]] = "客户指定"
    # 第二优先：同垂类语料库的实测配比
    prof = corpus_profile(corpus_dir) if corpus_dir else {}
    if prof and counts:
        keyof = sec_key or (lambda cid: cid)
        psum = sum(prof.values()) or 1
        budget = (total_pages * 800) if total_pages else sum(prof.values())
        for cid in counts:
            if cid in out:
                continue
            k = keyof(cid)
            if k in prof:
                out[cid] = int(budget * prof[k] / psum)
                src[cid] = "语料库配比"

    weights = {}
    if outline_path and Path(outline_path).exists():
        try:
            doc = yaml.safe_load(Path(outline_path).read_text(encoding="utf-8")) or {}
            for sec in doc.get("sections") or []:
                if isinstance(sec, dict) and sec.get("weight") is not None:
                    weights[sec["id"]] = float(sec["weight"])
        except Exception:
            weights = {}
    if weights and counts:
        budget = (total_pages * 800) if total_pages else sum(counts.values())
        wsum = sum(weights.get(c, 1.0) for c in counts) or 1
        for cid in counts:
            if cid not in out:
                out[cid] = int(budget * weights.get(cid, 1.0) / wsum)
                src[cid] = "按权重折算"
    return out, src


def _body_text(sec):
    """把一章的正文块拼成文本。只算 para/heading——表格与插图不计入字数，
    否则「贴一张大表」就能把篇幅门禁蒙过去。"""
    out = []
    for blk in (sec.get("blocks") or []):
        if isinstance(blk, dict) and blk.get("type") in ("para", "heading"):
            out.append(str(blk.get("text") or ""))
    if not out:                                   # 兼容扁平写法
        b = sec.get("body") or sec.get("text") or ""
        out = b if isinstance(b, list) else [str(b)]
    return "\n".join(out)


def chapter_counts(content, mode=DEFAULT_COUNT_MODE):
    counts = {}
    for sec in (content.get("sections") or []):
        if isinstance(sec, dict):
            counts[sec.get("id")] = count_chars(_body_text(sec), mode)
    return counts


def _section_of(proj, cid):
    for sec in (proj.get("sections") or []):
        if isinstance(sec, dict) and sec.get("id") == cid:
            return sec
    return {}


def _prompt_spec(cid, sec):
    """章号（CH3）对不上起草提示的 key（scale），**按法定内容项交集认亲**。

    第一版直接拿 CH3 去查 section-prompts，永远查不到，必写项那一类缺口
    于是一条都报不出来——门禁看着在跑，实际漏掉了最该报的一类。
    用 covers 交集匹配就没这个问题：两边的 covers 都来自同一本法定大纲。
    """
    try:
        import claim_derive as CD
        doc_key = None
        direct = CD.section_prompt(cid)
        if direct:
            return direct.get("section") or {}
        import yaml as _y
        from assets import REF
        doc = _y.safe_load((REF / "section-prompts.yaml").read_text(
            encoding="utf-8")) or {}
        mine = set(sec.get("covers") or [])
        best = 0
        for k, v in (doc.get("sections") or {}).items():
            ov = len(mine & set((v or {}).get("covers") or []))
            if ov > best:
                best, doc_key = ov, k
        return ((doc.get("sections") or {}).get(doc_key) or {}) if doc_key else {}
    except Exception:
        return {}


def _open_probes(proj):
    """本项目还空着的专业取值点。技术方案章的字数缺口主要来自这里。"""
    try:
        import claim_derive as CD
        dp = CD._load("discipline-probes.yaml")
        vd = CD._vertical_dir(proj, None)
        sub = yaml.safe_load((vd / "subtypes.yaml").read_text(
            encoding="utf-8")) if vd else {}
        hits, _s, _n = CD.recognize_subtypes(proj, sub, None)
        if not hits and sub:
            hits = {k: ["兜底取并集"] for k in (sub.get("subtypes") or {})}
        st = CD.probe_status(CD.collect_probes(dp, sub, hits), proj)
        return [p for p in st if p.get("status") == "missing"]
    except Exception:
        return []


def diagnose(proj, content, cid, core):
    """一章为什么短——把缺口换算成可补的具体项。

    这是本脚本的重点。判定「未达标」谁都会做，难的是让「未达标」
    可执行：不给清单，补字数就只剩下**把句子写长**这一条路。
    """
    sec = _section_of(proj, cid)
    body = ""
    for s in (content.get("sections") or []):
        if isinstance(s, dict) and s.get("id") == cid:
            body = _body_text(s)
    gaps = []

    # ① 本章该写、图上有、正文没引用的节点
    owned = list(sec.get("provides") or []) + list(sec.get("requires") or [])
    nodes = proj.get("nodes") or {}
    missing_nodes = [n for n in owned
                     if n in nodes and f"{{{{{n}}}}}" not in body]
    if missing_nodes:
        gaps.append(("图上已有但本章正文没引用的节点", missing_nodes,
                     len(missing_nodes) * YIELD["node"],
                     "这些数已经确认过了，写进去不需要再问任何人——**先补这一类**"))

    # ② 本章空着的节点（写不进去，因为还没有值）
    empty = [n for n in owned
             if n in nodes and nodes[n].get("value") in (None, "", "UNKNOWN")]
    if empty:
        gaps.append(("本章依赖但仍为空的节点", empty,
                     len(empty) * YIELD["node"],
                     "这些要先走来源路由拿到值（ASK/SEARCH/COMPUTE），才能写"))

    # ③ 必写项未核销
    spec = _prompt_spec(cid, sec)
    unmet = [x for x in (spec.get("must_state") or [])
             if not any(k in body for k in str(x)[:6] if len(k.strip()) > 1)]
    if unmet:
        gaps.append(("本章必写项尚未在正文出现", [str(x).splitlines()[0] for x in unmet],
                     len(unmet) * YIELD["must_state"],
                     "法定内容，不是可选项。补不上就是这一章漏写"))

    # ④ 本章触发但未做的检索
    try:
        import intake_gen as IG
        covers = set(sec.get("covers") or []) or set(spec.get("covers") or [])
        tasks = [t for t in IG.research_tasks(proj, core)
                 if set(t.get("triggered_by") or []) & covers]
    except Exception:
        tasks = []
    if tasks:
        gaps.append(("本章触发但尚未完成的检索", [t["id"] for t in tasks],
                     len(tasks) * YIELD["research"],
                     "查回来的要先交客户核对才能写进正文"))

    # ⑤ 空着的取值点（技术方案章的主要缺口来源）
    probes = _open_probes(proj) if "技术方案" in " ".join(
        list(sec.get("covers") or []) + list(spec.get("covers") or [])) else []
    if probes:
        gaps.append(("尚未落地的专业取值点", [p.get("id") for p in probes][:20],
                     len(probes) * YIELD["probe"],
                     "取值点不落地，这一章只能写通用条款——字数凑够了也是废话"))

    return gaps


def gate(proj, content, core, outline_path=None, total_pages=None,
         corpus_dir=None, sec_key=None, mode=DEFAULT_COUNT_MODE):
    counts = chapter_counts(content, mode)
    tgt, src = targets(proj, outline_path, total_pages, counts, corpus_dir, sec_key)
    rows = []
    for cid, n in counts.items():
        t = tgt.get(cid)
        if not t:
            rows.append((cid, n, None, "未设目标", None, []))
            continue
        if n < t * TOL_LO:
            rows.append((cid, n, t, "未达标", src.get(cid),
                         diagnose(proj, content, cid, core)))
        elif n < t * TOL_WARN:
            rows.append((cid, n, t, "逼近下限", src.get(cid), []))
        elif n > t * TOL_HI:
            rows.append((cid, n, t, "超上限", src.get(cid), []))
        else:
            rows.append((cid, n, t, "达标", src.get(cid), []))
    return rows


def total_gate(rows, proj):
    """全篇总量单独判。

    逐章都卡在 90% 恰好通过，全篇就只有 90%——5 万字的要求会变成 4.5 万，
    而客户是按全篇总量提要求的。所以总量必须单独设一道，且比分章更严。
    """
    tot_target = proj.get("total_length_target")
    have = sum(r[1] for r in rows)
    if not tot_target:
        want = sum(r[2] for r in rows if r[2])
        return have, want, ("未设总量目标", None)
    ok = have >= tot_target * TOTAL_LO
    return have, int(tot_target), ("达标" if ok else "未达标",
                                   int(tot_target * TOTAL_LO) - have if not ok else 0)


def spread_check(rows, proj, corpus_dir, sec_key=None):
    """分散度：各章相对语料库配比的偏离。

    这一项不拦出稿，只提示。它回答的是「总量够了，但配比像不像一份可研」——
    结论章写成需求论证章的四倍，总量可能正好，评审读起来会觉得没有主次。
    """
    prof = corpus_profile(corpus_dir) if corpus_dir else {}
    if not prof:
        return []
    keyof = sec_key or (lambda cid: cid)
    psum = sum(prof.values()) or 1
    hsum = sum(r[1] for r in rows) or 1
    out = []
    for cid, n, _t, _v, _s, _g in rows:
        k = keyof(cid)
        if k not in prof:
            continue
        want = prof[k] / psum
        got = n / hsum
        ratio = got / want if want else 0
        if ratio < SPREAD_LO or ratio > SPREAD_HI:
            out.append((cid, round(got * 100, 1), round(want * 100, 1), round(ratio, 2)))
    return out


def render_gate(rows, mode=DEFAULT_COUNT_MODE, total=None, spread=None):
    L = ["=" * 74, "篇幅门禁", "=" * 74,
         f"字数口径：{mode}　{COUNT_MODES.get(mode, '')}",
         "（口径必须与语料库入库、与客户约定的一致；三处不一致时，"
         "最典型的事故是我们算达标、客户用 Word 一数不达标）", ""]
    short = [r for r in rows if r[3] == "未达标"]
    over = [r for r in rows if r[3] == "超上限"]
    for cid, n, t, verdict, s, _ in rows:
        if t is None:
            L.append(f"  {cid}: {n} 字　（未设目标，不判定）")
        else:
            mark = {"达标": "✓", "未达标": "✗", "超上限": "⚠",
                    "逼近下限": "·"}[verdict]
            L.append(f"  {mark} {cid}: {n} 字 / 目标 {t} 字"
                     f"（{s}）　{verdict}"
                     + (f"　差 {t - n} 字" if verdict == "未达标" else ""))
    L.append("")
    near = [r for r in rows if r[3] == "逼近下限"]
    if near:
        L.append(f"逼近下限（不拦，但提示）：{', '.join(r[0] for r in near)}")
        L.append("  逐章都擦着线过，全篇总量就只有目标的九成。见下方总量判定。")
        L.append("")
    if total:
        have, want, (v, short_by) = total
        if want:
            L.append(f"全篇总量：{have} 字 / 目标 {want} 字　{v}"
                     + (f"　还差 {short_by} 字" if short_by else ""))
        else:
            L.append(f"全篇总量：{have} 字（未设总量目标，仅统计）")
        L.append("")
    if spread:
        L.append("配比偏离（不拦出稿，提示主次是否失衡）：")
        for cid, got, want_, ratio in spread:
            L.append(f"  · {cid}: 占全篇 {got}%，语料库同章占 {want_}%，"
                     f"为 {ratio} 倍")
        L.append("  单章达标不等于配比合理。某章写成语料的四倍、另一章不足六成，"
                 "总量可能正好，")
        L.append("  但读者会觉得这份报告没有主次——这一项交由编制人判断，不自动处置。")
        L.append("")
    if not short and not over:
        blocked = bool(total and total[2][0] == "未达标")
        L.append("分章全部达标。" + ("全篇总量未达标，不放行——"
                 "逐章擦线通过、总量塌陷，正是这道总量门禁要拦的情形。"
                 if blocked else "可以出稿。"))
        return "\n".join(L)

    for cid, n, t, verdict, _, gaps in short:
        L.append("─" * 74)
        L.append(f"【{cid}】差 {t - n} 字。缺口在这里，不在文笔：")
        tot = 0
        if not gaps:
            L.append("  查不出结构性缺口——图上属于本章的东西都写进去了。")
            L.append("  这种情况说明**目标定高了**。出口是请客户书面下调本章目标，")
            L.append("  或从别的章移内容过来。不许注水。")
            continue
        for title, items, yield_, note in gaps:
            tot += yield_
            L.append(f"  · {title}（{len(items)} 项，约可补 {yield_} 字）")
            L.append(f"      {items[:8]}{' …' if len(items) > 8 else ''}")
            L.append(f"      {note}")
        L.append(f"  ── 清单合计约可补 {tot} 字，缺口 {t - n} 字："
                 + ("够补" if tot >= t - n else "**不够**"))
        if tot < t - n:
            L.append("     不够就说明目标定高了。请客户书面下调，不要用形容词填。")
    for cid, n, t, _, _, _ in over:
        L.append("─" * 74)
        L.append(f"【{cid}】超上限 {n - int(t * TOL_HI)} 字。"
                 f"先移附件：计算过程、台账、逐项清单进附件，正文留结论与关键中间量。")
        L.append("     **不删内容**——篇幅从不构成删除法定内容的理由。")
    L.append("")
    L.append("=" * 74)
    L.append("未达标的章不放行。补字数只有三条合法路径：补事实、补论证、")
    L.append("请客户书面下调目标。抄规范条文充数不在其列——评审一眼看得出，")
    L.append("而且会连带怀疑其余各章。")
    return "\n".join(L)


@guard
def main(argv):
    ap = argparse.ArgumentParser(description="篇幅门禁：不达标不出稿")
    ap.add_argument("project")
    ap.add_argument("content")
    ap.add_argument("--outline")
    ap.add_argument("--pages", type=int)
    ap.add_argument("--corpus", help="同垂类语料库条目目录；给了就用它的实测配比当默认目标")
    ap.add_argument("--count-mode", default=DEFAULT_COUNT_MODE, choices=list(COUNT_MODES),
                    help="字数口径，默认 nows（不计空格字符数，与语料库入库一致）")
    a = ap.parse_args(argv[1:])
    proj = yaml.safe_load(Path(a.project).read_text(encoding="utf-8")) or {}
    content = yaml.safe_load(Path(a.content).read_text(encoding="utf-8")) or {}
    core, _, _, _ = load_all()
    keyof = None
    smap = proj.get("corpus_section_map") or {}
    if smap:
        keyof = lambda cid: smap.get(cid, cid)          # noqa: E731
    rows = gate(proj, content, core, a.outline, a.pages,
                a.corpus, keyof, a.count_mode)
    tot = total_gate(rows, proj)
    spr = spread_check(rows, proj, a.corpus, keyof) if a.corpus else []
    print(render_gate(rows, a.count_mode, tot, spr))
    if any(r[3] == "未达标" for r in rows):
        return 1
    if tot[2][0] == "未达标":
        return 1
    if any(r[3] == "超上限" for r in rows):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
