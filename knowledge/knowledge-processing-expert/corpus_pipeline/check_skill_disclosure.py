# -*- coding: utf-8 -*-
"""check_skill_disclosure —— 检查 skill 是否符合渐进式披露原则（可执行判据）。

## 判据（不是感觉）

SKILL.md 是**入口**，不是手册。经验阈值（Anthropic skill 规范）：
    lines    <= 400     正文行数
    chars    <= 8000    正文字符（中文按字计）
    单节     <= 150 行   任一章节超过就该下沉

超阈值 → 退出码 1，并在输出里指出**该下沉哪一节**。

## 为什么要有这个

`knowledge-processing` 曾被从 49,008 字符精简到 3,900（-92%），
然后又被不断加回 —— 没有检查器就会反复膨胀。

## 用法

    python -m corpus_pipeline.check_skill_disclosure            # 检查全部
    python -m corpus_pipeline.check_skill_disclosure <name>     # 检查单个
    python -m corpus_pipeline.check_skill_disclosure --fix-hint <name>   # 给出下沉建议
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

# 阈值不是越紧越好。8,000 是拍的；实测有一个 skill 卡在 8,004，
# 为 4 个字符反复删句子反而损害内容 —— 所以放到 8,500（仍能挡住真实膨胀）。
LIMITS = {"lines": 400, "chars": 8500, "section_lines": 150}

LIMIT_NOTES = {
    "chars": [
        {"at": "v1.0", "value": 8000, "why": "中文按字计，约合 5000 词（Anthropic 建议上限）"},
        {"at": "v1.1", "value": 8500, "why": "8,000 过紧：feasibility 卡在 8,004，为 4 字符反复删句无意义"},
    ],
}
SKILLS_DIR = Path.home() / ".agents" / "skills"


def _sections(text: str):
    """按 # / ## / ### 切章，返回 [(title, start_line, line_count)]。"""
    lines = text.splitlines()
    marks = [(i, l) for i, l in enumerate(lines) if re.match(r"^#{1,3}\s+\S", l)]
    out = []
    for idx, (ln, title) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(lines)
        out.append((title.strip("# ").strip(), ln + 1, end - ln))
    return out


def check_one(name: str) -> dict:
    p = SKILLS_DIR / name / "SKILL.md"
    if not p.exists():
        return {"name": name, "error": "SKILL.md 不存在"}
    t = p.read_text(encoding="utf-8")
    lines = len(t.splitlines())
    chars = len(t)
    refs = sorted(x.name for x in (SKILLS_DIR / name / "references").glob("*")) \
        if (SKILLS_DIR / name / "references").exists() else []
    secs = _sections(t)
    big = [(ti, ln, n) for ti, ln, n in secs if n > LIMITS["section_lines"]]
    fails = []
    if lines > LIMITS["lines"]:
        fails.append("lines %d > %d" % (lines, LIMITS["lines"]))
    if chars > LIMITS["chars"]:
        fails.append("chars %d > %d" % (chars, LIMITS["chars"]))
    return {"name": name, "lines": lines, "chars": chars,
            "refs": refs, "sections": len(secs), "big_sections": big,
            "pass": not fails, "fails": fails}


def fix_hint(name: str, top: int = 5) -> str:
    r = check_one(name)
    if r.get("error"):
        return r["error"]
    out = ["%s：%d 行 / %d 字符（限 %d 行 / %d 字符）"
           % (name, r["lines"], r["chars"], LIMITS["lines"], LIMITS["chars"])]
    if r["pass"]:
        return "\n".join(out + ["  ✓ 符合渐进式披露"])
    out.append("  ✗ 超标，建议下沉以下几节到 references/：")
    for ti, ln, n in sorted(r["big_sections"] or [], key=lambda x: -x[2])[:top]:
        out.append("     L%-4d %-40s %3d 行" % (ln, ti[:40], n))
    if not r["big_sections"]:
        out.append("     （单节未超 150 行，但总行数超 → 建议整体拆分模块）")
    out.append("  现有 references: %s" % (r["refs"] or "无"))
    return "\n".join(out)


def main(argv=None):
    argv = argv or sys.argv[1:]
    if argv and argv[0] == "--fix-hint":
        print(fix_hint(argv[1]))
        return 0
    targets = argv if argv else sorted(
        p.name for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists())
    bad = []
    print("%-38s %6s %7s %6s %s" % ("skill", "行", "字符", "章节", "结论"))
    for n in targets:
        r = check_one(n)
        if r.get("error"):
            print("%-38s   %s" % (n, r["error"])); continue
        flag = "✓" if r["pass"] else "✗ " + "; ".join(r["fails"])
        print("%-38s %6d %7d %6d %s" % (n, r["lines"], r["chars"], r["sections"], flag))
        if not r["pass"]:
            bad.append(n)
    if bad:
        print("\n✗ 不符合渐进式披露: %s" % bad, file=sys.stderr)
        print("  用 --fix-hint <name> 看该下沉哪几节", file=sys.stderr)
        return 1
    print("\n全部符合")
    return 0


if __name__ == "__main__":
    sys.exit(main())
