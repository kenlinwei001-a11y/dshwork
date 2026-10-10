# -*- coding: utf-8 -*-
"""知识处理侧 P2：跨文档实体注册表 + SourceAnchor 精细化。

对齐文档：
  SourceAnchor 必须保留 page/section_path/block_id/char_start/char_end/table_cell，
  才能支持证据级溯源；
  K6 实体消歧要有跨文档 EntityRegistry，统一同一实体在不同文档的 mention。
"""
from __future__ import annotations

# SourceAnchor 完整字段（含 table_cell，对齐文档 K1 的定位契约）
SOURCE_ANCHOR_FIELDS = ("document_id", "page", "section_path", "block_id",
                        "char_start", "char_end", "table_cell")


def validate_source_anchor(anchor: dict) -> dict:
    """校验 SourceAnchor 是否足以支撑证据级溯源。

    最低要求：document_id 必填 + 至少一个精确定位（char span 或 table_cell）。
    返回 {ok, missing, has_precise_loc}。
    """
    anchor = anchor or {}
    missing = [f for f in ("document_id",) if not anchor.get(f)]
    precise = bool(anchor.get("char_start") is not None or anchor.get("table_cell"))
    return {"ok": not missing, "missing": missing, "has_precise_loc": precise}


class EntityRegistry:
    """跨文档实体注册表：canonical → aliases → mentions（跨文档统一同一实体）。"""

    def __init__(self):
        self._entities: dict = {}   # entity_id → {canonical, aliases, mentions}

    def register(self, entity_id: str, canonical: str, aliases: list[str] | None = None) -> dict:
        if entity_id in self._entities:
            return {"ok": False, "reason": f"实体 {entity_id} 已注册"}
        self._entities[entity_id] = {
            "entity_id": entity_id, "canonical": canonical,
            "aliases": list(aliases or []), "mentions": [],
        }
        return {"ok": True, "entity_id": entity_id}

    def add_mention(self, entity_id: str, surface: str, document_id: str, anchor: dict | None = None) -> dict:
        """登记一个 mention（某文档里出现的该实体），锚定 SourceAnchor。"""
        if entity_id not in self._entities:
            return {"ok": False, "reason": f"实体 {entity_id} 未注册"}
        self._entities[entity_id]["mentions"].append(
            {"surface": surface, "document_id": document_id, "anchor": anchor or {}}
        )
        return {"ok": True}

    def resolve(self, surface: str) -> dict:
        """解析：输入 surface → 命中实体（canonical 或 alias 匹配）。"""
        hits = []
        for eid, e in self._entities.items():
            if surface == e["canonical"] or surface in e["aliases"]:
                hits.append(eid)
        if not hits:
            return {"resolved": False, "surface": surface}
        if len(hits) > 1:
            return {"resolved": False, "surface": surface, "ambiguous": True,
                    "candidates": hits, "reason": "同一 surface 命中多个实体，需消歧"}
        return {"resolved": True, "surface": surface, "entity_id": hits[0]}

    def ambiguous_surfaces(self) -> list[str]:
        """列出所有跨文档歧义 surface（同一名字命中多个实体）。"""
        from collections import defaultdict
        by_surface = defaultdict(list)
        for eid, e in self._entities.items():
            for s in [e["canonical"], *e["aliases"]]:
                by_surface[s].append(eid)
        return sorted(s for s, ids in by_surface.items() if len(ids) > 1)

    def list_entities(self) -> list[dict]:
        return [dict(e) for e in self._entities.values()]
