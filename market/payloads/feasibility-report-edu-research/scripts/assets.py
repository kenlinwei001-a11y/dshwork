#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L0 资产加载。集中在一处，是为了让"资产坏了"这件事有一个可诊断的出口。

原来每个脚本各自 yaml.safe_load，某个 references/*.yaml 被改坏时
直接抛 traceback——使用者看到的是 Python 栈，不知道是哪个文件、
坏在哪一行、该怎么办。工业级系统不该这样。
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "references"

REQUIRED = {
    "core": ("ontology-core.yaml", ["regulatory_anchor", "classes", "constraints", "vocabularies"]),
    "argu": ("ontology-argumentation.yaml", ["argument_unit", "feasibility_frame", "evidence_model"]),
    "deriv": ("derivations.yaml", ["operators", "templates"]),
}
OPTIONAL = {
    "norms": ("norms.yaml", ["norms"]),
}


class AssetError(Exception):
    pass


def _load_one(path, required_keys, optional=False):
    if not path.exists():
        if optional:
            return {}
        raise AssetError(
            f"缺少必需的 L0 资产：{path.relative_to(ROOT)}\n"
            f"  这个文件定义了本体的一部分，缺了它检查结果不可信。\n"
            f"  若是误删，从 skill 包中恢复；若是有意裁剪，请同步修改 scripts/assets.py。")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"第 {mark.line + 1} 行第 {mark.column + 1} 列" if mark else "位置未知"
        raise AssetError(
            f"L0 资产 {path.relative_to(ROOT)} 解析失败（{where}）\n"
            f"  {getattr(e, 'problem', e)}\n"
            f"  常见原因：流式映射 {{}} 里写了块标量 |、中文引号未配对、缩进不一致。") from None
    if not isinstance(data, dict):
        raise AssetError(f"L0 资产 {path.relative_to(ROOT)} 顶层不是映射结构")
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise AssetError(
            f"L0 资产 {path.relative_to(ROOT)} 缺少必需的顶层段：{missing}\n"
            f"  这些段是检查器依赖的。缺失会导致对应检查静默跳过——"
            f"那比报错更危险。")
    return data


def load_all():
    """返回 (core, argu, deriv, norms)。任一必需资产异常都抛 AssetError。"""
    out = {}
    for key, (fname, req) in REQUIRED.items():
        out[key] = _load_one(REF / fname, req)
    for key, (fname, req) in OPTIONAL.items():
        try:
            out[key] = _load_one(REF / fname, req, optional=True)
        except AssetError:
            out[key] = {}
    return out["core"], out["argu"], out["deriv"], out.get("norms", {})


def load_l0():
    """向后兼容：只要三件核心资产。"""
    core, argu, deriv, _ = load_all()
    return core, argu, deriv


def guard(fn):
    """把 AssetError 变成人能读懂的退出，而不是 traceback。"""
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except AssetError as e:
            print("=" * 70)
            print("L0 资产加载失败 —— 无法继续")
            print("=" * 70)
            print(e)
            return 3
    return wrapper
