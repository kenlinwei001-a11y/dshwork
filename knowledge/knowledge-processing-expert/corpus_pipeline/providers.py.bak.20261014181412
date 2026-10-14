# -*- coding: utf-8 -*-
"""可替换环节的 provider 接缝（strategy seam）。

目的：让「用 semantica 替换某些环节」成为**换实现，而不是改流程**。
门禁只依赖下面的**接口契约**，不依赖具体实现；因此替换 provider 后
闭环判据（C1–C7）、分步门禁（S0–S11）、客观判据（K1–K12）**无需改动**。

默认实现全部为本地确定性实现（零 LLM）。后续可注册 semantica 版本：
    register_provider("entity_extraction", SemanticaEntityProvider())
此时门禁与下游不变，只换了产出的来源。

约定：每个 provider 返回**同一结构**，并声明 `capabilities`；
门禁依据 capabilities 决定哪些判据可执行，缺能力时该项判 `invalid`（不得判 pass）。
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# ------------------------------------------------------------------ 接口
@runtime_checkable
class EntityProvider(Protocol):
    """实体抽取与消歧。可替换为 semantica 的 extract_entities / add_entity / query_graph。"""
    name: str
    capabilities: set[str]          # {"extract", "disambiguate", "graph_write"}

    def extract(self, text: str) -> list[dict]:
        """→ [{name, type, mentions:[{char_span}], confidence}]"""

    def disambiguate(self, names: list[str]) -> dict:
        """→ {name: canonical}"""


@runtime_checkable
class RelationProvider(Protocol):
    """关系抽取与落库。可替换为 semantica 的 extract_relations / add_relationship。"""
    name: str
    capabilities: set[str]          # {"extract", "graph_write", "reasoning", "causal_chain"}

    def extract(self, text: str, entities: list[dict]) -> list[dict]:
        """→ [{from, to, type, evidence}]"""


@runtime_checkable
class ReasoningProvider(Protocol):
    """推演与因果。可替换为 semantica 的 run_reasoning / get_causal_chain / find_precedents。"""
    name: str
    capabilities: set[str]

    def derive(self, facts: list[dict], rules: list[dict]) -> list[dict]:
        """→ [{rule, computed, steps}]"""

    def causal_chain(self, start: str) -> list[dict]:
        """→ [{from, to, type}]"""


@runtime_checkable
class GraphProvider(Protocol):
    """图存储与分析。可替换为 semantica 的 query_graph / get_graph_analytics / export_graph。"""
    name: str
    capabilities: set[str]

    def add_entity(self, node_id: str, label: str, **meta) -> dict: ...
    def add_relationship(self, src: str, dst: str, rel_type: str, **meta) -> dict: ...
    def analytics(self) -> dict: ...
    def export(self, fmt: str = "json") -> Any: ...


# ------------------------------------------------------------------ 注册表
_REGISTRY: dict[str, Any] = {}


def register_provider(slot: str, provider) -> None:
    """注册/替换某环节的 provider。slot ∈ {'entity','relation','reasoning','graph'}"""
    if slot not in {"entity", "relation", "reasoning", "graph"}:
        raise KeyError(f"未知 slot: {slot}")
    _REGISTRY[slot] = provider


def get_provider(slot: str, default=None):
    """取 provider；未注册则返回传入的本地默认实现。"""
    return _REGISTRY.get(slot, default)


def provider_status() -> dict:
    """供门禁判断：哪些环节有 provider、其 capabilities 是什么。

    门禁用这张表决定判据是否 `invalid`：
      例：若 relation provider 无 "causal_chain" 能力，
          则 C7 的 causes 判据标 invalid，而**不是**判 pass。
    """
    return {slot: {"name": getattr(p, "name", type(p).__name__),
                   "capabilities": sorted(getattr(p, "capabilities", set()))}
            for slot, p in _REGISTRY.items()}


def required_capabilities() -> dict:
    """判据 → 所需能力。缺能力 ⇒ 该判据 invalid（不得 pass）。"""
    return {
        "C1": set(),                                    # 依据闭环：纯集合差
        "C2": set(),                                    # 关键取值：纯集合差 + 量纲
        "C3": set(),
        "C4": {"extract"},                              # 设备参数需抽取能力
        "C5": set(),
        "C6": set(),
        "C7": {"extract", "reasoning"},                 # 关系闭环需关系抽取与推演
        "K8": {"graph_write"},                          # 图完整性需可寻址写入
        "K10": set(),
    }


def gate_capability_report() -> dict:
    """输出「判据 → 可用性」，供编排器决定执行/跳过/invalid。"""
    st = provider_status()
    have: set[str] = set()
    for v in st.values():
        have |= set(v["capabilities"])
    return {g: ("ready" if need <= have else "invalid:missing=" + ",".join(sorted(need - have)))
            for g, need in required_capabilities().items()}


if __name__ == "__main__":
    import json
    print(json.dumps({"providers": provider_status(),
                      "capabilities_required": {k: sorted(v) for k, v in required_capabilities().items()},
                      "gate_readiness": gate_capability_report()},
                     ensure_ascii=False, indent=2))

# ------------------------------------------------------------------ 本地默认实现
# 默认全部为确定性本地实现（零 LLM）。semantica 版本可随时 register_provider 覆盖，
# 门禁与下游无需改动。
class LocalEntityProvider:
    name = "local-entity"
    capabilities = {"extract", "disambiguate"}

    def extract(self, text: str) -> list[dict]:
        """确定性实体候选：取文本中的书名号实体名、项目/单位名等（保守，不猜）。"""
        import re as _re
        names = set(_re.findall(r"《([^》]{2,40})》", text))
        return [{"name": n, "type": "StandardOrDocument", "mentions": [], "confidence": "rule"}
                for n in sorted(names)]

    def disambiguate(self, names: list[str]) -> dict:
        from .alias import build_alias_map
        m, _ = build_alias_map(list(names))
        return m


class LocalRelationProvider:
    name = "local-relation"
    capabilities = {"extract", "reasoning"}

    def extract(self, text: str, entities: list[dict]) -> list[dict]:
        return []            # 关系抽取暂由 LLM 层承担；结构化关系由 relations_ext 推导

    def derive(self, facts: list[dict], rules: list[dict]) -> list[dict]:
        return []            # 由既有的 stage_5 回放承担（确定性）


class LocalGraphProvider:
    name = "local-graph"
    capabilities = {"graph_write", "analytics", "export"}

    def __init__(self, corpus_dir=None):
        self.corpus_dir = corpus_dir

    def _load(self, name, default):
        import json
        from pathlib import Path as _P
        f = _P(self.corpus_dir) / name if self.corpus_dir else None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                  # noqa: BLE001
            return default

    def add_entity(self, node_id, label, **meta):
        return {"id": node_id, "name": label, "type": "ENTITY", **meta}

    def add_relationship(self, src, dst, rel_type, **meta):
        return {"from": src, "to": dst, "type": rel_type, **meta}

    def analytics(self) -> dict:
        nodes = self._load("graph/nodes.yaml", [])
        rels = self._load("graph/relations.yaml", [])
        deg: dict[str, int] = {}
        for r in rels:
            for side in ("from", "to"):
                deg[str(r.get(side))] = deg.get(str(r.get(side)), 0) + 1
        iso = [n.get("id") for n in nodes if n.get("id") not in deg]
        return {"nodes": len(nodes), "relations": len(rels), "isolated": len(iso),
                "isolated_ids": iso[:20], "max_degree": max(deg.values()) if deg else 0}

    def export(self, fmt: str = "json"):
        if fmt in ("json", "json-ld"):
            return {"nodes": self._load("graph/nodes.yaml", []),
                    "relations": self._load("graph/relations.yaml", [])}
        raise ValueError(f"本地实现仅支持 json/json-ld，收到 {fmt}")


def register_local_defaults(graph_corpus_dir=None) -> dict:
    """注册本地默认 provider（幂等）。默认态即为「就绪」。"""
    register_provider("entity", LocalEntityProvider())
    register_provider("relation", LocalRelationProvider())
    register_provider("graph", LocalGraphProvider(graph_corpus_dir))
    return provider_status()


register_local_defaults()

# ------------------------------------------------------------------ Semantica 接入（方案 A，惰性）
# 不在 import 时 spawn 子进程；首次查询 provider 状态/能力就绪度时才尝试一次（幂等）。
# 关闭：KP_SEMANTICA_PROVIDERS=0
_SEM_PROVIDERS = None
_SEM_ATTEMPTED = False


def ensure_semantica_providers(force: bool = False) -> dict:
    """探测并注册 Semantica provider（组合：semantica 优先、本地兜底）。

    诚实性约束：能力由**服务端自报工具清单 + 活体探测**两级证据得出；
    未获证据的能力不声明 —— 依赖它的判据判 `invalid`，不得视为通过。
    """
    global _SEM_PROVIDERS, _SEM_ATTEMPTED
    if _SEM_ATTEMPTED and not force:
        return _SEM_PROVIDERS or {"registered": False, "note": "未尝试"}
    _SEM_ATTEMPTED = True
    import os
    if os.environ.get("KP_SEMANTICA_PROVIDERS", "1") == "0":
        _SEM_PROVIDERS = {"registered": False, "note": "KP_SEMANTICA_PROVIDERS=0，已禁用"}
        return _SEM_PROVIDERS
    try:
        from .providers_semantica import register_semantica_providers
        _SEM_PROVIDERS = register_semantica_providers()
    except Exception as e:                                  # noqa: BLE001
        _SEM_PROVIDERS = {"registered": False, "error": f"{type(e).__name__}: {e}"}
    return _SEM_PROVIDERS


_sem_provider_status = provider_status


def provider_status() -> dict:                              # noqa: F811
    ensure_semantica_providers()
    st = _sem_provider_status()
    for v in st.values():
        src = getattr(get_provider("entity"), "capability_source", None)
    for slot in list(st):
        p = get_provider(slot)
        if hasattr(p, "capability_source"):
            v = st[slot]
            v["capability_source"] = p.capability_source
            if getattr(p, "fallbacks", None):
                v["fallbacks"] = p.fallbacks[-8:]
    return st
