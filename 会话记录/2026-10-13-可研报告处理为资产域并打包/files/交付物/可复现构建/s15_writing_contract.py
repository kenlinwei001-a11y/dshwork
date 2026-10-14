# -*- coding: utf-8 -*-
"""对齐「推演写作专家」的消费契约（确定性）。

该专家的 SKILL.md 明确输入是「语料包（30 文件契约，入口 manifest.yaml）+ 语义图谱」，
三通道消费：① 注入（constraints/meta/outline/style/术语/gate 结论行）
② 工具（corpus_get_skeleton / corpus_get_chunk / graph_query / graph_explain / graph_why / evidence_get …）
③ 内嵌（每节工作包：facts≤30 + claims + conflicts + gaps + skeleton 指针）

本脚本补齐 8 项契约缺口：
  G1 每节工作包          → wp/<NN>-<节>.yaml + wp/index.yaml
  G2 章节骨架（非空壳）  → style/section_skeletons/<NN>-<节>.yaml（段落顺序/表格列/句式骨架）
  G3 节点 status         → defined / undefined（+instruction）/ pending_review
  G4 节点 caliber        → 价格水平与面积口径
  G5 节点 kind           → quantity / judgment / text 三类
  G6 style_profile.terminology → 由 index/term_index.json 注入
  G7 占位符形式          → 统一 {{node:N-xxxxxxxxxxxx}}
  G8 节点 inheritable    → 判定量/结论 never，数值与文本 yes
并把写作契约登记进 manifest。
"""
import json
import re
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
PLACEHOLDER = "{{node:N-xxxxxxxxxxxx}}"


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def W(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


nodes = J(ROOT / "graph" / "nodes.yaml")
rules = J(ROOT / "graph" / "rules.yaml")
claims = J(ROOT / "graph" / "claims.yaml")
outline = J(ROOT / "outline.yaml")
conflicts = J(ROOT / "quality" / "conflicts.yaml")
gaps = J(ROOT / "quality" / "gaps.yaml")
derivation = J(ROOT / "reasoning" / "derivation.yaml")
terms = J(ROOT / "index" / "term_index.json")
SEC_PROMPTS = J(ROOT / "style" / "section_prompts.yaml")
SP = {x["chapter"]: x for x in SEC_PROMPTS["sections"]}
style = J(ROOT / "style" / "style_profile.yaml")
chunks = [json.loads(l) for l in (ROOT / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
skels = {json.loads(l)["id"]: json.loads(l) for l in
         (ROOT / "chunks" / "skeletons.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
chunk_by_id = {c["id"]: c for c in chunks}

# ── 归属 ────────────────────────────────────────────────────────────────
def chapter_of(cid):
    sp = (chunk_by_id.get(cid, {}).get("section_path") or [])
    return sp[0] if sp else "（未归属）"


for n in nodes:
    n["_chapter"] = chapter_of(n.get("source", ""))
    n["_path"] = chunk_by_id.get(n.get("source", {}), {}).get("section_path") or []

# ── G5 kind / G4 caliber / G3 status / G8 inheritable ───────────────────
JUDGMENT_PRED = re.compile(
    r"名称|地点|性质|形式|类别|等级|类别|年代|型号|牌号|系统$|体制|方式|类别|依据|状态|"
    r"来源|渠道|位置|形式及|标志|形式$|层数|分类|类型|品牌|颜色|编号|日期|时间$|分组|场地类别|"
    r"粗糙度|标准|目标|结论|判定|等级|设防|星级|率$|比$")
NUMERIC_UNIT = re.compile(r"^(万元|元|㎡|m|㎡/人|人|个|项|台|套|部|层|吨|米|毫米|MPa|kN|kW|kW·h|kWh|"
                          r"m³|L|L/s|W|V|A|℃|%|d|h|年|月|天|次|间|座|处|千米|公顷|亩|千卡|tce|Pa|dB|g|"
                          r"m³/d|m³/h|kgce|万m³|万kW·h|元/㎡|㎡/间|人|棵|辆|孔|回路|MW|kV|kVA|HP|HP台)$")


def classify(n):
    pred, val, unit, kind0 = n["predicate"], str(n["value"]), n["unit"], n.get("kind")
    is_num = bool(re.match(r"^-?[\d,]+(?:\.\d+)?$", val.replace("%", "").strip()))
    if kind0 == "judgment":
        return "judgment"
    if unit and (is_num or "%" in val):
        return "quantity"
    if is_num and (unit or NUMERIC_UNIT.match(unit or "")):
        return "quantity"
    if JUDGMENT_PRED.search(pred) or not is_num:
        return "judgment" if JUDGMENT_PRED.search(pred) else "text"
    return "quantity"


CONFLICT_KEYS = {(c["subject"], c["predicate"]) for c in conflicts if c["type"] == "numeric"}
BLOCKED = {u["rule"]: u for u in derivation["unresolved_rules"] if u.get("reason") == "blocked_by_conflict"}
MISSING_RULES = {u["rule"]: u for u in derivation["unresolved_rules"] if u.get("reason") == "missing_deps"}
RULE_BY_ID = {r["id"]: r for r in rules}
UNDEF_TARGETS = set()
for rid, u in {**BLOCKED, **MISSING_RULES}.items():
    r = RULE_BY_ID.get(rid)
    if r:
        UNDEF_TARGETS.add((r.get("target", ""), rid))
GAP_SUBJECTS = {str(g.get("subject", "")) for g in gaps}

for n in nodes:
    n["kind"] = classify(n)
    # caliber：价格水平与面积口径（专家要求数值量核对 unit + caliber）
    unit = n.get("unit", "")
    if unit in ("万元", "元", "元/㎡"):
        n["caliber"] = "2019年价格水平（报告编制期，未做价格调整）"
    elif unit == "㎡":
        n["caliber"] = "使用面积" if "使用面积" in n["predicate"] else "建筑面积"
    elif unit in ("㎡/人",):
        n["caliber"] = "建筑面积口径"
    else:
        n["caliber"] = ""
    # status
    key = (n["subject"], n["predicate"])
    tgt = [rid for (t, rid) in UNDEF_TARGETS if t and t == n["predicate"] and n["subject"] in ("本项目", n["subject"])]
    if key in CONFLICT_KEYS:
        n["status"] = "pending_review"
        n["instruction"] = "该 (主题, 属性) 存在未裁决数值冲突，正文并列呈现并标「⚠ 待审」，不得取其一。"
    elif tgt or n["predicate"] in {t for (t, _) in UNDEF_TARGETS if t} or n["subject"] in GAP_SUBJECTS:
        n["status"] = "undefined"
        n["instruction"] = "依赖缺失或口径未给出，按定性措辞表述（如「待…后测算」）并挂 gap，永不按 0 计算。"
    else:
        n["status"] = "defined"
        n["instruction"] = ""
    # inheritable：判定量与结论不跨项目继承
    n["inheritable"] = "never" if n["kind"] in ("judgment",) else "yes"

# 节点落盘在 L1 定义之后（需要章节序号）

# ── G2 章节骨架（真实骨架，替换空壳）────────────────────────────────────
SK = ROOT / "style" / "section_skeletons"
SK.mkdir(parents=True, exist_ok=True)
(TBL := re.compile(r"```table\n([\s\S]*?)```"))
L1 = [s["title"] for s in outline["sections"] if s["level"] == 1]

_IDX = {ch: i for i, ch in enumerate(L1, 1)}
_nodes_out = []
for n in nodes:
    n["section"] = n["_chapter"]
    n["section_index"] = _IDX.get(n["_chapter"], 0)
    _nodes_out.append({k: v for k, v in n.items() if not k.startswith("_")})
W(ROOT / "graph" / "nodes.yaml", _nodes_out)
SEC_CLAIMS = {}
for c in claims:
    SEC_CLAIMS.setdefault(chapter_of(c.get("source", "")), []).append(c)


def sentence_pattern(text, limit=6):
    """把骨架句做槽位化：占位符 → {{node}}，数字 → 数字槽。"""
    out = re.sub(r"\{\{node:N-[0-9a-f]+\}\}", "{{node}}", text)
    out = re.sub(r"[\d,]+(?:\.\d+)?%?", "⟨数字⟩", out)
    return out[:180]


skeleton_index = []
for i, ch in enumerate(L1, 1):
    cids = [c["id"] for c in chunks if chapter_of(c["id"]) == ch]
    seq, tables, patterns = [], [], []
    for cid in cids:
        c = chunk_by_id[cid]; t = c["text"]
        if c["type"] == "table":
            m = TBL.search(t)
            body = m.group(1).strip().split("\n") if m else []
            cols = [x.strip() for x in body[0].strip("|").split("|")] if body else []
            cap = ""
            prev = chunk_by_id.get(chunks[cids.index(cid) - 1]["id"], {}) if cids.index(cid) > 0 else {}
            cap = (prev.get("text", "")[:40] if prev.get("text", "").startswith("表") else "")
            tables.append({"caption": cap, "columns": cols, "rows": max(0, len(body) - 2)})
            seq.append({"type": "table", "n": 1, "columns": cols})
        elif c["type"] == "heading":
            seq.append({"type": "heading", "level": t.count("# ", 0, t.find(" ")) or t.split(" ")[0].count("#"),
                        "title": t.lstrip("# ").strip()})
        else:
            sk = skels.get(cid, {}).get("text", t)
            if len(seq) and seq[-1]["type"] == "paragraph":
                seq[-1]["n"] += 1
            else:
                seq.append({"type": "paragraph", "n": 1,
                            "skeleton_sample": sentence_pattern(sk)})
    for c in SEC_CLAIMS.get(ch, []):
        t = c.get("toulmin") or {}
        for k in ("claim", "grounds", "warrant"):
            v = t.get(k, "")
            if v and not v.startswith("**（"):
                patterns.append(sentence_pattern(v, 0))
    doc = {
        "section": ch, "section_index": i, "level": 1,
        "source": "由原报告同章确定性抽取（段落顺序 / 表格列结构 / 句式骨架）",
        "placeholder_form": PLACEHOLDER,
        "block_sequence": seq,
        "tables": tables,
        "argument_sentence_patterns": patterns[:12],
        "note": "骨架给「怎么写」：段落功能顺序、表格列结构、论证句式槽位。"
                "数值一律写占位符，不写本项目的字面数字。",
    }
    W(SK / f"{i:02d}-{ch}.yaml", doc)
    # corpus_get_skeleton 读的是 style/section_templates/<stem>.yaml —— 同步写入真骨架
    W(ROOT / "style" / "section_templates" / f"{i:02d}-{ch}.yaml",
      {**doc, "template": "## " + ch, "skeleton_source": "由原报告同章确定性抽取"})
    skeleton_index.append({"index": i, "section": ch, "blocks": len(seq), "tables": len(tables),
                           "patterns": len(patterns), "file": f"style/section_skeletons/{i:02d}-{ch}.yaml"})
W(SK / "index.yaml", {"sections": skeleton_index, "count": len(skeleton_index)})

# ── G1 每节工作包 ───────────────────────────────────────────────────────
WP = ROOT / "wp"
WP.mkdir(parents=True, exist_ok=True)
CONF_BY_CH, GAP_BY_CH = {}, {}
for c in conflicts:
    hit = [n["_chapter"] for n in nodes if n["id"] in c.get("involved", [])]
    for h in (sorted(set(hit)) or ["（未归属）"]):
        CONF_BY_CH.setdefault(h, []).append(c)
for g in gaps:
    succ = g.get("rule") and RULE_BY_ID.get(g["rule"])
    deps = succ.get("deps", []) if succ else []
    hs = {n["_chapter"] for n in nodes if n["predicate"] in deps or (succ and n["predicate"] == succ.get("target"))}
    for h in hs or {"（未归属）"}:
        GAP_BY_CH.setdefault(h, []).append(g)

wp_index = []
for i, ch in enumerate(L1, 1):
    sub = [n for n in nodes if n["_chapter"] == ch]
    uniq = list({n["id"]: n for n in sub}.values())
    # facts ≤30：优先冲突相关 > undefined > 被规则引用 > 出现次数
    refd = {d for r in rules for d in r.get("deps", [])} | {r.get("target", "") for r in rules}
    conf_ids = {x for c in CONF_BY_CH.get(ch, []) for x in c.get("involved", [])}

    def prio(n):
        return (0 if n["id"] in conf_ids else 1,
                0 if n["status"] == "undefined" else 1,
                0 if n["predicate"] in refd else 1,
                -sum(1 for x in nodes if x["id"] == n["id"]))
    picked = sorted(uniq, key=prio)[:30]
    wp = {
        "section": ch, "section_index": i, "level": 1,
        "outline": {"must_cover": next((x["covers"] for x in []) or [], []),
                    "title": ch, "skeleton": f"style/section_skeletons/{i:02d}-{ch}.yaml",
                    "length_target": None,
                    "length_note": "客户未给分章字数；按 §2 形态描述把握详略（该章形态见 章节提示词索引.md）"},
        "facts": [{"node_id": n["id"], "subject": n["subject"], "predicate": n["predicate"],
                   "value": n["value"], "unit": n["unit"], "kind": n["kind"], "caliber": n["caliber"],
                   "status": n["status"], "inheritable": n["inheritable"],
                   "instruction": n["instruction"], "chunk": n["source"]} for n in picked],
        "facts_total_in_section": len(uniq), "facts_truncated": len(uniq) > 30,
        "claims": [{"id": c["id"], "text": c.get("text"), "claim_type": c.get("claim_type"),
                    "status": c.get("status"), "toulmin": c.get("toulmin"),
                    "evidence_refs": c.get("evidence_refs", [])}
                   for c in claims if chapter_of(c.get("source", "")) == ch],
        "conflicts": CONF_BY_CH.get(ch, []),
        "gaps": GAP_BY_CH.get(ch, []),
        "rules_touching_section": [{"id": r["id"], "label": r.get("label"), "expr": r.get("expr"),
                                    "deps": r.get("deps"), "target": r.get("target"),
                                    "recheck": ("派生差异" if r["id"] in {d['rule'] for d in derivation['derivation_diff']}
                                                else "阻塞(冲突未裁决)" if r["id"] in BLOCKED
                                                else "未解(缺口径)" if r["id"] in MISSING_RULES else "闭合")}
                                   for r in rules
                                   if any(n["predicate"] in r.get("deps", []) or n["predicate"] == r.get("target")
                                          for n in uniq)],
        "return_contract": {
            "draft_md": "正文 Markdown，数值一律 " + PLACEHOLDER + "，不得写字面量",
            "node_mentions": "[{node_id, char_span, form}]",
            "new_claims": "[{text, supports[], evidence[]}]",
            "unresolved": "[{what, why, need_from_client}]",
        },
    }
    W(WP / f"{i:02d}-{ch}.yaml", wp)

    # ── 同时按 kp 约定落盘：project/work_packages/<section_id>.json ──
    # wp_get_facts 优先读这里；gate_check_draft 从 outline.must_cover 做关键词核销。
    sid = f"{i:02d}-{ch}"
    sub_titles = [x["title"] for x in outline["sections"]
                  if x["level"] == 2 and x["title"] in {t for t in
                  [c["text"].lstrip("# ").strip() for c in chunks
                   if c["type"] == "heading" and len((c.get("section_path") or [])) == 2
                   and (c.get("section_path") or [""])[0] == ch]}]
    must_cover = sub_titles or [ch]
    kw = SP.get(ch, {}).get("covers", [])
    kp_wp = {
        "work_package_id": f"WP-{sid}",
        "outline": {"section": sid, "title": ch,
                    "must_cover": must_cover,                     # 闸门按此做关键词核销（用文档自身小节标题，可检出）
                    "must_cover_legal": kw,                        # 法定内容项（人读，不参与闸门）
                    "word_budget": [1200, 1800],
                    "length_note": "客户未给分章字数；按章节形态把握详略（见 写作输入/章节提示词索引.md）"},
        "facts": [{"id": n["id"], "node_id": n["id"], "subject": n["subject"], "predicate": n["predicate"],
                   "value": n["value"], "unit": n["unit"], "kind": n["kind"], "caliber": n["caliber"],
                   "status": n["status"], "instruction": n["instruction"],
                   "inheritable": n["inheritable"], "chunk": n["source"]} for n in picked],
        "facts_paging": {"total": len(uniq), "page_size": 30, "pages": (len(uniq) + 29) // 30,
                         "tool": "wp_get_facts",
                         "note": "facts 超过 30 条时按页拉取（本节完整条数见 facts_paging.total）"},
        "claims": wp["claims"], "conflicts": wp["conflicts"], "gaps": wp["gaps"],
        "undefined": [{"node_id": n["id"], "predicate": n["predicate"], "instruction": n["instruction"]}
                      for n in picked if n["status"] == "undefined"],
        "skeleton": {"from_corpus": str(ROOT), "section": sid,
                     "file": f"style/section_templates/{sid}.yaml",
                     "forbid": ["原文中的字面数值", "把本项目的结论当新项目结论"]},
        "rules_touching_section": wp["rules_touching_section"],
        "return_contract": wp["return_contract"],
    }
    P = ROOT / "project" / "work_packages"
    P.mkdir(parents=True, exist_ok=True)
    (P / f"{sid}.json").write_text(json.dumps(kp_wp, ensure_ascii=False, indent=2), encoding="utf-8")
    wp_index.append({"index": i, "section": ch, "section_id": sid, "facts": len(picked), "of_total": len(uniq),
                     "claims": len(wp["claims"]), "conflicts": len(wp["conflicts"]),
                     "gaps": len(wp["gaps"]), "must_cover": len(must_cover),
                     "file": f"wp/{sid}.yaml", "kp_workpackage": f"project/work_packages/{sid}.json"})
W(WP / "index.yaml", {"workpackages": wp_index, "count": len(wp_index),
                      "push_order": "按 §2.2 章节顺序；概述与结论最后推（它们是全篇投影/复述）",
                      "note": "每节工作包即专家 SKILL.md 的通道③「内嵌」。"})

# ── G6 style_profile.terminology ────────────────────────────────────────
style["terminology"] = {t["surface"]: t["canonical"] for t in terms[:30] if t["surface"] != t["canonical"]}
style["citation_style"] = "依据《{标准名称}》（{版本}）{条款}；行内溯源标记 〔CL｜R｜E〕"
style["number_format"] = "千分位、保留与原文一致的小数位、单位后置、金额优先「万元」"
style["forbidden"] = style.get("forbidden", []) + ["较为", "基本上", "原则上", "暂按经验值", "大约"]
style["placeholder_form"] = PLACEHOLDER
W(ROOT / "style" / "style_profile.yaml", style)

# ── manifest 登记写作契约 ──────────────────────────────────────────────
m = J(ROOT / "manifest.yaml")
m["writing_contract"] = {
    "consumer": "推演写作专家（推演式报告写作 / corpus-deductive-writer）",
    "entry": "manifest.yaml",
    "channels": {
        "inject": ["manifest.constraints", "meta.yaml", "outline.yaml（本节）",
                   "style/style_profile.yaml", "index/term_index.json", "quality/gate_report.yaml（结论行）"],
        "tool": ["corpus_get_skeleton", "corpus_get_chunk", "graph_query", "graph_explain",
                 "graph_why", "evidence_get", "corpus_where_used", "graph_impact"],
        "inline_workpackage": "wp/<NN>-<节>.yaml",
    },
    "placeholder_form": PLACEHOLDER,
    "node_contract": {"kinds": ["quantity", "judgment", "text"],
                      "status_values": ["defined", "undefined", "pending_review"],
                      "fields": ["id", "subject", "predicate", "value", "unit", "kind",
                                 "caliber", "status", "instruction", "inheritable", "source"]},
    "skeleton_dir": "style/section_skeletons/",
    "workpackage_dir": "wp/",
    "gate": "gate_check_draft 由编排器调用，不由写作 Agent 自判",
}
W(ROOT / "manifest.yaml", m)

print(json.dumps({
    "nodes_total": len(nodes),
    "kind": {k: sum(1 for n in nodes if n["kind"] == k) for k in ("quantity", "judgment", "text")},
    "status": {s: sum(1 for n in nodes if n["status"] == s) for s in ("defined", "undefined", "pending_review")},
    "caliber_filled": sum(1 for n in nodes if n["caliber"]),
    "inheritable_never": sum(1 for n in nodes if n["inheritable"] == "never"),
    "section_skeletons": len(skeleton_index),
    "workpackages": len(wp_index),
    "terminology_entries": len(style["terminology"]),
}, ensure_ascii=False, indent=2))
