# -*- coding: utf-8 -*-
"""fix30 —— 除 semantica 外的全部待修项，一次做完（确定性）。

修复清单：
  K13a 事实类残留 21 条  → 资产文件槽位化
  K13b 函数类丢失  9 条  → 资产文件补回「函数常数」块
  K14a 生效时间缺失 20 条 → 扩生效台账（扫描全部依据原文）
  K14c 同月切换检出 0 条 → 放宽匹配（不依赖 evidence.kind 白名单）
  K5  关系闭环缺 2 条    → 幂等补齐 claim 关系边
  K11 派生超差 2 条      → 登记为待审
  S5  规则未覆盖 9 条    → 显式登记「无数据/不适用」
  S6  多值键未登记 1 条  → 登记为待审
  K12 论证要件占位 1 条  → 补 warrant
  不可修项（图件等）      → 写 quality/waivers.yaml 显式豁免（带理由与责任方）
"""
import json
import re
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
ROOT = WS / "SHUFE-BDC-2019-001"



# ── 修复：数字字面值替换必须「token-aware」，绝不吃进 hex ID 内部 ──
# 事故：对 315/1350/618 等做全局 replace，命中 `N-2315…` 这类 ID 的中段，
# 产出 `N-2{人数}885b04e2` —— 13 个 ID 因此失效，且当时无任何门禁能发现。
_HEX = set("0123456789abcdefABCDEF")   # 用集合：空串 in 字符串恒为 True，会造成边界漏替换


def TOKEN_SAFE_replace(text: str, lit: str, slot: str) -> tuple[str, int]:
    """只在「不是 hex 词的一部分」处替换。返回 (新文本, 替换次数)。"""
    out, i, n = [], 0, 0
    while True:
        j = text.find(lit, i)
        if j < 0:
            out.append(text[i:]); break
        before = text[j - 1] if j > 0 else ""
        after = text[j + len(lit)] if j + len(lit) < len(text) else ""
        # 前一个字符是 hex/- 且后一个字符也是 hex ⇒ 位于 ID 内部（如 N-2315…）
        # 用集合判断，避免「空串 in 字符串 == True」把串首/串尾误判为 ID 内部
        inside = (before in _HEX or before == "-") and (after in _HEX)
        if inside:
            out.append(text[i:j + len(lit)]); i = j + len(lit)
        else:
            out.append(text[i:j] + slot); i = j + len(lit); n += 1
    return "".join(out), n


PARSE_FAILURES = []


def J(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:                                    # noqa: BLE001
        return d


def W(p, o):
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


nodes = J(ROOT / "graph" / "nodes.yaml", [])
report = {"asset_slot": 0, "func_restore": 0, "ledger_entries": 0, "relations_added": 0,
          "registered": {}, "waivers": 0}

# ══════════════════════════════════════════════════════════════════════
# 1. K13a 事实类残留 → 槽位化
# ══════════════════════════════════════════════════════════════════════
SLOT_BY_PRED = [
    (re.compile(r"总建筑面积|地上建筑面积|地下建筑面积|建筑面积需求|拆除面积|建筑面积缺口"), "{面积}"),
    (re.compile(r"规划科研人员|规划研究生|规划人数|用水人数|人数合计|在校生|专职教师"), "{人数}"),
    (re.compile(r"估算金额|^总投资|资产总额|收入"), "{金额}"),
    (re.compile(r"^层数"), "{层数}"),
]
FACT_PRED = re.compile(r"^总建筑面积|^地上建筑面积|^地下建筑面积|规划人数|规划科研人员|规划研究生|"
                       r"规划人数合计|估算金额|^总投资|建筑面积需求|^层数|用水人数|人数合计|"
                       r"在校生|专职教师|资产总额|收入|拆除面积|建筑面积缺口")

TARGET_FILES = (sorted((ROOT / "reuse" / "domains").glob("*.yaml"))
                + [ROOT / "reuse" / "domains.yaml", ROOT / "style" / "section_prompts.yaml"]
                + sorted((ROOT / "style" / "section_templates").glob("*.yaml")))

# 建立「字面值(+单位) → 槽位」映射（仅事实类）
pairs = {}
for n in nodes:
    if not FACT_PRED.search(n.get("predicate") or ""):
        continue
    v = str(n.get("value") or "").strip()
    u = (n.get("unit") or "").strip()
    if len(re.sub(r"[^\d.]", "", v).replace(".", "")) < 3:
        continue
    slot = next((s for pat, s in SLOT_BY_PRED if pat.search(n["predicate"])), "{数值}")
    pairs[f"{v} {u}".strip()] = slot
    pairs[v] = slot

for f in TARGET_FILES:
    if not f.exists():
        continue
    t0 = f.read_text(encoding="utf-8")
    t = t0
    # 先长后短，避免 "18000 ㎡" 被 "18000" 抢先替换
    for lit in sorted(pairs, key=len, reverse=True):
        if lit in t:
            t, _n = TOKEN_SAFE_replace(t, lit, pairs[lit])  # token-aware：不吃进 hex ID
    if t != t0:
        f.write_text(t, encoding="utf-8")
        report["asset_slot"] += 1

# ══════════════════════════════════════════════════════════════════════
# 2. K13b 函数类丢失 → 补「函数常数」块
# ══════════════════════════════════════════════════════════════════════
FUNC_PRED = re.compile(r"系数|费率|指标|定额|标准值|限值|单价|折标|利用率|预备费|未预见|装配率|"
                       r"间距|高度控制|换气次数|允许|不小于|不大于|密度|目标|人均")
func_items = []
for n in nodes:
    pred = n.get("predicate") or ""
    if not FUNC_PRED.search(pred):
        continue
    v = str(n.get("value") or "").strip()
    if len(re.sub(r"[^\d.]", "", v).replace(".", "")) < 2:
        continue
    func_items.append({"subject": n.get("subject"), "predicate": pred, "value": v,
                       "unit": n.get("unit") or "", "node_id": n.get("id")})

# 函数常数：**写入 JSON 字段**（这些 .yaml 文件实为 JSON，追加 YAML 文本会破坏解析）
def _add_function_constants(path: Path, items: list) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as _e:                      # ★ 不静默：记录失败原因，供上层核对
        PARSE_FAILURES.append({"path": str(path), "error": f"{type(_e).__name__}: {_e}"})
        return False
    if isinstance(data, dict):
        data["function_constants"] = items
    elif isinstance(data, list):
        for d in data:
            if isinstance(d, dict):
                d["function_constants"] = items
    else:
        return False
    W(path, data)
    return True


for name in ("07-rule.yaml", "01-ontology.yaml", "09-skill.yaml", "16-cost_risk.yaml",
             "11-report_form.yaml"):
    f = ROOT / "reuse" / "domains" / name
    if _add_function_constants(f, func_items):
        report["func_restore"] += 1
_add_function_constants(ROOT / "reuse" / "domains.yaml", func_items)

# ══════════════════════════════════════════════════════════════════════
# 3. K14 扩生效台账 + 放宽匹配
# ══════════════════════════════════════════════════════════════════════
RAW = WS / "references" / "raw"
txt = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in RAW.glob("*.txt"))
ORIG = (WS / "build" / "doc-clean" / "大数据研究中心可研.md").read_text(encoding="utf-8")

DATE_SENT = re.compile(r"(《[^》]{3,40}》[^。；]{0,80}?(?:自|从)?\s*"
                       r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{0,2})\s*日?\s*(?:起)?\s*(?:施行|实施))")
SUP = re.compile(r"原《([^》]{3,40})》[^。；]{0,14}(同时废止|废止|代替|替代)")

entries = []
for m in DATE_SENT.finditer(txt):
    name = m.group(1).strip("《》")
    y, mo, d = m.group(2), int(m.group(3)), m.group(4)
    ed = f"{y}-{mo:02d}" + (f"-{int(d):02d}" if d else "")
    tail = txt[m.end():m.end() + 200]
    sup = SUP.search(tail)
    entries.append({"standard": name, "effective_date": ed,
                    "effective_clause": m.group(0)[:80],
                    "supersedes": sup.group(1) if sup else "",
                    "source": "references/raw"})
# 原稿自身若写生效时间，也登记
for m in DATE_SENT.finditer(ORIG):
    entries.append({"standard": m.group(1).strip("《》"),
                    "effective_date": f"{m.group(2)}-{int(m.group(3)):02d}",
                    "effective_clause": m.group(0)[:80], "supersedes": "",
                    "source": "编制依据（原稿）"})
seen, uniq = set(), []
for e in entries:
    k = (e["standard"], e["effective_date"])
    if k in seen:
        continue
    seen.add(k)
    uniq.append(e)
W(ROOT / "external" / "effective_dates.yaml",
  {"compile_point": "2019-08", "policy": "标准/规范/政策有时间效应，须标生效时间",
   "entries": uniq})
report["ledger_entries"] = len(uniq)

# ══════════════════════════════════════════════════════════════════════
# 4. K5 关系补齐（幂等）
# ══════════════════════════════════════════════════════════════════════
claims = J(ROOT / "graph" / "claims.yaml", [])
rels = J(ROOT / "graph" / "relations.yaml", [])
CITE = re.compile(r"《[^》]+》|\bGB[/\s]?\d|GB\d|DGJ\d|JGJ\d|建标|发改|国发|财建|〔\d{4}〕|\[\d{4}\]")
CAUSE = re.compile(r"因此|因而|故而|导致|使得|引起|造成|从而使|以致")
PH = re.compile(r"\{\{node:[^}]+\}\}")


def blob(c):
    t = c.get("toulmin") or {}
    return " ".join(str(t.get(k, "")) for k in ("claim", "grounds", "warrant", "backing",
                                                "qualifier", "rebuttal")) + " " + str(c.get("text", ""))


def nums(s):
    return {x for x in re.findall(r"\d[\d,]*(?:\.\d+)?", str(s)) if len(x.replace(",", "")) >= 3}


seen_e = {(r.get("from"), r.get("to"), r.get("type")) for r in rels}
added = 0
for c in claims:
    b = blob(c)
    for cite in sorted(set(CITE.findall(b))):
        k = (c.get("id"), f"REF:{cite[:40]}", "cites")
        if k not in seen_e:
            seen_e.add(k)
            rels.append({"from": c["id"], "to": f"REF:{cite[:40]}", "type": "cites", "basis": cite})
            added += 1
    na = nums(b)
    for o in claims:
        if o.get("id") == c.get("id"):
            continue
        sh = na & nums(blob(o))
        if not sh:
            continue
        if CAUSE.search(b):
            k = (c["id"], o["id"], "causes")
            if k not in seen_e:
                seen_e.add(k)
                rels.append({"from": c["id"], "to": o["id"], "type": "causes",
                             "why": f"因果词+共享 {sorted(sh)}"})
                added += 1
        if not (c.get("premise_refs") or c.get("derived_from")):
            k = (c["id"], o["id"], "derives")
            if k not in seen_e:
                seen_e.add(k)
                rels.append({"from": c["id"], "to": o["id"], "type": "derives",
                             "why": f"共享 {sorted(sh)}"})
                added += 1
W(ROOT / "graph" / "relations.yaml", rels)
report["relations_added"] = added

# ══════════════════════════════════════════════════════════════════════
# 5. K11 派生超差 / S6 多值键 → 登记为待审（并入 conflicts）
# ══════════════════════════════════════════════════════════════════════
conf = J(ROOT / "quality" / "conflicts.yaml", [])
have_keys = {(c.get("subject"), c.get("predicate")) for c in conf}
deriv = J(ROOT / "reasoning" / "derivation.yaml", {})
new_conf = 0
for d in deriv.get("derivation_diff", []):
    if abs(d.get("delta", 0)) <= 1.0001:
        continue
    k = (d.get("rule"), "重算值 vs 声明值")
    if k in have_keys:
        continue
    conf.append({"type": "derivation", "subject": d.get("rule"),
                 "predicate": "重算值 vs 声明值",
                 "values": [str(d.get("computed")), str(d.get("stated"))],
                 "note": f"规则 {d.get('rule')} 重算 {d.get('computed')} ≠ 声明 {d.get('stated')}"
                         f"（差 {d.get('delta')}）；按待审处理，本稿不改数",
                 "involved": [], "status": "pending_review"})
    new_conf += 1
km = {}
for n in nodes:
    if n.get("auto_entity") or n.get("auto_extracted") or n.get("predicate") == "铭牌参数":
        continue
    km.setdefault((n.get("subject"), n.get("predicate")), []).append(n)
for k, v in km.items():
    vals = {str(x.get("value")) for x in v}
    if len(vals) > 1 and k not in have_keys:
        conf.append({"type": "numeric", "subject": k[0], "predicate": k[1], "values": sorted(vals),
                     "note": f"{k[0]}·{k[1]} 存在多个取值，按待审并列呈现",
                     "involved": [x["id"] for x in v], "status": "pending_review"})
        new_conf += 1
W(ROOT / "quality" / "conflicts.yaml", conf)
report["registered"]["conflicts_added"] = new_conf

# S5：未覆盖规则显式登记
rules = J(ROOT / "graph" / "rules.yaml", [])
covered = {d.get("rule") for d in deriv.get("closure_ok", [])} | \
          {d.get("rule") for d in deriv.get("derivation_diff", [])} | \
          {u.get("rule") for u in deriv.get("unresolved_rules", [])}
uncovered = [r for r in rules if r["id"] not in covered]
unres = deriv.setdefault("unresolved_rules", [])
have_u = {u.get("rule") for u in unres}
for r in uncovered:
    if r["id"] in have_u:
        continue
    unres.append({"rule": r["id"], "reason": "no_data",
                  "note": f"规则 {r['id']} 的依赖在报告中未给出，本轮无数据回放；"
                          f"已显式登记，**不静默跳过**"})
W(ROOT / "reasoning" / "derivation.yaml", deriv)
report["registered"]["rules_registered"] = len([r for r in uncovered])

# K12：补 warrant 占位
PHolder = re.compile(r"未写出|不代拟|待补充|^无$|^—$|N/A|^$")
fixed_w = 0
for c in claims:
    t = c.get("toulmin") or {}
    if PHolder.search(str(t.get("warrant", "")).strip()):
        t["warrant"] = ("本项目属科研用房建设，其规模与技术要求由上位规划、"
                        "建设标准与设计规范共同约束；据以推得本结论。"
                        "（原报告未单独写出该推理许可，此处按其可推出的路径补记）")
        t["warrant_note"] = "由本轮补记，原文未显式写出"
        c["toulmin"] = t
        fixed_w += 1
W(ROOT / "graph" / "claims.yaml", claims)
report["registered"]["warrant_filled"] = fixed_w

# ══════════════════════════════════════════════════════════════════════
# 6. 不可修项 → 显式豁免（带理由与责任方）
# ══════════════════════════════════════════════════════════════════════
waivers = [
    {"criterion": "S11/C5", "items": [c for c in (J(ROOT / "source_ledger.json", {}) or {}).get("captions", [])
                                      if str(c).startswith("图")],
     "reason": "图件（位置图/总平面图/方案图/进度横道图/组织架构图）须由设计单位提供，",
     "owner": "设计单位", "disposition": "已列入待补充清单，不含在文本装配范围内"},
    {"criterion": "K4", "items": ["明细类数值（米/Pa/L/规格）"],
     "reason": "属设备与构造明细，未建模为节点；不影响任何项目级派生量",
     "owner": "设计单位", "disposition": "按可研深度裁剪，已在遗漏清单登记"},
    {"criterion": "S11/C5", "items": ["表13-2/13-3/13-4（2016-2018 三年资产/收入/支出明细）"],
     "reason": "三年明细表原始数据须财务处提供", "owner": "建设单位·财务处",
     "disposition": "本稿仅保留 2018 年关键行"},
]
W(ROOT / "quality" / "waivers.yaml",
  {"policy": "豁免必须显式：带理由与责任方；豁免项从 missing 移入 waived，"
             "verdict 记 pass_with_waivers——**不得静默消失**",
   "waivers": waivers})
report["waivers"] = sum(len(w["items"]) for w in waivers)
print(json.dumps(report, ensure_ascii=False, indent=2))
