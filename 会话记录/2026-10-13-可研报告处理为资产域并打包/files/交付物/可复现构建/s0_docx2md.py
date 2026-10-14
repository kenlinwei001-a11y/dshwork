# -*- coding: utf-8 -*-
"""工序 1 前置：从原始 docx 确定性重推导文档文本（纯标准库，无第三方依赖）。

必要性：工作区内的中间产物 input/大数据研究中心可研.md 曾被另一进程在本次任务进行中追加
了「附录A（处理者补充）——外部规范与法定大纲核查」，该附录不是原报告内容。为保证
「同输入同输出」与「溯源到原稿」，本脚本只以 build/source-original.docx
（sha256 00d9f1a3…，与用户附件一致）为唯一输入，重新推导段落/标题/表格。

样式映射：w:pStyle val ∈ {1,2,3} → h1/h2/h3（该 docx 的标题样式命名即数字）；
其余样式 → 普通段落。表格 w:tbl → Markdown 管道表格，单元格内换行折叠为空格。
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WS = Path(__file__).resolve().parent.parent
SRC = WS / "build" / "source-original.docx"
OUT = Path(__file__).resolve().parent / "doc-clean"
OUT.mkdir(parents=True, exist_ok=True)

HEADING = {"1": 1, "2": 2, "3": 3}


def para_text(p) -> str:
    parts = []
    for node in p.iter():
        tag = node.tag
        if tag == W + "t" and node.text:
            parts.append(node.text)
        elif tag == W + "tab":
            parts.append("\t")
        elif tag == W + "br":
            parts.append(" ")
    return re.sub(r"[ \u3000]+", " ", "".join(parts)).strip()


def para_style(p):
    pPr = p.find(W + "pPr")
    if pPr is None:
        return None
    ps = pPr.find(W + "pStyle")
    return ps.get(W + "val") if ps is not None else None


def cell_text(tc) -> str:
    return " ".join(para_text(p) for p in tc.findall(W + "p") if para_text(p)).strip()


def table_md(tbl) -> str:
    rows = []
    for tr in tbl.findall(W + "tr"):
        cells = [cell_text(tc) for tc in tr.findall(W + "tc")]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "```table\n" + "\n".join(lines) + "\n```"


z = zipfile.ZipFile(SRC)
root = ET.fromstring(z.read("word/document.xml"))
body = root.find(W + "body")

blocks, n_h, headings_authoritative = [], 0, []
for child in body:
    if child.tag == W + "p":
        t = para_text(child)
        if not t:
            continue
        lvl = HEADING.get(para_style(child) or "")
        if lvl:
            blocks.append("#" * lvl + " " + t)
            headings_authoritative.append((lvl, t))
            n_h += 1
        else:
            blocks.append(t)
    elif child.tag == W + "tbl":
        md = table_md(child)
        if md:
            blocks.append(md)

doc = "\n\n".join(blocks) + "\n"
(OUT / "大数据研究中心可研.md").write_text(doc, encoding="utf-8")

# 权威章节结构：直接取 docx 标题样式（w:pStyle 1/2/3），不用正则猜编号段落，
# 避免把「1.财经特色鲜明…」这类编号列表项误判为标题（kp stage_2 的 _parse_heading 有此缺陷）。
(OUT / "headings.json").write_text(json.dumps(
    [{"block": i, "level": lv, "title": t} for i, (lv, t) in enumerate(headings_authoritative)],
    ensure_ascii=False, indent=1), encoding="utf-8")

sha_docx = hashlib.sha256(SRC.read_bytes()).hexdigest()
sha_md = hashlib.sha256(doc.encode("utf-8")).hexdigest()
report = {"source_docx": SRC.name, "source_docx_sha256": sha_docx,
          "derived_md": "build/doc-clean/大数据研究中心可研.md", "derived_md_sha256": sha_md,
          "chars": len(doc), "blocks": len(blocks), "headings": n_h,
          "h1": sum(1 for b in blocks if b.startswith("# ")),
          "h2": sum(1 for b in blocks if b.startswith("## ")),
          "h3": sum(1 for b in blocks if b.startswith("### ")),
          "tables": sum(1 for b in blocks if b.startswith("```table"))}
(OUT / "derivation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
