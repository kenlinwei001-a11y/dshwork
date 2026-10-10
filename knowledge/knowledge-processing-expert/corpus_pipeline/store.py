"""语料包存储适配器 + manifest 生成 + Agent 访问工具（②）。

生产拓扑是「对象存储 + PG + 图库 + 向量库 + 事件流」；
本模块用文件系统统一背书（对象存储=文件，PG/图库/向量库=索引文件），
让 Agent 访问工具（②）在本机即可运行，接口与生产拓扑一一对应。
"""
from __future__ import annotations
import json
from pathlib import Path

from .spec import MANIFEST
from .backends import make_backends


class CorpusStore:
    """统一存储门面：对象存储 + PG + 图库 + 向量库（缺省回退文件系统）。"""

    def __init__(self, corpus_dir: str | Path):
        self.root = Path(corpus_dir)
        self.backends = make_backends(self.root)

    def object(self): return self.backends["object"]

    def pg(self): return self.backends.get("pg")

    def neo4j(self): return self.backends.get("neo4j")

    def qdrant(self): return self.backends.get("qdrant")

    def persist(self, graph: dict, meta: dict | None = None) -> dict:
        """把图谱/元数据落到真实后端（可用时），对象存储永远落盘。"""
        obj = self.object()
        obj.write("graph/graph.yaml", json.dumps(graph, ensure_ascii=False, indent=2))
        status = {"object": True, "pg": False, "neo4j": False, "qdrant": False}
        neo4j = self.neo4j()
        if neo4j:
            try:
                neo4j.upsert_nodes("Node", graph.get("facts", []), "id")
                neo4j.upsert_nodes("Claim", graph.get("claims", []), "id")
                neo4j.upsert_nodes("Rule", graph.get("rules", []), "id")
                neo4j.upsert_relations(graph.get("relations", []))
                status["neo4j"] = True
            except Exception as e:  # noqa: BLE001
                status["neo4j_error"] = str(e)
        pg = self.pg()
        if pg and meta:
            try:
                pg.upsert("corpus_meta", [meta])
                status["pg"] = True
            except Exception as e:  # noqa: BLE001
                status["pg_error"] = str(e)
        return status


def emit_manifest(corpus_dir: str | Path, corpus_id: str = "", version: str = "V1.0",
                  source_fingerprint: str = "", constraints: list[str] | None = None) -> Path:
    """生成 manifest.yaml（产物 #1）。

    对齐推演写作侧（instantiate_project）消费：JSON 对象含
    corpus_id / version / source_fingerprint / constraints，外加 30 条产物 files 清单。
    """
    d = Path(corpus_dir)
    d.mkdir(parents=True, exist_ok=True)
    manifest = {
        "corpus_id": corpus_id,
        "version": version,
        "status": "draft",   # P0：候选状态机，默认草稿；经 validated 后 publish 才可被装配侧复用
        "source_fingerprint": source_fingerprint,
        "constraints": constraints or [
            "借形不借值：数值/单位/实体名/结论一律不继承，仅继承结构/规则/句式/术语",
            "缺值守卫：依赖缺失节点 status=undefined，正文写「待…后测算」并挂 gap",
            "冲突待审：回放检出数字不一致一律待审，不自动裁决",
            "不许反算：不得由结论倒推中间量",
        ],
        "files": [
            {"name": m["name"], "stage": m["stage"], "format": m["fmt"], "primary": m["primary"], "agent": m["agent"]}
            for m in MANIFEST
        ],
    }
    p = d / "manifest.yaml"
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _load_json(corpus_dir: str | Path, rel: str):
    p = Path(corpus_dir) / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_yaml_lines(corpus_dir: str | Path, rel: str) -> str:
    p = Path(corpus_dir) / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


# --------------------------------------------------------------------------- #
# Agent 访问工具（②）—— 文件系统背书
# --------------------------------------------------------------------------- #
def corpus_get_chunk(corpus_dir, chunk_id=None, limit=20):
    """从 skeletons.jsonl 取脱敏 chunk（写作 Agent 只拿这个）。"""
    p = Path(corpus_dir) / "chunks" / "skeletons.jsonl"
    if not p.exists():
        return {"error": "skeletons.jsonl 不存在（先跑七道工序）"}
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        if chunk_id is None or c["id"] == chunk_id:
            out.append(c)
    return out[:limit] if chunk_id is None else (out[0] if out else {"error": f"chunk {chunk_id} 不存在"})


def corpus_get_skeleton(corpus_dir, section=None):
    """从 section_templates 取节模板。"""
    d = Path(corpus_dir) / "style" / "section_templates"
    if not d.exists():
        return {"error": "section_templates 不存在"}
    if section:
        p = d / f"{section}.yaml"
        return {"section": section, "content": p.read_text(encoding="utf-8")} if p.exists() else {"error": f"模板 {section} 不存在"}
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(d.glob("*.yaml"))}


def corpus_where_used(corpus_dir, node_id):
    """从 node_index 查节点被哪些 chunk 使用。"""
    idx = _load_json(corpus_dir, "index/node_index.json")
    for entry in (idx if isinstance(idx, list) else []):
        if entry.get("node") == node_id:
            return entry
    # 兼容 dict 结构
    if isinstance(idx, dict):
        return idx.get(node_id, {"error": f"节点 {node_id} 未被引用"})
    return {"error": f"节点 {node_id} 未被引用"}


def graph_get_node(corpus_dir, node_id):
    """从 nodes.yaml 取节点。"""
    txt = _load_yaml_lines(corpus_dir, "graph/nodes.yaml")
    return {"node_id": node_id, "found": node_id in txt, "graph_nodes": txt[:2000]}


def graph_query(corpus_dir, filter_text=""):
    txt = _load_yaml_lines(corpus_dir, "graph/nodes.yaml")
    return {"filter": filter_text, "nodes": txt[:2000]}


def graph_explain(corpus_dir, rule_id=None):
    return {"rule": rule_id, "rules": _load_yaml_lines(corpus_dir, "graph/rules.yaml")[:2000],
            "derivation": _load_yaml_lines(corpus_dir, "reasoning/derivation.yaml")[:2000]}


def graph_impact(corpus_dir, node_id):
    txt = _load_yaml_lines(corpus_dir, "graph/relations.yaml")
    return {"node": node_id, "relations": txt[:2000]}


def graph_why(corpus_dir, decision_id=None):
    return {"decision": decision_id, "decisions": _load_yaml_lines(corpus_dir, "reasoning/decisions.yaml")[:2000]}


def gate_check(corpus_dir):
    return {"invariants": _load_yaml_lines(corpus_dir, "graph/invariants.yaml")[:1000],
            "gate_report": _load_yaml_lines(corpus_dir, "quality/gate_report.yaml")[:1000]}


def evidence_get(corpus_dir, claim_id=None, with_excerpt=False):
    e = _load_yaml_lines(corpus_dir, "evidence/evidence.yaml")
    out = {"claim": claim_id, "evidence": e[:2000]}
    if with_excerpt:
        out["excerpts"] = list(Path(corpus_dir).glob("evidence/excerpts/*.md"))[:10]
        out["excerpts"] = [p.name for p in out["excerpts"]]
    return out


# --------------------------------------------------------------------------- #
# v1.3 新增：写作 Agent 契约的三缺工具（corpus_search / project_where_written /
# wp_get_facts）。文件系统背书，接口与 mcp-tools.md 契约一一对应。
# --------------------------------------------------------------------------- #
def corpus_search(corpus_dir, query="", k=5, filters=None):
    """向量检索脱敏 chunk。只返回 skeletons 占位符骨架，永不返回字面数值。"""
    root = Path(corpus_dir)
    pq_path = root / "chunks" / "embeddings.parquet"
    if not pq_path.exists():
        return {"error": "embeddings.parquet 不存在（先跑 embed_chunks）", "isError": True}
    if not query:
        return {"error": "需要 query", "isError": True}

    import math
    import pyarrow.parquet as pq

    table = pq.read_table(pq_path)
    ids = table["id"].to_pylist()
    vectors = table["vector"].to_pylist()

    from .embed import embed_texts, DEFAULT_MODEL
    qv = embed_texts([query], DEFAULT_MODEL)[0]

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0

    sk_by_id = {}
    sp = root / "chunks" / "skeletons.jsonl"
    for line in sp.read_text(encoding="utf-8").splitlines():
        if line:
            c = json.loads(line)
            sk_by_id[c["id"]] = c

    filters = filters or {}
    sec = filters.get("section")
    ind = filters.get("industry")
    meta = {}
    mp = root / "manifest.yaml"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            meta = {}

    corpus_id = meta.get("corpus_id", "")
    if ind and ind != meta.get("industry"):
        return {"query": query, "filters": filters, "results": [],
                "note": "industry 过滤未命中本语料包的行业档位"}

    results = []
    for score, i in sorted(((cosine(qv, v), i) for i, v in enumerate(vectors)), reverse=True):
        cid = ids[i]
        c = sk_by_id.get(cid)
        if not c:
            continue
        if sec and c.get("section") != sec:
            continue
        results.append({
            "chunk_id": cid,
            "corpus_id": corpus_id,                      # 按可用不可见档位由上层掩码
            "title": c.get("section", ""),
            "score": round(float(score), 4),
            "preview": (c.get("skeleton_md") or "")[:120],
        })
        if len(results) >= k:
            break
    return {"query": query, "filters": filters, "results": results}


def project_where_written(corpus_dir, node_id):
    """查节点在本项目已写草稿中的位置（编排器 commit_to_graph 写入）。"""
    p = Path(corpus_dir) / "project" / "drafts" / "node_mentions.jsonl"
    if not p.exists():
        return {"node": node_id, "mentions": [],
                "note": "project/drafts/node_mentions.jsonl 不存在（编排器 commit_to_graph 尚未运行）"}
    mentions = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("node") == node_id:
            mentions.append({"chunk": e.get("chunk"), "para": e.get("para"),
                             "char_span": e.get("char_span")})
    return {"node": node_id, "mentions": mentions}


def wp_get_facts(corpus_dir, work_package_id=None, page=0, page_size=30):
    """工作包 facts 分页：facts>30 时编排器只推前 30 条，其余按页拉取。

    优先读编排器落盘的工作包 project/work_packages/<id>.json；
    未落盘时回退为按 section 过滤图谱事实分页（兼容演示）。"""
    root = Path(corpus_dir)
    page = max(int(page), 0)
    page_size = max(int(page_size), 1)
    wp_path = root / "project" / "work_packages" / f"{work_package_id}.json"
    if work_package_id and wp_path.exists():
        wp = json.loads(wp_path.read_text(encoding="utf-8"))
        facts = wp.get("facts", [])
        total = len(facts)
        pages = (total + page_size - 1) // page_size
        return {"work_package_id": work_package_id, "page": page, "pages": pages,
                "total": total, "facts": facts[page * page_size:(page + 1) * page_size]}

    nodes = _load_json(root, "graph/nodes.yaml")
    if not isinstance(nodes, list):
        nodes = []
    if work_package_id:
        nodes = [n for n in nodes if n.get("section") == work_package_id]
    total = len(nodes)
    pages = (total + page_size - 1) // page_size if total else 0
    return {"work_package_id": work_package_id, "page": page, "pages": pages,
            "total": total, "facts": nodes[page * page_size:(page + 1) * page_size]}
