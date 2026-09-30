#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实例图 schema 校验 (S1-S6)

为什么单独一层：在结构不合法的图上跑 C1-C7，产出的"通过"是误导性的。
故障注入实测过——把某个节点的 value 写成字符串「一百」，
检查器不报错、不计算、只输出一条"通过项"。这叫漏检，比误报危险得多。

所以：schema 先跑，致命错误直接中止语义检查，不给出任何"通过"的假象。

分级：
  fatal  结构崩坏，无法继续（缺 project 段、nodes 不是映射…）
  error  必须修复，但可继续检查其余部分
  warning 可疑，交人工判断
"""

import ast
import re

NUMERIC_UNITS_EXEMPT = {"", None}

# select：方案比选。设计方案章里大半结论是选出来的，不是算出来的——
# 没有这个算子，那部分推演逻辑在图上就无处安放。
VALID_OPERATORS = {"index", "aggregate", "allocate", "rate", "lookup",
                   "identity", "forecast", "select"}
FORMULA_OPERATORS = {"index", "aggregate", "rate", "forecast"}


class SchemaFinding:
    def __init__(self, code, severity, subject, message, hint=None):
        self.code = code
        self.severity = severity      # fatal / error / warning
        self.subject = subject
        self.message = message
        self.hint = hint

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if v}


# lookup 是 rule_schema 的六个算子之一，但表达式解析器原先不认它——
# 于是「lookup(建筑高度, 使用性质)」里的 lookup 被当成了节点名，
# 规范判定类的推演链一律报断。算子表和表达式表要对齐。
FUNC_NAMES = {"sum", "round", "min", "max", "abs", "ceil", "floor",
              "solve", "forecast", "lookup"}


def _refs_in_formula(expr):
    """提取表达式引用的全部节点名。不求值，只解析。函数名不是节点。"""
    refs = []

    def walk(n):
        if isinstance(n, ast.Call):
            # 函数名不计入节点引用，只走实参
            if not (isinstance(n.func, ast.Name) and n.func.id in FUNC_NAMES):
                walk(n.func)
            for a in n.args:
                walk(a)
            return
        if isinstance(n, ast.Attribute):
            parts = []
            cur = n
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
                refs.append(".".join(reversed(parts)))
                return
        elif isinstance(n, ast.Name):
            refs.append(n.id)
            return
        for c in ast.iter_child_nodes(n):
            walk(c)

    walk(ast.parse(expr, mode="eval"))
    return refs


class SchemaValidator:

    def __init__(self, proj, core=None, argu=None, outline=None):
        self.p = proj if isinstance(proj, dict) else {}
        self.core = core or {}
        self.argu = argu or {}
        self.outline = outline or {}
        self.findings = []

    def add(self, code, sev, subject, message, hint=None):
        self.findings.append(SchemaFinding(code, sev, subject, message, hint))

    @property
    def fatal(self):
        return [f for f in self.findings if f.severity == "fatal"]

    # ---------------------------------------------------------------- S1
    def s1_structure(self):
        """顶层结构与必需字段。"""
        if not isinstance(self.p, dict) or not self.p:
            self.add("S1", "fatal", "<root>", "实例图为空或不是映射结构",
                     "参考 references/fixture_cug2024.yaml 的结构")
            return

        proj = self.p.get("project")
        if not isinstance(proj, dict):
            self.add("S1", "fatal", "project", "缺少 project 段或其不是映射结构",
                     "project 段须含 id、funding_regime 等分诊变量")
            return

        if not proj.get("id"):
            self.add("S1", "error", "project.id", "缺少项目标识")

        regime = proj.get("funding_regime")
        allowed = {"政府投资", "企业投资", "混合投资"}
        if not regime:
            self.add("S1", "error", "project.funding_regime",
                     "未声明由谁投资，无法确定适用哪本法定大纲",
                     "分诊阶段必问，且无法从项目名称推断")
        elif regime not in allowed:
            self.add("S1", "error", "project.funding_regime",
                     f"取值 {regime!r} 不在受控词表内", f"应为 {allowed} 之一")

        for seg in ("nodes", "evidence", "claims"):
            v = self.p.get(seg)
            if v is not None and not isinstance(v, dict):
                self.add("S1", "fatal", seg, f"{seg} 段必须是映射，实际是 {type(v).__name__}")
        for seg in ("rules", "sections"):
            v = self.p.get(seg)
            if v is not None and not isinstance(v, list):
                self.add("S1", "fatal", seg, f"{seg} 段必须是列表，实际是 {type(v).__name__}")

    # ---------------------------------------------------------------- S2
    def s2_node_types(self):
        """节点类型。这是最容易静默漏检的一层。"""
        nodes = self.p.get("nodes") or {}
        if not isinstance(nodes, dict):
            return
        prov_vocab = set(
            ((self.core.get("vocabularies") or {}).get("evidence_provenance") or {}).get("values")
            or ["E1_given", "E2_normative", "E3_external", "E4_derived",
                "E5_analogical", "E6_administrative"])

        for key, n in nodes.items():
            if not isinstance(n, dict):
                self.add("S2", "error", key, f"节点必须是映射，实际是 {type(n).__name__}")
                continue

            if "value" not in n:
                self.add("S2", "error", key, "节点缺 value")
                continue

            v = n["value"]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                self.add("S2", "error", key,
                         f"value 必须是数字，实际是 {type(v).__name__}: {v!r}",
                         "写成字符串会导致该节点被静默跳过——所有依赖它的派生都不会被校验")
                continue

            if not n.get("unit"):
                self.add("S2", "error", key, "节点缺 unit",
                         "无单位则 C2 的单位一致性检查失效")

            prov = n.get("provenance")
            if prov and prov not in prov_vocab:
                self.add("S2", "error", key, f"provenance {prov!r} 不在受控词表内",
                         f"应为 {sorted(prov_vocab)} 之一")

            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", key):
                self.add("S2", "warning", key, "节点名不是合法的点分标识符",
                         "非法标识符无法在派生公式中被引用")

    # ---------------------------------------------------------------- S3
    def s3_rules(self):
        """规则结构与公式可解析性。"""
        rules = self.p.get("rules") or []
        if not isinstance(rules, list):
            return
        nodes = self.p.get("nodes") or {}
        seen_ids = set()

        for i, r in enumerate(rules):
            where = f"rules[{i}]"
            if not isinstance(r, dict):
                self.add("S3", "error", where, "规则必须是映射")
                continue

            rid = r.get("id") or where
            if not r.get("id"):
                self.add("S3", "error", where, "规则缺 id")
            elif rid in seen_ids:
                self.add("S3", "error", rid, "规则 id 重复")
            seen_ids.add(rid)

            op = r.get("operator")
            if op not in VALID_OPERATORS:
                self.add("S3", "error", rid, f"operator {op!r} 非法",
                         f"应为 {sorted(VALID_OPERATORS)} 之一")

            if not r.get("target"):
                self.add("S3", "error", rid, "规则缺 target")

            if op in FORMULA_OPERATORS:
                f = r.get("formula")
                if not f:
                    self.add("S3", "error", rid, f"{op} 算子缺 formula")
                elif op != "forecast":
                    try:
                        refs = _refs_in_formula(f)
                    except SyntaxError as e:
                        self.add("S3", "error", rid, f"formula 语法错误：{e}")
                        continue
                    for ref in refs:
                        is_target_of_other = any(
                            isinstance(x, dict) and x.get("target") == ref for x in rules)
                        if ref not in nodes and not is_target_of_other:
                            # 编制过程中引用尚未提供的节点是常态——GAP 分诊会把它
                            # 变成一条客户提问。所以判 warning 而非 error，
                            # 但仍然要提出来，因为笔误和真缺口长得一模一样。
                            sev = "error" if r.get("on_missing") == "error" else "warning"
                            self.add("S3", sev, rid,
                                     f"formula 引用了图中尚不存在的节点 `{ref}`",
                                     "若为笔误请修正；若为待补输入，GAP 分诊会生成客户提问")
                if not r.get("unit"):
                    self.add("S3", "warning", rid, "规则缺 unit，无法做单位一致性校验")

            if op == "allocate":
                m = r.get("matrix")
                if not isinstance(m, dict):
                    self.add("S3", "error", rid, "allocate 算子缺 matrix")
                else:
                    for f in ("rows", "cols", "values"):
                        if f not in m:
                            self.add("S3", "error", rid, f"matrix 缺 {f}")

            if op in ("index", "rate", "lookup") and not r.get("basis"):
                self.add("S3", "warning", rid,
                         "指标/费率类规则未绑定 basis（依据）",
                         "C5 会因此报缺 backing")

    # ---------------------------------------------------------------- S4
    def s4_references(self):
        """引用完整性：指向不存在的对象是静默失效的主要来源。"""
        nodes = self.p.get("nodes") or {}
        ev = self.p.get("evidence") or {}
        claims = self.p.get("claims") or {}
        sections = self.p.get("sections") or []
        sec_ids = {s.get("id") for s in sections if isinstance(s, dict)}
        dims = set((self.argu.get("feasibility_frame") or {}).get("dimensions") or {})

        for i, r in enumerate(self.p.get("rules") or []):
            if isinstance(r, dict) and r.get("basis") and r["basis"] not in ev:
                self.add("S4", "error", r.get("id", f"rules[{i}]"),
                         f"basis 指向不存在的证据 `{r['basis']}`")

        for k, c in claims.items():
            if not isinstance(c, dict):
                self.add("S4", "error", k, "论证单元必须是映射")
                continue
            arg = c.get("argument") or {}
            for field in ("grounds", "backing"):
                for eid in (arg.get(field) or []):
                    if eid not in ev:
                        self.add("S4", "error", k,
                                 f"{field} 指向不存在的证据 `{eid}`")
            for d in (c.get("serves") or []):
                if dims and d not in dims:
                    self.add("S4", "error", k, f"serves 指向不存在的维度 `{d}`")
            for sid in (c.get("restated_in") or []):
                if sec_ids and sid not in sec_ids:
                    self.add("S4", "error", k, f"restated_in 指向不存在的章节 `{sid}`")

        for s in sections:
            if not isinstance(s, dict):
                continue
            for ck in (s.get("restates") or []):
                if ck not in claims:
                    self.add("S4", "error", s.get("id", "?"),
                             f"restates 指向不存在的论证单元 `{ck}`")
            for nk in (s.get("provides") or []):
                if nk not in nodes and not any(
                        isinstance(r, dict) and r.get("target") == nk
                        for r in (self.p.get("rules") or [])):
                    self.add("S4", "warning", s.get("id", "?"),
                             f"provides 声明了图中不存在的节点 `{nk}`")

        for nk in (self.p.get("occurrences") or {}):
            if nk not in nodes and not any(
                    isinstance(r, dict) and r.get("target") == nk
                    for r in (self.p.get("rules") or [])):
                self.add("S4", "error", nk,
                         "occurrences 记录了图中不存在的节点",
                         "C1 恒等检查会因此失去权威值比对")

        for d in (self.p.get("not_applicable") or {}):
            if dims and d not in dims:
                self.add("S4", "error", d, "not_applicable 声明了不存在的维度")

    # ---------------------------------------------------------------- S5
    def s5_covers_spelling(self):
        """covers 拼写。一个错别字会让 C7 既报缺失又不认已有章节。"""
        cov = ((self.core.get("regulatory_anchor") or {}).get("mandatory_coverage") or {})
        if not cov:
            return
        legal = set()
        for spec in cov.values():
            legal |= set(spec.get("items") or [])
        if not legal:
            return

        for s in (self.p.get("sections") or []):
            if not isinstance(s, dict):
                continue
            for item in (s.get("covers") or []):
                if item in legal:
                    continue
                near = [x for x in legal
                        if x[:2] == item[:2] or x[-2:] == item[-2:] or
                        len(set(x) & set(item)) >= max(2, len(item) - 2)]
                self.add("S5", "error", s.get("id", "?"),
                         f"covers 中的 `{item}` 不是法定大纲的内容项",
                         (f"是否想写：{near[:3]}" if near
                          else "法定内容项见 core.yaml → regulatory_anchor.mandatory_coverage"))

    # ---------------------------------------------------------------- S6
    def s6_duplicates(self):
        """重复 id。YAML 映射会静默保留最后一个，前面的直接消失。"""
        sections = [s for s in (self.p.get("sections") or []) if isinstance(s, dict)]
        seen = {}
        for s in sections:
            sid = s.get("id")
            if not sid:
                self.add("S6", "error", "sections[]", "章节缺 id")
                continue
            if sid in seen:
                self.add("S6", "error", sid, "章节 id 重复",
                         "章节 id 是全图引用锚点，重复会导致引用歧义")
            seen[sid] = True

    # ---------------------------------------------------------------- run
    def run(self):
        self.s1_structure()
        if self.fatal:
            return self.findings
        self.s2_node_types()
        self.s3_rules()
        self.s4_references()
        self.s5_covers_spelling()
        self.s6_duplicates()
        return self.findings


# =============================================================================
# 环检测
# =============================================================================

def detect_cycles(rules):
    """
    在派生依赖图上找环，返回环路径列表。

    derivations.yaml 的 cycle_policy 声明了这个行为但一直没实现——
    规格写了代码没写，在工业标准下就是缺陷，这里补上。

    可研中存在真实回环（面积 → 设备机房 → 面积），所以环不是致命错误，
    但必须显式暴露并要求人工设定切断点与收敛条件，不能静默迭代到不动点了事。
    """
    graph = {}
    for r in rules or []:
        if not isinstance(r, dict):
            continue
        tgt = r.get("target")
        f = r.get("formula")
        if not tgt or not f:
            continue
        try:
            graph.setdefault(tgt, set()).update(_refs_in_formula(f))
        except SyntaxError:
            continue

    cycles, seen_sets = [], []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}

    def dfs(node, stack):
        color[node] = GRAY
        stack.append(node)
        for nxt in graph.get(node, ()):
            if nxt not in color:
                continue
            if color[nxt] == GRAY:
                cyc = stack[stack.index(nxt):] + [nxt]
                key = frozenset(cyc)
                if key not in seen_sets:
                    seen_sets.append(key)
                    cycles.append(cyc)
            elif color[nxt] == WHITE:
                dfs(nxt, stack)
        stack.pop()
        color[node] = BLACK

    for n in list(graph):
        if color.get(n) == WHITE:
            dfs(n, [])
    return cycles


def report_schema(findings):
    if not findings:
        return "schema 校验通过"
    order = {"fatal": 0, "error": 1, "warning": 2}
    lines = ["=" * 74, "实例图 schema 校验", "=" * 74]
    n_fatal = sum(1 for f in findings if f.severity == "fatal")
    n_err = sum(1 for f in findings if f.severity == "error")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    lines.append(f"致命 {n_fatal} / 错误 {n_err} / 警告 {n_warn}")
    lines.append("")
    for f in sorted(findings, key=lambda x: (order[x.severity], x.code)):
        lines.append(f"[{f.code}·{f.severity}] {f.subject}")
        lines.append(f"    {f.message}")
        if f.hint:
            lines.append(f"    提示：{f.hint}")
        lines.append("")
    if n_fatal:
        lines.append("存在致命结构错误，已中止语义检查（C1-C7）。")
        lines.append("在结构不合法的图上跑语义检查，产出的「通过」是误导性的。")
    return "\n".join(lines)
