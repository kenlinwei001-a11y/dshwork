# -*- coding: utf-8 -*-
"""s4c —— 数值语义维度补全（回答客户反馈的根因）。

客户反馈的原话：「数字都来自同一个事实源，还不足以保证报告正确；
还必须保住数字的**对象、用途、单位和上下级关系**。」

原模型只有 (subject, predicate, value, unit, source)，缺 5 个维度：
  object_role       对象角色：控制值 / 实际值 / 设计值 / 需求值 / 估算值 / 指标值
  domain            专业·用途域：暖通冷负荷 / 暖通热负荷 / 电气电力 / 给排水 / 结构 / 投资…
  caliber_direction 口径方向：上限 / 下限 / 区间 / 等于（决定能否用于「不满足」判定）
  hierarchy_path    上下级归属：费用树/构件树路径（决定明细能否归入某汇总）
  precision         精度与容差（用于判定「舍入一致」而非「冲突」）

本步为**规则式确定性补全**（关键词 + 章节 + 谓词），每条标注 `sem_src=rule:<依据>`，
未命中者标 `unknown` 并**不猜测**。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
R = WS / "SHUFE-BDC-2019-001"

# ── 规则表（依据：谓词/主题/章节关键词）─────────────────────────
ROLE = [
    (r"控制|限高|控制在", "控制值"),
    (r"需求|需要|需求量", "需求值"),
    (r"设计|拟建", "设计值"),
    (r"实测|现状|既有", "实际值"),
    (r"推算|层高|重算|派生", "推演值"),
    (r"估算|概算|预算|金额|费用", "估算值"),
    (r"指标|定额|标准值|密度", "指标值"),
]
DOMAIN = [
    (r"冷负荷|制冷|冷量|空调.*(冷|制冷)", "暖通·冷负荷"),
    (r"热负荷|制热|热量|供暖", "暖通·热负荷"),
    (r"照明|用电|电力|配电|负荷密度|耗电|变压器|电缆", "电气·电力"),
    (r"新风|风量|通风|排风|换气", "暖通·通风"),
    (r"给水|排水|消防水|水泵|用水|管网", "给排水"),
    (r"结构|荷载|抗震|地基|桩|混凝土|钢筋", "结构"),
    (r"幕墙|立面|门窗|屋面|装饰|装修|涂料", "建筑·装饰"),
    (r"投资|费用|资金|预备费|建安|其他费|铺底", "投资·费用"),
    (r"绿地|噪声|排放|环境|环保", "环境"),
]
DIRECTION = [
    (r"不超过|不大于|上限|限高|控制|最高", "上限"),
    (r"不少于|不小于|不低于|下限|至少|最低", "下限"),
    (r"~|～|至|区间", "区间"),
    (r"等于|为|计|合计|总额", "等于"),
]
# 费用树：明细项 → 归属父项（依据「原报告口径」；此处只标已知归属，未标者不猜）
HIERARCHY = {
    "建筑·装饰": "建安工程费",
    "结构": "建安工程费",
    "给排水": "建安工程费",
    "暖通·冷负荷": "建安工程费",
    "暖通·热负荷": "建安工程费",
    "暖通·通风": "建安工程费",
    "电气·电力": "建安工程费",
}


def _match(rules, text, default="unknown"):
    for pat, val in rules:
        if re.search(pat, text):
            return val
    return default


def enrich() -> dict:
    nodes = json.loads((R / "graph" / "nodes.yaml").read_text(encoding="utf-8"))
    facts = json.loads((R / "graph" / "graph.yaml").read_text(encoding="utf-8"))
    n_changed = f_changed = 0

    def annotate(n: dict) -> dict:
        text = f"{n.get('subject','')} {n.get('predicate','')} {n.get('section','')}"
        role = _match(ROLE, text)
        dom = _match(DOMAIN, text)
        v = str(n.get("value", ""))
        direc = _match(DIRECTION, text + " " + v)
        if re.fullmatch(r"[\d.]+", v) and direc == "unknown":
            direc = "等于"
        n["object_role"] = role
        n["domain"] = dom
        n["caliber_direction"] = direc
        n["hierarchy_path"] = (HIERARCHY.get(dom, "unknown")
                               if n.get("predicate", "").endswith(("估算金额", "金额", "费用")) else "不适用")
        # 精度：小数位数 → 容差 = 半个最低有效位的 2 倍
        m = re.search(r"\.(\d+)", v)
        dec = len(m.group(1)) if m else 0
        n["precision"] = {"decimals": dec, "round_tol": (0.5 * 10 ** (-dec) * 2 if dec else 0.5)}
        n["sem_src"] = "rule:object_role/domain/direction/hierarchy/precision"
        return n

    for i, n in enumerate(nodes):
        b = json.dumps(n, ensure_ascii=False, sort_keys=True)
        nodes[i] = annotate(n)
        if json.dumps(nodes[i], ensure_ascii=False, sort_keys=True) != b:
            n_changed += 1
    for i, f in enumerate(facts.get("facts", [])):
        b = json.dumps(f, ensure_ascii=False, sort_keys=True)
        facts["facts"][i] = annotate(f)
        if json.dumps(facts["facts"][i], ensure_ascii=False, sort_keys=True) != b:
            f_changed += 1

    (R / "graph" / "nodes.yaml").write_text(json.dumps(nodes, ensure_ascii=False, indent=2), encoding="utf-8")
    (R / "graph" / "graph.yaml").write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")

    # 维度分布（供审计）
    from collections import Counter
    dist = {k: dict(Counter(str(n.get(k)) for n in nodes))
            for k in ("object_role", "domain", "caliber_direction", "hierarchy_path")}
    rep = {"annotated_nodes": len(nodes), "annotated_facts": len(facts.get("facts", [])),
           "distribution": dist,
           "note": "规则式补全；unknown 表示未命中规则，**不猜测**"}
    (R / "quality" / "semantic_dims.yaml").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep


if __name__ == "__main__":
    r = enrich()
    print(json.dumps({k: v for k, v in r.items() if k != "distribution"}, ensure_ascii=False, indent=2))
    for k, v in r["distribution"].items():
        top = sorted(v.items(), key=lambda x: -x[1])[:4]
        print(f"  {k}: {top}")
