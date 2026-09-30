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
