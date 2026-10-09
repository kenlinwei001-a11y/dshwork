"""确定性图谱编译与校验（零 LLM）。

对应 semantic-graph-compilation-skill 的确定性部分：
- 把八类节点装配为统一语义图谱。
- 校验跨节点引用、重复 id、悬空引用。
"""
from __future__ import annotations

NODE_KINDS = ("entities", "relations", "facts", "reasoning", "claims", "evidence", "conflicts", "validations")


def compile_graph(items: dict, project_id: str, version_id: str, meta: dict | None = None) -> dict:
    """把各节点列表装配为统一图谱结构。"""
    graph = {
        "project_id": project_id,
        "version_id": version_id,
        "meta": meta or {},
        "items": {k: (items.get(k) or []) for k in NODE_KINDS},
    }
    return graph


def _all_ids(items: dict) -> set[str]:
    ids = set()
    for kind in NODE_KINDS:
        for node in items.get(kind, []):
            if isinstance(node, dict) and node.get("id"):
                ids.add(node["id"])
    return ids


def dangling_refs(graph: dict) -> list[str]:
    """返回所有指向不存在节点的悬空引用。"""
    ids = _all_ids(graph.get("items", {}))
    missing: list[str] = []
    items = graph.get("items", {})
    ref_fields = {
        "relations": ("from", "to"),
        "reasoning": ("inputs", "outputs"),
        "claims": ("deps", "evidence"),
        "conflicts": ("involved",),
        "validations": ("claim",),
    }
    for kind, fields in ref_fields.items():
        for node in items.get(kind, []):
            if not isinstance(node, dict):
                continue
            for f in fields:
                val = node.get(f)
                refs = val if isinstance(val, list) else ([val] if isinstance(val, str) else [])
                for r in refs:
                    if r and r not in ids:
                        missing.append(f"{kind}[{node.get('id','?')}].{f} -> {r}")
    return missing


def validate_graph(graph: dict) -> dict:
    """确定性校验图谱，返回 {ok, errors, stats}。"""
    errors: list[str] = []
    items = graph.get("items", {})
    seen: set[str] = set()
    stats = {}
    for kind in NODE_KINDS:
        nodes = items.get(kind, [])
        stats[kind] = len(nodes)
        for node in nodes:
            if not isinstance(node, dict) or not node.get("id"):
                errors.append(f"{kind}: 节点缺少 id")
                continue
            if node["id"] in seen:
                errors.append(f"重复 id: {node['id']}")
            seen.add(node["id"])
    errors += dangling_refs(graph)
    return {"ok": not errors, "errors": errors, "stats": stats}
