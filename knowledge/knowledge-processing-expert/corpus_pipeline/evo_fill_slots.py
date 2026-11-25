# -*- coding: utf-8 -*-
"""evo_fill_slots —— 把提示词模板里的 {{槽位}} 填成本项目值。

五态（不把缺失写成 0，不编造）：
  filled            客户给了 / 库里查到
  computed          由规则或数量×单价算出
  missing_customer  客户必须给但没给        → 【待客户提供】
  missing_standard  标准里该有但库里没值    → 【待标准库补充】
  unfilled          无法判定                → 【待确认】

每个 filled/computed 值都带 node_id：
  - 图谱事实 → P-xxx
  - 本次派生 → D-xxx（定义写入 prompt-filled/derived-nodes.json）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from .evo_slot_common import (
        GraphIndex, canonical_name, citations, derive_id, eval_expr, format_number,
        load_aliases, norm, resolve_slot_name, same_number, split_table_slot,
        to_number, unit_of_value_text,
    )
except ImportError:
    from evo_slot_common import (
        GraphIndex, canonical_name, citations, derive_id, eval_expr, format_number,
        load_aliases, norm, resolve_slot_name, same_number, split_table_slot,
        to_number, unit_of_value_text,
    )


MISSING_MARK = {
    "missing_customer": "【待客户提供】",
    "missing_standard": "【待标准库补充】",
    "unfilled": "【待确认】",
}

STATUS_CN = {
    "filled": "filled", "computed": "computed",
    "missing_customer": "missing_customer",
    "missing_standard": "missing_standard",
    "unfilled": "unfilled",
}

TOTAL_ROWS = {"总计", "合计", "总合计", "共计"}

# 备注槽位里属于「标准文号 / 标准费率」的行
STANDARD_NOTE_ROWS = {
    "前期工程咨询费", "设计费", "招标代理费", "清单及标底编制费",
    "施工监理费", "施工图审图费", "人防易地建设费", "基本预备费",
}

# 建筑面积口径：表内「数量」列的推导
AREA_ROWS_UNDERGROUND = {
    "地下建筑结构工程",
}
AREA_ROWS_ABOVE = {
    "地上建筑结构工程", "装配式结构增加费", "外立面及屋面装饰工程",
}
AREA_ROWS_TOTAL = {
    "建筑安装工程费用", "单体工程", "土建工程", "桩基工程",
    "室内装饰工程", "安装工程", "给排水工程", "消防工程",
    "通风、空调工程", "强电工程", "弱电工程", "绿色二星增量费用",
    "工程建设其他费", "基本预备费",
}

# 明确没有面积口径、必须问客户的数量行
MISSING_QTY_ROWS = {
    "基坑围护工程", "电梯工程", "道路、广场、硬地、铺装", "绿化、景观",
    "室外安装工程", "标识工程", "低压电缆", "人防易地建设费", "拆除费",
    "新老建筑立面接口处理费",
    "立面门窗、玻璃幕墙", "立面装饰幕墙", "上人屋面",
    "设备屋面（涂料）", "架空板底",
}


# ================================================================ 结果对象


@dataclass
class FillResult:
    name: str
    status: str = "unfilled"
    value: object = None
    display: str = ""
    unit: str = ""
    node_id: str = ""
    source: str = ""
    reason: str = ""
    formula: str = ""
    inputs: list = field(default_factory=list)
    alternatives: list = field(default_factory=list)
    occurrences: int = 0

    def as_dict(self):
        return {
            "name": self.name, "status": self.status,
            "value": self.value, "display": self.display,
            "unit": self.unit, "node_id": self.node_id,
            "source": self.source, "reason": self.reason,
            "formula": self.formula, "inputs": list(self.inputs),
            "alternatives": list(self.alternatives),
            "occurrences": self.occurrences,
        }


def _num(v):
    return to_number(v) if not isinstance(v, (list, dict)) else None


def _same(a, b, tol=1e-6):
    return same_number(a, b, tol)


# ================================================================ 填槽器


class SlotValues:
    """从 GRAPH + 模板元数据构造的槽位解析器。"""

    def __init__(self, graph, *, section="", template_slots=None,
                 aliases_path=None, rules_path=None, explicit=None,
                 max_depth=6):
        self.section = str(section or "")
        self.graph = GraphIndex(graph or {}, aliases_path=aliases_path,
                                rules_path=rules_path)
        self.alias_to_canon = self.graph.alias_to_canon
        self.template_slots = {str(s.get("name")): s for s in (template_slots or [])}
        self.explicit = {}
        for k, v in (explicit or {}).items():
            self.explicit[str(k)] = self._normalize_explicit(v)
        self.cache = {}
        self.derived_nodes = {}
        self.conflicts = []
        self.max_depth = max_depth
        self._conflict_keys = set()

    # ---- 显式值

    @staticmethod
    def _normalize_explicit(v):
        if isinstance(v, dict):
            return {
                "value": v.get("value"),
                "unit": v.get("unit") or "",
                "source": v.get("source") or "EXPLICIT",
                "node_id": v.get("node_id") or "",
            }
        return {"value": v, "unit": "", "source": "EXPLICIT", "node_id": ""}

    # ---- 结果工厂

    def _result(self, name, **kw):
        meta = self.template_slots.get(name) or {}
        r = FillResult(name=name)
        r.unit = kw.get("unit") or meta.get("unit") or ""
        r.status = kw.get("status", "unfilled")
        r.value = kw.get("value")
        r.node_id = kw.get("node_id") or ""
        r.source = kw.get("source") or meta.get("source_type") or ""
        r.reason = kw.get("reason") or ""
        r.formula = kw.get("formula") or ""
        r.inputs = kw.get("inputs") or []
        r.alternatives = kw.get("alternatives") or []
        r.display = self._display(r)
        return r

    def _display(self, r):
        if r.status in MISSING_MARK:
            return MISSING_MARK[r.status]
        v = r.value
        if isinstance(v, (int, float)):
            s = format_number(v)
        elif isinstance(v, list):
            s = " / ".join(format_number(x) if isinstance(x, (int, float)) else str(x) for x in v)
        else:
            s = str(v).strip() if v is not None else ""
        if r.node_id:
            s = "%s〔%s〕" % (s, r.node_id)
        if r.alternatives:
            s += "⚠"
        return s

    def _add_derived(self, name, value, formula, inputs, unit=""):
        did = derive_id(self.section, name, formula)
        self.derived_nodes[did] = {
            "id": did, "section": self.section, "slot": name,
            "value": value, "unit": unit, "formula": formula,
            "inputs": inputs,
        }
        return did

    def _add_conflict(self, name, primary, alternative, note=""):
        key = (name, str(primary.get("value")), str(alternative.get("value")))
        if key in self._conflict_keys:
            return
        self._conflict_keys.add(key)
        a, b = _num(primary.get("value")), _num(alternative.get("value"))
        delta = round(a - b, 6) if (a is not None and b is not None) else None
        self.conflicts.append({
            "slot": name,
            "primary": primary,
            "alternative": alternative,
            "delta": delta,
            "note": note or "两侧口径待审，不裁决",
        })

    # ---- 公式依赖取值

    def dependency_value(self, name, depth=0):
        """给算式求值用：返回 (numeric_value, node_id, missing_reason)。"""
        if depth > self.max_depth:
            return None, "", "递归过深"
        # 显式值
        if name in self.explicit:
            v = self.explicit[name]["value"]
            return _num(v), self.explicit[name]["node_id"], ""
        # 表槽
        row, col = split_table_slot(name)
        if row:
            r = self.resolve_table(name, row, col, depth=depth + 1)
        else:
            r = self.resolve_plain(name, depth=depth + 1)
        if r.status in ("filled", "computed") and _num(r.value) is not None:
            return _num(r.value), r.node_id, ""
        return None, "", r.reason or r.status

    # ---- 普通槽位

    def resolve_plain(self, name, depth=0):
        if name in self.cache:
            return self.cache[name]
        if depth > self.max_depth:
            r = self._result(name, status="unfilled", reason="递归过深")
            self.cache[name] = r
            return r

        # 显式值优先
        if name in self.explicit:
            e = self.explicit[name]
            v = e["value"]
            if v is None:
                r = self._result(name, status="unfilled", reason="显式值缺失")
            else:
                r = self._result(name, status="filled", value=v, unit=e["unit"],
                                 source=e["source"], node_id=e["node_id"],
                                 reason="调用方显式传入")
            self.cache[name] = r
            return r

        # 特殊派生
        special = self._resolve_special(name, depth)
        if special is not None:
            self.cache[name] = special
            return special

        # 图谱事实（精确名无值 → 再试一次规范化后的 subject）
        fact, alts = self.graph.find(name)
        if not fact or fact.get("value") is None:
            cname = canonical_name(name, self.alias_to_canon)
            if cname and cname != name:
                f2, a2 = self.graph.find(cname)
                if f2 and f2.get("value") is not None:
                    fact, alts = f2, a2
        rules = self.graph.find_rule_for_target(name)
        if fact and fact.get("value") is not None:
            r = self._from_fact(name, fact, alts)
            # 有事实也要重算规则：客户值 vs 公式值不一致 → 两侧都留，不裁决
            if rules:
                rr = self._from_rules(name, rules, depth)
                if rr.status == "computed" and not _same(r.value, rr.value):
                    if not any(_same(rr.value, a.get("value")) for a in r.alternatives):
                        alt = {
                            "value": rr.value, "node_id": rr.node_id,
                            "source": rr.source, "status": "computed",
                            "formula": rr.formula,
                        }
                        r.alternatives.append(alt)
                        self._add_conflict(
                            name,
                            {"value": r.value, "node_id": r.node_id, "source": r.source},
                            alt, note="客户值与规则重算值不一致")
            self.cache[name] = r
            return r

        # 规则目标
        if rules:
            r = self._from_rules(name, rules, depth)
            self.cache[name] = r
            return r

        # 没有任何来源 → 按模板来源类型判缺失
        meta = self.template_slots.get(name) or {}
        st = meta.get("source_type") or ""
        if st == "STANDARD":
            r = self._result(name, status="missing_standard",
                             reason="标准库无值；需查标准/行业惯例")
        elif st == "COMPUTED":
            r = self._result(name, status="unfilled",
                             reason="有计算口径但依赖缺失，无法计算")
        elif st == "CUSTOMER":
            r = self._result(name, status="missing_customer",
                             reason="客户必须提供但资料未给")
        else:
            r = self._result(name, status="unfilled",
                             reason="无法判定来源")
        self.cache[name] = r
        return r

    def _resolve_special(self, name, depth):
        # 校区：从建设地点提取（有事实锚点）
        if name == "校区":
            f, alts = self.graph.find("建设地点")
            if f and f.get("value"):
                m = re.search(r"([一-龥]{2,8}校区)", str(f["value"]))
                if m:
                    return self._result(
                        name, status="computed", value=m.group(1),
                        node_id=f.get("id", ""), source="DERIVED",
                        formula="从「建设地点」提取校区",
                        inputs=[f.get("id", "")],
                        reason="由建设地点派生")
            return self._result(name, status="missing_customer",
                                reason="资料未给校区；可从建设地点确认")
        # 科研机构列表：子系统名称拼接
        if name == "科研机构列表":
            names, ids = [], []
            for i in range(1, 9):
                f, alts = self.graph.find("子系统%d名称" % i)
                if f and f.get("value") is not None:
                    names.append(str(f["value"]).strip())
                    ids.append(f.get("id", ""))
            if names:
                return self._result(
                    name, status="computed", value="、".join(names),
                    node_id=ids[0], source="DERIVED",
                    formula="子系统名称按序拼接", inputs=ids,
                    reason="由客户提供的分中心名称派生")
            return self._result(name, status="missing_customer",
                                reason="客户未给科研机构/分中心名称")
        # 标准文号
        if name == "标准文号":
            return self._result(name, status="missing_standard",
                                reason="标准文号需从标准库/原文查")
        # 工期/日期/拆除面积
        if name in ("开工年份", "开工月份", "竣工年份", "竣工月份", "建设工期", "拆除面积"):
            return self._result(name, status="missing_customer",
                                reason="客户资料未给，需向客户确认")
        # 原有建筑
        if name == "原有建筑":
            return self._result(name, status="missing_customer",
                                reason="客户未给需拆除的原有建筑名称")
        return None

    def _from_fact(self, name, fact, alts):
        v = fact.get("value")
        st = str(fact.get("status") or "")
        src_type = str(fact.get("source_type") or "")
        status = "computed" if (src_type == "COMPUTED" or st == "computed") else "filled"
        reason = ""
        if "待算" in str(v) or "待复算" in str(v):
            reason = "客户值含「待算」，按原文保留并标注"
        # 同 subject 其它值 → 冲突候选
        alt_out = []
        for a in alts:
            av = a.get("value")
            if av is None:
                continue
            if not _same(v, av):
                alt_out.append({
                    "value": av, "node_id": a.get("id", ""),
                    "source_type": a.get("source_type", ""),
                    "status": a.get("status", ""),
                })
        unit = str(fact.get("unit") or "").strip()
        if unit in ("", "待算", "待复算"):
            meta = self.template_slots.get(name) or {}
            unit = str(meta.get("unit") or "").strip() or unit
        r = self._result(
            name, status=status, value=v, unit=unit,
            node_id=fact.get("id", ""), source=src_type or "GRAPH",
            reason=reason, alternatives=alt_out,
        )
        # 资金来源这类槽位：正文既要金额，也要来源名（国拨资金/学校自筹资金）。
        # 由模板元数据 display=subject_value 控制，避免按槽位名硬编码。
        meta = self.template_slots.get(name) or {}
        if str(meta.get("display") or "") == "subject_value":
            subject = str(fact.get("subject") or "").strip()
            if subject and not r.display.startswith(subject):
                r.display = "%s %s" % (subject, r.display)
        if alt_out:
            self._add_conflict(
                name,
                {"value": v, "node_id": fact.get("id", ""), "source": src_type},
                alt_out[0], note="同一事实位存在多个值")
        return r

    def _from_rules(self, name, rules, depth):
        best = None
        missing_all = []
        for rule in rules:
            expr = str(rule.get("expr") or "")
            if not expr:
                continue
            values = {}
            inputs = []
            missing = []
            for dep in re.findall(r"\{([^{}]+)\}", expr):
                v, nid, why = self.dependency_value(dep, depth + 1)
                if v is None:
                    missing.append("%s(%s)" % (dep, why or "缺"))
                else:
                    values[dep] = v
                    if nid:
                        inputs.append(nid)
            if missing:
                missing_all.extend(missing)
                continue
            try:
                result, miss = eval_expr(expr, values)
            except Exception as e:
                missing_all.append("%s: %s" % (rule.get("rule_id"), e))
                continue
            if result is None:
                missing_all.append("%s: 依赖缺失 %s" % (rule.get("rule_id"), miss))
                continue
            # 图内已有同规则结果 → 对得上就用图节点，对不上就派生
            gres = rule.get("graph_result")
            gout = rule.get("graph_output")
            if gout and gres is not None and _same(result, gres):
                nid = gout
            else:
                nid = self.graph.find_id_by_value(name, result) or self._add_derived(
                    name, result, expr, inputs)
            cand = self._result(
                name, status="computed", value=result,
                node_id=nid, source="RULE",
                formula=expr, inputs=inputs,
                reason="由 %s 计算" % (rule.get("rule_id") or "规则"),
            )
            if best is None:
                best = cand
            # 若同一目标有多个规则，保留第一个可算结果
        if best is not None:
            return best
        return self._result(
            name, status="missing_customer",
            reason="规则依赖缺失：" + "；".join(sorted(set(missing_all))[:4]),
        )

    # ---- 表槽

    def resolve_table(self, name, row, col, depth=0):
        if name in self.cache:
            return self.cache[name]
        if depth > self.max_depth:
            r = self._result(name, status="unfilled", reason="递归过深")
            self.cache[name] = r
            return r

        # 显式值优先
        if name in self.explicit:
            r = self.resolve_plain(name, depth)
            self.cache[name] = r
            return r

        meta = self.template_slots.get(name) or {}
        unit = meta.get("unit") or ""
        raw_col = col
        if str(col).startswith("备注"):
            col = "备注"

        # 1) 显式表槽别名 / 聚合
        target = resolve_slot_name(name, self.alias_to_canon)
        if target and col not in ("数量", "单价", "备注"):
            r = self._resolve_table_via_target(name, target, depth)
            self.cache[name] = r
            return r

        # 2) 合价 / 金额
        if col in ("合价", "金额", "估算金额", "费用"):
            target = target or canonical_name(row, self.alias_to_canon)
            r = self._resolve_table_via_target(name, target, depth)
            self.cache[name] = r
            return r

        # 3) 数量
        if col == "数量":
            r = self._resolve_quantity(name, row, unit, depth)
            self.cache[name] = r
            return r

        # 4) 单价 = 合价 × 10000 ÷ 数量
        if col == "单价":
            r = self._resolve_unit_price(name, row, unit, depth)
            self.cache[name] = r
            return r

        # 5) 年用水量 / 年用电量 / 日用水量
        if col == "年用水量":
            r = self._resolve_water_year(name, row, depth)
            self.cache[name] = r
            return r
        if col == "年用电量":
            if row in TOTAL_ROWS:
                r = self._resolve_table_via_target(name, "年总耗电量", depth)
            else:
                r = self._resolve_power_year(name, row, depth)
            self.cache[name] = r
            return r
        if col == "日用水量":
            target = resolve_slot_name(name, self.alias_to_canon) or (row + "日水量")
            r = self._resolve_table_via_target(name, target, depth)
            self.cache[name] = r
            return r

        # 6) 指标/定额/系数列
        if col in ("用水定额", "用电指标", "需要系数", "同时使用系数",
                   "日均工作小时数", "年工作天数", "用水天数"):
            target = resolve_slot_name(name, self.alias_to_canon)
            if not target:
                target = row + col
            r = self._resolve_table_via_target(name, target, depth)
            if r.status not in ("filled", "computed"):
                st = "missing_standard" if col in (
                    "用水定额", "用电指标", "需要系数", "同时使用系数") else "missing_customer"
                r = self._result(name, status=st, reason="资料未给 %s" % col)
            self.cache[name] = r
            return r

        # 7) 备注
        if col == "备注":
            r = self._resolve_note(name, row, depth)
            self.cache[name] = r
            return r

        # 8) 其它列：row+col
        target = target or (canonical_name(row, self.alias_to_canon) + col)
        r = self._resolve_table_via_target(name, target, depth)
        self.cache[name] = r
        return r

    def _resolve_table_via_target(self, name, target, depth):
        if not target:
            return self._result(name, status="unfilled", reason="槽位名无法映射到节点")
        r = self.resolve_plain(target, depth + 1)
        if r.status in ("filled", "computed"):
            return self._result(
                name, status=r.status, value=r.value, unit=r.unit or (self.template_slots.get(name) or {}).get("unit", ""),
                node_id=r.node_id, source=r.source, reason=r.reason,
                formula=r.formula, inputs=r.inputs, alternatives=r.alternatives,
            )
        # 目标本身没有来源 → 按表槽的来源类型判缺失，不让它掉进 unfilled
        meta = self.template_slots.get(name) or {}
        st = meta.get("source_type") or ""
        if r.status == "unfilled":
            if st == "CUSTOMER":
                return self._result(name, status="missing_customer",
                                    reason="客户未给该子项，需向客户确认")
            if st == "STANDARD":
                return self._result(name, status="missing_standard",
                                    reason="标准库无该值，需查标准/行业惯例")
        # 保持目标缺失原因
        return self._result(name, status=r.status, reason=r.reason,
                            alternatives=r.alternatives)

    def _resolve_quantity(self, name, row, unit, depth):
        # 1) 显式表槽别名（建筑类行 → 总面积/地上/地下）
        target = resolve_slot_name(name, self.alias_to_canon)
        if target:
            r = self._resolve_table_via_target(name, target, depth)
            if r.status in ("filled", "computed"):
                return r
        # 2) 精确的 row+数量 事实（禁止子串匹配，避免把「合价」当「数量」）
        for cand in (row + "数量", row + "·数量"):
            facts = self.graph.by_subject.get(norm(cand)) or []
            f, alts = self.graph.pick(facts)
            if f and f.get("value") is not None:
                return self._from_fact(name, f, alts)
        # 3) 建筑面积口径
        if unit == "㎡":
            if row in AREA_ROWS_UNDERGROUND:
                return self._resolve_table_via_target(name, "地下建筑面积", depth)
            if row in AREA_ROWS_ABOVE:
                return self._resolve_table_via_target(name, "地上建筑面积", depth)
            if row in AREA_ROWS_TOTAL:
                return self._resolve_table_via_target(name, "本项目建筑面积", depth)
            # 面积类但资料没有该分项面积
            return self._result(name, status="missing_customer",
                                reason="客户未给该分项面积")
        if unit == "项":
            return self._result(name, status="filled", value="—",
                                source="FORM", reason="按项计，数量不适用")
        if row in MISSING_QTY_ROWS or unit in ("m", "部", "台"):
            return self._result(name, status="missing_customer",
                                reason="客户未给该分项数量/长度")
        return self._result(name, status="missing_customer",
                            reason="客户未给该分项数量")

    def _resolve_unit_price(self, name, row, unit, depth):
        r_amt = self.resolve_table("%s·合价" % row, row, "合价", depth + 1)
        r_qty = self.resolve_table("%s·数量" % row, row, "数量", depth + 1)
        amt, qty = _num(r_amt.value), _num(r_qty.value)
        if amt is None or qty is None or qty == 0:
            why = []
            if amt is None:
                why.append("合价缺失/不可算")
            if qty is None:
                why.append("数量缺失/不可算")
            return self._result(name, status="missing_customer",
                                reason="；".join(why) + "，无法计算单价")
        formula = "round({%s·合价}*10000/{%s·数量}, 0)" % (row, row)
        value = round(amt * 10000 / qty, 0)
        nid = self._add_derived(name, value, formula,
                                [x for x in (r_amt.node_id, r_qty.node_id) if x],
                                unit=unit or "元/㎡")
        return self._result(name, status="computed", value=value,
                            node_id=nid, source="DERIVED", formula=formula,
                            inputs=[x for x in (r_amt.node_id, r_qty.node_id) if x],
                            reason="数量×单价=合价 反算")

    def _water_base(self, depth):
        """(教师日水量+学生日水量)×天数÷10000；失败返回 (None, [], reason)。"""
        parts, ids, missing = [], [], []
        for who in ("教师用水", "学生用水"):
            rd = self.resolve_table("%s·日用水量" % who, who, "日用水量", depth + 1)
            v = _num(rd.value)
            if v is None:
                missing.append(who + "日用水量")
            else:
                parts.append(v)
                if rd.node_id:
                    ids.append(rd.node_id)
        rd = self.resolve_table("教师用水·用水天数", "教师用水", "用水天数", depth + 1)
        days = _num(rd.value)
        if days is None:
            rd2 = self.resolve_plain("年工作天数", depth + 1)
            days = _num(rd2.value)
            if rd2.node_id:
                ids.append(rd2.node_id)
            else:
                missing.append("年工作天数")
        elif rd.node_id:
            ids.append(rd.node_id)
        if missing or len(parts) < 2:
            return None, ids, "缺 " + "、".join(missing or ["用水日水量"])
        return round((parts[0] + parts[1]) * days / 10000, 6), ids, ""

    def _three_water_calibers(self, base, depth):
        """三种口径：×1.15%（公式字面）/ ×10%（上财原文）/ ×1.15（系数语义）。"""
        coef = 1.15
        r = self.resolve_plain("未预见系数", depth + 1)
        if _num(r.value) is not None:
            coef = _num(r.value)
        c1 = round(base + round(base * coef / 100, 2), 2)
        c2 = round(base + round(base * 0.10, 2), 2)
        c3 = round(base * coef, 2)
        return [c1, c2, c3], coef

    def _resolve_water_year(self, name, row, depth):
        # 表内「合计」「不可预计」没有逐行列，是三口径派生
        if row in TOTAL_ROWS or "不可预计" in row:
            base, ids, why = self._water_base(depth)
            if base is None:
                if row in TOTAL_ROWS:
                    return self._resolve_table_via_target(name, "年总用水量", depth)
                return self._result(name, status="missing_customer",
                                    reason="无法计算基数：" + why)
            if "不可预计" in row:
                c1, c2, c3 = [round(base * 1.15 / 100, 2),
                              round(base * 0.10, 2),
                              round(base * 0.15, 2)]
                formula = ("三口径：基数×1.15%%=%s；基数×10%%=%s；"
                           "基数×15%%（系数语义增量）=%s" % (c1, c2, c3))
                value = [c1, c2, c3]
            else:
                value, coef = self._three_water_calibers(base, depth)
                formula = ("三口径：基数+基数×%.2f%%=%s；基数+基数×10%%=%s；"
                           "基数×%.2f=%s（基数 %s）"
                           % (coef, value[0], value[1], coef, value[2], base))
                # 与客户值并存（不裁决）
                cust = self.resolve_plain("年总用水量", depth + 1)
                if cust.status in ("filled", "computed") and _num(cust.value) is not None:
                    self._add_conflict(
                        name,
                        {"value": cust.value, "node_id": cust.node_id, "source": cust.source},
                        {"value": value, "node_id": "", "source": "DERIVED",
                         "formula": formula},
                        note="表内合计与客户值口径不一致；三口径并列，不裁决")
            nid = self._add_derived(name, value, formula, ids)
            return self._result(name, status="computed", value=value,
                                node_id=nid, source="DERIVED", formula=formula,
                                inputs=ids,
                                reason="三口径并列，待审，不裁决")

        r_day = self.resolve_table("%s·日用水量" % row, row, "日用水量", depth + 1)
        r_days = self.resolve_table("%s·用水天数" % row, row, "用水天数", depth + 1)
        day, days = _num(r_day.value), _num(r_days.value)
        if day is None or days is None:
            return self._result(name, status="missing_customer",
                                reason="缺日用水量或用水天数，无法计算年用水量")
        formula = "round({%s·日用水量}*{%s·用水天数}/10000, 2)" % (row, row)
        value = round(day * days / 10000, 2)
        nid = self._add_derived(name, value, formula,
                                [x for x in (r_day.node_id, r_days.node_id) if x])
        return self._result(name, status="computed", value=value,
                            node_id=nid, source="DERIVED", formula=formula,
                            inputs=[x for x in (r_day.node_id, r_days.node_id) if x],
                            reason="日用水量×用水天数÷10000")

    def _resolve_power_year(self, name, row, depth):
        names = ["用电面积", "用电指标", "需要系数", "同时使用系数",
                 "日均工作小时数", "年工作天数"]
        vals, ids, missing = {}, [], []
        for c in names:
            rr = self.resolve_table("%s·%s" % (row, c), row, c, depth + 1)
            v = _num(rr.value)
            if v is None:
                missing.append(c)
            else:
                vals[c] = v
                if rr.node_id:
                    ids.append(rr.node_id)
        if missing:
            return self._result(name, status="missing_customer",
                                reason="缺 %s，无法计算年用电量" % "、".join(missing))
        formula = ("round(({%s·用电面积}*{%s·用电指标}*{%s·需要系数}*{%s·同时使用系数})*"
                   "{%s·日均工作小时数}*{%s·年工作天数}/10000000, 1)") % ((row,) * 6)
        value = round((vals["用电面积"] * vals["用电指标"] * vals["需要系数"]
                       * vals["同时使用系数"]) * vals["日均工作小时数"]
                      * vals["年工作天数"] / 10000000, 1)
        nid = self._add_derived(name, value, formula, ids)
        return self._result(name, status="computed", value=value,
                            node_id=nid, source="DERIVED", formula=formula,
                            inputs=ids, reason="面积×指标×系数×小时×天数÷10000000")

    def _resolve_note(self, name, row, depth):
        f, alts = self.graph.find(name)
        if f and f.get("value") is not None:
            return self._from_fact(name, f, alts)
        if any(k in row for k in STANDARD_NOTE_ROWS):
            return self._result(name, status="missing_standard",
                                reason="标准文号/费率需查标准库")
        return self._result(name, status="missing_customer",
                            reason="备注中的项目专有参数需客户提供")


# ================================================================ 填槽 API


def _collect_slots(template_text, template_slots=None):
    names = []
    seen = set()
    for m in re.finditer(r"\{\{([^{}]+)\}\}", template_text or ""):
        n = m.group(1).strip()
        if n and n not in seen and re.search(r"[一-龥A-Za-z0-9]", n):
            seen.add(n)
            names.append(n)
    for s in (template_slots or []):
        n = str(s.get("name") or "").strip()
        if n and n not in seen and re.search(r"[一-龥A-Za-z0-9]", n):
            seen.add(n)
            names.append(n)
    return names


def fill_slots(template_text, values, *, section="", cite=True):
    """把模板里的 {{槽位}} 用 values 填充。

    values:
      - SlotValues（推荐）：由 build_values_from_graph() 构造
      - dict：{槽位名: {"value","unit","source","node_id"}} 或 {槽位名: 值}

    返回：
      {"filled_text","slots","stats","derived_nodes","conflicts"}
    """
    template_text = str(template_text or "")
    if isinstance(values, SlotValues):
        resolver = values
        template_slots = list(resolver.template_slots.values())
    else:
        resolver = SlotValues({}, section=section, explicit=values)
        template_slots = []

    names = _collect_slots(template_text, template_slots)
    results = {}
    for n in names:
        row, col = split_table_slot(n)
        if row:
            r = resolver.resolve_table(n, row, col)
        else:
            r = resolver.resolve_plain(n)
        results[n] = r

    def repl(m):
        n = m.group(1).strip()
        r = results.get(n)
        if r is None:
            return MISSING_MARK["unfilled"]
        if r.status in ("filled", "computed"):
            if cite:
                return r.display
            return r.display.split("〔")[0]
        return MISSING_MARK.get(r.status, MISSING_MARK["unfilled"])

    filled_text = re.sub(r"\{\{([^{}]+)\}\}", repl, template_text)

    stats = {k: 0 for k in STATUS_CN}
    for r in results.values():
        stats[r.status] = stats.get(r.status, 0) + 1
    stats["total"] = len(results)
    stats["to_ask_customer"] = stats.get("missing_customer", 0)
    stats["to_web_search"] = stats.get("missing_standard", 0)

    # 出现次数
    for m in re.finditer(r"\{\{([^{}]+)\}\}", template_text):
        n = m.group(1).strip()
        if n in results:
            results[n].occurrences += 1

    return {
        "filled_text": filled_text,
        "slots": [results[n].as_dict() for n in names],
        "stats": stats,
        "derived_nodes": resolver.derived_nodes,
        "conflicts": resolver.conflicts,
    }


def build_values_from_graph(graph_path, *, section="", template_slots=None,
                            aliases_path=None, rules_path=None, explicit=None):
    graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    return SlotValues(graph, section=section, template_slots=template_slots,
                      aliases_path=aliases_path, rules_path=rules_path,
                      explicit=explicit)


# ================================================================ 渲染完整提示词


def _slot_stats_lines(stats):
    order = ["filled", "computed", "missing_customer", "missing_standard", "unfilled"]
    cn = {
        "filled": "filled（客户/库）",
        "computed": "computed（规则/反算）",
        "missing_customer": "missing_customer（问客户）",
        "missing_standard": "missing_standard（查标准库）",
        "unfilled": "unfilled（待确认）",
    }
    lines = ["| 状态 | 数量 |", "|---|---:|"]
    for k in order:
        lines.append("| %s | %d |" % (cn[k], stats.get(k, 0)))
    lines.append("| **合计** | **%d** |" % stats.get("total", 0))
    return "\n".join(lines)


def _render_filled_slot_table(result, template_slots, section):
    meta = {str(s.get("name")): s for s in (template_slots or [])}
    lines = ["| 槽位 | 含义 | 状态 | 值 | 单位 | 节点ID | 说明 |",
             "|---|---|---|---|---|---|---|"]
    mark = {"filled": "✓ 已填", "computed": "✓ 已算",
            "missing_customer": "◐ 缺客户", "missing_standard": "✗ 待标准",
            "unfilled": "? 待确认"}
    for r in result["slots"]:
        m = meta.get(r["name"]) or {}
        val = r.get("display") or ""
        if r["status"] in MISSING_MARK:
            val = "—"
        lines.append("| `{{%s}}` | %s | %s | %s | %s | %s | %s |" % (
            r["name"], m.get("label") or r["name"], mark.get(r["status"], r["status"]),
            val or "—", r.get("unit") or "—", r.get("node_id") or "—",
            (r.get("reason") or "").replace("|", "/")))
    return "\n".join(lines)


def _render_unresolved(result):
    by_status = {}
    for r in result["slots"]:
        if r["status"] in MISSING_MARK:
            by_status.setdefault(r["status"], []).append(r)
    lines = []
    for st in ("missing_customer", "missing_standard", "unfilled"):
        arr = by_status.get(st, [])
        if not arr:
            continue
        lines.append("**%s（%d）**" % (MISSING_MARK[st].strip("【】"), len(arr)))
        lines.append("")
        for r in arr:
            lines.append("- `{{%s}}`：%s" % (r["name"], r.get("reason") or "待确认"))
        lines.append("")
    return "\n".join(lines) if lines else "_本节无未解决槽位。_"


def _render_conflicts(result, graph_conflicts=None):
    lines = []
    if graph_conflicts:
        for c in graph_conflicts:
            lines.append("- **%s（%s）**：%s" % (
                c.get("id", "CF"), c.get("status", "待审"),
                c.get("description", "")))
    for c in result.get("conflicts") or []:
        p, a = c.get("primary") or {}, c.get("alternative") or {}
        lines.append("- **%s**：主值 %s〔%s〕；另一侧 %s〔%s〕；差 %s。%s" % (
            c.get("slot"), p.get("value"), p.get("node_id", ""),
            a.get("value"), a.get("node_id", ""), c.get("delta"),
            c.get("note") or "两侧都写，不裁决"))
    return "\n".join(lines) if lines else "_本节无已知冲突。_"


def render_filled_prompt(template_text, result, *, section="", template_slots=None,
                         graph_conflicts=None, derived_path="prompt-filled/derived-nodes.json"):
    """把模板文本 + 填槽结果渲染成完整提示词。"""
    t = str((result or {}).get("filled_text") or template_text or "")
    t = t.replace("# 提示词模板", "# 完整提示词（已填槽）", 1)
    stats = result["stats"]
    banner = (
        "> 由模板 T-%s 填槽生成 ｜ 槽位 %d：filled %d / computed %d / "
        "missing_customer %d / missing_standard %d / unfilled %d\n"
        "> 每个数值后的〔…〕为节点ID；`D-xxx` 为本次派生节点，定义见 `%s`。\n"
        "> 缺失值只标「待客户提供/待标准库补充/待确认」，**不写 0、不猜**。"
        % (section, stats.get("total", 0), stats.get("filled", 0), stats.get("computed", 0),
           stats.get("missing_customer", 0), stats.get("missing_standard", 0),
           stats.get("unfilled", 0), derived_path)
    )
    # 标题后插入 banner
    lines = t.splitlines()
    if lines and lines[0].startswith("#"):
        lines = [lines[0], "", banner] + lines[1:]
    else:
        lines = [banner] + lines
    t = "\n".join(lines)

    # 替换 ① 槽位表
    slot_table = _render_filled_slot_table(result, template_slots, section)
    if "### ① 形节点" in t:
        start = t.find("### ① 形节点")
        end = t.find("### ②", start)
        if end < 0:
            end = len(t)
        head_end = t.find("\n", start)
        # 保留标题与说明，替换表格
        block = t[start:end]
        # 找到表头行
        tbl_start = block.find("| 槽位 |")
        if tbl_start >= 0:
            new_block = block[:tbl_start] + slot_table + "\n\n"
            # 去掉原表格后的统计行
            new_block += "**槽位统计**：%s\n\n" % (
                "；".join("%s=%d" % (k, stats.get(k, 0)) for k in
                          ("filled", "computed", "missing_customer",
                           "missing_standard", "unfilled")))
            t = t[:start] + new_block + t[end:]
        else:
            t = t[:end] + "\n" + slot_table + "\n\n" + t[end:]

    # 在 ② 之前插入未解决 + 冲突
    extra = []
    extra.append("### ⑦ 未解决与待决策")
    extra.append("")
    extra.append(_render_unresolved(result))
    extra.append("")
    extra.append("### ⑨ 已知冲突（两侧都写，不裁决）")
    extra.append("")
    extra.append(_render_conflicts(result, graph_conflicts))
    extra.append("")
    if "### ②" in t:
        t = t.replace("### ②", "\n".join(extra) + "\n### ②", 1)
    else:
        t += "\n" + "\n".join(extra)

    # 末尾统计
    t += "\n### ⑩ 填槽统计\n\n" + _slot_stats_lines(stats) + "\n\n"
    t += "> 派生节点：`%s`（%d 个）\n" % (derived_path, len(result.get("derived_nodes") or {}))
    return t


# ================================================================ 批量 / CLI


def fill_template_file(template_path, graph_path, out_path, *,
                       section=None, template_slots_path=None,
                       aliases_path=None, rules_path=None, explicit=None):
    template_text = Path(template_path).read_text(encoding="utf-8")
    if section is None:
        m = re.search(r"§([0-9.]+)", template_text)
        section = m.group(1) if m else Path(template_path).stem
    template_slots = []
    if template_slots_path and Path(template_slots_path).exists():
        template_slots = json.loads(Path(template_slots_path).read_text(encoding="utf-8")).get("slots") or []
    resolver = build_values_from_graph(
        graph_path, section=section, template_slots=template_slots,
        aliases_path=aliases_path, rules_path=rules_path, explicit=explicit)
    result = fill_slots(template_text, resolver, section=section)
    graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    graph_conflicts = (graph.get("items") or {}).get("conflicts") or []
    filled = render_filled_prompt(
        template_text, result, section=section, template_slots=template_slots,
        graph_conflicts=graph_conflicts,
        derived_path=str(Path(out_path).parent / "derived-nodes.json"))
    out_dir = Path(out_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(filled, encoding="utf-8")
    # 派生节点登记表（跨节累积）
    dpath = out_dir / "derived-nodes.json"
    existing = {}
    if dpath.exists():
        try:
            existing = json.loads(dpath.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing.update(result.get("derived_nodes") or {})
    dpath.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    # 填槽报告（便于逐槽回查）
    rpath = out_dir / ("_fill-%s.json" % section)
    rpath.write_text(json.dumps({
        "section": section, "stats": result["stats"],
        "slots": result["slots"], "conflicts": result.get("conflicts") or [],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="把提示词模板填成完整提示词")
    ap.add_argument("--template", required=True)
    ap.add_argument("--graph", default="GRAPH-新项目-华东理工AI研究院-merged.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--section", default="")
    ap.add_argument("--slots", default="", help="模板槽位 JSON（默认按模板路径推断）")
    ap.add_argument("--aliases", default="形-可复用知识资产-v1.0/ontology/fact-aliases.yaml")
    ap.add_argument("--rules", default="形-可复用知识资产-v1.0/functions/derivation_templates.yaml")
    args = ap.parse_args(argv)
    slots_path = args.slots
    if not slots_path:
        p = Path(args.template)
        cand = p.parent / ("_slots-%s.json" % (args.section or p.stem))
        if cand.exists():
            slots_path = str(cand)
    result = fill_template_file(
        args.template, args.graph, args.out, section=args.section or None,
        template_slots_path=slots_path, aliases_path=args.aliases,
        rules_path=args.rules)
    print(json.dumps(result["stats"], ensure_ascii=False))
    print("derived_nodes", len(result.get("derived_nodes") or {}))
    print("conflicts", len(result.get("conflicts") or []))
    print("out", args.out)


if __name__ == "__main__":
    main()
