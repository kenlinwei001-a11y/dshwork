#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可行性研究报告本体图谱 —— 一致性检查器 (L0)

实现 C1-C6 六类约束，与项目类型无关。
输入：ontology/core.yaml + ontology/argumentation.yaml + rules/derivations.yaml + 实例图
输出：结构化冲突清单（人工裁决用）+ 缺口清单（分诊为客户提问 / web 检索任务）

设计原则：
  - 只报告，不自动改。数字的对错由数据提供方负责，本体只负责发现不一致。
  - 缺口必须归因到可行性维度 D1-D9，否则修补无从下手。
"""

import ast
import sys
import json
import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import SchemaValidator, detect_cycles, report_schema  # noqa: E402
from assets import load_all, guard  # noqa: E402

# =============================================================================
# 受限表达式求值
# =============================================================================

FUNCS = {
    "sum": lambda *a: sum(a),
    "round": round,
    "min": min,
    "max": max,
    "abs": abs,
    "ceil": lambda x: -(-x // 1),
    "floor": lambda x: x // 1,
}


class Unresolved(Exception):
    """引用了图中不存在的节点。不得静默当 0。"""


def _dotted(node):
    """把 ast 的属性链还原成点分节点名。"""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        raise ValueError("非法的节点引用")
    parts.append(node.id)
    return ".".join(reversed(parts))


def evaluate(expr, nodes, used=None):
    """在受限 AST 白名单上求值。used 收集实际引用到的节点，构成 E4 证据轨迹。"""
    if used is None:
        used = []

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            if isinstance(n.value, (int, float)):
                return n.value
            raise ValueError("表达式中只允许数字常量")
        if isinstance(n, (ast.Name, ast.Attribute)):
            key = n.id if isinstance(n, ast.Name) else _dotted(n)
            if key not in nodes:
                raise Unresolved(key)
            used.append(key)
            return nodes[key]["value"]
        if isinstance(n, ast.BinOp):
            l, r = ev(n.left), ev(n.right)
            op = type(n.op)
            if op is ast.Add:
                return l + r
            if op is ast.Sub:
                return l - r
            if op is ast.Mult:
                return l * r
            if op is ast.Div:
                return l / r
            raise ValueError("不支持的运算符")
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            v = ev(n.operand)
            return v if isinstance(n.op, ast.UAdd) else -v
        if isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name) or n.func.id not in FUNCS:
                raise ValueError("不在白名单中的函数")
            return FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError(f"不支持的语法节点 {type(n).__name__}")

    return ev(ast.parse(expr, mode="eval")), used


# =============================================================================
# 检查结果
# =============================================================================

class Finding:
    def __init__(self, code, severity, subject, message, detail=None, dimension=None,
                 action=None):
        self.code = code
        self.severity = severity          # error / warning / info
        self.subject = subject
        self.message = message
        self.detail = detail or {}
        self.dimension = dimension        # 归因到 D1-D9
        self.action = action              # 建议动作：ask_client / web_search / human_review

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if v}


# =============================================================================
# 检查器
# =============================================================================

class Validator:

    def __init__(self, core, argu, derivations, project, norms=None):
        self.norms = (norms or {}).get("norms") or {}
        self.core = core
        self.argu = argu
        self.deriv = derivations
        self.p = project
        self.nodes = {k: dict(v) for k, v in (project.get("nodes") or {}).items()}
        self.findings = []
        self.trace = {}
        self.passed = []
        # 证据 → 维度 反查表，用于把证据层缺陷归因到可行性维度
        self.ev_dim = {}
        for c in (project.get("claims") or {}).values():
            arg = c.get("argument") or {}
            for eid in (arg.get("grounds") or []) + (arg.get("backing") or []):
                for d in c.get("serves") or []:
                    self.ev_dim.setdefault(eid, set()).add(d)

    def _applicable(self, spec):
        """求值维度的 applicable_when。仅支持 always / 单个上下文布尔变量 / not 取反。"""
        expr = (spec.get("applicable_when") or "always").strip()
        if expr == "always":
            return True
        ctx = self.p.get("project") or {}
        neg = expr.startswith("not ")
        key = expr[4:].strip() if neg else expr
        key = key.split(".")[-1]
        val = bool(ctx.get(key, False))
        return (not val) if neg else val

    def dim_of(self, eid):
        ds = sorted(self.ev_dim.get(eid, []))
        return "/".join(ds) if ds else None

    def add(self, *a, **kw):
        self.findings.append(Finding(*a, **kw))

    # ---------------------------------------------------------------- 求解
    def solve(self):
        """跑派生规则至不动点。已声明的 derived 节点做比对，未声明的直接生成。"""
        rules = self.p.get("rules") or []

        # 环检测：可研中存在真实回环（面积→设备机房→面积），所以不判致命，
        # 但必须显式暴露并要求人工设定切断点，不能静默迭代了事。
        for cyc in detect_cycles(rules):
            self.add("CYCLE", "warning", " → ".join(cyc),
                     f"派生依赖存在回环，长度 {len(cyc) - 1}",
                     action="human_review",
                     detail={"环路径": " → ".join(cyc),
                             "处置": "需人工设定切断点与迭代收敛条件，或拆分为两个独立节点"})

        pending = [r for r in rules if r["operator"] in ("index", "rate", "aggregate")]
        for _round in range(20):
            progressed = False
            still = []
            for r in pending:
                try:
                    val, used = evaluate(r["formula"], self.nodes)
                except Unresolved as e:
                    still.append(r)
                    continue
                except Exception as e:
                    self.add("C2", "error", r["target"],
                             f"规则 {r['id']} 表达式非法：{e}",
                             dimension=r.get("serves"), action="human_review")
                    continue
                progressed = True
                self.trace[r["target"]] = {"rule": r["id"], "used": used, "value": val}
                tgt = r["target"]
                if tgt in self.nodes:
                    before = len(self.findings)
                    self._check_derivation(r, val)
                    if len(self.findings) == before:
                        self.passed.append(f"C2 {r['id']}: {tgt} 重算一致 ({round(val, 4)})")
                else:
                    self.nodes[tgt] = {"value": val, "unit": r.get("unit"),
                                       "provenance": "E4_derived",
                                       "source": f"rule:{r['id']}"}
            pending = still
            if not progressed:
                break

        # 仍未解出 = 输入缺失，按 on_missing 分诊
        for r in pending:
            try:
                evaluate(r["formula"], self.nodes)
            except Unresolved as e:
                missing = str(e)
                policy = r.get("on_missing", "ask")
                action = {"ask": "ask_client", "error": "human_review",
                          "skip": "human_review"}[policy]
                self.add("GAP", "error" if policy == "error" else "warning",
                         missing,
                         f"规则 {r['id']} 缺输入节点 `{missing}`，无法计算 {r['target']}",
                         dimension=r.get("serves"), action=action,
                         detail={"rule": r["id"], "target": r["target"]})

    def _check_derivation(self, rule, computed):
        """C2 派生约束：声明值 vs 重算值 + 单位一致性。"""
        tgt = rule["target"]
        declared = self.nodes[tgt]
        tol = rule.get("tolerance", self.deriv["rule_schema"]["fields"]["tolerance"]["default"])
        if "value" not in declared or declared["value"] in (None, "", "UNKNOWN"):
            # 派生节点还没有声明值 —— 算得出来但图上没写。
            # 以前这里直接 KeyError 崩掉，整份体检一条结果都出不来，
            # 而调用方（语料库入库）只看到「体检未能完成」，
            # 看不出是哪个节点的问题。崩在校验器里比校验不出问题更糟。
            self.add("C2", "warning", tgt,
                     f"派生节点无声明值，规则 {rule['id']} 重算得 {round(computed, 4)}"
                     f"——把它写回图上，否则正文引用时无值可注",
                     dimension=rule.get("serves"), action="human_review")
            return
        dv = declared["value"]
        if isinstance(dv, str) or isinstance(dv, bool):
            self.add("C2", "warning", tgt,
                     f"派生节点声明值不是数字（{dv!r}），跳过复算",
                     dimension=rule.get("serves"), action="human_review")
            return
        denom = abs(dv) if dv else 1.0
        dev = abs(computed - dv) / denom
        if dev > tol:
            self.add("C2", "error", tgt,
                     f"派生不符：声明 {dv}，按规则 {rule['id']} 重算 {round(computed, 4)}"
                     f"（偏差 {dev:.2%} > 容差 {tol:.2%}）",
                     dimension=rule.get("serves"), action="human_review",
                     detail={"formula": rule["formula"], "declared": dv,
                             "computed": round(computed, 4)})
        if rule.get("unit") and declared.get("unit") and rule["unit"] != declared["unit"]:
            self.add("C2", "error", tgt,
                     f"单位不符：声明 {declared['unit']}，规则 {rule['id']} 产出 {rule['unit']}",
                     dimension=rule.get("serves"), action="human_review")
        # index/rate/lookup 必须有 basis（E2 证据）
        if rule["operator"] in ("index", "rate", "lookup") and not rule.get("basis"):
            self.add("C5", "error", tgt,
                     f"规则 {rule['id']} 使用了指标/费率但未绑定依据（Norm）",
                     dimension=rule.get("serves"), action="web_search")

    # ---------------------------------------------------------------- C1
    def c1_identity(self):
        """恒等约束：同一节点在全文各出现处的值必须一致。"""
        for node, occs in (self.p.get("occurrences") or {}).items():
            vals = {}
            for o in occs:
                vals.setdefault(o["value"], []).append(o["section"])
            if len(vals) > 1:
                majority = max(vals.items(), key=lambda kv: len(kv[1]))
                minority = {v: s for v, s in vals.items() if v != majority[0]}
                self.add("C1", "error", node,
                         f"同一节点全文取值不一致：{list(vals.keys())}",
                         action="human_review",
                         detail={"分布": {str(v): s for v, s in vals.items()},
                                 "多数值": majority[0],
                                 "疑似笔误": {str(v): s for v, s in minority.items()}})
            elif node in self.nodes and list(vals)[0] != self.nodes[node]["value"]:
                self.add("C1", "error", node,
                         f"正文取值 {list(vals)[0]} 与图中权威值 {self.nodes[node]['value']} 不符",
                         action="human_review")

    # ---------------------------------------------------------------- C3
    def c3_balance(self):
        """平衡约束：硬等式 + 二维分解行列双向校验。"""
        for r in self.p.get("rules") or []:
            if r.get("hard_constraint"):
                lhs, rhs = [s.strip() for s in r["hard_constraint"].split("==")]
                try:
                    lv, _ = evaluate(lhs, self.nodes)
                    rv, _ = evaluate(rhs, self.nodes)
                except Unresolved as e:
                    self.add("C3", "warning", str(e),
                             f"硬约束 {r['hard_constraint']} 无法校验，缺节点 `{e}`",
                             dimension=r.get("serves"), action="ask_client")
                    continue
                if abs(lv - rv) > 1e-6:
                    self.add("C3", "error", r["target"],
                             f"硬约束不成立：{lhs}={lv} ≠ {rhs}={rv}",
                             dimension=r.get("serves"), action="human_review")
                else:
                    self.passed.append(f"C3 {r['id']}: 硬约束成立 {r['hard_constraint']} = {lv}")

            if r["operator"] == "allocate":
                before = len(self.findings)
                self._check_allocation(r)
                if len(self.findings) == before:
                    self.passed.append(f"C3 {r['id']}: {r['target']} 行/列/全表三向合计平衡")

    def _check_allocation(self, r):
        m = r["matrix"]
        vals, rows, cols = m["values"], m["rows"], m["cols"]
        # 行合计
        for row in rows:
            s = sum(vals[row][c] for c in cols)
            ref = m.get("row_totals", {}).get(row)
            if ref:
                try:
                    rv, _ = evaluate(ref, self.nodes)
                except Unresolved as e:
                    self.add("C3", "warning", ref, f"分解校验缺节点 `{e}`",
                             dimension=r.get("serves"), action="ask_client")
                    continue
                if abs(s - rv) > 1e-6:
                    self.add("C3", "error", f"{r['target']}[{row}]",
                             f"行合计不平：{row} 各年度和 {s} ≠ 总额 {rv}",
                             dimension=r.get("serves"), action="human_review")
        # 列合计
        for col in cols:
            s = sum(vals[row][col] for row in rows)
            ref = m.get("col_totals", {}).get(col)
            if ref is not None:
                cv = ref if isinstance(ref, (int, float)) else evaluate(ref, self.nodes)[0]
                if abs(s - cv) > 1e-6:
                    self.add("C3", "error", f"{r['target']}[{col}]",
                             f"列合计不平：{col} 各来源和 {s} ≠ 年度合计 {cv}",
                             dimension=r.get("serves"), action="human_review")
        # 总计
        grand = sum(vals[row][c] for row in rows for c in cols)
        if m.get("grand_total"):
            try:
                gv, _ = evaluate(m["grand_total"], self.nodes)
                if abs(grand - gv) > 1e-6:
                    self.add("C3", "error", r["target"],
                             f"全表合计不平：{grand} ≠ {m['grand_total']}={gv}",
                             dimension=r.get("serves"), action="human_review")
            except Unresolved as e:
                self.add("C3", "warning", str(e), f"全表合计缺节点 `{e}`",
                         dimension=r.get("serves"), action="ask_client")
        # 年度范围须落在工期内
        dur = self.p.get("project", {}).get("duration", {})
        if dur.get("start") and dur.get("end"):
            y0, y1 = str(dur["start"])[:4], str(dur["end"])[:4]
            out = [c for c in cols if not (y0 <= str(c) <= y1)]
            if out:
                self.add("C3", "error", r["target"],
                         f"分解年度 {out} 超出工期 {y0}~{y1}",
                         dimension=r.get("serves"), action="human_review")

    # ---------------------------------------------------------------- C4
    def c4_argument(self):
        """论证完备性：Toulmin 六元组 + 维度覆盖 + 复述落实 + 结论可追溯。"""
        claims = self.p.get("claims") or {}
        dims = self.argu["feasibility_frame"]["dimensions"]

        for key, c in claims.items():
            arg = c.get("argument") or {}
            # C4a 四项必填
            for f in ("claim", "grounds", "warrant", "backing"):
                if not arg.get(f):
                    cn = self.argu["argument_unit"]["fields"][f]["cn"]
                    tag = {"grounds": "裸论断", "warrant": "断链论证"}.get(f, "论证不完整")
                    self.add("C4a", "error", key,
                             f"[{tag}] 论证缺「{cn}」({f})",
                             dimension=(c.get("serves") or [None])[0],
                             action="web_search" if f == "backing" else "ask_client")
            # qualifier 存在但 rebuttal 缺失 → 提示
            if arg.get("qualifier") and not arg.get("rebuttal"):
                self.add("C4a", "warning", key,
                         "已声明限定条件但未写反驳与例外，评审易被追问",
                         dimension=(c.get("serves") or [None])[0], action="human_review")

        # C4b 维度覆盖（按 applicability 过滤）
        covered = {d for c in claims.values() for d in (c.get("serves") or [])}
        declared_na = self.p.get("not_applicable") or {}
        for d, spec in dims.items():
            if not self._applicable(spec):
                # C4e 不适用的维度必须显式声明理由，不得静默跳过
                if d not in declared_na:
                    self.add("C4e", "error", d,
                             f"维度 {d}（{spec['cn']}）按项目属性不适用，"
                             f"但未在 not_applicable 中显式声明理由",
                             dimension=d, action="human_review")
                else:
                    self.passed.append(f"C4e {d}: 已声明不适用 —— {declared_na[d]}")
                continue
            if d not in covered:
                self.add("C4b", "error", d,
                         f"可行性维度 {d}（{spec['cn']}）没有任何论证支撑",
                         dimension=d, action="ask_client")

        # C4f 稳健性条件必填
        for key, c in claims.items():
            if not c.get("robustness_required"):
                continue
            if not (c.get("argument") or {}).get("robustness"):
                self.add("C4f", "error", key,
                         "论点建立在预测值或财务指标之上，但未给出敏感因素与临界值",
                         dimension=(c.get("serves") or [None])[0], action="ask_client")

        # 维度依赖：上游不成立则下游悬空
        status = self.p.get("dimension_status") or {}
        for d, spec in dims.items():
            for up in spec.get("depends_on") or []:
                if status.get(up) == "unsound" and status.get(d) == "sound":
                    self.add("C4b", "error", d,
                             f"{d} 声明成立，但其依赖的 {up} 不成立，结论悬空",
                             dimension=d, action="human_review")

        # C4c 复述落实
        sections = {s["id"]: s for s in (self.p.get("sections") or [])}
        for key, c in claims.items():
            for sid in c.get("restated_in") or []:
                if sid not in sections:
                    self.add("C4c", "error", key, f"复述目标章节 {sid} 不存在",
                             action="human_review")
                elif key not in (sections[sid].get("restates") or []):
                    self.add("C4c", "error", key,
                             f"论断声明需在 {sid} 复述，但该章 restates 未包含它",
                             dimension=(c.get("serves") or [None])[0],
                             action="human_review")

        # C4d 纯派生章节不得引入新事实
        for s in self.p.get("sections") or []:
            if s.get("derived_only") and s.get("provides"):
                self.add("C4d", "error", s["id"],
                         f"纯派生章节不得 provides 新节点：{s['provides']}",
                         action="human_review")
            if not s.get("serves"):
                self.add("C4b", "warning", s["id"],
                         "该章节不服务于任何可行性维度，考虑删除或补充 serves",
                         action="human_review")

    # ---------------------------------------------------------------- C5
    def c5_evidence(self):
        """证据充分性：来源必填项、时效、类比证据不得独立支撑。"""
        ev = self.p.get("evidence") or {}
        today = self.p.get("as_of")
        today = datetime.date.fromisoformat(str(today)) if today else datetime.date.today()
        windows = self.argu["constraints"]["C5_evidence_sufficiency"]["staleness_window"]

        def days(s):
            return int(str(s).rstrip("d"))

        for eid, e in ev.items():
            pv = e.get("provenance")
            if pv == "E1_given" and not e.get("provider"):
                self.add("C5c", "error", eid, "E1 客户给定证据缺提供方，无法签认",
                         dimension=self.dim_of(eid), action="ask_client")
            if pv == "E3_external":
                for f, cn in (("url", "URL"), ("published_at", "发布日期"),
                              ("retrieved_at", "检索日期")):
                    if not e.get(f):
                        self.add("C5c", "error", eid, f"E3 外部证据缺{cn}，不可溯源",
                                 dimension=self.dim_of(eid), action="web_search")
            if pv in ("E2_normative", "E3_external") and e.get("retrieved_at"):
                age = (today - datetime.date.fromisoformat(str(e["retrieved_at"]))).days
                lim = days(windows["E2" if pv == "E2_normative" else "E3"])
                if age > lim:
                    self.add("C5b", "error", eid,
                             f"证据已过时效窗口（检索于 {age} 天前，上限 {lim} 天），须重新核查",
                             dimension=self.dim_of(eid), action="web_search")
            if pv == "E2_normative" and e.get("superseded_by"):
                self.add("C5b", "error", eid,
                         f"所引规范已被 {e['superseded_by']} 替代，必须更新",
                         dimension=self.dim_of(eid), action="web_search")
            if pv == "E6_administrative":
                for f, cn in (("doc_no", "文号"), ("issuer", "发文机关"),
                              ("approved_at", "批复日期"), ("valid_until", "有效期")):
                    if not e.get(f):
                        self.add("C5e", "error", eid, f"E6 行政批复缺{cn}",
                                 dimension=self.dim_of(eid), action="ask_client")
                if e.get("deviates") and not e.get("adjustment"):
                    self.add("C5f", "error", eid,
                             "建设内容/规模/投资相对批复发生变化，但未逐项列出调整情况",
                             dimension=self.dim_of(eid), action="ask_client")
            if pv == "E5_analogical" and not e.get("comparability"):
                self.add("C5a", "error", eid, "E5 类比证据未说明可比性条件",
                         dimension=self.dim_of(eid), action="ask_client")

        # C5a 类比不得独立支撑
        for key, c in (self.p.get("claims") or {}).items():
            g = c.get("argument", {}).get("grounds") or []
            if g and all(ev.get(x, {}).get("provenance") == "E5_analogical" for x in g):
                self.add("C5a", "error", key,
                         "论据全部为类比工程（E5），不足以独立支撑论点",
                         dimension=(c.get("serves") or [None])[0], action="ask_client")

    # ---------------------------------------------------------------- C5g
    def c5g_norm_registry(self):
        """规范引用与登记册比对。引错标准名称是可研的高频低级错误。"""
        if not self.norms:
            return
        ev = self.p.get("evidence") or {}
        matched = 0
        for eid, e in ev.items():
            if not isinstance(e, dict) or e.get("provenance") != "E2_normative":
                continue
            content = str(e.get("content") or "")
            # 编号定身份，名称查写法——两件事要分开做。
            # 先按编号匹配上就不再看名称，会漏掉「名字写错但编号对」这种最常见的情况。
            hit = None
            for nid, n in self.norms.items():
                code = str(n.get("code") or "")
                if code and code in content:
                    hit = (nid, n)
                    break
            if not hit:
                for nid, n in self.norms.items():
                    title = str(n.get("title") or "")
                    if title and title in content:
                        hit = (nid, n)
                        break
            if not hit:
                for nid, n in self.norms.items():
                    for alias in (n.get("aliases_seen_in_practice") or []):
                        if alias and alias in content:
                            hit = (nid, n)
                            break
                    if hit:
                        break

            if not hit:
                self.add("C5g", "warning", eid,
                         "所引规范未登记在 references/norms.yaml",
                         dimension=self.dim_of(eid), action="human_review",
                         detail={"内容": content[:60],
                                 "为何要登记": "未登记的规范无法纳入时效核验调度"})
                continue

            nid, n = hit
            title = str(n.get("title") or "")
            if title and title not in content:
                bad_alias = next((a for a in (n.get("aliases_seen_in_practice") or [])
                                  if a and a in content), None)
                if bad_alias:
                    self.add("C5g", "error", eid,
                             f"规范名称写法有误：报告写「{bad_alias}」，"
                             f"登记册为《{title}》（{n.get('code')}）",
                             dimension=self.dim_of(eid), action="human_review",
                             detail={"说明": (n.get("correct_title_note") or
                                            "引错标准名称在评审中会被直接指出").strip()[:200]})

            matched += 1
            st = n.get("status")
            if st in ("superseded", "repealed"):
                self.add("C5g", "error", eid,
                         f"所引规范状态为 {st}"
                         + (f"，已被 {n.get('superseded_by')} 替代" if n.get("superseded_by") else ""),
                         dimension=self.dim_of(eid), action="web_search")
            elif st == "in_use_unverified":
                self.add("C5g", "warning", eid,
                         f"规范 {n.get('code')} 的现行状态未经查证（登记册标注 in_use_unverified）",
                         dimension=self.dim_of(eid), action="web_search",
                         detail={"核验要点": (n.get("verify") or {}).get("questions", [])[:3]})
        if matched:
            self.passed.append(f"C5g: {matched} 条规范引用已在登记册中匹配")

    # ---------------------------------------------------------------- C6
    def c6_reference(self):
        """指称一致性：同一术语在不同章节必须绑定同一实体集合。"""
        bind = {}
        for s in self.p.get("sections") or []:
            for term, ents in (s.get("terms") or {}).items():
                bind.setdefault(term, {})[s["id"]] = set(ents)
        for term, per_sec in bind.items():
            sets = {frozenset(v) for v in per_sec.values()}
            if len(sets) > 1:
                self.add("C6", "error", term,
                         f"术语「{term}」在不同章节指称的实体集合不一致",
                         action="human_review",
                         detail={sid: sorted(v) for sid, v in per_sec.items()})

    # ---------------------------------------------------------------- C7
    def _outline_id(self):
        """按 funding_regime 选法定大纲。这是分诊输入决定检查口径的落点。"""
        regime = (self.p.get("project") or {}).get("funding_regime")
        return {"政府投资": "outline-gov-2023", "企业投资": "outline-ent-2023",
                "混合投资": "outline-gov-2023"}.get(regime)

    def c7_statutory_coverage(self):
        """法定覆盖：outline 必须覆盖法定大纲 mandatory_coverage 的全部 items。"""
        anchor = self.core.get("regulatory_anchor") or {}
        cov = anchor.get("mandatory_coverage") or {}
        regime = (self.p.get("project") or {}).get("funding_regime")
        if not regime:
            self.add("C7", "error", "project.funding_regime",
                     "未声明由谁投资，无法确定适用哪本法定大纲，C7 无法执行",
                     action="ask_client")
            return
        self.passed.append(f"C7 口径: {regime} → {self._outline_id()}")
        if not cov:
            return
        sections = self.p.get("sections") or []
        if not sections:
            return
        # 章节通过 covers 字段声明它承载了哪些法定 item
        carried = set()
        for s in sections:
            carried |= set(s.get("covers") or [])
        missing_ch = []
        for ch, spec in cov.items():
            items = spec.get("items") or []
            miss = [i for i in items if i not in carried]
            if miss:
                missing_ch.append((ch, spec.get("title"), miss))
        for ch, title, miss in missing_ch:
            self.add("C7", "error", f"{ch} {title}",
                     f"法定大纲要求的内容无章节承载：{miss}",
                     action="human_review",
                     detail={"anchor": anchor.get("authority", {}).get("doc")})
        if not missing_ch:
            total = sum(len(v.get("items") or []) for v in cov.values())
            self.passed.append(f"C7: 法定大纲 {len(cov)} 章 {total} 项内容全部有章节承载")

        # C7b 空壳覆盖——防止靠声明 covers 骗过 C7
        shell = 0
        for s_ in sections:
            if not s_.get("covers"):
                continue
            status = s_.get("content_status", "sourced")
            if status == "missing":
                self.add("C7b", "error", s_["id"],
                         f"章节声明承载 {s_['covers']}，但无实际内容来源（空壳覆盖）",
                         action="ask_client",
                         detail={"标题": s_.get("title")})
                shell += 1
            elif status == "partial":
                self.add("C7b", "warning", s_["id"],
                         f"章节内容不完整：{s_.get('gap', '未说明缺口')}",
                         action="ask_client", detail={"标题": s_.get("title")})
        if not shell:
            self.passed.append("C7b: 无空壳覆盖章节")


    # ---------------------------------------------------------------- C8
    def c8_traceable(self):
        """取值可溯源。不得编造这条规则里，唯一可机检的那一部分。

        它不能证明有 from 的数是对的，但能保证每个数都指得回一份材料的一页。
        编造若发生，必然发生在"没有 from 的那一批"里——所以那一批要被点名。
        """
        mats = self.p.get("materials")
        if not mats:
            return                       # 图尚未进入素材摄入阶段，不适用
        reg = {m.get("id") for m in mats if isinstance(m, dict)}
        unsourced = []
        bad = 0
        for nid, n in self.nodes.items():
            fr = n.get("from")
            if fr:
                if not isinstance(fr, dict):
                    self.add("C8", "error", nid, "from 不是映射结构，无法定位来源",
                             action="human_review")
                    bad += 1
                elif fr.get("material") not in reg:
                    self.add("C8", "error", nid,
                             f"from.material「{fr.get('material')}」未在 materials 段登记",
                             action="human_review",
                             detail={"已登记素材": sorted(x for x in reg if x)})
                    bad += 1
                elif not fr.get("locator"):
                    self.add("C8", "error", nid,
                             "from 缺 locator（页码/表号/图号），视同未抽取",
                             action="ask_client")
                    bad += 1
            elif n.get("provenance") in ("E1_given", "E6_administrative"):
                unsourced.append(nid)
        if unsourced:
            self.add("C8", "warning", "取值溯源",
                     f"{len(unsourced)} 个客户给定/批复类取值没有 from，无法倒查出自哪份材料的哪一页",
                     action="ask_client",
                     detail={"节点": sorted(unsourced)[:20],
                             "处置": "补 from（素材 id + 页码/表号），或降级为待确认"})
        if not bad and not unsourced:
            self.passed.append("C8: 全部客户给定取值都能指回具体材料的具体位置")

    # ---------------------------------------------------------------- C10
    def c10_external_fit(self):
        """外部证据须经适配性评估与客户确认。

        缺 adopted_by 意味着这条是 agent 自己塞进去的。本 skill 的可信度
        建立在"事实和依据都由人确认过"之上，这一条是它在外部证据侧的落点。
        """
        ev = self.p.get("evidence") or {}
        loc = str((self.p.get("project") or {}).get("location") or "")
        used = set()
        for c in (self.p.get("claims") or {}).values():
            arg = (c or {}).get("argument") or {}
            used |= set(arg.get("warrant") or []) | set(arg.get("backing") or [])
        no_fit, no_adopt = [], []
        for eid, e in ev.items():
            if not isinstance(e, dict):
                continue
            if e.get("provenance") not in ("E2_normative", "E3_external", "E5_analogical"):
                continue
            juris = e.get("jurisdiction")
            if juris and loc and not any(
                    str(j) in ("全国", "国家") or str(j) in loc or loc in str(j) for j in juris):
                self.add("C10b", "error", eid,
                         f"效力地域 {juris} 不含项目所在地「{loc}」——跨地域套用地方规定",
                         action="human_review")
            if eid not in used:
                continue
            if not e.get("fit"):
                no_fit.append(eid)
            if not e.get("adopted_by"):
                no_adopt.append(eid)
        if no_adopt:
            self.add("C10", "error", "外部依据采纳",
                     f"{len(no_adopt)} 条被引作保证/支撑的外部依据没有 adopted_by，"
                     f"即未经客户确认",
                     action="ask_client",
                     detail={"证据": sorted(no_adopt)[:20],
                             "处置": "用 fit_rank.py 排序后交客户勾选，记录确认人与确认日期"})
        elif no_fit:
            self.add("C10", "warning", "外部依据适配性",
                     f"{len(no_fit)} 条外部依据未记录适配性评估（六维分值）",
                     action="web_search", detail={"证据": sorted(no_fit)[:20]})
        else:
            if ev:
                self.passed.append("C10: 外部依据均经适配性评估并由客户确认")

    # ---------------------------------------------------------------- C11
    def c11_routing(self):
        """来源路由不得违反。见 references/provenance-routing.yaml。"""
        targets = {r.get("target") for r in (self.p.get("rules") or [])
                   if isinstance(r, dict)}
        handfilled = [nid for nid, n in self.nodes.items()
                      if n.get("provenance") == "E4_derived" and nid not in targets]
        if handfilled:
            self.add("C11", "error", "手填派生值",
                     f"{len(handfilled)} 个节点声明为 E4_derived 但图中无对应规则",
                     action="human_review",
                     detail={"节点": sorted(handfilled)[:20],
                             "为什么是错的": "手填派生值等于切断派生链，C2 从此对它失效",
                             "处置": "补规则；确实是客户给的就改标 E1_given"})
        declared = [nid for nid, n in self.nodes.items()
                    if n.get("provenance") == "E1_given" and nid in targets
                    and not n.get("declared_vs_recomputed")]
        if declared:
            self.add("C11", "warning", "口径待裁决",
                     f"{len(declared)} 个节点既标为客户给定、又是某条规则的 target",
                     action="human_review",
                     detail={"节点": sorted(declared)[:20],
                             "处置": "这是边界情形 E2：两个值都留着由 C2 比对，"
                                     "并标 declared_vs_recomputed: true 表示已知情"})
        if not handfilled and not declared:
            self.passed.append("C11: 来源路由无违规（无手填派生值）")


    # ---------------------------------------------------------------- C14
    def c14_placeholder(self):
        """回退检索得来的参照值，必须诚实地标着自己是参照值。

        它与编造的分界线全在标注上：标 E1_given 就等于宣称"这是本项目的实测值"，
        而客户从没说过这个数——那不只是数字可能错，是把责任悄悄记到了客户头上。
        """
        bad = 0
        placeholders = []
        for nid, n in self.nodes.items():
            if not n.get("is_placeholder"):
                # E5 类比值不得直接充当取值
                if n.get("provenance") == "E5_analogical" and not n.get("benchmark_only"):
                    self.add("C14", "error", nid,
                             "E5 类比值被当作本项目的取值使用",
                             action="ask_client",
                             detail={"为什么不行": "同类项目的值只能佐证合理性，不能充当取值",
                                     "处置": "本项目的实定值走 ASK；确要保留对标，标 benchmark_only: true"})
                    bad += 1
                continue
            placeholders.append(nid)
            if n.get("provenance") == "E1_given":
                self.add("C14", "error", nid,
                         "参照值被标成 E1_given —— 等于宣称这是客户给定的实测值",
                         action="human_review",
                         detail={"处置": "改标真实来源等级（E2_normative / E3_external / E5_analogical）",
                                 "为什么要紧": "E1 承载的是责任归属。客户从没说过这个数"})
                bad += 1
            if not n.get("adopted_by"):
                self.add("C14", "error", nid,
                         "参照值没有 adopted_by —— 未经客户选择",
                         action="ask_client",
                         detail={"处置": "用 fit_rank.py --mode value 出候选表请客户勾选"})
                bad += 1
            if not n.get("refine_when"):
                self.add("C14", "warning", nid,
                         "参照值未写明何时替换成实定值",
                         action="ask_client",
                         detail={"示例": "设计单位出具能耗计算书后"})
        if placeholders and not bad:
            self.add("C14", "info", "参照值清单",
                     f"{len(placeholders)} 个节点当前用的是参照值，出稿前须逐条过一遍",
                     action="human_review",
                     detail={"节点": sorted(placeholders)[:20],
                             "出口": "要么已被实定值替换，要么客户确认「就按参照值出稿」——不允许静默保留"})
        if not placeholders and not bad:
            self.passed.append("C14: 无参照值占位，也无 E5 被当作取值")

    # ---------------------------------------------------------------- run
    def run(self):
        self.solve()
        self.c7_statutory_coverage()
        self.c1_identity()
        self.c3_balance()
        self.c4_argument()
        self.c5_evidence()
        self.c5g_norm_registry()
        self.c6_reference()
        self.c8_traceable()
        self.c10_external_fit()
        self.c11_routing()
        self.c14_placeholder()
        return self.findings


# =============================================================================
# 报告
# =============================================================================

SEV_ORDER = {"error": 0, "warning": 1, "info": 2}
ACTION_CN = {"ask_client": "→ 客户提问", "web_search": "→ web 检索核查",
             "human_review": "→ 人工裁决"}


def report(findings, validator):
    lines = []
    ok = [f for f in findings if f.severity == "error"]
    warn = [f for f in findings if f.severity == "warning"]
    lines.append("=" * 74)
    lines.append("可行性研究报告本体图谱 —— 一致性检查报告")
    lines.append("=" * 74)
    lines.append(f"错误 {len(ok)} 项 / 警告 {len(warn)} 项 / 合计 {len(findings)} 项")
    lines.append("")

    for f in sorted(findings, key=lambda x: (SEV_ORDER[x.severity], x.code)):
        head = f"[{f.code}·{f.severity}] {f.subject}"
        if f.dimension:
            head += f"  ({f.dimension})"
        lines.append(head)
        lines.append(f"    {f.message}")
        if f.detail:
            for k, v in f.detail.items():
                lines.append(f"      {k}: {v}")
        if f.action:
            lines.append(f"    {ACTION_CN.get(f.action, f.action)}")
        lines.append("")

    # 缺口分诊
    asks = [f for f in findings if f.action == "ask_client"]
    webs = [f for f in findings if f.action == "web_search"]
    if asks or webs:
        lines.append("-" * 74)
        lines.append("缺口分诊")
        lines.append("-" * 74)
        if asks:
            lines.append(f"客户提问清单（{len(asks)} 项）：")
            for f in asks:
                lines.append(f"  · [{f.dimension or '-'}] {f.subject} —— {f.message}")
        if webs:
            lines.append(f"web 检索任务（{len(webs)} 项）：")
            for f in webs:
                lines.append(f"  · [{f.dimension or '-'}] {f.subject} —— {f.message}")
        lines.append("")

    if validator.passed:
        lines.append("-" * 74)
        lines.append(f"通过项（{len(validator.passed)} 项）")
        lines.append("-" * 74)
        for t in validator.passed:
            lines.append(f"  ✓ {t}")
        lines.append("")

    # 派生轨迹
    if validator.trace:
        lines.append("-" * 74)
        lines.append("派生轨迹（E4 证据，供审计）")
        lines.append("-" * 74)
        for tgt, t in validator.trace.items():
            lines.append(f"  {tgt} = {round(t['value'], 4)}   [{t['rule']}] ← {t['used']}")
    return "\n".join(lines)


@guard
def main(argv):
    if len(argv) < 2:
        print("用法: validators.py <project.yaml> [--json out.json]")
        return 2
    core, argu, deriv, norms = load_all()
    try:
        proj = yaml.safe_load(Path(argv[1]).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"实例图 YAML 解析失败：{e}")
        return 2

    # --- schema 先跑。结构不合法时不给出任何"通过"的假象 ---
    sv = SchemaValidator(proj, core, argu)
    sfindings = sv.run()
    if sfindings:
        print(report_schema(sfindings))
        print()
    if sv.fatal:
        return 2

    v = Validator(core, argu, deriv, proj, norms)
    findings = v.run()
    print(report(findings, v))

    if "--json" in argv:
        out = Path(argv[argv.index("--json") + 1])
        out.write_text(json.dumps(
            {"schema": [f.to_dict() for f in sfindings],
             "findings": [f.to_dict() for f in findings],
             "passed": v.passed,
             "trace": v.trace},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 已写入 {out}")

    bad = any(f.severity == "error" for f in findings) or \
          any(f.severity in ("error", "fatal") for f in sfindings)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
