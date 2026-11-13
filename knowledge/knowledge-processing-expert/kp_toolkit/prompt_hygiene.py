#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提示词净化：把「实例化提示词」拆成**模板（零项目值）**＋**事实包（本项目值）**。

问题：现提示词里写着「上海财经大学 = 950 人」「本节原文约 1351 字符」
「§3.1.2〔N-9bd50795df49〕」——这些是上财的身份与取值。直接交给写作 agent 写新项目，
模型会把它们当范例复用，等于把上财的数字搬进别的项目。

做法（确定性）：
  to_template()  逐行改写：值 → {{值}}，主体 → {{主体}}，节点 ID → {{节点}}，
                 项目尺度（原文约 N 字符 / M 个切片 / 证据等级计数）→ 占位；
                 保留可复用部分：法定覆盖、标签、技术函数算式、返回契约、约束类型。
  fact_pack()    把被替换掉的东西原样收进事实包（节点ID、主体、谓词、值、单位、定位、证据等级）。
  scan()         对模板做泄漏扫描：项目专名 / 字面数值 / 节点ID / 项目尺度短语，逐类计数并给样例。

判据：模板里**一个上财的具体值都不许留**；留在模板里的数字只允许是
标准号（GB50016-2014）、条款号（5.1.1、表5.1.1）、层级（h2/层级 3）、表号（表N）。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Tuple

NODE_ID_RE = re.compile(r"N-[0-9a-f]{12}")
VALUE_LINE_RE = re.compile(r"^\s{2}·\s")

# 项目专名（换项目时必须改；出现在模板里即为泄漏）
PROJECT_ENTITIES = [
    "上海财经大学", "上财", "中山北一路", "虹口区", "虹口", "赤峰路", "广秀路",
    "广灵一路", "广灵二路", "第五教学楼", "同济工程咨询", "数据科研与统计研究院",
    "应用统计研究中心", "理论计算机研究中心", "管理科学与量化信息研究中心",
    "统计与管理学院", "大数据研究中心", "2019ZX054",
]

# 允许保留在模板里的数字形态（标准号/条款/层级/表号/占位）
ALLOW_NUM_PATTERNS = [
    r"GB\s?/?T?\d{3,5}(?:[-—.]\d{2,4})?",     # GB50016-2014 / GB/T50353-2013
    r"JGJ\s?\d{2,4}(?:[-—]\d{2,4})?",
    r"建标\s?\d{3}(?:[-—]\d{4})?",
    r"第\s?\d+(?:\.\d+)*\s?条",
    r"表\s?\d+(?:[-.]\d+)*",
    r"表N",
    r"层级\s?\d",
    r"h[1-6]",
    r"E[0-5]",
    r"R-[^\s,，、]+",
    r"304\s?号",
]


def _num_is_allowed(token: str, context: str) -> bool:
    for pat in ALLOW_NUM_PATTERNS:
        if re.search(pat, context):
            return True
    return False


EXPR_LINE_RE = re.compile(r"^\s{2}·\s*R-[^:：]+[:：]")


def scan(text: str) -> Dict[str, Any]:
    """泄漏扫描：返回各类命中数与样例（用于「改前/改后」对照）。
    技术函数行里的算式常量（1000/10000/2 等）不算泄漏。"""
    hits: Dict[str, List[str]] = {"项目专名": [], "节点ID": [], "字面数值": [], "项目尺度": []}
    for ent in PROJECT_ENTITIES:
        for m in re.finditer(re.escape(ent), text):
            hits["项目专名"].append(text[max(0, m.start() - 12):m.end() + 12].replace("\n", " "))
    for m in NODE_ID_RE.finditer(text):
        hits["节点ID"].append(text[max(0, m.start() - 12):m.end() + 12].replace("\n", " "))
    for m in re.finditer(r"本节原文约\s*\d+\s*字符|第\s*\d+\s*个切片|本章证据等级分布：(?=\s*[^\{\n])[^\n]*", text):
        hits["项目尺度"].append(m.group(0)[:60].replace("\n", " "))
    for line in text.splitlines():
        if EXPR_LINE_RE.match(line):      # 算式常量豁免
            continue
        if "规范" in line and ("待核" in line or "已核" in line or "部分可核" in line):  # 规范引用行豁免
            continue
        stripped = NODE_ID_RE.sub("{{节点}}", line)   # 节点 ID 是绑定符号，不算数值泄漏
        for m in re.finditer(r"[-+]?\d+(?:\.\d+)?", stripped):
            ctx = stripped[max(0, m.start() - 8):m.end() + 8]
            if _num_is_allowed(m.group(0), ctx):
                continue
            hits["字面数值"].append(ctx.replace("\n", " "))
    return {k: {"count": len(v), "samples": v[:5]} for k, v in hits.items()}


def _split_value_line(line: str) -> Tuple[str, str, str, str, str]:
    """把「· 主体 = 值 ｜ 定位〔ID〕标签」拆成 (主体, 值, 定位, 节点ID, 标签)。"""
    body = VALUE_LINE_RE.sub("", line).strip()
    nid = ""
    m = NODE_ID_RE.search(body)
    if m:
        nid = m.group(0)
        body = body[: m.start()].rstrip() + body[m.end():]
    tag = ""
    m = re.search(r"\[(硬|软)\|[^\]]*\]", body)
    if m:
        tag = m.group(0)
        body = body.replace(tag, "").strip()
    loc = ""
    if "｜" in body:
        body, loc = [x.strip() for x in body.rsplit("｜", 1)]
    loc = re.sub(r"〔\s*〔?|\s*〕", "", loc).strip("〔〕 ")
    if "=" in body:
        subj, val = [x.strip() for x in body.split("=", 1)]
    else:
        subj, val = body, ""
    return subj, val, loc, nid, tag


def to_template(prompt: str, section_meta: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """返回 (模板文本, 事实包条目)。模板里任何一个上财值都不保留。"""
    facts: List[Dict[str, Any]] = []
    out: List[str] = []
    emitted_value_style = False
    for raw in prompt.splitlines():
        line = raw

        # 1 标题行：书名与路径 → 占位
        m = re.match(r"依据脱敏骨架撰写《(.+?)》一节（(.+?)，层级 (\d)）。", line)
        if m:
            out.append("依据本节骨架撰写《{{本节标题}}》（{{章节路径}}，层级 {{层级}}）。")
            continue

        # 2 标签行：保留（属于复用定位，不是项目身份）
        if line.startswith("本项目标签："):
            out.append(line)
            continue

        # 3 项目尺度行
        if re.match(r"本节原文约\s*\d+\s*字符", line):
            out.append("本节骨架规模：{{骨架字数}} 字、{{切片数}} 段；据此控制详略（按目标项目工作包预算校准）。")
            continue

        # 4 事实节点清单标题
        if re.match(r"本节须覆盖\s*\d+\s*条事实节点", line):
            out.append("本节须覆盖 {{事实条数}} 条事实节点，取值唯一来源是本节事实节点表：")
            continue

        # 4.5 论断/证据引文行（含 CL-/EV-/E-/RS- 编号）→ 槽位
        m = re.search(r"〔((?:CL|EV|E|RS|TD)-[^〕]+)〕", line)
        if m and VALUE_LINE_RE.match(line):
            kind = re.match(r"(CL|EV|E|RS|TD)", m.group(1)).group(1)
            out.append("  · {{论断或证据引文}}〔{{%s-ID}}〕" % kind)
            continue

        # 5 取值行 → 槽位化（同一节只留一行样式；兼容非 N- 前缀的绑定号）
        if (VALUE_LINE_RE.match(line) and "=" in line
                and not line.strip().startswith("· R-") and "／" not in line):
            subj, val, loc, nid, tag = _split_value_line(line)
            facts.append({"node": nid, "subject": subj, "value": val, "loc": loc, "tag": tag})
            if not emitted_value_style:
                out.append("  · {{主体}} = {{值}} ｜ 约束 {{约束}} ｜ 定位本节骨架 ｜ 绑定 {{节点}}")
                emitted_value_style = True
            continue

        # 6 「另 N 条」
        if re.match(r"^\s{2}·\s*另\s*\d+\s*条见本节事实表", line):
            continue

        # 7 技术函数清单（保留：R 名属于可复用规则，不是项目值）
        if line.startswith("涉及技术函数："):
            out.append(line)
            continue

        # 8 证据等级分布（计数是项目统计）
        if line.startswith("本章证据等级分布："):
            out.append("本章证据等级分布：{{证据等级分布}}（E1 必须注明提供方与日期；E2 必须带标准号+条款号）")
            continue

        # 8.5 论断行：[claim_type] 论断原文（含项目取值）→ 槽位
        if re.match(r"^\s{2}·\s*\[[a-z_]+\]", line):
            out.append("  · [{{claim_type}}] {{论断原文（数值一律走节点槽位）}}")
            continue

        # 9 冲突行（值全部槽位化）
        if line.strip().startswith("·") and "待审冲突" in line:
            out.append(line)
            continue
        if line.strip().startswith("·") and ("／" in line or "strong" in line or "确认后" in line):
            out.append("  · {{冲突主体}} · {{冲突谓词}}：{{冲突值A}} ／ {{冲突值B}}（待审；处理动作由客户确认后填写）")
            continue

        # 10 其余行：专名还在就槽位化
        for ent in PROJECT_ENTITIES:
            if ent in line:
                line = line.replace(ent, "{{项目专名}}")
        out.append(line)

    return "\n".join(out), facts


def build(corpus: Dict[str, Any], prompts: List[Dict[str, Any]]) -> Dict[str, Any]:
    tpl_pack, fact_pack, report = [], [], {"sections": 0, "before": {}, "after": {}, "residual": []}
    before_total = {"项目专名": 0, "节点ID": 0, "字面数值": 0, "项目尺度": 0}
    after_total = {"项目专名": 0, "节点ID": 0, "字面数值": 0, "项目尺度": 0}
    for p in prompts:
        tpl, facts = to_template(p.get("prompt") or "", p)
        b = scan(p.get("prompt") or "")
        a = scan(tpl)
        for k in before_total:
            before_total[k] += b[k]["count"]
            after_total[k] += a[k]["count"]
        if any(a[k]["count"] for k in a):
            report["residual"].append({"section": p.get("section_no"), "scan": a})
        tpl_pack.append({
            "section_no": p.get("section_no"), "title": "{{本节标题}}", "level": p.get("level"),
            "path": ["{{章节路径}}"], "facts_count": "{{事实条数}}",
            "rules": p.get("rules") or [], "norm_refs": p.get("norm_refs") or [],
            "template": tpl, "return_contract": p.get("return_contract"),
        })
        fact_pack.append({
            "section_no": p.get("section_no"), "title": p.get("title"), "level": p.get("level"),
            "path": p.get("path"), "facts": facts,
            "conflicts": p.get("conflicts") or [], "norm_refs": p.get("norm_refs") or [],
        })
    report["sections"] = len(prompts)
    report["before"], report["after"] = before_total, after_total
    return {"templates": tpl_pack, "facts": fact_pack, "report": report}
