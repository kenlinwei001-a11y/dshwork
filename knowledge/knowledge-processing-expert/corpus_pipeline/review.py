# -*- coding: utf-8 -*-
"""知识处理侧 P0：候选 → 正式资产状态机。

对齐智演知识处理侧 K0–K11 的「三个质量关口 + 发布」边界：
  - K4 抽取产物是「候选」（status=draft），装配侧默认不可见；
  - 经 K5–K10（标准化/消歧/关联/验证/审核）推进到 validated；
  - K11 发布为 published，装配侧才可检索/复用。

语料包级别状态机（manifest.status）：
  draft → validated → published（只允许单向推进，禁止回退/跳级）
"""
from __future__ import annotations
import json
from pathlib import Path

CORPUS_STATUS = ("draft", "validated", "published")
_STATUS_ORDER = {"draft": 0, "validated": 1, "published": 2}


def promote_status(manifest: dict, target: str) -> dict:
    """单向推进语料包状态：draft → validated → published。

    禁止回退、禁止跳级（draft 不能直接到 published，须先 validated）。
    返回 {ok, from, to, reason}。
    """
    current = (manifest or {}).get("status", "draft")
    if current not in CORPUS_STATUS:
        current = "draft"
    if target not in CORPUS_STATUS:
        return {"ok": False, "from": current, "to": target, "reason": f"非法目标状态 {target}"}
    if _STATUS_ORDER[target] <= _STATUS_ORDER[current]:
        return {"ok": False, "from": current, "to": target,
                "reason": f"状态只能单向推进：{current} → {target} 非法"}
    if target == "published" and current != "validated":
        return {"ok": False, "from": current, "to": target,
                "reason": "发布前必须先 validated（通过质量关口），禁止 draft 直接发布"}
    return {"ok": True, "from": current, "to": target}


def is_published(manifest: dict) -> bool:
    return (manifest or {}).get("status") == "published"


def get_package_status(library_root, package: str) -> dict:
    """读语料包 manifest 的当前状态。"""
    manifest = _read_manifest(library_root, package)
    return {"package": package, "status": manifest.get("status", "draft"),
            "corpus_id": manifest.get("corpus_id", ""), "version": manifest.get("version", "")}


def _read_manifest(library_root, package: str) -> dict:
    p = Path(library_root) / package / "manifest.yaml"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}


def promote_package(library_root, package: str, target: str) -> dict:
    """推进语料包状态并写回 manifest（draft → validated → published）。"""
    manifest = _read_manifest(library_root, package)
    if not manifest:
        return {"ok": False, "reason": f"语料包 {package} 的 manifest 不存在"}
    r = promote_status(manifest, target)
    if not r["ok"]:
        return r
    manifest["status"] = target
    p = Path(library_root) / package / "manifest.yaml"
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "package": package, "from": r["from"], "to": target}


def publish_package(library_root, package: str) -> dict:
    """发布语料包（validated → published），装配侧从此可检索/复用。"""
    return promote_package(library_root, package, "published")
