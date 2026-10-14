# -*- coding: utf-8 -*-
"""实体别名/同义归并（确定性字符串算法，零 LLM）。

为什么需要：实体层若不收敛，「上财」与「上海财经大学」会成为两个节点，
导致关系端点不可寻址、跨文档消歧失效。

两级策略：
  ① 种子别名表（领域词表，人工维护，最高优先）；
  ② 编辑距离近似（difflib.SequenceMatcher，阈值显式）。
**不用模型**：模型会引入不确定判定，而归并是判定层的输入。
"""
from __future__ import annotations

import difflib

# 领域种子别名：canonical → [变体…]
ALIAS_SEED: list[tuple[str, list[str]]] = [
    ("上海财经大学", ["上财", "上海财大", "SUFE", "本校"]),
    ("上海财经大学中山北一路校区", ["中山北一路校区", "中北校区", "北一路校区"]),
    ("本项目", ["本工程", "该项目", "本建设项目"]),
    ("本报告", ["可研报告", "本可行性研究报告"]),
    ("管理科学与量化信息研究中心", ["管理科学与量化信息中心", "量化信息研究中心"]),
    ("理论计算机研究中心", ["理论计算机中心"]),
    ("应用统计研究中心", ["应用统计中心"]),
    ("数据科研与统计研究院", ["统计研究院", "大数据研究院"]),
    ("上海财经大学统计与管理学院", ["统计与管理学院", "统管学院"]),
    ("公共服务配套用房", ["配套用房", "公共服务用房"]),
]


def seed_map() -> dict[str, str]:
    m: dict[str, str] = {}
    for c, alts in ALIAS_SEED:
        m[c] = c
        for a in alts:
            m[a] = c
    return m


def build_alias_map(names, threshold: float = 0.86, min_len: int = 4):
    """把实体名归并到规范名。

    返回 (mapping, groups)：
      mapping: {原名: 规范名}
      groups:  {规范名: [别名…]}（仅含成员数 > 1 的组）

    规则：种子表优先；否则选编辑距离最高且 ≥ threshold、且长度 ≥ min_len 的规范名。
    低于阈值的一律**保持原样**（不强行归并）。
    """
    seed = seed_map()
    canon = [c for c, _ in ALIAS_SEED]
    mapping: dict[str, str] = {}
    for nm in names:
        nm = str(nm).strip()
        if not nm:
            continue
        if nm in seed:
            mapping[nm] = seed[nm]
            continue
        best, bs = nm, 0.0
        for c in canon:
            r = difflib.SequenceMatcher(None, nm, c).ratio()
            if r > bs:
                best, bs = c, r
        mapping[nm] = best if (bs >= threshold and len(nm) >= min_len) else nm
    groups: dict[str, list[str]] = {}
    for k, v in mapping.items():
        groups.setdefault(v, []).append(k)
    return mapping, {c: sorted(ks) for c, ks in groups.items() if len(ks) > 1}


def merge_report(names) -> dict:
    """给出门禁可用的归并统计。"""
    mapping, groups = build_alias_map(names)
    return {"input_names": len(list(names)), "canonical": len(set(mapping.values())),
            "merged_groups": len(groups), "groups": groups,
            "merge_ratio": round(1 - len(set(mapping.values())) / max(len(mapping), 1), 4)}


if __name__ == "__main__":
    names = ["上财", "上海财经大学", "本项目", "本工程", "统管学院",
             "上海财经大学统计与管理学院", "某个无关名字"]
    m, g = build_alias_map(names)
    assert m["上财"] == "上海财经大学" and m["本工程"] == "本项目"
    assert m["统管学院"] == "上海财经大学统计与管理学院"
    assert m["某个无关名字"] == "某个无关名字"
    print("alias.py 自测通过；组:", g)
