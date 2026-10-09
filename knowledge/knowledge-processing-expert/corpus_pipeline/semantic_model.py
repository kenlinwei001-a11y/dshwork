# -*- coding: utf-8 -*-
"""语义模型（Ossie 式概念字典）—— Schema Diff 的「语义对齐」锚点。

把领域规则库（domain_rules）的 COMPUTE_SPEC / VARIABLES / TERM_ALIASES 组合成
结构化的「语义概念字典」，每个概念含 canonical_name / aliases / kind / unit / formula / deps。

语义对齐 = 把新/旧 Schema 字段映射到标准概念：命中的判「改名/同义」，未命中的交
语义分类器（默认别名表，可接 Jev）判「新概念/元数据」，同名异义靠 description 消歧。

目标与 Apache Ossie 一致（语义层标准、YAML 定义标准概念），格式预留 Ossie 导入适配。
"""
from __future__ import annotations
import re

from .domain_rules import (
    FEASIBILITY_COMPUTE_SPEC, FEASIBILITY_VARIABLES, TERM_ALIASES,
)


def _slug(name: str) -> str:
    """概念 id：非空兜底（Ossie 式英文 id 映射可后续补充）。"""
    return name or "unnamed"


def build_concepts(doc_type: str | None = None) -> dict[str, dict]:
    """构建概念字典：metric（计算指标，来自 COMPUTE_SPEC）+ attribute（输入变量，来自 VARIABLES）。"""
    concepts: dict[str, dict] = {}

    # 1. metric 概念：计算指标
    for label, s in FEASIBILITY_COMPUTE_SPEC.items():
        deps = re.findall(r'\{([^{}]+)\}', s["spec"])
        concepts[label] = {
            "id": _slug(label),
            "canonical_name": label,
            "aliases": sorted(k for k, v in TERM_ALIASES.items() if v == label),
            "kind": "metric",
            "unit": s.get("unit", ""),
            "formula": s.get("spec", ""),
            "deps": deps,
            "description": "",
        }

    # 2. attribute 概念：输入变量
    for label, v in FEASIBILITY_VARIABLES.items():
        if label in concepts:
            continue  # 同名 metric 优先
        concepts[label] = {
            "id": _slug(label),
            "canonical_name": label,
            "aliases": sorted(k for k, val in TERM_ALIASES.items() if val == label),
            "kind": "attribute",
            "unit": v.get("unit", ""),
            "formula": None,
            "deps": [],
            "description": "",
        }

    return concepts


def resolve_concept(name: str, concepts: dict[str, dict] | None = None):
    """字段名 → 概念匹配（语义对齐）。

    返回 (concept, via)：
      concept：命中的概念 dict；None 表示未命中。
      via：'canonical'（精确匹配规范名）| 'alias'（别名命中）| None（未命中）。
    """
    if not name:
        return None, None
    concepts = concepts if concepts is not None else build_concepts()
    if name in concepts:
        return concepts[name], "canonical"
    # 别名匹配：优先用 concepts 里各概念的 aliases 字段（含导入的 Ossie synonyms）
    for c in concepts.values():
        if name in (c.get("aliases") or []):
            return c, "alias"
    # 兜底：全局 TERM_ALIASES
    canon = TERM_ALIASES.get(name)
    if canon and canon in concepts:
        return concepts[canon], "alias"
    return None, None


def matched_concept_id(name: str, concepts: dict[str, dict] | None = None) -> str | None:
    """返回命中的概念 id（或 None）—— 语义对齐精简版，供 schema_diff 调用。"""
    concept, _ = resolve_concept(name, concepts)
    return concept["id"] if concept else None


# --------------------------------------------------------------------------- #
# Apache Ossie YAML 导入/导出适配器（未来对接 Apache Ossie 生态）
# --------------------------------------------------------------------------- #
def _extract_ossie_expr(expression) -> str:
    """从 Ossie 的 expression（{dialects: [...]}）提取 ANSI_SQL 表达式文本。"""
    if isinstance(expression, str):
        return expression
    if isinstance(expression, dict):
        for d in expression.get("dialects", []):
            if isinstance(d, dict) and d.get("dialect") == "ANSI_SQL":
                return d.get("expression", "")
        dialects = expression.get("dialects", [])
        if dialects and isinstance(dialects[0], dict):
            return dialects[0].get("expression", "")
    return ""


def import_ossie_yaml(yaml_text: str, merge_into: dict[str, dict] | None = None) -> dict[str, dict]:
    """从 Apache Ossie 语义模型 YAML 导入概念字典。

    映射（用于「语义对齐」的锚点扩充，不覆盖本地计算规格）：
      datasets[].fields[].name → attribute 概念；synonyms → aliases。
      metrics[].name → metric 概念；synonyms → aliases；expression → formula。

    merge_into：若提供，则合并进该概念字典（本地概念优先，不覆盖）。
    """
    import yaml
    data = yaml.safe_load(yaml_text) or {}
    concepts = dict(merge_into) if merge_into else {}

    for model in data.get("semantic_model", []):
        if not isinstance(model, dict):
            continue
        # datasets → fields → attribute 概念
        for ds in model.get("datasets", []):
            if not isinstance(ds, dict):
                continue
            for f in ds.get("fields", []):
                if not isinstance(f, dict) or not f.get("name"):
                    continue
                name = f["name"]
                if name in concepts:
                    continue  # 本地概念优先
                concepts[name] = {
                    "id": name,
                    "canonical_name": name,
                    "aliases": f.get("synonyms") or [],
                    "kind": "attribute",
                    "unit": f.get("datatype", ""),
                    "formula": None,
                    "deps": [],
                    "description": f.get("description", ""),
                }
        # metrics → metric 概念
        for m in model.get("metrics", []):
            if not isinstance(m, dict) or not m.get("name"):
                continue
            name = m["name"]
            if name in concepts:
                continue
            expr = _extract_ossie_expr(m.get("expression"))
            concepts[name] = {
                "id": name,
                "canonical_name": name,
                "aliases": m.get("synonyms") or [],
                "kind": "metric",
                "unit": m.get("datatype", ""),
                "formula": expr,
                "deps": re.findall(r'\{([^{}]+)\}', expr) if expr else [],
                "description": m.get("description", ""),
            }
    return concepts


def export_ossie_yaml(concepts: dict[str, dict], model_name: str = "domain_semantic_model",
                      version: str = "0.2.0.dev0") -> str:
    """把概念字典导出为 Apache Ossie 语义模型 YAML。

    attribute → datasets[].fields[]，metric → metrics[]，aliases → synonyms。
    """
    import yaml
    fields, metrics = [], []
    for name, c in concepts.items():
        if not isinstance(c, dict):
            continue
        synonyms = c.get("aliases") or []
        if c.get("kind") == "metric":
            metrics.append({
                "name": name,
                "description": c.get("description", ""),
                "synonyms": synonyms,
                "expression": {"dialects": [{"dialect": "ANSI_SQL", "expression": c.get("formula", "")}]},
            })
        else:
            fields.append({
                "name": name,
                "description": c.get("description", ""),
                "synonyms": synonyms,
            })
    model = {
        "version": version,
        "semantic_model": [{
            "name": model_name,
            "datasets": [{"name": "variables", "fields": fields}],
            "metrics": metrics,
            "relationships": [],
        }],
    }
    return yaml.safe_dump(model, allow_unicode=True, sort_keys=False)
