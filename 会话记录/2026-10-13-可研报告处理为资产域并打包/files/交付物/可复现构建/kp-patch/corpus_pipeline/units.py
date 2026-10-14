# -*- coding: utf-8 -*-
"""量纲归一（确定性，零 LLM）。

用途：门禁比较「值+单位」时，消除同一物理量的不同写法造成的**假缺口**。
例：`5000 万元` 与 `50000000 元`、`1.2 万kW·h` 与 `12000 kW·h`。

设计约束：
  · 纯词表 + 浮点比较，无外部依赖；
  · 容差显式参数化；
  · 判不了就返回 None，**不猜**。
"""
from __future__ import annotations

# 单位 → (基准单位, 换算系数)
UNIT_CANON: dict[str, tuple[str, float]] = {
    "万元": ("元", 1e4), "亿元": ("元", 1e8), "千元": ("元", 1e3),
    "元/㎡": ("元/㎡", 1.0),
    "万kW·h": ("kW·h", 1e4), "万kWh": ("kW·h", 1e4), "万kW·h/年": ("kW·h", 1e4),
    "万kWh/年": ("kW·h", 1e4), "kW·h": ("kW·h", 1.0), "kWh": ("kW·h", 1.0),
    "万m³": ("m³", 1e4), "m3": ("m³", 1.0), "m³": ("m³", 1.0), "m3/h": ("m³/h", 1.0),
    "L/S": ("L/s", 1.0), "L／S": ("L/s", 1.0), "l/s": ("L/s", 1.0),
    "Kw": ("kW", 1.0), "KW": ("kW", 1.0), "kw": ("kW", 1.0), "kW": ("kW", 1.0),
    "㎡": ("㎡", 1.0), "平方米": ("㎡", 1.0), "米": ("m", 1.0), "m": ("m", 1.0),
    "%": ("%", 1.0), "kgce": ("kgce", 1.0), "kgce/㎡": ("kgce/㎡", 1.0),
    # 基准单位必须显式登记为自身映射，否则「一方可归一、另一方不可」会退化为不可比
    "元": ("元", 1.0), "㎡": ("㎡", 1.0), "m": ("m", 1.0), "kW": ("kW", 1.0),
    "kW·h": ("kW·h", 1.0), "m³": ("m³", 1.0), "m³/h": ("m³/h", 1.0),
    "L/s": ("L/s", 1.0), "人": ("人", 1.0), "个": ("个", 1.0), "台": ("台", 1.0),
    "套": ("套", 1.0), "座": ("座", 1.0), "间": ("间", 1.0), "层": ("层", 1.0),
    "Pa": ("Pa", 1.0), "kPa": ("kPa", 1.0), "dB": ("dB", 1.0),
}


def normalize_units(value, unit: str) -> tuple[float | None, str]:
    """把 (值, 单位) 折算到基准单位。无法解析时返回 (None, 原单位)。"""
    u = (unit or "").strip()
    if u in UNIT_CANON:
        cu, f = UNIT_CANON[u]
        try:
            return float(str(value).replace(",", "")) * f, cu
        except (ValueError, TypeError):
            return None, cu
    return None, u


def same_quantity(v1, u1, v2, u2, tol: float = 0.005) -> bool:
    """判断两个「值+单位」是否表示同一物理量（跨单位）。

    · 都能归一 → 基准单位相同且相对差 ≤ tol 才算同量；
    · 都不能归一 → 退化为「单位与值字面相同」；
    · 只有一方可归一 → **返回 False（不猜）**。
    """
    a, ua = normalize_units(v1, u1)
    b, ub = normalize_units(v2, u2)
    if a is not None and b is not None:
        if ua != ub:
            return False
        if a == 0 and b == 0:
            return True
        return abs(a - b) <= max(abs(a), abs(b)) * tol
    if a is None and b is None:
        return (u1 or "") == (u2 or "") and str(v1).replace(",", "") == str(v2).replace(",", "")
    return False


def to_canonical_text(value, unit: str) -> str:
    """归一后的稳定文本，用于去重与比对。"""
    v, u = normalize_units(value, unit)
    return f"{v:g} {u}" if v is not None else f"{value} {unit}".strip()


if __name__ == "__main__":
    assert same_quantity("5000", "万元", "50000000", "元")
    assert same_quantity("1.2", "万kW·h", "12000", "kW·h")
    assert not same_quantity("5000", "万元", "5000", "元")
    assert not same_quantity("10", "㎡", "10", "m")
    assert to_canonical_text("18319", "㎡") == "18319 ㎡"
    print("units.py 自测通过")
