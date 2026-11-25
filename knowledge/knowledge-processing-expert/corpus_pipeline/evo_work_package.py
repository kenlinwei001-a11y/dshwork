# -*- coding: utf-8 -*-
"""evo_work_package —— 推演写作专家的工作包生成器。

输入：节号 + 形包 + 图谱 + 填槽结果
输出：严格按写作专家契约的 JSON 工作包

    {
      "section", "title",
      "must_cover": [...],
      "word_budget": {"min": ..., "max": ...},
      "skeleton": {"paras", "para_roles", "tables", "style", "source_excerpt"},
      "facts": [{"node_id", "subject", "value", "unit", "status", "origin",
                 "formula", "inputs", ...}],
      "claims": [],
      "conflicts": [...],
      "gaps": [...],
      "skeleton_pointer": "...",
      "return_contract": {...}
    }

纪律：
* ``skeleton.source_excerpt`` 一定是去值后的原文骨架（来自 ⓿b），不是已填值。
* ``facts`` 只给本节相关节点（以 ``_fill-<section>.json`` 的 node_id 为准，
  再补本节骨架段落标签节点、冲突另一侧节点、本节派生节点）。
* ``conflicts`` 只给本节相关冲突，双方保留、不裁决。
* ``gaps`` 从 ``_fill-*.json`` 的 missing_customer / missing_standard 与图谱
  undefined 节点抽取。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # 包内运行
    from .evo_corpus_api import (
        conflict_alternative_facts,
        conflicts_for_section,
        corpus_get_skeleton,
        gaps_for_section,
        graph_query,
        load_graph,
        norm_section,
        project_root,
        section_title,
    )
except Exception:  # 直接脚本运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from corpus_pipeline.evo_corpus_api import (  # type: ignore
        conflict_alternative_facts,
        conflicts_for_section,
        corpus_get_skeleton,
        gaps_for_section,
        graph_query,
        load_graph,
        norm_section,
        project_root,
        section_title,
    )


RETURN_CONTRACT = {
    "draft_md": "Markdown，数值全部为 node 引用（{{node:<node_id>}}），不得写字面量",
    "node_mentions": "node_id + char_span + form；char_span 为 body 中的字符区间",
    "new_claims": "text + supports + evidence；supports 为 node_id 列表",
    "unresolved": "what + why + need_from_client；缺失项不得留空",
}


def build_work_package(
    section: str,
    pack_dir: Optional[Any] = None,
    graph_path: Optional[Any] = None,
    template_path: Optional[Any] = None,
    fill_path: Optional[Any] = None,
    root: Optional[Any] = None,
) -> Dict[str, Any]:
    """生成一节的工作包（写作专家契约）。

    ``pack_dir`` 兼容旧参数；实际形包固定为 ``<root>/形-可复用知识资产-v1.0``。
    ``template_path`` / ``fill_path`` 保留为显式覆盖入口，默认按节号查找。
    """
    root = project_root(root)
    section = norm_section(section)

    skeleton_full = corpus_get_skeleton(section, pkg=pack_dir, root=root)
    title = skeleton_full.get("title") or section_title(section, root)

    gq = graph_query(section, "all", graph=graph_path, root=root)
    facts = gq.get("nodes") or []
    conflicts = conflicts_for_section(section, facts, graph=graph_path, root=root)
    # 已判定相关的冲突，才把另一侧节点补给写作者
    facts = conflict_alternative_facts(facts, conflicts, graph=graph_path, root=root)
    gaps = gaps_for_section(section, facts, graph=graph_path, root=root)

    # 把冲突 id 挂回 facts，写作者能直接看到「这个节点有争议」。
    # 注意：槽位名常带「·数量/·单价/·合价」后缀，必须按基名匹配。
    def _base(s):
        return re.split(r"[·.]", str(s or ""))[0].strip()

    for f in facts:
        fbase = _base(f.get("subject"))
        fslots = {_base(x) for x in (f.get("slot_names") or [])}
        ids = []
        for c in conflicts:
            cid = c.get("conflict_id")
            cbase = _base(c.get("subject"))
            involved = [str(x) for x in (c.get("involved") or [])]
            alt_ids = [str(a.get("node_id")) for a in (c.get("alternatives") or [])]
            if (f.get("node_id") in involved or f.get("node_id") in alt_ids
                    or (cbase and (cbase == fbase or cbase in fslots))):
                ids.append(cid)
        f["conflict_ids"] = list(dict.fromkeys(ids))

    skeleton = {
        "paras": skeleton_full.get("paras", 0),
        "para_roles": skeleton_full.get("para_roles", []),
        "tables": skeleton_full.get("tables", []),
        "style": skeleton_full.get("style", ""),
        "source_excerpt": skeleton_full.get("source_excerpt", []),
        "original_chars": skeleton_full.get("original_chars", 0),
        "form_note": skeleton_full.get("form_note", {}),
    }

    counts = {
        "facts": len(facts),
        "facts_quantity": sum(1 for f in facts if f.get("kind") == "quantity"),
        "facts_text": sum(1 for f in facts if f.get("kind") in ("text", "judgment")),
        "facts_undefined": sum(1 for f in facts if f.get("status") == "undefined"),
        "conflicts": len(conflicts),
        "gaps": len(gaps),
        "gaps_material": sum(1 for x in gaps if x.get("material")),
    }

    return {
        "section": section,
        "title": title,
        "must_cover": skeleton_full.get("must_cover", []),
        "word_budget": skeleton_full.get("word_budget", {"min": 0, "max": 0}),
        "skeleton": skeleton,
        "facts": facts,
        "claims": [],
        "conflicts": conflicts,
        "gaps": gaps,
        "skeleton_pointer": skeleton_full.get("skeleton_pointer", ""),
        "return_contract": dict(RETURN_CONTRACT),
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "root": str(root),
            "counts": counts,
            "graph": str(graph_path or (root / "GRAPH-新项目-华东理工AI研究院-merged.json")),
            "template": str(template_path or (root / "prompt-templates" / (section + ".md"))),
            "fill": str(fill_path or (root / "prompt-filled" / ("_fill-%s.json" % section))),
            "note": "本工作包只交接形与值；正文由推演写作专家独立完成",
        },
    }


def write_work_package(section: str, out_path: Any, **kwargs) -> Dict[str, Any]:
    pkg = build_work_package(section, **kwargs)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    return pkg


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="生成推演写作专家工作包")
    ap.add_argument("--section", required=True, help="节号，如 1.1 / 13.3")
    ap.add_argument("--out", default=None, help="输出 JSON 路径（默认 work-packages/<section>.json）")
    ap.add_argument("--root", default=None, help="项目工作区（含形包/图谱/prompt-filled）")
    ap.add_argument("--graph", default=None)
    ap.add_argument("--template", default=None)
    ap.add_argument("--fill", default=None)
    ap.add_argument("--summary", action="store_true", help="只打印摘要")
    args = ap.parse_args(argv)

    root = project_root(args.root)
    out = Path(args.out) if args.out else (root / "work-packages" / (norm_section(args.section) + ".json"))
    pkg = write_work_package(
        args.section,
        out,
        graph_path=args.graph,
        template_path=args.template,
        fill_path=args.fill,
        root=root,
    )
    summary = {
        "out": str(out),
        "section": pkg["section"],
        "title": pkg["title"],
        "must_cover": len(pkg["must_cover"]),
        "word_budget": pkg["word_budget"],
        "skeleton": {
            "paras": pkg["skeleton"]["paras"],
            "tables": len(pkg["skeleton"]["tables"]),
            "style": pkg["skeleton"]["style"],
        },
        "counts": pkg["meta"]["counts"],
    }
    if args.summary:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(pkg, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
