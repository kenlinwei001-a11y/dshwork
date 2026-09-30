"""确定性溯源链构建（零 LLM）。

对应 provenance-binding-skill 的确定性部分：
- 按引用把 Decision → Claim → Reasoning → Fact → Evidence → Sentence → Chunk → Document 串成链。
"""
from __future__ import annotations


def build_provenance(node_id: str, graph: dict) -> list[dict]:
    """从一个节点反向追溯到证据来源，返回有序溯源链。"""
    items = graph.get("items", {})
    index = {}
    for kind in ("entities", "relations", "facts", "reasoning", "claims", "evidence", "conflicts", "validations"):
        for node in items.get(kind, []):
            if isinstance(node, dict) and node.get("id"):
                index[node["id"]] = node

    chain: list[dict] = []
    visited: set[str] = set()

    def walk(nid: str, depth: int = 0):
        if nid in visited or depth > 20:
            return
        visited.add(nid)
        node = index.get(nid)
        if not node:
            return
        chain.append({"id": nid, "kind": _kind_of(nid, items), "depth": depth, "source": node.get("source")})
        for ref in _upstream_refs(node):
            walk(ref, depth + 1)

    walk(node_id)
    return chain


def _kind_of(nid: str, items: dict) -> str:
    for kind in ("entities", "relations", "facts", "reasoning", "claims", "evidence", "conflicts", "validations"):
        for node in items.get(kind, []):
            if isinstance(node, dict) and node.get("id") == nid:
                return kind
    return "unknown"


def _upstream_refs(node: dict) -> list[str]:
    refs = []
    for f in ("deps", "evidence", "inputs", "from", "involved", "claim"):
        val = node.get(f)
        if isinstance(val, list):
            refs.extend(v for v in val if isinstance(v, str))
        elif isinstance(val, str):
            refs.append(val)
    return refs


def trace_to_evidence(claim_id: str, graph: dict) -> list[str]:
    """返回 claim 可追溯到的 evidence / sentence 来源 id 列表。"""
    chain = build_provenance(claim_id, graph)
    return [c["id"] for c in chain if c["kind"] in ("evidence", "facts", "sentence", "chunk", "document")]
