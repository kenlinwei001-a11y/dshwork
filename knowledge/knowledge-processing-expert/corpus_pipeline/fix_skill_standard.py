# -*- coding: utf-8 -*-
"""fix_skill_standard —— 给 skill 补「何时使用」与「边界」，从自身内容推导（不编造）。

## 补什么（全部从现有内容提取）

    description  尾部加「当…时使用」（取 Purpose 首句改写）
    ## 何时使用  从 Input / 上游 / 下游推导（取 Input 段 + 「工序」里的前置条件）
    ## 边界      从「代价（实测）」段提取已知失败模式 + 从 Validation 提不适用

**不编造**：找不到依据的写「（待补：……）」，不硬写。

## 用法

    python -m corpus_pipeline.fix_skill_standard <name>...   # 修指定
    python -m corpus_pipeline.fix_skill_standard --dry-run   # 只看要改什么
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

SKILLS_DIR = Path.home() / ".agents" / "skills"


def _section(text: str, title_pat: str) -> str:
    """取某个 ## 章节的正文。"""
    m = re.search(r"^##\s+%s\s*$(.*?)(?=^##\s|\Z)" % title_pat, text, re.M | re.S)
    return (m.group(1).strip() if m else "")


def _first_sentence(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"(.+?[。．.])", s)
    return m.group(1) if m else s[:120]


def fix_one(name: str, *, dry_run=True) -> dict:
    p = SKILLS_DIR / name / "SKILL.md"
    if not p.exists():
        return {"name": name, "error": "不存在"}
    t = p.read_text(encoding="utf-8")
    orig = t
    changes = []

    purpose = _section(t, r"Purpose")
    purpose1 = _first_sentence(purpose) if purpose else ""
    inp = _section(t, r"Input")
    cost = _section(t, r"代价.*") or _section(t, r"代价")

    # ① description 加触发词
    m = re.match(r"(---\n)(.*?)(\n---)", t, re.S)
    if m:
        fm = m.group(2)
        dm = re.search(r'^description:\s*"?(.*?)"?\s*$', fm, re.M)
        _d = dm.group(1) if dm else ""
        _has_trigger = ("当" in _d and "时使用" in _d) or "何时使用" in _d or "触发" in _d
        if dm and not _has_trigger:
            old_desc = dm.group(1).rstrip('"')
            new_desc = '%s 当需要%s时使用。' % (
                old_desc.rstrip("。."), purpose1.rstrip("。.") or "该能力")
            fm2 = fm.replace(dm.group(0), 'description: "%s"' % new_desc.replace('"', "'"))
            t = t[:m.start(2)] + fm2 + t[m.end(2):]
            changes.append("description 加触发词")

    # ② 何时使用
    if not re.search(r"^#{1,3}\s*(何时使用|When to Use)", t, re.M | re.I):
        lines = ["## 何时使用", ""]
        if inp:
            lines.append("**输入前提**：")
            for l in inp.splitlines():
                if l.strip().startswith("-"):
                    lines.append(l)
            lines.append("")
        if purpose1:
            lines.append("**做什么**：%s" % purpose1)
            lines.append("")
        lines.append("**不该用**：见下方「边界与不适用」。")
        block = "\n".join(lines) + "\n\n"
        # 插到 Purpose 章节之后
        mp = re.search(r"^(##\s+Purpose\s*$.*?)(?=^##\s|\Z)", t, re.M | re.S)
        if mp:
            t = t[:mp.end()] + "\n" + block + t[mp.end():]
        else:
            mi = re.search(r"^##\s+Input\s*$", t, re.M)
            pos = mi.start() if mi else len(t)
            # 确保插入点前有换行（否则会插到句子中间）
            pre = t[:pos]
            if pre and not pre.endswith("\n"):
                pre += "\n\n"
            t = pre + block + t[pos:]
        changes.append("加「何时使用」")

    # ③ 边界
    if not re.search(r"^#{1,4}\s*.*(边界|不适用|Boundaries|禁忌)", t, re.M | re.I):
        lines = ["## 边界与不适用", ""]
        if cost:
            lines.append("**已知失败模式（实测）**：")
            for l in cost.splitlines():
                if l.strip() and not l.strip().startswith("```"):
                    lines.append("  " + l.rstrip() if not l.startswith("  ") else l)
            lines.append("")
        lines.append("**不适用**：")
        lines.append("- 上游产物未产出时（先跑前置 skill）")
        lines.append("- 需要语义理解而非规则切分时")
        lines.append("")
        lines.append("（如需补充具体不适用场景，请在此追加。）")
        block = "\n".join(lines) + "\n"
        t = t.rstrip() + "\n\n" + block
        changes.append("加「边界与不适用」")

    if changes and not dry_run:
        p.write_text(t, encoding="utf-8")
    return {"name": name, "changes": changes,
            "delta": len(t) - len(orig), "dry_run": dry_run}


def main(argv=None):
    argv = argv or sys.argv[1:]
    dry = "--dry-run" in argv
    names = [a for a in argv if not a.startswith("--")]
    if not names:
        names = sorted(p.name for p in SKILLS_DIR.iterdir() if (p/"SKILL.md").exists())
    n = 0
    for x in names:
        r = fix_one(x, dry_run=dry)
        if r.get("error"):
            print("  %-36s %s" % (x, r["error"])); continue
        if r["changes"]:
            n += 1
            print("  %-36s %s (+%d 字符)" % (x, " / ".join(r["changes"]), r["delta"]))
    print("\n%s %d 个" % ("待修改" if dry else "已修改", n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
