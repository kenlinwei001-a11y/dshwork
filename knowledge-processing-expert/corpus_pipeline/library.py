"""语料资产库：跨语料包检索与复用，支撑「写新项目时调用之前资产」的场景。

语料库目录结构：每个子目录是一个完整语料包（七道工序产出）。
工具能力：列出语料包 / 关键词检索 / 取指定资产 / 找最相似语料包（类比）。
"""
from __future__ import annotations
import json
from pathlib import Path

DEFAULT_LIBRARY = "/Users/apple/Desktop/workdsh/knowledge-processing-expert/corpus-library"

# 可取的资产类型 → 文件映射
ASSETS = {
    "meta": "meta.yaml",
    "outline": "outline.yaml",
    "templates": "style/section_templates",
    "style": "style/style_profile.yaml",
    "terms": "index/term_index.json",
    "claims": "graph/claims.yaml",
    "nodes": "graph/nodes.yaml",
    "rules": "graph/rules.yaml",
    "skeleton": "chunks/skeletons.jsonl",
    "evidence": "evidence/evidence.yaml",
    "manifest": "manifest.yaml",
    "reuse": "reuse/domains.yaml",
}


def _read_data(p: Path):
    """读取 JSON 或 YAML 文件并返回解析后的对象；文件缺失返回 None，解析失败回退为原文。

    语料包契约（spec.py）中 meta.yaml / outline.yaml / style_profile.yaml / rules.yaml 等
    为 YAML，而 index/term_index.json 为 JSON，故统一按「先 JSON 后 YAML」解析。
    """
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except (ValueError, json.JSONDecodeError):
        try:
            import yaml  # 懒加载，保持无强依赖
            return yaml.safe_load(text)
        except Exception:
            return text


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def list_packages(library_root: str = DEFAULT_LIBRARY) -> list[dict]:
    """列出语料库中所有语料包（名称/标题/类型/规模）。"""
    root = Path(library_root)
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not (d / "manifest.yaml").exists():
            continue
        meta = _read_data(d / "meta.yaml") or {}
        out.append({
            "name": d.name,
            "title": meta.get("title", d.name),
            "doc_type": meta.get("doc_type"),
            "data_cutoff": meta.get("data_cutoff"),
            "source_sha": meta.get("source_sha"),
            "files": len(list(d.rglob("*"))),
        })
    return out


def search_packages(library_root: str = DEFAULT_LIBRARY, query: str = "") -> list[dict]:
    """按关键词检索语料包（标题/术语/章节匹配），返回匹配片段。"""
    root = Path(library_root)
    q = (query or "").strip().lower()
    hits = []
    if not root.exists():
        return hits
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        meta = _read_data(d / "meta.yaml") or {}
        title = str(meta.get("title", "")).lower()
        terms = _read_data(d / "index" / "term_index.json") or []
        term_surfaces = " ".join(str(t.get("surface", "")) for t in terms).lower()
        outline = _read_data(d / "outline.yaml") or {}
        sections = " ".join(str(s.get("title", "")) for s in outline.get("sections", [])).lower()
        haystack = f"{title} {term_surfaces} {sections}"
        if not q or q in haystack:
            matched_terms = [t.get("surface") for t in terms if q and q in str(t.get("surface", "")).lower()][:10]
            matched_sections = [s.get("title") for s in outline.get("sections", []) if q and q in str(s.get("title", "")).lower()][:10]
            hits.append({
                "name": d.name,
                "title": meta.get("title"),
                "doc_type": meta.get("doc_type"),
                "matched_terms": matched_terms,
                "matched_sections": matched_sections,
            })
    return hits


def get_asset(library_root: str = DEFAULT_LIBRARY, package: str = "", asset: str = "outline") -> dict:
    """取某个语料包的指定资产（outline/templates/style/terms/claims/nodes/rules/skeleton/evidence/meta）。"""
    root = Path(library_root)
    pkg = root / package
    if not pkg.is_dir():
        return {"error": f"语料包 {package} 不存在"}
    if asset not in ASSETS:
        return {"error": f"未知资产类型 {asset}，可选：{list(ASSETS)}"}
    rel = ASSETS[asset]
    p = pkg / rel
    if asset == "templates":
        if not p.is_dir():
            return {"error": "无节模板"}
        return {"package": package, "asset": asset, "templates": {f.stem: _read_text(f) for f in sorted(p.glob("*.yaml"))}}
    if asset == "skeleton":
        lines = [json.loads(l) for l in _read_text(p).splitlines() if l.strip()]
        return {"package": package, "asset": asset, "count": len(lines), "items": lines[:10]}
    return {"package": package, "asset": asset, "content": _read_data(p)}


def find_analog(library_root: str = DEFAULT_LIBRARY, doc_type: str = "", query: str = "") -> dict:
    """找最相似的语料包（doc_type 优先匹配，再按关键词命中数排序），供新项目写作复用。"""
    pkgs = list_packages(library_root)
    if not pkgs:
        return {"error": "语料库为空"}
    scored = []
    for p in pkgs:
        score = 0
        if doc_type and p.get("doc_type") == doc_type:
            score += 100
        if query:
            hits = search_packages(library_root, query)
            for h in hits:
                if h["name"] == p["name"]:
                    score += len(h["matched_terms"]) * 3 + len(h["matched_sections"]) * 5
        scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    best = scored[0]
    return {"best": best[1]["name"], "title": best[1]["title"], "doc_type": best[1]["doc_type"], "score": best[0],
            "suggested_assets": ["outline", "templates", "style", "terms", "claims"]}
