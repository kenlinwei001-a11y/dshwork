# -*- coding: utf-8 -*-
"""判官准确率的【单一事实来源】。

生产者：semantica_rule_judge.py / semantica_judge_test.py
    → 写 <kind>-judge-accuracy.yaml（最新一轮）并追加 judge-accuracy-history.yaml（历史）
消费者：semantica_normalize_queue.py / semantica_report.py / semantica_make_review_md.py
    → 只调用本模块；**任何地方都不得再硬编码准确率数字**

为什么：LLM 判官是随机性的，同一组人工标准答案多轮实测会得到不同的值（见 judge-accuracy-history.yaml）。
单轮值不能当定值用；报告必须给出【实测区间】与【轮数】。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path


def _out(out_dir) -> Path:
    return Path(out_dir)


def latest_path(out_dir, kind: str) -> Path:
    return _out(out_dir) / (kind + "-judge-accuracy.yaml")


def history_path(out_dir) -> Path:
    return _out(out_dir) / "judge-accuracy-history.yaml"


def load_latest(out_dir, kind: str):
    p = latest_path(out_dir, kind)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def append_history(out_dir, kind: str, rec: dict) -> None:
    hp = history_path(out_dir)
    hist = {"entries": []}
    if hp.exists():
        try:
            hist = json.loads(hp.read_text(encoding="utf-8"))
        except Exception:
            hist = {"entries": []}
    entry = {"kind": kind, "date": date.today().isoformat(),
             "at": datetime.now().isoformat(timespec="seconds")}
    entry.update(rec)
    hist.setdefault("entries", []).append(entry)
    hp.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")


def observed_range(out_dir, kind: str):
    hp = history_path(out_dir)
    if not hp.exists():
        return None
    try:
        entries = json.loads(hp.read_text(encoding="utf-8")).get("entries", [])
    except Exception:
        return None
    vals = [e["accuracy"] for e in entries
            if e.get("kind") == kind and isinstance(e.get("accuracy"), (int, float))]
    if not vals:
        return None
    return {"runs": len(vals), "min": min(vals), "max": max(vals), "latest": vals[-1]}


def _precision(detail: list, pred_key: str, pred_val: str):
    xs = [d for d in detail if d.get(pred_key) == pred_val]
    if not xs:
        return None
    return round(sum(1 for d in xs if d.get("hit")) / len(xs), 3)


def stats(out_dir, kind: str) -> dict:
    latest = load_latest(out_dir, kind) or {}
    detail = latest.get("detail") or []
    key = "rule_engine" if kind == "rule" else "llm"
    return {
        "accuracy": latest.get("accuracy"),
        "n": latest.get("n"),
        "same_precision": _precision(detail, key, "SAME"),
        "diff_precision": _precision(detail, key, "DIFF"),
        "range": observed_range(out_dir, kind),
        "source": str(latest_path(out_dir, kind)),
        "note": "LLM 判官存在随机性；须给实测区间与轮数，不得用单轮值冒充定值",
    }


def fmt(out_dir, kind: str, label: str) -> str:
    s = stats(out_dir, kind)
    if s.get("accuracy") is None:
        return label + "：未实测"
    line = "%s **%.1f%%**（%s 组标准答案）" % (label, s["accuracy"] * 100, s.get("n"))
    r = s.get("range")
    if r and r["runs"] > 1:
        line += "，实测区间 %.1f–%.1f%%（%d 轮）" % (r["min"] * 100, r["max"] * 100, r["runs"])
    return line


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    for k, lab in (("rule", "规则判官"), ("llm", "LLM 判官")):
        print(" ", fmt(d, k, lab))
        s = stats(d, k)
        print("    判 SAME 精度:", s["same_precision"], "| 判 DIFF 精度:", s["diff_precision"])



def tier_precision(out_dir, prefix: str = "A"):
    """从 confidence-calibration.yaml 读某分档的实测精度（如 A 档）。"""
    p = _out(out_dir) / "confidence-calibration.yaml"
    if not p.exists():
        return None
    try:
        tp = json.loads(p.read_text(encoding="utf-8")).get("tier_precision", {})
    except Exception:
        return None
    for k, v in tp.items():
        if str(k).strip().startswith(prefix):
            return v
    return None


def tier_fmt(out_dir, prefix: str = "A") -> str:
    v = tier_precision(out_dir, prefix)
    if not v or not v.get("total"):
        return prefix + " 档：样本不足，未校准"
    return "%s 档 %d/%d = %.0f%%" % (prefix, v.get("correct"), v.get("total"),
                                     (v.get("precision") or 0) * 100)
