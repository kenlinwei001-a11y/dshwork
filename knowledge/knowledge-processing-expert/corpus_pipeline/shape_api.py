# -*- coding: utf-8 -*-
"""shape_api —— 形包的 MCP 消费接口（3 个工具）。

## 为什么

形包有 32 个文件，agent 不该逐个读。只需 3 个动作：

    browse_shape(pkg)                                知道有什么
    resolve_shape(pkg, asset, key=None)              按需取一个资产（可过滤）
    build_section_prompt(pkg, graph, section, tags)  直接产出某节提示词

**agent 不需要读 manifest.json、不需要知道 assets/ 结构、不需要读任何 json。**

## 设计原则

- **零 LLM**：纯 JSON 读取 + 过滤 + 拼装
- **不加载不需要的**：resolve 只读指定的那一个 asset 文件
- **降级可见**：取不到就明确报错，不返回空
"""
from __future__ import annotations
import json
from pathlib import Path

# 资产别名 → 文件（防 agent 记不住文件名）
ASSETS = {
    "skeleton": "skeleton.json", "rules": "rules.json",
    "prompt_template": "prompt_template.json", "section_guides": "section_guides.json",
    "fact_sources": "fact_sources.json", "fact_roles": "fact_roles.json",
    "fact_aliases": "fact_aliases.json", "standard_db": "standard_db.json",
    "standards": "standards.json", "gate_registry": "gate_registry.json",
    "quality_gates": "quality_gates.json", "causality": "causality.json",
    "constraints": "constraints.json", "known_defects": "known_defects.json",
    "node_kinds": "node_kinds.json", "relation_types": "relation_types.json",
    "claim_patterns": "claim_patterns.json", "reasoning_patterns": "reasoning_patterns.json",
    "limit_refs": "limit_refs.json", "domains": "domains.json",
    "reference_contract": "reference_contract.json", "source_types": "source_types.json",
}


def _pkg(pkg_path) -> Path:
    p = Path(pkg_path)
    # 允许传 zip 所在目录或包目录或 zip 本身
    if p.is_file() and p.suffix == ".zip":
        return p.parent / p.stem
    if (p / "manifest.json").exists():
        return p
    for cand in p.glob("形-agent-*"):
        if (cand / "manifest.json").exists():
            return cand
    raise FileNotFoundError("找不到形包（需含 manifest.json）：%s" % pkg_path)


def browse_shape(pkg_path) -> dict:
    """知道形包有什么。返回 manifest 摘要 + 可用 asset 别名列表。"""
    root = _pkg(pkg_path)
    mf = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return {
        "package": mf.get("package_id"), "version": mf.get("version"),
        "purpose": mf.get("purpose"),
        "hard_invariants": mf.get("hard_invariants"),
        "key_assets": {k: {"what": v.get("what"), "lookup": v.get("lookup"),
                           "use": v.get("use")}
                       for k, v in (mf.get("key_assets") or {}).items()},
        "stats": mf.get("stats"),
        "dont_load": mf.get("dont_load"),
        "contracts": mf.get("contracts"),
        "available_assets": sorted(set(ASSETS) & {f.stem for f in (root/"assets").glob("*.json")}),
        "_hint": "用 resolve_shape(pkg, asset, key) 取具体资产；asset 取 available_assets 里的值",
    }


def resolve_shape(pkg_path, asset: str, key: str | None = None,
                  limit: int = 50) -> dict:
    """按需取一个资产。key 支持点号路径（如 'rules.R-总投资构成'）。"""
    root = _pkg(pkg_path)
    fn = ASSETS.get(asset) or (asset if asset.endswith(".json") else None)
    if not fn:
        return {"error": "未知 asset: %r" % asset,
                "available": sorted(ASSETS)}
    fp = root / "assets" / fn
    if not fp.exists():
        return {"error": "资产文件不存在: %s" % fn}
    data = json.loads(fp.read_text(encoding="utf-8"))

    if not key:
        # 未给 key：返回顶层键 + 大小，避免整包吐出
        if isinstance(data, dict):
            return {"asset": asset, "file": fn,
                    "top_keys": list(data)[:30],
                    "size": fp.stat().st_size,
                    "_hint": "用 key 指定要取的部分，如 key='rules.R-总投资构成'"}
        return {"asset": asset, "file": fn, "type": "list", "len": len(data),
                "first": data[:2], "size": fp.stat().st_size}

    cur = data
    for seg in str(key).split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        elif isinstance(cur, list):
            try:
                cur = cur[int(seg)]
            except (ValueError, IndexError):
                return {"error": "key 路径在 list 处失败: %r" % seg}
        else:
            return {"error": "key 路径不存在: %r（在 %r 处断）" % (key, seg)}
    if isinstance(cur, list) and len(cur) > limit:
        return {"asset": asset, "key": key, "len": len(cur), "items": cur[:limit],
                "_truncated": "共 %d 条，只返回前 %d 条" % (len(cur), limit)}
    return {"asset": asset, "key": key, "value": cur}


def build_section_prompt(pkg_path, graph_path, section: str,
                         tags: list | None = None, title: str = "",
                         path: str = "", level: int = 2) -> dict:
    """直接产出某节写作提示词（内部调 section_prompt_builder，不可用则手工拼）。"""
    root = _pkg(pkg_path)
    gp = Path(graph_path)
    if not gp.exists():
        return {"error": "graph 不存在: %s" % graph_path}
    graph = json.loads(gp.read_text(encoding="utf-8"))

    # 优先用 builder
    try:
        from corpus_pipeline.section_prompt_builder import build_prompt
        r = build_prompt(graph, section=section, title=title, path=path,
                         level=level, tags=tags)
        r["_mode"] = "builder"
        return r
    except Exception as e:
        # 降级：手工按模板拼
        tpl = json.loads((root / "assets" / "prompt_template.json").read_text(encoding="utf-8"))
        facts = [f for f in (graph.get("items", {}).get("facts") or [])
                 if str(f.get("section") or "").lstrip("§") == str(section).lstrip("§")]
        lines = [
            "MANUAL_ASSEMBLY（未经 build_prompt 校验，原因：%s）" % type(e).__name__,
            "依据脱敏骨架撰写《%s》一节（%s，层级 %d）。" % (title or "§" + section, path or "", level),
            "本项目标签：%s" % " · ".join(tags or ["科研", "可研", "中型"]),
            "本节须覆盖 %d 条事实节点：" % len(facts),
        ]
        for f in facts[:40]:
            lines.append("  · %s = %s %s ｜ %s〔%s〕" % (f.get("subject"), f.get("value"),
                         f.get("unit") or "", f.get("section"), f.get("id")))
        lines.append("返回：正文 Markdown（数值写〔节点ID〕引用）＋ node_mentions ＋ new_claims ＋ unresolved。")
        return {"prompt": "\n".join(lines), "facts": facts, "stats": {"facts": len(facts)},
                "_mode": "manual_fallback", "_reason": str(e)[:120],
                "_template_sections": len((tpl.get("prompt_template") or {}).get("sections") or [])}
