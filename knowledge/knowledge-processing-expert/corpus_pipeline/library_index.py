# -*- coding: utf-8 -*-
"""library_index —— 基于 INDEX.yaml + 别名 的包检索（补 search_packages 不做同义词扩展的短板）。

用法：
  from corpus_pipeline.library_index import search
  search("可研")           → 命中所有 doc_type 含可研/可行性的包
  search("新材料")         → 命中 industry=新材料 的包
"""
from __future__ import annotations
import yaml
from pathlib import Path

DEFAULT_LIBRARY = Path(__file__).resolve().parent.parent / "corpus-library"


def _load(library_root=None):
    root = Path(library_root or DEFAULT_LIBRARY)
    p = root / "INDEX.yaml"
    if not p.exists():
        return None, root
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}, root


def search(query: str = "", library_root=None, include_draft: bool = False) -> list:
    """按 索引别名 + 标题 + 领域 检索已发布包。"""
    idx, root = _load(library_root)
    if idx is None:
        return []
    q = (query or "").strip().lower()
    out = []
    for pk in idx.get("packages") or []:
        if not include_draft and pk.get("status") != "published":
            continue
        hay = " ".join([
            str(pk.get("title") or ""),
            str(pk.get("doc_type") or ""),
            str(pk.get("industry") or ""),
            " ".join(pk.get("aliases") or []),
        ]).lower()
        if not q or q in hay:
            out.append(pk)
    return out


def get(package_id: str, library_root=None) -> dict:
    idx, _ = _load(library_root)
    for pk in (idx or {}).get("packages") or []:
        if package_id in (pk.get("id"), pk.get("dir")):
            return pk
    return {}


def stats(library_root=None) -> dict:
    idx, _ = _load(library_root)
    return (idx or {}).get("stats") or {}
