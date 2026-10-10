"""测试历史项目资产库四个函数 + kp-mcp 的 library_* 工具 dispatch（含 stdio 往返）。

运行：.venv/bin/python corpus_pipeline/test_library.py
"""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline import library as L


def build_fixture(root: Path) -> None:
    """在 root 下造两个语料包（真实 YAML + JSON 混合，验证 _read_data 双格式解析）。"""
    pkg = root / "pkg-alpha"
    (pkg / "index").mkdir(parents=True)
    (pkg / "style" / "section_templates").mkdir(parents=True)
    (pkg / "manifest.yaml").write_text("constraints: []\nstatus: published\n", encoding="utf-8")
    (pkg / "meta.yaml").write_text(
        "title: 高校科研用房可研报告\ndoc_type: 可研报告\ndata_cutoff: 2025-12-31\nsource_sha: abc\n",
        encoding="utf-8",
    )
    (pkg / "outline.yaml").write_text(
        "sections:\n  - title: 建设规模论证\n  - title: 投资估算\n", encoding="utf-8",
    )
    (pkg / "index" / "term_index.json").write_text(
        json.dumps([{"surface": "科研用房"}, {"surface": "人均面积"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (pkg / "style" / "section_templates" / "s1.yaml").write_text("段落顺序: [现状, 论证, 结论]\n", encoding="utf-8")

    pkg2 = root / "pkg-beta"
    (pkg2 / "index").mkdir(parents=True)
    (pkg2 / "manifest.yaml").write_text("constraints: []\nstatus: published\n", encoding="utf-8")
    (pkg2 / "meta.yaml").write_text(
        "title: 物流园区厂房可研\ndoc_type: 可研报告\ndata_cutoff: 2026-01-31\nsource_sha: def\n",
        encoding="utf-8",
    )
    (pkg2 / "outline.yaml").write_text("sections:\n  - title: 总平面布置\n", encoding="utf-8")
    (pkg2 / "index" / "term_index.json").write_text(
        json.dumps([{"surface": "厂房"}, {"surface": "物流"}], ensure_ascii=False), encoding="utf-8",
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_fixture(root)

        # 1) list_packages
        pkgs = L.list_packages(str(root))
        assert len(pkgs) == 2, pkgs
        assert {p["name"] for p in pkgs} == {"pkg-alpha", "pkg-beta"}, pkgs
        assert pkgs[0]["doc_type"] == "可研报告"
        print("[OK] list_packages:", [p["name"] for p in pkgs])

        # 2) search_packages（关键词命中术语与章节标题）
        hits = L.search_packages(str(root), "科研")
        assert any(h["name"] == "pkg-alpha" for h in hits), hits
        alpha = next(h for h in hits if h["name"] == "pkg-alpha")
        assert "科研用房" in alpha["matched_terms"], alpha  # 命中术语
        assert alpha["matched_sections"] == [], alpha  # 「科研」不在章节标题里
        section_hits = L.search_packages(str(root), "建设")
        a2 = next(h for h in section_hits if h["name"] == "pkg-alpha")
        assert "建设规模论证" in a2["matched_sections"], a2  # 命中章节标题
        print("[OK] search_packages 命中术语与章节标题:", alpha["matched_terms"], a2["matched_sections"])

        # 3) get_asset（outline 走 YAML 解析、templates 走目录、terms 走 JSON）
        outline = L.get_asset(str(root), "pkg-alpha", "outline")
        assert len(outline["content"]["sections"]) == 2, outline
        templates = L.get_asset(str(root), "pkg-alpha", "templates")
        assert "s1" in templates["templates"], templates
        terms = L.get_asset(str(root), "pkg-alpha", "terms")
        assert terms["content"][0]["surface"] == "科研用房", terms
        bad = L.get_asset(str(root), "pkg-alpha", "nope")
        assert "error" in bad, bad
        print("[OK] get_asset: outline/templates/terms 均正确解析，未知资产返回 error")

        # 4) find_analog（doc_type 匹配优先 + 关键词排序）
        analog = L.find_analog(str(root), doc_type="可研报告", query="科研")
        assert analog["best"] == "pkg-alpha", analog
        assert "outline" in analog["suggested_assets"], analog
        print("[OK] find_analog 命中:", analog["best"], "score=", analog["score"])

        # 5) MCP dispatch（直接调用 _dispatch）
        from mcp import server as S
        assert S._dispatch("library_list_packages", {"library_root": str(root)}), "list dispatch"
        assert S._dispatch("library_find_analog", {"library_root": str(root), "doc_type": "可研报告", "query": "科研"})
        print("[OK] server._dispatch 四个 library 工具接线正确")

        # 6) stdio 往返（最忠实：真实 MCP 握手 + tools/list + tools/call）
        py = sys.executable
        proc = subprocess.Popen(
            [py, str(Path(__file__).resolve().parent.parent / "mcp" / "server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        def rpc(msg):
            proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            return json.loads(proc.stdout.readline())

        init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {}}})
        assert init["result"]["serverInfo"]["name"] == "kp-mcp", init
        tl = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {t["name"] for t in tl["result"]["tools"]}
        for t in ("library_list_packages", "library_search", "library_get_asset", "library_find_analog"):
            assert t in names, f"{t} 未在 tools/list 中"
        call = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "library_list_packages", "arguments": {"library_root": str(root)}}})
        body = json.loads(call["result"]["content"][0]["text"])
        assert len(body) == 2, body
        proc.terminate()
        print("[OK] stdio 往返：initialize/tools/list/tools/call 全通过，library_* 已在工具清单")

    print("\n全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
