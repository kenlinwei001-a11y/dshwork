# -*- coding: utf-8 -*-
"""知识处理侧 P2：知识 ≠ 能力（K8 双路径）。

对齐文档的关键洞察：「只有报告 → 只能归纳候选方法；有代码/配置/执行记录 → 才能登记真实能力」。
函数库、Skill、DAG 不能从历史报告文本可靠「抽取」出来。

本模块区分资产来源：
  induced    —— 从历史资料归纳的知识结构（候选/待验证，不能当可执行能力发布）
  registered —— 从代码/配置/执行记录登记的真实能力制品（可发布为可执行能力）
"""
from __future__ import annotations

ASSET_ORIGIN = ("induced", "registered")

# 可执行证据：资产带这些字段之一，才视为「登记的能力」（而非仅归纳的方法）
_EXECUTABLE_HINTS = ("formula", "expr", "code", "function", "implementation",
                     "executable", "binding", "test", "interface")


def classify_origin(asset: dict) -> str:
    """判断单个资产是「归纳的知识结构」还是「登记的真实能力」。

    规则：带可执行证据（formula/expr/code/function/...）→ registered；
    只有描述/模式/示例 → induced（候选方法，非能力）。
    """
    if not isinstance(asset, dict):
        return "induced"
    if any(k in asset for k in _EXECUTABLE_HINTS):
        return "registered"
    return "induced"


def assess_capability(domains: list[dict]) -> dict:
    """对 16 域评估：哪些是「归纳的候选方法」，哪些是「登记的真实能力」。

    返回 {domain_id: {origin, actionable, note}}。
    actionable=False 表示只有归纳、无代码登记，不能当可执行能力发布。
    """
    out = {}
    for dm in domains or []:
        origin = classify_origin(dm)
        out[dm.get("id", "?")] = {
            "origin": origin,
            "actionable": origin == "registered",
            "note": "真实能力（可执行）" if origin == "registered" else "候选方法（仅归纳，未经代码登记，不可当生产级能力发布）",
        }
    return out


def capability_summary(assess: dict) -> dict:
    """能力评估汇总：登记能力数 vs 候选方法数。"""
    registered = [k for k, v in assess.items() if v["origin"] == "registered"]
    induced = [k for k, v in assess.items() if v["origin"] == "induced"]
    return {
        "registered_capabilities": registered,
        "induced_candidates": induced,
        "registered_count": len(registered),
        "induced_count": len(induced),
        "actionable": not induced,   # 无候选缺口时全部可执行
    }
