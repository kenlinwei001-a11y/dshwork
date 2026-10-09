# -*- coding: utf-8 -*-
"""领域规则库 —— 知识处理侧单一事实源。

把「可研报告」等领域的计算规则（原 instantiate.py 硬编码的 COMPUTE_SPEC）下沉为
知识处理侧的领域资产：

  - corpus_run 按 doc_type 经 rules_for_domain/inject_domain_rules 产出 label 对齐的 rules；
  - instantiate.py 从这里 import 计算规格（COMPUTE_SPEC / DISPLAY_RULES）；
  - 抽取层抽出的自然语言规则 label 经 resolve_label（TERM_ALIASES 术语映射）自动对齐。

原则：规则/公式/术语归一的知识只存一份（本模块），推演写作侧只消费、不重复定义。
"""
from __future__ import annotations
import re

# 可研报告计算规则：label → {spec(公式模板，{变量} 占位), unit}
FEASIBILITY_COMPUTE_SPEC = {
    "正常年合格产能": {"spec": "floor({新增生产线数量}*{每年工作日}*{每日班次}*{每班时长}*{单线毛产出速率}*({有效开动率}/100)*({最终合格率}/100))", "unit": "套"},
    "计划产能占用率": {"spec": "round({正常年计划销售量}/{正常年合格产能}*100, 2)", "unit": "%"},
    "安装集成费": {"spec": "round({设备与系统购置费合计}*0.06, 2)", "unit": "万元"},
    "基本预备费": {"spec": "round(({工程费用}+{工程建设其他费用})*0.08, 2)", "unit": "万元"},
    "建设投资": {"spec": "round({建筑与公辅工程合计}+{设备与系统购置费合计}+{安装集成费}+{工程建设其他费用}+{基本预备费}, 2)", "unit": "万元"},
    "融资前项目资金需求": {"spec": "round({建设投资}+{净营运资金需求}, 2)", "unit": "万元"},
    "拟需借款": {"spec": "round(max({融资前项目资金需求}-{股东资金}, 0), 2)", "unit": "万元"},
    "正常年营业收入": {"spec": "round({正常年计划销售量}*{不含税销售单价}/10000, 2)", "unit": "万元"},
    "正常年经营现金盈余": {"spec": "round({正常年营业收入}-{正常年变动成本}-{年度固定付现成本}, 2)", "unit": "万元"},
    "静态资金回收期": {"spec": "round(2+({融资前项目资金需求}-{首年经营现金盈余})/{正常年经营现金盈余}, 2)", "unit": "年"},
    "经营付现收支平衡销量": {"spec": "ceil({年度固定付现成本}*10000/({不含税销售单价}-{单套变动成本}))", "unit": "套"},
}

# 展示类规则（不参与计算，随骨架借形）
DISPLAY_RULES = {"R-金额精度"}

# 输入变量定义（COMPUTE_SPEC 公式中出现的输入变量的 unit/type，语义对齐的「属性」概念来源）
FEASIBILITY_VARIABLES = {
    "新增生产线数量": {"unit": "条", "type": "int", "source": "客户提供"},
    "每年工作日": {"unit": "天", "type": "int"},
    "每日班次": {"unit": "班", "type": "int"},
    "每班时长": {"unit": "小时", "type": "number"},
    "单线毛产出速率": {"unit": "套/小时", "type": "number"},
    "有效开动率": {"unit": "%", "type": "number"},
    "最终合格率": {"unit": "%", "type": "number"},
    "正常年计划销售量": {"unit": "套", "type": "number"},
    "不含税销售单价": {"unit": "元", "type": "number"},
    "建筑与公辅工程合计": {"unit": "万元", "type": "number"},
    "设备与系统购置费合计": {"unit": "万元", "type": "number"},
    "工程费用": {"unit": "万元", "type": "number"},
    "工程建设其他费用": {"unit": "万元", "type": "number"},
    "净营运资金需求": {"unit": "万元", "type": "number"},
    "股东资金": {"unit": "万元", "type": "number"},
    "正常年变动成本": {"unit": "万元", "type": "number"},
    "年度固定付现成本": {"unit": "万元", "type": "number"},
    "首年经营现金盈余": {"unit": "万元", "type": "number"},
    "单套变动成本": {"unit": "元", "type": "number"},
}

# 术语归一映射：表面词/别名 → 规范 label（抽取层自动对齐用）
TERM_ALIASES = {
    # 产能
    "产能": "正常年合格产能", "合格产能": "正常年合格产能", "年产能": "正常年合格产能", "设计产能": "正常年合格产能",
    # 营收
    "营业收入": "正常年营业收入", "营业总收入": "正常年营业收入", "总营收": "正常年营业收入", "年收入": "正常年营业收入",
    # 投资
    "总投资": "建设投资", "建设总投资": "建设投资", "项目总投资": "建设投资", "投资": "建设投资",
    # 回收期
    "回收期": "静态资金回收期", "投资回收期": "静态资金回收期", "静态回收期": "静态资金回收期", "回本期": "静态资金回收期",
    # 借款
    "借款": "拟需借款", "融资额": "拟需借款", "贷款需求": "拟需借款",
    # 平衡销量
    "盈亏平衡销量": "经营付现收支平衡销量", "盈亏平衡点": "经营付现收支平衡销量", "保本销量": "经营付现收支平衡销量",
    # 现金盈余
    "经营现金流": "正常年经营现金盈余", "现金盈余": "正常年经营现金盈余",
    # 资金需求
    "资金需求": "融资前项目资金需求", "项目资金需求": "融资前项目资金需求",
    # 预备费/安装
    "预备费": "基本预备费", "安装费": "安装集成费", "集成费": "安装集成费",
    # 占用率
    "产能利用率": "计划产能占用率", "产能占用率": "计划产能占用率",
}

# doc_type → 计算规格（领域注册表；未知 doc_type 回退可研规则库）
DOMAIN_REGISTRY = {
    "可研报告": FEASIBILITY_COMPUTE_SPEC,
    "可行性研究报告": FEASIBILITY_COMPUTE_SPEC,
    "feasibility": FEASIBILITY_COMPUTE_SPEC,
}

# 向后兼容别名（instantiate.py 从这里 import）
COMPUTE_SPEC = FEASIBILITY_COMPUTE_SPEC


def _spec_for(doc_type: str | None) -> dict:
    if not doc_type:
        return FEASIBILITY_COMPUTE_SPEC
    return DOMAIN_REGISTRY.get(doc_type, FEASIBILITY_COMPUTE_SPEC)


def resolve_label(raw_label: str, doc_type: str | None = None) -> str:
    """把自然语言 label 归一为领域规则库的规范 label。

    顺序：精确匹配规范 label → 术语别名映射 → 原样返回（无法归一）。
    """
    if not raw_label:
        return raw_label
    spec = _spec_for(doc_type)
    if raw_label in spec:
        return raw_label
    return TERM_ALIASES.get(raw_label, raw_label)


def rules_for_domain(doc_type: str | None = None) -> list[dict]:
    """产出某领域的计算规则（label/spec/deps/target 对齐计算规格），供 corpus_run 注入。"""
    spec = _spec_for(doc_type)
    rules = []
    for label, s in spec.items():
        deps = re.findall(r'\{([^{}]+)\}', s["spec"])
        rules.append({
            "id": f"R-{label}",
            "kind": "compute",
            "label": label,
            "expr": s["spec"],
            "deps": deps,
            "target": label,
            "guard": "missing_any_dep => undefined",
        })
    return rules


def inject_domain_rules(graph: dict, doc_type: str | None) -> dict:
    """把领域规则库注入 graph["rules"]，并把已有 rules（LLM 抽取）的 label 经术语映射归一。

    领域规则优先：与 LLM 抽取规则同 label 的不重复注入；LLM 规则 label 若为别名则归一。
    """
    if not doc_type:
        return graph
    existing = graph.get("rules", [])
    normalized, seen_labels = [], set()
    for r in existing:
        r = dict(r)
        raw_label = r.get("label") or r.get("id", "")
        r["label"] = resolve_label(raw_label, doc_type)
        normalized.append(r)
        seen_labels.add(r["label"])

    injected = [r for r in rules_for_domain(doc_type) if r["label"] not in seen_labels]
    graph["rules"] = normalized + injected
    return graph
