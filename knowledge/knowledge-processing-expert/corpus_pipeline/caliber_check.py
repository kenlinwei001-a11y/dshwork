# -*- coding: utf-8 -*-
"""caliber_check —— 口径冲突判定（借鉴 EvoOntology 的 Mapping 思想）。

## 解决什么问题

两个数不等，可能是：
  A. 真冲突（同一口径下算错了）
  B. **口径差异**（两个值来自不同口径，都"对"）

没有口径信息时，只能一律标"冲突待审"——这正是之前的做法。
有了 mapping.calibers / default / semantic_filter，就能判 B 类。

## **重要：这是「疑似」判定，不是「已确认」**

`KNOWN_DELIBERATE` 里的方向与口径对是**领域常识推测**，不是客户确认过的。
所以 `caliber_difference` 的置信度一律标「推测，待客户确认」，
正文必须同时写出两侧口径与数值，**不得据此认定某个值正确**。

## 判据（确定性，零 LLM）

1. 该事实位有 mapping 且 canonical=True
2. 两个值的来源口径标签不同（provided_caliber vs recomputed_caliber）
3. 差异方向与该事实位的 known_deliberate_deltas 匹配（若登记过）
   → 判「口径差异」；否则判「真冲突」

## 用法

    from corpus_pipeline.caliber_check import classify_conflict
    r = classify_conflict("建筑安装工程费用", 9860, 10180, fact_source_map)
    # {'kind': 'caliber_difference' | 'true_conflict', 'reason': '...'}
"""
from __future__ import annotations

# 已知的「刻意差异」——同一事实位在不同口径下的合法差值方向与量级
# 这些不是 bug，是口径设计使然
# delta_sign 指 recomputed - provided 的符号。
# 同一事实位两个方向都可能出现（客户口径可能是"宽"的也可能是"窄"的），所以两侧都登记。
KNOWN_DELIBERATE = {
    "建筑安装工程费用": [
        {"delta_sign": "-", "about": "规则值低于客户值 → 客户口径更宽（含装饰/含税）",
         "caliber_pair": ("客户=含装饰或含税", "规则=不含装饰不含税")},
        {"delta_sign": "+", "about": "规则值高于客户值 → 规则口径更宽（含装饰增量）",
         "caliber_pair": ("客户=不含装饰", "规则=含装饰装修")},
    ],
    "总投资": [
        {"delta_sign": "-", "about": "规则值低于客户值 → 客户含暂列金/建设期利息",
         "caliber_pair": ("客户=含暂列金", "规则=不含暂列金")},
        {"delta_sign": "+", "about": "规则值高于客户值 → 规则含客户漏项",
         "caliber_pair": ("客户=不含漏项", "规则=全含")},
    ],
    "总建筑面积": [
        {"delta_sign": "-", "about": "规则值低于客户值 → 客户含人防/架空层",
         "caliber_pair": ("客户=含人防", "规则=不含人防")},
        {"delta_sign": "+", "about": "规则值高于客户值 → 规则含地下/客户只报地上",
         "caliber_pair": ("客户=仅地上", "规则=含地下")},
    ],
    "土建工程": [
        {"delta_sign": "-", "about": "规则值低于客户值 → 客户含装饰/外立面/装配式增量",
         "caliber_pair": ("客户=含装饰", "规则=不含装饰")},
        {"delta_sign": "+", "about": "规则值高于客户值 → 规则含装饰装修/外立面/装配式增量",
         "caliber_pair": ("客户=不含装饰装修", "规则=含装饰装修")},
    ],
    "安装工程": [
        {"delta_sign": "-", "about": "规则值低于客户值 → 客户含主设备购置",
         "caliber_pair": ("客户=含设备购置", "规则=不含设备购置")},
        {"delta_sign": "+", "about": "规则值高于客户值 → 规则含设备购置",
         "caliber_pair": ("客户=不含设备购置", "规则=含设备购置")},
    ],
    "年总用水量": [
        {"delta_sign": "-", "about": "规则值低于客户值 → 客户含绿化/未预见系数/其他用水",
         "caliber_pair": ("客户=含绿化或未预见", "规则=不含")},
        {"delta_sign": "+", "about": "规则值高于客户值 → 规则含客户漏计的项",
         "caliber_pair": ("客户=漏项", "规则=全含")},
    ],
    "年总耗电量": [
        {"delta_sign": "-", "about": "规则值低于客户值 → 客户含动力/特殊负荷",
         "caliber_pair": ("客户=含动力", "规则=不含动力")},
        {"delta_sign": "+", "about": "规则值高于客户值 → 规则含空调动力，客户只报照明",
         "caliber_pair": ("客户=仅照明", "规则=含空调动力")},
    ],
    "工程建设其他费用": [
        {"delta_sign": "-", "about": "规则值低于客户值 → 客户含土地费/报建费",
         "caliber_pair": ("客户=含土地费", "规则=不含土地费")},
        {"delta_sign": "+", "about": "规则值高于客户值 → 规则含客户漏项",
         "caliber_pair": ("客户=漏项", "规则=全含")},
    ],
    "公共服务配套用房建筑面积": [
        {"delta_sign": "-", "about": "规则值低于客户值 → 客户直接采用建筑面积，规则按使用面积换算",
         "caliber_pair": ("客户=直接给定建筑面积", "规则=使用面积÷系数")},
        {"delta_sign": "+", "about": "规则值高于客户值 → 规则按换算，客户报的是使用面积",
         "caliber_pair": ("客户=使用面积", "规则=换算后建筑面积")},
    ],
}


def _mapping_of(subject: str, fsm: dict) -> dict | None:
    if not isinstance(fsm, dict):
        return None
    for f in (fsm.get("facts") or []):
        if f.get("fact") == subject:
            m = f.get("mapping") or {}
            return m if m.get("canonical") else None
    return None


def classify_conflict(subject: str, provided, recomputed, fsm: dict,
                      provided_caliber: str | None = None,
                      recomputed_caliber: str | None = None) -> dict:
    """判定两个数的差异是「口径差异」还是「真冲突」。"""
    m = _mapping_of(subject, fsm)
    try:
        p = float(provided); r = float(recomputed)
    except (TypeError, ValueError):
        return {"kind": "unclassified", "reason": "非数值，无法比较", "mapping": m}
    delta = round(r - p, 4)

    if not m:
        return {"kind": "true_conflict", "confidence": "**确定是冲突**",
                "reason": "该事实位无口径锚定，无法用口径解释",
                "delta": delta, "mapping": None,
                "action": "登记待审，请客户说明数据来源"}

    # 有口径锚定：看差值方向是否与「已知刻意差异」匹配
    rule = (KNOWN_DELIBERATE.get(subject) or [])
    sign = "+" if delta > 0 else ("-" if delta < 0 else "0")
    for d in rule:
        if d["delta_sign"] == sign:
            pc, rc = d["caliber_pair"]
            return {"kind": "caliber_difference",
                    "confidence": "**推测，待客户确认**",
                    "delta": delta,
                    "reason": "%s（%s vs %s）" % (d["about"], pc, rc),
                    "suggested_calibers": {"provided": pc, "recomputed": rc},
                    "mapping": m,
                    "action": "登记为**疑似口径差异**；正文须同时写出两侧口径与数值，"
                              "并标注「口径待客户确认」；**不得据此认定某个值正确**"}
    return {"kind": "true_conflict", "confidence": "**待确认口径**", "delta": delta,
            "reason": "有口径锚定，但差值方向不在已知刻意差异清单内",
            "available_calibers": m.get("calibers"), "mapping": m,
            "action": "登记待审：可能是未登记的口径差异，也可能是真算错；请客户确认"}
