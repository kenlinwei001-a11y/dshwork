# -*- coding: utf-8 -*-
"""Markdown → DOCX（纯标准库：zipfile + XML，无第三方依赖）。

支持：标题（#/##/###）、段落、Markdown 表格（带框线）、引用块（> 转为缩进段）、
行内粗体（**…**）。用于把装配好的报告渲染成可直接打开/修改/报审的 Word 文档。
"""
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
SRC = WS / "交付物" / "报告" / "上海财经大学中山北一路校区大数据研究中心可行性研究报告（还原稿）.md"
DST = SRC.with_suffix(".docx")

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
FONT = "宋体"
FONT_LAT = "Times New Roman"


def runs(text):
    """行内 **粗体** → run 序列。"""
    out = []
    for i, seg in enumerate(re.split(r"(\*\*[^*]+\*\*)", text)):
        if not seg:
            continue
        bold = seg.startswith("**") and seg.endswith("**")
        t = seg[2:-2] if bold else seg
        rpr = "<w:rPr>" + ("<w:b/>" if bold else "") + \
              f'<w:rFonts w:ascii="{FONT_LAT}" w:eastAsia="{FONT}"/><w:sz w:val="21"/></w:rPr>'
        out.append(f'<w:r>{rpr}<w:t xml:space="preserve">{escape(t)}</w:t></w:r>')
    return "".join(out) or '<w:r><w:t xml:space="preserve"></w:t></w:r>'


def para(text, style=None, align=None, indent=0):
    ppr = "<w:pPr>"
    if style:
        ppr += f'<w:pStyle w:val="{style}"/>'
    if align:
        ppr += f'<w:jc w:val="{align}"/>'
    if indent:
        ppr += f'<w:ind w:left="{indent}"/>'
    ppr += "</w:pPr>"
    return f"<w:p>{ppr}{runs(text)}</w:p>"


def table(rows):
    xs = []
    n = max(len(r) for r in rows)
    xs.append('<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
              '<w:tblW w:w="5000" w:type="pct"/>'
              '<w:tblBorders>'
              + "".join(f'<w:{s} w:val="single" w:sz="4" w:color="808080"/>'
                        for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
              + "</w:tblBorders></w:tblPr>")
    for i, r in enumerate(rows):
        r = list(r) + [""] * (n - len(r))
        xs.append("<w:tr>")
        for cell in r:
            bold = i == 0
            c = cell if bold else cell
            xs.append('<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr>'
                      + para(("**" + c + "**") if (bold and c) else c) + "</w:tc>")
        xs.append("</w:tr>")
    xs.append("</w:tbl>")
    return "".join(xs)


def md_to_body(md):
    lines = md.split("\n")
    body, i = [], 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s\-|:]+\|$", lines[i + 1]):
            rows = []
            hdr = [c.strip() for c in l.strip("|").split("|")]
            rows.append(hdr)
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip().replace("\\|", "|") for c in lines[i].strip("|").split("|")])
                i += 1
            body.append(table(rows))
            continue
        if l.startswith("### "):
            body.append(para(l[4:], style="Heading3"))
        elif l.startswith("## "):
            body.append(para(l[3:], style="Heading2"))
        elif l.startswith("# "):
            body.append(para(l[2:], style="Heading1"))
        elif l.startswith("> "):
            body.append(para(l[2:], indent=420))
        elif l.strip() == "---":
            body.append(para(""))
        elif l.strip():
            body.append(para(l))
        i += 1
    return "".join(body)


STYLES = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W_NS}><w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="{FONT_LAT}" w:eastAsia="{FONT}"/><w:sz w:val="21"/></w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>
<w:pPr><w:spacing w:line="320" w:lineRule="auto" w:after="80"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="180" w:after="90"/><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="140" w:after="70"/><w:outlineLvl w:val="2"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="23"/></w:rPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/></w:style>
</w:styles>'''

CT = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>'''

RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''

DOCRELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

md = SRC.read_text(encoding="utf-8")
body = md_to_body(md)
sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1247" w:bottom="1440" w:left="1247"/></w:sectPr>')
doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
       f'<w:document {W_NS}><w:body>{body}{sect}</w:body></w:document>')

FIXED_TIME = (2020, 1, 1, 0, 0, 0)      # 固定条目时间戳：保证 DOCX 字节级可复现


def _put(z, name, data):
    zi = zipfile.ZipInfo(name, date_time=FIXED_TIME)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    z.writestr(zi, data)


with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as z:
    _put(z, "[Content_Types].xml", CT)
    _put(z, "_rels/.rels", RELS)
    _put(z, "word/document.xml", doc)
    _put(z, "word/styles.xml", STYLES)
    _put(z, "word/_rels/document.xml.rels", DOCRELS)

print({"docx": str(DST.relative_to(WS)), "bytes": DST.stat().st_size,
       "paragraphs": body.count("<w:p>"), "tables": body.count("<w:tbl>")})
