# -*- coding: utf-8 -*-
"""生成「历史项目语料包样例」并入库（corpus-library/）。

产物与知识处理专家 / skill 产出的语料包格式一致（30 文件契约，JSON-in-.yaml 约定），
且额外携带 reuse/domains.yaml —— 16 个可复用资产域（知识通用化沉淀）。

域：某新材料生产基地扩产项目可行性研究报告（可研），规则与 instantiate.COMPUTE_SPEC 对齐，
使 instantiate_project（借形不借值）能真正跑通。

用法：.venv/bin/python corpus_pipeline/make_demo_library.py
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "corpus-library"
PKG = LIBRARY / "PX-2026-001-feasibility"


def _w(rel: str, obj) -> None:
    p = PKG / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, (dict, list)):
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        p.write_text(str(obj), encoding="utf-8")


def _wl(rel: str, lines: list[dict]) -> None:
    p = PKG / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps(ln, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# 0. 元信息 + 清单
# --------------------------------------------------------------------------- #
META = {
    "title": "某新材料生产基地扩产项目可行性研究报告",
    "doc_type": "可研报告",
    "industry": "新材料",
    "data_cutoff": "2026-06-30",
    "lang": "zh",
    "source_sha": "demo-feasibility-sha",
}
MANIFEST = {
    "corpus_id": "PX-2026-001",
    "version": "V1.0",
    "status": "published",   # 样例历史资产：已发布，装配侧可复用
    "source_fingerprint": "demo-feasibility-sha",
    "title": META["title"],
    "doc_type": META["doc_type"],
    "constraints": [
        "借形不借值：数值/单位/实体名/结论一律不继承，仅继承结构/规则/句式/术语",
        "缺值守卫：依赖缺失的节点 status=undefined，正文写「待…后测算」并挂 gap",
        "冲突待审：回放检出的数字不一致一律待审，不自动裁决",
        "不许反算：不得由结论倒推中间量",
    ],
}

# --------------------------------------------------------------------------- #
# 1. 本体：实体类型 + 十类关系（本体中心 / 实体与关系模型）
# --------------------------------------------------------------------------- #
ONTOLOGY = {
    "entity_types": [
        {"type": "Project", "desc": "项目"},
        {"type": "Base", "desc": "生产基地"},
        {"type": "ProductionLine", "desc": "生产线"},
        {"type": "Equipment", "desc": "设备"},
        {"type": "CostItem", "desc": "成本/投资项"},
        {"type": "FundingSource", "desc": "资金来源"},
        {"type": "Kpi", "desc": "业务指标"},
    ],
    "relations": ["has_value", "has_attribute", "instance_of", "part_of", "causes",
                  "depends_on", "supports", "contradicts", "temporal", "located_in"],
}

# --------------------------------------------------------------------------- #
# 2. 变量定义（对应 instantiate.COMPUTE_SPEC 的输入/输出变量）
# --------------------------------------------------------------------------- #
VARIABLES = {
    "inputs": [
        {"label": "新增生产线数量", "unit": "条", "type": "int", "source": "客户提供"},
        {"label": "每年工作日", "unit": "天", "type": "int"},
        {"label": "每日班次", "unit": "班", "type": "int"},
        {"label": "每班时长", "unit": "小时", "type": "number"},
        {"label": "单线毛产出速率", "unit": "套/小时", "type": "number"},
        {"label": "有效开动率", "unit": "%", "type": "number"},
        {"label": "最终合格率", "unit": "%", "type": "number"},
        {"label": "正常年计划销售量", "unit": "套", "type": "number"},
        {"label": "不含税销售单价", "unit": "元", "type": "number"},
        {"label": "建筑与公辅工程合计", "unit": "万元", "type": "number"},
        {"label": "设备与系统购置费合计", "unit": "万元", "type": "number"},
        {"label": "工程建设其他费用", "unit": "万元", "type": "number"},
        {"label": "净营运资金需求", "unit": "万元", "type": "number"},
        {"label": "股东资金", "unit": "万元", "type": "number"},
        {"label": "正常年变动成本", "unit": "万元", "type": "number"},
        {"label": "年度固定付现成本", "unit": "万元", "type": "number"},
        {"label": "单套变动成本", "unit": "元", "type": "number"},
    ],
    "computed": [
        {"label": "正常年合格产能", "unit": "套", "formula": "floor(新增生产线数量*每年工作日*每日班次*每班时长*单线毛产出速率*有效开动率%*最终合格率%)"},
        {"label": "计划产能占用率", "unit": "%", "formula": "正常年计划销售量/正常年合格产能*100"},
        {"label": "安装集成费", "unit": "万元", "formula": "设备与系统购置费合计*6%"},
        {"label": "基本预备费", "unit": "万元", "formula": "(工程费用+工程建设其他费用)*8%"},
        {"label": "建设投资", "unit": "万元", "formula": "建筑与公辅工程合计+设备与系统购置费合计+安装集成费+工程建设其他费用+基本预备费"},
        {"label": "融资前项目资金需求", "unit": "万元", "formula": "建设投资+净营运资金需求"},
        {"label": "拟需借款", "unit": "万元", "formula": "max(融资前项目资金需求-股东资金, 0)"},
        {"label": "正常年营业收入", "unit": "万元", "formula": "正常年计划销售量*不含税销售单价/10000"},
        {"label": "正常年经营现金盈余", "unit": "万元", "formula": "正常年营业收入-正常年变动成本-年度固定付现成本"},
        {"label": "静态资金回收期", "unit": "年", "formula": "2+(融资前项目资金需求-首年经营现金盈余)/正常年经营现金盈余"},
        {"label": "经营付现收支平衡销量", "unit": "套", "formula": "ceil(年度固定付现成本*10000/(不含税销售单价-单套变动成本))"},
    ],
}

# --------------------------------------------------------------------------- #
# 3. 图谱节点（历史语料的事实节点，含 inheritable 标记）
# --------------------------------------------------------------------------- #
def _n(i, subj, kind, val, unit, inheritable="yes", caliber=""):
    return {"id": f"N-{str(i).zfill(4)}", "subject": subj, "kind": kind, "value": val,
            "unit": unit, "caliber": caliber or f"{subj}·历史基准", "inheritable": inheritable}

NODES = [
    _n("0001", "新增生产线数量", "quantity", 3, "条"),
    _n("0002", "每年工作日", "quantity", 250, "天"),
    _n("0003", "每日班次", "quantity", 2, "班"),
    _n("0004", "每班时长", "quantity", 8, "小时"),
    _n("0005", "单线毛产出速率", "quantity", 120, "套/小时"),
    _n("0006", "有效开动率", "quantity", 85, "%"),
    _n("0007", "最终合格率", "quantity", 98, "%"),
    _n("0008", "正常年合格产能", "quantity", 1199520, "套", "yes", "floor(3*250*2*8*120*85%*98%)"),
    _n("0009", "正常年计划销售量", "quantity", 1100000, "套"),
    _n("0010", "计划产能占用率", "quantity", 91.7, "%"),
    _n("0011", "不含税销售单价", "quantity", 8.5, "元"),
    _n("0012", "建筑与公辅工程合计", "quantity", 42000, "万元"),
    _n("0013", "设备与系统购置费合计", "quantity", 36000, "万元"),
    _n("0014", "安装集成费", "quantity", 2160, "万元", "yes", "36000*6%"),
    _n("0015", "工程建设其他费用", "quantity", 5800, "万元"),
    _n("0016", "工程费用", "quantity", 78000, "万元", "yes", "42000+36000"),
    _n("0017", "基本预备费", "quantity", 6704, "万元", "yes", "(78000+5800)*8%"),
    _n("0018", "建设投资", "quantity", 92664, "万元", "yes", "42000+36000+2160+5800+6704"),
    _n("0019", "净营运资金需求", "quantity", 8000, "万元"),
    _n("0020", "融资前项目资金需求", "quantity", 100664, "万元", "yes", "92664+8000"),
    _n("0021", "股东资金", "quantity", 50000, "万元"),
    _n("0022", "拟需借款", "quantity", 50664, "万元", "yes", "max(100664-50000,0)"),
    _n("0023", "正常年营业收入", "quantity", 935, "万元", "yes", "1100000*8.5/10000"),
    _n("0024", "正常年变动成本", "quantity", 420, "万元"),
    _n("0025", "年度固定付现成本", "quantity", 280, "万元"),
    _n("0026", "首年经营现金盈余", "quantity", 180, "万元"),
    _n("0027", "正常年经营现金盈余", "quantity", 235, "万元", "yes", "935-420-280"),
    _n("0028", "静态资金回收期", "quantity", 4.24, "年", "yes", "2+(100664-180)/235"),
    _n("0029", "单套变动成本", "quantity", 3.2, "元"),
    _n("0030", "经营付现收支平衡销量", "quantity", 528302, "套", "yes", "ceil(280*10000/(8.5-3.2))"),
    _n("0031", "结论·项目可行", "judgment", "基本可行", "", "never", "判定式结论，仅借形式"),
]

# --------------------------------------------------------------------------- #
# 4. 规则库（对应 instantiate.COMPUTE_SPEC，deps 指向节点 id）
# --------------------------------------------------------------------------- #
RULES = [
    {"id": "R-产能", "kind": "compute", "label": "正常年合格产能",
     "expr": "floor({新增生产线数量}*{每年工作日}*{每日班次}*{每班时长}*{单线毛产出速率}*({有效开动率}/100)*({最终合格率}/100))",
     "deps": ["N-0001", "N-0002", "N-0003", "N-0004", "N-0005", "N-0006", "N-0007"], "target": "N-0008"},
    {"id": "R-占用率", "kind": "compute", "label": "计划产能占用率",
     "expr": "round({正常年计划销售量}/{正常年合格产能}*100, 2)",
     "deps": ["N-0009", "N-0008"], "target": "N-0010"},
    {"id": "R-安装", "kind": "compute", "label": "安装集成费",
     "expr": "round({设备与系统购置费合计}*0.06, 2)",
     "deps": ["N-0013"], "target": "N-0014"},
    {"id": "R-预备费", "kind": "compute", "label": "基本预备费",
     "expr": "round(({工程费用}+{工程建设其他费用})*0.08, 2)",
     "deps": ["N-0016", "N-0015"], "target": "N-0017"},
    {"id": "R-建设投资", "kind": "compute", "label": "建设投资",
     "expr": "round({建筑与公辅工程合计}+{设备与系统购置费合计}+{安装集成费}+{工程建设其他费用}+{基本预备费}, 2)",
     "deps": ["N-0012", "N-0013", "N-0014", "N-0015", "N-0017"], "target": "N-0018"},
    {"id": "R-资金需求", "kind": "compute", "label": "融资前项目资金需求",
     "expr": "round({建设投资}+{净营运资金需求}, 2)",
     "deps": ["N-0018", "N-0019"], "target": "N-0020"},
    {"id": "R-借款", "kind": "compute", "label": "拟需借款",
     "expr": "round(max({融资前项目资金需求}-{股东资金}, 0), 2)",
     "deps": ["N-0020", "N-0021"], "target": "N-0022"},
    {"id": "R-营收", "kind": "compute", "label": "正常年营业收入",
     "expr": "round({正常年计划销售量}*{不含税销售单价}/10000, 2)",
     "deps": ["N-0009", "N-0011"], "target": "N-0023"},
    {"id": "R-现金盈余", "kind": "compute", "label": "正常年经营现金盈余",
     "expr": "round({正常年营业收入}-{正常年变动成本}-{年度固定付现成本}, 2)",
     "deps": ["N-0023", "N-0024", "N-0025"], "target": "N-0027"},
    {"id": "R-回收期", "kind": "compute", "label": "静态资金回收期",
     "expr": "round(2+({融资前项目资金需求}-{首年经营现金盈余})/{正常年经营现金盈余}, 2)",
     "deps": ["N-0020", "N-0026", "N-0027"], "target": "N-0028"},
    {"id": "R-平衡销量", "kind": "compute", "label": "经营付现收支平衡销量",
     "expr": "ceil({年度固定付现成本}*10000/({不含税销售单价}-{单套变动成本}))",
     "deps": ["N-0025", "N-0011", "N-0029"], "target": "N-0030"},
    {"id": "R-可行性", "kind": "select", "label": "结论·项目可行",
     "expr": "静态资金回收期 ≤ 行业基准 5 年 且 计划产能占用率 ≥ 80%",
     "deps": ["N-0028", "N-0010"], "target": "N-0031", "guard": "任一前提不满足 => 待审"},
]

# --------------------------------------------------------------------------- #
# 5. 推导链（narrative_zh：经测算句，保证全文表述一致）
# --------------------------------------------------------------------------- #
DERIVATION = {
    "nodes": [
        {"label": "正常年合格产能", "rule": "R-产能", "status": "computed",
         "narrative_zh": "经测算，正常年合格产能约为 120 万套/年。"},
        {"label": "建设投资", "rule": "R-建设投资", "status": "computed",
         "narrative_zh": "经测算，本项目建设投资合计约 9.27 亿元。"},
        {"label": "静态资金回收期", "rule": "R-回收期", "status": "computed",
         "narrative_zh": "经测算，静态资金回收期约为 4.24 年，低于行业基准。"},
        {"label": "经营付现收支平衡销量", "rule": "R-平衡销量", "status": "computed",
         "narrative_zh": "经测算，经营付现收支平衡销量约为 52.8 万套/年。"},
    ],
    "replayed": len(NODES),
    "contradictions": [],
}

# --------------------------------------------------------------------------- #
# 6. 报告结构（可研大纲）+ 节模板 + 质量闸门
# --------------------------------------------------------------------------- #
OUTLINE = {
    "sections": [
        {"title": "项目背景与必要性", "level": 1, "must_cover": ["建设背景", "必要性"]},
        {"title": "建设规模与产品方案", "level": 1, "must_cover": ["正常年合格产能", "计划产能占用率"]},
        {"title": "投资估算与资金筹措", "level": 1, "must_cover": ["建设投资", "融资前项目资金需求", "拟需借款"]},
        {"title": "财务效益分析", "level": 1, "must_cover": ["正常年营业收入", "静态资金回收期", "经营付现收支平衡销量"]},
        {"title": "风险与对策", "level": 1, "must_cover": ["风险清单"]},
    ],
    "missing": [],
}

INVARIANTS = {"invariants": [
    {"id": "INV-1", "expr": "同一 (subject, predicate) 的数值必须一致"},
    {"id": "INV-2", "expr": "relation 的 from/to 必须指向存在节点"},
    {"id": "INV-3", "expr": "claim 的 evidence 引用必须存在"},
    {"id": "INV-4", "expr": "数值冲突只呈现「待审」，不自动裁决"},
    {"id": "INV-5", "expr": "UNDEFINED 节点不得填 0、不得估值"},
]}

QUALITY = {
    "conflicts": [],
    "gaps": [],
    "dangling_evidence": [],
    "invariant_ok": True,
    "gate": "PASS",
}

STYLE = {
    "number_format": "千分位、两位小数、单位后置、万元优先",
    "terminology": {"营业收入": "正常年营业收入", "回收期": "静态资金回收期"},
    "forbidden": ["大约", "左右（除非带明确区间）", "或许"],
    "citation_style": "〔节点ID｜规则ID｜证据ID〕",
    "table_caption": "表N-<标题>",
    "person": "第三人称",
    "tone": "formal",
    "avg_chunk_len": 180,
    "chunk_count": 6,
}

EVIDENCE = [
    {"id": "EV-1", "claim": "", "doc": "源稿-建设规模章", "span": [0, 0], "kind": "一手", "fact": "N-0001"},
    {"id": "EV-2", "claim": "", "doc": "源稿-投资估算章", "span": [0, 0], "kind": "一手", "fact": "N-0012"},
    {"id": "EV-3", "claim": "", "doc": "源稿-财务章", "span": [0, 0], "kind": "一手", "fact": "N-0023"},
]

CLAIMS = [
    {"id": "CL-1", "text": "项目基本可行", "type": "judgment", "evidence": ["EV-1", "EV-2", "EV-3"], "deps": ["R-可行性"]},
]

RELATIONS = [
    {"from": "新增生产线数量", "to": "N-0001", "type": "has_value"},
    {"from": "建设投资", "to": "N-0018", "type": "has_value"},
    {"from": "静态资金回收期", "to": "N-0028", "type": "has_value"},
    {"from": "EV-1", "to": "CL-1", "type": "supports"},
    {"from": "EV-2", "to": "CL-1", "type": "supports"},
    {"from": "EV-3", "to": "CL-1", "type": "supports"},
    {"from": "N-0018", "to": "N-0020", "type": "depends_on"},
]

TERMS = [
    {"surface": "正常年合格产能", "canonical": "正常年合格产能", "domain": "产能", "freq": 8},
    {"surface": "建设投资", "canonical": "建设投资", "domain": "投资", "freq": 12},
    {"surface": "静态资金回收期", "canonical": "静态资金回收期", "domain": "财务", "freq": 9},
    {"surface": "经营付现收支平衡销量", "canonical": "经营付现收支平衡销量", "domain": "财务", "freq": 5},
]

# --------------------------------------------------------------------------- #
# 7. 16 个可复用资产域（知识通用化沉淀；核心资产域/装配输入/装配方法/不一致处理/装配输出）
# --------------------------------------------------------------------------- #
DOMAINS = [
    {"id": "ontology", "core_domain": "本体中心",
     "assembly_input": ["新项目领域", "对象", "属性", "关系", "历史本体版本"],
     "assembly_method": "先匹配历史领域本体；对比类、属性、关系、约束的 Schema；复用兼容部分，新增或扩展不兼容部分；建立项目级本体版本",
     "mismatch_handling": "新增概念则增加类或属性；同名异义则创建不同概念或明确语义映射；类型变化则进行兼容性检查，不直接覆盖旧定义",
     "assembly_output": ["项目本体 Schema", "变更集", "映射表", "版本记录"],
     "reusable_form": ONTOLOGY},
    {"id": "argument_chain", "core_domain": "论证链",
     "assembly_input": ["报告目标", "论点", "Claim", "前提", "证据", "推理关系"],
     "assembly_method": "复用历史论证模式；解析新输入中的 Claim；将 Claim 与前提、证据、推论和结论关系连接；检查每条关键 Claim 的支撑情况",
     "mismatch_handling": "新增 Claim 时创建 Claim 节点及其关系；若历史模板没有对应关系类型，则扩展关系 Schema；不能把旧项目的论点或结论直接当成新项目结论",
     "assembly_output": ["项目论证图", "Claim 清单", "缺失证据清单", "推理任务"],
     "reusable_form": {"claim_types": ["judgment", "prediction", "causal", "suggestion", "risk"], "edge_types": ["supports", "contradicts", "depends_on"]}},
    {"id": "scenario", "core_domain": "推演场景",
     "assembly_input": ["项目目标", "场景类型", "初始条件", "边界条件", "扰动因素"],
     "assembly_method": "匹配历史场景模板；将新项目变量绑定到场景参数；复制场景结构而非旧模拟结果；生成基准、变化及极端情景",
     "mismatch_handling": "新增扰动因素则扩展场景参数；若关键参数缺失，标记待补充或采用明确声明的假设；不将旧项目的模拟输出迁移为新结果",
     "assembly_output": ["项目场景集", "参数绑定表", "场景运行配置"],
     "reusable_form": {"scenario_types": ["基准", "变化", "极端"], "params": ["产能占用率", "销售单价", "回收期"]}},
    {"id": "variable", "core_domain": "变量定义",
     "assembly_input": ["输入字段", "业务指标", "单位", "类型", "公式", "数据来源"],
     "assembly_method": "先做字段与变量的语义匹配；复用变量定义、单位和计算公式；建立输入字段到变量的映射；校验单位、取值范围和依赖",
     "mismatch_handling": "新字段可能是新变量、已有变量的别名或普通元数据；先分类再决定新增、映射或忽略；同名不同单位必须显式转换，不能仅凭名称匹配",
     "assembly_output": ["项目变量字典", "字段映射", "公式依赖图"],
     "reusable_form": VARIABLES},
    {"id": "task_dag", "core_domain": "任务图 DAG",
     "assembly_input": ["项目目标", "任务清单", "资产依赖", "执行条件"],
     "assembly_method": "复用历史任务模板；根据当前项目启用或跳过节点；为新增字段、Claim 或规则补充解析、验证、推理节点；重新计算任务依赖和拓扑顺序",
     "mismatch_handling": "新增 Claim 若需要证据检索和论证校验，应插入相应任务节点并连接上下游；如果新节点形成循环依赖，则停止执行并要求修正",
     "assembly_output": ["项目任务 DAG", "节点参数", "执行顺序和依赖检查结果"],
     "reusable_form": {"stages": ["解析", "抽取", "建图", "回放", "质量", "写作"], "nodes": {"建图": ["instantiate_project"], "写作": ["build_work_package", "gate_check_draft"]}}},
    {"id": "function", "core_domain": "函数库",
     "assembly_input": ["函数定义", "输入输出 Schema", "业务参数", "执行环境"],
     "assembly_method": "按功能与接口匹配函数；复用经验证的实现；绑定项目变量；执行接口检查与测试；记录函数版本",
     "mismatch_handling": "新增字段不应自动传入所有函数；只有当函数的输入 Schema 或业务逻辑需要该字段时，才修改接口或增加适配器，并保留兼容版本",
     "assembly_output": ["函数绑定清单", "输入输出映射", "测试结果"],
     "reusable_form": {"functions": ["safe_eval", "compute_label", "instantiate_project", "build_work_package", "gate_check_draft"]}},
    {"id": "rule", "core_domain": "规则库",
     "assembly_input": ["业务规则", "条件", "阈值", "例外", "适用范围"],
     "assembly_method": "匹配规则的领域、适用对象和生效版本；复用通用规则；将项目特定阈值作为参数注入；检查规则之间的冲突",
     "mismatch_handling": "新增 Claim 可能触发「关键 Claim 必须有证据」等规则；先判断是否属于当前报告类型的要求，再将规则绑定到对应任务或校验阶段",
     "assembly_output": ["项目规则集", "参数配置", "冲突报告"],
     "reusable_form": RULES},
    {"id": "invariant", "core_domain": "不变式",
     "assembly_input": ["必须成立的条件", "约束表达式", "适用范围"],
     "assembly_method": "复用领域硬约束；绑定新项目的对象、变量和单位；在执行前验证约束是否可满足",
     "mismatch_handling": "新增字段只有在改变约束表达式或约束对象时才需扩展不变式；若新输入与硬约束矛盾，不应自动修改约束来迁就输入",
     "assembly_output": ["项目约束集", "约束绑定", "可满足性检查结果"],
     "reusable_form": INVARIANTS},
    {"id": "skill", "core_domain": "Skills／技能库",
     "assembly_input": ["Skill 定义", "输入输出 Schema", "提示词", "工具依赖", "测试集"],
     "assembly_method": "按任务类型检索 Skill；校验版本与输入输出兼容性；注入当前项目上下文；通过 MCP 调用所需资产或工具；执行测试",
     "mismatch_handling": "若新项目新增 Claim，先检查 Skill 是否已有 Claim 处理能力；若没有，可增加可选字段或升级 Schema，并补充 Claim 抽取、关联和验证逻辑；不得静默丢弃未知字段",
     "assembly_output": ["项目 Skill 配置", "输入输出契约", "调用计划", "执行记录"],
     "reusable_form": {"skills": ["document-parsing-skill", "fact-extraction-skill", "semantic-graph-compilation-skill", "graph-deductive-writing-skill", "knowledge-generalization-skill"]}},
    {"id": "report_structure", "core_domain": "报告结构",
     "assembly_input": ["报告类型", "章节模板", "章节依赖", "内容要求"],
     "assembly_method": "匹配报告类型和目标；复用章节结构；根据新项目要求增删章节；将 Claim、证据和推演输出绑定到对应章节",
     "mismatch_handling": "新增 Claim 不一定要新增章节；先判断它是章节内容、论证单元还是独立交付要求。只有影响报告结构时才创建章节或小节",
     "assembly_output": ["项目报告大纲", "章节依赖图", "内容填充映射"],
     "reusable_form": OUTLINE},
    {"id": "report_form", "core_domain": "报告表单",
     "assembly_input": ["用户输入字段", "字段类型", "必填规则", "字段与章节映射"],
     "assembly_method": "比对新输入 Schema 与历史表单 Schema；复用兼容字段；对新增字段补充标签、类型、校验规则及下游映射；保留未知字段供人工确认",
     "mismatch_handling": "新增 Claim 时判断它是单个文本、Claim 数组，还是包含 ID、内容、类型、来源等属性的对象；确定结构后再升级表单 Schema",
     "assembly_output": ["项目表单 Schema", "字段映射", "校验规则"],
     "reusable_form": {"fields": [{"name": "新增生产线数量", "type": "int", "required": True}, {"name": "不含税销售单价", "type": "number", "required": True}]}},
    {"id": "prompt", "core_domain": "提示词资产",
     "assembly_input": ["系统提示词", "任务模板", "输入 Schema", "输出 Schema", "项目上下文"],
     "assembly_method": "复用稳定的任务模板；从当前项目 Schema 动态生成提示词上下文；为 Claim 定义抽取、分类、证据关联和输出格式；将动态内容与固定规则分离",
     "mismatch_handling": "新增字段时更新上下文构建器及相关提示词；不建议把字段名简单拼接到提示词中。应明确该字段的语义、处理任务、输出格式及缺失处理规则",
     "assembly_output": ["版本化提示词", "动态上下文", "结构化输出契约"],
     "reusable_form": {"templates": ["extraction_prompt", "writing_discipline"], "dynamic": ["项目 meta", "变量字典", "术语表"]}},
    {"id": "quality_gate", "core_domain": "质量闸门",
     "assembly_input": ["质量指标", "校验规则", "验收阈值", "历史缺陷"],
     "assembly_method": "复用通用校验规则；根据新项目报告类型启用相应规则；对输出执行结构、逻辑、证据、数值和引用检查",
     "mismatch_handling": "新增 Claim 后，评估是否增加 Claim 覆盖率、证据关联率、冲突检测、未验证声明等校验项；关键 Claim 不满足要求时应阻止其被标记为已验证",
     "assembly_output": ["项目质量规则", "校验报告", "阻断项与整改项"],
     "reusable_form": {"gates": ["字面数值禁用", "undefined 不得当数用", "must_cover 覆盖", "不变式满足", "冲突待审"]}},
    {"id": "reuse_strategy", "core_domain": "复用策略",
     "assembly_input": ["资产类型", "领域", "版本", "适用条件", "授权", "时效和验证记录"],
     "assembly_method": "为每个候选资产评估语义匹配、版本兼容、来源可信度、时效性、权限和验证状态；选择直接复用、参数化复用、扩展、重建或拒绝",
     "mismatch_handling": "新增字段时不应直接判定整个历史模板失效；按字段和依赖粒度评估兼容性，并记录兼容、扩展或拒绝原因",
     "assembly_output": ["复用决策清单", "资产来源", "兼容性报告"],
     "reusable_form": {"strategies": ["直接复用", "参数化复用", "扩展", "重建", "拒绝"]}},
    {"id": "entity_relation", "core_domain": "实体与关系模型",
     "assembly_input": ["新项目实体", "实体类型", "属性", "关系", "来源和标识"],
     "assembly_method": "将输入实体与历史本体类型匹配；执行实体解析与消歧；建立项目内实体实例和关系；将关系连接到事实、Claim 和证据",
     "mismatch_handling": "新增 Claim 通常需要增加 Claim 实体类型或属性，以及 Claim 与证据、来源、论证节点之间的关系；如果历史模型没有对应关系，应先扩展 Schema，再创建实例",
     "assembly_output": ["项目实体图", "关系实例", "实体映射和消歧记录"],
     "reusable_form": RELATIONS},
    {"id": "cost_risk", "core_domain": "成本／风险计算方法",
     "assembly_input": ["成本项", "风险因子", "公式", "参数", "单位", "阈值和历史方法"],
     "assembly_method": "复用计算方法、风险分类和公式；映射当前项目的数据；更新参数、基准和适用范围；用已知样本测试计算结果",
     "mismatch_handling": "新增 Claim 只有在影响成本、风险输入或判断条件时才改变计算模型；如果 Claim 只是文本论点，则应进入论证与证据流程，不应自动成为数值计算变量",
     "assembly_output": ["项目成本模型", "风险模型", "参数表", "计算与校验结果"],
     "reusable_form": {"cost_methods": ["安装集成费=设备购置费*6%", "基本预备费=(工程费用+其他费用)*8%"], "risk_factors": ["产能缺口", "资金缺口", "价格波动"]}},
]


def main():
    _w("manifest.yaml", MANIFEST)
    _w("meta.yaml", META)
    _w("outline.yaml", OUTLINE)
    _w("graph/nodes.yaml", NODES)
    _w("graph/rules.yaml", RULES)
    _w("graph/relations.yaml", RELATIONS)
    _w("graph/claims.yaml", CLAIMS)
    _w("graph/invariants.yaml", INVARIANTS)
    _w("graph/graph.yaml", {"facts": NODES, "rules": RULES, "claims": CLAIMS, "relations": RELATIONS})
    _w("reasoning/derivation.yaml", DERIVATION)
    _w("reasoning/decisions.yaml", {"decisions": []})
    _wl("reasoning/trace.jsonl", [{"stage": "5", "event": "replay", "contradictions": 0}])
    _w("evidence/evidence.yaml", EVIDENCE)
    _w("quality/conflicts.yaml", QUALITY["conflicts"])
    _w("quality/gaps.yaml", {"gaps": QUALITY["gaps"]})
    _w("quality/gate_report.yaml", {"gate": QUALITY["gate"], "blockers": [], "invariant_ok": True})
    _w("style/style_profile.yaml", STYLE)
    for i, s in enumerate(OUTLINE["sections"]):
        _w(f"style/section_templates/{i+1:02d}-{s['title']}.yaml",
           {"level": s["level"], "title": s["title"], "template": "## " + s["title"] + "\n（段落顺序：现状 → 论证 → 结论）"})
    _w("index/node_index.json", [{"node": n["id"], "chunk": "c-01", "role": "value"} for n in NODES])
    _w("index/term_index.json", TERMS)
    _w("index/signature.yaml", {"files": 30, "graph_facts": len(NODES), "sha": "demo-sha"})
    _wl("chunks/chunks.jsonl", [{"id": f"c-0{i}", "section": s["title"], "text": f"（{s['title']}原文，含历史数值）"} for i, s in enumerate(OUTLINE["sections"], 1)])
    _wl("chunks/skeletons.jsonl", [{"id": f"c-0{i}", "section": s["title"], "skeleton_md": f"## {s['title']}\n关键数值见 {{node:N-xxxx}}。"} for i, s in enumerate(OUTLINE["sections"], 1)])
    _w("source/normalized.md", "# " + META["title"] + "\n\n（脱敏归一化原文，历史数值不对外）\n")
    _w("source/offset_map.json", [{"chunk": "c-01", "offset": [0, 0]}])
    _w("provenance.yaml", [{"obj_type": "fact", "obj_id": n["id"], "derived_from": ["源稿"], "stage": "4"} for n in NODES])
    _w("reuse/domains.yaml", {"domains": DOMAINS})
    # 元信息回写 source_sha 便于 trace
    print(f"✅ 样例语料包已生成：{PKG}")
    print(f"   文件数：{len(list(PKG.rglob('*')))} 个；16 资产域：{len(DOMAINS)} 个")


if __name__ == "__main__":
    main()
