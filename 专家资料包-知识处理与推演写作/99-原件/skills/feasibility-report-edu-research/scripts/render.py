#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
渲染管线：把实例图 + 章节正文渲染为带锚点的 docx，并输出回读所需的绑定表。

核心设计：**正文里不许出现字面数字，只能写 {{节点名}}。**

这不是风格约束，是物理约束。人（或模型）一旦能直接把 26400 敲进正文，
SSOT 就破了——同一个数会在十几处被各自敲一遍，改一处漏十处。
本脚本遇到未声明的占位符直接报错退出，不生成半成品文档。

同时输出 bindings.json：node_id → 文档中的锚点位置。
这是反向回读（客户改稿后回读为图上的节点变更）的前提。
详见 references/reconcile.yaml。

用法：
    python3 scripts/render.py <project.yaml> <content.yaml> -o out/
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\}\}")


def fmt(value, unit=None):
    """数值格式化。可研报告不使用千分位分隔符，整数直出，小数去尾零。"""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        s = str(value)
    elif isinstance(value, float):
        s = f"{value:.4f}".rstrip("0").rstrip(".")
    else:
        s = str(value)
    return s




# =============================================================================
# 排版
# =============================================================================

def load_typography(preset=None):
    f = ROOT / "references/typography.yaml"
    if not f.exists():
        return None
    doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    name = preset or doc.get("default_preset") or "gov_review"
    ps = (doc.get("presets") or {}).get(name)
    if not ps:
        raise SystemExit(f"排版预设「{name}」不存在。可选：{list((doc.get('presets') or {}))}")
    return {"name": name, "cn": ps.get("cn", name), "elements": ps.get("elements") or {},
            "page": ps.get("page") or {}, "size_map": doc.get("size_map") or {}}


def _pt(spec, key, size_map, default=12):
    v = spec.get(key)
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    return float(size_map.get(str(v), default))


def _set_font(run_or_style, name, fallback=None):
    """同时设西文与中文字体。

    只设 font.name 的话，**中文会退回默认字体**——文档里中英文两种脸。
    而且在编制人自己的机器上常常看不出来（本机装了对应字体），
    发出去才被发现，那时已经在评委手里了。
    """
    from docx.oxml.ns import qn
    fonts = run_or_style.font
    fonts.name = name
    el = run_or_style._element
    rPr = el.get_or_add_rPr() if hasattr(el, "get_or_add_rPr") else el.rPr
    if rPr is None:
        return
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:eastAsia"), name)
    rFonts.set(qn("w:ascii"), fallback or name)
    rFonts.set(qn("w:hAnsi"), fallback or name)


def apply_typography(doc, ty):
    """把预设写进文档样式与页面设置。返回是否成功设了 eastAsia（供 C16 自检）。"""
    if not ty:
        return False
    from docx.shared import Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    sm, el = ty["size_map"], ty["elements"]
    ALIGN = {"center": WD_ALIGN_PARAGRAPH.CENTER, "left": WD_ALIGN_PARAGRAPH.LEFT,
             "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}

    def style_of(sname, spec):
        try:
            st = doc.styles[sname]
        except KeyError:
            return
        _set_font(st, spec.get("font", "宋体"), spec.get("fallback"))
        st.font.size = Pt(_pt(spec, "size", sm))
        if spec.get("bold") is not None:
            st.font.bold = bool(spec["bold"])
        pf = st.paragraph_format
        if spec.get("line_spacing"):
            pf.line_spacing = float(spec["line_spacing"])
        if spec.get("space_before") is not None:
            pf.space_before = Pt(float(spec["space_before"]))
        if spec.get("space_after") is not None:
            pf.space_after = Pt(float(spec["space_after"]))
        if spec.get("align") in ALIGN:
            pf.alignment = ALIGN[spec["align"]]
        if spec.get("first_line_indent"):
            # 中文首行缩进按字数算，2 字 = 2 × 字号
            pf.first_line_indent = Pt(_pt(spec, "size", sm) * float(spec["first_line_indent"]))

    style_of("Normal", el.get("body", {}))
    style_of("Title", el.get("title", {}))
    for lvl, key in ((1, "heading1"), (2, "heading2"), (3, "heading3")):
        style_of(f"Heading {lvl}", el.get(key, {}))

    pg = ty.get("page") or {}
    m = pg.get("margin_cm") or {}
    for sec in doc.sections:
        if m.get("top"):    sec.top_margin = Cm(float(m["top"]))
        if m.get("bottom"): sec.bottom_margin = Cm(float(m["bottom"]))
        if m.get("left"):   sec.left_margin = Cm(float(m["left"]))
        if m.get("right"):  sec.right_margin = Cm(float(m["right"]))
    return True


def verify_eastasia(docx_path):
    """C16a：打开成品确认正文样式真的设了 w:eastAsia。

    不做这一步的话，「中英文两种脸」这个坑在本机永远暴露不出来。
    """
    import docx
    from docx.oxml.ns import qn
    d = docx.Document(docx_path)
    try:
        rPr = d.styles["Normal"]._element.rPr
    except Exception:
        return False
    if rPr is None:
        return False
    rf = rPr.rFonts
    return rf is not None and bool(rf.get(qn("w:eastAsia")))

# =============================================================================
# 篇幅核对
# =============================================================================

# 字面数字检查：正文与表格里出现的数字，必须是 {{节点}} 解析出来的，不能是手打的。
# 以前只查反方向（图上有节点、正文没用到），漏了正方向——
# 而正方向才是 18219 那类事故的产生机制：手打一个数，从此它与图无关。
# 表格尤其危险：一张表几十个单元格，手打一个混在里面根本看不出来。
_LIT_SKIP = [
    re.compile(r"^\s*(?:第\s*[0-9一二三四五六七八九十]+\s*[章节条款]|"
               r"[0-9]+(?:\.[0-9]+)*[\s、.）)]|[（(][0-9]+[）)])"),   # 章节号与序号
    re.compile(r"(?:19|20)\d{2}\s*年"),                              # 年份
    re.compile(r"(?:GB|JGJ|CJJ|DGJ|DBJ|建标|HJ)\s?/?\s?T?\s?[\d\-—./]+"),  # 规范编号
    re.compile(r"[〔\[（(]\s*(?:19|20)\d{2}\s*[〕\]）)]\s*第?\s*\d+\s*号"),   # 文号
    re.compile(r"[a-zA-Zμ㎡°]\s*[23]\b"),                            # m2 m3 之类的指数
]
_LIT_NUM = re.compile(r"(?<![A-Za-z0-9.\-])\d[\d,]*(?:\.\d+)?(?![0-9])")


def literal_numbers(text):
    """一段文本里手打的数字。返回空列表表示干净。"""
    t = str(text or "")
    for rx in _LIT_SKIP:
        t = rx.sub(" ", t)
    return _LIT_NUM.findall(t)


class _TableRows:
    """表的行也该受 SSOT 管。

    单元格的值早就走 {{节点}} 了，但**行本身是手写枚举的**——
    图上新增一个配套用房分项，表不会自己多一行，得有人记得去改 content.yaml。
    「记得去改」正是我们要消灭的东西。

    所以支持 rows_from：按节点族生成行。
      rows_from: {prefix: "support.", suffix: ".area", label: note, unit: ㎡}
    图上加一条 support.xxx.area，表自动多一行；删一条，自动少一行。
    """


def _cjk_len(t):
    """中文按字计，英文数字按 2 字符折 1 字，粗略但够用。"""
    n = 0
    run = 0
    for ch in t:
        if "\u4e00" <= ch <= "\u9fff":
            n += 1
        elif ch.isalnum():
            run += 1
        else:
            n += run // 2
            run = 0
    return n + run // 2


def length_report(counts, outline_path=None, total_pages=None):
    """每章实际字数 vs 预算区间。

    这是**提示，不是门禁**。字数达标不等于写得好，不达标也不一定是问题。
    它的价值是让「某章被一笔带过」这件事在出稿前可见，
    而不是等评审指出来。

    权重来自垂类 outline.yaml；没有权重就只报字数不判偏离。
    """
    weights = {}
    if outline_path and Path(outline_path).exists():
        try:
            doc = yaml.safe_load(Path(outline_path).read_text(encoding="utf-8")) or {}
            for sec in doc.get("sections") or []:
                if isinstance(sec, dict) and sec.get("weight") is not None:
                    weights[sec["id"]] = float(sec["weight"])
        except Exception:
            weights = {}

    L = ["", "-" * 70, "篇幅核对", "-" * 70]
    total = sum(counts.values())
    L.append(f"正文合计约 {total} 字（约 {total / 800:.1f} 页）")
    if not weights:
        for cid, n in counts.items():
            L.append(f"  {cid}: {n} 字")
        L.append("  （垂类未定义章节权重，只报字数不判偏离）")
        return "\n".join(L), []

    budget_total = (total_pages * 800) if total_pages else total
    wsum = sum(weights.get(c, 1.0) for c in counts) or 1
    off = []
    for cid, n in counts.items():
        w = weights.get(cid, 1.0)
        target = budget_total * w / wsum
        lo, hi = target * 0.6, target * 1.6
        if n < lo:
            off.append((cid, n, int(target), "偏短"))
            L.append(f"  {cid}: {n} 字　目标约 {int(target)}　⚠ 偏短")
        elif n > hi:
            off.append((cid, n, int(target), "偏长"))
            L.append(f"  {cid}: {n} 字　目标约 {int(target)}　⚠ 偏长")
        else:
            L.append(f"  {cid}: {n} 字　目标约 {int(target)}　✓")
    if off:
        L.append("")
        L.append("  偏短的三条出路：补事实（去追料）、补论证（去补论据）、")
        L.append("  或承认这一章内容就这么多并如实告知客户。")
        L.append("  **不许抄规范条文充数**——评审一眼看得出，而且会怀疑其余各章。")
        L.append("  偏长的先移附件：计算过程、台账、逐项清单进附件，正文留结论与关键中间量。")
    return "\n".join(L), off


class Renderer:

    def __init__(self, proj, content):
        self.p = proj
        self.c = content
        self.nodes = proj.get("nodes") or {}
        self.bindings = {}
        self.errors = []
        self.literals = []
        self.figures = []
        self.wordcount = {}
        self.outline_path = None   # 垂类 outline.yaml，供篇幅权重
        self.total_pages = None    # 客户给的页数上限，没给就按实际总量归一
        self.preset = None         # 排版预设，没指定就用 typography.yaml 的默认
        self._bm_id = 0

    def resolve(self, name):
        n = self.nodes.get(name)
        if n is None:
            self.errors.append(name)
            return None
        return n

    # ------------------------------------------------------------------
    def _split(self, text):
        """把含占位符的文本切成 [(literal|node, payload), ...]。"""
        out, last = [], 0
        for m in PLACEHOLDER.finditer(text):
            if m.start() > last:
                out.append(("lit", text[last:m.start()]))
            out.append(("node", m.group(1)))
            last = m.end()
        if last < len(text):
            out.append(("lit", text[last:]))
        return out

    def _add_runs(self, para, text, section_id, block_id):
        """写入段落。节点值用书签包起来，供反向回读定位。"""
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        for kind, payload in self._split(text):
            if kind == "lit":
                if payload:
                    para.add_run(payload)
                continue
            node = self.resolve(payload)
            if node is None:
                para.add_run(f"{{{{{payload}}}}}")
                continue

            self._bm_id += 1
            bm = f"n{self._bm_id}"
            start = OxmlElement("w:bookmarkStart")
            start.set(qn("w:id"), str(self._bm_id))
            start.set(qn("w:name"), bm)
            para._p.append(start)

            rendered = fmt(node["value"])
            para.add_run(rendered)

            end = OxmlElement("w:bookmarkEnd")
            end.set(qn("w:id"), str(self._bm_id))
            para._p.append(end)

            self.bindings.setdefault(payload, []).append({
                "bookmark": bm,
                "section": section_id,
                "block": block_id,
                "rendered": rendered,
                "value": node["value"],
                "unit": node.get("unit"),
            })

    # ------------------------------------------------------------------
    def _table_rows(self, blk):
        """表的行：显式写死的用 rows，按节点族生成的用 rows_from。"""
        spec = blk.get("rows_from")
        if not spec:
            return blk.get("rows") or []
        pre, suf = spec.get("prefix", ""), spec.get("suffix", "")
        label_key = spec.get("label", "note")
        rows = []
        for nid, n in sorted(self.nodes.items()):
            if not (nid.startswith(pre) and nid.endswith(suf)):
                continue
            label = n.get(label_key) or nid[len(pre):len(nid) - len(suf) or None]
            rows.append([str(label), "{{" + nid + "}}", n.get("unit") or spec.get("unit", "")])
        if not rows:
            self.errors.append(
                f"表「{blk.get('title', '')}」的 rows_from 没匹配到任何节点"
                f"（前缀 {pre!r} 后缀 {suf!r}）——空表不该出现在成稿里")
        rows += [list(x) for x in (spec.get("append") or [])]
        return rows

    def _add_figure(self, doc, blk, out_dir, sid, bid):
        """生成 SVG 并嵌入段落。SVG 同时落盘，供排版单独取用。

        缺节点时不静默跳过——记进 self.errors，让整次渲染中止。
        一张缺了数的图比没有图更糟：它看起来像是已经画过了。
        """
        import figures as F
        fid = blk.get("figure")
        try:
            svg = F.build(fid, self.p)
        except (F.FigureError, Exception) as e:
            if isinstance(e, F.FigureError):
                self.errors.append(f"插图 {fid}（{sid}）：{e}")
                return
            raise
        fdir = Path(out_dir) / "figures"
        fdir.mkdir(parents=True, exist_ok=True)
        svg_path = fdir / f"{fid}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        self.figures.append({"id": fid, "section": sid, "block": bid,
                             "svg": str(svg_path.relative_to(Path(out_dir)))})
        try:
            png = F.to_png(svg, width=1000)
        except F.FigureError as e:
            self.errors.append(f"插图 {fid}：{e}")
            return
        import io
        from docx.shared import Inches
        doc.add_picture(io.BytesIO(png), width=Inches(5.8))
        doc.paragraphs[-1].alignment = 1

    def build(self, out_dir):
        try:
            import docx
        except ImportError:
            print("需要 python-docx：pip install python-docx --break-system-packages")
            return 2

        doc = docx.Document()
        ty = load_typography(self.preset)
        applied = apply_typography(doc, ty)
        proj = self.p.get("project") or {}
        doc.add_heading(proj.get("name", "可行性研究报告"), 0)

        for sec in self.c.get("sections") or []:
            sid = sec.get("id", "?")
            for bi, blk in enumerate(sec.get("blocks") or []):
                bid = f"{sid}#{bi}"
                t = blk.get("type", "para")
                if t == "heading":
                    doc.add_heading(blk.get("text", ""), blk.get("level", 1))
                elif t == "para":
                    p = doc.add_paragraph()
                    self._add_runs(p, blk.get("text", ""), sid, bid)
                    self.wordcount[sid] = self.wordcount.get(sid, 0) + _cjk_len(blk.get("text", ""))
                elif t == "bullet":
                    p = doc.add_paragraph(style="List Bullet")
                    self._add_runs(p, blk.get("text", ""), sid, bid)
                    self.wordcount[sid] = self.wordcount.get(sid, 0) + _cjk_len(blk.get("text", ""))
                elif t == "figure":
                    # 客户没提供设计单位的图时，用图上的参数生成示意图。
                    # 只画数据图——设计图（总平面、平面立面剖面、系统图）一律不画，
                    # 那些承载的是设计单位的专业判断，画出来会被当成设计成果审。
                    self._add_figure(doc, blk, out_dir, sid, bid)
                elif t == "table":
                    cols = blk.get("columns") or []
                    rows = self._table_rows(blk)
                    if blk.get("title"):
                        doc.add_paragraph(blk["title"])
                    tb = doc.add_table(rows=1, cols=len(cols))
                    tb.style = "Table Grid"
                    for j, c in enumerate(cols):
                        tb.rows[0].cells[j].text = str(c)
                    for ri, row in enumerate(rows):
                        cells = tb.add_row().cells
                        for j, cell in enumerate(row[:len(cols)]):
                            para = cells[j].paragraphs[0]
                            self._add_runs(para, str(cell), sid, f"{bid}.r{ri}c{j}")
                            if not blk.get("literal_ok"):
                                for lit in literal_numbers(cell):
                                    self.literals.append(
                                        f"{sid} 表「{blk.get('title', bid)}」第 {ri + 1} 行："
                                        f"手打了数字 {lit}——应写成 {{{{节点名}}}}")

        if getattr(self, "literals", None):
            print(f"\n表格里手打了 {len(self.literals)} 个数字——**它们与图无关，改图不会跟着改**：")
            for x in sorted(set(self.literals))[:20]:
                print(f"  · {x}")
            print("  这正是「第 13 章写 18219、其余十处写 18319」的产生机制。")
            print("  确属不该建节点的（如单位换算系数），在该 block 上标 literal_ok: true 并写明理由。")
            self.errors += self.literals

        if self.errors:
            uniq = sorted(set(self.errors))
            print("渲染中止：正文引用了图中不存在的节点，或插图缺少所需数据")
            for e in uniq:
                print(f"  · {e}")
            print("\n不生成半成品文档——带着未解析占位符的稿子一旦流出，")
            print("就会有人手工把数字填进去，SSOT 当场失效。")
            return 1

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        docx_path = out / "report.docx"
        doc.save(docx_path)

        if ty:
            print(f"排版预设：{ty['cn']}（{ty['name']}）"
                  f"　正文 {ty['elements'].get('body', {}).get('font', '—')} "
                  f"{ty['elements'].get('body', {}).get('size', '—')}")
            if not (applied and verify_eastasia(docx_path)):
                print("  ⚠ 中文字体（w:eastAsia）未设置成功——文档里中英文会是两种脸。")
                print("    这个问题在装了对应字体的本机看不出来，发出去才会被发现。")

        if self.wordcount:
            txt, _off = length_report(self.wordcount, self.outline_path, self.total_pages)
            print(txt)

        if self.figures:
            print(f"已生成插图 {len(self.figures)} 张 → {out / 'figures'}")
            for f in self.figures:
                print(f"  · {f['id']}  ({f['section']})")

        (out / "bindings.json").write_text(
            json.dumps(self.bindings, ensure_ascii=False, indent=2), encoding="utf-8")

        # default=str：节点上可能带 YAML 解析出的 date（如 adopted_at），
        # 不兜住会在快照这一步崩掉，而快照失败会让整次渲染无声中止
        graph_state = json.dumps(self.nodes, ensure_ascii=False, sort_keys=True, default=str)
        snapshot = {
            "project_id": proj.get("id"),
            "graph_sha256": hashlib.sha256(graph_state.encode("utf-8")).hexdigest(),
            "node_count": len(self.nodes),
            "anchor_count": sum(len(v) for v in self.bindings.values()),
            "bound_nodes": len(self.bindings),
            "content_sha256": hashlib.sha256(
                json.dumps(self.c, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        }
        (out / "snapshot.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"已生成 {docx_path}")
        print(f"锚点 {snapshot['anchor_count']} 处，覆盖 {snapshot['bound_nodes']} 个节点")
        unbound = sorted(set(self.nodes) - set(self.bindings))
        if unbound:
            print(f"\n图中有 {len(unbound)} 个节点未出现在正文中：")
            for u in unbound[:12]:
                print(f"  · {u}")
            if len(unbound) > 12:
                print(f"  … 另 {len(unbound) - 12} 个")
            print("孤儿节点要么该写进正文，要么该从图里删掉——两者都不做会让图与文脱节。")
        return 0


def main(argv):
    if len(argv) < 3:
        print("用法: render.py <project.yaml> <content.yaml> [-o out_dir]"
              " [--outline 垂类outline.yaml] [--pages N] [--preset gov_review|enterprise|compact]")
        print("  --outline 给出章节篇幅权重；--pages 是客户给的页数上限。")
        print("  两者都不给时只统计字数，不判偏离。")
        return 2
    proj = yaml.safe_load(Path(argv[1]).read_text(encoding="utf-8"))
    content = yaml.safe_load(Path(argv[2]).read_text(encoding="utf-8"))
    out = argv[argv.index("-o") + 1] if "-o" in argv else "out"
    r = Renderer(proj, content)
    if "--outline" in argv:
        r.outline_path = argv[argv.index("--outline") + 1]
    else:
        # 未显式给出时，按项目 profile 找垂类模版；找不到就只报字数
        pid = (proj.get("project") or {}).get("profile")
        for cand in ([ROOT / "references/vertical/outline.yaml"] +
                     ([ROOT / f"references/verticals/{pid}/outline.yaml"] if pid else [])):
            if cand.exists():
                r.outline_path = str(cand); break
    if "--pages" in argv:
        r.total_pages = float(argv[argv.index("--pages") + 1])
    if "--preset" in argv:
        r.preset = argv[argv.index("--preset") + 1]
    return r.build(out)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
