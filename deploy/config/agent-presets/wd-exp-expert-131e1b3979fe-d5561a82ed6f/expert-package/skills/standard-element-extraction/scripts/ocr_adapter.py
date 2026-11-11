# -*- coding: utf-8 -*-
"""OCR 适配器（留白接口）

设计：**结构抽取不依赖 OCR，取值依赖可替换的 OCR 引擎。**
  - 今天：vision（系统 Vision，随 grid 工具；中文标准文本可用，密集小字表格会漏）
  - 将来：local（你的本地 OCR 模型）—— 只需实现 OCRBackend.recognize 一个方法
  - none：只抽结构（行列与空位），值留空并标 UNVERIFIED

接入契约（local 后端必须满足）：
  recognize(image_png_bytes: bytes) -> {"text": str, "conf": float}
  · 输入是**单格裁切图**（PNG 字节，已放大到 300dpi 以上）
  · 输出纯文本（多行用空格连接）与置信度 0~1
  · 不得改写数字（不得把 0.00 输出成 0.0）；原文位数必须保留
  · 无法识别时返回 {"text": "", "conf": 0.0}，不要猜

用法：
  from ocr_adapter import get_backend
  be = get_backend("local")          # 或 "vision" / "none"
  r = be.recognize(png_bytes)
"""
import os, subprocess

class OCRBackend:
    name = "base"
    def available(self) -> bool: return False
    def recognize(self, image_png: bytes) -> dict:
        raise NotImplementedError

class VisionBackend(OCRBackend):
    """系统 Vision（macOS）：由 hj84-2016/out/grid 工具在切格时一并完成，这里只做可用性声明。"""
    name = "vision"
    def available(self) -> bool:
        here = os.path.dirname(os.path.abspath(__file__))
        return bool(os.environ.get("TABLE_GRID_BIN")) or os.path.exists(os.path.join(here, "bin", "grid"))
    def recognize(self, image_png: bytes) -> dict:
        # 单格 OCR 走 grid 工具（整页一次处理，避免逐格起进程）
        raise NotImplementedError(
            "vision 后端在 table_from_pdf.py 的整页流程中调用；单格接口待本地模型接入后再提供")

class LocalBackend(OCRBackend):
    """本地 OCR 模型（待部署）——留白位。

    接入方式：设置环境变量 OCR_LOCAL_ENDPOINT（http://127.0.0.1:PORT/ocr）
    或把模型加载逻辑写进 recognize()。契约见模块 docstring。
    """
    name = "local"
    def available(self) -> bool:
        return bool(os.environ.get("OCR_LOCAL_ENDPOINT"))
    def recognize(self, image_png: bytes) -> dict:
        ep = os.environ.get("OCR_LOCAL_ENDPOINT")
        if not ep:
            raise NotImplementedError(
                "本地 OCR 未部署：请设置 OCR_LOCAL_ENDPOINT 或实现 LocalBackend.recognize")
        # 期望返回 {"text": "...", "conf": 0.98}
        import json, urllib.request
        req = urllib.request.Request(ep, data=image_png, headers={"Content-Type": "image/png"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))

class NoneBackend(OCRBackend):
    """只抽结构：单元格留空，值标 UNVERIFIED"""
    name = "none"
    def available(self) -> bool: return True
    def recognize(self, image_png: bytes) -> dict: return {"text": "", "conf": 0.0}

_REG = {"vision": VisionBackend, "local": LocalBackend, "none": NoneBackend}

def get_backend(name: str = "vision") -> OCRBackend:
    if name not in _REG:
        raise ValueError(f"unknown ocr engine: {name}; choose from {list(_REG)}")
    return _REG[name]()

def status() -> dict:
    return {k: get_backend(k).available() for k in _REG}

if __name__ == "__main__":
    print(status())
