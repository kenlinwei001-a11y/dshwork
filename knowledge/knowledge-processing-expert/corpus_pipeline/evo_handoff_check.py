# -*- coding: utf-8 -*-
"""evo_handoff_check —— 交接包自检（不依赖 LLM）。

检查每个 handoff/<节号>.md：
  1. 四段齐全：本次问题 / 真实输入文件 / 交付物 / 检查标准；
  2. 交付物含 body + citations + self_check + notes_for_reviewer + 审核判定；
  3. 引用的输入文件真实存在；
  4. writer_role 与节号分派一致（§1-6 engineering，§7+ investment）；
  5. 问题描述含「用上财…形 + 华东理工…值」。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.evo_handoff import writer_for  # type: ignore


REQUIRED_HEADINGS = [
    "## 一、本次问题",
    "## 二、真实输入文件",
    "## 三、交付物",
    "## 四、检查标准",
]

REQUIRED_DELIVERABLE = [
    "body", "citations", "self_check", "notes_for_reviewer", "review_verdict",
]

SELF_CHECK_KEYS = {"number_bound", "missing_handled", "conflicts_pending",
                   "formula_shown"}
CITATION_KEYS = {"claim_text", "evidence_ids", "source_file", "section", "quote"}


def _json_block_after(text: str, heading: str) -> dict | None:
    i = text.find(heading)
    if i < 0:
        return None
    m = re.search(r"```json\s*(\{.*?\})\s*```", text[i:], re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def _input_paths(text: str) -> list[tuple[str, bool]]:
    out = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        m = re.search(r"`([^`]+)`", cells[1])
        if not m:
            continue
        out.append((m.group(1), "✅" in cells[2]))
    return out


def check_handoff(path: Path, project_dir: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    section = path.stem
    problems: list[str] = []

    for h in REQUIRED_HEADINGS:
        if h not in text:
            problems.append("缺少段：%s" % h)

    for k in REQUIRED_DELIVERABLE:
        if k not in text:
            problems.append("交付物缺少字段：%s" % k)

    # writer 分派
    m = re.search(r">\s*给：`([^`]+)`", text)
    if not m:
        problems.append("缺少「给：writer」声明")
    else:
        want = writer_for(section)
        if m.group(1) != want:
            problems.append("writer 分派错误：%s（应为 %s）" % (m.group(1), want))

    # 问题描述
    if not ("用上财" in text and "华东理工" in text and "还原" in text):
        problems.append("本次问题未写「用上财…的形 + 华东理工…的值，还原…」")

    # 输入文件存在性
    paths = _input_paths(text)
    if not paths:
        problems.append("真实输入文件表为空或格式不对")
    for rel, marked_ok in paths:
        p = Path(rel)
        full = p if p.is_absolute() else project_dir / p
        if not full.exists():
            problems.append("输入文件不存在：%s" % rel)
        if not marked_ok:
            problems.append("输入文件被标为缺失：%s" % rel)

    # self_check 四布尔键
    sc = _json_block_after(text, "### 3.3 `self_check`")
    if not sc:
        problems.append("self_check JSON 块无法解析")
    else:
        missing = SELF_CHECK_KEYS - set(sc)
        if missing:
            problems.append("self_check 缺键：%s" % ", ".join(sorted(missing)))
        for k in SELF_CHECK_KEYS:
            if k in sc and not isinstance(sc[k], bool):
                problems.append("self_check.%s 不是 bool" % k)

    # citations 字段
    cit = _json_block_after(text, "### 3.2 `citations`")
    if not cit:
        problems.append("citations JSON 块无法解析")
    else:
        missing = CITATION_KEYS - set(cit)
        if missing:
            problems.append("citations 缺字段：%s" % ", ".join(sorted(missing)))

    return problems


def negative_test(dir_path: Path, project_dir: Path) -> tuple[bool, list[str]]:
    """故意去掉 self_check，自检必须报错。"""
    src = dir_path / "1.1.md"
    if not src.exists():
        return False, ["negative test 需要 handoff/1.1.md"]
    text = src.read_text(encoding="utf-8")
    bad = text.replace("self_check", "self_check_removed")
    tmp = dir_path / "_negative-test.md"
    tmp.write_text(bad, encoding="utf-8")
    try:
        problems = check_handoff(tmp, project_dir)
    finally:
        tmp.unlink(missing_ok=True)
    return bool(problems), problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="交接包自检")
    ap.add_argument("--handoff-dir", default="handoff")
    ap.add_argument("--project-dir", default=".")
    ap.add_argument("--negative-test", action="store_true",
                    help="故意删掉 self_check，验证自检能报错")
    args = ap.parse_args(argv)

    hdir = Path(args.handoff_dir)
    project_dir = Path(args.project_dir)
    files = sorted(hdir.glob("*.md"))
    if not files:
        print("FAIL: %s 下没有 handoff markdown" % hdir)
        return 2

    all_problems = {}
    for p in files:
        probs = check_handoff(p, project_dir)
        if probs:
            all_problems[p.name] = probs

    print("checked %d handoff files" % len(files))
    if all_problems:
        print("FAIL:")
        for name, probs in all_problems.items():
            print(" -", name)
            for x in probs:
                print("   *", x)
        return 1

    print("PASS: 四段齐全、交付物字段齐全、输入文件存在、writer 分派正确、self_check 四布尔键")

    if args.negative_test:
        caught, probs = negative_test(hdir, project_dir)
        print("negative test (删 self_check): caught=%s" % caught)
        if not caught:
            print("FAIL: 反例未被发现")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
