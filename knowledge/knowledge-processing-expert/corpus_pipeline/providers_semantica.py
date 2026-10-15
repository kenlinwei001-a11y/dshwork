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
        self.failure_log: list[str] = []   # 记录失败
        self.fallbacks: list[str] = []     # ★ 曾漏初始化：回落记录会 AttributeError（已修）

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
        # ★ fail-closed：**无人提供该方法**不是"空结果"，而是**能力缺失**。
        #   此前 return [] 把接线错误伪装成正常空输出（本会话反复出现的同一类缺陷）。
        raise NotImplementedError(
            f"composite[{self.slot}] 无实现提供 {meth}()：primary={getattr(self.primary,'name',None)} "
            f"fallback={getattr(self.fallback,'name',None)}；记录={self.fallbacks}")

    # EntityProtocol
    def extract(self, text):        return self._call("extract", text)
    def disambiguate(self, names):  return self._call("disambiguate", names)
    # RelationProtocol
    # ★ 曾写作 self._call("derive", ...)：`derive` 在两侧实现里**都不存在**
    #   ⇒ hasattr 全跳过 ⇒ 落到末尾 return [] ⇒ **永远瞬时返回空**，
    #   表现为"Semantica 未参与"而实为**接线错误**（实测 s4 outputs=0 的真因）。
    def run_reasoning(self, facts, rules): return self._call("run_reasoning", facts, rules)
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

    def _to_semantica(self, facts, rules):
        """把本管线的 facts/rules 转成 Semantica Reasoner 的**语法与谓词**。

        实测契约（semantica/reasoning/reasoner.py、mcp_server/_tool_run_reasoning）：
          · 规则串语法 `IF <cond> AND <cond> THEN <concl>`（变量写 ?var）；**不支持 `:-`**
          · 事实为 `pred(arg, arg)`；**只做 Horn 逻辑前向链，不做算术**
        因此：
          · 事实层：节点 → 取值(P,v)；依 caliber_direction → 上限(P,v)/下限(P,v)；
            依 object_role → 设计值(P,v)；规则 → 派生(T,D)/依赖(T,D)（供模态传播与传递闭包）
          · 规则层：加载**通用逻辑规则库** logic_rules.yaml（跨项目复用、零数据）；
            管线里的**算术规则（computes）不传**（Semantica 不做算术），记入 skipped 不静默丢弃
        变量名统一用 **predicate**：与 rules.yaml 的 deps/target 同一命名空间，否则无法合一。
        """
        gf = []
        for f in (facts or []):
            if not isinstance(f, dict):
                continue
            key = str(f.get("predicate") or f.get("subject") or "").strip()
            val = str(f.get("value") or "").strip()
            if not key:
                continue
            if val:
                gf.append(f"取值({key}, {val})")
                d = str(f.get("caliber_direction") or "")
                if "上限" in d:
                    gf.append(f"上限({key}, {val})")
                if "下限" in d:
                    gf.append(f"下限({key}, {val})")
                if "设计" in str(f.get("object_role") or ""):
                    gf.append(f"设计值({key}, {val})")
        skipped = []
        for r in (rules or []):
            if not isinstance(r, dict):
                continue
            tgt = str(r.get("target") or r.get("label") or "").strip()
            if not tgt:
                continue
            for d in (r.get("deps") or []):
                d = str(d).strip()
                if d:
                    # ★ join 键（被依赖项 d）置于**第 1 参数位** —— 引擎要求 join 变量在
                    #   两侧处于同一位置（已实测：跨位置/链式 join 不产生推导）。
                    gf.append(f"派生源({d}, {tgt})")
                    gf.append(f"依赖源({d}, {tgt})")
            if str(r.get("kind") or "").lower() in ("compute", "compute_rule") or r.get("expr"):
                skipped.append(str(r.get("id") or tgt))
        import yaml as _y
        lib = []
        for c in (Path("/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert"
                       "/corpus_pipeline/logic_rules.yaml"),
                  Path(__file__).resolve().parent / "logic_rules.yaml"):
            if c.exists():
                d = _y.load(c.read_text(encoding="utf-8"),
                            Loader=getattr(_y, "CSafeLoader", _y.SafeLoader)) or {}
                lib = [x["if_then"] for x in (d.get("rules") or []) if x.get("if_then")]
                break
        return list(dict.fromkeys(gf)), lib, skipped

    def run_reasoning(self, facts, rules):
        gf, lib, skipped = self._to_semantica(facts, rules)
        self.last_adapter = {"facts_sent": len(gf), "rules_sent": len(lib),
                             "skipped_arithmetic": skipped}
        raw = self.c.run_reasoning(gf, lib)
        # ★ providers.py 约定「每个 provider 返回**同一结构**」⇒ 本层负责规范化：
        #   此前直接返回 raw dict ⇒ 下游 list(dict) 得到键名、再 .get() 即 AttributeError。
        return self._normalize(raw)

    @staticmethod
    def _normalize(raw) -> list:
        """{"derived_facts": ["需比对上限(X)"]} → [{rule,target,status,engine,raw}, ...]"""
        import re as _re
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            if raw.get("error"):
                return [{"rule": "semantica", "target": None, "status": "错误",
                         "engine": "semantica", "raw": str(raw["error"])}]
            items = raw.get("derived_facts") or []
        else:
            items = []
        out = []
        for it in items:
            t = it if isinstance(it, str) else json.dumps(it, ensure_ascii=False)
            m = _re.match(r"^\s*([\w\u4e00-\u9fff_]+)\s*\((.*)\)\s*$", t)
            pred = m.group(1) if m else "推演结论"
            arg = (m.group(2).split(",")[0].strip() if m else "")
            out.append({"rule": f"SEM-{pred}", "target": arg or t, "predicate": pred,
                        "status": "推演结论", "engine": "semantica", "raw": t})
        return out


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
