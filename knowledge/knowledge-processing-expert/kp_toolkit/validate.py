"""确定性 schema 校验（零 LLM，仅标准库）。

对应各 skill 的 validator 部分：按契约字段校验结构化输出。
不依赖 jsonschema，用最小组件实现「必填字段 + 类型 + 枚举」校验。
"""
from __future__ import annotations

_REQUIRED = {
    "entity": ["id", "name", "type"],
    "fact": ["id", "subject", "predicate", "value"],
    "claim": ["id", "text"],
    "relation": ["id", "from", "to", "type"],
    "evidence": ["id", "source"],
    "reasoning": ["id", "inputs", "outputs"],
}

_ENUMS = {
    "validations.status": ("SUPPORT", "PARTIAL_SUPPORT", "CONTRADICT", "CONTEXT", "INSUFFICIENT"),
}


def validate_schema(nodes: list[dict], kind: str) -> dict:
    """校验一类节点的必填字段，返回 {ok, errors}。"""
    errors: list[str] = []
    required = _REQUIRED.get(kind, ["id"])
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"[{i}] 非对象")
            continue
        for f in required:
            if f not in node or node[f] in (None, ""):
                errors.append(f"[{i}] 缺少字段 {f}")
    return {"ok": not errors, "errors": errors}
