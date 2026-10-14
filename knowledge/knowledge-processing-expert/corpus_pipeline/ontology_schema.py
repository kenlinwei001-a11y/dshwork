# -*- coding: utf-8 -*-
"""本体管理接入点 —— 对齐 Semantica 的 OWL / SHACL / SKOS 概念。

把 corpus_pipeline 的本体（概念字典 + 十类关系 + 约束 + Claim 模型）导出为
OWL(类/属性) + SHACL(约束) + SKOS(受控词表) 对齐的本体 Schema，可导入回概念字典；
并提供 bootstrap_claim_ontology 作为「自动扩展本体」的执行层（P1），
默认确定性规则诱导 Claim 本体草稿；semantica_client 已接入 Semantica MCP
（见 semantica_client.py）：默认自动连接（KP_SEMANTICA_AUTO=0 可关闭），
spawn/握手失败一律降级确定性规则，不硬编码、可插拔（与 Jev/Ossie 一致）。
"""
from __future__ import annotations

from .spec import TEN_RELATIONS
from .semantic_model import build_concepts
from .ontology import CLAIM_TYPE_VALUES, CLAIM_STATUS_VALUES, CLAIM_INPUT_FIELDS, CLAIM_DERIVED_FIELDS


def _auto_semantica_client():
    """懒连接已部署的 Semantica MCP；失败返回 None（调用方降级确定性规则）。"""
    import os
    if os.environ.get("KP_SEMANTICA_AUTO", "1") == "0":
        return None
    try:
        from .semantica_client import get_semantica_client
        return get_semantica_client()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 本体 Schema 导出 / 导入（对齐 OWL / SHACL / SKOS）
# --------------------------------------------------------------------------- #
def export_ontology_schema(concepts: dict | None = None, relations=None, semantica_source: str = "local") -> dict:
    """把概念字典 + 关系 + 约束导出为 OWL/SHACL/SKOS 对齐的本体 Schema。

    返回 {classes, properties, constraints, vocabulary}：
      classes     —— OWL 类（实体类型 + metric/attribute 概念类型 + Claim）
      properties  —— OWL 对象属性（十类关系）+ 数据属性（unit/formula）
      constraints —— SHACL 约束（Claim 的 claim_type/status 枚举等）
      vocabulary  —— SKOS 受控词表（概念 prefLabel + aliases）

    semantica_source：
      "local"（默认）—— 仅本地导出；
      "semantica"      —— 从已部署的 Semantica MCP 导出其知识图谱（export_graph + 摘要）；
      "both"           —— 本地导出 + semantica 图快照（键 semantica）。
    任一模式下 Semantica 不可用都不报错，只附 available=false。
    """
    if semantica_source in ("semantica", "both"):
        semantica = {"available": False}
        try:
            client = _auto_semantica_client()
            if client is not None:
                semantica = {
                    "available": True,
                    "summary": client.get_graph_summary(),
                    "graph": client.export_graph("json-ld"),
                }
        except Exception as cause:
            semantica = {"available": False, "error": str(cause)}
        if semantica_source == "semantica":
            return semantica

    concepts = concepts if concepts is not None else build_concepts()
    relations = relations or list(TEN_RELATIONS)

    # OWL 类
    classes = [
        {"name": "Entity", "type": "owl:Class"},
        {"name": "Claim", "type": "owl:Class", "description": "论证对象（独立论证单元，非普通文本字段）"},
        {"name": "Metric", "type": "owl:Class", "subClassOf": "Entity", "description": "计算指标"},
        {"name": "Attribute", "type": "owl:Class", "subClassOf": "Entity", "description": "输入变量"},
    ]

    # OWL 对象属性（十类关系）
    properties = [{"name": r, "type": "owl:ObjectProperty"} for r in relations]
    # OWL 数据属性（概念的单位/公式）
    properties += [
        {"name": "unit", "type": "owl:DatatypeProperty"},
        {"name": "formula", "type": "owl:DatatypeProperty"},
        {"name": "claim_type", "type": "owl:DatatypeProperty", "range": list(CLAIM_TYPE_VALUES)},
        {"name": "status", "type": "owl:DatatypeProperty", "range": list(CLAIM_STATUS_VALUES)},
        {"name": "has_evidence", "type": "owl:ObjectProperty", "range": "Evidence"},
        {"name": "has_premise", "type": "owl:ObjectProperty", "range": "Claim"},
    ]

    # SHACL 约束
    constraints = [
        {"shape": "ClaimShape", "targetClass": "Claim",
         "constraints": [
             {"property": "claim_type", "in": list(CLAIM_TYPE_VALUES), "minCount": 1},
             {"property": "status", "in": list(CLAIM_STATUS_VALUES), "minCount": 1},
         ]},
    ]

    # SKOS 受控词表（概念 + prefLabel + altLabels）
    vocabulary = [
        {"concept": name, "prefLabel": name, "altLabels": c.get("aliases", []), "kind": c.get("kind", "")}
        for name, c in concepts.items()
    ]

    result = {"classes": classes, "properties": properties, "constraints": constraints, "vocabulary": vocabulary}
    if semantica_source == "both":
        result = {**result, "semantica": semantica}
    return result


def import_ontology_schema(schema: dict, merge_into: dict | None = None) -> dict:
    """从本体 Schema 导入概念字典（SKOS 词表 → 概念，prefLabel→canonical、altLabels→aliases）。

    本地概念优先（merge_into 不覆盖）。返回概念字典（向后兼容：直接返回 dict）。
    """
    concepts = dict(merge_into) if merge_into else {}
    for v in schema.get("vocabulary", []):
        name = v.get("prefLabel") or v.get("concept")
        if not name or name in concepts:
            continue
        concepts[name] = {
            "id": name,
            "canonical_name": name,
            "aliases": v.get("altLabels", []),
            "kind": v.get("kind", "attribute"),
            "unit": "",
            "formula": None,
            "deps": [],
            "description": "",
        }
    return concepts


def push_ontology_to_semantica(schema: dict) -> dict:
    """把本体 Schema 的类/对象属性/词表同步进已部署的 Semantica 知识图谱。

    返回 {available, entities_added, relationships_added, errors}；
    Semantica 不可用只记 summary，不抛异常（本地导入不受影响）。
    """
    push = {"available": False, "entities_added": 0, "relationships_added": 0, "errors": []}
    try:
        client = _auto_semantica_client()
        if client is None:
            return push
        push["available"] = True
        for c in schema.get("classes", []):
            if not isinstance(c, dict) or not c.get("name"):
                continue
            client.add_entity(c["name"], c.get("description") or c["name"],
                              "Class" if c.get("type") == "owl:Class" else "Concept")
            push["entities_added"] += 1
        for v in schema.get("vocabulary", []):
            vname = (v.get("prefLabel") or v.get("concept") or "").strip()
            if not vname:
                continue
            client.add_entity(vname, vname, "Concept", {"aliases": v.get("altLabels", [])})
            push["entities_added"] += 1
        for p in schema.get("properties", []):
            if not isinstance(p, dict) or p.get("type") != "owl:ObjectProperty" or not p.get("name"):
                continue
            client.add_entity(p["name"], p["name"], "Property")
            push["entities_added"] += 1
            if p.get("range"):
                client.add_relationship(p["name"], p["range"], "HAS_RANGE")
                push["relationships_added"] += 1
    except Exception as cause:
        push["errors"].append(str(cause))
    return push


# --------------------------------------------------------------------------- #
# 自动扩展本体（P1 执行层）：bootstrap_claim_ontology
# --------------------------------------------------------------------------- #
def bootstrap_claim_ontology(diffs: list[dict], semantica_client=None) -> dict:
    """从 Schema Diff 的「新增 Claim」诱导 Claim 本体草稿（P1 执行层）。

    默认确定性规则：检测到 Claim 新增时，在本体里新增 Claim 类 + 属性 + 约束 + 词表。
    预留 semantica_client：未来接入 Semantica 的 bootstrap_schema（从数据诱导本体草稿），
    本函数不硬编码、可插拔（与 Jev/Ossie 一致）。

    返回 {bootstrapped, ontology, source}。
    """
    from .schema_diff import _detect_claim_addition
    if not _detect_claim_addition(diffs):
        return {"bootstrapped": False, "reason": "无 Claim 新增，不扩展本体"}

    if semantica_client is not None:
        # 已接入：交给 Semantica 的 bootstrap_schema 从数据诱导本体草稿；
        # 调用失败（Semantica 不可用/异常）时降级确定性规则，不阻塞主链路。
        try:
            return semantica_client.bootstrap_schema(diffs)
        except Exception:
            pass
    elif (auto := _auto_semantica_client()) is not None:
        try:
            return auto.bootstrap_schema(diffs)
        except Exception:
            pass

    # 确定性规则：Claim 类的本体草稿（类 + 属性 + 约束 + 词表）
    ontology = {
        "classes": [
            {"name": "Claim", "type": "owl:Class", "description": "论证对象"},
            {"name": "Evidence", "type": "owl:Class", "description": "证据"},
        ],
        "properties": [
            {"name": "claim_type", "type": "owl:DatatypeProperty", "range": list(CLAIM_TYPE_VALUES)},
            {"name": "status", "type": "owl:DatatypeProperty", "range": list(CLAIM_STATUS_VALUES)},
            {"name": "has_evidence", "type": "owl:ObjectProperty", "range": "Evidence"},
            {"name": "has_premise", "type": "owl:ObjectProperty", "range": "Claim"},
            {"name": "derived_from", "type": "owl:ObjectProperty", "range": "Claim"},
        ],
        "constraints": [
            {"shape": "ClaimShape", "targetClass": "Claim",
             "constraints": [
                 {"property": "claim_type", "in": list(CLAIM_TYPE_VALUES)},
                 {"property": "status", "in": list(CLAIM_STATUS_VALUES)},
                 {"property": "text", "minCount": 1},
             ]},
        ],
        "vocabulary": [
            {"concept": "Claim", "prefLabel": "论断", "altLabels": ["声明", "主张", "论点"]},
        ],
    }
    return {"bootstrapped": True, "ontology": ontology, "source": "deterministic"}


# --------------------------------------------------------------------------- #
# 16 域自动装配变更集（P1 执行层）：assemble_domain_changes
# --------------------------------------------------------------------------- #
def assemble_domain_changes(diffs: list[dict], semantica_client=None) -> dict:
    """对 Schema Diff 差异，为每个受影响资产域生成具体变更集（覆盖 16 域）。

    对「新增 Claim」场景，为 yes 域生成可执行变更（本体/论证链/任务DAG/规则/Skill/表单/
    提示词/质量闸门/复用策略/实体关系），conditional 域按条件生成（默认 None）。

    与 analyze_schema_impact（决策层，输出「动作描述」）的区别：本函数是执行层，
    输出每个域的「具体变更内容」，供编排 Agent 直接落地，而非仅描述该做什么。

    返回 {changed, impact, changes}。
    """
    from .schema_diff import _detect_claim_addition, analyze_schema_impact
    if not _detect_claim_addition(diffs):
        return {"changed": False, "reason": "无 Claim 新增"}

    impact = analyze_schema_impact(diffs)
    ontology_boot = bootstrap_claim_ontology(diffs, semantica_client)

    changes = {
        # ---- yes 域：具体变更集 ----
        "ontology": ontology_boot.get("ontology") if ontology_boot.get("bootstrapped") else None,
        # 本体诱导来源（deterministic 规则 / semantica 抽取），供编排器与审计溯源
        "ontology_source": ontology_boot.get("source"),
        "argument_chain": {
            "new_claim_nodes": ["Claim（论证对象）"],
            "relation_types": ["supports", "contradicts", "depends_on", "premise_of"],
        },
        "task_dag": {
            "new_tasks": [
                {"task": "claim_extract", "desc": "从输入抽取并标准化 Claim", "deps": []},
                {"task": "claim_link", "desc": "将 Claim 与实体/证据/前提/章节关联", "deps": ["claim_extract"]},
                {"task": "claim_validate", "desc": "检查证据支持/逻辑冲突/状态标记", "deps": ["claim_link"]},
            ],
        },
        "rule": {
            "new_rules": [
                {"rule": "关键 Claim 必须有证据", "trigger": "claim_type ∈ {fact, conclusion, inference}"},
                {"rule": "Claim 分类", "trigger": f"claim_type ∈ {list(CLAIM_TYPE_VALUES)}"},
                {"rule": "未验证声明不得标记为已验证", "trigger": "status == unverified 时不得写为已证"},
            ],
        },
        "skill": {
            "skills": ["ClaimExtractionSkill", "ClaimLinkingSkill", "ClaimValidationSkill"],
        },
        "report_form": {
            "new_fields": [
                {"name": "claim_type", "type": "enum", "values": list(CLAIM_TYPE_VALUES)},
                {"name": "source", "type": "string"},
                {"name": "status", "type": "enum", "values": list(CLAIM_STATUS_VALUES)},
            ],
        },
        "prompt": {
            "context_additions": [
                "Claim 抽取指令（claim_type 五类 fact/hypothesis/inference/conclusion/recommendation）",
                "只填输入字段，推演字段（status/evidence_refs/confidence）由系统产生",
                "证据关联与输出格式",
            ],
        },
        "quality_gate": {
            "new_checks": [
                "Claim 覆盖率", "证据关联率", "冲突检测", "未验证声明阻断",
                "关键 Claim 不满足要求时阻止标记为已验证",
            ],
        },
        "reuse_strategy": {
            "decision": "依赖联动扩展（向后兼容）",
            "reason": "新增 Claim 字段，沿依赖图更新受影响资产，不判整模板失效",
        },
        "entity_relation": {
            "new_entities": ["Claim"],
            "new_relations": [
                {"relation": "Claim-supports-Evidence", "type": "supports"},
                {"relation": "Claim-depends_on-Claim", "type": "depends_on"},
                {"relation": "Claim-derived_from-Claim", "type": "derived_from"},
            ],
        },
        # ---- conditional 域：按条件生成（默认 None，不盲目装配） ----
        "scenario": None,          # 仅当 Claim 是待验证假设（claim_type=hypothesis）才建场景
        "variable": None,          # 仅当 Claim 可映射为可计算指标才新增变量
        "function": None,          # 仅当需结构化计算/校验才绑定函数
        "invariant": None,         # 仅当涉及硬约束才扩展不变式
        "report_structure": None,  # 仅当独立论证需求才扩展章节
        "cost_risk": None,         # 仅当涉及成本/风险计算才更新模型
    }

    return {"changed": True, "impact": impact, "changes": changes}
