# -*- coding: utf-8 -*-
"""安装器：把本次优化落到上游 kp 工程（新增模块 + 最小侵入补丁）。

用法：
    python install.py --check                 # 只体检，不写
    python install.py --target <kp_dir>       # 实际安装（自动备份 .bak）
    python install.py --target <kp_dir> --rollback

设计原则：
  · **优先新增文件**，修改现有文件仅限三处，且每处都是「插入一段」而非重写；
  · 每次修改前备份 `<file>.bak`；rollback 从备份恢复；
  · 幂等：重复运行不会重复插入（靠标记串判定）。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ["units.py", "alias.py", "source_ledger.py", "closure_verify.py",
           "stage_gates.py", "objective_criteria.py", "relations_ext.py", "providers.py"]

MARK_ONTO = "# --- kp-patch: claim-level relations (append-only) ---"
MARK_SPEC = "# --- kp-patch: extended contract files ---"
MARK_MCP = "# --- kp-patch: verification tools ---"

ONTO_SNIPPET = f'''
{MARK_ONTO}
# 论断级关系词表扩展。上游 TEN_RELATIONS 只覆盖事实/实体关系，
# 缺 cites/restates/causes/derives 等，导致 premise_refs/derived_from 无从填充。
try:
    from .relations_ext import CLAIM_RELATIONS as _CLAIM_RELATIONS
    RELATION_TYPES = sorted(set(RELATION_TYPES) | set(_CLAIM_RELATIONS)) \\
        if isinstance(globals().get("RELATION_TYPES"), (list, set, tuple)) else _CLAIM_RELATIONS
except Exception:                       # pragma: no cover
    _CLAIM_RELATIONS = {{}}
'''

SPEC_SNIPPET = f'''
{MARK_SPEC}
# 契约扩展（30 → 32）：句子层与源侧索引。
# sentences.jsonl：Claim 追踪的最小单位；source_ledger.json：闭环校验的源侧索引。
EXTENDED_CONTRACT_FILES = ["chunks/sentences.jsonl", "source_ledger.json"]
'''

MCP_SNIPPET = f'''
{MARK_MCP}
# 校验类工具（客观判据；判定不消费 LLM 的意见）
try:
    from corpus_pipeline.source_ledger import build_source_ledger as _build_ledger
    from corpus_pipeline.closure_verify import closure_verify as _closure_verify
    from corpus_pipeline.stage_gates import run_stage_gates as _run_stage_gates
    from corpus_pipeline.objective_criteria import run_objective_criteria as _run_objective
    from corpus_pipeline.relations_ext import apply_expected_relations as _apply_relations
    from corpus_pipeline.providers import provider_status as _provider_status
    KP_VERIFY_TOOLS = ["build_source_ledger", "verify_closure", "stage_gate",
                       "objective_verify", "apply_claim_relations", "provider_status"]
except Exception:                       # pragma: no cover
    KP_VERIFY_TOOLS = []
'''

TOOL_SCHEMA = [
    {"name": "build_source_ledger",
     "description": "生成源侧索引（引用/表/带单位数值/标题/题注/设备参数）。门禁前提。",
     "inputSchema": {"type": "object", "properties": {
         "corpus_dir": {"type": "string"}, "source_md": {"type": "string"},
         "source_docx": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "verify_closure",
     "description": "七道闭环校验：源侧索引 − 产物 − 豁免 = ∅。missing 非空即 FAIL。",
     "inputSchema": {"type": "object", "properties": {
         "corpus_dir": {"type": "string"}, "draft_path": {"type": "string"}},
         "required": ["corpus_dir"]}},
    {"name": "stage_gate",
     "description": "分步门禁 S0–S11（含探针正样本标定；未标定判 invalid）。",
     "inputSchema": {"type": "object", "properties": {
         "corpus_dir": {"type": "string"}, "draft_path": {"type": "string"},
         "source_md": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "objective_verify",
     "description": "12 条客观判据（确定性算法）；无法客观化者标 judgment_required。",
     "inputSchema": {"type": "object", "properties": {
         "corpus_dir": {"type": "string"}, "draft_path": {"type": "string"},
         "source_md": {"type": "string"}, "source_docx": {"type": "string"},
         "declared_sha256": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "apply_claim_relations",
     "description": "按规则推导应有 claim 关系并合并入图（幂等；dry_run 支持）。",
     "inputSchema": {"type": "object", "properties": {
         "corpus_dir": {"type": "string"}, "dry_run": {"type": "boolean"}},
         "required": ["corpus_dir"]}},
    {"name": "provider_status",
     "description": "可替换环节（entity/relation/reasoning/graph）的 provider 与能力表；"
                    "供门禁判断判据可用性（缺能力 ⇒ invalid，不得 pass）。",
     "inputSchema": {"type": "object", "properties": {}}},
]


def check(target: Path) -> dict:
    r = {"target": str(target), "exists": target.exists(), "modules_present": [], "patches": {}}
    if not target.exists():
        return r
    cp = target / "corpus_pipeline"
    r["modules_present"] = [m for m in MODULES if (cp / m).exists()]
    r["modules_missing"] = [m for m in MODULES if not (cp / m).exists()]
    onto = (cp / "ontology.py")
    spec = (cp / "spec.py")
    mcp = target / "mcp" / "server.py"
    r["patches"] = {
        "ontology.py": (MARK_ONTO in onto.read_text(encoding="utf-8")) if onto.exists() else "missing",
        "spec.py": (MARK_SPEC in spec.read_text(encoding="utf-8")) if spec.exists() else "missing",
        "mcp/server.py": (MARK_MCP in mcp.read_text(encoding="utf-8")) if mcp.exists() else "missing",
        "mcp-config tools 段": "todo",
    }
    cfg = target / "mcp" / "mcp-config.json"
    if cfg.exists():
        try:
            j = json.loads(cfg.read_text(encoding="utf-8"))
            tools = j.get("tools", {})
            r["patches"]["mcp-config tools 段"] = (
                "done" if any("verify_closure" in (v or []) for v in tools.values()) else "todo")
        except Exception as e:                                   # noqa: BLE001
            r["patches"]["mcp-config tools 段"] = f"parse error: {e}"
    return r


def _backup(p: Path) -> str:
    """带时间戳备份。

    修正记录：原实现为「`.bak` 已存在则跳过」，导致若目录里已有旧 `.bak`
    （本项目里 4 个文件的 `.bak` 分别是 Sep 23 / Oct 9 / Oct 10），
    就**没有记录补丁前的真实状态**；据此回滚会一并擦除这些日期之后的
    其它改动（包括并行进行的 semantica 接入工作）。
    现在一律写 `<file>.bak.<YYYYmmddHHMMSS>`，绝不跳过。
    """
    import time as _t
    b = p.with_name(p.name + ".bak." + _t.strftime("%Y%m%d%H%M%S"))
    shutil.copy2(p, b)
    return str(b)


def _patch(path: Path, mark: str, snippet: str, anchor: str | None = None) -> str:
    """在文件中插入片段（幂等）。anchor 为插入点前的锚串；None 表示追加到末尾。"""
    if not path.exists():
        return "missing"
    s = path.read_text(encoding="utf-8")
    if mark in s:
        return "already"
    _backup(path)
    if anchor and anchor in s:
        s = s.replace(anchor, anchor + "\n" + snippet, 1)
    else:
        s = s.rstrip() + "\n" + snippet + "\n"
    path.write_text(s, encoding="utf-8")
    return "patched"


def _patch_mcp_config(path: Path) -> str:
    if not path.exists():
        return "missing"
    j = json.loads(path.read_text(encoding="utf-8"))
    tools = j.setdefault("tools", {})
    if any("verify_closure" in (v or []) for v in tools.values()):
        return "already"
    _backup(path)
    tools["verify"] = [t["name"] for t in TOOL_SCHEMA]
    path.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
    return "patched"


def install(target: Path) -> dict:
    cp = target / "corpus_pipeline"
    cp.mkdir(parents=True, exist_ok=True)
    out = {"modules": {}, "patches": {}}
    for m in MODULES:
        src, dst = HERE / "corpus_pipeline" / m, cp / m
        if dst.exists() and dst.read_bytes() == src.read_bytes():
            out["modules"][m] = "unchanged"
            continue
        if dst.exists():
            _backup(dst)
        shutil.copy2(src, dst)
        out["modules"][m] = "installed"
    out["patches"]["ontology.py"] = _patch(cp / "ontology.py", MARK_ONTO, ONTO_SNIPPET)
    out["patches"]["spec.py"] = _patch(cp / "spec.py", MARK_SPEC, SPEC_SNIPPET)
    out["patches"]["mcp/server.py"] = _patch(target / "mcp" / "server.py", MARK_MCP, MCP_SNIPPET)
    out["patches"]["mcp/mcp-config.json"] = _patch_mcp_config(target / "mcp" / "mcp-config.json")
    return out


def rollback(target: Path) -> dict:
    n = 0
    for b in list(target.rglob("*.bak")):
        orig = Path(str(b)[:-4])
        shutil.copy2(b, orig)
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
        print(json.dumps(rollback(t), ensure_ascii=False, indent=2))
        return 0
    if a.check:
        print(json.dumps(check(t), ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(install(t), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
