#!/usr/bin/env python3
"""把语料包里的章节写作提示词契约（style/section_prompts.yaml）确定性渲染为 Markdown。

设计原则（工具 + LLM 分层）：
- 本脚本是**确定性步骤**：只读 JSON 契约、按固定顺序拼装，不调用模型、不做语义判断。
- 同一输入必得同一输出（章节顺序取 sections 数组顺序，不排序、不抽样）。
- 不复制项目专有数值：冲突值、缺口、依据绑定一律按原契约原样转写，不重算、不补口径。

用法：
    python3 render_section_prompts_md.py <corpus_dir> <out.md>

corpus_dir 形如 .../交付物/SHUFE-BDC-2019-001
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

VERDICT_ICON = {
    "合规": "✅",
    "不合规": "❌",
    "待审": "⚠️",
    "待核查": "🔍",
}

# 依据绑定角色：语义取自 external/bindings.yaml 的 note，不另行解释
ROLE_CN = {
    "constrains": "约束报告取值",
    "warrants": "支撑报告论证",
    "benchmark": "参照报告引用",
    "driver": "决定报告结构",
}

GAP_TYPE_CN = {
    "explicit_unknown": "显式未知（须留白交客户）",
    "basis_missing": "依据缺失（须补依据再写）",
}


def load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def bl(items: List[str], indent: str = "  ") -> List[str]:
    return [indent + "- " + str(x) for x in items]


def inline(items: List[str]) -> str:
    return "、".join(items) if items else "—"


def render(corpus: str) -> str:
    sp = load(os.path.join(corpus, "style/section_prompts.yaml"))
    bd = load(os.path.join(corpus, "external/bindings.yaml"))
    cp = load(os.path.join(corpus, "external/compliance.yaml"))

    verdict_of = {r["binding"]: r.get("verdict", "") for r in cp.get("results", [])}
    basis_titles = {r["binding"]: r.get("basis_titles", []) for r in cp.get("results", [])}
    bindings_by_id = {b["id"]: b for b in bd.get("bindings", [])}

    sections = sp["sections"]
    families = sp["families"]
    used_family = []
    for s in sections:
        if s["family"] not in used_family:
            used_family.append(s["family"])
    unused_family = [k for k in families if k not in used_family]

    # ---- 汇总口径（确定性计数） ----
    n_facts = sum(s["slice"]["available_facts"] for s in sections)
    n_claims = sum(len(s["slice"]["claims"]) for s in sections)
    n_conf = sum(len((s.get("project_issues") or {}).get("conflicts", [])) for s in sections)
    n_gap = sum(len((s.get("project_issues") or {}).get("gaps", [])) for s in sections)
    n_bind_cite = sum(len((s.get("project_issues") or {}).get("external_bindings", [])) for s in sections)
    n_bind_uniq = len({b["id"] for s in sections for b in (s.get("project_issues") or {}).get("external_bindings", [])})

    out: List[str] = []
    a = out.append

    a("# 上海财经大学中山北一路校区大数据研究中心 · 章节写作提示词")
    a("")
    a("> **是什么**：从《可行性研究报告（修订版）》抽取出来的「每章怎么起草」的提示词契约——"
      "不是通用写作模板，而是**每章一套**：必要性章在论证、规模章在测算、技术章在判定取值、"
      "投资章在归集、结论章在复述。")
    a("")
    a("| 项 | 值 |")
    a("|---|---|")
    a("| 抽取对象 | `DOC-REPORT-01` 可行性研究报告（修订版）＋ 20 份外部依据（D2–D21），联合处理 |")
    a("| 语料标识 | `SHUFE-BDC-2019-001` |")
    a("| 契约文件 | `style/section_prompts.yaml`（本文件的唯一数据源） |")
    a("| 章节族 | %d 族，本报告启用 %d 族（%s） |" % (
        len(families), len(used_family), "、".join("`%s`" % f for f in used_family)))
    a("| 一级章 | %d 章，各指向所属族并附本项目注入 |" % len(sections))
    a("| 切片总量 | %d 个事实节点 / %d 条论断（按章去重前） |" % (n_facts, n_claims))
    a("| 本项目注入 | 待审冲突 %d 条、缺口 %d 条、依据绑定 %d 处（去重 %d 条） |" % (
        n_conf, n_gap, n_bind_cite, n_bind_uniq))
    a("| 渲染方式 | `tools/render_section_prompts_md.py` 确定性渲染（同输入同输出，不调模型） |")
    a("")
    a("> ⚠️ **复用边界**：本文件是**样式资产**。跨项目复用只取章节族结构、"
      "prepare / must_state / must_not 规则与写法；项目专有数值已槽位化（`{原文值}` / `{重算值}` / `{值}`），"
      "必须由新项目节点库注入。事实记录在 `quality/conflicts.yaml`，不在本文件。")
    a("")
    a("---")
    a("")

    # ---- 0 用法与门禁 ----
    a("## 0　怎么用（门禁）")
    a("")
    a("**起草顺序**：" + sp["usage"]["order"])
    a("")
    a("**门禁**：" + sp["usage"]["gate"])
    a("")
    a("逐章动作固定为五步：")
    a("")
    a("1. 读该章 **法定覆盖**（§3，源自 `outline.yaml`）——没覆盖到的，写了也不算完成")
    a("2. 读该章 **切片**（`写作输入/chapters/NN-章名.md`）——事实输入，正文只许引用其节点 ID")
    a("3. 查 **缺什么论据**（`claims`）——没论断的章要说明为什么")
    a("4. 查 **缺什么取值点**（关键取值点 / `gaps`）——缺值留白，不估算")
    a("5. 过 **prepare → must_state → must_not** 三关，再过 §1 自检")
    a("")

    # ---- 0.1 确定性检查：抽取口径的已知偏差 ----
    co_family = {}
    for s in sections:
        co_family.setdefault(s["family"], []).append(s["chapter"])
    co_family = {k: v for k, v in co_family.items() if len(v) > 1}
    zero_fact = [s["chapter"] for s in sections if s["slice"]["available_facts"] == 0]
    by_verdict = cp.get("by_verdict", {})

    a("### 0.1　抽取口径与已知偏差（确定性检查；以下各项须人工确认，不得静默修正）")
    a("")
    a("| # | 偏差 | 具体项 | 起草时的处置 |")
    a("|---|---|---|---|")
    if co_family:
        a("| 1 | **共族章共用一套基线** | %s | 非首章逐章核对基线是否真的适用于本章，不适用处按本章重写 |" % (
            "；".join("`%s`：%s" % (k, "、".join(v)) for k, v in co_family.items())))
    if zero_fact:
        a("| 2 | **零事实章** | %s | 无事实可引：从相邻章借，或整段留白并标「待补充」；**不许造数** |" % ("、".join(zero_fact)))
    if unused_family:
        a("| 3 | **族未启用** | %s | 本报告缺该章；新项目按 2023 大纲编写时须补，不得沿用旧口径省略 |" % (
            "、".join("%s（%s）" % (f, families[f]["cn"]) for f in unused_family)))
    if by_verdict:
        a("| 4 | **不可直接引用的依据绑定** | 不合规 %s；待核查 %s | 不合规项改写引用或标「待核」；待核查项先补依据再落笔 |" % (
            "、".join(by_verdict.get("不合规", [])) or "—",
            "、".join(by_verdict.get("待核查", [])) or "—"))
        if by_verdict.get("待审"):
            a("| 5 | **待审前提（未裁决）** | %s | 并列呈现并标「待审」；判定随前提分支，不单选一个值 |" % (
                "、".join(by_verdict.get("待审", []))))
    a("")

    # ---- 1 通用约束 ----
    a("## 1　通用约束（每章都适用）")
    a("")
    a("### 1.1　硬规则")
    a("")
    a("\n".join(bl(sp["common"]["hard"], "")))
    a("")
    a("### 1.2　文风")
    a("")
    a("\n".join(bl(sp["common"]["style"], "")))
    a("")
    a("### 1.3　自检")
    a("")
    a(sp["common"]["self_check"])
    a("")
    a("---")
    a("")

    # ---- 2 章节族 ----
    a("## 2　章节族提示（%d 族各写一次，不按章重复）" % len(families))
    a("")
    a("> 族是「同一类活」的最小单元。同一族内各章共用同一套核心问题与坑，差异由 §3 的本项目注入承担。")
    if unused_family:
        a(">")
        a("> 本报告**未启用**：%s（2023 大纲要求的「运营方案与绩效」，旧口径报告没有这一章；"
          "新项目若按 2023 大纲编写必须补，见 §2.%d）。" % (
              "、".join("`%s`（%s）" % (f, families[f]["cn"]) for f in unused_family),
              list(families).index(unused_family[0]) + 1))
    a("")
    for i, (key, f) in enumerate(families.items(), 1):
        a("### 2.%d　`%s`　%s" % (i, key, f["cn"]))
        a("")
        a("- **法定覆盖**：%s" % inline(f.get("covers", [])))
        a("- **核心问题**：%s" % f["focus"])
        a("- **形态**：%s" % f["shape"])
        a("- **评审盯什么**：%s" % f["review"])
        if f.get("prepare"):
            a("- **起草前置（prepare）**：")
            a("\n".join(bl(f["prepare"], "  ")))
        if f.get("must_state"):
            a("- **必须写到（must_state）**：")
            a("\n".join(bl(f["must_state"], "  ")))
        if f.get("must_not"):
            a("- **本章特有的坑（must_not）**：")
            a("\n".join(bl(f["must_not"], "  ")))
        a("")
    a("---")
    a("")

    # ---- 3 本项目 16 章 ----
    a("## 3　本报告 %d 章实例化（族归属 + 本项目注入）" % len(sections))
    a("")
    a("> 每章的可执行提示 = §2 对应族基线 **＋** 本节的项目注入。冲突与缺口只标「待审 / 待补」，不裁决、不补值。")
    a("")
    for i, s in enumerate(sections, 1):
        fam = s["family"]
        a("### 3.%d　第 %d 章　%s → 族 `%s` · %s" % (i, i, s["chapter"], fam, s["family_cn"]))
        a("")
        a("- **法定覆盖**：%s" % inline(s.get("covers", [])))
        a("- **核心问题**：%s" % s["focus"])
        sl = s["slice"]
        a("- **切片**：%d 个唯一事实节点（%d 次陈述）；论断 %s" % (
            sl["available_facts"], sl["statements"],
            inline(sl["claims"]) if sl["claims"] else "无"))
        a("- **关键取值点（%d 个谓词）**：%s" % (len(sl["predicates"]), inline(sl["predicates"])))
        a("- **事实清单**：`写作输入/chapters/%02d-%s.md`" % (i, s["chapter"]))

        pi = s.get("project_issues") or {}
        conflicts = pi.get("conflicts", [])
        gaps = pi.get("gaps", [])
        binds = pi.get("external_bindings", [])

        if not (conflicts or gaps or binds):
            if sl["available_facts"] == 0:
                a("- **本项目注入**：无冲突、无缺口、无依据绑定；但**本章零事实节点**（见下方起草前置）")
            else:
                a("- **本项目注入**：无（本章无冲突、无缺口、无依据绑定）")
        else:
            a("- **本项目注入**：")
            for c in conflicts:
                a("  - ⚠️ **待审冲突**：%s·%s（%s）——并列值如何处理由客户确认，不得自行裁决" % (
                    c.get("subject", ""), c.get("predicate", ""), " / ".join(c.get("values", []))))
            for g in gaps:
                a("  - 🔍 **缺口** `%s`：%s —— %s" % (
                    g.get("id", ""), g.get("subject", ""), GAP_TYPE_CN.get(g.get("type", ""), g.get("type", ""))))
            for b in binds:
                bid = b["id"]
                v = b.get("verdict") or verdict_of.get(bid, "")
                rule = bindings_by_id.get(bid, {}).get("report", {}).get("rule", "")
                a("  - %s **依据绑定** `%s`（%s）· %s" % (
                    VERDICT_ICON.get(v, "•"), bid, ROLE_CN.get(b.get("role", ""), b.get("role", "")), rule))

        if pi.get("conflicts") or pi.get("gaps"):
            a("")
            a("> 起草时：冲突值以 `{面积}` 一类槽位并列呈现并标「待审」；缺口值整段留白并标「待补充」，不估算。")

        a("")
        a("**本章可执行提示**（族基线 ＋ 注入，合并后的完整版）")
        a("")
        a("- 起草前置（prepare）：")
        a("\n".join(bl(s["prepare"], "  ")))
        a("- 必须写到（must_state）：")
        a("\n".join(bl(s["must_state"], "  ")))
        if s.get("must_not"):
            a("- 本章特有的坑（must_not）：")
            a("\n".join(bl(s["must_not"], "  ")))
        a("- 形态：%s" % s["shape"])
        a("- 评审盯什么：%s" % s["review"])
        a("")
    a("---")
    a("")

    # ---- 4 依据绑定台账 ----
    a("## 4　依据绑定台账（%d 条，判定三态：合规 / 不合规 / 待审·待核查）" % len(bd.get("bindings", [])))
    a("")
    a("> 方向：外部依据 `constrains`→ 报告取值、`warrants`→ 报告论证、`benchmark`→ 报告引用、`driver`→ 报告结构。"
      "判定来自于 `external/compliance.yaml` 的确定性复核，**不改动报告任何数字**。")
    a("")
    cnt = cp.get("counts", {})
    a("**判定分布**：" + "　".join("%s %d" % (k, cnt[k]) for k in ["合规", "不合规", "待审", "待核查"] if k in cnt))
    a("")
    a("| ID | 角色 | 报告取值 | 依据条款 | 判定 |")
    a("|---|---|---|---|---|")
    for b in bd.get("bindings", []):
        bid = b["id"]
        v = verdict_of.get(bid, "")
        titles = basis_titles.get(bid) or []
        a("| `%s` | %s | %s | %s | %s %s |" % (
            bid,
            ROLE_CN.get(b["role"], b["role"]),
            b["report"]["value"].replace("|", "／"),
            "；".join(titles) if titles else "—",
            VERDICT_ICON.get(v, "•"),
            v,
        ))
    a("")
    if cp.get("key_finding"):
        a("**关键发现**：" + str(cp["key_finding"]))
        a("")
    a("---")
    a("")

    # ---- 5 自检清单 ----
    a("## 5　交稿前自检（可机检项优先）")
    a("")
    a("| # | 检查 | 判据 |")
    a("|---|---|---|")
    checks = [
        ("正文无字面数字", "全文 grep `[0-9]` 只剩 `{{节点ID}}`、文号、条号"),
        ("无凭空事实", "每个 `{{节点ID}}` 都在 `index/node_index.json` 中存在"),
        ("Toulmin 必填项齐", "每条论断有论点/论据/保证/支撑；保证缺失标「未给出」"),
        ("冲突未裁决", "冲突处并列呈现并标「待审」，无单值化"),
        ("缺口未估算", "缺口处留白并标「待补充」，无插值"),
        ("口径一致", "同一取值在全校/本校区/本期三种口径下不混用"),
        ("跨章数字一致", "同一节点在总论与详章取值一致（总论只复述）"),
        ("依据可回读", "引用标准名称/版本与 §4 台账一致；不合规项已改写或标「待核」"),
    ]
    for i, (k, v) in enumerate(checks, 1):
        a("| %d | %s | %s |" % (i, k, v))
    a("")
    a("---")
    a("")
    a("> 数据源：`style/section_prompts.yaml` · `external/bindings.yaml` · `external/compliance.yaml`；"
      "渲染器：`knowledge/knowledge-processing-expert/tools/render_section_prompts_md.py`。"
      "本文件不含独立事实，所有取值以语料包节点为准。")
    a("")

    return "\n".join(out)


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        sys.stderr.write("用法: render_section_prompts_md.py <corpus_dir> <out.md>\n")
        return 2
    corpus, out_path = argv[1], argv[2]
    md = render(corpus)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    sys.stdout.write(json.dumps({
        "corpus": corpus,
        "out": out_path,
        "chars": len(md),
        "lines": md.count("\n") + 1,
    }, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
