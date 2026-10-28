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

# ===== 高校科研用房可研 =====
# **来源：形包 functions/derivation_templates.yaml（已验证正确的版本）**
# 不用上财 graph/rules.yaml —— 后者含已知缺陷（见形包 ontology/known-defects.yaml）：
#   · DF1 R-总计算负荷 缺 需要系数×同时使用系数
#   · DF8 R-资金筹措构成 与 R-总投资构成 target 重名
#   · 分中心名硬编码（项目专属）
EDU_RESEARCH_COMPUTE_SPEC = {
    "总投资": {"spec": "round({建安工程费用}+{工程建设其他费用}+{预备费}+{原建筑拆除费用}, 2)", "unit": ""},
    "总建筑面积": {"spec": "round({地上建筑面积}+{地下建筑面积}, 0)", "unit": ""},
    "公共服务配套用房建筑面积": {"spec": "round({公共服务配套用房使用面积合计}/{公共服务配套用房综合平面利用系数}, 0)", "unit": ""},
    "地上总建筑面积需求": {"spec": "round({科研人员规划人数}*{科研人员用房人均建筑面积指标}+{研究生博士生访问学者规划人数}*{研究生博士生访问学者用房人均建筑面积指标}+{公共服务配套用房建筑面积}, 0)", "unit": ""},
    "科研人员规划人数": {"spec": "{子系统1·规划科研人员}+{子系统2·规划科研人员}+{子系统3·规划科研人员}+{子系统4·规划科研人员}", "unit": ""},
    "研究生博士生访问学者规划人数": {"spec": "{子系统1·规划研究生博士生访问学者}+{子系统2·规划研究生博士生访问学者}+{子系统3·规划研究生博士生访问学者}+{子系统4·规划研究生博士生访问学者}", "unit": ""},
    "建筑高度控制": {"spec": "round({一层层高}+({层数}-1)*{标准层层高}, 1)", "unit": ""},
    "最高日用水量": {"spec": "round(({科研学生用水人数}*{科研学生用水定额}+{办公用水人数}*{办公用水定额})/1000*(1+{未预见系数}/100), 2)", "unit": ""},
    "消防用水量总计": {"spec": "{室外消火栓系统用水量}+{室内消火栓系统用水量}+{自动喷水灭火系统用水量}", "unit": ""},
    "总计算负荷": {"spec": "round({负荷估算面积口径}*({空调负荷密度指标}+{照明及其他负荷密度指标})*{需要系数}*{同时使用系数}/1000, 0)", "unit": ""},
    "冷负荷": {"spec": "round({本项目建筑面积}*{单位面积冷负荷指标}/1000, 0)", "unit": ""},
    "热负荷": {"spec": "round({本项目建筑面积}*{单位面积热负荷指标}/1000, 0)", "unit": ""},
    "多联机装机冷量": {"spec": "{30HP机组单台制冷量}*{30HP机组台数}+{16HP机组单台制冷量}*{16HP机组台数}+{10HP机组单台制冷量}*{10HP机组台数}", "unit": ""},
    "年总用水量": {"spec": "round({教师用水日水量}*{年工作天数}/10000, 2)+round({学生用水日水量}*{年工作天数}/10000, 2)+round(({教师用水日水量}+{学生用水日水量})*{年工作天数}/10000*({未预见系数}/100), 2)", "unit": ""},
    "年总耗电量": {"spec": "round(({科研用房用电面积}*{科研用房用电指标}*{科研用房需要系数}*{科研用房同时使用系数}+{公共配套服务用房用电面积}*{公共配套服务用房用电指标}*{公共配套服务用房需要系数}*{公共配套服务用房同时使用系数})*{日均工作小时数}*{年工作天数}/10000000, 1)", "unit": ""},
    "综合能耗（当量值）": {"spec": "round({年总耗电量}*{电力折标系数当量值}+{年总用水量}*{水折标系数}, 0)", "unit": ""},
    "单位面积综合能耗（当量值）": {"spec": "round({综合能耗（当量值）}*1000/{本项目建筑面积}, 2)", "unit": ""},
    "单位建筑面积电耗": {"spec": "round({年总耗电量}*10000/{本项目建筑面积}, 2)", "unit": ""},
    "基本预备费": {"spec": "round(({建筑安装工程费用}+{工程建设其他费})*{基本预备费费率}/100, 2)", "unit": ""},
    "建筑安装工程费用": {"spec": "round({单体工程}+{室外总体工程}+{抗震支架}+{绿色二星增量费用}, 2)", "unit": ""},
    "单体工程": {"spec": "round({土建工程}+{安装工程}, 2)", "unit": ""},
    "土建工程": {"spec": "round({桩基工程}+{基坑围护工程}+{地下建筑结构工程}+{地上建筑结构工程}+{装配式结构增加费}+{室内装饰工程}+{外立面及屋面装饰工程}, 2)", "unit": ""},
    "安装工程": {"spec": "round({给排水工程}+{消防工程}+{通风空调工程}+{强电工程}+{弱电工程}+{电梯工程}, 2)", "unit": ""},
    "室外总体工程": {"spec": "round({道路广场硬地铺装}+{绿化景观}+{室外安装工程}+{标识工程}, 2)", "unit": ""},
    "工程建设其他费": {"spec": "round({建设单位管理费}+{前期工程咨询费}+{勘察费}+{设计费}+{招标代理费}+{清单及标底编制费}+{施工监理费}+{施工图审图费}+{竣工图编制费}+{场地准备及临时设施费}+{低压电缆}+{人防易地建设费}, 2)", "unit": ""},
    "单位造价（总投资口径）": {"spec": "round({总投资}*10000/{本项目建筑面积}, 0)", "unit": ""},
    "总投资（筹措口径）": {"spec": "round({国拨资金}+{学校自筹资金}, 2)", "unit": ""},
    "国拨资金占比": {"spec": "round({国拨资金}/{总投资}*100, 2)", "unit": ""},
    "资产负债率": {"spec": "round({负债总额}/{资产总额}*100, 2)", "unit": ""},
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
COMPUTE_SPEC = {**FEASIBILITY_COMPUTE_SPEC, **EDU_RESEARCH_COMPUTE_SPEC}


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
