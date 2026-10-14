# -*- coding: utf-8 -*-
"""16 个可复用资产域的「本项目沉淀」（LLM 语义层产物）。

借形不借值：这里给出的是**结构 / 规则 / 关系 / 句式 / 术语 / 口径**，
项目专属数值只以「口径说明 + 溯源指针」形式出现（nodes/claims/chunks 由发射器解析成真实 ID），
下游装配时按新项目数据重算，不继承本项目数值。
"""

DOMAIN_SOURCE = {
    # ------------------------------------------------------------------ 1 本体
    "ontology": {
        "entity_types": [
            {"type": "Project", "cn": "建设项目", "desc": "可研的对象，本例为一个拆除重建的科研用房单体"},
            {"type": "OwnerUnit", "cn": "建设单位", "desc": "高校及其内部管理机构（基建处/审计处/财务处/后勤）"},
            {"type": "Campus", "cn": "校区", "desc": "多校区高校的一个校区，含四至与功能定位"},
            {"type": "Building", "cn": "房屋建筑", "desc": "单体建筑，含层数/高度/结构形式/耐火与抗震等级"},
            {"type": "ExistingBuilding", "cn": "既有建筑", "desc": "拟拆除的原有建筑（建设年代/面积/结构类型/现状缺陷）"},
            {"type": "ResearchCenter", "cn": "科研机构", "desc": "研究中心/研究院/实验室，规模论证的组织单元"},
            {"type": "Room", "cn": "用房", "desc": "科研用房与公共服务配套用房（交流讨论/报告厅/阅览/档案…）"},
            {"type": "PersonCategory", "cn": "人员类别", "desc": "科研人员、研究生/博士生/访问学者——人均指标不同，必须分类"},
            {"type": "CostItem", "cn": "费用项", "desc": "投资估算的树状费用项（分项→单位工程→专业工程）"},
            {"type": "FundingSource", "cn": "资金来源", "desc": "国拨资金 / 学校自筹，含年度需求与占比"},
            {"type": "Kpi", "cn": "技术经济指标", "desc": "面积、造价、能耗、负荷等可复算指标"},
            {"type": "Mandate", "cn": "政策法规与标准", "desc": "规划纲要、行业规定、国家标准/地方标准/定额、批复文件"},
            {"type": "Discipline", "cn": "学科", "desc": "支撑必要性论证的学科（本例为统计学与经管学科群）"},
            {"type": "Equipment", "cn": "设备", "desc": "大型机电设备（多联机/水泵/风机/变压器/电梯），带台数与参数"},
            {"type": "Schedule", "cn": "进度节点", "desc": "方案设计→初步设计→施工图→招标→施工→竣工验收"},
            {"type": "Risk", "cn": "风险因素", "desc": "社会稳定风险与工程质量安全风险因子"},
        ],
        "relations": ["has_value", "has_attribute", "instance_of", "part_of", "causes",
                      "depends_on", "supports", "contradicts", "temporal", "located_in"],
        "notes": [
            "Mandate 一个节点四种角色：driver(mandates)/benchmark(complies_with)/warrant(warrants)/domain(constrains)，不塌缩",
            "PersonCategory 必须分类建模：科研人员与研究生的人均建筑面积指标不同，只给总数无法测算",
            "CostItem 必须建到「能由别的数算出」的那一层，否则汇总值无法重算",
        ],
        "sources": {"chunks": ["c-8dfde7c45562", "c-79069a20782b", "c-d8eaa250581d", "c-e6649218e0c0", "c-067b6352bde6"]},
    },

    # ------------------------------------------------------------------ 2 实体与关系模型
    "entity_relation": {
        "relation_examples": [
            {"from": "大数据研究中心", "to": "上海财经大学", "type": "part_of", "note": "机构→单位"},
            {"from": "大数据研究中心", "to": "中山北一路校区", "type": "located_in", "note": "单体→校区"},
            {"from": "原第五教学楼", "to": "大数据研究中心", "type": "causes", "note": "拆除重建的因果关系"},
            {"from": "管理科学与量化信息研究中心", "to": "大数据研究中心", "type": "part_of", "note": "四个科研机构均 part_of"},
            {"from": "公共服务配套用房·交流讨论室", "to": "公共服务配套用房", "type": "part_of"},
            {"from": "总投资", "to": "建筑安装工程费用", "type": "depends_on", "note": "费用层级依赖"},
            {"from": "地上总建筑面积需求", "to": "科研人员规划人数", "type": "depends_on"},
            {"from": "地上总建筑面积需求", "to": "地上建筑面积", "type": "contradicts",
             "note": "测算需求大于实建设计，构成必须显式化的矛盾（待审）"},
            {"from": "EV-必要性-01", "to": "CL-必要性-01", "type": "supports"},
            {"from": "开工时间", "to": "建设工期", "type": "temporal"},
        ],
        "resolution_notes": [
            "机构名消歧：本报告同时出现「统计与管理学院」「数据科学与统计研究院」「数据科研与统计研究院」——同名异写，须经实体注册表消歧后再建边",
            "章节标题里的用房与表内的用房须按业务名归一（如「数据/语音通信系统与综合布线系统」是专业系统不是用房）",
        ],
        "sources": {"chunks": ["c-223358da3e9d", "c-d8ff50ae58f4", "c-b506cede9b46"], "claims": ["CL-规模-01"]},
    },

    # ------------------------------------------------------------------ 3 变量定义
    "variable": {
        "inputs": [
            {"label": "分类人数——科研人员", "unit": "人", "type": "int", "note": "按科研机构逐中心给出后合计"},
            {"label": "分类人数——研究生/博士生/访问学者", "unit": "人", "type": "int"},
            {"label": "人均建筑面积指标——科研人员", "unit": "㎡/人", "type": "number", "source": "规范给定上限"},
            {"label": "人均建筑面积指标——研究生等", "unit": "㎡/人", "type": "number", "source": "规范给定上限"},
            {"label": "公共服务配套用房使用面积合计", "unit": "㎡", "type": "number"},
            {"label": "综合平面利用系数", "unit": "-", "type": "number"},
            {"label": "各费用项金额", "unit": "万元", "type": "number", "note": "逐分项，不由合计反推"},
            {"label": "各费用项单位造价", "unit": "元/㎡ 或 元/m 或 元/部", "type": "number"},
            {"label": "国拨资金", "unit": "万元", "type": "number"},
            {"label": "学校自筹资金", "unit": "万元", "type": "number"},
            {"label": "基本预备费费率", "unit": "%", "type": "number"},
            {"label": "装配率", "unit": "%", "type": "number"},
            {"label": "用水定额", "unit": "L/人·日", "type": "number"},
            {"label": "未预见系数", "unit": "%", "type": "number"},
            {"label": "用电指标 / 需要系数 / 同时使用系数", "unit": "W/㎡ / - / -", "type": "number"},
            {"label": "单位面积冷负荷指标 / 热负荷指标", "unit": "W/㎡", "type": "number"},
            {"label": "折标系数（电力当量值 / 水）", "unit": "tce/万kW·h、tce/万m³", "type": "number"},
            {"label": "年工作天数", "unit": "d", "type": "int"},
        ],
        "computed": [
            {"label": "科研人员规划人数", "unit": "人", "formula": "各科研中心科研人员之和"},
            {"label": "研究生博士生访问学者规划人数", "unit": "人", "formula": "各科研中心研究生之和"},
            {"label": "公共服务配套用房建筑面积", "unit": "㎡", "formula": "使用面积合计 / 综合平面利用系数"},
            {"label": "地上总建筑面积需求", "unit": "㎡",
             "formula": "科研人员数×科研人均指标 + 研究生数×研究生人均指标 + 配套用房建筑面积"},
            {"label": "总建筑面积", "unit": "㎡", "formula": "地上建筑面积 + 地下建筑面积"},
            {"label": "基本预备费", "unit": "万元", "formula": "(建筑安装工程费用 + 工程建设其他费) × 费率"},
            {"label": "建筑安装工程费用", "unit": "万元", "formula": "单体工程 + 室外总体工程 + 抗震支架 + 绿色二星增量费用"},
            {"label": "总投资", "unit": "万元", "formula": "建安工程费用 + 工程建设其他费用 + 预备费 + 拆除费用"},
            {"label": "单位造价", "unit": "元/㎡", "formula": "总投资 / 总建筑面积"},
            {"label": "国拨资金占比", "unit": "%", "formula": "国拨资金 / 总投资"},
            {"label": "资产负债率", "unit": "%", "formula": "负债总额 / 资产总额"},
            {"label": "最高日用水量", "unit": "m³/d", "formula": "(分类人数×用水定额)/1000 ×(1+未预见系数)"},
            {"label": "消防用水量", "unit": "L/s", "formula": "室外消火栓 + 室内消火栓 + 自动喷水"},
            {"label": "年用电量", "unit": "万kW·h", "formula": "Σ(面积×用电指标×需要系数×同时使用系数)×日工时×年天数"},
            {"label": "冷负荷 / 热负荷", "unit": "kW", "formula": "建筑面积 × 单位面积(冷|热)负荷指标"},
            {"label": "综合能耗（当量值/等价值）", "unit": "tce", "formula": "Σ(能耗量 × 折标系数)"},
            {"label": "单位面积综合能耗 / 单位建筑面积电耗", "unit": "kgce/㎡、kW·h/㎡", "formula": "能耗 / 总建筑面积"},
        ],
        "unit_traps": [
            "未预见系数原文以 % 表达（10），公式中须 /100，否则结果放大 100 倍",
            "用电量由 W·h 折「万 kW·h」除数为 1e7（不是 1e4），否则结果放大 1000 倍",
            "「万元」与「元」在单位造价与分项金额之间必须显式换算",
        ],
        "sources": {"chunks": ["c-79069a20782b", "c-d8eaa250581d", "c-951d51ce96e3", "c-46385d4ae269", "c-9b17de8351af"],
                    "rules": ["R-应建规模", "R-总投资构成", "R-年用电量", "R-综合能耗"]},
    },

    # ------------------------------------------------------------------ 4 规则库
    "rule": {
        "chain_notes": [
            "规模链：表5-1~5-4 逐中心人数 → 合计 315/1350 → 人均指标法 → 地上需求 18040 ㎡ → 与设计 18000 ㎡ 比对",
            "造价链：逐行单位造价×数量 → 分项 → 单位工程 → 单体/室外 → 建安工程费 → 总投资（分项之和与表列合计存在多处 ±1 与一处 6.12% 差异）",
            "资金链：总投资 → 国拨+自筹 → 年度需求 → 学校财务能力（资产负债率）",
            "能耗链：分类人数/面积 → 用水量·用电量 → 折标 → 综合能耗 → 单位面积能耗",
        ],
        "verified_closure": ["R-建筑面积构成", "R-土建工程", "R-总投资构成", "R-资金筹措构成", "R-国拨资金占比",
                             "R-资产负债率", "R-最高日用水量", "R-消防用水量合计", "R-冷负荷", "R-热负荷",
                             "R-年用水量", "R-综合能耗"],
        "sources": {"rules": ["R-应建规模", "R-总投资构成", "R-基本预备费", "R-室外总体工程", "R-年用电量"]},
    },

    # ------------------------------------------------------------------ 5 不变式
    "invariant": {
        "invariants": [
            {"id": "INV-1", "expr": "同一 (subject, predicate) 的数值必须一致", "scope": "全图", "level": "error"},
            {"id": "INV-2", "expr": "relation 的 from/to 必须指向存在的节点", "scope": "全图", "level": "error"},
            {"id": "INV-3", "expr": "claim 的 evidence 引用必须存在", "scope": "claims", "level": "error"},
            {"id": "INV-4", "expr": "数值冲突只呈现「待审」，不自动裁决", "scope": "conflicts", "level": "hard"},
            {"id": "INV-5", "expr": "UNDEFINED 节点不得填 0、不得估值", "scope": "nodes", "level": "hard"},
            {"id": "INV-6", "expr": "派生值不得手填（总投资必须由分项算出）", "scope": "rules", "level": "hard"},
            {"id": "INV-7", "expr": "依赖存在未裁决冲突时，派生校核必须阻塞而非取一值硬算", "scope": "rules", "level": "hard"},
            {"id": "INV-8", "expr": "软约束（规范版本/定额/造价指标）被新证据替换要走适配性评估并留痕，不算冲突裁决", "scope": "evidence", "level": "hard"},
            {"id": "INV-9", "expr": "硬约束的值变更，来源不得是检索结果", "scope": "evidence", "level": "hard"},
        ],
        "notes": ["INV-7 在本项目被实测触发：总建筑面积 18319/18219 冲突未裁决，导致 5 条派生规则阻塞"],
        "sources": {"conflicts": ["本项目·总建筑面积"]},
    },

    # ------------------------------------------------------------------ 6 论证链
    "argument_chain": {
        "claim_types": ["fact", "hypothesis", "inference", "conclusion", "recommendation"],
        "nature_types": ["judgment", "prediction", "causal", "suggestion", "risk"],
        "edge_types": ["supports", "contradicts", "depends_on"],
        "toulmin_template": {
            "claim": "本项目应当立项建设 / 项目可行",
            "grounds": "分类事实（人数、面积、造价、政策、现状缺陷）",
            "warrant": "从「国家/上位要求」到「本项目必须建」的推理许可——**最常被省略、也是评审最爱抓的断链点**",
            "backing": "法规文号 / 规范条款 / 内部规划 / 学校财务数据",
            "qualifier": "充分 / 基本合理 / 有保障 / 低风险",
            "rebuttal": "显式写出反证或未闭合项，不隐藏",
        },
        "necessity_dimensions": [
            {"id": "D1", "name": "国家与行业背景（新兴领域科研水平、创新驱动）", "warrant_present": False},
            {"id": "D2", "name": "区域发展（地方大数据研究机构空缺）", "warrant_present": False},
            {"id": "D3", "name": "校区设施条件（既有建筑老化、功能不符）", "warrant_present": True},
            {"id": "D4", "name": "学校战略（双一流、一流学科建设）", "warrant_present": True},
        ],
        "broken_links": [
            {"dimension": "D1", "note": "原文只给「国家有大数据战略/创新驱动」与结论，中间「所以本校要建」的保证未写出"},
            {"dimension": "D2", "note": "以「同类高校已建、本校缺失」作论据，未展开「缺失 ⇒ 必须自建」的保证（亦未论证共建/共享等替代方案）"},
        ],
        "compliance_template": "政策法规符合性对照表不是手写的，是 complies_with 边全集的渲染结果",
        "sources": {"claims": ["CL-必要性-01", "CL-必要性-02", "CL-必要性-03", "CL-必要性-04",
                                "CL-结论-02", "CL-建议-01", "CL-规模-01", "CL-资金-01", "CL-风险等级-01"]},
    },

    # ------------------------------------------------------------------ 7 推演场景
    "scenario": {
        "scenario_types": ["基准", "变化", "极端"],
        "params": [
            {"name": "分类人数（科研人员 / 研究生等）", "role": "规模链第一驱动量"},
            {"name": "人均建筑面积指标（两档）", "role": "受规范上限约束，可调但须说明依据"},
            {"name": "综合平面利用系数", "role": "使用面积→建筑面积的换算口径"},
            {"name": "装配率 / 绿色建筑星级", "role": "政策要求变更直接改动增量费用"},
            {"name": "单方造价与各分项单价", "role": "造价链驱动量，替换后须重跑派生"},
            {"name": "国拨资金与自筹比例", "role": "资金链驱动量"},
            {"name": "建设工期", "role": "资金年度需求分布驱动量"},
        ],
        "scenario_templates": [
            {"id": "SC-基准", "desc": "按原文全部取值复算，得到三链闭合与否的基线结论", "status": "已执行"},
            {"id": "SC-规模上浮", "desc": "分类人数或人均指标上调，观察地上需求是否超过设计面积与容积率约束", "status": "未执行（无客户输入）"},
            {"id": "SC-标准变更", "desc": "装配率/绿色星级提高，增量费用按政策加计", "status": "未执行（原文已声明未含）"},
            {"id": "SC-极端", "desc": "国拨资金未获批、全额自筹，检验学校财务承载与工期资金峰值", "status": "未执行（无客户输入）"},
        ],
        "notes": ["场景只复制结构，不迁移本项目模拟结果；参数取值一律来自新项目输入"],
        "sources": {"rules": ["R-应建规模", "R-资金筹措构成"]},
    },

    # ------------------------------------------------------------------ 8 任务图 DAG
    "task_dag": {
        "stages": ["归一化", "骨架抽取", "切块", "本体抽取", "推演回放", "质量登记", "脱敏索引", "装配复用", "写作"],
        "nodes": {
            "归一化": ["stage_1_normalize"],
            "骨架抽取": ["stage_2_outline", "legal_coverage_check"],
            "切块": ["stage_3_chunk"],
            "本体抽取": ["validate_extraction", "apply_extraction"],
            "推演回放": ["replay_same_key", "replay_derivation", "judge_select_rules"],
            "质量登记": ["detect_conflicts", "register_gaps", "run_invariants"],
            "脱敏索引": ["desensitize_numerics", "build_node_index", "build_term_index"],
            "装配复用": ["schema_diff", "decide_reuse", "instantiate_project", "run_quality_gates"],
            "写作": ["build_work_package", "gate_check_draft"],
        },
        "ordering_constraints": [
            "骨架抽取必须先于一切内容工作（章节 id 是全图引用锚点，冻结后再改等于全图返工）",
            "推演回放必须先于质量登记的冲突判定",
            "存在未裁决 error 级冲突时不得进入写作阶段",
        ],
        "sources": {"chunks": []},
    },

    # ------------------------------------------------------------------ 9 函数库
    "function": {
        "functions": [
            {"name": "safe_eval", "sig": "(expr, env) -> number", "note": "受控命名空间求值，禁用 builtins"},
            {"name": "num / canon", "sig": "(value) -> float|str", "note": "限定词归一后的数值比较"},
            {"name": "resolve_dep", "sig": "(dep) -> (value, nodes, reason)", "note": "依赖名三级匹配 + 别名 + 冲突感知"},
            {"name": "stage_1_normalize / stage_2_outline / stage_3_chunk", "sig": "(text|md, out) -> artifact"},
            {"name": "validate_extraction / apply_extraction", "sig": "(unit|chunks, extractions) -> graph"},
            {"name": "emit_nodes / emit_rules / emit_evidence / emit_reasoning / emit_index / emit_reuse", "sig": "(root, ...) -> artifact"},
            {"name": "instantiate_project / build_work_package / gate_check_draft", "sig": "(...) -> 装配与写作产物"},
        ],
        "measured": ["22 条规则实际完成重算（12 闭合 / 7 差异 / 3 判定）",
                     "1 条规则因缺口径未解析，5 条因未裁决冲突阻塞"],
        "sources": {"rules": ["R-应建规模", "R-土建工程", "R-投资闭合校核"]},
    },

    # ------------------------------------------------------------------ 10 Skills
    "skill": {
        "skills": [
            {"name": "document-parsing-skill", "role": "docx/PDF → Document IR，保留页码段落表格"},
            {"name": "sentence-segmentation-skill", "role": "稳定 Sentence ID"},
            {"name": "semantic-chunking-skill", "role": "语义边界切块，表格/图注独立成块"},
            {"name": "entity-extraction-skill / entity-resolution-skill", "role": "实体抽取与消歧"},
            {"name": "fact-extraction-skill", "role": "SPO 结构化事实"},
            {"name": "relation-extraction-skill", "role": "十类关系"},
            {"name": "claim-extraction-skill / claim-evidence-binding-skill / claim-validation-skill", "role": "论断与证据绑定、论断校验"},
            {"name": "reasoning-extraction-skill", "role": "公式/规则/多步推导"},
            {"name": "evidence-extraction-skill", "role": "证据分级 E1–E6 与原文定位"},
            {"name": "provenance-binding-skill", "role": "决策→Claim→Reasoning→Fact→Evidence→Sentence→Chunk→Document 反向溯源"},
            {"name": "conflict-detection-skill", "role": "数字/时间/实体/Claim/版本冲突，输出待审"},
            {"name": "extraction-quality-audit-skill", "role": "结构完整性、证据覆盖、关系合法性、跨项目污染、孤立节点"},
            {"name": "ontology-resolution-skill / semantic-graph-compilation-skill", "role": "本体映射与图谱编译"},
            {"name": "knowledge-generalization-skill", "role": "本体/推理模式/Claim 模式沉淀，隔离项目专属事实"},
            {"name": "graph-deductive-writing-skill", "role": "沿推理链推演写作，正文可反向回读"},
            {"name": "feasibility-report-edu-research", "role": "高校科研用房可研领域本体与法定大纲（304 号文）"},
        ],
        "capability_boundary_note": "仅有报告文本 → 只能归纳候选方法（induced）；"
                                    "有代码/配置/执行记录才登记为真实能力（registered）。"
                                    "本包中 rule/function/task_dag 域为 registered（有可执行 Python 与实测结果），"
                                    "其余域为 induced（从报告归纳，待审核）。",
        "sources": {"chunks": []},
    },

    # ------------------------------------------------------------------ 11 报告结构
    "report_structure": {
        "actual_outline": [
            "总论", "学校简介", "项目建设背景及必要性分析", "项目选址及建设条件", "项目建设内容及规模",
            "项目规划设计方案", "节能设计", "环境影响评价", "卫生防疫与劳动安全", "社会稳定风险分析",
            "项目管理及实施进度", "项目招投标方案", "投资估算及资金筹措", "社会效益", "结论与建议", "附件",
        ],
        "legal_outline_2023": [
            "概述", "项目建设背景和必要性", "项目需求分析与产出方案", "项目选址与要素保障", "项目建设方案",
            "项目运营方案", "项目投融资与财务方案", "项目影响效果分析", "项目风险管控方案", "研究结论及建议",
        ],
        "version_note": "本报告 2019 年 8 月编制，采用旧版章节体系；304 号文通用大纲 2023 年 5 月 1 日起施行。"
                        "按现行口径编写时须以 304 号文十章为准，本报告结构仅作「行文之形」参照，不作「结构之准」。",
        "gap_analysis": [
            "未单列「项目运营方案」章（运营内容散落在 11.3 节）",
            "未单列「项目影响效果分析」章（仅 14 章社会效益，无经济影响/资源能源/碳达峰碳中和分析）",
            "未单列「项目风险管控方案」章（仅社会稳定风险独立成章，工程质量与安全风险散落）",
            "「项目投融资与财务方案」仅覆盖投资估算与资金筹措，未含财务分析（盈利能力/融资方案比选/债务清偿/财务可持续性）",
            "未含「要素保障分析」独立小节（水电气热供给条件散落在 4.2.2）",
        ],
        "must_cover_discipline": "标题可变，覆盖不可少；变形只搬动内容的容器，不增减内容本身",
        "sources": {"chunks": [], "outline": True},
    },

    # ------------------------------------------------------------------ 12 报告表单
    "report_form": {
        "fields": [
            {"name": "项目名称", "type": "string", "required": True},
            {"name": "建设单位", "type": "string", "required": True},
            {"name": "建设地点", "type": "string", "required": True},
            {"name": "建设性质", "type": "enum(新建|改扩建|拆除重建)", "required": True},
            {"name": "分类人数（按组织单元×人员类别）", "type": "table", "required": True},
            {"name": "人均建筑面积指标（两档）", "type": "number", "required": True},
            {"name": "公共服务配套用房需求（功能×间数×单间标准）", "type": "table", "required": True},
            {"name": "综合平面利用系数", "type": "number", "required": True},
            {"name": "投资估算明细（分项×数量×单位×单位造价）", "type": "table", "required": True},
            {"name": "基本预备费费率", "type": "number", "required": True},
            {"name": "资金来源与年度需求（国拨/自筹×年度）", "type": "table", "required": True},
            {"name": "装配率 / 绿色建筑星级", "type": "string", "required": True},
            {"name": "建设工期与开竣工时间", "type": "string", "required": True},
            {"name": "用水定额 / 用电指标 / 负荷指标", "type": "table", "required": False},
            {"name": "实验室专项取值（换气次数/通风柜台数/排风量）", "type": "table", "required": True,
             "note": "高校科研用房必问项；本报告缺失，表单须强制填写"},
        ],
        "unknown_handling": "字段缺值一律保持显式未知（TODO/待补充），不填 0、不估值",
        "sources": {"rules": ["R-应建规模"], "gaps": ["G-902"]},
    },

    # ------------------------------------------------------------------ 13 提示词资产
    "prompt": {
        "templates": {
            "extraction": "按 schema 输出 JSON；数值必须带单位与原文可检索的 verbatim；"
                          "同一指标跨章 subject/predicate 必须一致；找不到证据的 Claim 也要抽但 evidence_refs 留空；"
                          "warrant 原文没写就留空，不代拟。",
            "writing_discipline": "正文只写 {{节点名}} 占位符，不出现手打数字；"
                                  "冲突以「待审」呈现；缺值写「待X确认后生成」而不是占位文字；"
                                  "不引入图上没有的新事实。",
            "evidence_grading": "E1 单位内部资料 / E2 规范标准定额 / E3 政策法规与上位规划 / "
                                "E4 公开统计 / E5 第三方委托成果 / E6 专家判断与类推。",
        },
        "dynamic_context": ["项目 meta", "变量字典", "术语表", "冲突待审清单", "缺口清单", "规范在册状态"],
        "sources": {"chunks": []},
    },

    # ------------------------------------------------------------------ 14 质量闸门
    "quality_gate": {
        "gates": [
            {"id": "QG1", "name": "来源可信度", "rule": "每个可复用资产必须能指回原稿或客户确认的来源；"
                                                      "检索结果不得直接入图", "applies_to": "全域"},
            {"id": "QG2", "name": "语义完整性", "rule": "结构完整性、证据覆盖、关系合法性、无孤立节点、无跨项目污染", "applies_to": "graph/*"},
            {"id": "QG3", "name": "可复用性", "rule": "借形不借值：reusable_form 中不得含项目专属数值；"
                                                     "口径与单位必须显式；能确定性复算", "applies_to": "reuse/*"},
        ],
        "blocking_rules": ["存在未裁决 error 级冲突不得进入写作", "关键 Claim 无证据不得标记为已验证",
                           "draft 未过 validated 不得 published"],
        "sources": {"conflicts": ["本项目·总建筑面积", "室外总体工程"]},
    },

    # ------------------------------------------------------------------ 15 复用策略
    "reuse_strategy": {
        "strategies": ["直接复用", "参数化复用", "扩展", "重建", "拒绝"],
        "decision_examples": [
            {"asset": "规模论证链（人均指标法）", "strategy": "参数化复用",
             "reason": "结构稳定、指标受规范约束，换项目只需换分类人数与指标取值"},
            {"asset": "造价链（分项→单位工程→单体/室外→建安→总投资）", "strategy": "参数化复用",
             "reason": "构成口径通用，但单价与费率须按新项目所在地与年份重取"},
            {"asset": "规范清单", "strategy": "重建",
             "reason": "软约束，默认已过期；本报告多处版本并存（照明 2004/2013、节能 DGJ08-107 2012/2015 等），须按现行口径重查"},
            {"asset": "本项目数值（18319/13032/…）", "strategy": "拒绝",
             "reason": "项目专属事实，禁止迁移"},
        ],
        "granularity_rule": "不因单个字段不兼容就判定整个模板失效；按字段与依赖粒度评估并记录原因",
        "sources": {"conflicts": ["建筑照明设计标准", "公共建筑节能设计标准"]},
    },

    # ------------------------------------------------------------------ 16 成本／风险计算方法
    "cost_risk": {
        "cost_methods": [
            {"name": "费用构成归集法", "expr": "总投资 = 建安工程费用 + 工程建设其他费用 + 预备费 + 拆除费用"},
            {"name": "单位造价法", "expr": "分项金额 = 数量 × 单位造价"},
            {"name": "费率法", "expr": "基本预备费 = (建安工程费用 + 工程建设其他费用) × 费率"},
            {"name": "系数法", "expr": "前期费用 = 基数 × 系数（如 勘察费 = 建安费×0.35%、竣工图编制费 = 设计费×8%）"},
            {"name": "造价指标法", "expr": "参照类似工程造价指标（原文列为估算依据，但未给出指标来源与数值）"},
        ],
        "cost_structure": ["建筑安装工程费用 → 单体工程/室外总体工程/抗震支架/绿色二星增量费用",
                           "单体工程 → 土建工程/安装工程", "土建工程 → 桩基/基坑围护/地下结构/地上结构/装配式增加费/室内装饰/外立面及屋面",
                           "安装工程 → 给排水/消防/通风空调/强电/弱电/电梯",
                           "工程建设其他费 → 管理费/咨询费/勘察设计费/招标代理/监理/审图/竣工图/场地准备/市政配套/人防"],
        "risk_factors": [
            {"id": "RK-1", "name": "施工环境污染风险", "phase": "施工期", "level": "较小",
             "note": "风险随施工结束消失，但装修期噪声对师生教学与周边居民影响可能较大"},
            {"id": "RK-2", "name": "交通出行及安全风险", "phase": "施工期", "level": "较小",
             "note": "施工车辆进出与建材占道"},
            {"id": "RK-3", "name": "工程管理及施工安全风险", "phase": "施工期", "level": "概率小/影响较严重",
             "note": "欠薪与工伤易引发群体性事件"},
            {"id": "RK-4", "name": "标准版本失效风险", "phase": "全过程", "level": "中",
             "note": "本报告实测存在 4 组规范多版本并存与 1 组规范名称不一致，是本类报告被打回的高频原因"},
            {"id": "RK-5", "name": "派生值与原文脱节风险", "phase": "编制期", "level": "中",
             "note": "实测投资表 7 处派生差异、规模结论与自身测算不符"},
            {"id": "RK-6", "name": "手续未闭合风险", "phase": "前期", "level": "中",
             "note": "拆除手续在办理中、国拨资金无批复文件"},
            {"id": "RK-7", "name": "实验室专项取值缺失风险", "phase": "设计期", "level": "较高",
             "note": "通风柜台数/排风量/实验室换气次数未给出，评审必问"},
        ],
        "risk_method": "按风险管理四要素（外部环境、内部管理、技术、财务）× 前期/施工/运营 三阶段识别，"
                       "分合法性/合理性/可行性/可控性四维评估，措施后复评等级",
        "sources": {"claims": ["CL-风险-01", "CL-风险-02", "CL-风险-03", "CL-风险等级-01", "CL-风险结论-01"],
                    "rules": ["R-基本预备费", "R-总投资构成"]},
    },
}
