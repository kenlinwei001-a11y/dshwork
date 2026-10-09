"""确定性数字/时间冲突检测（零 LLM）。

对应 conflict-detection-skill 的确定性部分：
- 数字冲突：同一实体/指标在不同节点出现不一致数值。
- 时间冲突：同一实体的时间区间/日期互相矛盾。
输出「待审」清单，不做裁决。
"""
from __future__ import annotations
import re

_NUM = re.compile(r'[-+]?\d[\d,]*(?:\.\d+)?%?')


def _norm_num(s: str) -> float | None:
    try:
        return float(s.replace(",", "").replace("%", ""))
    except (ValueError, AttributeError):
        return None


def detect_numeric_conflicts(facts: list[dict]) -> list[dict]:
    """检测同一 subject+predicate 下数值不一致的事实，返回待审清单。"""
    groups: dict[tuple, list[dict]] = {}
    for f in facts:
        key = (f.get("subject"), f.get("predicate"))
        groups.setdefault(key, []).append(f)
    out = []
    for (subj, pred), fs in groups.items():
        values = set()
        for f in fs:
            for num in _NUM.findall(str(f.get("value", ""))):
                v = _norm_num(num)
                if v is not None:
                    values.add(v)
        if len(values) > 1:
            out.append({
                "type": "numeric",
                "subject": subj,
                "predicate": pred,
                "values": sorted(values),
                "involved": [f.get("id") for f in fs],
                "status": "待审",
            })
    return out


def detect_time_conflicts(facts: list[dict]) -> list[dict]:
    """检测同一 subject 上互相矛盾的时间表述（简化启发式），返回待审清单。"""
    out = []
    year = re.compile(r'(20\d{2}|19\d{2})')
    for f in facts:
        times = f.get("time") or f.get("value") or ""
        years = sorted(set(year.findall(str(times))))
        # 若同一事实内出现多个相距甚远的年份且无「至/区间」标记，标记待审
        if len(years) >= 2:
            span = int(years[-1]) - int(years[0])
            if span > 50 and not re.search(r'至|~|-|到|区间|range', str(times)):
                out.append({
                    "type": "time",
                    "subject": f.get("subject"),
                    "years": years,
                    "involved": [f.get("id")],
                    "status": "待审",
                })
    return out


# --------------------------------------------------------------------------- #
# 写作查数：核实正文数字与事实源一致 + 前后一致性 + 口径
# --------------------------------------------------------------------------- #
_NUM_WITH_UNIT = re.compile(
    r'(-?\d[\d,]*(?:\.\d+)?%?)\s*([A-Za-z][\w/]*|[\u4e00-\u9fff]{1,3})'
)
_NODE_REF = re.compile(r'\{\{node:[^}]+\}\}')


def check_number_consistency(draft_md: str, facts: list[dict]) -> dict:
    """写作查数：核实正文数字与事实源一致，检测前后不一致与口径存疑。

    供写作 Agent 每写一节后调用（替代事后 gate 的粗检）：
      - bound：正文数字能匹配到事实源（单源事实），给出 subject 与 fact id。
      - unbound：正文出现但事实源没有的数字（可能新值/笔误，需人工核实）。
      - inconsistent：同一 subject 在正文多处出现不同数值（前后不一致）。
      - caliber_issues：同一 subject 的数值单位不一致（流量 vs 存量）。

    确定性、零 LLM，同输入同输出。
    """
    # 0. 剥离 node 占位符（引用不是字面数字）
    text = _NODE_REF.sub(' ', draft_md or '')

    # 1. 提取数字 + 紧跟单位
    numbers = []
    for m in _NUM_WITH_UNIT.finditer(text):
        numbers.append({
            "value": m.group(1),
            "unit": m.group(2),
            "context": text[max(0, m.start() - 16):m.end() + 16].strip(),
            "span": [m.start(), m.end()],
        })

    # 2. 事实源索引（归一化数值 → facts）
    fact_by_value: dict[float, list[dict]] = {}
    for f in facts:
        v = _norm_num(str(f.get("value", "")))
        if v is not None:
            fact_by_value.setdefault(v, []).append(f)

    # 3. 逐数字核实
    bound, unbound = [], []
    for n in numbers:
        v = _norm_num(n["value"])
        matched = fact_by_value.get(v) if v is not None else None
        if matched:
            n["subjects"] = sorted({f.get("subject", "?") for f in matched})
            n["matched_fact_ids"] = [f.get("id") for f in matched]
            bound.append(n)
        else:
            unbound.append(n)

    # 4. 前后不一致：同一 subject 在正文出现多个不同数值
    subject_values: dict[str, set] = {}
    for n in bound:
        for s in n.get("subjects", []):
            subject_values.setdefault(s, set()).add(n["value"])
    inconsistent = [
        {"subject": s, "values": sorted(vals, key=_norm_num), "status": "待审"}
        for s, vals in subject_values.items() if len(vals) > 1
    ]

    # 5. 口径存疑：同一 subject 的单位不一致（流量 vs 存量）
    subject_units: dict[str, set] = {}
    for n in bound:
        if not n.get("unit"):
            continue
        for s in n.get("subjects", []):
            subject_units.setdefault(s, set()).add(n["unit"])
    caliber_issues = [
        {"subject": s, "units": sorted(u), "status": "待审"}
        for s, u in subject_units.items() if len(u) > 1
    ]

    return {
        "numbers_found": len(numbers),
        "bound": len(bound),
        "unbound": len(unbound),
        "unbound_list": unbound,
        "inconsistent": inconsistent,
        "caliber_issues": caliber_issues,
    }
