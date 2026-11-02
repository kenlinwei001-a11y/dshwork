# -*- coding: utf-8 -*-
"""entity_derivation —— 从事实主体推导真正的实体（领域词典驱动，确定性，零 LLM）。

## 为什么需要

`instantiate` 只产 facts / rules，**不产 entities**。若用正则从 subject 抠前缀，
会得到「科研」「公共服务配套」这类碎片——因为 subject 是「公共服务配套用房建筑面积」，
前缀不是实体全名。

## 做法：领域词典 + 最长匹配

用**用房类型词典**（来自建标191-2018 与项目类型）匹配 subject 的**最长包含**，
命中即归入该实体；再补「项目」「标准」两类实体，并用关系连起来。

    entities:
      PRJ       项目本体
      USE-xx    用房类型（科研用房 / 研究生用房 / 公共服务配套用房 / 公共配套服务用房）
      STD-xx    依据标准

    relations:
      PRJ  -[has_part]->   USE-xx        项目由哪些用房构成
      USE  -[measured_by]-> 事实         用房类型的规模/指标/负荷
      RULE -[bounded_by]->  STD-xx       规则依据哪个标准

## 用法

    from corpus_pipeline.entity_derivation import derive
    ents, rels = derive(facts, rules, relations_raw, meta)
"""
from __future__ import annotations
import re

# 用房类型词典（可扩展到其他项目类型：实验楼 / 中试基地 / 教学楼）
USE_TYPE_DICT = [
    ("科研用房", ["科研用房", "科研人员用房", "研究用房", "实验室用房"]),
    ("研究生/博士生/访问学者用房", ["研究生/博士生/访问学者用房", "研究生用房", "博士生用房", "访问学者用房"]),
    ("公共服务配套用房", ["公共服务配套用房", "公共服务用房", "配套用房"]),
    ("公共配套服务用房", ["公共配套服务用房", "公共配套用房", "配套服务用房"]),
]

_STD = re.compile(r"((?:GB/T|GB|JGJ/T|JGJ|DGJ\d*|CJJ|CECS|建标)\s*[\d\-—.]*\d\s*[-—]\s*\d{4})")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _match_use_type(subject: str):
    """最长匹配：返回命中的用房类型名（不在词典里返 None）。"""
    s = _norm(subject)
    best = None
    for canon, aliases in USE_TYPE_DICT:
        for a in aliases:
            if a in s and (best is None or len(a) > len(best[1])):
                best = (canon, a)
    return best[0] if best else None


def derive(facts: list, rules: list, relations_raw: list | None = None,
           meta: dict | None = None) -> tuple[list, list]:
    """返回 (entities, relations)。确定性：同输入同输出。"""
    meta = meta or {}
    entities, relations = [], []
    seen = set()

    def add_ent(eid, name, etype, src):
        if eid in seen:
            return
        seen.add(eid)
        entities.append({"id": eid, "name": name, "type": etype, "source": src})

    # ① 项目本体
    add_ent("PRJ", meta.get("title") or "项目", "Project", "§1.1")

    # ② 用房类型（词典命中）
    use_hits = {}
    for f in facts:
        ut = _match_use_type(f.get("subject"))
        if not ut:
            continue
        use_hits.setdefault(ut, []).append(f)
    for i, ut in enumerate(use_hits, start=1):
        eid = "USE-%02d" % i
        add_ent(eid, ut, "UseType", "由事实主体词典匹配")
        relations.append({"id": "RL%03d" % (len(relations) + 1),
                          "from": "PRJ", "to": eid, "type": "has_part",
                          "subject": ut, "payload": {"components": len(use_hits[ut])},
                          "source": {"kind": "ontology"}})
        for f in use_hits[ut]:
            relations.append({"id": "RL%03d" % (len(relations) + 1),
                              "from": eid, "to": f["id"], "type": "measured_by",
                              "subject": f.get("subject"), "payload": {"unit": f.get("unit")},
                              "source": {"kind": "fact_binding"}})

    # ③ 标准实体（从 bounded_by 关系的 payload / source 抠标准号）
    std_hits = {}
    for r in (relations_raw or []):
        if str(r.get("type")) != "bounded_by":
            continue
        pl = r.get("payload") or {}
        src = r.get("source") or {}
        code = pl.get("standard_id") or _STD.search(str(src.get("standard") or pl.get("clause") or ""))
        code = re.sub(r"\s+", "", code if isinstance(code, str) else (code.group(1) if code else ""))
        if code:
            std_hits.setdefault(code, []).append(r.get("subject"))
    for i, code in enumerate(sorted(std_hits), start=1):
        eid = "STD-%02d" % i
        add_ent(eid, code, "Standard", "relations.bounded_by")
        for subj in std_hits[code]:
            relations.append({"id": "RL%03d" % (len(relations) + 1),
                              "from": subj, "to": eid, "type": "bounded_by",
                              "subject": subj, "payload": {"standard_id": code},
                              "source": {"kind": "standard_binding"}})

    # ④ 规则 → 标准（如果 rule 里有 standard_id）
    for r in rules:
        sid = r.get("standard_id")
        if not sid:
            continue
        rid = str(r.get("id"))
        relations.append({"id": "RL%03d" % (len(relations) + 1),
                          "from": rid, "to": sid, "type": "bounded_by",
                          "subject": rid, "payload": {"standard_id": sid},
                          "source": {"kind": "rule_binding"}})

    return entities, relations
