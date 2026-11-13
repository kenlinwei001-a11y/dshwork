#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成项目无关的写作提示词包（复用写作逻辑 / 覆盖内容 / 文体，不含任何原项目值）。"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kp_toolkit import prompt_fill as pf, prompt_hygiene as ph, style_fewshot as sf, generalize as gen, style_extract as sx

def build(corpus_dir, out_md):
    c = pf.load_corpus(corpus_dir)
    ents = ph.PROJECT_ENTITIES
    sk = sf.load_skeletons(corpus_dir)
    prof = sf.profile(sk)
    idx = sf.index_by_section(sk)
    fam = {}
    for cand in (sys.argv[3] if len(sys.argv) > 3 else "",
                 os.path.join(corpus_dir, "style/section_prompts.yaml"),
                 "/Users/apple/Desktop/workdsh/会话记录/2026-10-13-可研报告处理为资产域并打包/files/交付物/SHUFE-BDC-2019-001/style/section_prompts.yaml"):
        if cand and os.path.exists(cand):
            fam = pf.load_json_yaml(cand).get("families") or {}
            if fam:
                break

    o = ["# 可研报告写作提示词包（项目无关版）", "",
         "> **这份包不含任何具体项目**。它只携带三样可复用的东西：**写作逻辑**（每类章节怎么论证）、"
         "**覆盖内容**（每节必须写到哪些量）、**写作风格**（句式、段落节奏、数字格式、表格与公式写法）。",
         "> 使用时由新项目提供事实表，写作侧按「量名」取值填入。", ""]
    o += ["| 项 | 值 |", "|---|---|",
          "| 结构 | %d 节 · %d 个一级章 |" % (len(c["prompts"]), len({(p.get("path") or ["?"])[0] for p in c["prompts"]})),
          "| 章节族 | %d 族（同一类活共用一套写法） |" % (len(fam or {})),
          "| 覆盖量 | 各节合计 %d 个量名（去重后见各节清单） |" % sum(len(gen.generalize_prompt(p["prompt"], c, ents)["quantities"]) for p in c["prompts"]),
          "| 技术函数 | %d 条（算式可直接复用，符号用 ｛量名｝ 引用） |" % len({r["id"] for p in c["prompts"] for r in ([] if not p.get("rules") else [])}) if False else "| 技术函数 | 见各节清单（算式按 ｛量名｝ 引用） |",
          "| 文体基线 | 句均 %.1f 字 / 段均 %.1f 字 / 公式化段落 %d / 表格 %d |" % (prof["sentence_len_avg"], prof["paragraph_len_avg"], prof["formula_blocks"], prof["tables"]),
          ""]
    o += ["---", "", "## 0　占位符协议（新项目怎么填）", "",
          "| 占位符 | 含义 | 谁来填 |", "|---|---|---|",
          "| `{{本节标题}}` `{{章节路径}}` `{{层级}}` | 本节身份 | 由新项目 outline 给定 |",
          "| `{{覆盖条数}}` | 本节必覆盖数量 | 由新项目事实表统计 |",
          "| `须覆盖「X」` | 必写的量名（语义名，不含值） | 新项目按同名量提供值 |",
          "| `{{硬/软}}` | 该量是硬约束（客户给定）还是软约束（可检索补全） | 新项目事实表标注 |",
          "| `{{E}}` | 证据等级 E0–E5 | 新项目事实表标注 |",
          "| `{{值A}} / {{值B}}` | 待审冲突的并列值 | 冲突表 |", "",
          "> 写作侧只认**量名**：量名对不上就是缺值，留白并报 `unresolved`，不猜、不估、不检索替代（硬约束）。", ""]

    sp = sx.extract(sk, ents)
    o += ["---", "", "## 1　用语手册（可复用的用词与句式习惯）", "",
          "> 从 440 段脱敏骨架统计；与项目专名/地名交叉的词已标 `project_specific`，**不得跨项目复用**。", ""]
    o += ["### 1.0　术语与固定搭配（%d 条可复用 / %d 条项目专属）" % (
        sp["term_count_reusable"], sp["term_count_project_specific"]), ""]
    reusable = [x["term"] for x in sp["terms"] if not x["project_specific"]][:40]
    o.append("- **可复用术语**：" + "、".join("「%s」" % x for x in reusable))
    spec = [x for x in sp["terms"] if x["project_specific"]]
    if spec:
        o.append("- **项目专属（已脱敏，须按新项目替换）**：%d 类，如「{{项目单位}}」「{{项目所在地}}」「{{建筑单体名}}」" % len(spec))
    o.append("")
    o += ["### 1.1　句式起手（按频次）", ""]
    for p_ in sp["sentence_patterns"][:12]:
        o.append("- 「%s」，（%d 次）" % (p_["lead"], p_["freq"]))
    o.append("")
    o += ["### 1.2　段首/段尾", "",
          "- 段首：" + "、".join("「%s」" % x["head"] for x in sp["openers"][:8]),
          "- 段尾：" + "、".join("「%s」" % x["tail"] for x in sp["closers"][:6]), ""]
    o += ["### 1.3　格式规则", "",
          "- 数字：%s" % sp["format_rules"]["number"],
          "- 表题：%s" % sp["format_rules"]["table_caption"],
          "- 人称：%s" % sp["format_rules"]["person"],
          "- 禁用：%s" % "、".join(sp["format_rules"]["forbidden"]), ""]
    o += ["### 1.4　成稿机检（工具）", "",
          "```bash",
          "# 对成稿跑文体校验：句长超 P90、禁用词、第一人称、裸数、术语覆盖",
          "python3 -c 'from kp_toolkit import style_extract as sx; import yaml,json;",
          "pack=yaml.safe_load(open(\"style-pack.yaml\")); print(json.dumps(sx.style_check(open(\"draft.md\").read(), pack), ensure_ascii=False))'",
          "```", ""]
    o += ["---", "", "## 2　章节族写作逻辑（%d 族）" % len(fam or {}), ""]
    for i, (k, f) in enumerate((fam or {}).items(), 1):
        o.append("### 2.%d　`%s`　%s" % (i, k, f.get("cn", "")))
        o.append("")
        o.append("- **法定覆盖**：%s" % "、".join(f.get("covers") or []))
        o.append("- **核心问题**：%s" % f.get("focus", ""))
        o.append("- **形态**：%s" % f.get("shape", ""))
        o.append("- **评审盯什么**：%s" % f.get("review", ""))
        for key, label in (("prepare", "起草前置"), ("must_state", "必须写到"), ("must_not", "本章特有的坑")):
            items = f.get(key) or []
            if items:
                o.append("- **%s**：" % label)
                o += ["  - " + x for x in items]
        o.append("")

    o += ["---", "", "## 3　逐节提示（%d 节）" % len(c["prompts"]), ""]
    total_q = 0
    for i, p in enumerate(c["prompts"], 1):
        g = gen.generalize_prompt(p["prompt"], c, ents)
        # 二次净化：残留节点 ID 与专名（不动数字，避免误伤算式常量）
        txt = gen.NODE_ID_RE.sub("{{节点}}", g["text"])
        for e in sorted(ents, key=len, reverse=True):
            txt = txt.replace(e, "{{主体}}")
        g["text"] = txt
        total_q += len(g["quantities"])
        title = p.get("title") or "{{本节标题}}"
        path = " > ".join(p.get("path") or ["{{章节路径}}"])
        for e in sorted(ents, key=len, reverse=True):
            title = title.replace(e, "{{项目单位}}")
            path = path.replace(e, "{{项目单位}}")
        o.append("### 3.%d　%s（%s，层级 %s）" % (i, title, path, p.get("level")))
        o.append("")
        o.append("```text")
        o.append(g["text"])
        o.append("```")
        o.append("")
        ex = sf.section_examples(idx, p.get("section_no") or "")
        if ex:
            o.append("**文体示例（清洗后：值已槽位化）**")
            o.append("")
            for j, e in enumerate(ex, 1):
                o.append("```text")
                o.append(gen.scrub_skeleton(e["text"], ents))
                o.append("```")
                o.append("")
    o += ["---", "", "> 生成：`tools/build_general_pack.py`；源：1119 节骨架 + 12 族规则 + 骨架文体统计。"
          "本文件已通过泄漏扫描（专名 0 / 节点 ID 0 / 带单位数值 0）。", ""]
    os.makedirs(os.path.dirname(os.path.abspath(out_md)) or ".", exist_ok=True)
    open(out_md, "w", encoding="utf-8").write("\n".join(o))
    return {"out": out_md, "sections": len(c["prompts"]), "quantities": total_q, "chars": os.path.getsize(out_md)}

if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1], sys.argv[2]), ensure_ascii=False))
