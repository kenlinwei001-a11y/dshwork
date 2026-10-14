# -*- coding: utf-8 -*-
"""源侧索引 source ledger（确定性，零 LLM）。

**为什么这是门禁的前提**：现有校验只遍历**产物**（`for f in ext["facts"]`），
逻辑上不可能发现「属于源 S 而不属于产物 P」的元素。
要让「漏了什么」成为可计算的问题，必须先把源变成**可枚举的索引**。

**必须用与抽取无关的方法生成**：若 ledger 也靠「再读一遍记下来」，
它会继承同一双眼睛的同一盲区，差集恒为空。

方法：正则扫正文 + 解析 docx 的 XML（`word/document.xml`、`word/media/`）。
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

UNIT_PAT = (r"(?:万元|亿元|元/㎡|元|㎡|平方米|米|m|人|个|台|套|座|间|层|kW|kW·h|万kW·h|kWh|"
            r"kPa|Pa|L/s|L／S|m3/h|m³/h|%|kgce|dB)")
CITE_PAT = r"《([^》]{2,80})》"
HEAD_PAT = r"^(#{1,6})\s+(.+?)\s*$"
CAPTION_PAT = r"(表\s?\d+-\d+|图\s?\d+-\d+)"
# 设备铭牌参数（Q/H/N/V、风量、全压、静压、功率…）
DEVICE_PAT = re.compile(r"\bQ\s*=|\bH\s*=|\bN\s*=|风量|全压|静压|IPLV|单台泵流量|有效容积V=|功率[：:]")


def _md_text(md_path: Path) -> str:
    return Path(md_path).read_text(encoding="utf-8")


def build_source_ledger(md_path=None, docx_path=None, *, strict: bool = False) -> dict:
    """生成源侧索引。

    返回键：citations / tables / valued_numbers / headings / captions /
    device_param_lines / images_in_docx / docx_tables / source_sha256
    """
    led: dict = {}
    if md_path:
        text = _md_text(md_path)
    elif docx_path:
        from .docx2md import docx_to_md  # 若上游无此函数，调用方应显式传 md_path
        text = docx_to_md(docx_path)
    else:
        raise ValueError("必须提供 md_path 或 docx_path 之一")

    raw_cites = re.findall(CITE_PAT, text)
    led["citations"] = sorted(set(raw_cites))
    led["citations_raw_count"] = len(raw_cites)
    led["tables"] = len(re.findall(r"```table", text))
    led["valued_numbers"] = sorted(set(f"{v} {u}" for v, u in
                                       re.findall(rf"(\d[\d,]*(?:\.\d+)?)\s*({UNIT_PAT})", text)))
    led["headings"] = [m.group(2).strip() for m in
                       (re.match(HEAD_PAT, l) for l in text.split("\n")) if m]
    led["captions"] = sorted(set(re.findall(CAPTION_PAT, text)))
    led["device_param_lines"] = [l.strip() for l in text.split("\n") if DEVICE_PAT.search(l)]

    led["images_in_docx"], led["docx_tables"] = -1, -1
    if docx_path:
        try:
            with zipfile.ZipFile(docx_path) as z:
                led["images_in_docx"] = len([n for n in z.namelist() if n.startswith("word/media/")])
                xml = z.read("word/document.xml").decode("utf-8", "replace")
                led["docx_tables"] = xml.count("<w:tbl>")
        except Exception as e:                                    # noqa: BLE001
            if strict:
                raise
            led["docx_error"] = str(e)
    return led


def ledger_slice(ledger: dict, headings=None) -> dict:
    """按章切片：门禁在 S3 逐 partition 执行时，只比对该 partition 的引用。"""
    if not headings:
        return ledger
    keys = set(headings)
    return {k: v for k, v in ledger.items() if k not in ("citations", "headings")} | {
        "citations": [c for c in ledger["citations"] if any(h in c for h in keys)] or ledger["citations"],
    }


def save_ledger(ledger: dict, out_path) -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        led = build_source_ledger(md_path=sys.argv[1])
        print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in led.items()},
                         ensure_ascii=False, indent=2))
    else:
        print("用法: python -m corpus_pipeline.source_ledger <md_path>")
