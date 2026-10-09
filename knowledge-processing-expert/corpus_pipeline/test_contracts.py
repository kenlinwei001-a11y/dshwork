# -*- coding: utf-8 -*-
"""数据契约 + 版本固化验证（对齐智演装配引擎第四节/第十节）。

覆盖：操作类型 + base_version、bundle content_hash、乐观锁、3 条关键验收用例。

运行：.venv/bin/python corpus_pipeline/test_contracts.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.contracts import (
    PATCH_OPERATIONS, make_patch, bundle_version, check_base_version, content_hash,
)
from corpus_pipeline.schema_diff import diff_schemas, decide_change_strategy


def test_patch_operations():
    assert len(PATCH_OPERATIONS) == 8
    p = make_patch("rules", "PARAMETERIZE", [{"id": "R1"}], "PX-2026-001@1.0")
    assert p["operation"] == "PARAMETERIZE" and p["base_version"] == "PX-2026-001@1.0"
    # 非法操作类型报错
    try:
        make_patch("rules", "BOGUS", [], "v1")
        assert False, "应拒绝非法操作类型"
    except ValueError:
        pass
    print("[OK] 8 操作类型 + base_version；非法操作类型拒绝")


def test_bundle_content_hash():
    based_on = {"corpus_id": "PX-2026-001", "version": "1.0"}
    b1 = bundle_version("NEW", "1.0", based_on, [make_patch("rules", "ADD", [1], "v1")], [])
    b2 = bundle_version("NEW", "1.0", based_on, [make_patch("rules", "ADD", [2], "v1")], [])
    # 变更集不同 → 内容哈希不同
    assert b1["content_hash"] != b2["content_hash"]
    # 相同输入 → 相同哈希（可复现）
    b3 = bundle_version("NEW", "1.0", based_on, [make_patch("rules", "ADD", [1], "v1")], [])
    assert b1["content_hash"] == b3["content_hash"]
    assert b1["published"] is False  # 默认未发布
    print("[OK] content_hash：变更不同→哈希不同；同输入→哈希相同（可复现）")


def test_base_version_optimistic_lock():
    # 验收用例 8：版本并发冲突 → 检测基础版本过期
    r = check_base_version("PX@1.0", "PX@1.0")
    assert r["ok"] is True
    r2 = check_base_version("PX@1.0", "PX@2.0")
    assert r2["ok"] is False and "过期" in r2["reason"]
    print("[OK] 乐观锁：base_version 匹配通过，过期检测并拒绝")


def test_acceptance_same_name_diff_semantics():
    # 验收用例 3：同名字段但语义不同（类型变化）→ 不能直接映射，应 rebuild
    diffs = diff_schemas({"claims": {"type": "string"}}, {"claims": {"type": "array"}})
    r = decide_change_strategy(diffs)
    assert r["strategy"] == "rebuild", f"同名异义不应直接复用，实际 {r['strategy']}"
    print("[OK] 同名异义（类型变化）→ rebuild，不直接映射")


def test_acceptance_permission_reject():
    # 验收用例 9：无权限访问 → 拒绝复用
    r = decide_change_strategy([], forbidden=True)
    assert r["strategy"] == "reject"
    p = make_patch("asset", "REJECT", {"reason": "无权限"}, "v1")
    assert p["operation"] == "REJECT"
    print("[OK] 无权限 → reject，不读取/复用")


def test_content_hash_deterministic():
    # 验收用例 10：相同确定性配置 → 等价结构化结果
    a = {"x": 1, "y": [1, 2], "z": "标"}
    assert content_hash(a) == content_hash(dict(a))
    assert content_hash(a) != content_hash({"x": 2, "y": [1, 2], "z": "标"})
    print("[OK] content_hash 确定性：同输入等价，异输入不同")


def main() -> int:
    test_patch_operations()
    test_bundle_content_hash()
    test_base_version_optimistic_lock()
    test_acceptance_same_name_diff_semantics()
    test_acceptance_permission_reject()
    test_content_hash_deterministic()
    print("\n数据契约 + 版本固化验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
