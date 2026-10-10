# -*- coding: utf-8 -*-
"""知识处理侧 P1：资产依赖图（DependencyGraph）+ 影响传播。

对齐文档「资产依赖可计算」：系统必须知道一个 Skill 依赖哪些 Schema/函数/规则/MCP 工具，
才能在装配侧做可靠的影响分析——取代「按 16 域静态拍脑袋」，改为「沿依赖图精确传播」。

依赖图（哪个资产域依赖哪些上游域）：
  本体(ontology) 是根；论证链/变量/规则/实体关系/报告结构依赖本体；
  函数依赖变量；Skill 依赖本体+规则+函数；任务DAG 依赖 Skill+函数；
  提示词依赖 Skill+报告结构；质量闸门依赖本体+规则+论证链；复用策略依赖质量闸门。
"""
from __future__ import annotations
from collections import deque

# 16 个资产域的依赖关系（key 依赖 values）
ASSET_DEPENDENCIES = {
    "ontology": [],
    "entity_relation": ["ontology"],
    "variable": ["ontology"],
    "rule": ["ontology", "variable"],
    "invariant": ["ontology", "variable"],
    "argument_chain": ["ontology"],
    "scenario": ["ontology", "variable", "rule"],
    "function": ["variable"],
    "skill": ["ontology", "rule", "function"],
    "task_dag": ["ontology", "rule", "skill", "function"],
    "report_structure": ["ontology"],
    "report_form": ["ontology", "report_structure"],
    "prompt": ["skill", "report_structure"],
    "quality_gate": ["ontology", "rule", "argument_chain"],
    "reuse_strategy": ["ontology", "quality_gate"],
    "cost_risk": ["variable", "function", "rule"],
}

# 反向索引：资产 → 依赖它的下游资产（dependents）
_DEPENDENTS = {a: [] for a in ASSET_DEPENDENCIES}
for _asset, _ups in ASSET_DEPENDENCIES.items():
    for _up in _ups:
        _DEPENDENTS.setdefault(_up, []).append(_asset)


def dependents_of(asset: str) -> list[str]:
    """谁依赖这个资产（直接下游）。"""
    return list(_DEPENDENTS.get(asset, []))


def impacted_assets(changed_asset: str) -> list[str]:
    """给定「变更的资产」，沿依赖图正向传播，返回所有受影响的下游资产（含变更资产自身）。

    例如 ontology 新增 Claim → 传播到 entity_relation/variable/rule/argument_chain/...
    → 再传播到依赖它们的 skill/task_dag/quality_gate/...。
    """
    impacted = set()
    queue = deque([changed_asset])
    while queue:
        a = queue.popleft()
        if a in impacted:
            continue
        impacted.add(a)
        for downstream in dependents_of(a):
            if downstream not in impacted:
                queue.append(downstream)
    return sorted(impacted)


def dependency_closure(asset: str) -> list[str]:
    """给定资产，返回它（及它的上游依赖）的传递闭包（依赖了谁）。"""
    seen = set()
    queue = deque([asset])
    while queue:
        a = queue.popleft()
        if a in seen:
            continue
        seen.add(a)
        for up in ASSET_DEPENDENCIES.get(a, []):
            if up not in seen:
                queue.append(up)
    return sorted(seen)


def check_cycles() -> list[list[str]]:
    """检测依赖图是否有环（拓扑排序），返回环（若有）。"""
    from .orchestrator import topological_order
    tasks = [{"id": a, "deps": ASSET_DEPENDENCIES.get(a, [])} for a in ASSET_DEPENDENCIES]
    r = topological_order(tasks)
    if r["ok"]:
        return []
    return r.get("cycle", [])
