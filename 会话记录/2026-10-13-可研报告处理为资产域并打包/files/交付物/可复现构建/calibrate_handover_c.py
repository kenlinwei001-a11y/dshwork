# -*- coding: utf-8 -*-
"""calibrate_handover_c —— 对「环节之间」C 比对做**探针标定**。

原则（本会话确立）：**未标定的探针/扫描器/审计不得采信，必须先用已知正样本对齐。**
C 比对此前从未被反证过 —— 本脚本为它构造已知正/负样本，测 recall 与 precision。

被测判据：
  C_internal_contradiction  C 自述状态与门禁结论矛盾（status=validated 而 verdict=blocked）
  C_count_mismatch          C 自述计数与内容实际计数不符

做法：备份 → 注入偏差 → 跑 compare → 判定是否命中 → 还原。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
PKG = WS / "SHUFE-BDC-2019-001"
sys.path.insert(0, str(WS / "build"))
import handover as HO  # noqa: E402


def _backup(paths):
    tmp = Path(tempfile.mkdtemp())
    for p in paths:
        if p.exists():
            shutil.copy2(p, tmp / p.name)
    return tmp


def _restore(paths, tmp):
    for p in paths:
        if (tmp / p.name).exists():
            shutil.copy2(tmp / p.name, p)


def run() -> dict:
    stage = "s5a"                        # 有依赖的环节，compare 会逐依赖核对
    dep = "s4b"
    mf = PKG / "manifest.yaml"
    vp = PKG / "quality" / "verify_pipeline.yaml"
    # C 读的是各依赖声明产物里的自述元数据；此处直接测 compare 的 C 分支
    entry = {"id": stage, "outputs": [], "depends_on": [dep]}
    upstream = {dep: {"id": dep, "outputs": [
        "SHUFE-BDC-2019-001/manifest.yaml", "SHUFE-BDC-2019-001/quality/verify_pipeline.yaml",
        "SHUFE-BDC-2019-001/quality/gaps_unmodeled_values.json"]}}
    # 给该依赖造一份 A（自报），使 compare 能取到 A 分支
    d = HO.HD / stage; d.mkdir(parents=True, exist_ok=True)

    res = {"checks": [], "stage": stage, "dep": dep}

    # ── 负样本（基线）：不应报任何 C 类差异 ────────────────────────
    base = HO.compare(entry, upstream)
    ck = [x for x in base["diffs"] if x["kind"].startswith("C_")]
    res["checks"].append({"case": "基线（未注入）", "expect": "不命中", "got": len(ck),
                          "ok": len(ck) == 0, "kinds": [x["kind"] for x in ck]})

    # ── 正样本 1：C_internal_contradiction（status=validated 而 verdict=blocked）──
    tmp = _backup([mf, vp])
    try:
        if vp.exists():
            j = json.loads(vp.read_text(encoding="utf-8"))
            j["verdict"] = "blocked"
            vp.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
        got = HO.compare(entry, upstream)
        ck = [x for x in got["diffs"] if x["kind"] == "C_internal_contradiction"]
        res["checks"].append({"case": "注入：manifest=validated 且 verdict=blocked",
                              "expect": "命中 C_internal_contradiction", "got": len(ck),
                              "ok": len(ck) > 0, "kinds": [x["kind"] for x in ck]})
    finally:
        _restore([mf, vp], tmp)

    # ── 正样本 2：C_count_mismatch（自述计数 vs 实际计数）──────────
    # 选一个自述 count 的产物，改其 count 字段
    gap = PKG / "quality" / "gaps_unmodeled_values.json"
    if gap.exists():
        tmp2 = _backup([gap])
        try:
            j = json.loads(gap.read_text(encoding="utf-8"))
            real = j.get("count")
            j["count"] = (int(real) if isinstance(real, int) else 0) + 7   # 注入偏差
            gap.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
            got = HO.compare(entry, upstream)
            ck = [x for x in got["diffs"] if x["kind"] == "C_self_inconsistent"]
            res["checks"].append({"case": "注入：产物自述 count 偏 +7",
                                  "expect": "命中 C_self_inconsistent", "got": len(ck),
                                  "ok": len(ck) > 0, "kinds": [x["kind"] for x in ck]})
        finally:
            _restore([gap], tmp2)

    fired = [c for c in res["checks"] if c["got"] > 0]
    res["summary"] = {
        "cases": len(res["checks"]),
        "fired": len(fired),
        "recall_on_positive": (sum(1 for c in res["checks"]
                                   if c["expect"].startswith("命中") and c["ok"])
                               / max(sum(1 for c in res["checks"] if c["expect"].startswith("命中")), 1)),
        "false_positive_on_baseline": (sum(1 for c in res["checks"]
                                           if c["expect"] == "不命中" and not c["ok"])
                                       / max(sum(1 for c in res["checks"] if c["expect"] == "不命中"), 1)),
        "verdict": "calibrated" if all(c["ok"] for c in res["checks"]) else "NOT_CALIBRATED",
    }
    (PKG / "quality" / "calibration_handover_c.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = run()
    print(json.dumps(r["summary"], ensure_ascii=False, indent=2))
    for c in r["checks"]:
        print(f"  {'✅' if c['ok'] else '❌'} {c['case'][:44]:46s} 期望 {c['expect']:24s} 实际 {c['got']}")
