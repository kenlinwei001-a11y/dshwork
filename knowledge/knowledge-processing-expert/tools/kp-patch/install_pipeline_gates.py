# -*- coding: utf-8 -*-
"""install_pipeline_gates —— 第 2 步：把门禁接进流水线（自动跑 + FAIL 阻塞 manifest 状态）。

三处插入，均幂等、均带标记、均自动时间戳备份：

  ① `corpus_pipeline/__init__.py`
     包装 `run_pipeline` —— `corpus_run` 跑完七道工序后**自动**执行
     verify_pipeline + apply_manifest_gate，并把结果并入返回值。
  ② `corpus_pipeline/orchestrator.py`
     包装 `gate_check_draft` —— 编排器每节验收时**自动**附带 section_gate
     （must_cover / facts 引用率 / 占位符形态），FAIL 时把 verdict 降级为 review。
  ③ `mcp/server.py`
     注册 `verify_all` 工具（一次跑完三族门禁 + 写 manifest 状态）。

用法：
    python install_pipeline_gates.py --check
    python install_pipeline_gates.py
    python install_pipeline_gates.py --rollback
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = "/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert"

MARK_INIT = "# --- kp-patch: pipeline gates (auto-run) ---"
MARK_ORCH = "# --- kp-patch: section gate (auto-run) ---"
MARK_TOOL = '"name": "verify_all"'
MARK_DISP = "# --- kp-patch: verify_all dispatch ---"

INIT_SNIPPET = f'''
{MARK_INIT}
# `corpus_run` 跑完七道工序后**自动**执行三族门禁，并按状态机约束写 manifest。
# 原则：判定由门禁做，不由写作/抽取 Agent 自判；有 FAIL 则状态停在 draft，不得进 validated。
_orig_run_pipeline = run_pipeline


def run_pipeline(*args, **kwargs):                 # noqa: F811
    result = _orig_run_pipeline(*args, **kwargs)
    try:
        from .verify_pipeline import apply_manifest_gate, verify_pipeline
        root = kwargs.get("root") or (args[1] if len(args) > 1 else None)
        src = kwargs.get("original_path") or (args[4] if len(args) > 4 else None)
        if root:
            s = str(src) if src else ""
            v = verify_pipeline(root,
                                source_md=s if s.endswith(".md") else None,
                                source_docx=s if s.endswith(".docx") else None)
            result["gate"] = apply_manifest_gate(root, v)
            result["gate"]["detail"] = {{k: v.get(k) for k in
                                        ("verdict", "closure", "stage_gates", "objective",
                                         "blocking_count", "invalid_count")}}
    except Exception as _e:                         # 门禁异常不得吞掉流水线结果，但要显式记录
        result["gate"] = {{"verdict": "error", "error": str(_e),
                          "note": "门禁执行异常，**不得视为通过**"}}
    return result
'''

ORCH_SNIPPET = f'''
{MARK_ORCH}
# 编排器每节验收时自动附带逐节门禁（must_cover / facts 引用率 / 占位符形态）。
_orig_gate_check_draft = gate_check_draft


def gate_check_draft(project_dir, section_id, draft_md):       # noqa: F811
    base = _orig_gate_check_draft(project_dir, section_id, draft_md)
    try:
        from .verify_pipeline import section_gate
        sg = section_gate(project_dir, section_id, draft_md)
        base["section_gate"] = sg
        if sg.get("verdict") == "FAIL":
            base["notes"] = list(base.get("notes") or []) + ["逐节门禁未通过：" + "；".join(sg.get("blocking", []))]
            if base.get("verdict") == "pass":
                base["verdict"] = "review"
    except Exception as _e:
        base["section_gate"] = {{"verdict": "error", "error": str(_e)}}
    return base
'''

DISP_SNIPPET = f'''    {MARK_DISP}
    if name == "verify_all":
        from corpus_pipeline.verify_pipeline import apply_manifest_gate, verify_pipeline
        v = verify_pipeline(args["corpus_dir"], draft_path=args.get("draft_path"),
                            source_md=args.get("source_md"), source_docx=args.get("source_docx"),
                            compile_point=args.get("compile_point"),
                            declared_sha256=args.get("declared_sha256"))
        return {{"verify": v, "manifest": apply_manifest_gate(args["corpus_dir"], v)}}
'''

TOOL = {"name": "verify_all",
        "description": "一次跑完三族门禁（闭环/分步/客观判据），落盘 quality/*.yaml，"
                       "并按状态机写 manifest（FAIL 则停在 draft，不自动 publish）",
        "inputSchema": {"type": "object",
                        "properties": {"corpus_dir": {"type": "string"},
                                       "draft_path": {"type": "string"},
                                       "source_md": {"type": "string"},
                                       "source_docx": {"type": "string"},
                                       "compile_point": {"type": "string"},
                                       "declared_sha256": {"type": "string"}},
                        "required": ["corpus_dir"]}}


def _bk(p: Path) -> str:
    b = p.with_name(p.name + ".bak." + time.strftime("%Y%m%d%H%M%S"))
    shutil.copy2(p, b)
    return str(b)


def _insert(path: Path, mark: str, snippet: str, before_anchor: str | None = None) -> str:
    if not path.exists():
        return "missing"
    s = path.read_text(encoding="utf-8")
    if mark in s:
        return "already"
    _bk(path)
    if before_anchor and before_anchor in s:
        s = s.replace(before_anchor, snippet + before_anchor, 1)
    else:
        s = s.rstrip() + "\n" + snippet
    path.write_text(s, encoding="utf-8")
    return "patched"


def check(t: Path) -> dict:
    init = (t / "corpus_pipeline" / "__init__.py")
    orch = (t / "corpus_pipeline" / "orchestrator.py")
    srv = (t / "mcp" / "server.py")
    return {"verify_pipeline.py": (t / "corpus_pipeline" / "verify_pipeline.py").exists(),
            "init wrapper": MARK_INIT in init.read_text(encoding="utf-8") if init.exists() else "missing",
            "orchestrator wrapper": MARK_ORCH in orch.read_text(encoding="utf-8") if orch.exists() else "missing",
            "verify_all tool": MARK_TOOL in srv.read_text(encoding="utf-8") if srv.exists() else "missing",
            "verify_all dispatch": MARK_DISP in srv.read_text(encoding="utf-8") if srv.exists() else "missing"}


def install(t: Path) -> dict:
    import ast
    out = {}
    # 模块
    src, dst = HERE / "corpus_pipeline" / "verify_pipeline.py", t / "corpus_pipeline" / "verify_pipeline.py"
    if dst.exists() and dst.read_bytes() == src.read_bytes():
        out["verify_pipeline.py"] = "unchanged"
    else:
        if dst.exists():
            _bk(dst)
        shutil.copy2(src, dst)
        out["verify_pipeline.py"] = "installed"
    # ① run_pipeline 包装
    out["init"] = _insert(t / "corpus_pipeline" / "__init__.py", MARK_INIT, INIT_SNIPPET)
    # ② gate_check_draft 包装
    out["orchestrator"] = _insert(t / "corpus_pipeline" / "orchestrator.py", MARK_ORCH, ORCH_SNIPPET)
    # ③ verify_all 工具（schema + dispatch）
    srv = t / "mcp" / "server.py"
    if srv.exists():
        s = srv.read_text(encoding="utf-8")
        if MARK_TOOL not in s:
            anchor = '"name": "provider_status"'
            if anchor in s:
                _bk(srv)
                i = s.rindex("\n", 0, s.index(anchor))
                tool_line = "    " + json.dumps(TOOL, ensure_ascii=False) + ",\n"
                s = s[:i] + "\n" + tool_line + s[i:]
                srv.write_text(s, encoding="utf-8")
                out["tool"] = "patched"
            else:
                out["tool"] = "anchor-missing"
        else:
            out["tool"] = "already"
        out["dispatch"] = _insert(srv, MARK_DISP, DISP_SNIPPET,
                                  before_anchor='    raise ValueError(f"unknown tool {name}")')
        ast.parse(srv.read_text(encoding="utf-8"))
    # 组：verify_all 并入 processing + assembly + verify
    gp = t / "corpus_pipeline" / "groups.py"
    if gp.exists():
        g = gp.read_text(encoding="utf-8")
        if "verify_all" not in g:
            _bk(gp)
            g = g.rstrip() + ('\n# --- kp-patch: verify_all into groups ---\n'
                              'for _g in ("processing", "assembly", "verify"):\n'
                              '    if "verify_all" not in TOOL_GROUPS.get(_g, []):\n'
                              '        TOOL_GROUPS.setdefault(_g, []).append("verify_all")\n')
            gp.write_text(g, encoding="utf-8")
            out["groups"] = "patched"
        else:
            out["groups"] = "already"
    for f in ("corpus_pipeline/__init__.py", "corpus_pipeline/orchestrator.py", "mcp/server.py"):
        ast.parse((t / f).read_text(encoding="utf-8"))
    return out


def rollback(t: Path) -> dict:
    n = 0
    for b in t.rglob("*.bak.*"):
        orig = Path(str(b).split(".bak.")[0])
        shutil.copy2(b, orig)
        b.unlink()
        n += 1
    return {"restored": n}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=DEFAULT)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    a = ap.parse_args()
    t = Path(a.target)
    if a.rollback:
        print(json.dumps(rollback(t), ensure_ascii=False, indent=2)); return 0
    print(json.dumps(check(t) if a.check else install(t), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
