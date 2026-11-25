# -*- coding: utf-8 -*-
"""evo_gate_engine —— 真正执行 EvoOntology 的 gate.expression（零 LLM）。

## 为什么需要

`gate.expression` 是结构化字符串，但**没有任何引擎执行它** ——
`validate_semantics` 只查 JSON 合法性和引用完整性，不算数。

本模块把「表达式 + 值」连起来，输出 PASS / FAIL / SKIP。

## 安全

**不用 eval**。用 `ast.parse` + 白名单节点遍历，只允许：
  常量、Name、二元运算(+ - * / // %)、一元运算(+/-)、比较(== != < <= > >=)、
  函数调用(abs/round/min/max/sum)

## 取值来源（按优先级）

  1. `limit` term 的 `definition` 里 `报告指标 X = <值>`
  2. 任意 term 的 `name` / `definition` 里 `<metric> = <值><unit>`
  3. 都没有 → 该变量记为 UNKNOWN，式子 SKIP（不猜）

## 用法

    from corpus_pipeline.evo_gate_engine import run_gates
    r = run_gates(workspace, version)
    # → {passed, failed, skipped, results:[{gate_id, status, expr, detail}]}
"""
from __future__ import annotations
import ast
import json
import re
from pathlib import Path

ALLOWED_FUNCS = {"abs", "round", "min", "max", "sum"}
_BIN = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)
_UN = (ast.UAdd, ast.USub)
_CMP = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)


class _Safe:
    """AST 白名单求值器。"""

    def __init__(self, env: dict):
        self.env = env

    def eval(self, expr: str):
        tree = ast.parse(expr, mode="eval")
        return self._ev(tree.body)

    def _ev(self, n):
        if isinstance(n, ast.Constant):
            if isinstance(n.value, (int, float, str)):
                return n.value
            raise ValueError("常量类型不允许: %r" % type(n.value))
        if isinstance(n, ast.Name):
            if n.id in self.env and self.env[n.id] is not None:
                return self.env[n.id]
            raise NameError("变量无值: %s" % n.id)
        if isinstance(n, ast.BinOp) and isinstance(n.op, _BIN):
            a, b = self._ev(n.left), self._ev(n.right)
            op = n.op
            if isinstance(op, ast.Add): return a + b
            if isinstance(op, ast.Sub): return a - b
            if isinstance(op, ast.Mult): return a * b
            if isinstance(op, ast.Div): return a / b
            if isinstance(op, ast.FloorDiv): return a // b
            if isinstance(op, ast.Mod): return a % b
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, _UN):
            v = self._ev(n.operand)
            return +v if isinstance(n.op, ast.UAdd) else -v
        if isinstance(n, ast.Compare):
            left = self._ev(n.left)
            for op, comp in zip(n.ops, n.comparators):
                right = self._ev(comp)
                ok = (isinstance(op, ast.Eq) and left == right) or \
                     (isinstance(op, ast.NotEq) and left != right) or \
                     (isinstance(op, ast.Lt) and left < right) or \
                     (isinstance(op, ast.LtE) and left <= right) or \
                     (isinstance(op, ast.Gt) and left > right) or \
                     (isinstance(op, ast.GtE) and left >= right)
                if not ok:
                    return False
                left = right
            return True
        if isinstance(n, ast.BoolOp):
            vals = [self._ev(v) for v in n.values]
            if isinstance(n.op, ast.And):
                return all(vals)
            if isinstance(n.op, ast.Or):
                return any(vals)
            raise ValueError("BoolOp 类型不允许")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ALLOWED_FUNCS:
            args = [self._ev(a) for a in n.args]
            return {"abs": abs, "round": round, "min": min, "max": max, "sum": sum}[n.func.id](*args)
        raise ValueError("AST 节点不允许: %s" % type(n).__name__)


def _from_facts(terms: list) -> dict:
    """**优先从显式 fact 层取值**（v4 做法）。

    fact 的 name 形如「事实：项目总投资 = 13032万元」→ 可直接解析，不靠正则碰运气。
    """
    env = {}
    for t in terms:
        if t.get("type") != "fact":
            continue
        nm = str(t.get("name") or "")
        m = re.match(r"^事实[：:]\s*(.+?)\s*=\s*([\d,]+(?:\.\d+)?)\s*(.*)$", nm)
        if not m:
            continue
        cn = m.group(1).strip()
        try:
            v = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        env[cn] = v
        env[str(t.get("id")).replace("fact_", "")] = v
        # CN→英 id 映射复用
        for k2, cn2 in _CN2ID().items():
            if cn2 == cn:
                env[k2] = v
    return env


def _CN2ID() -> dict:
    return {
        "total_investment": "项目总投资", "construction_installation_cost": "建安工程费用",
        "other_construction_cost": "工程建设其他费用", "contingency_cost": "预备费",
        "demolition_cost": "原建筑拆除费用", "total_floor_area": "总建筑面积",
        "above_ground_area": "地上建筑面积", "underground_area": "地下建筑面积",
        "single_building_works": "单体工程", "civil_works": "土建工程",
        "installation_works": "安装工程", "outdoor_works": "室外总体工程",
    }


def collect_values(terms: list) -> tuple:
    """从 term 收集「变量名 → 数值」。

    返回 (env, conflicts, sources)：
      env       变量名 → 值
      conflicts 同一变量在多个源取到不同值 [{name, values:{src:val}}]
      sources   变量名 → 取值来源（'limit' / 'term'）

    **单源真理检查**：同变量两次取到不同值 → 记 conflict，
    由 run_gates 把它标成 CONFLICT 并报警，而不是悄悄用后一个。
    """
    env = _from_facts(terms)          # ★ 先从 fact 层取（有则优先）
    sources = {k: "fact" for k in env}
    match_method = {}
    conflicts = []
    _seen = {}

    def _put(name, val, src):
        if name in _seen and _seen[name][0] != val:
            prev_val, prev_src = _seen[name]
            conflicts.append({"name": name, "values": {prev_src: prev_val, src: val}})
            return
        if name not in _seen:
            _seen[name] = (val, src)
            env[name] = val
            sources[name] = src
    # ① limit term
    for t in terms:
        if t.get("type") != "limit":
            continue
        d = str(t.get("definition") or "")
        m = re.search(r"报告指标\s*(.+?)\s*=\s*([\d,]+(?:\.\d+)?)", d)
        if m:
            v = float(m.group(2).replace(",", ""))
            _put(m.group(1).strip(), v, "limit")
            _put(str(t.get("id")).replace("limit_", ""), v, "limit")
    # ② 所有 term 的 definition 里 `xxx = <数>`
    for t in terms:
        d = str(t.get("definition") or "")
        for m in re.finditer(r"([a-z_][a-z0-9_]{2,})\s*=\s*([\d,]+(?:\.\d+)?)", d):
            env.setdefault(m.group(1), float(m.group(2).replace(",", "")))
        # name 里「X = 123」
        nm = str(t.get("name") or "")
        m = re.search(r"([a-z_][a-z0-9_]{2,})\s*=\s*([\d,]+(?:\.\d+)?)", nm)
        if m:
            env.setdefault(m.group(1), float(m.group(2).replace(",", "")))
    # ②a-2 通用：metric 的 definition 里「合价 N 万元」→ 用 metric 的 id 作变量名
    #      （学 v4 的 build_gate_inputs.py；比逐个中文名映射覆盖广）
    for t_ in terms:
        if t_.get("type") != "metric":
            continue
        tid = str(t_.get("id") or "")
        if not tid or tid in env:
            continue
        d = str(t_.get("definition") or "")
        m = re.search(r"合价\s*([\d,]+(?:\.\d+)?)\s*万元", d)
        if m:
            try:
                env[tid] = float(m.group(1).replace(",", ""))
                sources[tid] = "definition_合价"
                continue
            except ValueError:
                pass

    # ②b 从 term 的 definition 里抽「中文名 + 数字 + 万元」模式（v3 的明细值）
    CN2ID = {
        "单体工程": "single_building_works", "土建工程": "civil_works",
        "安装工程": "installation_works", "室外总体工程": "outdoor_works",
        "外立面及屋面装饰工程": "facade_roof_decoration",
        "抗震支架": "seismic_bracket", "绿色二星增量费用": "green_increment",
        "桩基工程": "pile_foundation", "基坑围护工程": "pit_support",
        "地下建筑结构工程": "underground_structure",
        "地上建筑结构工程": "above_ground_structure",
        "装配式结构增加费": "prefab_increment", "室内装饰工程": "interior_decoration",
        "建设单位管理费": "construction_unit_management_fee",
        "前期工程咨询费": "preliminary_consulting_fee", "勘察费": "survey_fee",
        "设计费": "design_fee", "招标代理费": "bidding_agency_fee",
        "施工监理费": "supervision_fee",
    }
    # 关键：优先抓「合价 N 万元」，其次「N 万元」，**最后才抓裸数字**
    #   因为 term 定义里「土建工程，数量 18319㎡，单位造价 4254 元，合价 7793 万元」
    #   抓第一个数字会得到 18319（面积），不是 7793（合价）
    # ②a 优先：term 的 name 精确等于中文名 → 直接从它自己的 definition 取合价
    #   避免「安装工程」误命中「建安工程费用」定义里的数字
    cn_by_name = {}
    for t_ in terms:
        nm = str(t_.get("name") or "").strip()
        if nm in CN2ID:
            vid = CN2ID[nm]
            d = str(t_.get("definition") or "")
            for pat in [r"合价\s*([\d,]+(?:\.\d+)?)", r"([\d,]+(?:\.\d+)?)\s*万元"]:
                m = re.search(pat, d)
                if m:
                    try:
                        env[vid] = float(m.group(1).replace(",", "")); break
                    except ValueError: pass

    for t_ in terms:
        d = str(t_.get("definition") or "") + " " + str(t_.get("name") or "")
        for cn, vid in CN2ID.items():
            if vid in env: continue
            pats = [
                re.escape(cn) + r"[^。；]{0,40}?合价\s*([\d,]+(?:\.\d+)?)",
                re.escape(cn) + r"[^。；]{0,40}?([\d,]+(?:\.\d+)?)\s*万元",
                re.escape(cn) + r"[^0-9]{0,10}([\d,]+(?:\.\d+)?)",
            ]
            for pat in pats:
                m = re.search(pat, d)
                if m:
                    try:
                        env[vid] = float(m.group(1).replace(",", ""))
                        break
                    except ValueError:
                        continue
    # ②c 拆除单价 / 装配率 / 绿建等级（从 definition 里的短语）
    for t_ in terms:
        d = str(t_.get("definition") or "")
        m = re.search(r"(\d+)\s*元/平方米", d)
        if m and "demolition_unit_price" not in env:
            env["demolition_unit_price"] = float(m.group(1))
        m = re.search(r"预制率\s*(?:不小于|≥|>=)?\s*(\d+)%", d)
        if m and "prefabrication_rate" not in env:
            env["prefabrication_rate"] = float(m.group(1))
        m = re.search(r"绿色建筑(\S{1,4}星)", d)
        if m and "green_building_level" not in env:
            env["green_building_level"] = m.group(1)

    # ③ 具体已知指标（v3 的 29 limits 用中文名，补英文 id 别名）
    ALIAS = {
        "total_investment": "项目总投资", "construction_installation_cost": "建安工程费用",
        "other_construction_cost": "工程建设其他费用", "contingency_cost": "预备费",
        "demolition_cost": "原建筑拆除费用", "total_floor_area": "总建筑面积",
    }
    for k, cn in ALIAS.items():
        if k not in env and cn in env:
            env[k] = env[cn]
    return env, conflicts, sources, match_method


# 注：曾有 check_dual_source「同值双源检测」，因正则无法区分
# 「term 定义里的值」与「term 提到的值」而误报 2384 处，已移除。
# 真正的单源真理保障靠 gate_engine：18 条门禁会按 limit 的值实算，
# 若 term 与 limit 不一致，改动方会在流程里被发现（而非靠全文正则扫）。


def build_gate_inputs(workspace, version: str = "", *, out=None) -> dict:
    """从 limit 与 term 生成 gate_inputs.json（指标 ID → 数值）。

    **值和公式解耦**：同一套门禁可以跑不同项目的数据，只要换 inputs。
    """
    ws = Path(workspace)
    ver = version or json.loads((ws/"active.json").read_text(encoding="utf-8"))["active_version"]
    terms = json.loads((ws/"versions"/ver/"terms.json").read_text(encoding="utf-8"))
    env, conflicts, sources, _mm = collect_values(terms)
    payload = {
        "schema": "gate-inputs/v1",
        "source": {"workspace": str(ws), "version": ver},
        "note": "指标 ID → 数值。改这里不影响门禁公式，换项目只换 inputs。",
        "inputs": {k: v for k, v in sorted(env.items())},
        "sources": sources,
        "conflicts": conflicts,
        "count": len(env),
    }
    if out:
        Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        payload["out"] = str(out)
    return payload


def run_gates(workspace, version: str = "", *, verbose=False,
              gate_inputs=None) -> dict:
    """跑门禁。gate_inputs 可传 dict 或 json 路径，覆盖从 workspace 抽的值。"""
    ws = Path(workspace)
    ver = version or json.loads((ws/"active.json").read_text(encoding="utf-8"))["active_version"]
    terms = json.loads((ws/"versions"/ver/"terms.json").read_text(encoding="utf-8"))
    env, conflicts, sources, _mm = collect_values(terms)
    if gate_inputs is not None:
        gi = (json.loads(Path(gate_inputs).read_text(encoding="utf-8"))
              if isinstance(gate_inputs, (str, Path)) else gate_inputs)
        over = gi.get("inputs") if isinstance(gi, dict) and "inputs" in gi else gi
        if isinstance(over, dict):
            for k, v in over.items():
                try:
                    env[str(k)] = float(v)
                    sources[str(k)] = "gate_inputs"
                except (TypeError, ValueError):
                    pass

    conf_names = {c["name"] for c in conflicts}
    results = []
    for t in terms:
        if t.get("type") != "gate":
            continue
        gid = t.get("id")
        d = str(t.get("definition") or "")
        m = re.search(r"表达式[：:]\s*([^；]+)", d)
        expr = (m.group(1).strip() if m else "")
        st = re.search(r"状态[：:]\s*([a-z_]+)", d)
        status = st.group(1) if st else ""
        if not expr:
            # 9 个 slot 门禁：设计上不可自动判定，**不假装能判**
            results.append({"gate_id": gid, "status": "UNVERIFIABLE",
                            "reason": "空槽门禁（slot）：口径类，不假装可判"})
            continue
        # 表达式里用到冲突变量 → 标 CONFLICT，不静默采用某一值
        used = set(re.findall(r"[a-z_][a-z0-9_]*", expr)) & conf_names
        if used:
            results.append({"gate_id": gid, "status": "CONFLICT",
                            "reason": "变量多源冲突：%s" % ", ".join(sorted(used))[:80],
                            "expr": expr[:80]})
            continue
        try:
            ok = _Safe(env).eval(expr)
            results.append({"gate_id": gid, "status": "PASS" if ok else "FAIL",
                            "expr": expr[:120]})
        except NameError as e:
            # 变量无值 → 补 inputs 就能判，不是终态
            results.append({"gate_id": gid, "status": "UNVERIFIABLE",
                            "reason": "缺输入：%s（补 gate_inputs 后可判）" % str(e)[:50],
                            "expr": expr[:80]})
        except Exception as e:
            results.append({"gate_id": gid, "status": "ERROR",
                            "reason": "%s: %s" % (type(e).__name__, str(e)[:60]),
                            "expr": expr[:80]})

    from collections import Counter
    c = Counter(r["status"] for r in results)
    return {"version": ver, "env_size": len(env),
            "passed": c.get("PASS", 0), "failed": c.get("FAIL", 0),
            "skipped": c.get("SKIP", 0), "errors": c.get("ERROR", 0),
            "unverifiable": c.get("UNVERIFIABLE", 0),
            "conflicts": c.get("CONFLICT", 0),
            "conflict_detail": conflicts[:10],
            "sources": sources,
            "total": len(results), "results": results}
