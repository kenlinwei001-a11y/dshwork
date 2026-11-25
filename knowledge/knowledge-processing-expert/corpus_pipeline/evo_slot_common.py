# -*- coding: utf-8 -*-
"""evo_slot_common —— 模板/填槽共用工具。

只做确定性的事：名称归一、别名、规则装载、数字格式化、安全算式求值。
不读网络、不调 LLM、不写死项目值。
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from pathlib import Path

# ---------------------------------------------------------------- 名称归一

_PUNCT = "，,。；;、：:（）()【】[]《》<>「」\"'“”‘’·・/\\|_—–-"
_KEEP_CHARS = re.compile(r"[^一-龥A-Za-z0-9%.+*/·]")


def norm(s) -> str:
    """匹配用归一：去标点/空白/大小写差异，保留 · 作为表槽分隔符。"""
    t = str(s if s is not None else "").strip()
    t = t.replace("（", "(").replace("）", ")")
    t = t.replace("・", "·").replace("／", "/")
    t = re.sub(r"\*\*|`", "", t)
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"^[0-9]+(?:\.[0-9]+)*[.、]?", "", t)
    t = t.replace("的", "")
    t = _KEEP_CHARS.sub("", t)
    return t.lower()


def strip_markdown(s) -> str:
    t = str(s if s is not None else "").strip()
    t = re.sub(r"\*\*|`", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def split_table_slot(name: str):
    """把 `桩基工程·合价` 拆成 (桩基工程, 合价)；无机位返回 (None, None)。"""
    s = str(name or "").strip()
    for sep in ("·", "・", "|"):
        if sep in s:
            a, b = s.split(sep, 1)
            return a.strip(), b.strip()
    return None, None


def canon_col(header: str) -> str:
    """表头 → 语义列名。只做语义归类，不改原文列名。"""
    h = strip_markdown(header)
    hn = norm(h)
    if "序号" in h or "编号" in h:
        return "序号"
    if (h.endswith("·单位") or h.endswith("单位")) and "单位造价" not in h and "单价" not in h:
        return "单位"
    if "单位造价" in h or "单价" in h:
        return "单价"
    if "合价" in h or "金额" in h:
        return "合价"
    if "备注" in h:
        return "备注"
    if "年用水量" in h:
        return "年用水量"
    if "日用水量" in h:
        return "日用水量"
    if "用水天数" in h:
        return "用水天数"
    if "用水定额" in h:
        return "用水定额"
    if "年用电量" in h:
        return "年用电量"
    if "用电面积" in h:
        return "用电面积"
    if "用电指标" in h:
        return "用电指标"
    if "需要系数" in h:
        return "需要系数"
    if "同时使用系数" in h:
        return "同时使用系数"
    if "日均工作小时" in h:
        return "日均工作小时数"
    if "年工作天数" in h:
        return "年工作天数"
    if "折标煤" in h:
        return "折标煤"
    if "折标系数" in h:
        return "折标系数"
    if "能源消耗" in h:
        return "能源消耗"
    if "比例" in h:
        return "比例"
    if "数量" in h:
        return "数量"
    if h == "单位" or h.endswith("单位"):
        return "单位"
    # 去掉括号里的单位
    return re.sub(r"[（(].*?[)）]", "", h).strip() or hn


def unit_from_header(header: str) -> str:
    h = strip_markdown(header)
    m = re.search(r"[（(]([^（）()]+)[)）]", h)
    if m:
        return m.group(1).strip()
    if "单位造价" in h:
        return "元/㎡"
    if "单价" in h:
        return "元"
    if "合价" in h or "金额" in h:
        return "万元"
    return ""


def to_number(v):
    """字符串/数字 → float；不可解析返回 None。不把 None 当 0。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s:
        return None
    # 允许「5500 待算」这类带注记的值：取开头的数
    m = re.match(r"^([-+]?\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def same_number(a, b, tol: float = 1e-6) -> bool:
    na, nb = to_number(a), to_number(b)
    if na is None or nb is None:
        return str(a) == str(b)
    if abs(na - nb) <= tol:
        return True
    return abs(na - nb) <= max(abs(na), abs(nb)) * 1e-6


def format_number(v, *, max_dec: int = 4) -> str:
    """自然格式：整数加千分位；小数去尾零。不写单位。"""
    n = to_number(v)
    if n is None:
        return str(v)
    if abs(n - round(n)) < 1e-9:
        n = int(round(n))
        return f"{n:,}" if abs(n) >= 10000 else str(n)
    s = f"{n:.{max_dec}f}".rstrip("0").rstrip(".")
    if "." in s:
        a, b = s.split(".", 1)
        try:
            a = f"{int(a):,}"
        except ValueError:
            pass
        return a + "." + b
    return s


def format_value(v, unit: str = "") -> str:
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return format_number(v)
    s = str(v).strip()
    return s


def unit_of_value_text(text: str) -> str:
    """从「11,800 万元」「15,600 ㎡」「46.61」里猜单位。"""
    t = strip_markdown(text)
    m = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?\s*([^\s\d〔【】.,，]+)", t)
    if m:
        u = m.group(1).strip("（）()，,。；;")
        if u:
            return u
    return ""


# ---------------------------------------------------------------- 别名 / 规则


def load_yaml(path):
    try:
        import yaml
    except Exception:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# 人工登记的跨节别名（只在归一后仍对不上时使用，不替代显式别名表）
MANUAL_ALIASES = {
    "项目总投资": "总投资",
    "建筑安装工程费用": "建安工程费用",
    "建筑安装工程费": "建安工程费用",
    "建安工程费": "建安工程费用",
    "建安费": "建安工程费用",
    "工程建设其他费": "工程建设其他费用",
    "二类费": "工程建设其他费用",
    "其他费": "工程建设其他费用",
    "其他费用": "工程建设其他费用",
    "拆除费": "原建筑拆除费用",
    "原建筑拆除费": "原建筑拆除费用",
    "基本预备费": "预备费",
    "总建筑面积": "本项目建筑面积",
    "新建总建筑面积": "本项目建筑面积",
    "建筑面积": "本项目建筑面积",
    "年用水量": "年总用水量",
    "年总用水": "年总用水量",
    "年用电量": "年总耗电量",
    "年耗电量": "年总耗电量",
    "单位造价": "单位造价（总投资口径）",
    "项目单位造价": "单位造价（总投资口径）",
    "综合能耗": "综合能耗（当量值）",
    "总能耗": "综合能耗（当量值）",
    "教师用水": "办公用水",
    "学生用水": "科研学生用水",
    "教师用水量": "教师用水日水量",
    "学生用水量": "学生用水日水量",
    "科研用房面积": "科研用房用电面积",
    "配套用房面积": "公共配套服务用房用电面积",
    "公共配套服务用房面积": "公共配套服务用房用电面积",
}


def load_aliases(path=None):
    """返回 (canonical→aliases, alias_norm→canonical)。"""
    canon_aliases = {}
    alias_to_canon = {}
    if path:
        data = load_yaml(path)
        for canonical, aliases in (data.get("aliases") or {}).items():
            c = str(canonical).strip()
            arr = [str(x).strip() for x in (aliases or []) if str(x).strip()]
            canon_aliases[c] = arr
            alias_to_canon[norm(c)] = c
            for a in arr:
                alias_to_canon[norm(a)] = c
    for a, c in MANUAL_ALIASES.items():
        alias_to_canon.setdefault(norm(a), c)
        canon_aliases.setdefault(c, [])
        if a not in canon_aliases[c]:
            canon_aliases[c].append(a)
        alias_to_canon.setdefault(norm(c), c)
    return canon_aliases, alias_to_canon


def canonical_name(name: str, alias_to_canon: dict) -> str:
    n = norm(name)
    if not n:
        return str(name or "").strip()
    out = alias_to_canon.get(n, str(name or "").strip())
    # 人工登记的目标名再归一到图谱实际 subject（如 项目总投资 → 总投资）
    for _ in range(2):
        nn = norm(out)
        if nn in MANUAL_ALIASES and MANUAL_ALIASES[nn] != out:
            out = MANUAL_ALIASES[nn]
        else:
            break
    return out


# 表槽的显式语义别名：row·col → 图谱 subject / 聚合槽位
TABLE_SLOT_ALIASES = {
    "建筑安装工程费用·合价": "建安工程费用",
    "建筑安装工程费·合价": "建安工程费用",
    "建安工程费用·合价": "建安工程费用",
    "工程建设其他费·合价": "工程建设其他费用",
    "工程建设其他费用·合价": "工程建设其他费用",
    "基本预备费·合价": "预备费",
    "预备费·合价": "预备费",
    "拆除费·合价": "原建筑拆除费用",
    "原建筑拆除费用·合价": "原建筑拆除费用",
    "总计·合价": "总投资",
    "合计·合价": "总投资",
    "总计·单价": "单位造价（总投资口径）",
    "合计·单价": "单位造价（总投资口径）",
    "总计·数量": "本项目建筑面积",
    "合计·数量": "本项目建筑面积",
    # 7.2.2 水量表
    "教师用水·用水定额": "办公用水定额",
    "教师用水·数量": "办公用水人数",
    "教师用水·日用水量": "教师用水日水量",
    "教师用水·用水天数": "年工作天数",
    "学生用水·用水定额": "科研学生用水定额",
    "学生用水·数量": "科研学生用水人数",
    "学生用水·日用水量": "学生用水日水量",
    "学生用水·用水天数": "年工作天数",
    "不可预计水量（10%）·年用水量": "不可预计水量",
    "合计·年用水量": "年总用水量",
    # 7.2.2 电量表
    "科研用房·用电面积": "科研用房用电面积",
    "科研用房·用电指标": "科研用房用电指标",
    "科研用房·需要系数": "科研用房需要系数",
    "科研用房·同时使用系数": "科研用房同时使用系数",
    "科研用房·日均工作小时数": "日均工作小时数",
    "科研用房·年工作天数": "年工作天数",
    "公共配套服务用房·用电面积": "公共配套服务用房用电面积",
    "公共配套服务用房·用电指标": "公共配套服务用房用电指标",
    "公共配套服务用房·需要系数": "公共配套服务用房需要系数",
    "公共配套服务用房·同时使用系数": "公共配套服务用房同时使用系数",
    "公共配套服务用房·日均工作小时数": "日均工作小时数",
    "公共配套服务用房·年工作天数": "年工作天数",
    "合计·年用电量": "年总耗电量",
    # 表内数量口径
    "建筑安装工程费用·数量": "本项目建筑面积",
    "单体工程·数量": "本项目建筑面积",
    "土建工程·数量": "本项目建筑面积",
    "桩基工程·数量": "本项目建筑面积",
    "室内装饰工程·数量": "本项目建筑面积",
    "安装工程·数量": "本项目建筑面积",
    "室外总体工程·数量": "本项目建筑面积",
    "抗震支架·数量": "本项目建筑面积",
    "给排水工程·数量": "本项目建筑面积",
    "消防工程·数量": "本项目建筑面积",
    "通风、空调工程·数量": "本项目建筑面积",
    "强电工程·数量": "本项目建筑面积",
    "弱电工程·数量": "本项目建筑面积",
    "绿色二星增量费用·数量": "本项目建筑面积",
    "地下建筑结构工程·数量": "地下建筑面积",
    "地上建筑结构工程·数量": "地上建筑面积",
    "装配式结构增加费·数量": "地上建筑面积",
    "外立面及屋面装饰工程·数量": "地上建筑面积",
    "工程建设其他费·数量": "本项目建筑面积",
    "基本预备费·数量": "本项目建筑面积",
}
TABLE_SLOT_ALIASES_NORM = {norm(k): v for k, v in TABLE_SLOT_ALIASES.items()}


def resolve_slot_name(name: str, alias_to_canon: dict) -> str:
    """槽位名 → 图谱 subject。表槽优先走显式别名，再走 row+col 组合。"""
    row, col = split_table_slot(name)
    if row:
        key = norm(row) + "·" + norm(col)
        if key in TABLE_SLOT_ALIASES_NORM:
            return TABLE_SLOT_ALIASES_NORM[key]
        crow = canonical_name(row, alias_to_canon)
        if col in ("合价", "金额", "估算金额", "费用"):
            return crow
        if col in ("数量", "单价", "备注"):
            return ""  # 这三类由填槽器按区域/公式/缺失单独处理
        # 指标列：先试 row+col，再试 col 本身
        return crow + col
    return canonical_name(name, alias_to_canon)


def load_rules(path=None):
    """装载 derivation_templates.yaml → {rule_id: {...}}。"""
    out = {}
    if not path:
        return out
    data = load_yaml(path)
    for rid, rv in (data.get("rules") or {}).items():
        if not isinstance(rv, dict):
            continue
        out[str(rid)] = {
            "rule_id": str(rid),
            "target": str(rv.get("target") or ""),
            "expr": str(rv.get("expr") or ""),
            "deps_required": [str(x) for x in (rv.get("deps_required") or [])],
            "section": str(rv.get("section") or ""),
            "guard": str(rv.get("guard") or ""),
        }
    return out


# ---------------------------------------------------------------- 安全算式


class SafeEvalError(ValueError):
    pass


_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
    ast.Load, ast.Call, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
    ast.Mod, ast.UAdd, ast.USub, ast.Tuple,
)


def _eval_node(node, env):
    if not isinstance(node, _ALLOWED_NODES):
        raise SafeEvalError("不允许的表达式节点：%s" % type(node).__name__)
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, env)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise SafeEvalError("只允许数值常量")
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise SafeEvalError("未知变量：%s" % node.id)
        return env[node.id]
    if isinstance(node, ast.UnaryOp):
        v = _eval_node(node.operand, env)
        return +v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp):
        a = _eval_node(node.left, env)
        b = _eval_node(node.right, env)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            if b == 0:
                raise SafeEvalError("除零")
            return a / b
        if isinstance(node.op, ast.Pow):
            return a ** b
        if isinstance(node.op, ast.Mod):
            return a % b
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise SafeEvalError("只允许函数名调用")
        fname = node.func.id
        funcs = {
            "round": lambda x, n=0: round(x, int(n)),
            "min": min, "max": max, "abs": abs,
        }
        if fname not in funcs:
            raise SafeEvalError("不允许的函数：%s" % fname)
        args = [_eval_node(a, env) for a in node.args]
        return funcs[fname](*args)
    raise SafeEvalError("不允许的表达式节点：%s" % type(node).__name__)


def eval_expr(expr: str, values: dict):
    """求值 `round({A}+{B}, 2)`。

    values: {变量名: 数值}
    返回 (result, missing_names)。任何依赖缺失 → (None, [缺失名...])。
    """
    expr = str(expr or "").strip()
    if not expr:
        return None, []
    names = []
    missing = []
    env = {}

    def repl(m):
        name = m.group(1).strip()
        if name in env:
            return env[name]
        key = "__v%d" % len(names)
        names.append(name)
        v = values.get(name)
        if v is None:
            missing.append(name)
            env[key] = None
            return key
        n = to_number(v)
        if n is None:
            # 非数值文本不能代入算式
            missing.append(name)
            env[key] = None
            return key
        env[key] = n
        return key

    py = re.sub(r"\{([^{}]+)\}", repl, expr)
    if missing:
        return None, missing
    try:
        tree = ast.parse(py, mode="eval")
        return _eval_node(tree, env), []
    except Exception as e:
        raise SafeEvalError("算式求值失败：%s（%s）" % (expr, e))


def derive_id(section: str, slot: str, formula: str = "") -> str:
    raw = ("%s|%s|%s" % (section, slot, formula)).encode("utf-8")
    return "D-" + hashlib.sha1(raw).hexdigest()[:12]


# ---------------------------------------------------------------- 引用 / 小工具


CITE_RE = re.compile(r"〔([A-Z]+-[0-9a-z]+)〕")


def citations(text: str) -> list:
    return CITE_RE.findall(str(text or ""))


def with_cite(value_text: str, node_id: str) -> str:
    s = str(value_text).strip()
    if not node_id:
        return s
    return "%s〔%s〕" % (s, node_id)


# ---------------------------------------------------------------- 图谱索引


class GraphIndex:
    """GRAPH JSON 的确定性索引：事实、冲突、规则。

    选择规则（不裁决冲突）：
      1. 优先 provided 且 source_type 非 COMPUTED 的事实；
      2. 其次 CUSTOMER / CUSTOMER_PRIMARY / STANDARD；
      3. 最后任意有值事实。
    同一 subject 的其它值进入 alternatives，由调用方显式呈现。
    """

    def __init__(self, graph: dict, *, aliases_path=None, rules_path=None):
        self.graph = graph or {}
        items = (graph or {}).get("items") or {}
        self.facts = list(items.get("facts") or [])
        self.conflicts = list(items.get("conflicts") or [])
        self.reasoning = list(items.get("reasoning") or [])
        self.by_id = {str(f.get("id")): f for f in self.facts if f.get("id")}
        self.by_subject = {}
        for f in self.facts:
            self.by_subject.setdefault(norm(f.get("subject")), []).append(f)
        self.canon_aliases, self.alias_to_canon = load_aliases(aliases_path)
        self.rules = load_rules(rules_path)
        # 图内 reasoning 也作为规则来源（expr 与 result 都在图里）
        for r in self.reasoning:
            rid = str(r.get("rule_id") or r.get("id") or "")
            if not rid:
                continue
            if rid not in self.rules:
                self.rules[rid] = {
                    "rule_id": rid,
                    "target": str(r.get("target") or ""),
                    "expr": str(r.get("formula") or ""),
                    "deps_required": [],
                    "section": str(r.get("section") or ""),
                    "guard": "",
                    "graph_result": r.get("result"),
                    "graph_output": r.get("output"),
                    "graph_inputs": r.get("inputs") or [],
                }
            else:
                self.rules[rid]["graph_result"] = r.get("result")
                self.rules[rid]["graph_output"] = r.get("output")
                self.rules[rid]["graph_inputs"] = r.get("inputs") or []

    # ---- 事实检索

    def facts_for(self, name: str) -> list:
        n = norm(name)
        if not n:
            return []
        if n in self.by_subject:
            return list(self.by_subject[n])
        # 表槽显式别名 / row+col 组合
        target = resolve_slot_name(name, self.alias_to_canon)
        if target and norm(target) in self.by_subject:
            return list(self.by_subject[norm(target)])
        # 无表槽分隔符时才允许子串匹配；表槽必须走显式别名，避免
        # 「科研用房·用电指标」误配到「科研用房」。
        if "·" in n:
            return []
        c = self.alias_to_canon.get(n)
        if c and norm(c) in self.by_subject:
            return list(self.by_subject[norm(c)])
        cands = []
        for subj, fs in self.by_subject.items():
            if len(subj) >= 4 and (subj in n or n in subj):
                cands.extend(fs)
        return cands

    @staticmethod
    def pick(facts: list):
        """从同 subject 的多个事实中选主值，返回 (primary, alternatives)。"""
        def score(f):
            st = str(f.get("status") or "")
            src = str(f.get("source_type") or "")
            v = f.get("value")
            s = 0
            if v is not None and st not in ("undefined", "missing"):
                s += 20
            if st == "provided":
                s += 10
            if src in ("CUSTOMER", "CUSTOMER_PRIMARY"):
                s += 5
            elif src == "STANDARD":
                s += 4
            elif src == "COMPUTED":
                s += 1
            return s
        if not facts:
            return None, []
        ordered = sorted(facts, key=score, reverse=True)
        primary = ordered[0]
        alts = [f for f in ordered[1:]]
        return primary, alts

    def find(self, name: str):
        return self.pick(self.facts_for(name))

    def find_by_id(self, node_id: str):
        return self.by_id.get(str(node_id or ""))

    def rule_targets(self) -> dict:
        """target_norm → [rule...]"""
        out = {}
        for r in self.rules.values():
            t = str(r.get("target") or "").strip()
            if t:
                out.setdefault(norm(t), []).append(r)
        return out

    def find_rule_for_target(self, name: str):
        n = norm(name)
        cands = self.rule_targets().get(n) or []
        if not cands:
            c = self.alias_to_canon.get(n)
            if c:
                cands = self.rule_targets().get(norm(c)) or []
        if not cands:
            # 双向别名：用规范化后的 canonical 再对一遍
            cn = canonical_name(name, self.alias_to_canon)
            for r in self.rules.values():
                if canonical_name(r.get("target") or "", self.alias_to_canon) == cn:
                    cands.append(r)
        return cands

    def find_id_by_value(self, name: str, value):
        for f in self.facts_for(name):
            if f.get("value") is not None and same_number(f.get("value"), value):
                return f.get("id", "")
        return ""

    def conflicts_for(self, name: str, node_ids=None) -> list:
        n = norm(name)
        ids = set(node_ids or [])
        out = []
        for c in self.conflicts:
            inv = set(c.get("involved") or [])
            desc = str(c.get("description") or "")
            if (ids and ids & inv) or (n and n in norm(desc)):
                out.append(c)
        return out


def read_text(path) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def dump_json(path, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
