# -*- coding: utf-8 -*-
"""claim 级关系扩展与「应有关系」推导（确定性，零 LLM）。

**为什么需要**：上游 `TEN_RELATIONS` 只覆盖事实/实体关系，没有
`cites`（引用）/ `restates`（复述）/ `causes`（因果）/ `derives`（派生）等
**论断间关系**。词表缺项的直接后果是 `premise_refs` / `derived_from` 字段空置——
不是不想填，是**没有可填的语义槽**。

本模块提供两件事：
  ① `CLAIM_RELATIONS`：7 类 claim 级关系词表（对上游 TEN_RELATIONS 的扩展）；
  ② `derive_expected_relations()`：由 claim 文本**规则化地推出应有关系**，
     与图谱现有边求差，得到「缺边清单」——即 C7 闭环的输入。

**全程不含 LLM**：判据是「文本含《…》/GB 编号 ⇒ 应有 cites」这类可判定规则。
"""
from __future__ import annotations

import re

CLAIM_RELATIONS: dict[str, str] = {
    "cites": "claim → mandate/standard：这条结论依据哪条规范",
    "restates": "claim → claim：总论/结论复述各章结论",
    "causes": "claim → claim：因果链条",
    "derives": "claim → claim：显式推演派生",
    "precedes": "claim → claim：论证顺序/前置条件",
    "quantifies": "claim → node：结论与其数值绑定",
    "specializes": "claim → mandate：通则落到本项目",
}

CITE_PAT = re.compile(r"《[^》]+》|\bGB[/\s]?\d|GB\d|DGJ\d|JGJ\d|建标|发改|国发|财建|〔\d{4}〕|\[\d{4}\]")
CAUSE_PAT = re.compile(r"因此|因而|故而|导致|使得|引起|造成|从而使|以致")
RESTATE_CH = {"总论", "结论与建议", "结论"}


def _blob(c: dict) -> str:
    t = c.get("toulmin") or {}
    return " ".join(str(t.get(k, "")) for k in
                    ("claim", "grounds", "warrant", "backing", "qualifier", "rebuttal")) \
        + " " + str(c.get("text", ""))


def nums_of(s) -> set[str]:
    """取显著数字（≥3 位），用于判定复述/派生。1–2 位数字噪声太大，排除。"""
    return {x for x in re.findall(r"\d[\d,]*(?:\.\d+)?", str(s)) if len(x.replace(",", "")) >= 3}


def derive_expected_relations(claims: list[dict], relations: list[dict] | None = None) -> dict:
    """推出「应有关系」，并给出候选边与缺口。

    返回：{expected: {type: n}, candidates: {type: [edge…]}, missing: {type: n}}
    """
    rels = relations or []
    have = {}
    for r in rels:
        have[r.get("type")] = have.get(r.get("type"), 0) + 1

    cand: dict[str, list[dict]] = {k: [] for k in CLAIM_RELATIONS}
    in_restate_ch = [c for c in claims if _chapter_of(c) in RESTATE_CH]

    for c in claims:
        b = _blob(c)
        # cites
        for cite in sorted(set(CITE_PAT.findall(b))):
            cand["cites"].append({"from": c.get("id"), "to": f"REF:{cite[:40]}",
                                  "type": "cites", "basis": cite})
        # restates：总论/结论的论断与各章论断共享显著数字
        if _chapter_of(c) in RESTATE_CH:
            na = nums_of(b)
            for o in claims:
                if o.get("id") == c.get("id") or _chapter_of(o) in RESTATE_CH:
                    continue
                sh = na & nums_of(_blob(o))
                if sh:
                    cand["restates"].append({"from": c.get("id"), "to": o.get("id"),
                                             "type": "restates", "why": f"共享数值 {sorted(sh)}"})
                    break
        # causes / derives：共享数字 + 因果词
        na = nums_of(b)
        for o in claims:
            if o.get("id") == c.get("id"):
                continue
            sh = na & nums_of(_blob(o))
            if not sh:
                continue
            if CAUSE_PAT.search(b):
                cand["causes"].append({"from": c.get("id"), "to": o.get("id"),
                                       "type": "causes", "why": f"因果词+共享 {sorted(sh)}"})
            if not (c.get("premise_refs") or c.get("derived_from")):
                cand["derives"].append({"from": c.get("id"), "to": o.get("id"),
                                        "type": "derives", "why": f"共享 {sorted(sh)}"})

    expected = {k: len(v) for k, v in cand.items() if v}
    return {"expected": expected,
            "candidates": cand,
            "have": have,
            "missing": {k: max(v - have.get(k, 0), 0) for k, v in expected.items()},
            "vocabulary": CLAIM_RELATIONS}


def _chapter_of(c: dict) -> str:
    sp = c.get("section_path") or []
    if sp:
        return sp[0]
    return c.get("chapter") or c.get("restated_chapter") or ""


def apply_expected_relations(corpus_dir, *, dry_run: bool = False) -> dict:
    """把候选边合并进 graph/relations.yaml（幂等：按 (from,to,type) 去重）。"""
    import json
    from pathlib import Path
    root = Path(corpus_dir)
    claims = json.loads((root / "graph" / "claims.yaml").read_text(encoding="utf-8"))
    rels = json.loads((root / "graph" / "relations.yaml").read_text(encoding="utf-8"))
    res = derive_expected_relations(claims, rels)
    seen = {(r.get("from"), r.get("to"), r.get("type")) for r in rels}
    added = []
    for t, edges in res["candidates"].items():
        for e in edges:
            k = (e["from"], e["to"], t)
            if k in seen:
                continue
            seen.add(k)
            added.append({**e, "type": t})
    if not dry_run and added:
        rels.extend(added)
        (root / "graph" / "relations.yaml").write_text(
            json.dumps(rels, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"added": len(added), "by_type": {t: sum(1 for a in added if a["type"] == t)
                                             for t in CLAIM_RELATIONS},
            "expected": res["expected"], "missing_after": res["missing"]}


if __name__ == "__main__":
    import json
    print(json.dumps(CLAIM_RELATIONS, ensure_ascii=False, indent=2))
