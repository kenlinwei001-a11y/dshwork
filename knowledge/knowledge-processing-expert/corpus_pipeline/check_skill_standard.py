# -*- coding: utf-8 -*-
"""check_skill_standard —— skill 标准合规检查（格式 / 文不对题 / 结构）。

## 五组判据（全部可机器判定）

    F1  YAML frontmatter 存在且可解析
    F2  frontmatter 有 name 与 description
    F3  name 与目录名一致（防文不对题的第一道）
    F4  name 是 kebab-case（官方规范）
    F5  description 含触发信息（何时使用 / when to use / 触发）

    S1  有「何时使用」类章节
    S2  有「边界 / 不适用」类章节
    （S3 已废弃：正文不必提自己名字，原判据为假阳性）

## 用法

    python -m corpus_pipeline.check_skill_standard            # 全部
    python -m corpus_pipeline.check_skill_standard <name>...  # 指定
    # 退出码 0 = 全过；1 = 有 FAIL
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

SKILLS_DIR = Path.home() / ".agents" / "skills"
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# 触发表达：显式词 + 中文「当…时使用」句式（后者是标准中文触发写法）
TRIGGER_WORDS = ("何时使用", "when to use", "触发", "use when", "use this",
                 "时使用", "场合", "需要时")
TRIGGER_PATTERNS = (r"当[^。]{2,40}时使用", r"当需要[^。]{2,40}", r"适用于")


def _frontmatter(text: str):
    """返回 (fm_dict, body, ok)。"""
    if not text.startswith("---"):
        return {}, text, False
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text, False
    raw = text[3:end].strip()
    body = text[end + 4:]
    try:
        import yaml
        fm = yaml.safe_load(raw) or {}
    except Exception:
        return {}, body, False
    return fm if isinstance(fm, dict) else {}, body, True


def check_one(name: str) -> dict:
    p = SKILLS_DIR / name / "SKILL.md"
    if not p.exists():
        return {"name": name, "error": "SKILL.md 不存在"}
    t = p.read_text(encoding="utf-8")
    fm, body, ok = _frontmatter(t)
    fails, warns = [], []

    # F1
    if not ok:
        fails.append("F1 frontmatter 缺失或不可解析")
    # F2
    for k in ("name", "description"):
        if not fm.get(k):
            fails.append("F2 frontmatter 缺 `%s`" % k)
    # F3
    fmname = str(fm.get("name") or "")
    if fmname and fmname != name:
        fails.append("F3 name=%r ≠ 目录名 %r（**文不对题风险**）" % (fmname, name))
    # F4
    if fmname and not KEBAB.match(fmname):
        fails.append("F4 name=%r 不是 kebab-case" % fmname)
    # F5
    desc = str(fm.get("description") or "")
    if desc:
        has = any(w in desc.lower() or w in desc for w in TRIGGER_WORDS) or \
              any(re.search(p, desc) for p in TRIGGER_PATTERNS)
        if not has:
            warns.append("F5 description 未见触发词（何时使用/触发/当…时使用/use when）")
    # S1
    if not re.search(r"^#{1,3}\s*(何时使用|When to Use|使用场景)", body, re.M | re.I):
        warns.append("S1 未见「何时使用」章节")
    # S2
    if not re.search(r"^#{1,4}\s*.*(边界|不适用|Boundaries|禁忌)", body, re.M | re.I):
        warns.append("S2 未见「边界/不适用」章节")
    # S3 已移除：正文不需要提及自己的 name，这不是缺陷

    return {"name": name, "lines": len(t.splitlines()), "chars": len(t),
            "fm_name": fmname, "desc_len": len(desc),
            "fails": fails, "warns": warns,
            "pass": not fails}


def main(argv=None):
    argv = argv or sys.argv[1:]
    targets = argv if argv else sorted(
        p.name for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists())
    bad, warned = [], []
    print("%-36s %5s %7s %s" % ("skill", "行", "字符", "结论"))
    print("-" * 78)
    for n in targets:
        r = check_one(n)
        if r.get("error"):
            print("%-36s   %s" % (n, r["error"])); continue
        flag = "✓" if r["pass"] else "✗"
        extra = ""
        if r["fails"]:
            extra = " | " + "; ".join(f[:40] for f in r["fails"])
        elif r["warns"]:
            extra = " | warn: " + "; ".join(w[:30] for w in r["warns"])
        print("%-36s %5d %7d %s%s" % (n, r["lines"], r["chars"], flag, extra))
        if r["fails"]:
            bad.append(n)
        elif r["warns"]:
            warned.append(n)
    print()
    print("FAIL %d / WARN %d / 总 %d" % (len(bad), len(warned), len(targets)))
    if bad:
        print("✗ 不合规：%s" % bad, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
