# -*- coding: utf-8 -*-
"""外科式回滚 / 正确基线快照（用于修正 install.py 的备份缺陷）。

**缺陷**：原 `_backup()` 写成「`.bak` 已存在则跳过」，导致 4 个文件的 `.bak`
是补丁前的**旧版本**（Sep 23 / Oct 9 / Oct 10）。若按它回滚，会一并擦掉
这些日期之后的所有改动——**包括另一个对话的 semantica 接入工作**。

**修正思路**：不依赖文件级还原，改为**按补丁标记做外科式移除**——
我的补丁全部带唯一标记（`kp-patch:`），且形态固定：
  · 追加型：标记起至文件末尾整块删除；
  · 内联型：按起始/结束标记成对删除。
这样得到的就是**精确的补丁前内容**，与任何第三方改动无关。

用法：
    python surgical_rollback.py --check                      # 体检：能否外科回滚
    python surgical_rollback.py --snapshot                   # 生成正确基线 *.prepatch.<ts>
    python surgical_rollback.py --rollback                   # 外科式回滚（先自动快照）
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TARGET = "/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert"
DEFAULT_SKILLS = "/Users/apple/.agents/skills"
TS = time.strftime("%Y%m%d%H%M%S")

# 追加型：标记 → 从标记所在行起，删到文件末尾
APPEND_MARKS = {
    "corpus_pipeline/ontology.py": "# --- kp-patch: claim-level relations (append-only) ---",
    "corpus_pipeline/spec.py": "# --- kp-patch: extended contract files ---",
    "mcp/server.py": "# --- kp-patch: verification tools ---",
    "corpus_pipeline/groups.py": "# --- kp-patch: verify group ---",
}
# 内联型：起始标记 → 结束标记（含），整块删除
INLINE_BLOCKS = [
    ("mcp/server.py", "# --- kp-patch: verify dispatch ---", '    raise ValueError(f"unknown tool {name}")'),
    ("mcp/server.py", '    {"name": "build_source_ledger"', '    {"name": "provider_status"'),
]
# JSON 键
JSON_KEYS = [("mcp/mcp-config.json", ["tools", "verify"])]


def strip_append(s: str, mark: str) -> tuple[str, bool]:
    i = s.find(mark)
    if i == -1:
        return s, False
    # 回退到该行行首
    j = s.rfind("\n", 0, i)
    return s[:j if j != -1 else i].rstrip() + "\n", True


def strip_inline(s: str, start: str, end: str) -> tuple[str, bool]:
    i = s.find(start)
    if i == -1:
        return s, False
    j = s.find(end, i)
    if j == -1:
        return s, False
    # 删除 [i, j) —— 结束标记本身保留
    k = s.rfind("\n", 0, i)
    k = k + 1 if k != -1 else i
    return s[:k] + s[j:], True


def strip_json_key(s: str, path: list[str]) -> tuple[str, bool]:
    try:
        j = json.loads(s)
    except Exception:                                     # noqa: BLE001
        return s, False
    cur = j
    for k in path[:-1]:
        if not isinstance(cur, dict) or k not in cur:
            return s, False
        cur = cur[k]
    if not isinstance(cur, dict) or path[-1] not in cur:
        return s, False
    del cur[path[-1]]
    return json.dumps(j, ensure_ascii=False, indent=2) + "\n", True


def process_file(p: Path, dry: bool, out_suffix: str | None) -> dict:
    """返回 {found, removed, target}；out_suffix 非空则写出快照。"""
    if not p.exists():
        return {"found": False, "removed": [], "note": "missing"}
    s0 = p.read_text(encoding="utf-8")
    s, removed = s0, []
    rel = str(p)
    for relpath, mark in APPEND_MARKS.items():
        if rel.endswith(relpath):
            s, ok = strip_append(s, mark)
            if ok:
                removed.append(f"append:{mark[:34]}")
    for relpath, start, end in INLINE_BLOCKS:
        if rel.endswith(relpath):
            s, ok = strip_inline(s, start, end)
            if ok:
                removed.append(f"inline:{start[:34]}")
    for relpath, keypath in JSON_KEYS:
        if rel.endswith(relpath):
            s, ok = strip_json_key(s, keypath)
            if ok:
                removed.append(f"json:{'.'.join(keypath)}")
    if not removed:
        return {"found": False, "removed": [], "note": "无标记"}
    if not dry:
        if out_suffix:
            p.with_name(p.name + out_suffix).write_text(s0, encoding="utf-8")
        p.write_text(s, encoding="utf-8")
    return {"found": True, "removed": removed, "target": str(p)}


def targets(target: Path) -> list[Path]:
    return [target / r for r in
            list(APPEND_MARKS) + list({r for r, _, _ in INLINE_BLOCKS}) + [r for r, _ in JSON_KEYS]]


def skills_targets(sdir: Path) -> list[Path]:
    out = []
    for f in sdir.rglob("SKILL.md"):
        if "<!-- kp-patch:v1 -->" in f.read_text(encoding="utf-8", errors="replace"):
            out.append(f)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--skills-dir", default=DEFAULT_SKILLS)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    a = ap.parse_args()
    t = Path(a.target)
    files = targets(t)
    res = {}
    if a.check:
        for f in files:
            r = process_file(f, dry=True, out_suffix=None)
            if r.get("found") or r.get("note") != "missing":
                res[str(f.relative_to(t))] = r["removed"] or r["note"]
        sk = skills_targets(Path(a.skills_dir))
        res["skills"] = [str(s) for s in sk]
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    suffix = ".prepatch." + TS if a.snapshot else None
    if a.rollback:
        # 回滚前先落一份正确基线快照，避免再次出现「旧 .bak」问题
        for f in files:
            process_file(f, dry=True, out_suffix=".prepatch." + TS)
            r = process_file(f, dry=False, out_suffix=".prepatch." + TS)
            if r["found"]:
                res[str(f.relative_to(t))] = r["removed"]
        for s in skills_targets(Path(a.skills_dir)):
            txt = s.read_text(encoding="utf-8")
            i = txt.find("<!-- kp-patch:v1 -->")
            if i != -1:
                s.with_name(s.name + ".prepatch." + TS).write_text(txt, encoding="utf-8")
                j = txt.rfind("\n", 0, i)
                s.write_text(txt[:j if j != -1 else i].rstrip() + "\n", encoding="utf-8")
                res.setdefault("skills", []).append(str(s))
        print(json.dumps({"rolled_back": res, "snapshot_suffix": ".prepatch." + TS},
                         ensure_ascii=False, indent=2))
        return 0
    # snapshot 模式：只写快照，不动原文件
    for f in files:
        out = f.with_name(f.name + suffix)
        if f.exists():
            out.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            res[str(f.relative_to(t))] = str(out.name)
    for s in skills_targets(Path(a.skills_dir)):
        out = s.with_name(s.name + suffix)
        out.write_text(s.read_text(encoding="utf-8"), encoding="utf-8")
        res.setdefault("skills", []).append(out.name)
    print(json.dumps({"snapshot_suffix": suffix, "files": res}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
