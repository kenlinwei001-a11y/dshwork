# -*- coding: utf-8 -*-
"""fastload —— YAML 读取带 JSON 缓存层。

## 为什么需要

实测瓶颈全在读 YAML，不在计算：

    nodes.yaml 1.9 MB / 2410 节点
      yaml.safe_load : 30.78 s
      json.loads     :  0.08 s   → 快 387.8 倍

整条链路 34 s 里 32 s 在读 YAML，纯计算只有 0.01 s。

## 做法

读 YAML 时，同目录生成 `xxx.yaml.json` 缓存；下次直接读 JSON。
缓存失效判据：缓存 mtime < 源文件 mtime。

**源码仍是 YAML**（人读友好、可 git diff），JSON 只是运行时缓存。
缓存文件不进包（加 .gitignore 语义：文件名以 `.yaml.json` 结尾）。

## 用法

    from corpus_pipeline.fastload import load
    d = load(Path("graph/nodes.yaml"))     # 首次慢，之后 0.08 s
    d = load(Path("x.yaml"), use_cache=False)   # 绕过缓存
"""
from __future__ import annotations
import json
import os
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

CACHE_SUFFIX = ".json"
CACHE_ENV = "KP_NOCACHE"          # 设 1 则禁用缓存


def _cache_path(src: Path) -> Path:
    return src.with_suffix(src.suffix + CACHE_SUFFIX)


def _cache_ok(src: Path, cch: Path) -> bool:
    try:
        return cch.exists() and cch.stat().st_mtime >= src.stat().st_mtime
    except OSError:
        return False


def load(src, *, use_cache: bool = True):
    """读 YAML/JSON 文件；YAML 自动建 JSON 缓存。"""
    src = Path(src)
    if not src.exists():
        return None
    if os.environ.get(CACHE_ENV) == "1":
        use_cache = False

    # 已是 JSON
    if src.suffix == ".json":
        try:
            return json.loads(src.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    # YAML：先查缓存
    cch = _cache_path(src)
    if use_cache and _cache_ok(src, cch):
        try:
            return json.loads(cch.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    if yaml is None:
        return None
    try:
        data = yaml.safe_load(src.read_text(encoding="utf-8"))
    except Exception:
        return None

    # 回写缓存（失败不影响返回）
    if use_cache:
        try:
            cch.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return data


def warm(paths) -> dict:
    """批量预热缓存。返回 {path: 耗时秒}。"""
    import time
    out = {}
    for p in paths:
        t = time.time()
        load(Path(p))
        out[str(p)] = round(time.time() - t, 3)
    return out


def clear(root) -> int:
    """清除某目录下所有缓存，返回删除数。"""
    n = 0
    for p in Path(root).rglob("*" + CACHE_SUFFIX):
        try:
            p.unlink(); n += 1
        except OSError:
            pass
    return n
