# -*- coding: utf-8 -*-
"""数据契约 + 操作类型 + 版本固化（对齐智演装配引擎第四节/第九节）。

把装配流程中的散落 JSON 收敛为显式契约，保证可测试、可审计、可防并发覆盖。
"""
from __future__ import annotations
import hashlib
import json

# 8 个资产操作类型（文档第四节「推荐的操作类型」）
PATCH_OPERATIONS = (
    "REUSE",         # 引用历史资产的现有版本
    "PARAMETERIZE",  # 保留结构，注入新参数
    "ADD",           # 新增资产或字段
    "MODIFY",        # 修改项目级副本或新版本
    "MAP",           # 建立新旧字段/对象的语义映射
    "DEPRECATE",     # 标记旧定义不再用于新项目
    "REBUILD",       # 重建项目级资产
    "REJECT",        # 拒绝不兼容或不允许的资产
)


def content_hash(obj) -> str:
    """对象的内容哈希（sha256），用于版本固化与 base_version 校验。"""
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_patch(target_asset: str, operation: str, payload, base_version: str) -> dict:
    """构造带 operation + base_version 的 AssetPatch（文档第四节契约）。

    operation ∈ PATCH_OPERATIONS；base_version 为历史资产版本（乐观锁基准）。
    """
    if operation not in PATCH_OPERATIONS:
        raise ValueError(f"非法操作类型 {operation}，应为 {PATCH_OPERATIONS}")
    return {
        "target_asset": target_asset,
        "operation": operation,
        "payload": payload,
        "base_version": base_version,
    }


def bundle_version(project_id: str, version: str, based_on: dict, patches: list, lineage: list) -> dict:
    """固化项目资产包版本（Asset Publisher 最小版）。

    返回 {project_id, version, content_hash, based_on, published}。
    content_hash 覆盖 based_on + patches + lineage，任何一处变化都会改变哈希。
    published 默认 False，验证通过后由 publisher 置 True。
    """
    digest = content_hash({"based_on": based_on, "patches": patches, "lineage": lineage})
    return {
        "project_id": project_id,
        "version": version,
        "content_hash": digest,
        "based_on": based_on,
        "published": False,
    }


def check_base_version(expected_base_version: str, actual_base_version: str) -> dict:
    """乐观锁：校验 base_version 是否过期（文档第四节：防并发覆盖）。

    返回 {ok, reason}。ok=False 表示基础版本过期，需重新装配或合并。
    """
    if expected_base_version == actual_base_version:
        return {"ok": True}
    return {"ok": False,
            "reason": f"基础版本过期：期望 {expected_base_version}，实际 {actual_base_version}，需重新装配或合并"}
