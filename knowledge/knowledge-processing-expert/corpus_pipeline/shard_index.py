# -*- coding: utf-8 -*-
"""shard_index —— 语料包分片索引（browse / resolve 两段式取数）。

## 解决什么问题

`nodes.yaml` 1.87 MB / 2410 节点，**一次全读 36 秒**。
但写某一节只需要该节的几十个节点。

实测：
    nodes.yaml 全读          36.18 s
    relations.yaml 全读      18.82 s
    → 55 s 里有 54 s 是"读了不需要的"

## 做法：两段式（借 EvoOntology 的 browse_semantics / resolve_semantics）

    browse()          读 shards/index.json（几千字节，毫秒级）→ 知道有什么、在哪
    resolve(section)  读 shards/by-section/<hash>.json（几十 KB）→ 只取该节

**分片维度**（可叠加）：
    by-section   按章节（写报告时最常用）
    by-domain    按 16 域
    by-kind      按节点类型
    by-rule      按规则（查某条规则涉及哪些节点）

## 用法

    from corpus_pipeline.shard_index import build, browse, resolve

    build("<语料包目录>")                       # 一次性建索引
    idx = browse("<语料包目录>")                # {sections: {...}, domains: {...}, counts: {...}}
    nodes = resolve("<语料包目录>", section="§5.2")
    nodes = resolve("<语料包目录>", domain="投资估算")
    nodes = resolve("<语料包目录>", ids=["P-abc123", "P-def456"])
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

SHARD_DIR = "shards"


def _h(s: str) -> str:
    """稳定短哈希：同输入同文件名（不用中文文件名，避免跨平台问题）。"""
    return hashlib.sha1(str(s).encode("utf-8")).hexdigest()[:12]


def _load_yaml(p: Path):
    try:
        from corpus_pipeline.fastload import load as _fl
        return _fl(p)
    except Exception:
        import yaml
        return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None


def _dump(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def build(corpus_dir) -> dict:
    """建分片索引。返回 {sections, domains, rules, kinds, total_nodes, shards_written}。"""
    root = Path(corpus_dir)
    nodes = _load_yaml(root / "graph" / "nodes.yaml") or []
    rels = _load_yaml(root / "graph" / "relations.yaml") or []
    rules = _load_yaml(root / "graph" / "rules.yaml") or []
    sroot = root / SHARD_DIR

    # ---- 分桶 ----
    buckets = {"by-section": {}, "by-domain": {}, "by-kind": {}}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        sec = str(n.get("section") or "§?")
        buckets["by-section"].setdefault(sec, []).append(n)
        dom = str(n.get("domain") or "未分类")
        buckets["by-domain"].setdefault(dom, []).append(n)
        kind = str(n.get("kind") or "unknown")
        buckets["by-kind"].setdefault(kind, []).append(n)

    # 关系按端点归属分片（一个关系进两侧章节，便于单节取全）
    node_sec = {str(n.get("id")): str(n.get("section") or "§?")
                for n in nodes if isinstance(n, dict) and n.get("id")}
    rel_by_sec = {}
    for r in rels:
        if not isinstance(r, dict):
            continue
        for key in ("from", "to"):
            s = node_sec.get(str(r.get(key)))
            if s:
                rel_by_sec.setdefault(s, []).append(r)

    # 规则按 section 分片
    rule_by_sec = {}
    for r in rules:
        if not isinstance(r, dict):
            continue
        s = str(r.get("section") or r.get("section_basis") or "§?")
        rule_by_sec.setdefault(s, []).append(r)

    # ---- 写分片 ----
    written = 0
    index = {"version": "1", "source": str(root.name),
             "counts": {"nodes": len(nodes), "relations": len(rels), "rules": len(rules)},
             "by-section": {}, "by-domain": {}, "by-kind": {}}
    for dim, bs in buckets.items():
        for name, items in bs.items():
            fn = "%s/%s.json" % (dim, _h(name))
            entry = {"name": name, "file": fn, "count": len(items)}
            if dim == "by-section":
                entry["relations"] = {"file": "relations/%s.json" % _h(name),
                                      "count": len(rel_by_sec.get(name, []))}
                entry["rules"] = {"file": "rules/%s.json" % _h(name),
                                  "count": len(rule_by_sec.get(name, []))}
            index[dim][name] = entry
            _dump(sroot / fn, items); written += 1
    for name, items in rel_by_sec.items():
        _dump(sroot / "relations" / ("%s.json" % _h(name)), items); written += 1
    for name, items in rule_by_sec.items():
        _dump(sroot / "rules" / ("%s.json" % _h(name)), items); written += 1

    # 节点 id → 分片，供 resolve(ids=...) 用
    idmap = {}
    for sec, items in buckets["by-section"].items():
        for n in items:
            if n.get("id"):
                idmap[str(n["id"])] = _h(sec)
    # id 映射单独存（2410 条，别塞进 index.json 拖慢 browse）
    _dump(sroot / "index.json", index)
    _dump(sroot / "ids.json", idmap)

    return {"sections": len(buckets["by-section"]), "domains": len(buckets["by-domain"]),
            "kinds": len(buckets["by-kind"]), "total_nodes": len(nodes),
            "shards_written": written, "index_size": (sroot / "index.json").stat().st_size}


def browse(corpus_dir) -> dict:
    """只读索引（毫秒级）。返回目录：有什么、多少、在哪。"""
    root = Path(corpus_dir) / SHARD_DIR
    p = root / "index.json"
    if not p.exists():
        return {"error": "索引不存在，先跑 build()", "hint": "kp_cli.py shard <目录>"}
    idx = json.loads(p.read_text(encoding="utf-8"))
    return idx


def resolve(corpus_dir, *, section=None, domain=None, kind=None, ids=None,
            with_relations=False, with_rules=False) -> list:
    """按需取分片。返回该片的节点列表（可附带关系与规则）。"""
    root = Path(corpus_dir) / SHARD_DIR
    ip = root / "index.json"
    if not ip.exists():
        return []
    idx = json.loads(ip.read_text(encoding="utf-8"))

    def _read(rel):
        p = root / rel
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

    if section is not None:
        e = (idx.get("by-section") or {}).get(section)
        if not e:
            return []
        out = _read(e["file"])
        if with_relations:
            out = {"nodes": out, "relations": _read(e["relations"]["file"])}
        if with_rules:
            out = out if isinstance(out, dict) else {"nodes": out}
            out["rules"] = _read(e["rules"]["file"])
        return out
    if domain is not None:
        e = (idx.get("by-domain") or {}).get(domain)
        return _read(e["file"]) if e else []
    if kind is not None:
        e = (idx.get("by-kind") or {}).get(kind)
        return _read(e["file"]) if e else []
    if ids is not None:
        ip2 = root / "ids.json"
        m = json.loads(ip2.read_text(encoding="utf-8")) if ip2.exists() else {}
        shards = {m[i] for i in ids if i in m}
        out = []
        for sh in shards:
            for n in _read("by-section/%s.json" % sh):
                if str(n.get("id")) in ids:
                    out.append(n)
        return out
    return []

# ============================================================
# 可执行契约（机制，不是纪律）
# ============================================================

class NotShardable(ValueError):
    """该语料包不具备分片条件——调用方必须改用全读。"""


def assert_shardable(corpus_dir, *, min_sections: int = 5, max_unassigned: float = 0.3) -> dict:
    """断言该语料包可分片。不满足即 raise NotShardable（退出码非 0）。

    判据（确定性，可 CI 回归）：
      ① 索引存在
      ② section 数 >= min_sections
      ③ section 为 "§?" 的节点占比 <= max_unassigned

    **为什么要这个**：轻量产物（从客户材料抽的）没有章节归属，
      section 全是 "§?"，分片对它无效。误用会拿到空结果却"看起来成功"。

    用法：
        from corpus_pipeline.shard_index import assert_shardable, NotShardable
        try:
            assert_shardable(corpus)
        except NotShardable as e:
            # 明确降级为全读
            nodes = fastload.load(corpus / "graph" / "nodes.yaml")
    """
    root = Path(corpus_dir)
    ip = root / SHARD_DIR / "index.json"
    if not ip.exists():
        raise NotShardable("索引不存在：先跑 shard_index.build(%r)" % str(root))

    idx = json.loads(ip.read_text(encoding="utf-8"))
    secs = idx.get("by-section") or {}
    total = int((idx.get("counts") or {}).get("nodes") or 0)
    unassigned = int((secs.get("§?") or {}).get("count") or 0)
    ratio = (unassigned / total) if total else 1.0

    if len([s for s in secs if s != "§?"]) < min_sections:
        raise NotShardable(
            "有效 section 只有 %d 个（需 >= %d）；该语料包无章节归属，分片无效"
            % (len([s for s in secs if s != "§?"]), min_sections))
    if ratio > max_unassigned:
        raise NotShardable(
            "未归属节点占 %.0f%%（上限 %.0f%%）；分片会漏掉大部分节点"
            % (ratio * 100, max_unassigned * 100))
    return {"sections": len(secs), "unassigned_ratio": round(ratio, 4),
            "nodes": total, "shardable": True}


def resolve_or_full(corpus_dir, *, section=None, domain=None, kind=None,
                    with_relations=False, with_rules=False):
    """能分片就分片，不能就全读并**明确标注降级**。

    返回值统一为 dict：
        {"mode": "shard"|"full_fallback", "nodes": [...], "relations": [...], "rules": [...]}

    **降级必须可见**——这是与 assert_shardable 的分工：
      assert_shardable 用于"我要分片，不行就报错"
      resolve_or_full  用于"尽量分片，不行就降级但要告诉我"
    """
    out = {"mode": "shard", "nodes": [], "relations": [], "rules": []}
    try:
        assert_shardable(corpus_dir)
    except NotShardable as e:
        out["mode"] = "full_fallback"
        out["fallback_reason"] = str(e)
        nodes = _load_yaml(Path(corpus_dir) / "graph" / "nodes.yaml") or []
        out["nodes"] = [n for n in nodes if isinstance(n, dict)]
        if with_relations:
            out["relations"] = _load_yaml(Path(corpus_dir) / "graph" / "relations.yaml") or []
        if with_rules:
            out["rules"] = _load_yaml(Path(corpus_dir) / "graph" / "rules.yaml") or []
        return out

    r = resolve(corpus_dir, section=section, domain=domain, kind=kind,
                with_relations=with_relations, with_rules=with_rules)
    if isinstance(r, dict):
        out["nodes"] = r.get("nodes") or []
        out["relations"] = r.get("relations") or []
        out["rules"] = r.get("rules") or []
    else:
        out["nodes"] = r or []
    return out

# ============================================================
# 不依赖章节的分片键（对无章节文档同样有效）
# ============================================================

def _norm_label(s: str) -> str:
    import re
    return re.sub(r"\s+", "", str(s or ""))


def build_inverted(corpus_dir) -> dict:
    """建**倒排索引**：把「查询时用的键」映射到节点 id 列表。

    不依赖 section，所以对客户材料（无章节）同样有效。

    倒排维度：
        label_prefix  按名字首字（1 字 + 2 字）
        unit          按单位
        kind          按类型
        rule          按产出它的规则
        dep_of        按「它依赖谁」的反向（谁用了它）
        magnitude     按量级（小额/万元级/十万级/百万级）

    写入 shards/inverted.json。
    """
    root = Path(corpus_dir)
    nodes = _load_yaml(root / "graph" / "nodes.yaml") or []
    rules = _load_yaml(root / "graph" / "rules.yaml") or []
    sroot = root / SHARD_DIR
    sroot.mkdir(parents=True, exist_ok=True)

    inv = {k: {} for k in ("label_prefix", "unit", "kind", "rule", "dep_of", "magnitude")}
    node_by_id = {}

    def _add(dim, key, nid):
        k = str(key or "").strip()
        if not k:
            return
        inv[dim].setdefault(k, [])
        if nid not in inv[dim][k]:
            inv[dim][k].append(nid)

    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "")
        if not nid:
            continue
        node_by_id[nid] = n
        lab = _norm_label(n.get("label"))
        # 名字首 1 字与 2 字
        if lab:
            _add("label_prefix", lab[0], nid)
            if len(lab) >= 2:
                _add("label_prefix", lab[:2], nid)
        _add("unit", n.get("unit"), nid)
        _add("kind", n.get("kind"), nid)
        _add("rule", n.get("rule"), nid)
        # 量级（仅数值）
        v = n.get("value")
        try:
            f = abs(float(v))
        except (TypeError, ValueError):
            f = None
        if f is not None:
            mag = ("<1" if f < 1 else "1-100" if f < 100 else "100-1e4" if f < 1e4
                   else "1e4-1e6" if f < 1e6 else ">=1e6")
            _add("magnitude", mag, nid)
        # 依赖：该节点被哪些规则当输入 → 反向索引
        for r in rules:
            if not isinstance(r, dict):
                continue
            deps = [str(d) for d in (r.get("deps") or [])]
            if str(n.get("label")) in deps or nid in deps:
                _add("dep_of", str(r.get("id")), nid)

    _dump(sroot / "inverted.json", inv)
    return {k: len(v) for k, v in inv.items()}


def browse_inverted(corpus_dir) -> dict:
    """看倒排索引有哪些键（毫秒级）。"""
    p = Path(corpus_dir) / SHARD_DIR / "inverted.json"
    if not p.exists():
        return {"error": "倒排索引不存在，先跑 build_inverted()"}
    inv = json.loads(p.read_text(encoding="utf-8"))
    return {dim: {"keys": len(m), "sample": sorted(m)[:8]} for dim, m in inv.items()}


def query(corpus_dir, *, unit=None, label_prefix=None, kind=None, rule=None,
          dep_of=None, magnitude=None, limit=200) -> list:
    """按倒排键查询节点（不依赖章节）。多键取交集。"""
    root = Path(corpus_dir)
    p = root / SHARD_DIR / "inverted.json"
    if not p.exists():
        return []
    inv = json.loads(p.read_text(encoding="utf-8"))
    sets = []
    for dim, val in (("unit", unit), ("label_prefix", label_prefix), ("kind", kind),
                     ("rule", rule), ("dep_of", dep_of), ("magnitude", magnitude)):
        if val is None:
            continue
        ids = set((inv.get(dim) or {}).get(str(val)) or [])
        sets.append(ids)
    if not sets:
        return []
    hit = set.intersection(*sets) if len(sets) > 1 else sets[0]
    nodes = _load_yaml(root / "graph" / "nodes.yaml") or []
    by_id = {str(n.get("id")): n for n in nodes if isinstance(n, dict)}
    return [by_id[i] for i in list(hit)[:limit] if i in by_id]


def resolve_closure(corpus_dir, rule_id: str, *, direction: str = "upstream",
                    max_depth: int = 6) -> dict:
    """沿规则依赖取**闭包**——不依赖章节，按推理链取数。

    direction='upstream'   取该规则直接与间接依赖的事实（写作时要引用的上游）
    direction='downstream' 取该规则产出的、以及用它的下游

    返回 {"rule": rule_id, "nodes": [...], "edges": [...], "depth": n}
    """
    root = Path(corpus_dir)
    nodes = _load_yaml(root / "graph" / "nodes.yaml") or []
    rules = _load_yaml(root / "graph" / "rules.yaml") or []
    rels = _load_yaml(root / "graph" / "relations.yaml") or []
    by_label = {str(n.get("label")): n for n in nodes if isinstance(n, dict)}
    by_id = {str(n.get("id")): n for n in nodes if isinstance(n, dict)}
    rule_by_id = {str(r.get("id")): r for r in rules if isinstance(r, dict)}

    seen_nodes, seen_edges = {}, []
    frontier = [rule_id]
    depth = 0
    while frontier and depth < max_depth:
        depth += 1
        nxt = []
        for rid in frontier:
            r = rule_by_id.get(rid)
            if not r:
                continue
            deps = [str(d) for d in (r.get("deps") or [])]
            for d in deps:
                # deps 可能是「P-xxxx」节点 id（instantiate 已解析），也可能是事实名
                n = by_id.get(d) if d.startswith("P-") else by_label.get(d)
                if n and str(n.get("id")) not in seen_nodes:
                    seen_nodes[str(n.get("id"))] = n
                    lab = str(n.get("label"))
                    if lab:
                        nxt.append(lab)
            # 关系侧也要
            for rel in rels:
                if not isinstance(rel, dict):
                    continue
                if str(rel.get("payload", {}).get("rule_id")) == rid:
                    for side in ("from", "to"):
                        nid = str(rel.get(side))
                        if nid in by_id and nid not in seen_nodes:
                            seen_nodes[nid] = by_id[nid]
                    seen_edges.append(rel)
        frontier = nxt
    return {"rule": rule_id, "nodes": list(seen_nodes.values()),
            "edges": seen_edges, "depth": depth, "direction": direction}
