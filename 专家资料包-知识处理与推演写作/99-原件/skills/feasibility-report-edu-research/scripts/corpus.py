#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史报告语料库：入库脱值、按章检索。

把做过的报告攒成库、写新报告时按章参照，这个思路补上了图谱补不了的东西：
该审批口认可的话术、章节的详略与铺陈、表格栏目、纯定性内容的写法。

但检索到的历史章节里混着两种东西——可复用的**形**和不可复用的**值**，
而它们在文本里长得一模一样。参照写作最常见的错误不是没参照，是参照得太完整：
上一份的面积、单方造价、地方配建比例、政策文号，顺手就带进了新报告，
带进来之后正文读起来毫无异常。

所以入库时**强制脱值**：数字、专名、地名、文号、规范编号全部替换成槽位标记。
提醒「注意不要照抄数字」不管用；把值物理抽掉，就带不过来。

入库还会跑一遍检查器，把该报告自己的缺陷标在库里。
历史库不是正确性的来源——我们验过的两份真实报告各缺 6–8 章法定内容。

用法：
  corpus.py ingest <report.docx> --graph project.yaml --meta meta.yaml -o corpus/<id>
  corpus.py retrieve <corpus_dir> --section 章节key [--vertical v] [--subtype s]
  corpus.py check <corpus_dir>/<id>          自检投影是否干净
"""

import re
import sys
import json
import argparse
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assets import AssetError, REF, guard  # noqa: E402

SLOT = re.compile(r"⟨[^⟩]{0,40}⟩")
# 章节号与列表序号不算"值"：一、1.1、（3）、第5章
STRUCTURAL_NUM = re.compile(
    r"^\s*(?:第\s*[0-9一二三四五六七八九十]+\s*[章节]|"
    r"[0-9]+(?:\.[0-9]+)*\s|[（(][0-9]+[）)]|[0-9]+[、.])")


# =============================================================================
# 脱敏投影
# =============================================================================

def build_projector(graph, meta):
    """按图谱与元数据构造投影规则。

    数值优先映射到节点名——参照的是「这里要写一个总建筑面积」，
    不是「这里写 18319」。对不上节点的降级为 ⟨数值⟩。
    """
    # 值 → 节点名的映射必须**只保留有区分度的值**。
    # 第一版直接建了个全量字典，结果在表格里原形毕露：
    # 冬季温度 18℃ 被标成 ⟨fire.roof_tank_volume⟩（消防水箱 18 m³）、
    # 噪声 50 dB 标成 ⟨storm.overflow_period⟩（雨水重现期 50 年）。
    # **标错的节点名比不标更有害**——参照者会当真，而它看起来完全正常。
    # 所以两条门槛：① 该值在图上唯一；② 值本身够特殊
    # （有小数位，或绝对值 ≥ 1000）。层数 12、温度 26、年限 50 这类小整数
    # 在一份报告里到处都是，映射必然撞号，降级成 ⟨数值⟩ 才是对的。
    hits = {}
    for nid, n in (graph.get("nodes") or {}).items():
        v = n.get("value")
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        distinctive = (not float(v).is_integer()) or abs(v) >= 1000
        if not distinctive:
            continue
        for form in {str(int(v)) if float(v).is_integer() else None, str(v), f"{v:,}"}:
            if form:
                hits.setdefault(form, set()).add(nid)
    val2node = {form: next(iter(ns)) for form, ns in hits.items() if len(ns) == 1}
    names = [x for x in (meta.get("names") or []) if x]
    places = [x for x in (meta.get("places") or []) if x]
    orgs = [x for x in (meta.get("orgs") or []) if x]
    return {"val2node": val2node,
            "names": sorted(names, key=len, reverse=True),
            "places": sorted(places, key=len, reverse=True),
            "orgs": sorted(orgs, key=len, reverse=True)}


DOC_NO = re.compile(r"[〔\[（(]\s*(19|20)\d{2}\s*[〕\]）)]\s*第?\s*\d+\s*号")
NORM_NO = re.compile(r"(?:GB\s?/?\s?T?\s?\d{4,5}(?:\s?[-—]\s?\d{2,4})?|"
                     r"JGJ\s?\d+(?:\s?[-—]\s?\d{2,4})?|"
                     r"建标\s?\d+(?:\s?[-—]\s?\d{2,4})?|"
                     r"CJJ\s?\d+|DBJ\s?[\d/\-]+)")
YEAR = re.compile(r"(19|20)\d{2}\s*年")
# 人名：真实入库时「岳劲峰教授」「葛冬冬、何斯迈、江波」整串漏了过去。
# 姓名本身无法用正则可靠识别，但**职称是可靠的锚点**——
# 中文报告里提到具体人几乎总是带职称。带职称的连同前面 2–4 字一起投影掉。
PERSON = re.compile(r"[\u4e00-\u9fa5]{2,4}(?=(?:教授|副教授|研究员|副研究员|"
                    r"讲师|博士|院士|主任|副主任|处长|校长|副校长|院长|副院长|"
                    r"总工|总经理|工程师|老师))")
# 顿号串起来的人名列表：「葛冬冬、何斯迈、江波、杨超林、林天逸等」
PERSON_LIST = re.compile(r"(?:[\u4e00-\u9fa5]{2,4}、){2,}[\u4e00-\u9fa5]{2,4}(?=等)")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def project(text, pj, is_cell=False):
    """把一段正文脱值。顺序要紧：先长后短，先专名后数字。

    is_cell=True 用于表格单元格：单元格不是段落，开头的「1.」是数值的一部分，
    不是列表序号。不区分的话，「1.5 ㎡/人」会被切成「1.」+「5」，
    投影出来是「1.⟨层高⟩」——比不投影还糟。
    """
    if not text:
        return text
    out = text
    for nm in pj["names"]:
        out = out.replace(nm, "⟨建设单位⟩")
    for pl in pj["places"]:
        out = out.replace(pl, "⟨项目所在地⟩")
    for og in pj["orgs"]:
        out = out.replace(og, "⟨内设机构⟩")
    out = PERSON_LIST.sub("⟨人员⟩", out)
    out = PERSON.sub("⟨人员⟩", out)
    out = DOC_NO.sub("⟨文号⟩", out)
    out = NORM_NO.sub("⟨规范编号⟩", out)
    out = YEAR.sub("⟨年份⟩", out)

    # 单位里的指数不是值：m3/d、m2 若被投影成 ⟨数值⟩，表头就成了乱码。
    out = UNIT_EXP.sub(lambda mo: {"2": "²", "3": "³"}[mo.group(1)], out)

    head = ""
    if not is_cell:
        m = STRUCTURAL_NUM.match(out)
        if m:                              # 章节号与序号保留，它们是结构不是值
            head, out = out[:m.end()], out[m.end():]

    def rep(mo):
        raw = mo.group(0)
        node = pj["val2node"].get(raw) or pj["val2node"].get(raw.replace(",", ""))
        return f"⟨{node}⟩" if node else "⟨数值⟩"
    return head + NUM.sub(rep, out)


SUSPECT_ORG = re.compile(r"[\u4e00-\u9fa5]{2,12}(?:研究中心|研究院|实验室|学院|"
                         r"研究所|工程中心|平台|公司|集团)")
UNIT_EXP = re.compile(r"(?<=[mM])([23])(?![0-9])")
# 「充分发挥研究中心」「借助研究中心这个平台」——正则从任意汉字往前贪，
# 报回一堆不是名字的候选。候选一多，人就不看了，噪声必须先滤掉：
# 专名里不出现虚词与动词性成分。
_NOT_A_NAME = ("的", "了", "及", "与", "和", "这个", "该", "作为", "充分",
               "依靠", "借助", "以此", "使", "在", "个", "等", "对", "把",
               "已", "将", "被", "由", "为", "其", "本", "此", "着", "又")


def leftover_numbers(text):
    """投影自检：骨架里不该再有阿拉伯数字（章节号与序号除外）。"""
    t = text
    m = STRUCTURAL_NUM.match(t)
    if m:
        t = t[m.end():]
    t = SLOT.sub("", t)
    return NUM.findall(t)


def leftover_names(text):
    """疑似漏投影的专名。

    真实入库时人名与内设机构名整串漏了过去——它们不含数字，
    数值自检完全看不见，而它们恰恰是「这份是谁的报告」最直接的痕迹。
    这里只报可疑项交人工确认，不自动替换：机构名里有一部分是通用说法。
    """
    t = SLOT.sub("", text)
    return sorted({c for c in SUSPECT_ORG.findall(t)
                   if not any(w in c for w in _NOT_A_NAME)})


# =============================================================================
# 入库
# =============================================================================

HEADING_MAX = 40
# 表体只留前若干行——参照的是「这张表放什么量」，不是整张台账
MAX_TABLE_ROWS = 12


def _heading_kind(p, t):
    """这一段是不是标题，以及凭什么判定的。

    切章是整条入库链上**最脆的一环**，而它的可靠性完全取决于源文档：
      · 有标题样式 → 可靠
      · 无样式（.doc 转来的常见）→ 只能靠编号 + 长度启发式，不可靠
    真实入库时踩过两次：第一次按「含关键词」切，一章吃进 439 段；
    第二次退到「够短就算标题」，正文里的短句照样被当成标题。
    所以现在**只认三种锚点**，并如实报告用的是哪一种。
    """
    style = str(getattr(getattr(p, "style", None), "name", "") or "")
    if "Heading" in style or "标题" in style:
        m = re.search(r"(\d)", style)
        return "style", int(m.group(1)) if m else 1
    if t.endswith(("。", "；", "：")):
        # 「3. 设漏电火灾报警系统。」——带编号但以句号收尾的是列举项不是标题。
        # 不排除它，设计方案章会切出 89 个"小节"，写作计划又变成没人能执行的长表。
        return None, None
    if re.match(r"^\s*第\s*[0-9一二三四五六七八九十]+\s*章", t):
        return "chapter_no", 1
    if re.match(r"^\s*[0-9]+(?:\.[0-9]+)*[\s、.]", t) and len(t) <= HEADING_MAX:
        lvl = t.strip().split()[0].count(".") + 2
        return "numbering", min(lvl, 4)
    return None, None


def _flat(t):
    """表格单元格里的换行会把 markdown 表拆散。合并成一行，保留可读性。"""
    return " ".join(str(t or "").split())


def _iter_blocks(doc):
    """按**正文顺序**遍历段落与表格。

    d.paragraphs 拿不到表格，而「表该怎么列」恰恰是语料库最有价值的一项——
    图谱能算出表里的数，算不出这张表该设哪几栏。
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, doc)
        elif isinstance(child, CT_Tbl):
            yield Table(child, doc)


def split_sections(docx_path, section_map):
    """按标题切章。section_map: {正则: 章节key}，正则**从段首匹配**。

    章节 key 用 section-prompts.yaml 的那套，切完即可与起草提示对齐。
    返回 (切片, 切章质量报告)。
    """
    import docx
    from docx.table import Table
    d = docx.Document(docx_path)
    pats = [(re.compile(k), v) for k, v in section_map.items()]
    cur, out = None, {}
    kinds, total = {}, 0
    for blk in _iter_blocks(d):
        if isinstance(blk, Table):
            if cur and blk.rows:
                # 只捕表头是不够的：设计参数大半在表格里（室内外计算参数、
                # 换气次数、负荷指标），正文里的数字反而多是规范限值。
                # 只存栏目，等于把这一章最实的内容漏掉了。
                # 表体一并捕，但**同样要过投影**——表格单元格是最容易漏脱值的地方。
                cols = [_flat(c.text) for c in blk.rows[0].cells]
                body = [[_flat(c.text) for c in r.cells]
                        for r in blk.rows[1:MAX_TABLE_ROWS + 1]]
                tb = {"cols": cols, "rows": len(blk.rows), "body": body,
                      "truncated": len(blk.rows) - 1 > MAX_TABLE_ROWS}
                out[cur]["tables"].append(tb)
                # 表要记在**当前小节**上。只记到章上的话，设计方案章那 11 张表
                # 会全部堆到第一个 chunk 里——室内外计算参数表跑到「设计总说明」，
                # 暖通那个 chunk 一张表都没有。捕了表体之后，这种错位就不是小事。
                if out[cur]["subs"]:
                    out[cur]["subs"][-1].setdefault("tables", []).append(tb)
            continue
        p = blk
        t = p.text.strip()
        if not t:
            continue
        total += 1
        kind, level = _heading_kind(p, t)
        hit = None
        if kind:
            # search 会命中正文里随口提到的关键词，所以只从段首匹配
            hit = next((v for rx, v in pats if rx.match(t)), None)
        if hit and hit not in out:          # 同一章只认第一次出现的标题
            cur = hit
            kinds[hit] = kind
            out[cur] = {"title": t, "paras": [], "tables": [], "subs": []}
            continue
        if cur and kind and not hit:
            # 章内的下级标题。设计方案章有 439 个自然段，按自然段做写作计划
            # 没人能执行；按「建筑设计 / 结构设计 / 给排水设计」这一级才能。
            out[cur]["subs"].append({"title": t, "level": level or 2, "paras": []})
            out[cur]["paras"].append(t)
            continue
        if cur:
            out[cur]["paras"].append(t)
            if out[cur]["subs"]:
                out[cur]["subs"][-1]["paras"].append(t)

    quality = {"total_paragraphs": total, "matched_sections": len(out),
               "anchor_kinds": kinds, "warnings": []}
    if not any(k == "style" for k in kinds.values()):
        quality["warnings"].append(
            "源文档没有标题样式（.doc 转换件常见），切章靠编号与长度启发式——"
            "结果须人工核对。可靠做法：在源文档里把章节标题设成标题样式后重新入库。")
    # 一章占比过高有两种成因，处置完全不同，不能混报：
    #   ① 没切开——后面的标题没被识别，整条尾巴都灌进了这一章
    #   ② 本来就长——设计方案章带各专业条文，四成段落是常态
    # 判据是**它是不是最后一个被切出来的章**：没切开的那一章必然一路吃到文末。
    order = list(out.keys())
    for idx, key in enumerate(order):
        share = len(out[key]["paras"]) / max(total, 1)
        if share <= 0.35:
            continue
        if idx == len(order) - 1:
            quality["warnings"].append(
                f"「{key}」吃进了 {share:.0%} 的段落，且是最后一个切出来的章——"
                f"后面的标题多半没被识别。核对 section_map 或补标题样式。")
        else:
            quality.setdefault("notes", []).append(
                f"「{key}」占 {share:.0%} 的段落，但其后仍有章被正确切出，"
                f"应属该章本身就长（设计方案章常见）。检索时按它的实际篇幅参照。")
    missing = [v for _, v in pats if v not in out]
    if missing:
        quality["warnings"].append(f"未匹配到的章节：{missing}")
    return out, quality


def defects_by_section(graph):
    """入库即体检。历史库不是正确性的来源——把它自己的毛病标出来。"""
    try:
        from assets import load_all
        import validators as V
        core, argu, deriv, norms = load_all()
        val = V.Validator(core, argu, deriv, graph, norms)
        findings = val.run()
    except Exception as e:                       # 体检失败不该挡住入库
        return {"_error": [f"缺陷体检未能完成：{e}"]}
    sec_ids = {s.get("id") for s in (graph.get("sections") or []) if isinstance(s, dict)}
    out = {}
    for f in findings:
        if f.severity == "info":
            continue
        key = next((sid for sid in sec_ids if sid and sid in str(f.subject)), "_global")
        out.setdefault(key, []).append(f"[{f.code}·{f.severity}] {f.subject}：{f.message}")
    return out


# =============================================================================
# 蒸馏 —— 把历史章节化成「提示词」，而不是留成「文本」
# =============================================================================
# 检索出来的骨架一旦进了起草上下文，模型就不再是「写」，而是「改」——
# 顺着已有句子往下续、把不合适的地方删掉。产出必然带着那份报告的骨相，
# 这就是套模板，脱不脱值都一样。
#
# 所以骨架**不进起草上下文**。进上下文的是从骨架里量出来的形：
# 段落功能的顺序、各占多少篇幅、表设了哪几栏、结论摆在哪。
# 这些约束足以让新报告「像这一类报告」，又不含一句可以顺手续写的原句。
# =============================================================================

_CONCLUSION = re.compile(r"(综上|因此|故此|由此可见|是必要的|是可行的|完全可行|"
                         r"符合.{0,6}要求|建议.{0,4}实施)")
_LIST_HEAD = re.compile(r"^\s*(?:[（(][0-9一二三四五六七八九十]+[）)]|"
                        r"[0-9]+[、.]|[一二三四五六七八九十][、.]|"
                        r"一是|二是|三是|其[一二三四])")
_BASIS = re.compile(r"(⟨文号⟩|⟨规范编号⟩|《)")


def _para_function(t):
    """给一段正文贴功能标签——只留标签，不留原句。"""
    if len(t) <= 90 and _CONCLUSION.search(t):
        return "结论判断"
    if _BASIS.search(t):
        return "依据引述"
    if SLOT.search(t):
        return "定量陈述"
    if _LIST_HEAD.match(t):
        return "分项罗列"
    return "定性说明"


def _runs(seq, lens=None):
    """游程压缩：['定性','定性','定量'] → [{func,paras,chars}...]。

    带上字数是为了下一步能做**段落级篇幅计划**——
    「这一章写 3000 字」没法执行，「这一段写 180 字」才能执行。
    """
    lens = lens or [0] * len(seq)
    out = []
    for x, n in zip(seq, lens):
        if out and out[-1]["func"] == x:
            out[-1]["paras"] += 1
            out[-1]["chars"] += n
        else:
            out.append({"func": x, "paras": 1, "chars": n})
    return out


def distill(sec):
    """从脱值骨架量出「形」。返回的东西里没有一句可续写的原文。"""
    paras = sec.get("paragraphs") or []
    funcs = [_para_function(t) for t in paras]
    lens = [len(t) for t in paras] or [0]
    tally = {}
    for f in funcs:
        tally[f] = tally.get(f, 0) + 1
    total = sum(lens) or 1
    slots = _runs(funcs, lens)
    subs = []
    for sb in (sec.get("subs") or []):
        sp = sb.get("paragraphs") or []
        sf = [_para_function(t) for t in sp]
        sl = [len(t) for t in sp]
        st = {}
        for f in sf:
            st[f] = st.get(f, 0) + 1
        subs.append({
            "title": sb.get("title"), "level": sb.get("level", 2),
            "paras": len(sp), "chars": sum(sl),
            "mix": [f"{k} {v}" for k, v in sorted(st.items(), key=lambda x: -x[1])][:3],
        })
    return {
        "para_count": len(paras),
        "char_count": sec.get("char_count", total),
        "slots": slots,
        "subs": subs,
        "flow": [f"{s['func']}×{s['paras']}" for s in slots],
        "mix": {k: f"{v / max(len(funcs), 1):.0%}" for k, v in
                sorted(tally.items(), key=lambda x: -x[1])},
        "para_len": {"mean": int(sum(lens) / len(lens)), "max": max(lens)},
        "ends_with": funcs[-1] if funcs else None,
        "tables": sec.get("tables") or [],
    }


# =============================================================================
# 语义 chunk —— 存储、检索、图谱锚定三者用同一个粒度
# =============================================================================
# 一开始按「章」存，一份 MD 一万四千字，检索出来的东西没法用：
# 写给排水那一节，拿到的是整个设计方案章。
#
# 正确的粒度是**写作单元**：一次可交付的写作、一次可核对的事实闭合。
# 这个粒度在做逐段计划时已经量出来了——设计方案章的 89 个小节卷起来
# 正好是建筑/结构/给排水/强电/弱电/暖通 6+1 个。用同一套逻辑切 chunk，
# 于是「存的单元 = 检索的单元 = 写的单元 = 图谱挂的单元」，四者对齐。
#
# chunk_id 用 `章节key-序号` 而不是内容哈希：哈希会在改一个字之后变，
# 而图上挂着的引用不该因为改了个错别字就断掉。
# =============================================================================

MAX_CHUNKS_PER_SECTION = 22


def rollup_subs(subs):
    """把下级小节卷到一个既不碎、也不粗的层级上。返回 None 表示卷不出来。"""
    levels = sorted({s.get("level", 2) for s in subs})
    for lv in levels:
        heads = [i for i, s in enumerate(subs) if s.get("level", 2) == lv]
        if not (3 <= len(heads) <= MAX_CHUNKS_PER_SECTION):
            continue
        groups = []
        for j, i in enumerate(heads):
            end = heads[j + 1] if j + 1 < len(heads) else len(subs)
            groups.append(subs[i:end])
        return groups
    return None


def chunk_section(key, sec):
    """把一章切成语义 chunk。切不出来就整章一个 chunk——**不硬切**。"""
    subs = sec.get("subs") or []
    groups = rollup_subs(subs) if len(subs) >= 3 else None
    if not groups:
        return [{"id": f"{key}-01", "title": sec.get("title") or key,
                 "paragraphs": sec.get("paragraphs") or [],
                 "tables": sec.get("tables") or [], "whole_section": True}]
    out = []
    for n, grp in enumerate(groups, 1):
        paras = []
        for sb in grp:
            paras.append(sb["title"])
            paras += sb.get("paragraphs") or []
        out.append({"id": f"{key}-{n:02d}", "title": grp[0]["title"],
                    "paragraphs": paras,
                    "sub_titles": [s["title"] for s in grp[1:]],
                    "whole_section": False})
    # 表跟着小节走。挂不到小节的（出现在第一个小节之前）才落到首个 chunk
    placed = 0
    for n, grp in enumerate(groups):
        tbs = [t for sb in grp for t in (sb.get("tables") or [])]
        if tbs:
            out[n]["tables"] = tbs
            placed += len(tbs)
    orphan = (sec.get("tables") or [])[:max(len(sec.get("tables") or []) - placed, 0)]
    if orphan:
        out[0].setdefault("tables", [])
        out[0]["tables"] = orphan + out[0]["tables"]
        out[0]["tables_are_section_level"] = True
    return out


def ingest(docx_path, graph, meta, out_dir):
    pj = build_projector(graph, meta)
    secmap = meta.get("section_map") or {}
    if not secmap:
        raise AssetError(
            "meta.yaml 缺 section_map —— 不知道按什么标题切章。\n"
            "  写法：{正则: 章节key}，章节key 用 section-prompts.yaml 里的那套。")
    raw, quality = split_sections(docx_path, secmap)
    dfx = defects_by_section(graph)

    entry = {"id": meta.get("id"), "fit_meta": meta.get("fit_meta") or {}, "sections": {}}
    dirty, suspect, chapters = [], [], {}
    for key, blk in raw.items():
        paras = [project(t, pj) for t in blk["paras"]]
        for t in paras:
            dirty += leftover_numbers(t)
            suspect += leftover_names(t)
        tables = []
        for tb in (blk.get("tables") or []):
            t = {"cols": [project(c, pj, True) for c in tb["cols"]], "rows": tb["rows"],
                 "body": [[project(c, pj, True) for c in row]
                          for row in tb.get("body") or []],
                 "truncated": tb.get("truncated", False)}
            for cell in t["cols"] + [c for row in t["body"] for c in row]:
                dirty += leftover_numbers(cell)
                suspect += leftover_names(cell)
            tables.append(t)
        def _proj_tables(tbs):
            out_t = []
            for tb in (tbs or []):
                t = {"cols": [project(c, pj, True) for c in tb["cols"]], "rows": tb["rows"],
                     "body": [[project(c, pj, True) for c in row]
                              for row in tb.get("body") or []],
                     "truncated": tb.get("truncated", False)}
                for cell in t["cols"] + [c for row in t["body"] for c in row]:
                    dirty.append(None) if False else None
                out_t.append(t)
            return out_t
        subs = [{"title": project(sb["title"], pj), "level": sb.get("level", 2),
                 "paragraphs": [project(t, pj) for t in sb["paras"]],
                 "tables": _proj_tables(sb.get("tables"))}
                for sb in (blk.get("subs") or [])]
        sec = {
            "title": project(blk["title"], pj),
            "paragraphs": paras,
            "subs": subs,
            "tables": tables,
            "char_count": sum(len(t) for t in blk["paras"]),
            "para_count": len(paras),
            "defects": dfx.get(key, []),
        }
        sec["shape"] = distill(sec)          # 检索时只发这一份，不发 paragraphs
        entry["sections"][key] = sec
        chapters[key] = sec
    entry["global_defects"] = dfx.get("_global", []) + dfx.get("_error", [])
    entry["split_quality"] = quality
    entry["projection_leftovers"] = sorted(set(dirty))
    entry["suspect_proper_nouns"] = sorted(set(suspect))[:40]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    entry["chunks"] = write_chunks(out, entry["id"], chapters)
    # 正文落到 chapters/*.md 之后，entry.yaml 里就不再留 paragraphs 了。
    # 一是它有 400 多 KB，没人会去读，而入库时那 29 个疑似漏投影的专名
    # **必须有人过一遍**——读不动就没人过。二是把「形」和「文」分成两个
    # 文件，检索时只读 entry.yaml 就不可能顺手把原文带进起草上下文。
    for key, sec in entry["sections"].items():
        sec.pop("paragraphs", None)
        for sb in (sec.get("subs") or []):
            sb.pop("paragraphs", None)
    (out / "entry.yaml").write_text(
        yaml.safe_dump(entry, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return entry


def write_chunks(out, eid, chapters):
    """每个语义 chunk 一个 MD，外加一份索引。

    人要能读、能改投影、能 diff——entry.yaml 里的 400KB 做不到这些，
    而入库报回的那 29 个疑似漏投影的专名**必须有人过一遍**，读不动就没人过。
    """
    cdir = out / "chunks"
    cdir.mkdir(parents=True, exist_ok=True)
    for old in cdir.glob("*.md"):
        old.unlink()

    index = []
    for key, sec in chapters.items():
        for ck in chunk_section(key, sec):
            paras = ck["paragraphs"]
            funcs = [_para_function(t) for t in paras]
            tally = {}
            for f in funcs:
                tally[f] = tally.get(f, 0) + 1
            chars = sum(len(t) for t in paras)
            L = [f"# {ck['id']}　{ck['title']}", "",
                 f"> 条目 `{eid}`｜章节 `{key}`｜{len(paras)} 段 / 约 {chars} 字", ">",
                 "> **本文件是脱值骨架，不是可引用的正文。**",
                 "> 数字、专名、文号、规范编号已替换为 ⟨槽位⟩。",
                 "> 用途是人工核对投影是否干净——**不要放进起草上下文**；",
                 "> 起草只看索引里量出来的形（功能顺序、篇幅、表栏）。", ""]
            if ck.get("sub_titles"):
                L += ["> 下含：" + "、".join(ck["sub_titles"]), ""]
            if ck.get("tables"):
                L += ["## 表格栏目",
                      ("（本章级表格，未能定位到具体小节）"
                       if ck.get("tables_are_section_level") else ""), ""]
                for i, tb in enumerate(ck["tables"], 1):
                    L.append(f"**表 {i}**（{tb['rows']} 行）")
                    L.append("")
                    L.append("| " + " | ".join(tb["cols"]) + " |")
                    L.append("|" + "---|" * len(tb["cols"]))
                    for row in (tb.get("body") or []):
                        L.append("| " + " | ".join(row) + " |")
                    if tb.get("truncated"):
                        L.append(f"（表体已截断，原表 {tb['rows']} 行）")
                    L.append("")
            if sec.get("defects"):
                L += ["## 所属章节的已知缺陷", ""] + [
                    f"- {d}" for d in sec["defects"]] + [""]
            L += ["## 骨架", ""] + list(paras)
            (cdir / f"{ck['id']}.md").write_text("\n".join(L) + "\n", encoding="utf-8")

            index.append({
                "chunk": ck["id"], "section": key, "title": ck["title"],
                "paras": len(paras), "chars": chars,
                "mix": [f"{k} {v}" for k, v in
                        sorted(tally.items(), key=lambda x: -x[1])][:3],
                "flow": [f"{s['func']}×{s['paras']}"
                         for s in _runs(funcs, [len(t) for t in paras])][:10],
                "tables": [tb["cols"] for tb in (ck.get("tables") or [])][:6],
                "sub_titles": ck.get("sub_titles") or [],
                "whole_section": ck.get("whole_section", False),
                "file": f"chunks/{ck['id']}.md",
            })
    (out / "index.yaml").write_text(
        yaml.safe_dump({"entry": eid, "chunks": index},
                       allow_unicode=True, sort_keys=False), encoding="utf-8")
    return index


# =============================================================================
# 引用完整性 —— 语料与图谱之间唯一的那根线
# =============================================================================
# 骨架与图谱是**松耦合**的：它们之间只有一根线，就是槽位标签里的字符串
# 恰好等于图上的节点 id。没有外键，没有引用计数，谁也不认识谁。
#
# 松耦合本身是对的——语料是文本，图谱是数据，硬绑在一起会让两边都改不动。
# 但松到「改个节点名，语料里的标签悄悄失效而没人知道」就过头了。
# 一根线也是线，得有人看着它。
#
# 两个方向都要报：
#   悬空标签   骨架里写着 ⟨scale.design_total⟩，图上没有这个节点
#   无锚节点   图上有这个节点，骨架里一次都没出现
# 后者不是错误——很多节点的值是小整数或 UNKNOWN，本来就锚不上——
# 但它是**这份语料还有多少内容没被图覆盖**的直接度量。
# =============================================================================

TYPED_SLOTS = {"数值", "年份", "文号", "规范编号", "人员",
               "建设单位", "项目所在地", "内设机构", "槽位"}


def slot_refs(entry_dir):
    """骨架里用到的节点名槽位 → 出现次数。类型槽位（⟨数值⟩等）不计。"""
    out = {}
    for f in sorted((Path(entry_dir) / "chunks").glob("*.md")):
        body = f.read_text(encoding="utf-8").split("## 骨架", 1)[-1]
        for m in SLOT.findall(body):
            name = m.strip("⟨⟩")
            if name in TYPED_SLOTS:
                continue
            out[name] = out.get(name, 0) + 1
    return out


def ref_integrity(entry_dir, graph):
    refs = slot_refs(entry_dir)
    nodes = set(graph.get("nodes") or {})
    dangling = {k: v for k, v in refs.items() if k not in nodes}
    anchored = set(refs) & nodes
    return {"refs": len(refs), "dangling": dangling,
            "anchored": sorted(anchored), "unanchored": sorted(nodes - anchored),
            "coverage": len(anchored) / max(len(nodes), 1)}


# =============================================================================
# 检索
# =============================================================================

def read_chapter_md(entry, section):
    """按需读某章的骨架 MD。检索默认不走这里——只有人显式索取才读。"""
    d = entry.get("_dir")
    if not d:
        return []
    f = Path(d) / "chunks" / f"{section}-01.md"
    if not f.exists():
        return []
    body = f.read_text(encoding="utf-8").split("## 骨架", 1)
    if len(body) < 2:
        return []
    return [x for x in (ln.strip() for ln in body[1].splitlines())
            if x and not x.startswith("#")]


def load_corpus(corpus_dir):
    out = []
    for f in sorted(Path(corpus_dir).glob("*/entry.yaml")):
        try:
            e = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        e["_dir"] = str(f.parent)          # 骨架 MD 在旁边，按需才读
        out.append(e)
    return out


def rank_entries(entries, section, want):
    """按适配性排序。同垂类同子类同报送层级 > 同垂类同子类 > 同垂类 > 同大纲版本。"""
    scored = []
    for e in entries:
        if section not in (e.get("sections") or {}):
            continue
        fm = e.get("fit_meta") or {}
        s = 0
        if want.get("vertical") and fm.get("vertical") == want["vertical"]:
            s += 4
        if want.get("subtype") and want["subtype"] in (fm.get("subtypes") or []):
            s += 3
        if want.get("reporting_to") and fm.get("reporting_to") == want["reporting_to"]:
            s += 2
        if want.get("outline_version") and fm.get("outline_version") == want["outline_version"]:
            s += 2
        if str(fm.get("review_outcome", "")).startswith("通过"):
            s += 1
        try:
            s += min(int(fm.get("year", 0)) - 2015, 8) * 0.1
        except Exception:
            pass
        scored.append((s, e))
    scored.sort(key=lambda x: -x[0])
    return scored[:3]                     # 每章至多 3 条；多了只会看第一条


def diff_hints(fm, want):
    """主动指出差异。不指出，参照者会默认它可比。"""
    h = []
    if want.get("reporting_to") and fm.get("reporting_to") != want["reporting_to"]:
        h.append(f"这份是「{fm.get('reporting_to')}」口径，您这份报「{want['reporting_to']}」——详略要求不同")
    if want.get("outline_version") and fm.get("outline_version") != want["outline_version"]:
        h.append(f"这份依据「{fm.get('outline_version')}」编制，**结构不可参照**，只看行文")
    if want.get("subtype") and want["subtype"] not in (fm.get("subtypes") or []):
        h.append(f"子类不同（这份是 {fm.get('subtypes')}），专业条件部分不通用")
    if fm.get("known_gaps"):
        h.append(f"这份相对现行大纲缺：{fm['known_gaps']}——不要连缺失一起继承")
    return h


def render_retrieve(section, hits, want, show_skeleton=False):
    """检索的产物是**一段起草提示词**，不是一段可续写的文本。

    历史章节在这里已经被量成了形（功能顺序、篇幅、表栏），原文不出现。
    起草仍然是从图谱与客户输入重新写，只是写成这一类报告该有的样子。
    """
    L = ["=" * 74, f"起草提示 · {section}（形来自历史库，值来自图谱）", "=" * 74, ""]
    if not hits:
        L.append("库里没有可比条目。按 section-prompts.yaml 的本章提示直接起草——")
        L.append("没有参照不影响正确性，参照错了才影响。")
        return "\n".join(L)

    L.append("【怎么用这段提示】")
    L.append("  下面给的是同类报告这一章的**形**：段落功能怎么排、各占多少篇幅、")
    L.append("  表设了哪几栏、结论摆在哪。历史原文不在这里，也不该去找——")
    L.append("  照着原文续写出来的东西带着那份报告的骨相，脱不脱值都是套模板。")
    L.append("  起草时：本章图谱切片给事实，客户素材给情况，这段提示只管形。")
    L.append("")

    for i, (score, e) in enumerate(hits, 1):
        fm = e.get("fit_meta") or {}
        sec = e["sections"][section]
        sh = sec.get("shape") or distill(sec)
        L.append(f"【同类样本 {i}】{e.get('id')}　适配度 {score:.1f}"
                 f"（{fm.get('vertical')} / {fm.get('subtypes')} / "
                 f"{fm.get('reporting_to')} / {fm.get('outline_version')} / "
                 f"{fm.get('year')} / 评审{fm.get('review_outcome', '未知')}）")
        L.append(f"  篇幅：{sh['para_count']} 段 / 约 {sh['char_count']} 字，"
                 f"段均 {sh['para_len']['mean']} 字（最长 {sh['para_len']['max']}）")
        L.append(f"  铺陈顺序：{' → '.join(sh['flow'][:12])}"
                 + ("　…" if len(sh["flow"]) > 12 else ""))
        L.append("  成分配比：" + "、".join(f"{k} {v}" for k, v in sh["mix"].items()))
        if sh.get("ends_with"):
            L.append(f"  收尾方式：以「{sh['ends_with']}」结章")
        for ck in (e.get("chunks") or []):
            if ck.get("section") != section:
                continue
            L.append(f"    ▸ {ck['chunk']}　{ck['title']}　"
                     f"{ck['paras']} 段 / {ck['chars']} 字　"
                     + "、".join(ck.get("mix") or []))
        for tb in (sh.get("tables") or [])[:4]:
            L.append(f"  表（{tb['rows']} 行）栏目：{' | '.join(tb['cols'][:8])}")
        for h in diff_hints(fm, want):
            L.append(f"  ⚠ 差异：{h}")
        if sec.get("defects"):
            L.append("  ✗ 这一章的已知缺陷——**照着形写，但不要照着这些毛病写**：")
            for d in sec["defects"][:6]:
                L.append(f"      · {d}")
        else:
            L.append("  ✓ 这一章入库体检未见缺陷")
        if show_skeleton:
            paras = sec.get("paragraphs") or read_chapter_md(e, section)
            L.append(f"  骨架（仅供人工核对，不得放进起草上下文；"
                     f"全文见 {e.get('_dir', '')}/chapters/{section}.md）：")
            for t in paras[:6]:
                L.append(f"      {t[:110]}")
            if len(paras) > 6:
                L.append(f"      …（共 {len(paras)} 段）")
        L.append("")

    L.append("-" * 74)
    L.append("【起草纪律】")
    L.append("  1 值不来自这里。数、政策、规范、口径仍走来源路由（COMPUTE/ASK/SEARCH）。")
    L.append("  2 结构以法定大纲为准。旧口径样本只说明行文，不说明该写哪几节。")
    L.append("  3 缺陷先过一遍，明确本章不重复。")
    L.append("  4 样本少于两份时，把上面的形当参考而非标准——"
             "一份样本反映的是那位编制人的习惯。")
    L.append("  5 写完自检：正文里不得出现样本特有的专名、文号、规范编号（C19b）。")
    return "\n".join(L)


# =============================================================================
# CLI
# =============================================================================

@guard
def main(argv):
    ap = argparse.ArgumentParser(description="历史报告语料库")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a1 = sub.add_parser("ingest", help="入库：切章 + 脱值 + 体检")
    a1.add_argument("docx")
    a1.add_argument("--graph", required=True)
    a1.add_argument("--meta", required=True)
    a1.add_argument("-o", "--out", required=True)

    a2 = sub.add_parser("retrieve", help="按章检索参照")
    a2.add_argument("corpus_dir")
    a2.add_argument("--section", required=True)
    a2.add_argument("--vertical")
    a2.add_argument("--subtype")
    a2.add_argument("--reporting-to")
    a2.add_argument("--outline-version")
    a2.add_argument("--show-skeleton", action="store_true",
                    help="附带脱值骨架，仅供人工核对——不要放进起草上下文")

    a3 = sub.add_parser("check", help="自检投影是否干净 + 语料与图谱的引用完整性")
    a3.add_argument("entry_dir")
    a3.add_argument("--graph", help="配套图谱；给了就一并核引用完整性")

    a = ap.parse_args(argv[1:])

    if a.cmd == "ingest":
        graph = yaml.safe_load(Path(a.graph).read_text(encoding="utf-8"))
        meta = yaml.safe_load(Path(a.meta).read_text(encoding="utf-8"))
        e = ingest(a.docx, graph, meta, a.out)
        print(f"已入库 {e['id']} → {a.out}/entry.yaml")
        q = e.get("split_quality") or {}
        for w in (q.get("warnings") or []):
            print(f"  ⚠ 切章：{w}")
        print(f"  章节 {len(e['sections'])} 个，"
              f"缺陷 {sum(len(s['defects']) for s in e['sections'].values())} 条"
              f"（另有全局 {len(e['global_defects'])} 条）")
        if e["projection_leftovers"]:
            print(f"  ⚠ 投影残留 {len(e['projection_leftovers'])} 处："
                  f"{e['projection_leftovers'][:12]}")
            print("    一个漏网的数字就够引发一次事故——补投影规则后重新入库。")
            return 1
        if e.get("suspect_proper_nouns"):
            print(f"  ⚠ 疑似漏投影的专名 {len(e['suspect_proper_nouns'])} 个（交人工确认）：")
            print(f"    {e['suspect_proper_nouns'][:12]}")
            print("    确属该项目专有的，加进 meta.orgs 后重新入库；")
            print("    是通用说法的（如「设计单位」）可以忽略。")
        print("  ✓ 投影干净：骨架里没有残留数值")
        return 0

    if a.cmd == "retrieve":
        want = {"vertical": a.vertical, "subtype": a.subtype,
                "reporting_to": a.reporting_to, "outline_version": a.outline_version}
        hits = rank_entries(load_corpus(a.corpus_dir), a.section, want)
        print(render_retrieve(a.section, hits, want, a.show_skeleton))
        return 0

    e = yaml.safe_load((Path(a.entry_dir) / "entry.yaml").read_text(encoding="utf-8"))
    bad = e.get("projection_leftovers") or []
    print(f"{e.get('id')}：章节 {len(e.get('sections') or {})} 个，投影残留 {len(bad)} 处")
    if bad:
        print(f"  {bad[:20]}")
        return 1
    print("  ✓ 投影干净")

    gp = Path(a.graph) if a.graph else (Path(a.entry_dir) / "graph.yaml")
    if not gp.exists():
        print("  （未找到配套图谱，跳过引用完整性核验）")
        return 0
    g = yaml.safe_load(gp.read_text(encoding="utf-8")) or {}
    r = ref_integrity(a.entry_dir, g)
    print(f"  引用完整性：骨架用到 {r['refs']} 个节点名槽位，"
          f"图上 {len(r['anchored'])} / {len(r['anchored']) + len(r['unanchored'])} "
          f"个节点有文本锚点（{r['coverage']:.0%}）")
    if r["dangling"]:
        print(f"  ✗ 悬空标签 {len(r['dangling'])} 个——骨架指向图上不存在的节点：")
        print(f"      {sorted(r['dangling'])[:12]}")
        print("    多半是图谱改过节点名而语料没跟着改。**松耦合不等于不核**。")
        return 1
    print("  ✓ 无悬空标签")
    if r["unanchored"]:
        print(f"  · 无文本锚点的节点 {len(r['unanchored'])} 个——图上有值，骨架里没出现。")
        print("    不是错误（小整数与 UNKNOWN 本来就锚不上），"
              "但它是这份语料还有多少内容没被图覆盖的直接度量。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
