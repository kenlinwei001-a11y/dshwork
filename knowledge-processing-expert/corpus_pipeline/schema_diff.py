# -*- coding: utf-8 -*-
"""Schema Diff 引擎 —— 确定性结构比对 + 语义对齐。

分层（对应「LLM 语义建议 + 确定性校验」原则）：
  1. 结构比对（确定性）：字段名/类型，识别 新增 / 缺失 / 类型变化 / 未变。
  2. 语义对齐（确定性锚点）：用 semantic_model 把字段映射到标准概念，识别 改名 / 同义。
  3. 语义分类（可插拔）：未命中概念的字段，用分类器判 新变量 / 元数据；
     默认 DeterministicClassifier（规则），可替换为 JevClassifier（Choice 概率分类）。

产物（diff 清单）供下游 Asset Assembler 做「依赖联动扩展」，而非全量重写。
"""
from __future__ import annotations

from .semantic_model import build_concepts, resolve_concept, matched_concept_id


# --------------------------------------------------------------------------- #
# 语义分类器接口（可插拔：默认确定性，可接 Jev）
# --------------------------------------------------------------------------- #
class SemanticClassifier:
    """把「未命中概念字典的字段」分类为 new_variable / metadata / ..."""

    def classify(self, name: str, field_def: dict, concepts: dict) -> dict:
        raise NotImplementedError


_METADATA_HINTS = ("_id", "_source", "_status", "_created", "_updated", "_version",
                   "id", "source", "status", "created_at", "updated_at", "version", "timestamp")


def _looks_like_metadata(name: str) -> bool:
    low = name.lower()
    return any(low == h or low.endswith(h) for h in _METADATA_HINTS)


class DeterministicClassifier(SemanticClassifier):
    """确定性分类器：未命中概念 → 按命名特征判 元数据 / 新变量。零依赖，可复现。"""

    def classify(self, name: str, field_def: dict, concepts: dict) -> dict:
        kind = "metadata" if _looks_like_metadata(name) else "new_variable"
        return {"kind": kind, "confidence": 1.0, "concept_id": None, "classifier": "deterministic"}


class JevClassifier(SemanticClassifier):
    """可插拔 Jev 分类器（预留：Jev 作为独立 MCP 接入，不在此硬编码）。

    架构约定：Jev 是「语义判断题」的外部决策模型，未来作为独立 jev-mcp MCP 接入；
    kp-mcp 的 `semantic_classify` 工具暴露语义分类，默认走确定性（本类的 fallback），
    接 jev-mcp 后由上层把 Choice 概率作为额外信号传入，而非在 corpus_pipeline 内直连。

    接入时：把 name/field_def 组织成 state，问 Choice 问题
    「该字段相对历史 Schema 属于哪类？A新业务变量 B已有变量别名 C普通元数据 D结构性变化」，
    用返回的概率分布填充 confidence。
    """

    def __init__(self, client=None):
        self.client = client  # 预留：接入 jev-mcp 客户端后启用

    def classify(self, name: str, field_def: dict, concepts: dict) -> dict:
        if self.client is None:
            return DeterministicClassifier().classify(name, field_def, concepts)
        # 预留：组装 state + Choice 问题，解析概率分布 → kind/confidence
        raise NotImplementedError("jev-mcp 客户端已注入但 classify 尚未实现")


# --------------------------------------------------------------------------- #
# Schema Diff
# --------------------------------------------------------------------------- #
def _type_of(field_def: dict) -> str:
    return field_def.get("type", "unknown") if isinstance(field_def, dict) else "unknown"


def diff_schemas(old_schema: dict, new_schema: dict, concepts: dict | None = None,
                 classifier: SemanticClassifier | None = None) -> list[dict]:
    """对比新旧 Schema，输出差异清单（结构比对 + 语义对齐 + 语义分类）。

    old_schema/new_schema：{字段名: {"type": "string|number|array|object|boolean"}}。

    每个差异项含：
      kind: added | removed | type_changed | renamed
      语义信息：concept_id / via / semantic（新增字段的分类）
    """
    concepts = concepts if concepts is not None else build_concepts()
    classifier = classifier or DeterministicClassifier()

    added = []   # (field, new_def)
    removed = []  # (field, old_def)
    diffs = []

    # 1. 结构比对：新增 / 类型变化
    for field, new_def in new_schema.items():
        if field not in old_schema:
            added.append((field, new_def))
        elif _type_of(old_schema[field]) != _type_of(new_def):
            diffs.append({
                "field": field, "kind": "type_changed",
                "old_type": _type_of(old_schema[field]), "new_type": _type_of(new_def),
            })
    # 缺失
    for field in old_schema:
        if field not in new_schema:
            removed.append((field, old_schema[field]))

    # 2. 语义对齐：removed 字段的概念 id（用于改名检测）
    removed_concept = {}
    for field, _ in removed:
        cid = matched_concept_id(field, concepts)
        if cid:
            removed_concept[cid] = field

    # 3. 新增字段：改名检测 + 语义分类
    matched_removed = set()
    for field, new_def in added:
        cid = matched_concept_id(field, concepts)
        if cid and cid in removed_concept:
            diffs.append({
                "field": field, "kind": "renamed",
                "from": removed_concept[cid], "concept_id": cid,
            })
            matched_removed.add(removed_concept[cid])
        else:
            concept, via = resolve_concept(field, concepts)
            semantic = ({"kind": "alias_of_existing", "concept_id": concept["id"], "via": via, "confidence": 1.0}
                        if concept else classifier.classify(field, new_def, concepts))
            diffs.append({"field": field, "kind": "added", "new_type": _type_of(new_def), "semantic": semantic})

    # 4. 剩余 removed（未参与改名）
    for field, old_def in removed:
        if field not in matched_removed:
            diffs.append({"field": field, "kind": "removed", "old_type": _type_of(old_def)})

    return diffs


def summarize(diffs: list[dict]) -> dict:
    """差异摘要：按 kind 计数，便于闸门/装配决策。"""
    from collections import Counter
    c = Counter(d["kind"] for d in diffs)
    return {
        "total": len(diffs),
        "by_kind": dict(c),
        "added_fields": [d["field"] for d in diffs if d["kind"] == "added"],
        "removed_fields": [d["field"] for d in diffs if d["kind"] == "removed"],
        "renamed_fields": [(d["from"], d["field"]) for d in diffs if d["kind"] == "renamed"],
        "type_changed": [d["field"] for d in diffs if d["kind"] == "type_changed"],
    }


# --------------------------------------------------------------------------- #
# 16 域依赖联动扩展：Schema Diff → 资产域影响分析 + 装配动作
# --------------------------------------------------------------------------- #
# 16 个资产域对「新增 Claim」的影响规则（文档第三节影响分析表）。
# level：yes（受影响，须装配）/ conditional（视情况，按条件判断）。
CLAIM_IMPACT = {
    "ontology": ("yes", "检查是否已有 Claim 类及属性；没有则新增或扩展 Claim 类型与属性"),
    "argument_chain": ("yes", "将 Claim 加入论证图，定义前提/支持/反驳/推导关系"),
    "scenario": ("conditional", "仅当 Claim 是待验证假设时建立对应场景"),
    "variable": ("conditional", "仅当 Claim 可映射为可计算指标时才新增变量"),
    "task_dag": ("yes", "添加 Claim 解析/关联/校验任务节点并更新依赖"),
    "function": ("conditional", "需要结构化抽取/计算/校验时才绑定函数"),
    "rule": ("yes", "检查是否有 Claim 分类/证据要求/冲突检测规则"),
    "invariant": ("conditional", "仅对必须满足的 Claim 结构约束添加校验"),
    "skill": ("yes", "复用/扩展 Claim 抽取、实体链接、证据关联、验证技能"),
    "report_structure": ("conditional", "独立论证需求才扩展章节"),
    "report_form": ("yes", "增加 Claim 输入区、类型选择、来源字段、校验规则"),
    "prompt": ("yes", "扩展相关提示词的输入上下文与输出契约"),
    "quality_gate": ("yes", "检查 Claim 是否有依据、是否冲突、是否被误述为事实"),
    "reuse_strategy": ("yes", "评估旧模板是否兼容 Claim，记录扩展原因"),
    "entity_relation": ("yes", "建立 Claim 实例，连接证据/前提/来源/报告段落"),
    "cost_risk": ("conditional", "仅当 Claim 涉及成本/风险计算时才更新模型"),
}

_CLAIM_HINTS = ("claim", "assertion", "论点", "论断", "结论", "主张")


def _detect_claim_addition(diffs: list[dict]) -> bool:
    """检测 Schema Diff 里是否有 Claim 类新增字段。"""
    for d in diffs:
        if d["kind"] != "added":
            continue
        field = str(d.get("field", ""))
        if any(h in field.lower() or h in field for h in _CLAIM_HINTS):
            return True
    return False


def _generic_impact(domain_id: str, has_renamed: bool, has_type_changed: bool, has_added: bool) -> tuple[str, str]:
    """无 Claim 新增时，按改名/类型变化/新增字段做局部影响判断。"""
    if domain_id == "ontology":
        if has_type_changed:
            return "yes", "字段类型变化：兼容性检查，不直接覆盖旧定义"
        return "conditional", "结构未变则复用历史本体"
    if domain_id == "variable":
        if has_renamed or has_type_changed or has_added:
            return "yes", "字段改名/类型变化/新增：语义匹配 + 单位校验 + 字段映射"
        return "no", "无变化"
    if domain_id == "report_form":
        return ("yes", "新增字段补标签/类型/校验规则及下游映射") if has_added else ("no", "无变化")
    if domain_id == "prompt":
        return ("yes", "更新上下文构建器，明确新字段语义/任务/输出/缺失处理") if has_added else ("no", "无变化")
    if domain_id == "entity_relation":
        return ("conditional", "新增字段可能需建实体实例及关系") if has_added else ("no", "无变化")
    if domain_id == "task_dag":
        return ("conditional", "新增字段可能需补解析/校验节点") if has_added else ("no", "无变化")
    if domain_id in ("argument_chain", "rule", "quality_gate", "reuse_strategy", "skill"):
        return ("conditional", "新增字段可能影响该域，按语义分类后决定") if has_added else ("no", "无变化")
    if domain_id == "report_structure":
        return ("no", "新增字段不一定要新增章节，先判是否影响结构")
    if domain_id in ("scenario", "function", "invariant", "cost_risk"):
        return ("no", "文本类新增不改变该域；仅当涉及可计算/硬约束/成本风险才改")
    return ("no", "不受影响")


def analyze_schema_impact(diffs: list[dict]) -> dict:
    """Schema Diff → 16 资产域影响分析 + 装配动作（依赖联动扩展，而非全量重写）。

    返回 {domain_id: {affected: yes/conditional/no, action: str}}。
    新增 Claim 触发跨域联动（本体/论证链/任务DAG/规则/Skill/表单/提示词/质量闸门/复用策略/实体关系）；
    其余按改名/类型变化/新增字段做局部判断。
    """
    has_claim = _detect_claim_addition(diffs)
    has_renamed = any(d["kind"] == "renamed" for d in diffs)
    has_type_changed = any(d["kind"] == "type_changed" for d in diffs)
    has_added = any(d["kind"] == "added" for d in diffs)

    impact = {}
    for domain_id, rule in CLAIM_IMPACT.items():
        if has_claim:
            level, action = rule
        else:
            level, action = _generic_impact(domain_id, has_renamed, has_type_changed, has_added)
        impact[domain_id] = {"affected": level, "action": action}
    return impact


# --------------------------------------------------------------------------- #
# 显式变更策略（P2）：7 种复用策略的决策
# --------------------------------------------------------------------------- #
CHANGE_STRATEGIES = (
    "direct_reuse",              # 直接复用（引用历史资产版本，不改模板）
    "parameterized_reuse",       # 参数化复用（结构同，仅参数/阈值/单位/名称不同）
    "backward_compatible_extend",  # 向后兼容扩展（新增可选字段，创建新版本）
    "dependency_linked_extend",  # 依赖联动扩展（新字段影响多域，创建新版本沿依赖图更新）
    "branch_adapt",              # 分支适配（特殊需求，从模板分支）
    "rebuild",                   # 重建（领域/语义差异过大，重建项目专属资产）
    "reject",                    # 拒绝复用（版本不兼容/权限不足/来源不可信/约束冲突）
)


def decide_change_strategy(diffs: list[dict], forbidden: bool = False) -> dict:
    """根据 Schema Diff 差异，决定变更策略（7 种之一）。

    决策顺序（文档第四/五节）：
      1. reject：显式约束冲突/版本不兼容/权限不足（forbidden=True 时）
      2. direct_reuse：无差异
      3. dependency_linked_extend：Claim 新增（跨域联动）
      4. parameterized_reuse：仅改名/别名命中概念（语义相同）
      5. rebuild：字段类型变化（改变旧字段语义，不兼容）
      6. backward_compatible_extend：新增可选字段（旧消费者可忽略）
      7. branch_adapt / reject：预留（需外部输入，本函数不自动判定）

    返回 {strategy, modify_template, reason}。modify_template 恒为 False
    （历史模板不被新项目修改直接覆盖，只创建项目级实例或新版本）。
    """
    if forbidden:
        return {"strategy": "reject", "modify_template": False,
                "reason": "约束冲突/版本不兼容/权限不足/来源不可信，禁止自动装配"}

    if not diffs:
        return {"strategy": "direct_reuse", "modify_template": False,
                "reason": "新旧 Schema 无差异，直接引用历史资产版本"}

    kinds = {d["kind"] for d in diffs}

    # 依赖联动：Claim 新增（跨域影响）
    if _detect_claim_addition(diffs):
        return {"strategy": "dependency_linked_extend", "modify_template": False,
                "reason": "新增 Claim 触发跨域联动，创建新版本并沿依赖图更新受影响资产"}

    # 参数化：仅改名（命中概念 = 同义）
    if "renamed" in kinds and "type_changed" not in kinds and "added" not in kinds:
        return {"strategy": "parameterized_reuse", "modify_template": False,
                "reason": "字段改名/别名，语义相同，生成项目级参数配置"}

    # 类型变化：改变旧字段语义，不兼容
    if "type_changed" in kinds:
        return {"strategy": "rebuild", "modify_template": False,
                "reason": "字段类型变化改变旧字段语义，不兼容，重建项目专属资产"}

    # 新增可选字段（向后兼容）
    if "added" in kinds:
        return {"strategy": "backward_compatible_extend", "modify_template": False,
                "reason": "新增可选字段，旧消费者可忽略，创建新版本显式定义新字段结构"}

    # 默认：差异可忽略
    return {"strategy": "direct_reuse", "modify_template": False,
            "reason": "差异可忽略，直接复用历史资产"}
