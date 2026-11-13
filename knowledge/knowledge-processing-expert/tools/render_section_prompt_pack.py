#!/usr/bin/env python3
"""把语料包里的「逐节提示词」契约渲染为一份可交付的 MD：总审 Agent + N 节独立提示词。

数据源（唯一事实源，不改写、不重算）：
  <corpus>/写作输入/section-prompts.yaml   —— 每节一条：section_no/title/level/path/
                                              facts_count/rules/norm_refs/conflicts/prompt/return_contract

设计原则：
- 确定性渲染：同输入同输出，不调模型，不排序（保持原顺序 = 报告结构顺序）。
- 不搬运项目数值：facts 只给条数，具体取值在事实表 / 节点索引里，正文由写作侧按节点 ID 引用。
- 总审的判定尺度取自项目既有约定（must 项 ×150 字下限、五步展开、结论可复算），不新增规则。

用法：
    python3 render_section_prompt_pack.py <corpus_dir> <out.md>
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def load_sections(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if yaml is None:
        return json.loads(text)
    return yaml.safe_load(text)


def render(corpus: str) -> str:
    src = os.path.join(corpus, "写作输入/section-prompts.yaml")
    secs = load_sections(src)

    n_facts = sum(int(s.get("facts_count") or 0) for s in secs)
    n_rules = sum(len(s.get("rules") or []) for s in secs)
    n_sec_rules = sum(1 for s in secs if s.get("rules"))
    n_conf = sum(len(s.get("conflicts") or []) for s in secs)
    n_sec_conf = sum(1 for s in secs if s.get("conflicts"))
    n_norm = sum(len(s.get("norm_refs") or []) for s in secs)
    chapters: List[str] = []
    for s in secs:
        top = (s.get("path") or ["?"])[0]
        if top not in chapters:
            chapters.append(top)
    lv = {}
    for s in secs:
        lv[s.get("level")] = lv.get(s.get("level"), 0) + 1

    o: List[str] = []
    a = o.append

    a("# 上海财经大学中山北一路校区大数据研究中心 · 写作提示词包")
    a("")
    a("> **结构**：一位**总审 Agent**（只验收、不改稿）＋ **%d 节各自的独立提示词**（每节一份，不共用一个模板）。" % len(secs))
    a("> **口径**：逐节提示词由语料包 `写作输入/section-prompts.yaml` 确定性渲染；项目数值不进本文件，正文按节点 ID 引用。")
    a("")
    a("| 项 | 值 |")
    a("|---|---|")
    a("| 抽取来源 | `DOC-REPORT-01` 可行性研究报告（修订版）＋ 20 份外部依据 |")
    a("| 语料标识 | `SHUFE-BDC-2019-001` |")
    a("| 契约文件 | `写作输入/section-prompts.yaml`（%d 条，本节提示词的唯一数据源） |" % len(secs))
    a("| 章 / 节 | %d 个一级章 · %d 节（h1×%d · h2×%d · h3×%d） |" % (
        len(chapters), len(secs),
        lv.get(1, 0), lv.get(2, 0), lv.get(3, 0)))
    a("| 事实节点 | 各节合计 %d 条引用（按节去重前；真值在 `fact-brief.yaml` / `node-index.tsv`） |" % n_facts)
    a("| 技术函数 | %d 个，分布在 %d 节（这 %d 节必须写算式并可复算） |" % (n_rules, n_sec_rules, n_sec_rules))
    a("| 待审冲突 | %d 条，涉及 %d 节（并列呈现，不裁决） |" % (n_conf, n_sec_conf))
    a("| 规范依据 | %d 处引用（未核条款不得据此写「符合规范」） |" % n_norm)
    a("| 渲染 | `tools/render_section_prompt_pack.py`（零 LLM，同输入同输出） |")
    a("")
    a("> ⚠️ **口径**：本包以 `section-prompts.yaml`（2026-10-23，%d 条）为准；更早的 "
      "`章节提示词索引.md`（2026-10-15，144 条）是**上一代分段**——含「目录」「附录A」与纯章壳，"
      "章节切分也不同（44 条在旧索引有、本包无；19 条本包有、旧索引无）。两者不可混用，写作以一个版本为准。" % len(secs))
    a("")
    a("---")
    a("")

    # ---------------- §1 总审 Agent ----------------
    a("## 1　总审 Agent（系统提示词，可直接贴用）")
    a("")
    a("```text")
    a("# 总审 · 可研报告章节验收")
    a("")
    a("## 角色")
    a("你是可研报告的**总审**。你只做验收，不改稿：输入是章节写作成员交回的一节正文及其回执")
    a("（draft_md / node_mentions / new_claims / unresolved），输出是 pass 或 reject + 问题清单 + 退回原因。")
    a("你不重写、不润色、不重算数值、不替客户裁决冲突。")
    a("")
    a("## 判定依据（按序读，不得跳步）")
    a("1. 本节独立提示词（§3 对应条目）：法定覆盖、必写取值、技术函数、冲突、返回契约；")
    a("2. 本节事实节点值表（`fact-brief.yaml` / `node-index.tsv`）：正文每个数值必须能回指节点 ID；")
    a("3. 项目硬规则（§2.1）：无字面数字、无凭空事实、冲突待审、缺值留白。")
    a("")
    a("## 四项判定尺度（缺一项即 reject）")
    a("① **覆盖完整性**：本节提示词列出的必写取值/法定覆盖项，是否都有对应段落；")
    a("   node_mentions 是否覆盖本节的 facts_count 条节点（缺哪条就列哪条）。")
    a("② **深度**：每项是否走完五步——是什么 → 依据（条款/标准/函数）→ 取值 → 比选或校核 → 结论；")
    a("   只有形容词与口号、没有依据与取值的段落，逐句摘出并 reject。")
    a("③ **篇幅**：正文不少于「本节必写项数 × 150 字」；不足给差额，不用重复句凑数。")
    a("④ **结论可复算**：凡涉及技术函数的节，必须写出算式并按表达式复算；")
    a("   复算不一致、或只给结果不给算式的，列函数名与差异并 reject。")
    a("")
    a("## 判定输出（结构化）")
    a("- verdict：pass | reject")
    a("- findings[]：{尺度①②③④, 位置（节号/段落序号/引文）, 问题, 期望} —— 每条都带位置，不写「整体偏弱」")
    a("- missing_facts[]：本节点覆盖但未进正文的节点 ID")
    a("- unsupported[]：正文里找不到节点支撑的句子（原句摘录）")
    a("- pending_conflicts[]：正文把待审冲突写成了单一取值的，逐处列出")
    a("- reject 时必须给**可执行的退改指令**（补哪节、补哪条节点、算式写成什么形式），不给「再丰富一些」")
    a("")
    a("## 硬边界")
    a("- 不改稿、不重算、不新增事实、不裁决冲突（冲突一律并列并标「待审」）；")
    a("- 不接受以拉长句式、同义反复充当篇幅；")
    a("- 规范条款处于待核状态时，不接受「符合规范」「满足要求」类断言；")
    a("- 结论章（社会效益/结论与建议）不接受任何新数值。")
    a("```")
    a("")
    a("> 出处：四项尺度取自项目既有约定（`member-20ae759842f3` 独立审核：覆盖/深度/篇幅 must×150/结论可复算；"
      "禁止以拉长句式充篇幅），并叠加本项目硬规则。本节未新增任何判定标准。")
    a("")
    a("---")
    a("")

    # ---------------- §2 派发协议 ----------------
    a("## 2　派发与统稿协议（总审之外的那一半）")
    a("")
    a("### 2.1　项目硬规则（每节都适用）")
    a("")
    a("- 正文不许出现字面数字，只能写 `{{节点ID}}`；数值唯一来源是事实节点值表")
    a("- 不许新增图上没有的事实；要新增，先入图")
    a("- 缺值显式留白（缺口不得填 0、不得估值、不许反算）")
    a("- 冲突一律「待审」并列，不裁决")
    a("- 引用即绑定：每个数值后带〔节点ID〕")
    a("- 规范条款待核时，不得据此写「符合规范」")
    a("")
    a("### 2.2　编排（专家团口径）")
    a("")
    a("| 角色 | 承担 | 输入 | 输出 |")
    a("|---|---|---|---|")
    a("| 主理人（统稿） | 派发、串行依赖、跨章一致性、终稿 | 全节回执 | 统稿交付稿 + 差异说明 |")
    a("| 章节写作成员 | 按本节提示词逐项写透 | §3 本节条目 + 事实表 | 正文 + node_mentions + new_claims + unresolved |")
    a("| **总审** | 只验收（§1） | 上者回执 + 本节提示词 | pass/reject + findings + 退回指令 |")
    a("")
    a("流程：`选节 → 读本节提示词 → prepare（算/查/问）→ 起草 → 自检 → 总审 → reject 则退回重写 → 主理人统稿`。")
    a("")
    a("### 2.3　统稿时总审之外还要查的三条跨章一致性")
    a("")
    a("1. 同一节点在总论与详章取值一致（总论只复述，不产出新值）")
    a("2. 规模→投资→招标三章的金额口径一致（分项之和 = 合计）")
    a("3. 结论章逐维度复述，且不出现全篇别处没有的数")
    a("")
    a("---")
    a("")

    # ---------------- §3 逐节提示词 ----------------
    a("## 3　逐节提示词（%d 节，一节一份）" % len(secs))
    a("")
    a("> 读法：`节号 + 标题` → 路径确定所在一级章 → 事实节点表是本节取值全集 → 技术函数节必须写算式 → 末尾是返回契约。")
    a("")
    for i, s in enumerate(secs, 1):
        path = " > ".join(s.get("path") or [])
        a("### 3.%d　`%s`　%s　（%s）" % (i, s.get("section_no", ""), s.get("title", ""), path))
        a("")
        meta = [
            "层级 h%s" % s.get("level", "?"),
            "事实节点 %d 条" % int(s.get("facts_count") or 0),
        ]
        if s.get("rules"):
            meta.append("技术函数 %d 个：%s" % (len(s["rules"]), "、".join("`%s`" % r for r in s["rules"])))
        if s.get("norm_refs"):
            meta.append("规范依据 %d 处" % len(s["norm_refs"]))
        a("- " + "　｜　".join(meta))
        for c in s.get("conflicts") or []:
            vals = " / ".join(str(v) for v in (c.get("values") or []))
            a("- ⚠️ **待审冲突**：%s·%s（%s）%s" % (
                c.get("subject", ""), c.get("predicate", ""), vals,
                ("　动作：" + c["action"]) if c.get("action") else ""))
        if s.get("norm_refs"):
            for r in s["norm_refs"]:
                if isinstance(r, dict):
                    st = r.get("status", "")
                    mark = "🔍" if st and st != "已核" else "📐"
                    clause = str(r.get("clause", ""))
                    if clause and all(ch.isdigit() or ch == "." for ch in clause):
                        clause = "第%s条" % clause
                    a("- %s 规范：%s　%s（%s）" % (
                        mark, r.get("standard", ""), clause, st or "状态未标"))
                else:
                    a("- 📐 规范：%s" % r)
        a("")
        a("```text")
        a((s.get("prompt") or "").strip())
        a("```")
        a("")
        a("**返回契约**：%s" % s.get("return_contract", ""))
        a("")
    a("---")
    a("")

    # ---------------- §4 索引 ----------------
    a("## 4　索引（%d 节速查）" % len(secs))
    a("")
    a("| # | 节号 | 标题 | 层级 | 一级章 | 事实 | 函数 | 冲突 |")
    a("|---|---|---|---|---|---|---|---|")
    for i, s in enumerate(secs, 1):
        a("| %d | `%s` | %s | h%s | %s | %d | %d | %d |" % (
            i, s.get("section_no", ""), s.get("title", ""), s.get("level", ""),
            (s.get("path") or ["?"])[0],
            int(s.get("facts_count") or 0),
            len(s.get("rules") or []),
            len(s.get("conflicts") or []),
        ))
    a("")
    a("---")
    a("")
    a("> 数据源：`写作输入/section-prompts.yaml`（%d 条）。"
      "本文件不含独立事实；所有取值以语料包节点为准，冲突以「待审」呈现。" % len(secs))
    a("")

    return "\n".join(o)


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        sys.stderr.write("用法: render_section_prompt_pack.py <corpus_dir> <out.md>\n")
        return 2
    corpus, out_path = argv[1], argv[2]
    md = render(corpus)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    sys.stdout.write(json.dumps({
        "corpus": corpus, "out": out_path, "chars": len(md), "lines": md.count("\n") + 1,
    }, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
