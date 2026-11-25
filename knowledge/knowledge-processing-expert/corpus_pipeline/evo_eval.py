# -*- coding: utf-8 -*-
"""evo_eval —— 抽取精度评测（标注集 → precision / recall / F1）。

## 为什么

那个 agent 自己承认：「正则精度还没有被系统性度量；没有标注集 → precision/recall 的评分」。

本模块把这件事做实：**用人工核对过的 gate_inputs.json 当金标准**，
测 `collect_values` 抽得准不准。

## 指标

    TP 抽到且值对      FP 抽到但值错      FN 该有但没抽
    Precision = TP/(TP+FP)        「抽到的有多准」
    Recall    = TP/(TP+FN)        「该抽的抽到多少」
    F1        = 2PR/(P+R)

## 阈值（不达标不放行）

    Precision >= 0.95   误报多 → 下游会拿错值算
    Recall    >= 0.70   漏太多 → 大量 UNVERIFIABLE
    F1        >= 0.80

**Precision 比 Recall 严** —— 宁可漏抽（门禁报 UNVERIFIABLE），不要抽错（门禁假 PASS）。
"""
from __future__ import annotations
import json
from pathlib import Path

THRESH = {"precision": 0.95, "recall": 0.70, "f1": 0.80}
EPS = 1e-6


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def evaluate(workspace, version: str = "", *, gold_inputs=None,
             extractor=None) -> dict:
    """用金标准测抽取器。gold_inputs 可传 dict 或 json 路径。"""
    ws = Path(workspace)
    ver = version or json.loads((ws/"active.json").read_text(encoding="utf-8"))["active_version"]
    terms = json.loads((ws/"versions"/ver/"terms.json").read_text(encoding="utf-8"))

    if extractor is None:
        from corpus_pipeline.evo_gate_engine import collect_values
        extractor = collect_values
    got = extractor(terms)
    mine = got[0] if isinstance(got, tuple) else got

    gi = gold_inputs
    if isinstance(gi, (str, Path)):
        gi = json.loads(Path(gi).read_text(encoding="utf-8"))
    gold = (gi.get("inputs") if isinstance(gi, dict) and "inputs" in gi else gi) or {}

    gnum = {k: _num(v) for k, v in gold.items() if _num(v) is not None}
    mnum = {k: _num(v) for k, v in mine.items() if _num(v) is not None}

    common = [k for k in gnum if k in mnum]
    tp = [k for k in common if abs(mnum[k] - gnum[k]) < EPS]
    fp = [{"key": k, "mine": mnum[k], "gold": gnum[k]}
          for k in common if k not in tp]
    fn = [k for k in gnum if k not in mnum]

    p = len(tp) / len(common) if common else 0.0
    r = len(tp) / len(gnum) if gnum else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    verdicts = {
        "precision": "PASS" if p >= THRESH["precision"] else "FAIL",
        "recall": "PASS" if r >= THRESH["recall"] else "FAIL",
        "f1": "PASS" if f1 >= THRESH["f1"] else "FAIL",
    }
    return {"version": ver,
            "gold_count": len(gnum), "mine_count": len(mnum), "overlap": len(common),
            "tp": len(tp), "fp": len(fp), "fn": len(fn),
            "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4),
            "thresholds": THRESH, "verdicts": verdicts,
            "fp_detail": fp[:15], "fn_detail": fn[:15],
            "ok": all(v == "PASS" for v in verdicts.values())}
