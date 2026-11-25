# -*- coding: utf-8 -*-
"""evo_graph_clean —— 图谱确定性清洗（零 LLM）。

## 用户问题

`GRAPH-新项目-华东理工AI研究院-merged.json` 的 facts 里混入 21+ 个
「不是项目事实」的节点：标准号片段、未替换占位符、标签词、文件名、代码片段。
这些节点会污染属性自洽判定和提示词槽位，必须确定性删除，不能靠 LLM 猜。

## 删除规则（按顺序命中，第一条生效）

1. subject 含 `{` 或 `}`                     → 占位符残留
2. subject 是纯标准号片段（DGJ / GB/T / JGJ …，无编号） → 标准号片段
3. subject 是标签词（INPUT输入 / DERIVED推演结果 / COMPUTED / CUSTOMER …） → 标签词
4. subject 是输入完整性自评统计标签（可直接计算 / 真缺待补充 …） → 自评标签
5. subject 含文件扩展名（.yaml / .md / .json …） → 文件名
6. subject 是路径（含 `/`）或小写连字符文件名（legal-outline） → 文件引用
7. subject 是全大写代码片段（EC0 / DGJ …）          → 代码片段

## 保留/修复规则

- value 为 None 且 status 不是 undefined → 把 status 改成 undefined，**不删**，
  保留缺口信息（用户明确要求）。
- subject 长度 > 30 且不含常见项目词 → 进入人工复核清单，**不自动删**。

## 不变量

- 只改 `items.facts`；`conflicts` / `reasoning` / `claims` / `validations`
  原样保留。
- 删除前检查 conflicts/reasoning/claims 是否引用该 fact；有引用则拒绝删除，
  转入人工复核（本图实测无引用）。
- 清洗后必须仍保留 8 条 conflicts，且 CF1/CF2/CF3 三条数值冲突必须还在。
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


# ================================================================ 规则

STANDARD_FRAGMENT_RE = re.compile(
    r"^(?:GB|GB/T|GBT|JGJ|DGJ|DBJ|CJJ|CECS|ISO|IEC|EN|ASTM|BS|DIN|JIS|建标)"
    r"\s*$",
    re.IGNORECASE,
)

LABEL_EXACT = {
    "INPUT输入", "OUTPUT输出", "INTERMEDIATE中间量", "DERIVED推演结果",
    "COMPUTED", "CUSTOMER", "CUSTOMER_PRIMARY", "JUDGMENT", "FORM",
    "UNREGISTERED", "INPUT", "OUTPUT", "INTERMEDIATE", "DERIVED",
}

LABEL_RE = re.compile(
    r"^(?:INPUT|OUTPUT|INTERMEDIATE|DERIVED|COMPUTED|CUSTOMER(?:_PRIMARY)?|"
    r"JUDGMENT|FORM|UNREGISTERED)(?:[\u4e00-\u9fff].*)?$",
    re.IGNORECASE,
)

META_LABELS = {
    "可直接计算", "需先计算再判定", "真缺待补充", "存在口径冲突",
    "已填", "待填", "缺失", "合计项", "小计项",
}

FILE_EXT_RE = re.compile(
    r"\.(?:yaml|yml|md|json|txt|csv|tsv|xlsx?|docx?|pdf|xml|html?|py|js|ts)$",
    re.IGNORECASE,
)

# 只认 ASCII 路径；不能用 \w（Unicode 下会匹配中文，误删「研究生/博士生/访问学者用房」）
PATH_LIKE_RE = re.compile(r"^[A-Za-z0-9_./\\-]+$")
FILE_STEM_RE = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)+$")
CODE_FRAGMENT_RE = re.compile(r"^[A-Z]{2,}[0-9]*$")

PROJECT_WORDS = (
    "项目", "工程", "建设", "建筑", "面积", "费用", "投资", "用房", "科研",
    "校区", "学校", "设备", "系统", "负荷", "用水", "用电", "人员", "学生",
    "教师", "层", "高度", "结构", "材料", "招标", "风险", "管理", "进度",
    "资金", "估算", "规模", "设计", "节能", "环境", "安全", "卫生", "消防",
    "暖通", "电气", "给排水", "弱电", "强电", "装修", "绿化", "道路", "停车",
    "面积指标", "容量", "系数", "定额", "单价", "合价", "数量", "比例",
)

DELETE = "delete"
FIX_UNDEFINED = "fix_undefined"
REVIEW = "review"
KEEP = "keep"


def classify_fact(fact: dict) -> tuple[str, str]:
    """返回 (action, reason)。确定性、无副作用。"""
    subject = str(fact.get("subject") or "").strip()
    value = fact.get("value")
    status = str(fact.get("status") or "")

    if not subject:
        return DELETE, "空 subject"
    if "{" in subject or "}" in subject:
        return DELETE, "占位符残留（subject 含 { 或 }）"
    if STANDARD_FRAGMENT_RE.match(subject):
        return DELETE, "标准号片段（只有代号、无编号）"
    if subject in LABEL_EXACT or LABEL_RE.match(subject):
        return DELETE, "标签词/枚举名被当成事实"
    if subject in META_LABELS:
        return DELETE, "输入完整性自评统计标签被当成事实"
    if FILE_EXT_RE.search(subject):
        return DELETE, "文件名被当成事实（含文件扩展名）"
    if PATH_LIKE_RE.match(subject) and ("/" in subject or "\\" in subject):
        return DELETE, "文件路径被当成事实"
    if FILE_STEM_RE.match(subject):
        return DELETE, "文件名词干被当成事实"
    if CODE_FRAGMENT_RE.match(subject):
        return DELETE, "全大写代码片段被当成事实"
    if value is None and status != "undefined":
        return FIX_UNDEFINED, "value=None 但 status 非 undefined → 标 undefined 保留"
    if len(subject) > 30 and not any(w in subject for w in PROJECT_WORDS):
        return REVIEW, "subject 长度>30 且不含常见项目词 → 人工复核"
    return KEEP, ""


def _fact_refs(items: dict) -> dict[str, list[str]]:
    """收集 reasoning / claims / conflicts / validations 对 fact id 的引用。"""
    refs: dict[str, list[str]] = {}

    def add(fid: Any, where: str) -> None:
        if isinstance(fid, str) and fid:
            refs.setdefault(fid, []).append(where)

    for r in items.get("reasoning") or []:
        for x in (r.get("inputs") or []) + (r.get("deps_labels") or []):
            add(x, "reasoning:%s" % (r.get("rule_id") or r.get("id") or "?"))
        add(r.get("output"), "reasoning:%s" % (r.get("rule_id") or r.get("id") or "?"))
    for c in items.get("claims") or []:
        for x in ((c.get("deps") or []) + (c.get("evidence_refs") or [])
                  + (c.get("premise_refs") or []) + (c.get("derived_from") or [])):
            add(x, "claim:%s" % (c.get("id") or "?"))
    for c in items.get("conflicts") or []:
        for x in c.get("involved") or []:
            add(x, "conflict:%s" % (c.get("id") or "?"))
    for v in items.get("validations") or []:
        add(v.get("claim"), "validation:%s" % (v.get("claim") or "?"))
    return refs


def clean_graph(graph: dict) -> dict:
    """返回 {clean, removed, fixed, review, refs}。"""
    items = graph.get("items") or {}
    facts = list(items.get("facts") or [])
    refs = _fact_refs(items)

    clean_facts, removed, fixed, review = [], [], [], []
    for f in facts:
        action, reason = classify_fact(f)
        fid = f.get("id")
        if action == DELETE:
            if fid in refs:
                review.append({
                    "id": fid, "subject": f.get("subject"), "value": f.get("value"),
                    "reason": "规则命中删除，但被引用：%s → 转人工复核"
                              % ", ".join(refs[fid][:3]),
                })
                clean_facts.append(f)
            else:
                removed.append({
                    "id": fid, "subject": f.get("subject"), "value": f.get("value"),
                    "status": f.get("status"), "section": f.get("section"),
                    "reason": reason,
                })
            continue
        if action == FIX_UNDEFINED:
            nf = dict(f)
            nf["status"] = "undefined"
            nf["cleaning_note"] = reason
            fixed.append({
                "id": fid, "subject": f.get("subject"), "value": f.get("value"),
                "old_status": f.get("status"), "reason": reason,
            })
            clean_facts.append(nf)
            continue
        if action == REVIEW:
            review.append({
                "id": fid, "subject": f.get("subject"), "value": f.get("value"),
                "reason": reason,
            })
        clean_facts.append(f)

    clean = json.loads(json.dumps(graph, ensure_ascii=False))
    clean["items"]["facts"] = clean_facts

    # stats 重算（只重算能确定性统计的字段）
    before_stats = dict(graph.get("stats") or {})
    stats = dict(before_stats)
    stats["facts"] = len(clean_facts)
    stats["provided"] = sum(1 for f in clean_facts if f.get("status") == "provided")
    stats["undefined"] = sum(1 for f in clean_facts if f.get("status") == "undefined")
    stats["computed"] = sum(1 for f in clean_facts if f.get("status") == "computed")
    stats["reasoning"] = len(clean["items"].get("reasoning") or [])
    stats["conflicts"] = len(clean["items"].get("conflicts") or [])
    stats["removed_by_clean"] = len(removed)
    stats["fixed_undefined"] = len(fixed)
    clean["stats"] = stats

    meta = dict(clean.get("meta") or {})
    meta["cleaning"] = {
        "by": "corpus_pipeline.evo_graph_clean",
        "rules": [
            "subject 含 { 或 } → 删",
            "纯标准号片段（DGJ/GB/T/GB/JGJ…）→ 删",
            "标签词（INPUT输入/DERIVED推演结果/COMPUTED/CUSTOMER…）→ 删",
            "自评统计标签（可直接计算/需先计算再判定/真缺待补充/存在口径冲突…）→ 删",
            "含文件扩展名（.yaml/.md/.json…）→ 删",
            "路径或小写连字符文件名（legal-outline/skeleton/legal-outline）→ 删",
            "全大写代码片段（EC0/DGJ/JGJ…）→ 删",
            "value=None 且 status≠undefined → 标 undefined 保留",
            "subject>30 且不含项目词 → 人工复核，不自动删",
        ],
        "before_facts": len(facts),
        "after_facts": len(clean_facts),
        "removed": len(removed),
        "fixed_undefined": len(fixed),
        "manual_review": len(review),
    }
    clean["meta"] = meta
    return {
        "clean": clean,
        "removed": removed,
        "fixed": fixed,
        "review": review,
        "refs": {k: v for k, v in refs.items() if k in {r["id"] for r in removed}},
    }


def validate_cleaning(before: dict, result: dict) -> list[str]:
    """硬校验；返回问题列表，空表示通过。"""
    problems: list[str] = []
    clean = result["clean"]
    before_facts = list((before.get("items") or {}).get("facts") or [])
    after_facts = list((clean.get("items") or {}).get("facts") or [])
    removed = result["removed"]

    if len(after_facts) != len(before_facts) - len(removed):
        problems.append("facts 数不守恒：%d - %d != %d"
                        % (len(before_facts), len(removed), len(after_facts)))

    before_conf = (before.get("items") or {}).get("conflicts") or []
    after_conf = (clean.get("items") or {}).get("conflicts") or []
    if len(after_conf) != len(before_conf):
        problems.append("conflicts 数变化：%d → %d" % (len(before_conf), len(after_conf)))
    if len(after_conf) != 8:
        problems.append("conflicts 不是 8 条（实际 %d）" % len(after_conf))

    desc = " ".join(str(c.get("description") or "") for c in after_conf)
    for needle in ("年总用水量", "土建工程", "安装工程"):
        if needle not in desc:
            problems.append("数值冲突丢失：%s" % needle)

    alive = {f.get("id") for f in after_facts}
    for c in after_conf:
        for fid in c.get("involved") or []:
            if fid not in alive:
                problems.append("conflict %s 的 involved 节点 %s 不在清洗后 facts 中"
                                % (c.get("id"), fid))

    # 残留规则命中检查
    for f in after_facts:
        action, reason = classify_fact(f)
        if action == DELETE:
            problems.append("清洗后仍命中删除规则：%s (%s)" % (f.get("subject"), reason))
    return problems


# ================================================================ 报告

def _md_escape(v: Any) -> str:
    s = "—" if v is None else str(v)
    return s.replace("|", "\\|").replace("\n", " ")


def render_report(before: dict, result: dict, problems: list[str],
                  origin_before: dict | None = None,
                  origin_after: dict | None = None) -> str:
    clean = result["clean"]
    bs = before.get("stats") or {}
    cs = clean.get("stats") or {}
    L: list[str] = []
    L.append("# 图谱清洗报告（P0-2）")
    L.append("")
    L.append("> 输入：`GRAPH-新项目-华东理工AI研究院-merged.json`  ")
    L.append("> 输出：`GRAPH-新项目-华东理工AI研究院-clean.json`  ")
    L.append("> 工具：`corpus_pipeline/evo_graph_clean.py`（确定性规则，零 LLM）")
    L.append("")
    L.append("## 一、清洗前后对比")
    L.append("")
    L.append("| 指标 | 清洗前 | 清洗后 | 变化 |")
    L.append("|---|---:|---:|---:|")
    L.append("| facts 数 | %s | %s | %+d |" % (bs.get("facts"), cs.get("facts"),
                                                (cs.get("facts") or 0) - (bs.get("facts") or 0)))
    L.append("| provided | %s | %s | %+d |" % (bs.get("provided"), cs.get("provided"),
                                                (cs.get("provided") or 0) - (bs.get("provided") or 0)))
    L.append("| computed | %s | %s | %+d |" % (bs.get("computed"), cs.get("computed"),
                                                (cs.get("computed") or 0) - (bs.get("computed") or 0)))
    L.append("| undefined | %s | %s | %+d |" % (bs.get("undefined"), cs.get("undefined"),
                                                 (cs.get("undefined") or 0) - (bs.get("undefined") or 0)))
    L.append("| conflicts | %s | %s | %+d |" % (bs.get("conflicts"), cs.get("conflicts"),
                                                 (cs.get("conflicts") or 0) - (bs.get("conflicts") or 0)))
    L.append("| 垃圾节点（删除） | — | %d | — |" % len(result["removed"]))
    L.append("| 修正 undefined | — | %d | — |" % len(result["fixed"]))
    L.append("| 人工复核 | — | %d | — |" % len(result["review"]))
    if origin_before and origin_after:
        L.append("")
        L.append("### 属性自洽重跑（`evo_origin_check.check`）")
        L.append("")
        L.append("| 指标 | 清洗前 | 清洗后 |")
        L.append("|---|---:|---:|")
        for k in ("input", "derived", "undetermined"):
            L.append("| %s | %s | %s |" % (
                k, (origin_before.get("counts") or {}).get(k),
                (origin_after.get("counts") or {}).get(k)))
        L.append("| total | %s | %s |" % (
            origin_before.get("total"), origin_after.get("total")))
    L.append("")
    L.append("## 二、删了什么")
    L.append("")
    L.append("| # | id | subject | value | 删除理由 |")
    L.append("|---:|---|---|---:|---|")
    for i, r in enumerate(result["removed"], 1):
        L.append("| %d | `%s` | `%s` | %s | %s |" % (
            i, _md_escape(r.get("id")), _md_escape(r.get("subject")),
            _md_escape(r.get("value")), _md_escape(r.get("reason"))))
    L.append("")
    L.append("## 三、修正为 undefined（保留缺口）")
    L.append("")
    if result["fixed"]:
        L.append("| id | subject | value | 原 status |")
        L.append("|---|---|---:|---|")
        for r in result["fixed"]:
            L.append("| `%s` | `%s` | %s | %s |" % (
                _md_escape(r.get("id")), _md_escape(r.get("subject")),
                _md_escape(r.get("value")), _md_escape(r.get("old_status"))))
    else:
        L.append("无（本图所有 value=None 的节点原本已是 `undefined`）。")
    L.append("")
    L.append("## 四、人工复核清单（未自动删）")
    L.append("")
    if result["review"]:
        L.append("| id | subject | value | 原因 |")
        L.append("|---|---|---:|---|")
        for r in result["review"]:
            L.append("| `%s` | `%s` | %s | %s |" % (
                _md_escape(r.get("id")), _md_escape(r.get("subject")),
                _md_escape(r.get("value")), _md_escape(r.get("reason"))))
    else:
        L.append("无。")
    L.append("")
    L.append("## 五、冲突保留校验")
    L.append("")
    confs = (clean.get("items") or {}).get("conflicts") or []
    L.append("清洗后 conflicts = **%d** 条。" % len(confs))
    L.append("")
    L.append("| id | type | status | 描述 |")
    L.append("|---|---|---|---|")
    for c in confs:
        L.append("| %s | %s | %s | %s |" % (
            c.get("id"), _md_escape(c.get("type")), _md_escape(c.get("status")),
            _md_escape(str(c.get("description") or "")[:160])))
    L.append("")
    L.append("**三条数值冲突点名校验**：")
    L.append("")
    desc = " ".join(str(c.get("description") or "") for c in confs)
    for needle, cid in (("年总用水量", "CF1"), ("土建工程", "CF2"), ("安装工程", "CF3")):
        L.append("- %s：%s" % (needle, "✅ 在" if needle in desc else "❌ 丢失（%s）" % cid))
    L.append("")
    L.append("## 六、硬校验")
    L.append("")
    if problems:
        L.append("❌ **未通过**：")
        L.append("")
        for p in problems:
            L.append("- %s" % p)
    else:
        L.append("✅ 全部通过：facts 守恒、8 条 conflicts 保留、CF1/CF2/CF3 在、"
                 "无 conflict 引用失效、无残留删除规则命中。")
    L.append("")
    L.append("## 七、清洗规则（确定性）")
    L.append("")
    for rule in (clean.get("meta") or {}).get("cleaning", {}).get("rules", []):
        L.append("- %s" % rule)
    L.append("")
    return "\n".join(L)


# ================================================================ CLI

def _load_origin_counts(graph_path: str, rules_path: str | None) -> dict | None:
    if not rules_path:
        return None
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from corpus_pipeline.evo_origin_check import check  # type: ignore
        import yaml  # type: ignore

        rules = yaml.safe_load(Path(rules_path).read_text(encoding="utf-8"))
        rules = (rules or {}).get("rules") or {}
        return check(graph_path, rules_from_pack=rules)
    except Exception as e:  # 报告里显式暴露，不静默
        return {"error": "%s: %s" % (type(e).__name__, e)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="确定性清洗图谱垃圾节点")
    ap.add_argument("--graph", default="GRAPH-新项目-华东理工AI研究院-merged.json")
    ap.add_argument("--out", default="GRAPH-新项目-华东理工AI研究院-clean.json")
    ap.add_argument("--report", default="graph-clean-报告.md")
    ap.add_argument("--json-report", default="graph-clean-明细.json")
    ap.add_argument("--rules", default="形-可复用知识资产-v1.0/functions/derivation_templates.yaml",
                    help="用于清洗前后属性自洽对比；传空字符串可关闭")
    args = ap.parse_args(argv)

    gp = Path(args.graph)
    data = json.loads(gp.read_text(encoding="utf-8"))
    result = clean_graph(data)
    problems = validate_cleaning(data, result)

    origin_before = _load_origin_counts(str(gp), args.rules or None)
    out = Path(args.out)
    out.write_text(json.dumps(result["clean"], ensure_ascii=False, indent=2), encoding="utf-8")
    origin_after = _load_origin_counts(str(out), args.rules or None)

    report = render_report(data, result, problems, origin_before, origin_after)
    Path(args.report).write_text(report, encoding="utf-8")
    Path(args.json_report).write_text(json.dumps({
        "before_stats": data.get("stats"),
        "after_stats": result["clean"].get("stats"),
        "removed": result["removed"],
        "fixed": result["fixed"],
        "review": result["review"],
        "dangling_refs": result["refs"],
        "problems": problems,
        "origin_before": origin_before,
        "origin_after": origin_after,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("facts %s → %s；删除 %d；修正 undefined %d；人工复核 %d；conflicts %s → %s" % (
        (data.get("stats") or {}).get("facts"),
        (result["clean"].get("stats") or {}).get("facts"),
        len(result["removed"]), len(result["fixed"]), len(result["review"]),
        (data.get("stats") or {}).get("conflicts"),
        (result["clean"].get("stats") or {}).get("conflicts")))
    if isinstance(origin_before, dict) and "counts" in origin_before:
        print("origin before:", origin_before.get("counts"))
    if isinstance(origin_after, dict) and "counts" in origin_after:
        print("origin after :", origin_after.get("counts"))
    if problems:
        print("VALIDATION FAILED:")
        for p in problems:
            print(" -", p)
        return 1
    print("VALIDATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
