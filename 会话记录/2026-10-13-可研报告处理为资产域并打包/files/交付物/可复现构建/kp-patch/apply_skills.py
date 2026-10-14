# -*- coding: utf-8 -*-
"""把 skills/PATCHES.md 里的 5 个增量片段插入对应 SKILL.md（插入式、幂等、自动备份）。

用法：
    python apply_skills.py --check
    python apply_skills.py --skills-dir /Users/apple/.agents/skills
    python apply_skills.py --skills-dir ... --rollback
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCH_FILE = HERE / "skills" / "PATCHES.md"
MARK = "<!-- kp-patch:v1 -->"


def parse_patches() -> list[dict]:
    txt = PATCH_FILE.read_text(encoding="utf-8")
    out = []
    # 每个 skill 段：## N. `name` … **锚点**：`anchor` … ```markdown … ```
    for sec in re.split(r"\n## \d+\.\s+", txt)[1:]:
        m = re.match(r"`([^`]+)`", sec.strip())
        if not m:
            continue
        name = m.group(1)
        a = re.search(r"\*\*锚点\*\*：`([^`]*)`", sec)
        anchor = a.group(1) if a else None
        blocks = re.findall(r"```markdown\n([\s\S]*?)```", sec)
        if not blocks:
            continue
        out.append({"skill": name, "anchor": anchor, "snippet": blocks[0].rstrip() + "\n"})
    return out


def apply_one(skill_dir: Path, patch: dict, dry: bool = False) -> str:
    f = skill_dir / "SKILL.md"
    if not f.exists():
        return "missing"
    s = f.read_text(encoding="utf-8")
    if MARK in s:
        return "already"
    if dry:
        return "would-patch"
    shutil.copy2(f, f.with_suffix(".md.bak"))
    snip = patch["snippet"]
    anchor = patch.get("anchor")
    if anchor and anchor in s:
        # 找到锚点所在行尾，插入其后
        idx = s.index(anchor) + len(anchor)
        eol = s.find("\n", idx)
        eol = len(s) if eol == -1 else eol
        s = s[:eol] + "\n\n" + snip + s[eol:]
    else:
        s = s.rstrip() + "\n\n" + snip + "\n"
    f.write_text(s, encoding="utf-8")
    return "patched"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skills-dir", default="/Users/apple/.agents/skills")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    a = ap.parse_args()
    d = Path(a.skills_dir)
    patches = parse_patches()
    if a.rollback:
        n = 0
        for b in d.rglob("SKILL.md.bak"):
            shutil.copy2(b, Path(str(b)[:-4]))
            b.unlink()
            n += 1
        print(json.dumps({"restored": n}, ensure_ascii=False, indent=2))
        return 0
    res = {}
    for p in patches:
        res[p["skill"]] = apply_one(d / p["skill"], p, dry=a.check)
    print(json.dumps({"parsed": len(patches), "skills_dir": str(d), "result": res},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
