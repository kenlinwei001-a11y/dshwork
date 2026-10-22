# -*- coding: utf-8 -*-
"""kp_toolkit.claim_classify —— fact / claim 确定性分类器（零 LLM）

判据来源：可证伪性。不是"看起来像判断"，而是"能不能被单一测量证伪"。

四步判定（顺序不可换）：
  ① 规范条文转述 → fact(E2)      含「应/不应/不应低于」+ 标准号
  ② 判断词分类   → claim        按词性分 conclusion/recommendation/hypothesis/inference
  ③ 有值无判断词 → fact
  ④ 都没有       → None（不是知识）

对外：
    classify(text, has_value=None)  -> {kind, claim_type, signals, falsifiable_by}
    explain(text)                   -> 人读的判定理由
"""
import re

# 判断词按 claim_type 分族（顺序即优先级）
RECOMMEND = ("建议", "宜采用", "宜设", "应优先", "推荐")
HYPOTHESIS = ("可能", "预计", "力争", "将达", "有望", "预估", "届时")
INFERENCE = ("由于", "导致", "从而", "因此", "由此", "进而", "致使")
CONCLUSION = ("充分", "合理", "必要", "可行", "良好", "有利", "显著", "可控", "不会",
              "能够", "确保", "有保障", "推动", "提升", "促进", "满足要求", "符合要求",
              "优于", "不足", "有待", "的需要", "不可或缺", "有保障")

# 规范条文转述标志（这些是「规范要求」不是「本项目判断」）
NORM_REQ = ("应", "不应", "不应低于", "不应小于", "不应大于", "必须", "不得")
NORM_REF = re.compile(r"(GB\s*/?\s*T?\s*\d{4,5}|JGJ\s*\d+|DGJ\s*[\dA-Z]+|建标\s*\d+)")

# 数值标志
VALUE_RE = re.compile(r"\d+(?:\.\d+)?\s*(㎡|m²|m³|米|m|层|度|年|月|日|万元|元|人|kW|kW·h|kWh|%|L/|W/)")


def _hit(text, words):
    return [w for w in words if w in text]


# 文本型事实值（不是数值，但同样是可核验的客观取值）
TEXT_VALUE = ("二级", "一级", "三级", "四级", "乙类", "甲类", "丙类", "丁类",
              "联锁", "分流", "合流", "框架", "剪力墙", "桩筏", "筏板",
              "类", "型", "级", "等", "层", "度")
# 方位/邻近关系（场地四至等，是可核验的空间事实）
DIRECTION = ("东侧", "西侧", "南侧", "北侧", "东面", "西面", "南面", "北面",
             "毗邻", "临近", "靠近", "紧邻", "位于", "地处")

def _text_value(t):
    """有「主体 + 是/为/= + 取值」结构，即使取值不是数字"""
    if re.search(r"(=|是|为|采用|按|取)\s*[\u4e00-\u9fa5A-Za-z0-9·（）\.]{1,20}$", t.strip()):
        return True
    if any(v in t for v in DIRECTION):
        return True
    return any(v in t for v in TEXT_VALUE) and len(t) < 80


def classify(text, has_value=None, has_triple=None):
    """判定一段文本是 fact 还是 claim，以及 claim 的子类型。

    text:       原文
    has_value:  是否已抽出结构化数值；None 表示自动检测
    返回 {kind, claim_type, signals, falsifiable_by, why}
    """
    t = str(text or "")
    if not t.strip():
        return {"kind": None, "why": "空文本"}

    # 数值型 或 文本型取值（含方位关系）都算「有值」；显式 False 不否定自动检测
    auto_val = bool(VALUE_RE.search(t)) or _text_value(t)
    if has_value is None:
        has_value = auto_val
    elif has_value is False and auto_val:
        has_value = True
    # ① 规范条文转述 → fact（不是本项目的判断，是标准要求）
    norm_req = _hit(t, NORM_REQ)
    norm_ref = NORM_REF.findall(t)
    if norm_req and (norm_ref or "规范" in t or "标准" in t):
        return {"kind": "fact", "claim_type": None,
                "signals": {"norm_req": norm_req[:3], "norm_ref": norm_ref[:2]},
                "falsifiable_by": "查该规范原文对应条款即可验证",
                "why": "规范条文转述：含「" + "/".join(norm_req[:2]) + "」且引标准，属标准要求非本项目判断"}

    # ①b 三元组完整 → fact（优先于判断词，因为参数句可能含「应」等字）
    if has_triple and not _hit(t, RECOMMEND + HYPOTHESIS + INFERENCE + CONCLUSION):
        return {"kind": "fact", "claim_type": None,
                "signals": {"has_triple": True},
                "falsifiable_by": "查图纸/报告/现场即可验证",
                "why": "主体-谓词-取值三元组完整且无强判断词 → 结构化事实"}

    # ② 判断词分类（先算各族命中数，避免「因此…良好」这类总结句被判 inference）
    cnt = {ct: len(_hit(t, w)) for w, ct in
           ((RECOMMEND, "recommendation"), (HYPOTHESIS, "hypothesis"),
            (INFERENCE, "inference"), (CONCLUSION, "conclusion"))}
    order = ["recommendation", "hypothesis", "inference", "conclusion"]
    # 结论词多于推理词 → 结论优先（「因此…具有良好效益」属结论）
    if cnt["conclusion"] > cnt["inference"] and cnt["conclusion"] > 0:
        order = ["recommendation", "hypothesis", "conclusion", "inference"]
    for ct in order:
        words = {"recommendation": RECOMMEND, "hypothesis": HYPOTHESIS,
                 "inference": INFERENCE, "conclusion": CONCLUSION}[ct]
        h = _hit(t, words)
        if h:
            fb = {
                "conclusion": "找到一条证据表明该判断不成立（如必要性不足的反证）",
                "recommendation": "找出更优方案或证明该建议不可行",
                "hypothesis": "实际结果与预测不符（如未达预期指标）",
                "inference": "证明前提成立但结论不成立，或存在其他原因",
            }[ct]
            return {"kind": "claim", "claim_type": ct,
                    "signals": {"judge_words": h[:4]},
                    "falsifiable_by": fb,
                    "why": "含判断词「" + "/".join(h[:3]) + "」→ " + ct}

    # ③ 有值无判断词 → fact
    if has_value:
        return {"kind": "fact", "claim_type": None,
                "signals": {"has_value": True, "has_triple": bool(has_triple)},
                "falsifiable_by": "查图纸/报告/现场即可验证",
                "why": ("主体-谓词-取值三元组完整 → 结构化事实" if has_triple
                        else "有具体取值且无判断词 → 可核验的客观事实")}

    # ④ 都没有
    return {"kind": None,
            "why": "既无数值也无可证伪的判断词，不构成知识节点（可能是章节标题或过渡语）"}


def explain(text):
    """人读判定理由"""
    r = classify(text)
    return (f"判定：{r['kind']}" + (f"（{r['claim_type']}）" if r.get("claim_type") else "")
            + "\n理由：" + r["why"]
            + ("\n可被推翻于：" + r["falsifiable_by"] if r.get("falsifiable_by") else ""))


def batch(nodes):
    """批量复判：返回 [{id, old_kind, new_kind, claim_type, why}]"""
    out = []
    for n in nodes:
        t = str(n.get("value") or n.get("subject") or "")
        old = n.get("kind") or ("claim" if str(n.get("id", "")).startswith("CL-") else "fact")
        r = classify(t, has_value=(old == "quantity"))
        out.append({"id": n.get("id"), "text": t[:80], "old_kind": old,
                    "new_kind": r["kind"], "claim_type": r.get("claim_type"),
                    "signals": r.get("signals"), "falsifiable_by": r.get("falsifiable_by"),
                    "why": r.get("why"), "changed": r["kind"] != old})
    return out
