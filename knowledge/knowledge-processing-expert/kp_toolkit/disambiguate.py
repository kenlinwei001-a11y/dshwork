# -*- coding: utf-8 -*-
"""kp_toolkit.disambiguate —— 消歧（确定性，零 LLM）

抽取后、冲突检测前的必做环节。四类消歧：
  ① 主体消歧  subject 为「本项目」或主体识别错 → 从上下文补
  ② 型号消歧  同一名称多个规格被抽成同一 subject → 加唯一标识
  ③ 表述消歧  ≤70 / 约2300 → 归一化，原表述存 raw_value
  ④ 版本消歧  同一标准多版本 → 判定应用哪版，标 report_fix

实测：15 条「冲突」里 9 条是消歧缺失造成的噪声。
"""
import re
from collections import defaultdict

PREFIX = re.compile(r"^(≤|≥|约|不小于|不大于|不超过|不低于)\s*")
GENERIC = {"本项目", "该项目", "本工程", "本报告", "本项目工程"}

# 旧版 → 现行版（版本消歧用）
SUPERSEDED = {
    "GB50673-2002": ("GB50763-2012", "已废止"),
    "JGJ50-2001": ("GB50763-2012", "旧行业标准，已被国家标准替代"),
    "GB50034-2004": ("GB50034-2013", "新版替代"),
    "GB50019-2003": ("GB50736-2012", "暖通部分已并入 GB50736-2012"),
    "GB50189-2005": ("GB50189-2015", "新版替代"),
    "DGJ08-107-2012": ("DGJ08-107-2015", "新版替代"),
    "建筑规划面积指标": ("建筑面积指标", "2018 版正式名称为「建筑面积指标」"),
}


def normalize_value(v):
    """表述消歧：返回 (归一化值, 原表述或None)"""
    s = str(v or "").strip()
    m = PREFIX.match(s)
    if not m: return s, None
    return s[m.end():].strip(), s


def is_generic_subject(subj):
    return str(subj or "").strip() in GENERIC


def infer_subject(node, chunk_text, window=120):
    """主体消歧：从数值在原文中的位置附近推断真实主体

    返回 (subject, evidence) 或 (None, None)
    """
    v = str(node.get("value") or "")
    if not v or not chunk_text: return None, None
    i = chunk_text.find(v)
    if i < 0: return None, None
    # 关键：取「数值位置之前」的文本，不是整个上下文的前 window 字
    before = chunk_text[max(0, i - window):i]
    ctx = chunk_text[max(0, i - window):i + window]
    # 「X：35」或「X = 35」
    m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{2,14})\s*[：:=]\s*[^，。；]{0,10}$", before)
    if m: return m.group(1).strip(), ctx
    # 「X为 35」「X取 35」
    m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{2,14})\s*(?:为|是|取|达到|控制在)\s*$", before)
    if m: return m.group(1).strip(), ctx
    # 「X的 … 35」取最后一个名词
    m = re.search(r"([\u4e00-\u9fa5]{2,10})的[^，。；]{0,12}$", before)
    if m: return m.group(1).strip(), ctx
    return None, None


def group_variants(nodes, base_of=None):
    """型号消歧：按基础名称分组，返回 {base: [node,...]}"""
    g = defaultdict(list)
    for n in nodes:
        subj = str(n.get("subject") or "")
        base = base_of(subj) if base_of else subj.split("（")[0]
        g[base].append(n)
    return {k: v for k, v in g.items() if len(v) > 1}


def apply_model_tags(nodes, table_rows, base_of=None, key_field="air"):
    """型号消歧：按表格行给节点加型号标识

    table_rows: [{"no","name","air","cool","heat","power","qty"}]
    返回被修改的节点数
    """
    by_name = defaultdict(list)
    for r in table_rows: by_name[r["name"]].append(r)
    fixed = 0
    for n in nodes:
        subj = str(n.get("subject") or "")
        base = base_of(subj) if base_of else subj.split("（")[0]
        if "（" in subj: continue
        variants = by_name.get(base) or []
        if len(variants) <= 1: continue
        v = str(n.get("value") or "")
        hit = next((r for r in variants
                    if v in (r.get("cool"), r.get("heat"), r.get("power"))), None)
        if not hit: continue
        tag = f"风量{hit['air']}m³/h" if hit.get(key_field) else f"序号{hit['no']}"
        n["subject"] = f"{base}（{tag}）"
        n["model_variant"] = {k: hit.get(k) for k in ("no", "air", "cool", "heat", "power", "qty")}
        fixed += 1
    return fixed


def resolve_version(code_or_name):
    """版本消歧：返回 (应使用版本, 理由) 或 (None, None)"""
    s = str(code_or_name or "")
    for old, (new, why) in SUPERSEDED.items():
        if old in s: return new, why
    return None, None


def disambiguate(nodes, chunk_text_of=None, table_rows=None, base_of=None):
    """一键四类消歧，返回统计"""
    stat = {"value_normalized": 0, "subject_fixed": 0, "model_tagged": 0, "version_hint": 0}
    # ③ 表述
    for n in nodes:
        v, raw = normalize_value(n.get("value"))
        if raw:
            n["raw_value"] = raw; n["value"] = v; stat["value_normalized"] += 1
    # ① 主体
    if chunk_text_of:
        for n in nodes:
            if not is_generic_subject(n.get("subject")): continue
            cid = (n.get("anchor") or {}).get("slice_id") or n.get("source")
            subj, ev = infer_subject(n, chunk_text_of(cid) if cid else "")
            if subj and subj not in GENERIC:
                n["subject_before_disamb"] = n.get("subject")
                n["subject"] = subj
                n["subject_evidence"] = ev
                stat["subject_fixed"] += 1
    # ② 型号
    if table_rows:
        stat["model_tagged"] = apply_model_tags(nodes, table_rows, base_of)
    # ④ 版本（只提示，不改节点）
    for n in nodes:
        use, why = resolve_version(n.get("subject"))
        if use:
            n["version_should_use"] = use; n["version_note"] = why
            stat["version_hint"] += 1
    return stat
