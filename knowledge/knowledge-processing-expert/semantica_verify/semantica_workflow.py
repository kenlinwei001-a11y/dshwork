# -*- coding: utf-8 -*-
"""Semantica 强制工作流：把「必须用 Semantica」写进代码结构，而不是靠声明。

为什么需要它（用户指出的问题）：规则字符串只是【数据】，防不住三件事——
  1. 有人改用手写实现顶替（本项目真实发生过：本地 derive() 冒充 Reasoner）；
  2. provider 静默降级：Semantica 不报错、返回空结果，被记成「成功」；
  3. 漏跑某个环节，事后无从察觉。

本模块用代码封死：
  * 所有 Semantica 调用必须经 semantica_call()，它记账（引擎名/版本/次数）；
  * 每个 Step 跑完必须通过 require() 门禁：要求调用次数下限 + 输出非空；
  * 任一门禁不过 → 抛 WorkflowViolation，工作流【fail-closed】停止，绝不降级续跑；
  * 产物落 semantica-attestation.yaml，记录每步的引擎/版本/输入输出计数/耗时/状态；
  * lint_no_substitute() 扫描目录，发现手写前向链等替身实现即报错。
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

SEMANTICA_VERSION = None


def _version() -> str:
    global SEMANTICA_VERSION
    if SEMANTICA_VERSION is None:
        try:
            import semantica
            SEMANTICA_VERSION = getattr(semantica, "__version__", "?")
        except Exception:
            SEMANTICA_VERSION = "unavailable"
    return SEMANTICA_VERSION


class WorkflowViolation(RuntimeError):
    """门禁未通过：工作流必须停止，不得降级继续。"""


EVIDENCE = {"calls": Counter(), "last_engine": {}, "started": datetime.now().isoformat(timespec="seconds")}


def semantica_call(engine: str, fn, *args, **kwargs):
    """【唯一】允许的 Semantica 调用入口：记账 + 调用 + 记账。"""
    EVIDENCE["calls"][engine] += 1
    EVIDENCE["last_engine"][engine] = _version()
    return fn(*args, **kwargs)


def calls_of(engine: str) -> int:
    return EVIDENCE["calls"].get(engine, 0)


def require(step: str, engines, min_output: int = 1, output_count=None,
            min_calls: int = 1) -> dict:
    """门禁：引擎必须被真实调用过，且输出不得为空（挡住静默降级）。"""
    if isinstance(engines, str):
        engines = [engines]
    detail = {}
    for e in engines:
        c = calls_of(e)
        detail[e] = c
        if c < min_calls:
            raise WorkflowViolation(
                "步骤 [%s] 未真实调用 Semantica 引擎 %s（实际 %d 次 < 要求 %d 次）——禁止降级或替代实现"
                % (step, e, c, min_calls))
    if output_count is not None and output_count < min_output:
        raise WorkflowViolation(
            "步骤 [%s] 输出为空（%d < %d）——疑似 provider 静默降级，工作流停止"
            % (step, output_count, min_output))
    return detail


@dataclass
class Step:
    name: str
    engines: list
    fn: object                    # 可调用：fn() -> 输出（可选返回计数）
    min_output: int = 1
    note: str = ""
    result: dict = field(default_factory=dict)


def run_workflow(steps, out_dir, title: str = "Semantica 强制工作流"):
    """顺序执行步骤；任一门禁不过立即抛错（fail-closed）。返回 attestation。"""
    out = Path(out_dir)
    att = {"title": title, "semantica_version": _version(),
           "started": EVIDENCE["started"], "steps": [], "status": "running"}
    before = Counter(EVIDENCE["calls"])
    for st in steps:
        t0 = time.time()
        rec = {"step": st.name, "engines": st.engines, "note": st.note}
        try:
            out_count = st.fn()
            rec["output_count"] = out_count
            rec["engine_calls"] = require(st.name, st.engines,
                                         output_count=out_count, min_output=st.min_output)
            rec["status"] = "pass"
        except WorkflowViolation:
            rec["status"] = "violation"
            rec["elapsed_s"] = round(time.time() - t0, 2)
            att["steps"].append(rec)
            att["status"] = "failed"
            att["failed_at"] = st.name
            att["finished"] = datetime.now().isoformat(timespec="seconds")
            (out / "semantica-attestation.yaml").write_text(
                json.dumps(att, ensure_ascii=False, indent=2), encoding="utf-8")
            raise
        rec["elapsed_s"] = round(time.time() - t0, 2)
        att["steps"].append(rec)
    after = Counter(EVIDENCE["calls"])
    att["status"] = "pass"
    att["total_calls"] = {k: after[k] - before[k] for k in after}
    att["finished"] = datetime.now().isoformat(timespec="seconds")
    (out / "semantica-attestation.yaml").write_text(
        json.dumps(att, ensure_ascii=False, indent=2), encoding="utf-8")
    return att


FORBIDDEN_PATTERNS = [
    (r"def\s+derive\s*\(", "手写 derive() 前向链"),
    (r"while\s+changed\s*:", "手写不动点前向链循环"),
    (r"def\s+forward_chain\s*\(", "自建 forward_chain"),
    (r"本地实现", "自称『本地实现』的替身"),
    (r"与\s*Semantica\s*Reasoner\s*的规则语义保持一致的本地实现", "显式声明的替身"),
]


def lint_no_substitute(root, exclude=("semantica_workflow.py", "semantica_judge.py")) -> list:
    """扫描目录，发现替身实现即返回违规清单（空列表=通过）。"""
    bad = []
    for p in sorted(Path(root).glob("*.py")):
        if p.name in exclude or p.name.startswith("_"):
            continue
        text = p.read_text(encoding="utf-8")
        for pat, why in FORBIDDEN_PATTERNS:
            for m in re.finditer(pat, text):
                line = text[:m.start()].count("\n") + 1
                bad.append({"file": p.name, "line": line, "pattern": why})
    return bad


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    bad = lint_no_substitute(root)
    if bad:
        print("发现替身实现（违规）：")
        for b in bad:
            print("  %s:%d  %s" % (b["file"], b["line"], b["pattern"]))
        sys.exit(1)
    print("替身检查通过：未发现手写前向链等替代实现")
