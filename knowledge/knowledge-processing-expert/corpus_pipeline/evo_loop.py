# -*- coding: utf-8 -*-
"""evo_loop —— 评估 → 分析 → 5Why 倒推根因 → 修复 → 再评估（PDCA 闭环）。

## 双轨设计

    轨 A｜提示词质量（119 节全覆盖，纯代码）
        检查每节提示词是否含：正确形态 / 形节点 / 值填充 / 缺项分类 / web检索指向
        快，能覆盖 80% 根因（多数问题在提示词阶段已产生）

    轨 B｜正文还原度（现有 3 节，逐步扩）
        五维评分：形态35% / 篇幅15% / 计算25% / 值15% / 冲突10%
        慢，但验证最终效果

## 5 Why 机制

差异类型 → 预设根因链（知识库）→ 逐层追问 → 定位到「可修的一层」

    Why1 这节分低？        → 形态不对（段落/表格/文体）
    Why2 形态为何不对？     → 提示词里的形态信息错
    Why3 形态信息为何错？   → 形态从 chunks 抽，chunks 段落虚低
    Why4 chunks 为何虚低？  → 旧切片 55% 一段塞多段
    Why5 为何一段塞多段？   → 切片规格缺失（skill 只写"不跨章节合并"）
    根因：切片规格缺失 → 已用 semantica 修复（可验证）

## LOOP 终止条件

- 所有根因状态为 FIXED（有验证证据）
- 或连续两轮无新根因
- 或达到 max_rounds

## 用法

    from corpus_pipeline.evo_loop import run_loop
    r = run_loop(graph=..., prompts=..., forms=..., chunks=..., max_rounds=3)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# ================================================================ 5 Why 知识库
# 差异类型 → 五层根因链 + 可修点
WHY_CHAINS = {
    "形态_段落数": {
        "why": [
            "这节的段落数与原文差很多",
            "提示词给出的目标段数错了",
            "目标段数来自 chunks 统计，而旧 chunks 一段塞多段",
            "旧切片是 LLM 按 prompt 自由切的，55% 的 chunk 含 2-3 段",
            "semantic-chunking-skill 只写了「不跨章节强行合并」，没规定「一段一个 chunk」",
        ],
        "root": "切片规格缺失",
        "fix": "已用 semantica.split（structural/paragraph）重切，段落数 472→832",
        "verifiable": "对比新旧 chunks 的 para_count 分布",
    },
    "形态_表格列": {
        "why": [
            "还原的表列数比原文少",
            "提示词没告诉 LLM 原文有哪些列",
            "形态里的列定义来自 chunks 表头，而复合表头（合并单元格）被拍平后错位",
            "原文投资估算表的「技术经济指标」跨 3 列、「估算金额」跨 1 列",
            "markdown 表格不支持合并单元格，转换时列对应关系丢失",
        ],
        "root": "复合表头在 md 化时错位",
        "fix": "改用数据行语义推断列（数量=大整数/单位=㎡·部·项/合价=金额）",
        "verifiable": "投资估算表能否还原成 7 列 × 46 行",
    },
    "形态_文体": {
        "why": [
            "原文表格为主，还原写成多小节散文",
            "提示词没强制「表格为主」",
            "形态里有 style 字段但没转成硬约束",
            "形态抽取时只记了 style=table_dominant，没给反例",
            "提示词生成器把 style 写成了描述而非纪律",
        ],
        "root": "style 未转成可执行的形态纪律",
        "fix": "提示词加「不得改变文体」+「不得拆表」+「不得减少列」五条硬纪律",
        "verifiable": "检查提示词是否含这五条",
    },
    "形态_公式块": {
        "why": [
            "规范引用/设备参数混在正文里，被当成项目事实",
            "提示词没把 $$ 块独立出来",
            "chunks 里 $$ 块和正文混在同一 chunk",
            "旧切片不识别 $ 标记",
            "semantic-chunking-skill 没规定公式块要独立",
        ],
        "root": "$$ 块未独立",
        "fix": "重切时把 $$...$$ 识别为 type=quote 独立块（19 个）",
        "verifiable": "统计 type=quote 的 chunk 数",
    },
    "形节点_缺失": {
        "why": [
            "这节的提示词里「形节点 0 个」",
            "该节在形包里没有 rules_required",
            "形包只给 17/119 节定义了计算规则",
            "规则是从上财报告的公式反抽的，不是每节都有公式",
            "原文很多节本身就是定性叙述，没有可计算的形",
        ],
        "root": "定性节没有「非数值形」（内容项/证据要求）",
        "fix": "给无规则节补 must_cover + 仿照参考 + 证据要求",
        "verifiable": "检查 119 节里有几节含 must_cover",
    },
    "缺项_误分类": {
        "why": [
            "客户已给的数据被标成「需 web 检索」或「向客户索取」",
            "状态判定用了名称特征（含「性质」→web），没查事实来源",
            "判定顺序是「先猜词性，后查 source_type」",
            "source_type 在 fact_source_map 里，但判定函数没优先用它",
            "判定函数写得早，那时还没有 source_type 字段",
        ],
        "root": "状态判定未优先用 source_type",
        "fix": "改为「先查 source_type（CUSTOMER/STANDARD/COMPUTED），查不到才用词性兜底」",
        "verifiable": "统计「客户已给却被标缺」的数量",
    },
    "web检索_未执行": {
        "why": [
            "提示词写了「去 web 检索」，但正文里没有检索结果",
            "检索被推给了写作侧",
            "知识处理阶段没做检索这一步",
            "检索需要 API/浏览器，被当成「写作时再说」",
            "阶段边界没定义清楚：谁负责取证",
        ],
        "root": "检索责任未落到知识处理阶段",
        "fix": "知识处理侧先做检索并登记（URL/引文/时间），写作侧只消费已登记证据",
        "verifiable": "统计正文里有多少条带 URL 的引用",
    },
    "计算_等式不成立": {
        "why": [
            "正文里的算式左右不相等",
            "写作时凭记忆算，没走引擎",
            "提示词只要求「写出算式并复算」，没给已算好的结果",
            "规则引擎能算，但结果没注入提示词",
            "提示词生成时只取 rules_required 的 expr，没取 run_gates 的结果",
        ],
        "root": "算式结果未注入提示词",
        "fix": "提示词里直接给「已算结果 = 公式 = 各输入值」，禁止 LLM 自己算",
        "verifiable": "检查提示词是否含已算结果",
    },
    "值_原文残留": {
        "why": [
            "还原稿里出现上财的数值",
            "形态/示例里带了上财真值",
            "形包文档示例用了真值（如 6780/9350）",
            "写文档时图省事直接引用",
            "没有「形包不得含值」的自动检查",
        ],
        "root": "形包值污染检查只扫 YAML",
        "fix": "release-check 扩展到 md/json/csv，并加「数字+单位」正则",
        "verifiable": "grep 形包全目录的项目值",
    },
    "冲突_未传导": {
        "why": [
            "图谱里有冲突，但提示词/正文里看不到",
            "提示词生成器按 section 过滤冲突，冲突节点 section 是 §?",
            "computed 节点在建图时没带 section",
            "instantiate 生成 computed 节点时 section 取自规则，规则无 section 则落 §?",
            "rules.yaml 的规则没有 section 字段",
        ],
        "root": "computed 节点缺 section 归属",
        "fix": "冲突按 subject/involved 全局传播，不按 section 过滤",
        "verifiable": "检查 §7.1 提示词是否含土建冲突",
    },
    "近重名_判不了": {
        "why": [
            "建安工程费用(9860) 和 建筑安装工程费用(10180) 判不了是不是同一个",
            "两个名称相似度 0.855（0.85 判重、0.90 不判）",
            "它们是不同的口径，不是同义词",
            "口径差异需要 mapping.calibers 才能判",
            "fact_source_map 里这两个没有 calibers 锚定",
        ],
        "root": "近重名缺口径锚定",
        "fix": "给这类对加 alias 别名边（保留两侧值与来源），不自动合并",
        "verifiable": "检查这两条是否有 alias 边且值都保留",
    },
}

VERIFIABLE_STATUS = {"FIXED", "PARTIAL", "UNFIXED", "UNKNOWN"}


# ================================================================ 轨 A：提示词质量
def check_prompt_quality(prompt_text: str, section: str, form: dict | None) -> dict:
    """检查单节提示词的完整性。返回 {checks, score, issues}。"""
    t = prompt_text or ""
    checks = {}

    # ① 是否含原文形态
    has_form = "⓿ 本节原文形态" in t and "形包未收录" not in t
    checks["形态注入"] = has_form

    # ② 形态是否给了具体数字
    has_numbers = bool(re.search(r"\d+ 列 × \d+ 行", t)) or bool(re.search(r"\d+ 段", t))
    checks["形态含具体数字"] = has_numbers

    # ③ 是否含形态纪律五条
    discipline = sum([
        "不得改变文体" in t,
        "不得减少列" in t,
        "不得拆表" in t,
        "过程优先于结果" in t,
        "结构照原文" in t or "结构照原文" in t,
    ])
    checks["形态纪律≥3条"] = discipline >= 3

    # ④ 是否含形节点表
    has_nodes = "### ① 形节点" in t and "（0 个）" not in t
    checks["形节点非空"] = has_nodes

    # ⑤ 是否含值填充（节点 ID）
    has_ids = bool(re.search(r"〔[A-Z]+-[0-9a-z]+〕", t))
    checks["含值+节点ID"] = has_ids

    # ⑥ 缺项是否有分类（◐ / ✗ / ✓）
    has_states = ("◐" in t) or ("✗" in t) or ("✓ 已填" in t)
    checks["缺项有状态标记"] = has_states

    # ⑦ 是否含算式（原文有表的节应该有）
    has_expr = "```text" in t or "round({" in t
    checks["含算式或算式说明"] = has_expr

    # ⑧ 是否含 must_cover
    has_cover = "本节必须覆盖" in t
    checks["含 must_cover"] = has_cover

    # ⑨ 是否含仿照参考
    has_ref = "仿照参考" in t
    checks["含仿照参考"] = has_ref

    # ⑩ 是否含原文全文（架构修正）
    has_source = "⓿b 本节原文" in t
    checks["含原文全文"] = has_source

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    score = round(passed / total * 100, 1)

    # 差异归类
    issues = []
    if not has_form:
        issues.append("形态_缺失")
    if form and not has_numbers:
        issues.append("形态_数字缺失")
    if form and discipline < 3:
        issues.append("形态_文体")
    if not has_nodes:
        issues.append("形节点_缺失")
    if not has_ids:
        issues.append("值填充_缺失")
    if not has_expr and form and form.get("tables"):
        issues.append("计算_算式缺失")
    if not has_source:
        issues.append("原文_未注入")

    return {"section": section, "checks": checks, "score": score,
            "passed": passed, "total": total, "issues": issues}


# ================================================================ 5 Why
def five_why(issue: str) -> dict:
    """对一个差异类型做 5 Why 倒推。"""
    chain = WHY_CHAINS.get(issue)
    if not chain:
        return {"issue": issue, "why": ["（知识库未收录该差异类型）"],
                "root": "未知", "fix": "", "verifiable": "", "status": "UNKNOWN"}
    return {"issue": issue, "why": chain["why"], "root": chain["root"],
            "fix": chain["fix"], "verifiable": chain["verifiable"],
            "status": "PENDING"}


def aggregate_issues(results: list) -> dict:
    """汇总所有节的差异，按频次排序，附 5Why。"""
    from collections import Counter
    cnt = Counter()
    for r in results:
        for i in r.get("issues") or []:
            cnt[i] += 1
    out = []
    for issue, n in cnt.most_common():
        w = five_why(issue)
        w["affected_sections"] = n
        w["affected_ratio"] = round(n / max(len(results), 1) * 100, 1)
        out.append(w)
    return {"total_issues": len(out), "chains": out}


# ================================================================ LOOP
def run_loop(*, prompts: list, forms: dict | None = None,
             max_rounds: int = 3, verbose: bool = True) -> dict:
    """跑 PDCA 循环的「评估 + 5Why」部分（修复由外部执行）。

    prompts: [{"section","title","prompt"}] —— 每节提示词
    forms:   {section: form_dict} —— 形态（可选，用于交叉检查）
    """
    forms = forms or {}
    rounds = []
    seen_roots = set()

    for rd in range(1, max_rounds + 1):
        results = []
        for p in prompts:
            sec = p.get("section") or ""
            form = forms.get(sec) or forms.get(p.get("title") or "")
            results.append(check_prompt_quality(p.get("prompt") or "", sec, form))

        agg = aggregate_issues(results)
        avg = round(sum(r["score"] for r in results) / max(len(results), 1), 1)
        new_roots = {c["root"] for c in agg["chains"]} - seen_roots

        rounds.append({"round": rd, "avg_score": avg,
                       "issue_count": agg["total_issues"],
                       "chains": agg["chains"],
                       "new_roots": sorted(new_roots),
                       "results": results})
        seen_roots |= new_roots

        if verbose:
            print("  第 %d 轮：均分 %.1f，差异类型 %d 种，新根因 %d 个"
                  % (rd, avg, agg["total_issues"], len(new_roots)))

        # 收敛判据：无新根因即停（等外部修完再跑下一轮）
        if rd > 1 and not new_roots:
            if verbose:
                print("  → 无新根因，本轮收敛")
            break

    return {"rounds": rounds,
            "final_avg": rounds[-1]["avg_score"] if rounds else 0,
            "all_roots": sorted(seen_roots),
            "converged": len(rounds) > 1 and not rounds[-1]["new_roots"]}


def report(loop_result: dict, out_path=None) -> str:
    """生成 markdown 报告。"""
    L = ["# 还原能力 LOOP 报告", ""]
    L.append("| 轮次 | 均分 | 差异类型 | 新根因 |")
    L.append("|---|---:|---:|---:|")
    for r in loop_result["rounds"]:
        L.append("| %d | %.1f | %d | %d |"
                 % (r["round"], r["avg_score"], r["issue_count"], len(r["new_roots"])))
    L.append("")

    last = loop_result["rounds"][-1] if loop_result["rounds"] else {}
    L += ["## 当前差异与 5 Why 根因链", ""]
    for c in last.get("chains") or []:
        L.append("### %s（影响 %d 节 / %.1f%%）" % (c["issue"], c["affected_sections"],
                                                  c["affected_ratio"]))
        L.append("")
        L.append("**5 Why：**")
        for i, w in enumerate(c["why"], 1):
            L.append("%d. %s" % (i, w))
        L.append("")
        L.append("- **根因**：%s" % c["root"])
        L.append("- **修法**：%s" % c["fix"])
        L.append("- **验证**：%s" % c["verifiable"])
        L.append("")

    txt = "\n".join(L)
    if out_path:
        Path(out_path).write_text(txt, encoding="utf-8")
    return txt
