# -*- coding: utf-8 -*-
"""P0 状态机验证（候选 → 正式资产）。

覆盖：promote_status 单向推进/禁止回退/禁止跳级；list_packages 默认只 published；发布流程。

运行：.venv/bin/python corpus_pipeline/test_review.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.review import (
    promote_status, is_published, get_package_status, promote_package, publish_package,
)
from corpus_pipeline.library import list_packages, DEFAULT_LIBRARY


def test_promote_status_forward():
    assert promote_status({"status": "draft"}, "validated")["ok"] is True
    assert promote_status({"status": "validated"}, "published")["ok"] is True
    assert promote_status({}, "validated")["ok"] is True  # 缺省 draft
    print("[OK] 单向推进：draft → validated → published")


def test_promote_status_reject():
    # 禁止回退
    assert promote_status({"status": "published"}, "draft")["ok"] is False
    assert promote_status({"status": "validated"}, "draft")["ok"] is False
    # 禁止跳级（draft 不能直接 published）
    r = promote_status({"status": "draft"}, "published")
    assert r["ok"] is False and "validated" in r["reason"]
    # 非法状态
    assert promote_status({"status": "draft"}, "bogus")["ok"] is False
    print("[OK] 拒绝回退/跳级/非法状态")


def test_list_packages_default_published():
    pkgs = list_packages()  # 默认只 published
    names = {p["name"] for p in pkgs}
    assert "PX-2026-001-feasibility" in names  # demo 已发布
    assert all(p["status"] == "published" for p in pkgs)
    print(f"[OK] list_packages 默认只返回 published（{len(pkgs)} 个，demo 在内）")


def test_draft_filtered_until_published():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "draft-pkg"
        d.mkdir()
        (d / "manifest.yaml").write_text(json.dumps({"corpus_id": "T-001", "status": "draft"}), encoding="utf-8")
        (d / "meta.yaml").write_text(json.dumps({"title": "草稿包"}), encoding="utf-8")

        lib = tmp
        # 默认不可见（装配侧读不到草稿）
        assert "draft-pkg" not in {p["name"] for p in list_packages(lib)}
        # include_draft 可见
        assert "draft-pkg" in {p["name"] for p in list_packages(lib, include_draft=True)}

        # 发布流程：draft → validated → published
        r1 = promote_package(lib, "draft-pkg", "validated")
        assert r1["ok"]
        assert get_package_status(lib, "draft-pkg")["status"] == "validated"
        r2 = publish_package(lib, "draft-pkg")
        assert r2["ok"]
        assert get_package_status(lib, "draft-pkg")["status"] == "published"
        # 发布后默认可见
        assert "draft-pkg" in {p["name"] for p in list_packages(lib)}
    print("[OK] 草稿默认不可见 → 发布后装配侧可见")


def test_default_library_path():
    # DEFAULT_LIBRARY 用相对路径，收进子目录后仍正确
    assert Path(DEFAULT_LIBRARY).exists()
    assert (Path(DEFAULT_LIBRARY) / "PX-2026-001-feasibility" / "manifest.yaml").exists()
    print(f"[OK] DEFAULT_LIBRARY 相对路径正确：{DEFAULT_LIBRARY}")


def main() -> int:
    test_promote_status_forward()
    test_promote_status_reject()
    test_list_packages_default_published()
    test_draft_filtered_until_published()
    test_default_library_path()
    print("\nP0 状态机验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
