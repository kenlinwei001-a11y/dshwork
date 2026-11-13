#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文体层：把「脱敏骨架」做成 few-shot，并给出可机检的文体画像。

为什么要有这一层：
  前面的逐节提示词只约束了**写什么**（覆盖/取值/函数/冲突），没有约束**怎么写**。
  同一批节点，可以写成评审看得懂的论证，也可以写成一堆正确的空话——差别就在文体。
  本语料包的 438 段脱敏骨架已经把原报告的句式结构保留下来、把项目值抽成槽位
  （{{node:ID}} / {{ent:角色}} / {{time:YYYY-MM}}），因此**天然就是 few-shot 素材**：
  借形（句式、叙述顺序、段落节奏）不借值（槽位必须用目标项目节点重填）。

确定性：
  - 选例规则固定（同节 → 段落 → 含值槽位优先 → 按原文顺序 → 累计字数上限）。
  - 画像指标全部由骨架文本统计得出，不含模型判断。
"""
from __future__ import annotations

import json
import os
import re
import statistics
from typing import Any, Dict, List, Optional

SLOT_RE = re.compile(r"\{\{(?:node|ent|time):[^}]+\}\}")
SENT_SPLIT = re.compile(r"(?<=[。；！？])")
FORMULA_PREFIX = "$$"


def load_skeletons(corpus_dir: str) -> List[Dict[str, Any]]:
    path = os.path.join(corpus_dir, "chunks/skeletons.jsonl")
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _paras(skeletons: List[Dict[str, Any]], min_len: int = 40) -> List[Dict[str, Any]]:
    return [s for s in skeletons if s.get("type") == "paragraph" and len(s.get("text") or "") >= min_len]


def profile(skeletons: List[Dict[str, Any]]) -> Dict[str, Any]:
    paras = _paras(skeletons)
    sents: List[str] = []
    for p in paras:
        sents += [s for s in SENT_SPLIT.split(p["text"]) if s.strip()]
    sl = [len(s) for s in sents] or [0]
    pl = [len(p["text"]) for p in paras] or [0]
    heads: Dict[str, int] = {}
    for p in paras:
        h = SLOT_RE.sub("", p["text"]).strip()[:6].replace("\n", " ")
        if h:
            heads[h] = heads.get(h, 0) + 1
    tables = [s for s in skeletons if s.get("type") == "table"]
    return {
        "paragraphs": len(paras),
        "sentence_len_avg": round(statistics.mean(sl), 1),
        "sentence_len_p50": statistics.median(sl),
        "sentence_len_p90": sorted(sl)[max(0, int(len(sl) * 0.9) - 1)],
        "paragraph_len_avg": round(statistics.mean(pl), 1),
        "paragraph_len_p90": sorted(pl)[max(0, int(len(pl) * 0.9) - 1)],
        "formula_blocks": sum(1 for p in paras if p["text"].strip().startswith(FORMULA_PREFIX)),
        "with_node_slots": sum(1 for p in paras if "{{node:" in p["text"]),
        "with_entity_slots": sum(1 for p in paras if "{{ent:" in p["text"]),
        "with_time_slots": sum(1 for p in paras if "{{time:" in p["text"]),
        "tables": len(tables),
        "slot_density": round(sum(len(SLOT_RE.findall(p["text"])) for p in paras) / len(paras), 2),
        "top_heads": sorted(heads.items(), key=lambda kv: (-kv[1], kv[0]))[:8],
    }


def index_by_section(skeletons: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    idx: Dict[str, List[Dict[str, Any]]] = {}
    for s in skeletons:
        key = str(s.get("section_struct_no") or "")
        if key:
            idx.setdefault(key, []).append(s)
    for k in idx:
        idx[k].sort(key=lambda x: (x.get("index") or 0))
    return idx


def _trim_tail(text: str) -> str:
    """骨架常把下一节标题黏在段尾（如「地震」「地形地貌」），去掉这类残尾。"""
    lines = [ln for ln in text.splitlines()]
    while lines:
        last = lines[-1].strip()
        if last and len(last) <= 12 and not re.search(r"[。；，：！？]", last):
            lines.pop()
            continue
        break
    return "\n".join(lines).strip()


def _clip(text: str, limit: int) -> str:
    text = _trim_tail(text.strip())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in ("。", "；", "，"):
        pos = cut.rfind(mark)
        if pos > limit * 0.6:
            return cut[: pos + 1] + "……"
    return cut + "……"


def pick_examples(blocks: List[Dict[str, Any]], k: int = 3,
                  budget: int = 900, clip: int = 420) -> List[Dict[str, Any]]:
    """选例：段落 → 含值槽位优先 → 原文顺序；总字数受 budget 约束。"""
    paras = [b for b in blocks if b.get("type") == "paragraph" and len(b.get("text") or "") >= 40]
    if not paras:
        paras = [b for b in blocks if len(b.get("text") or "") >= 40]
    paras.sort(key=lambda b: (0 if "{{node:" in b["text"] else 1, b.get("index") or 0))
    picked, used = [], 0
    for b in paras:
        text = _clip(b["text"], clip)
        if used + len(text) > budget and picked:
            break
        picked.append({"index": b.get("index"), "text": text,
                       "slots": len(SLOT_RE.findall(b["text"])),
                       "type": b.get("type")})
        used += len(text)
        if len(picked) >= k:
            break
    return picked


def render_profile_block(prof: Dict[str, Any]) -> List[str]:
    heads = "、".join("「%s」" % h for h, n in prof["top_heads"] if h and not h.startswith("$"))
    o = ["### 1.1　文体画像（由 438 段脱敏骨架统计，非模型判断）", ""]
    o.append("| 维度 | 实测 | 写作时的约束 |")
    o.append("|---|---|---|")
    o.append("| 句长 | 均 %.1f 字（P50 %s / P90 %s） | 短句为主；超过 P90 的句子拆开 |" % (
        prof["sentence_len_avg"], prof["sentence_len_p50"], prof["sentence_len_p90"]))
    o.append("| 段长 | 均 %.1f 字（P90 %s） | 一段一个意思，不写大段铺陈 |" % (
        prof["paragraph_len_avg"], prof["paragraph_len_p90"]))
    o.append("| 段落形态 | 段落 %d 段；表格 %d 个；公式化段落 %d 段 | 有算式的节直接用 `$$ … $$` 承载算式与代入 |" % (
        prof["paragraphs"], prof["tables"], prof["formula_blocks"]))
    o.append("| 值槽密度 | 平均每段 %.2f 个槽位（%d 段含 `{{node:}}`） | 数值一律走槽位引用，不写死 |" % (
        prof["slot_density"], prof["with_node_slots"]))
    o.append("| 常用段首 | %s | 复刻叙述起手，但不许堆套话 |" % (heads or "—"))
    o.append("| 人称/语气 | 第三人称、formal | 不用「我们」「大家」；不用「较为/基本上/原则上」 |")
    o.append("| 数字格式 | 千分位、两位小数、单位后置、万元优先、面积用 ㎡ | 与原文一致，不混用元/万元 |")
    o.append("| 表题/引语 | `表N-<标题>` | 表格前一句说明这张表看什么 |")
    o.append("")
    return o


def render_examples_block(struct_no: str, examples: List[Dict[str, Any]]) -> List[str]:
    if not examples:
        return ["**文体示例**：本节无可用骨架（写作时按 §1.1 文体画像执行，不得自创腔调）。", ""]
    o = ["**文体示例（few-shot，取自本报告同节脱敏骨架）**", "",
         "> 借形不借值：句式、叙述顺序、段落节奏照此复刻；`{{node:*}}`/`{{ent:*}}`/`{{time:*}}` "
         "必须换成本节节点值，示例里任何具体数字都不得照抄。", ""]
    for i, ex in enumerate(examples, 1):
        o.append("```text")
        o.append("例 %d（原文第 %s 块，%d 个值槽位）" % (i, ex["index"], ex["slots"]))
        o.append(ex["text"])
        o.append("```")
        o.append("")
    return o


def section_examples(idx: Dict[str, List[Dict[str, Any]]], struct_no: str,
                     k: int = 3) -> List[Dict[str, Any]]:
    blocks = idx.get(str(struct_no)) or []
    if not blocks:
        # 退化：取同章（父节号）的骨架
        parent = str(struct_no).rsplit(".", 1)[0]
        for key in sorted(idx):
            if key.rsplit(".", 1)[0] == parent:
                blocks = idx[key]
                if blocks:
                    break
    return pick_examples(blocks, k=k)
