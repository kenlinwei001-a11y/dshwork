# -*- coding: utf-8 -*-
"""补齐 MCP 工具注册：TOOLS schema + dispatch 分支 + 分组。

install.py 的第一版只声明了工具名（KP_VERIFY_TOOLS），**没有注册 schema 与 dispatch**，
因此那些工具在 MCP 上不可调用。本脚本补上三处插入（幂等、自动备份）。

用法：
    python install_mcp_tools.py --target <kp_dir> --check
    python install_mcp_tools.py --target <kp_dir>
    python install_mcp_tools.py --target <kp_dir> --rollback
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from install import TOOL_SCHEMA

MARK_TOOLS = '"name": "provider_status"'
MARK_DISPATCH = "# --- kp-patch: verify dispatch ---"
MARK_GROUP = "# --- kp-patch: verify group ---"

TOOLS_ANCHOR = '''    {"name": "validate_source_anchor", "description": "校验 SourceAnchor 定位完整性（document_id 必填 + table_cell/char 精确定位）",
     "inputSchema": {"type": "object",
                     "properties": {"anchor": {"type": "object"}},
                     "required": ["anchor"]}},
]'''

DISPATCH_ANCHOR = '    raise ValueError(f"unknown tool {name}")'

DISPATCH_SNIPPET = f'''    {MARK_DISPATCH}
    if name == "build_source_ledger":
        from corpus_pipeline.source_ledger import save_ledger as _save_ledger
        led = _build_ledger(md_path=args.get("source_md"), docx_path=args.get("source_docx"))
        _save_ledger(led, Path(args["corpus_dir"]) / "source_ledger.json")
        return {{k: (len(v) if isinstance(v, list) else v) for k, v in led.items()}}
    if name == "verify_closure":
        return _closure_verify(args["corpus_dir"], draft_path=args.get("draft_path"))
    if name == "stage_gate":
        return _run_stage_gates(args["corpus_dir"], draft_path=args.get("draft_path"),
                               source_md=args.get("source_md"))
    if name == "objective_verify":
        return _run_objective(args["corpus_dir"], draft_path=args.get("draft_path"),
                              source_md=args.get("source_md"),
                              source_docx=args.get("source_docx"),
                              declared_sha256=args.get("declared_sha256"))
    if name == "apply_claim_relations":
        return _apply_relations(args["corpus_dir"], dry_run=bool(args.get("dry_run")))
    if name == "provider_status":
        return _provider_status()
'''


def _backup(p: Path) -> str:
    """带时间戳备份（修正「已存在则跳过」的缺陷，见 install.py 的说明）。"""
    import time as _t
    b = p.with_name(p.name + ".bak2." + _t.strftime("%Y%m%d%H%M%S"))
    shutil.copy2(p, b)
    return str(b)


def check(target: Path) -> dict:
    srv = target / "mcp" / "server.py"
    grp = target / "corpus_pipeline" / "groups.py"
    s = srv.read_text(encoding="utf-8") if srv.exists() else ""
    g = grp.read_text(encoding="utf-8") if grp.exists() else ""
    return {"tools_registered": MARK_TOOLS in s,
            "dispatch_registered": MARK_DISPATCH in s,
            "group_registered": MARK_GROUP in g,
            "tools_count": s.count('{"name": "')}


def install(target: Path) -> dict:
    out = {}
    srv = target / "mcp" / "server.py"
    s = srv.read_text(encoding="utf-8")

    # ① TOOLS schema
    if MARK_TOOLS in s:
        out["tools"] = "already"
    elif TOOLS_ANCHOR in s:
        _backup(srv)
        block = ",\n".join("    " + json.dumps(t, ensure_ascii=False) for t in TOOL_SCHEMA)
        s = s.replace(TOOLS_ANCHOR, TOOLS_ANCHOR[:-1].rstrip().rstrip(",") + ",\n"
                      + block + "\n]", 1)
        srv.write_text(s, encoding="utf-8")
        out["tools"] = f"patched(+{len(TOOL_SCHEMA)})"
    else:
        out["tools"] = "anchor-missing"

    # ② dispatch
    s = srv.read_text(encoding="utf-8")
    if MARK_DISPATCH in s:
        out["dispatch"] = "already"
    elif DISPATCH_ANCHOR in s:
        _backup(srv)
        s = s.replace(DISPATCH_ANCHOR, DISPATCH_SNIPPET + DISPATCH_ANCHOR, 1)
        srv.write_text(s, encoding="utf-8")
        out["dispatch"] = f"patched(+{len(TOOL_SCHEMA)})"
    else:
        out["dispatch"] = "anchor-missing"

    # ③ group
    grp = target / "corpus_pipeline" / "groups.py"
    g = grp.read_text(encoding="utf-8")
    if MARK_GROUP in g:
        out["group"] = "already"
    else:
        _backup(grp)
        names = ", ".join(f'"{t["name"]}"' for t in TOOL_SCHEMA)
        g = g.rstrip() + f'\n\n{MARK_GROUP}\nTOOL_GROUPS["verify"] = [{names}]\n'
        grp.write_text(g, encoding="utf-8")
        out["group"] = f"patched(+{len(TOOL_SCHEMA)})"
    return out


def rollback(target: Path) -> dict:
    n = 0
    for b in list(target.rglob("*.bak2")):
        shutil.copy2(b, Path(str(b)[:-5]))
        b.unlink()
        n += 1
    return {"restored": n}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    a = ap.parse_args()
    t = Path(a.target)
    if a.rollback:
        print(json.dumps(rollback(t), ensure_ascii=False, indent=2)); return 0
    if a.check:
        print(json.dumps(check(t), ensure_ascii=False, indent=2)); return 0
    print(json.dumps(install(t), ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    sys.exit(main())
