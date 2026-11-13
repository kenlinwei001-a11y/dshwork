#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文体抽取与校验：从脱敏骨架里抽出「用词用语习惯」，并可对成稿做机检。

抽什么（全部确定性、可复现）：
  1. 术语/固定搭配：2–8 字 n-gram，按出现频次与分布筛；与项目专名交叉的标 `project_specific`（不可跨项目复用）
  2. 句式起手：段首 6 字以内 + 首个逗号前的引导语（如「经测算」「根据…」），按频次
  3. 段首/段尾套语：段首 4 字、段尾 6 字分布
  4. 格式规则：数字千分位、单位后置、表题写法、人称、禁用词
校验什么：
  style_check(text, pack) → 句长超 P90 句数、禁用词命中、第一人称、无单位裸数、术语覆盖缺口
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from typing import Any, Dict, List

SENT_SPLIT = re.compile(r"(?<=[。；！？])")
NUM_UNIT = re.compile(r"\d[\d,\.]*\s*(万元|㎡|平方米|人|米|%|m³|吨|L/s|kW|元|个|间|层|kN/m2)")
STOP_HEADS = {"本项目", "项目", "本工程", "该", "其", "因此", "所以", "同时", "此外", "另外",
              "综上", "首先", "其次", "最后", "根据", "按照", "依据", "由于", "为了"}


def _paras(sk: List[Dict[str, Any]], min_len: int = 40) -> List[str]:
    return [s["text"] for s in sk if s.get("type") == "paragraph" and len(s.get("text") or "") >= min_len]


def _clean(text: str) -> str:
    return re.sub(r"\{\{[^}]+\}\}", "", text)


FORMAT_RULES = {
    "number": "千分位；单位后置；万元优先；面积用 ㎡；小数位与原文一致",
    "table_caption": "表N-<标题>",
    "person": "第三人称",
    "forbidden": ["大约", "左右（除非带明确区间）", "或许", "较为", "基本上", "原则上"],
}


def _slen(cleaned: List[str]) -> Dict[str, Any]:
    lens = [len(s) for t in cleaned for s in SENT_SPLIT.split(t) if s.strip()]
    return {"avg": round(statistics.mean(lens), 1), "p50": statistics.median(lens),
            "p90": sorted(lens)[max(0, int(len(lens) * 0.9) - 1)]}


def _plen(cleaned: List[str]) -> Dict[str, Any]:
    plen = [len(t) for t in cleaned]
    return {"avg": round(statistics.mean(plen), 1), "p90": sorted(plen)[max(0, int(len(plen) * 0.9) - 1)]}


def _patterns(cleaned: List[str], ents: List[str]) -> List[Dict[str, Any]]:
    heads: Counter = Counter()
    for t in cleaned:
        first = SENT_SPLIT.split(t.strip())[0]
        lead = first.split("，")[0][:14]
        for e in ents:
            lead = lead.replace(e, "{{主体}}")
        if not (2 <= len(lead) <= 14) or "{{主体}}" in lead:
            continue
        if re.fullmatch(r"[\d\s\.\-]+", lead) or "的" in lead or lead.endswith(("内", "是", "将", "为", "在")):
            continue
        heads[lead] += 1
    return [{"lead": k, "freq": v} for k, v in heads.most_common(30) if v >= 2]


def _openers(cleaned: List[str], ents: List[str]) -> List[Dict[str, Any]]:
    def s_(x: str) -> str:
        for e in ents:
            x = x.replace(e, "{{主体}}")
        return x
    c: Counter = Counter(s_(t.strip()[:4]) for t in cleaned if t.strip()[:4] not in STOP_HEADS)
    return [{"head": k, "freq": v} for k, v in c.most_common(15) if v >= 2]


def _closers(cleaned: List[str], ents: List[str]) -> List[Dict[str, Any]]:
    def s_(x: str) -> str:
        for e in ents:
            x = x.replace(e, "{{主体}}")
        return x
    c: Counter = Counter(s_(t.strip()[-8:]) for t in cleaned if len(t.strip()) >= 8)
    return [{"tail": k, "freq": v} for k, v in c.most_common(10) if v >= 2]


def extract(skeletons: List[Dict[str, Any]], project_entities: List[str],
            min_freq: int = 3) -> Dict[str, Any]:
    paras = _paras(skeletons)
    cleaned = [_clean(p) for p in paras]

    # 1) 术语：优先用 jieba 分词 + 词性过滤（名词类），无 jieba 时退化为 n-gram
    try:
        import jieba
        import jieba.posseg as pseg
        KEEP_POS = ("n", "nz", "vn", "an", "ng", "nrt", "ns")
        words: Counter = Counter()
        for t in cleaned:
            for w, flag in pseg.cut(t):
                w = w.strip()
                if len(w) < 3 or any(e in w for e in project_entities):
                    continue
                if flag.startswith(KEEP_POS) and not re.search(r"\d", w):
                    words[w] += 1
        terms = [{"term": w, "freq": c,
                  "project_specific": bool(re.search(r"[市区县]", w)) or any(e in w for e in project_entities)}
                 for w, c in words.most_common(60) if c >= 2]
        lens = [len(t) for t in cleaned]
        return {"corpus_paragraphs": len(paras), "terms": terms,
                "term_count_reusable": sum(1 for x in terms if not x["project_specific"]),
                "term_count_project_specific": sum(1 for x in terms if x["project_specific"]),
                "sentence_patterns": _patterns(cleaned, project_entities),
                "openers": _openers(cleaned, project_entities),
                "closers": _closers(cleaned, project_entities),
                "sentence_len": _slen(cleaned), "paragraph_len": _plen(cleaned),
                "format_rules": FORMAT_RULES}
    except ImportError:
        pass

    grams: Counter = Counter()
    for t in cleaned:
        t = re.sub(r"[^\u4e00-\u9fa5]+", " ", t)
        for seg in t.split():
            L = len(seg)
            for n in range(2, min(9, L + 1)):
                for i in range(L - n + 1):
                    grams[seg[i:i + n]] += 1
    # 去掉被更长高频串包含的短串
    BAD_TAIL = ("的", "了", "是", "在", "对", "将", "为", "和", "与", "及", "或", "等", "建", "有", "应")
    BAD_HEAD = ("的", "了", "和", "与", "及", "或", "等", "其", "该", "此")
    cand = {g: c for g, c in grams.items() if c >= max(min_freq, 4) and 3 <= len(g) <= 8}
    terms = []
    for g, c in sorted(cand.items(), key=lambda kv: (-kv[1], -len(kv[0]))):
        if "的" in g or g.endswith(BAD_TAIL) or g.startswith(BAD_HEAD):
            continue
        if re.search(r"[市区县]|路$|街$", g):      # 地名进项目专属，不进通用词表
            terms.append({"term": g, "freq": c, "project_specific": True})
            continue
        if any(g != h and g in h and cand.get(h, 0) >= c for h in cand):
            continue
        boundary = len(re.findall(r"(?<![\u4e00-\u9fa5])%s(?![\u4e00-\u9fa5])|%s[，。；：、]" % (re.escape(g), re.escape(g)),
                                  "\n".join(cleaned)))
        if boundary < max(2, c * 0.6):
            continue
        terms.append({"term": g, "freq": c, "project_specific": any(e in g for e in project_entities)})
        if len(terms) >= 60:
            break

    # 2) 句式起手：首句前 12 字 + 首个逗号前
    heads = Counter()
    for t in cleaned:
        first = SENT_SPLIT.split(t.strip())[0]
        lead = first.split("，")[0][:14]
        for e in project_entities:          # 引导语里的项目专名一律槽位化
            lead = lead.replace(e, "{{主体}}")
        if not (2 <= len(lead) <= 14):
            continue
        if re.fullmatch(r"[\d\s\.\-]+", lead) or "{{主体}}" in lead:
            continue
        if "的" in lead or lead.endswith(("内", "是", "将", "为", "在")):
            continue
        heads[lead] += 1
    patterns = [{"lead": k, "freq": v} for k, v in heads.most_common(30) if v >= 2]

    # 3) 段首/段尾
    def _scrub(x: str) -> str:
        for e in project_entities:
            x = x.replace(e, "{{主体}}")
        return x

    openers = Counter(_scrub(t.strip()[:4]) for t in cleaned if t.strip()[:4] not in STOP_HEADS)
    closers = Counter(_scrub(t.strip()[-8:]) for t in cleaned if len(t.strip()) >= 8)

    # 4) 句长
    lens = [len(s) for t in cleaned for s in SENT_SPLIT.split(t) if s.strip()]
    plen = [len(t) for t in cleaned]
    return {
        "corpus_paragraphs": len(paras),
        "terms": terms,
        "term_count_reusable": sum(1 for x in terms if not x["project_specific"]),
        "term_count_project_specific": sum(1 for x in terms if x["project_specific"]),
        "sentence_patterns": patterns,
        "openers": [{"head": k, "freq": v} for k, v in openers.most_common(15) if v >= 2],
        "closers": [{"tail": k, "freq": v} for k, v in closers.most_common(10) if v >= 2],
        "sentence_len": {"avg": round(statistics.mean(lens), 1), "p50": statistics.median(lens),
                         "p90": sorted(lens)[max(0, int(len(lens) * 0.9) - 1)]},
        "paragraph_len": {"avg": round(statistics.mean(plen), 1),
                          "p90": sorted(plen)[max(0, int(len(plen) * 0.9) - 1)]},
        "format_rules": {
            "number": "千分位；单位后置；万元优先；面积用 ㎡；小数位与原文一致",
            "table_caption": "表N-<标题>",
            "person": "第三人称",
            "forbidden": ["大约", "左右（除非带明确区间）", "或许", "较为", "基本上", "原则上"],
        },
    }


def style_check(text: str, pack: Dict[str, Any]) -> Dict[str, Any]:
    """对成稿做机检：句长 / 禁用词 / 人称 / 裸数 / 术语覆盖。"""
    sents = [s for s in SENT_SPLIT.split(text) if s.strip()]
    p90 = pack["sentence_len"]["p90"]
    long_sents = [s for s in sents if len(s) > p90]
    forbidden = [w for w in pack["format_rules"]["forbidden"] if w in text]
    first_person = [w for w in ("我们", "我国", "本单位") if w in text]
    bare_nums = NUM_UNIT.findall(text)
    terms = [t["term"] for t in pack["terms"] if not t["project_specific"]][:30]
    hit = [t for t in terms if t in text]
    return {
        "sentence_count": len(sents),
        "sentence_len_avg": round(statistics.mean([len(s) for s in sents]), 1) if sents else 0,
        "over_p90": len(long_sents),
        "over_p90_samples": [s[:40] for s in long_sents[:3]],
        "forbidden_hits": forbidden,
        "first_person": first_person,
        "unit_numbers": len(bare_nums),
        "term_coverage": "%d/%d" % (len(hit), len(terms)),
        "verdict": "pass" if not forbidden and not first_person and len(long_sents) <= max(1, len(sents) // 10) else "review",
    }
