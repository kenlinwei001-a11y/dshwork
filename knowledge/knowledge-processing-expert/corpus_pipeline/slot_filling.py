# -*- coding: utf-8 -*-
"""slot_filling —— 填槽模式：把「缺失依赖」变成「用户可填的槽位」。

## 为什么需要

语料包的规则 deps 里写的是**上财的组织名**：

    R-科研人员规划人数合计
      deps: [管理科学与量化信息研究中心·规划科研人员,
             理论计算机研究中心·规划科研人员, ...]

新项目（华东理工）的组织名完全不同。三种做法：

  ✗ 让客户迁就上财名         —— 客户不知道那些名字是什么
  ✗ 改语料包 rules.yaml 的 deps —— 动已发布资产，破坏版本完整性
  ✓ **填槽**：槽位按「位置」对应，用户填「这个槽在新项目叫什么 + 值多少」
              系统仍用**语料包原名**去计算，新名字只作展示

## 槽位 = 位置的占位，不是名字

    槽 S1  ← 语料包第 1 个加数：管理科学与量化信息研究中心·规划科研人员
            用户填：人工智能基础理论研究中心 / 85 人
            系统用：{管理科学与量化信息研究中心·规划科研人员} = 85

    → 规则不用改，客户用自己的名字填，系统按槽位对应

## 用法

    from corpus_pipeline.slot_filling import build_slots, apply_slots, slots_to_table

    # ① 从 instantiate 的 undefined 生成槽位
    slots = build_slots(undefined_notes, rules)

    # ② 导出成表格给人填（列：槽位/语料包原名/语料包原值/新项目名/新项目值/单位）
    table = slots_to_table(slots)

    # ③ 用户填完后回读，生成 provided_facts（label 用**语料包原名**）
    pf = apply_slots(slots, filled)     # filled = [{slot_id, project_label, project_value, unit}]
"""
from __future__ import annotations
import re
from typing import Iterable


# 伪依赖：不是真事实，是 instantiate 内部的占位串
_PSEUDO = ("输出未提供且无计算规格", "未提供", "N/A", "n/a")


def classify_slot(corpus_label: str, source_type: str | None, standard_basis: str | None = None) -> str:
    """槽位分类，决定谁来填。

    FILLABLE    用户填（组织名、项目专属值、客户真缺的）
    RETRIEVABLE 从标准库/web 取，不让用户填（人均指标、负荷密度、折标系数…）
    UPSTREAM    等上游规则算完自动有（研究生数由 4 个分中心加总）
    PSEUDO      伪依赖，丢弃
    """
    lab = str(corpus_label or "")
    if any(x in lab for x in _PSEUDO):
        return "PSEUDO"
    st = str(source_type or "").upper()
    # 「行业惯例」不是标准：每家的预备费率不同，必须问客户
    basis = str(standard_basis or "")
    if "惯例" in lab or "经验" in lab or "惯例" in basis or "经验值" in basis:
        return "FILLABLE"
    if st in ("RETRIEVABLE", "STANDARD"):
        return "RETRIEVABLE"
    # CUSTOMER_PRIMARY = 可直给也可算 → 等上游算（客户若已给，会进 provided 不算缺）
    if st in ("DERIVED", "COMPUTED", "CUSTOMER_PRIMARY"):
        return "UPSTREAM"
    return "FILLABLE"


def _slot_id(rule: str, pos: int) -> str:
    return "%s::S%d" % (rule, pos)


def build_slots(undefined_notes: Iterable[dict], rules: Iterable[dict] | None = None,
                source_map: dict | None = None) -> list[dict]:
    """把 instantiate 的 undefined_notes 展开成槽位列表。

    每个 missing 依赖 = 一个槽位；顺序与规则的 deps / expr 中出现的顺序一致。
    """
    rule_map = {str(r.get("id")): r for r in (rules or [])}
    slots: list[dict] = []
    for u in undefined_notes or []:
        rule = str(u.get("rule") or "")
        target = str(u.get("target_label") or "")
        missing = list(u.get("missing") or [])
        r = rule_map.get(rule) or {}
        deps = [str(d) for d in (r.get("deps") or [])]
        expr = str(r.get("expr") or "")
        for i, dep in enumerate(missing, start=1):
            # 位置：优先按 deps 顺序，退化按 expr 里 {name} 出现顺序
            pos = deps.index(dep) + 1 if dep in deps else i
            sm = (source_map or {}).get(dep)
            sm_type = sm.get("source_type") if isinstance(sm, dict) else sm
            sm_basis = sm.get("standard_basis") if isinstance(sm, dict) else None
            stype = classify_slot(dep, sm_type, sm_basis)
            if stype == "PSEUDO":
                continue
            slots.append({
                "slot_id": _slot_id(rule, pos),
                "slot_type": stype,
                "rule": rule,
                "target": target,
                "position": pos,
                "role": "加数" if "+" in expr else "输入",
                "corpus_label": dep,          # ← 系统计算时用这个
                "project_label": "",          # ← 用户填新名字（只作展示）
                "project_value": None,        # ← 用户填值
                "unit": "",
                "instruction": u.get("instruction") or "",
            })
    return slots


def slots_to_table(slots: list[dict]) -> list[dict]:
    """按 slot_type 排序：FILLABLE 在最前（用户只需填这些）。"""
    order = {"FILLABLE": 0, "RETRIEVABLE": 1, "UPSTREAM": 2}
    slots = sorted(slots, key=lambda s: (order.get(s.get("slot_type"), 9), s["slot_id"]))
    """转成人可填的表格行（给 content_open(kind:spreadsheet) 用）。"""
    out = []
    for s in slots:
        out.append({
            "槽位": s["slot_id"],
            "类型": s.get("slot_type", ""),
            "规则": s["rule"],
            "目标": s["target"],
            "语料包原名（勿改）": s["corpus_label"],
            "含义": s["instruction"][:60],
            "新项目名（可改）": s.get("project_label") or "",
            "值": s.get("project_value") if s.get("project_value") is not None else "",
            "单位": s.get("unit") or "",
        })
    return out


def apply_slots(slots: list[dict], filled: Iterable[dict]) -> list[dict]:
    """回填值，产出 provided_facts。

    **关键**：产出的 label 一律用 `corpus_label`（语料包原名），
    这样规则的 expr 占位能直接匹配；`project_label` 只写进 note 作溯源。
    """
    by_id = {str(f.get("slot_id")): f for f in (filled or [])}
    facts: list[dict] = []
    for s in slots:
        f = by_id.get(s["slot_id"])
        if not f:
            continue
        v = f.get("project_value", f.get("值"))
        if v in (None, ""):
            continue
        facts.append({
            "label": s["corpus_label"],           # ← 用原名，规则才认
            "value": v,
            "unit": f.get("unit") or s.get("unit") or "",
            "caliber": "填槽补充",
            "as_of": f.get("as_of") or "",
            "kind": "provided",
            "slot_id": s["slot_id"],
            "project_label": f.get("project_label") or "",   # 溯源用
            "from_rule": s["rule"],
        })
    return facts


def merge_with_provided(base: list[dict], slot_facts: list[dict]) -> list[dict]:
    """把填槽得到的事实并进已有 provided_facts；同 label 以填槽值为准（并记 note）。"""
    idx = {str(f.get("label")): i for i, f in enumerate(base)}
    out = list(base)
    for f in slot_facts:
        lab = str(f["label"])
        if lab in idx:
            old = out[idx[lab]]
            out[idx[lab]] = {**old, **f,
                             "note": "填槽覆盖：原 %s %s → 新 %s（来源 %s）" % (
                                 old.get("value"), old.get("unit") or "",
                                 f.get("value"), f.get("project_label") or "槽位补充")}
        else:
            out.append(f)
    return out

def hard_constraints(slots: list[dict], source_map: dict | None = None) -> list[dict]:
    """从槽位里挑出**硬约束且用户必须给**的项，生成「请客户提供」清单。

    原则（按用户要求）：
      · 硬约束缺值 → **明确提示用户输入**，不猜、不借、不用行业惯例填
      · 可检索项（RETRIEVABLE）→ 不进本清单，系统自己取
      · 上游可算的（UPSTREAM）→ 不进本清单，等上游算完自动有
      · 组织名类槽位（FILLABLE + 含「·」的复合名）→ 进本清单，但要用户给「新名 + 值」

    返回每一行都是「必须问人」的，正文据此写「待客户提供 X」。
    """
    out: list[dict] = []
    for s in slots:
        if s.get("slot_type") != "FILLABLE":
            continue
        lab = str(s.get("corpus_label") or "")
        compound = "·" in lab          # 组织名这类复合槽位
        out.append({
            "slot_id": s["slot_id"],
            "rule": s.get("rule"),
            "target": s.get("target"),
            "需要客户提供": lab,
            "是否为组织名槽位": compound,
            "建议问法": (
                "贵单位「%s」对应的实际部门叫什么？编制人数是多少？" % lab.split("·")[-1]
                if compound else
                "本项目「%s」的取值是多少？" % lab
            ),
            "缺了会阻塞": s.get("target"),
            "禁止": "不得用行业惯例/同类项目值代替；不得填 0；不得省略该分项",
        })
    return out


def render_ask_list(hard: list[dict]) -> str:
    """把硬约束清单渲染成给用户看的 Markdown（可直接贴进对话或表单）。"""
    if not hard:
        return "无硬约束缺失。"
    lines = ["以下 %d 项为**硬约束**，客户未提供或无法从标准检索，请补：" % len(hard), ""]
    lines.append("| # | 需要客户提供 | 建议问法 | 缺了会阻塞 |")
    lines.append("|---|---|---|---|")
    for i, h in enumerate(hard, start=1):
        lines.append("| %d | %s | %s | %s |" % (i, h["需要客户提供"], h["建议问法"], h["缺了会阻塞"]))
    lines += ["", "**纪律**：不得用行业惯例、同类项目值、0 值代替；缺就是缺，正文写「待客户提供 X」后测算。"]
    return "\n".join(lines)
