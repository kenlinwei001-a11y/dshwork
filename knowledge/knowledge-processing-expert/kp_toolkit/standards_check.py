# -*- coding: utf-8 -*-
"""kp_toolkit.standards_check —— 标准限值判定（确定性，零 LLM）

把已转录的表格限值做成可执行判定函数。
数据来源：公共标准库 clauses.yaml 的 table 字段（图片转录）。
未匹配到条目时返回 UNKNOWN —— 不猜、不近似。

对外：
    check_thermal(part, k, d=None, wwr=None)      → GB50189 表3.3.1-4 围护结构
    check_lpd(room, value, mode="目标")            → GB50034 表6.3.3/6.3.7/6.3.13
    LIMITS                                        → 全部限值原始数据
"""
from typing import Optional

# ══ GB50189-2015 表3.3.1-4 夏热冬冷地区甲类公共建筑 ══
# key: (部位, 条件) → K 上限 W/(m²·K)；SHGC 另存
THERMAL_K = {
    ("屋面", "D≤2.5"): 0.40,
    ("屋面", "D>2.5"): 0.50,
    ("外墙", "D≤2.5"): 0.60,
    ("外墙", "D>2.5"): 0.80,
    ("架空或外挑楼板", None): 0.70,
    ("外窗", "窗墙比≤0.20"): 3.5,
    ("外窗", "0.20<窗墙比≤0.30"): 3.0,
    ("外窗", "0.30<窗墙比≤0.40"): 2.6,
    ("外窗", "0.40<窗墙比≤0.50"): 2.4,
    ("外窗", "0.50<窗墙比≤0.60"): 2.2,
    ("外窗", "0.60<窗墙比≤0.70"): 2.2,
    ("外窗", "0.70<窗墙比≤0.80"): 2.0,
    ("外窗", "窗墙比>0.80"): 1.8,
    ("屋顶透明部分", "面积≤20%"): 2.6,
}
THERMAL_SHGC = {
    "0.20<窗墙比≤0.30": (0.44, 0.48),
    "0.30<窗墙比≤0.40": (0.40, 0.44),
    "0.40<窗墙比≤0.50": (0.35, 0.40),
    "0.50<窗墙比≤0.60": (0.35, 0.40),
    "0.60<窗墙比≤0.70": (0.30, 0.35),
    "0.70<窗墙比≤0.80": (0.26, 0.35),
    "窗墙比>0.80": (0.24, 0.30),
    "面积≤20%": (None, 0.30),
}

# ══ GB50034-2013 照明功率密度（现行值 / 目标值）W/㎡ ══
# key: (房间或场所, 表号) → (现行值, 目标值)
LPD = {
    ("普通办公室", "6.3.3"): (9.0, 8.0),
    ("高档办公室、设计室", "6.3.3"): (15.0, 13.5),
    ("会议室", "6.3.3"): (9.0, 8.0),
    ("服务大厅", "6.3.3"): (11.0, 10.0),
    ("教室、阅览室", "6.3.7"): (9.0, 8.0),
    ("实验室", "6.3.7"): (9.0, 8.0),
    ("美术教室", "6.3.7"): (15.0, 13.5),
    ("多媒体教室", "6.3.7"): (9.0, 8.0),
    ("计算机教室、电子阅览室", "6.3.7"): (15.0, 13.5),
    ("学生宿舍", "6.3.7"): (5.0, 4.5),
    ("走廊-一般", "6.3.13"): (2.5, 2.0),
    ("走廊-高档", "6.3.13"): (4.0, 3.5),
    ("厕所-一般", "6.3.13"): (3.5, 3.0),
    ("厕所-高档", "6.3.13"): (6.0, 5.0),
    ("试验室-一般", "6.3.13"): (9.0, 8.0),
    ("试验室-精细", "6.3.13"): (15.0, 13.5),
    ("检验-一般", "6.3.13"): (9.0, 8.0),
    ("检验-精细，有颜色要求", "6.3.13"): (23.0, 21.0),
    ("计量室、测量室", "6.3.13"): (15.0, 13.5),
    ("控制室-一般控制室", "6.3.13"): (9.0, 8.0),
    ("控制室-主控制室", "6.3.13"): (15.0, 13.5),
    ("电话站、网络中心、计算机站", "6.3.13"): (15.0, 13.5),
    ("风机房、空调机房", "6.3.13"): (4.0, 3.5),
    ("泵房", "6.3.13"): (4.0, 3.5),
    ("冷冻站", "6.3.13"): (6.0, 5.0),
    ("压缩空气站", "6.3.13"): (6.0, 5.0),
    ("锅炉房、煤气站的操作层", "6.3.13"): (5.0, 4.5),
    ("大件库", "6.3.13"): (2.5, 2.0),
    ("一般件库", "6.3.13"): (4.0, 3.5),
    ("半成品库", "6.3.13"): (6.0, 5.0),
    ("精细件库", "6.3.13"): (7.0, 6.0),
    ("公共车库", "6.3.13"): (2.5, 2.0),
    ("车辆加油站", "6.3.13"): (5.0, 4.5),
}

LIMITS = {"GB50189-2015 表3.3.1-4": {"thermal_k": THERMAL_K, "thermal_shgc": THERMAL_SHGC,
                                      "climate": "夏热冬冷（上海）"},
          "GB50034-2013 表6.3.3/6.3.7/6.3.13": {"lpd": LPD}}


def _wwr_key(wwr):
    """窗墙面积比 → 条件键"""
    if wwr is None: return None
    if wwr <= 0.20: return "窗墙比≤0.20"
    if wwr <= 0.30: return "0.20<窗墙比≤0.30"
    if wwr <= 0.40: return "0.30<窗墙比≤0.40"
    if wwr <= 0.50: return "0.40<窗墙比≤0.50"
    if wwr <= 0.60: return "0.50<窗墙比≤0.60"
    if wwr <= 0.70: return "0.60<窗墙比≤0.70"
    if wwr <= 0.80: return "0.70<窗墙比≤0.80"
    return "窗墙比>0.80"


def check_thermal(part, k, d=None, wwr=None, shgc=None, direction="南"):
    """GB50189-2015 表3.3.1-4 围护结构热工性能判定（夏热冬冷地区）

    part: 屋面 / 外墙 / 架空或外挑楼板 / 外窗 / 屋顶透明部分
    k:    设计传热系数 W/(m²·K)
    d:    热惰性指标（屋面/外墙用，判断 D≤2.5 还是 D>2.5）
    wwr:  窗墙面积比（外窗用，0~1）
    shgc: 太阳得热系数（外窗用，可选）
    direction: 东/南/西/北（判断 SHGC 取哪个值）

    返回 {"result": "PASS"|"FAIL"|"UNKNOWN", "limit":…, "basis":…, "reason":…}
    """
    part = str(part or "").strip()
    key2 = None
    if part in ("屋面", "外墙"):
        if d is None:
            return {"result": "UNKNOWN", "reason": "缺少热惰性指标 D，无法判断 D≤2.5 还是 D>2.5"}
        key2 = "D≤2.5" if float(d) <= 2.5 else "D>2.5"
    elif part == "外窗":
        key2 = _wwr_key(wwr)
        if key2 is None:
            return {"result": "UNKNOWN", "reason": "缺少窗墙面积比"}
    elif part == "屋顶透明部分":
        key2 = "面积≤20%"
    limit = THERMAL_K.get((part, key2))
    if limit is None:
        return {"result": "UNKNOWN", "reason": f"表3.3.1-4 无「{part} / {key2}」条目"}
    ok = float(k) <= limit
    out = {"result": "PASS" if ok else "FAIL", "limit": limit, "value": float(k),
           "basis": "GB50189-2015 表3.3.1-4（夏热冬冷）",
           "clause": f"{part} {key2 or ''}".strip()}
    if part == "外窗" and shgc is not None:
        pair = THERMAL_SHGC.get(key2)
        if pair:
            lim = pair[1] if direction == "北" else pair[0]
            if lim is not None:
                out["shgc_limit"] = lim
                out["shgc_pass"] = float(shgc) <= lim
    return out


def check_lpd(room, value, mode="目标", table=None):
    """GB50034-2013 照明功率密度判定

    room:  房间或场所（见 LPD 键）
    value: 设计 LPD，W/㎡
    mode:  "现行" 或 "目标"
    table: 可选，限定表号 6.3.3 / 6.3.7 / 6.3.13

    返回 {"result": "PASS"|"FAIL"|"UNKNOWN", …}
    """
    room = str(room or "").strip()
    cands = [(k, v) for k, v in LPD.items() if k[0] == room and (table is None or k[1] == table)]
    if not cands:
        # 模糊匹配
        cands = [(k, v) for k, v in LPD.items() if room and (room in k[0] or k[0] in room)]
    if not cands:
        return {"result": "UNKNOWN", "reason": f"GB50034 表6.3 无「{room}」条目"}
    if len(cands) > 1 and table is None:
        return {"result": "UNKNOWN", "reason": f"「{room}」匹配到多条，请指定 table",
                "candidates": [k[0] + "(" + k[1] + ")" for k, _ in cands]}
    (rn, tb), (cur, tgt) = cands[0]
    lim = cur if mode == "现行" else tgt
    ok = float(value) <= lim
    return {"result": "PASS" if ok else "FAIL", "limit": lim, "value": float(value),
            "mode": mode, "basis": f"GB50034-2013 表{tb}（{mode}值）",
            "room": rn, "table": tb}
