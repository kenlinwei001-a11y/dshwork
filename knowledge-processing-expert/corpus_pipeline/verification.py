# -*- coding: utf-8 -*-
"""装配侧验证工具（空白 A 的三个 MCP 工具）。

  check_requirements   —— 需求完备性检查（A1：主动识别缺项，不编造）
  sensitivity_analysis —— 敏感性分析（A7：哪些变量变化导致结论显著变化/翻转）
  validate_shacl       —— SHACL 约束执行（A7：校验节点是否符合本体约束）
"""
from __future__ import annotations
import json
from pathlib import Path

from .domain_rules import FEASIBILITY_VARIABLES
from .ontology import CLAIM_TYPE_VALUES, CLAIM_STATUS_VALUES


# --------------------------------------------------------------------------- #
# A1 需求完备性检查
# --------------------------------------------------------------------------- #
def check_requirements(provided_facts: list[dict], required_variables=None, project_goal: str | None = None) -> dict:
    """需求完备性检查：对比「已提供事实」与「必需变量」，输出缺失清单（不编造）。

    复用 domain_rules.FEASIBILITY_VARIABLES（19 个输入变量）作为必需字段清单。
    返回 {complete, missing, provided, total_required}。
    """
    required_variables = required_variables or list(FEASIBILITY_VARIABLES.keys())
    provided_labels = {f.get("label") for f in (provided_facts or [])}
    missing = []
    if not project_goal:
        missing.append({"field": "project_goal", "reason": "缺少项目目标/交付物要求"})
    for v in required_variables:
        if v not in provided_labels:
            missing.append({"field": v, "reason": "缺必需输入变量"})
    return {"complete": not missing, "missing": missing,
            "provided": sorted(provided_labels), "total_required": len(required_variables)}


# --------------------------------------------------------------------------- #
# A7 敏感性分析
# --------------------------------------------------------------------------- #
def _read_computed(project_dir: str) -> dict:
    """读 project 图库里的 computed 派生节点值（label → value）。"""
    nodes = json.loads((Path(project_dir) / "graph" / "nodes.yaml").read_text(encoding="utf-8"))
    return {n["label"]: n["value"] for n in nodes if n.get("status") == "computed"}


def sensitivity_analysis(corpus_dir: str, provided_facts: list[dict], meta: dict | None = None,
                         delta_ratio: float = 0.1) -> dict:
    """敏感性分析：对每个输入变量做 ±delta_ratio 扰动，重算派生值，看哪些变量「敏感」。

    敏感 = 任一派生值的相对变化超过 delta_ratio（即该输入变量的微小变化显著影响结论）。

    返回 {delta_ratio, variables, sensitive_variables}。
    variables 每项：{label, base_value, delta, derived_changes, sensitive}。
    """
    import tempfile
    from .instantiate import instantiate_project

    with tempfile.TemporaryDirectory() as tmp:
        base = instantiate_project(corpus_dir, str(Path(tmp) / "base"), provided_facts, meta)
        base_derived = _read_computed(base["project_dir"])

    result = []
    for f in provided_facts:
        base_val = f.get("value")
        if not isinstance(base_val, (int, float)) or base_val == 0:
            continue
        delta = abs(base_val) * delta_ratio
        changes: dict = {}
        for direction, dv in (("up", delta), ("down", -delta)):
            perturbed = [dict(x) for x in provided_facts]
            for p in perturbed:
                if p.get("label") == f["label"]:
                    p["value"] = base_val + dv
            with tempfile.TemporaryDirectory() as tmp:
                r = instantiate_project(corpus_dir, str(Path(tmp) / "pert"), perturbed, meta)
                derived = _read_computed(r["project_dir"])
            for k, v in derived.items():
                bv = base_derived.get(k)
                if bv and isinstance(bv, (int, float)) and bv != 0:
                    changes.setdefault(k, {})[direction] = round((v - bv) / bv, 4)

        sensitive = any(abs(c.get("up", 0)) > delta_ratio or abs(c.get("down", 0)) > delta_ratio
                        for c in changes.values())
        result.append({"label": f["label"], "base_value": base_val, "delta": round(delta, 4),
                       "derived_changes": changes, "sensitive": sensitive})

    return {"delta_ratio": delta_ratio, "variables": result,
            "sensitive_variables": [v["label"] for v in result if v["sensitive"]]}


# --------------------------------------------------------------------------- #
# A7 SHACL 约束执行
# --------------------------------------------------------------------------- #
def validate_shacl(nodes: list[dict], shapes=None) -> dict:
    """执行 SHACL 约束校验：检查节点是否符合约束（枚举 / 必填 / 类型）。

    默认校验 Claim 节点（claim_type/status 枚举 + text 必填），与 ontology_schema 的
    ClaimShape 约束一致。返回 {valid, violations, checked}。
    """
    shapes = shapes or [{
        "targetClass": "Claim",
        "constraints": [
            {"property": "claim_type", "in": list(CLAIM_TYPE_VALUES)},
            {"property": "status", "in": list(CLAIM_STATUS_VALUES)},
            {"property": "text", "minCount": 1},
        ],
    }]
    violations = []
    for node in nodes or []:
        for shape in shapes:
            for c in shape.get("constraints", []):
                prop = c["property"]
                val = node.get(prop)
                if "minCount" in c and c["minCount"] >= 1:
                    if val in (None, ""):
                        violations.append({"node": node.get("id"), "property": prop,
                                           "constraint": f"minCount>={c['minCount']}", "found": val})
                if "in" in c and val is not None and val != "":
                    if val not in c["in"]:
                        violations.append({"node": node.get("id"), "property": prop,
                                           "constraint": f"in {c['in']}", "found": val})
    return {"valid": not violations, "violations": violations, "checked": len(nodes or [])}
