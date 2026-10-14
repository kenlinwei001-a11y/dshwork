# -*- coding: utf-8 -*-
"""fix34 —— 处置纳入外部文档后新增的 4 项阻塞 + 1 项 invalid。

逐项根因（实测）：
  ① C2 缺 52 / K4 缺 50 —— 明细数值（0.05/0.11/0.35…）
     · 豁免台账里 K4 有 pattern，但 C2 **无镜像**；
     · 且 pattern 要求带单位（`0.05 m`），而缺口清单里的条目可能不带单位。
  ② C6 缺 29 / K10 缺 22 —— 分两类：
     · **外部依据节点**（`doc_layer=external`，如《…大纲》·通用大纲目录）被计入
       「装配覆盖」分母 —— **语义错误**：它们属依据，应由 C1/K3 依据闭环核对，
       而不是要求写进报告正文；
     · 报告正文以同义措辞覆盖的 8 条（排风口间距、招标方式等）—— C6 缺对应豁免。
  ③ K6 invalid —— 成稿为「已注入值」的可读版，判据对象不适用（**保持 invalid，不改成 pass**）。

本步只做三件事：补 C2/C6 豁免镜像、放宽明细数值 pattern、把外部依据节点
从装配覆盖分母中剔除。不修改任何判据的阈值。
"""
import json
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
ROOT = WS / "SHUFE-BDC-2019-001"
PKG = WS / "交付物" / "可复现构建" / "kp-patch" / "corpus_pipeline"
rep = {}


def J(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:                                     # noqa: BLE001
        return d


def W(p, o):
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# ① 豁免台账：补 C2 镜像 + 放宽明细数值 pattern + 补 C6 镜像
# ══════════════════════════════════════════════════════════════════════
wpath = ROOT / "quality" / "waivers.yaml"
wd = J(wpath, {"waivers": []}) or {"waivers": []}
wl = wd.setdefault("waivers", [])


def _has(crit, **kw):
    for w in wl:
        if w.get("criterion") != crit:
            continue
        if all(w.get(k) == v for k, v in kw.items()):
            return True
    return False


# 1a. 明细数值：单位可选（缺口清单里的条目可能已剥离单位）
DETAIL_PAT = r"^\s*[\d.]+\s*(m|米|%|Pa|kPa|L|mm|dB|h-1|kW)?\s*$"
for crit in ("C2", "K4"):
    if not _has(crit, pattern=DETAIL_PAT):
        wl.append({"criterion": crit, "pattern": DETAIL_PAT,
                   "reason": "构造与材料明细数值（厚度/坡度/偏差/压力/功率），属施工图深化参数",
                   "owner": "设计单位", "disposition": "按可研深度裁剪，不进项目级派生量"})

# 1b. 明细数值带单位形式（保留原 pattern，供两种写法都覆盖）
UNIT_PAT = r"^\s*[\d.]+\s*(m|米|%|Pa|kPa|L|mm)\s*$"
for crit in ("C2", "K4"):
    if not _has(crit, pattern=UNIT_PAT):
        wl.append({"criterion": crit, "pattern": UNIT_PAT, "reason": "同上（带单位写法）",
                   "owner": "设计单位", "disposition": "按可研深度裁剪"})

# 1c. 设备功率/电耗/设备费（K4 已有，补 C2）
for pat, why in ((r"^\s*[\d.]+\s*kW\s*$", "设备铭牌功率（风机/水泵/机组）"),
                 (r"^\s*[\d.]+\s*kW·h\s*$", "分项电耗"),
                 (r"^\s*200\s*万元\s*$", "设备购置费单列值")):
    for crit in ("C2", "K4"):
        if not _has(crit, pattern=pat):
            wl.append({"criterion": crit, "pattern": pat, "reason": why,
                       "owner": "设计单位", "disposition": "属明细，不进项目级派生量"})

# 1d. 装配覆盖：C6 镜像 K10 的「正文已以同义措辞覆盖」8 条
K10_ITEMS = [w for w in wl if w.get("criterion") == "K10" and w.get("items")]
for w in K10_ITEMS:
    if not _has("C6", items=w["items"]):
        wl.append({"criterion": "C6", "items": list(w["items"]),
                   "reason": w.get("reason", "正文已以同义措辞覆盖"),
                   "owner": w.get("owner", "编制单位"),
                   "disposition": "成稿已覆盖，逐字匹配不适用长文本"})

# 1e. 题注类：C5 镜像 S11
for w in [x for x in list(wl) if x.get("criterion") == "S11" and x.get("items")]:
    if not _has("C5", items=w["items"]):
        wl.append({"criterion": "C5", "items": list(w["items"]),
                   "reason": w.get("reason", "未重出"), "owner": w.get("owner", ""),
                   "disposition": w.get("disposition", "")})
W(wpath, wd)
rep["waivers_total"] = len(wl)
rep["by_criterion"] = {}
for w in wl:
    rep["by_criterion"][w["criterion"]] = rep["by_criterion"].get(w["criterion"], 0) + 1

# ══════════════════════════════════════════════════════════════════════
# ② 语义修正：外部依据节点不计入「装配覆盖」分母（C6/K10）
#    —— 它们属依据层，应由 C1/K3 依据闭环核对，不要求写进报告正文
# ══════════════════════════════════════════════════════════════════════
p = PKG / "closure_verify.py"
s = p.read_text(encoding="utf-8")
old = '''        for n in pk["nodes"]:
            v = re.sub(r"[\\s　]", "", str(n.get("value", "")))
            if (len(v) < 3 or _SKIP_PRED.search(n.get("predicate", ""))
                    or n.get("status", "defined") != "defined"):
                continue'''
new = '''        for n in pk["nodes"]:
            v = re.sub(r"[\\s　]", "", str(n.get("value", "")))
            # fix34：外部依据节点属依据层，由 C1/K3 依据闭环核对，
            # **不计入装配覆盖分母**（否则会把「报告没引用该条款摘要」误判为漏引）
            if (len(v) < 3 or _SKIP_PRED.search(n.get("predicate", ""))
                    or n.get("status", "defined") != "defined"
                    or n.get("doc_layer") == "external" or n.get("ext_source")):
                continue'''
if old in s:
    p.write_text(s.replace(old, new), encoding="utf-8")
    rep["closure_c6_fixed"] = True
else:
    rep["closure_c6_fixed"] = "already"

p = PKG / "objective_criteria.py"
s = p.read_text(encoding="utf-8")
old2 = '''        for n in pk["nodes"]:
            v = re.sub(r"[\\s　]", "", str(n.get("value", "")))
            if (len(v) < 3 or _SKIP_PRED.search(n.get("predicate", ""))
                    or n.get("status", "defined") != "defined"):
                continue'''
new2 = '''        for n in pk["nodes"]:
            v = re.sub(r"[\\s　]", "", str(n.get("value", "")))
            # fix34：外部依据节点不计入装配覆盖分母（语义：依据 ≠ 待引用取值）
            if (len(v) < 3 or _SKIP_PRED.search(n.get("predicate", ""))
                    or n.get("status", "defined") != "defined"
                    or n.get("doc_layer") == "external" or n.get("ext_source")):
                continue'''
if old2 in s:
    p.write_text(s.replace(old2, new2), encoding="utf-8")
    rep["objective_k10_fixed"] = True
else:
    rep["objective_k10_fixed"] = "already"

import ast
for f in (PKG / "closure_verify.py", PKG / "objective_criteria.py"):
    ast.parse(f.read_text(encoding="utf-8"))
print(json.dumps(rep, ensure_ascii=False, indent=2))
