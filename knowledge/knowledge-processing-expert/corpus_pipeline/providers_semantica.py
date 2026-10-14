# -*- coding: utf-8 -*-
"""providers_semantica —— 把 Semantica 接入门禁的 provider 接缝（方案 A）。

**核心原则：能力必须实测得出，不得假定。**
判定依据两级，均为客观证据：
  ① 服务端**自报工具清单**（客户端握手时写入 `client.tool_names`）；
  ② **活体探测**（发一次轻量调用，确认真能通）。

任何一项能力若拿不到证据，就**不声明** —— 依赖它的判据会判 `invalid`，
**不会因为「没查出问题」而被计为通过**。

组合策略（避免能力退化）：
  `CompositeProvider(primary=semantica, fallback=local)`
  · capabilities = 两者之并（实际能做到的）
  · capability_source = {能力: "semantica" | "local"} —— **逐项记录来源，可审计**
  · 调用优先走 semantica；semantica 抛错则回落本地，并把回落记入 `fallbacks`

这样既接通了 semantica，又不会因为它缺某项能力而让门禁整体失效，
同时**两图不一致的隐患变成可检项**（probe 文件里写着每项能力由谁提供）。
"""
from __future__ import annotations

import json
from pathlib import Path

# 能力 → Semantica 必须自报的工具
CAP_TOOLS = {
    "extract": ["extract_entities"],
    "disambiguate": ["query_graph"],
    "reasoning": ["run_reasoning"],
    "graph_write": ["add_entity", "add_relationship"],
    "analytics": ["get_graph_analytics"],
    "export": ["export_graph"],
}
# 关系抽取单独一项（capability 名与 entity 的 extract 同名但语义不同，用 relation_extract 区分）
REL_CAP_TOOLS = {"extract": ["extract_relations"], "reasoning": ["run_reasoning"]}

PROBE_FILE = "quality/provider_probe.yaml"


def _has_tools(client, names) -> bool:
    have = set(getattr(client, "tool_names", []) or [])
    return all(n in have for n in names)


def _live(client) -> tuple[bool, str]:
    """活体探测：一次轻量调用。"""
    try:
        r = client.get_graph_summary()
        return True, json.dumps(r, ensure_ascii=False)[:160]
    except Exception as e:                                # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


class CompositeProvider:
    """semantica 优先 + 本地兜底；逐项记录能力来源。"""

    def __init__(self, slot: str, primary, fallback, cap_source: dict, client=None):
        self.slot = slot
        self.primary = primary
        self.fallback = fallback
        self.client = client
        caps = set(getattr(fallback, "capabilities", set()) or set())
        caps |= {c for c, src in cap_source.items() if src == "semantica"}
        self.capabilities = caps
        self.capability_source = cap_source
        self.name = f"composite[{getattr(primary,'name','?')}+{getattr(fallback,'name','?')}]"
        self.failure_log: list[str] = []   # 记录失败（不再有 fallback）

    def _call(self, meth, *a, **kw):
        for impl, tag in ((self.primary, "semantica"), (self.fallback, "local")):
            if impl is None or not hasattr(impl, meth):
                continue
            try:
                r = impl.__getattribute__(meth)(*a, **kw)
                if tag == "local" and self.primary is not None:
                    self.fallbacks.append(f"{meth}→local")
                return r
            except Exception as e:                        # noqa: BLE001
                self.fallbacks.append(f"{meth}→{tag}失败:{type(e).__name__}")
        return []

    # EntityProtocol
    def extract(self, text):        return self._call("extract", text)
    def disambiguate(self, names):  return self._call("disambiguate", names)
    # RelationProtocol
    def run_reasoning(self, facts, rules): return self._call("derive", facts, rules)
    # GraphProtocol
    def add_entity(self, node_id, label, **meta):        return self._call("add_entity", node_id, label, **meta)
    def add_relationship(self, src, dst, t, **meta):     return self._call("add_relationship", src, dst, t, **meta)
    def analytics(self):            return self._call("analytics")
    def export(self, fmt="json"):   return self._call("export", fmt)


# ------------------------------------------------------------------ Semantica 侧实现
class _SEntity:
    name = "semantica-entity"

    def __init__(self, client, caps):
        self.c, self.capabilities = client, caps

    def extract(self, text):
        return self.c.call("extract_entities", {"text": text})

    def disambiguate(self, names):
        out = {}
        for n in names:
            try:
                out[n] = self.c.search_graph(n, limit=1) or n
            except Exception:                             # noqa: BLE001
                out[n] = n
        return out


class _SRelation:
    name = "semantica-relation"

    def __init__(self, client, caps):
        self.c, self.capabilities = client, caps

    def extract(self, text, entities):
        return self.c.call("extract_relations", {"text": text, "entities": entities})

    def run_reasoning(self, facts, rules):
        return self.c.run_reasoning([json.dumps(f, ensure_ascii=False) if isinstance(f, dict) else str(f)
                                     for f in (facts or [])])

    def causal_chain(self, start):
        return self.c.call("get_causal_chain", {"start": start})


class _SGraph:
    name = "semantica-graph"

    def __init__(self, client, caps, kg_path=None):
        self.c, self.capabilities, self.kg_path = client, caps, kg_path

    def add_entity(self, node_id, label, **meta):
        return self.c.add_entity(node_id, label, metadata=meta or None)

    def add_relationship(self, src, dst, rel_type, **meta):
        return self.c.add_relationship(src, dst, rel_type, metadata=meta or None)

    def analytics(self):
        return self.c.call("get_graph_analytics", {})

    def export(self, fmt="json-ld"):
        return self.c.export_graph(fmt)


# ------------------------------------------------------------------ 注册
def probe_semantica(client=None) -> dict:
    """探测 semantica 真实能力，返回证据（不注册）。"""
    if client is None:
        try:
            from .ontology_schema import _auto_semantica_client
            client = _auto_semantica_client()
        except Exception as e:                            # noqa: BLE001
            return {"available": False, "reason": f"客户端不可用: {type(e).__name__}: {e}",
                    "declared_tools": [], "capabilities": {}}
    if client is None:
        return {"available": False, "reason": "Semantica 未配置或不可连接（KP_SEMANTICA_AUTO 未启用）",
                "declared_tools": [], "capabilities": {}}
    tools = sorted(getattr(client, "tool_names", []) or [])
    ok, evidence = _live(client)
    caps = {}
    for cap, need in CAP_TOOLS.items():
        caps[cap] = "semantica" if (ok and _has_tools(client, need)) else "unavailable"
    for cap, need in REL_CAP_TOOLS.items():
        if cap in caps:
            continue
        caps[f"relation_{cap}"] = "semantica" if (ok and _has_tools(client, need)) else "unavailable"
    return {"available": True, "live": ok, "live_evidence": evidence,
            "declared_tools": tools, "capabilities": caps,
            "kg_path": getattr(client, "kg_path", None), "client": client}


def register_semantica_providers(corpus_dir=None, force: bool = False) -> dict:
    """探测并注册组合 provider（semantica 优先、本地兜底）。写成证据文件。"""
    from . import providers as P

    probe = probe_semantica()
    evidence = {k: v for k, v in probe.items() if k != "client"}
    if corpus_dir:
        q = Path(corpus_dir) / PROBE_FILE
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text(json.dumps({"policy": "能力须实测；未获证据的能力不声明，依赖它的判据判 invalid",
                                 "probe": evidence}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not probe.get("available") or not probe.get("live"):
        return {"registered": False, "probe": evidence,
                "note": "Semantica 不可用或活体探测失败 —— **不注册任何能力（fail-closed，禁止替身与降级）**"}
    client = probe["client"]
    caps = probe["capabilities"]

    e_caps = {c for c, s in caps.items() if s == "semantica" and c in ("extract", "disambiguate")}
    r_caps = {c for c, s in caps.items() if s == "semantica" and c in ("extract", "reasoning")}
    g_caps = {c for c, s in caps.items() if s == "semantica" and c in ("graph_write", "analytics", "export")}

    reg = {}
    for slot, primary, p_caps in (
            ("entity", _SEntity(client, e_caps), e_caps),
            ("relation", _SRelation(client, r_caps), r_caps),
            ("graph", _SGraph(client, g_caps, probe.get("kg_path")), g_caps)):
        local = P.get_provider(slot) or (P.LocalEntityProvider() if slot == "entity"
                                         else P.LocalRelationProvider() if slot == "relation"
                                         else P.LocalGraphProvider(corpus_dir))
        src = {c: ("semantica" if c in p_caps else "local") for c in P.required_capabilities().get("C4", set())}
        src = {}
        for c in (local.capabilities | p_caps):
            src[c] = "semantica" if c in p_caps else "local"
        comp = CompositeProvider(slot, primary, local, src, client)
        P.register_provider(slot, comp)
        reg[slot] = {"name": comp.name, "capabilities": sorted(comp.capabilities),
                     "capability_source": src}
    return {"registered": True, "probe": evidence, "providers": reg,
            "note": "已注册组合 provider：semantica 承担其自报且探测通过的能力，其余回落本地"}
