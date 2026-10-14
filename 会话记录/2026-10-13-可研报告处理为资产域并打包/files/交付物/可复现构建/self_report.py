# -*- coding: utf-8 -*-
"""self_report —— 环节**自报**契约（四元交叉中 A 的来源）。

为什么必须由环节自己写（不能由采集器代写）：
  四元交叉的有效性完全取决于来源独立。本会话同一坑踩过两次：
    · B 取「下游自己的产物」→ 与 A 不同源 → 通过率 0%（全 BLOCKED）
    · A 取「采集器观察」  → 与 B 同源   → 通过率 100%（全 CONFIRMED）
  两次都不是逻辑错，而是**源错**：来源相同的两份清单只是同一事实的两种说法，交叉是自证。
  故 A 必须由**被检查方（环节脚本）自己**写出：它"声称"产出了什么。
  harness 只负责扫盘得 B、读内容得 C —— 三者来源不同，交叉才有意义。

契约（文件放 <package>/quality/self_reports/<stage>_self_report.json）：
  { stage, script, declared_outputs: [...], counts: {...}, written_by: "stage:<stage>" }

未写自报的环节 ⇒ within_stage 判 INVALID（**不判 pass**），如实反映"该环节尚未自报"。
"""
from __future__ import annotations

import json
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
PKG = WS / "SHUFE-BDC-2019-001"
SR = PKG / "quality" / "self_reports"


def declare(stage: str, outputs, counts=None, script: str = "") -> dict:
    """由**环节脚本**调用：声明本环节产出了哪些产物。"""
    SR.mkdir(parents=True, exist_ok=True)
    rec = {"stage": stage, "script": script or f"{stage}.py",
           "declared_outputs": sorted(str(o) for o in (outputs or [])),
           "counts": counts or {},
           "written_by": f"stage:{stage}"}
    (SR / f"{stage}_self_report.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec
