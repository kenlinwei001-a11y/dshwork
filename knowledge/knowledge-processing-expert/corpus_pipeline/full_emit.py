"""补齐 30 文件契约里缺失产物的发射器（meta/provenance/invariants/evidence/reasoning三件套/quality三件套/style两件套/index三件套）。

original.docx(#5)、assets(#8)、embeddings.parquet(#11) 需外部输入（原稿/嵌入模型），此处不生成。
"""
from __future__ import annotations
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from .spec import TEN_RELATIONS

_TERM = re.compile(r'[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{1,}')


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def emit_meta(root: Path, raw_text: str, title: str = "") -> dict:
    """#2 meta.yaml"""
    m = re.search(r'^#\s+(.+)$', raw_text, re.M) or re.search(r'^(.{2,40})$', raw_text, re.M)
    meta = {
        "title": title or (m.group(1).strip() if m else "未命名稿件"),
        "doc_type": "report",
        "data_cutoff": None,
        "lang": "zh",
        "source_sha": _sha(raw_text),
    }
    (root / "meta.yaml").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def emit_provenance(root: Path, graph: dict, chunks: list[dict]) -> list[dict]:
    """#3 provenance.yaml —— 每个对象追溯到来源 chunk"""
    prov = []
    for f in graph.get("facts", []):
        prov.append({"obj_type": "fact", "obj_id": f["id"], "derived_from": [f.get("source")], "stage": "4"})
    for c in graph.get("claims", []):
        prov.append({"obj_type": "claim", "obj_id": c["id"], "derived_from": c.get("evidence", []), "stage": "4"})
    for r in graph.get("rules", []):
        prov.append({"obj_type": "rule", "obj_id": r["id"], "derived_from": r.get("inputs", []), "stage": "4"})
    (root / "provenance.yaml").write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
    return prov


def _infer_kind(value) -> str:
    """从值推断节点类型：数字→quantity，判断词/布尔→judgment，其余→text。"""
    if isinstance(value, bool):
        return "judgment"
    if isinstance(value, (int, float)):
        return "quantity"
    s = str(value)
    if re.match(r'^[-+]?\d[\d,]*(?:\.\d+)?%?$', s):
        return "quantity"
    if s in ("是", "否", "可行", "不可行", "基本可行", "待审", "真", "假", "yes", "no"):
        return "judgment"
    return "text"


def emit_nodes(root: Path, graph: dict) -> dict:
    """#12 graph/nodes.yaml —— 变量节点。

    对齐推演写作侧（instantiate_project）消费契约：每条节点含
    id / subject / kind(quantity|judgment|text) / value / unit / caliber / inheritable。
    facts 的 subject/predicate/value 归一化为变量节点；kind 按值类型推断，可被抽取层覆盖。
    """
    nodes = []
    for f in graph.get("facts", []):
        nodes.append({
            "id": f["id"],
            "subject": f.get("subject", f["id"]),
            "kind": f.get("kind") or _infer_kind(f.get("value")),
            "value": f.get("value"),
            "unit": f.get("unit", ""),
            "caliber": f.get("caliber", ""),
            "inheritable": f.get("inheritable", "yes"),
            "predicate": f.get("predicate", ""),
            "time": f.get("time", ""),
            "source": f.get("source", ""),
        })
    gdir = root / "graph"
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "nodes.yaml").write_text(json.dumps(nodes, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"nodes": len(nodes)}


def emit_rules(root: Path, graph: dict) -> dict:
    """#13 graph/rules.yaml —— 计算/判定规则。

    对齐推演写作侧契约：id / kind(compute|select) / expr / deps / target / label / guard。
    兼容抽取层旧字段（inputs→deps，output→target），缺省补 kind/label/guard。
    """
    rules = []
    for r in graph.get("rules", []):
        rules.append({
            "id": r.get("id", ""),
            "kind": r.get("kind", "compute"),
            "label": r.get("label") or r.get("id", ""),
            "expr": r.get("expr", ""),
            "deps": r.get("deps") or r.get("inputs", []),
            "target": r.get("target") or r.get("output"),
            "guard": r.get("guard", "missing_any_dep => undefined"),
        })
    gdir = root / "graph"
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "rules.yaml").write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"rules": len(rules)}


def emit_invariants(root: Path) -> dict:
    """#16 graph/invariants.yaml —— 不变式"""
    inv = {"invariants": [
        {"id": "INV-1", "expr": "同一 (subject, predicate) 的数值必须一致"},
        {"id": "INV-2", "expr": "relation 的 from/to 必须指向存在节点"},
        {"id": "INV-3", "expr": "claim 的 evidence 引用必须存在"},
        {"id": "INV-4", "expr": "数值冲突只呈现「待审」，不自动裁决"},
    ]}
    (root / "graph" / "invariants.yaml").write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
    return inv


def emit_evidence(root: Path, graph: dict, chunks: list[dict]) -> dict:
    """#18 evidence/evidence.yaml + #19 evidence/excerpts/*.md"""
    chunk_map = {c["id"]: c for c in chunks}
    evidence = list(graph.get("evidence", []))
    # 为每个 fact 自动生成证据记录（source chunk + span）
    for f in graph.get("facts", []):
        if not any(e.get("id") == f"ev-{f['id']}" for e in evidence):
            c = chunk_map.get(f.get("source"))
            span = [0, len(c["text"])] if c else [0, 0]
            evidence.append({"id": f"ev-{f['id']}", "claim": "", "doc": f.get("source"), "span": span, "kind": "fact", "fact": f["id"]})

    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "evidence.yaml").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    exdir = root / "evidence" / "excerpts"
    exdir.mkdir(parents=True, exist_ok=True)
    for e in evidence:
        c = chunk_map.get(e.get("doc"))
        if c:
            (exdir / f"{e['id']}.md").write_text(f"# {e['id']}\n\n来源 chunk: {e.get('doc')}\n\n```\n{c['text']}\n```\n", encoding="utf-8")
    return {"evidence": len(evidence), "excerpts": len(list(exdir.glob("*.md")))}


def emit_reasoning(root: Path, replay: dict, graph: dict, trace: list[dict]) -> dict:
    """#20 derivation.yaml + #21 decisions.yaml + #22 trace.jsonl"""
    # 推导链：按规则生成 nodes（label + narrative_zh），供写作「经测算」句直用；
    # 同时保留回放矛盾（contradictions）供闸门与待审。
    derivation_nodes = []
    for r in graph.get("rules", []):
        label = r.get("label") or r.get("id", "")
        derivation_nodes.append({
            "label": label,
            "rule": r.get("id", ""),
            "status": "computed",
            "chain": [{"step": 1, "rule": r.get("id", ""), "expr": r.get("expr", "")}],
            "narrative_zh": r.get("narrative_zh") or f"经测算，{label}按规则 {r.get('id', '')} 计算。",
        })
    derivation = {
        "nodes": derivation_nodes,
        "replayed": replay.get("replayed", 0),
        "contradictions": replay.get("contradictions", []),
    }
    (root / "reasoning").mkdir(parents=True, exist_ok=True)
    (root / "reasoning" / "derivation.yaml").write_text(json.dumps(derivation, ensure_ascii=False, indent=2), encoding="utf-8")

    decisions = {"decisions": [
        {"id": f"d{i+1}", "subject": c.get("subject"), "decision": "待审", "rationale": f"数值不一致: {c.get('values')}"}
        for i, c in enumerate(replay.get("contradictions", []))
    ]}
    (root / "reasoning" / "decisions.yaml").write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")

    tp = root / "reasoning" / "trace.jsonl"
    with open(tp, "a", encoding="utf-8") as f:
        for ev in trace:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return {"derivation_nodes": len(derivation["nodes"]), "decisions": len(decisions["decisions"])}


def emit_quality_split(root: Path, quality: dict) -> dict:
    """#23 conflicts.yaml + #24 gaps.yaml + #25 gate_report.yaml"""
    (root / "quality" / "conflicts.yaml").write_text(json.dumps(quality.get("conflicts", []), ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "quality" / "gaps.yaml").write_text(json.dumps({"gaps": quality.get("gaps", [])}, ensure_ascii=False, indent=2), encoding="utf-8")
    gate = {"gate": quality.get("gate", "REVIEW"), "blockers": quality.get("conflicts", []), "invariant_ok": quality.get("invariant_ok", False)}
    (root / "quality" / "gate_report.yaml").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    return gate


def emit_style(root: Path, chunks: list[dict], outline: dict) -> dict:
    """#26 style_profile.yaml + #27 section_templates/*.yaml"""
    lens = [len(c["text"]) for c in chunks] or [0]
    profile = {
        # 对齐推演写作侧（orchestrator.assemble_injection）消费的完整风格字段
        "number_format": "千分位、两位小数、单位后置、万元优先",
        "terminology": {},
        "forbidden": ["大约", "左右（除非带明确区间）", "或许"],
        "citation_style": "〔节点ID｜规则ID｜证据ID〕",
        "table_caption": "表N-<标题>",
        "person": "第三人称",
        "avg_chunk_len": sum(lens) // len(lens),
        "chunk_count": len(chunks),
        "lang": "zh",
        "tone": "formal",
    }
    (root / "style").mkdir(parents=True, exist_ok=True)
    (root / "style" / "style_profile.yaml").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    tdir = root / "style" / "section_templates"
    tdir.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(outline.get("sections", [])):
        (tdir / f"{i+1:02d}-{s['title']}.yaml").write_text(json.dumps({"level": s["level"], "title": s["title"], "template": "## " + s["title"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"templates": len(list(tdir.glob("*.yaml")))}


def emit_index(root: Path, graph: dict, chunks: list[dict], skeletons: list[dict]) -> dict:
    """#28 node_index.json + #29 term_index.json + #30 signature.yaml"""
    # 节点倒排：node → 出现的 chunk
    (root / "index").mkdir(parents=True, exist_ok=True)
    node_index = []
    for s, c in zip(skeletons, chunks):
        for nid in re.findall(r'\{\{node:(N-[0-9a-f]+)\}\}', s["text"]):
            node_index.append({"node": nid, "chunk": c["id"], "role": "value"})
    (root / "index" / "node_index.json").write_text(json.dumps(node_index, ensure_ascii=False, indent=2), encoding="utf-8")

    # 术语归一：surface → canonical（低频化/计数）
    all_text = " ".join(c["text"] for c in chunks)
    terms = Counter(_TERM.findall(all_text))
    term_index = [{"surface": t, "canonical": t.lower(), "freq": n} for t, n in terms.most_common(50)]
    (root / "index" / "term_index.json").write_text(json.dumps(term_index, ensure_ascii=False, indent=2), encoding="utf-8")

    # 签名：manifest + graph 的指纹
    sig = {"files": len(list(root.rglob("*"))), "graph_facts": len(graph.get("facts", [])), "sha": _sha(json.dumps(graph, ensure_ascii=False, sort_keys=True))}
    (root / "index" / "signature.yaml").write_text(json.dumps(sig, ensure_ascii=False, indent=2), encoding="utf-8")
    return sig


# --------------------------------------------------------------------------- #
# 16 个可复用资产域（知识通用化沉淀）：写新项目时按域借形，不借值。
# 每域记录「核心资产域 / 装配输入 / 装配方法 / 不一致处理 / 装配输出」，
# reusable_form 由 emit_reuse 用本语料包的 ontology/rules/variables/outline 填充。
# --------------------------------------------------------------------------- #
DOMAIN_SPECS = [
    {"id": "ontology", "core_domain": "本体中心",
     "assembly_input": ["新项目领域", "对象", "属性", "关系", "历史本体版本"],
     "assembly_method": "先匹配历史领域本体；对比类、属性、关系、约束 Schema；复用兼容部分，新增或扩展不兼容部分；建立项目级本体版本",
     "mismatch_handling": "新增概念则增加类或属性；同名异义则创建不同概念或明确语义映射；类型变化则兼容性检查，不直接覆盖旧定义",
     "assembly_output": ["项目本体 Schema", "变更集", "映射表", "版本记录"]},
    {"id": "argument_chain", "core_domain": "论证链",
     "assembly_input": ["报告目标", "论点", "Claim", "前提", "证据", "推理关系"],
     "assembly_method": "复用历史论证模式；解析新输入 Claim；连接前提/证据/推论/结论；检查关键 Claim 支撑",
     "mismatch_handling": "新增 Claim 建节点及关系；缺关系类型则扩展 Schema；不把旧项目结论当新项目结论",
     "assembly_output": ["项目论证图", "Claim 清单", "缺失证据清单", "推理任务"]},
    {"id": "scenario", "core_domain": "推演场景",
     "assembly_input": ["项目目标", "场景类型", "初始条件", "边界条件", "扰动因素"],
     "assembly_method": "匹配历史场景模板；绑定新项目变量；复制结构非旧结果；生成基准/变化/极端情景",
     "mismatch_handling": "新增扰动因素扩展参数；关键参数缺失标待补充或明示假设；不迁移旧模拟输出",
     "assembly_output": ["项目场景集", "参数绑定表", "场景运行配置"]},
    {"id": "variable", "core_domain": "变量定义",
     "assembly_input": ["输入字段", "业务指标", "单位", "类型", "公式", "数据来源"],
     "assembly_method": "字段与变量语义匹配；复用变量定义/单位/公式；建字段映射；校验单位/范围/依赖",
     "mismatch_handling": "新字段分类为新变量/别名/元数据后再定增删；同名不同单位显式转换",
     "assembly_output": ["项目变量字典", "字段映射", "公式依赖图"]},
    {"id": "task_dag", "core_domain": "任务图 DAG",
     "assembly_input": ["项目目标", "任务清单", "资产依赖", "执行条件"],
     "assembly_method": "复用历史任务模板；按项目启用/跳过节点；补解析/验证/推理节点；重算拓扑",
     "mismatch_handling": "新增 Claim 需证据检索则插节点连上下游；循环依赖停止并要求修正",
     "assembly_output": ["项目任务 DAG", "节点参数", "执行顺序和依赖检查"]},
    {"id": "function", "core_domain": "函数库",
     "assembly_input": ["函数定义", "输入输出 Schema", "业务参数", "执行环境"],
     "assembly_method": "按功能/接口匹配；复用验证实现；绑定变量；接口检查与测试；记录版本",
     "mismatch_handling": "新增字段不自动传所有函数；仅接口需要才改接口或加适配器并保留兼容版本",
     "assembly_output": ["函数绑定清单", "输入输出映射", "测试结果"]},
    {"id": "rule", "core_domain": "规则库",
     "assembly_input": ["业务规则", "条件", "阈值", "例外", "适用范围"],
     "assembly_method": "匹配领域/对象/版本；复用通用规则；项目阈值作参数注入；检查规则冲突",
     "mismatch_handling": "新增 Claim 触发证据规则时先判是否本报告类型要求再绑定到任务/校验",
     "assembly_output": ["项目规则集", "参数配置", "冲突报告"]},
    {"id": "invariant", "core_domain": "不变式",
     "assembly_input": ["必须成立条件", "约束表达式", "适用范围"],
     "assembly_method": "复用领域硬约束；绑定对象/变量/单位；执行前验可满足性",
     "mismatch_handling": "仅当新字段改变约束表达式/对象才扩展；不因新输入与硬约束矛盾而改约束迁就",
     "assembly_output": ["项目约束集", "约束绑定", "可满足性检查结果"]},
    {"id": "skill", "core_domain": "Skills／技能库",
     "assembly_input": ["Skill 定义", "输入输出 Schema", "提示词", "工具依赖", "测试集"],
     "assembly_method": "按任务类型检索；校验版本/兼容；注入上下文；经 MCP 调资产；执行测试",
     "mismatch_handling": "缺 Claim 处理能力则加可选字段/升级 Schema 并补逻辑；不静默丢弃未知字段",
     "assembly_output": ["项目 Skill 配置", "输入输出契约", "调用计划", "执行记录"]},
    {"id": "report_structure", "core_domain": "报告结构",
     "assembly_input": ["报告类型", "章节模板", "章节依赖", "内容要求"],
     "assembly_method": "匹配报告类型/目标；复用章节结构；按需增删章节；绑定 Claim/证据/推演到章节",
     "mismatch_handling": "新增 Claim 先判是章节内容/论证单元/独立交付，只有影响结构才建章节",
     "assembly_output": ["项目报告大纲", "章节依赖图", "内容填充映射"]},
    {"id": "report_form", "core_domain": "报告表单",
     "assembly_input": ["用户输入字段", "字段类型", "必填规则", "字段与章节映射"],
     "assembly_method": "比对新旧表单 Schema；复用兼容字段；新增字段补标签/类型/校验/下游映射；留未知字段",
     "mismatch_handling": "新增 Claim 先定结构（文本/数组/对象）再升级表单 Schema",
     "assembly_output": ["项目表单 Schema", "字段映射", "校验规则"]},
    {"id": "prompt", "core_domain": "提示词资产",
     "assembly_input": ["系统提示词", "任务模板", "输入 Schema", "输出 Schema", "项目上下文"],
     "assembly_method": "复用稳定模板；按 Schema 动态生成上下文；动态内容与固定规则分离",
     "mismatch_handling": "新增字段更新上下文构建器；不把字段名简单拼接；明确语义/任务/输出/缺失处理",
     "assembly_output": ["版本化提示词", "动态上下文", "结构化输出契约"]},
    {"id": "quality_gate", "core_domain": "质量闸门",
     "assembly_input": ["质量指标", "校验规则", "验收阈值", "历史缺陷"],
     "assembly_method": "复用通用校验；按报告类型启用规则；查结构/逻辑/证据/数值/引用",
     "mismatch_handling": "新增 Claim 评估是否加覆盖率/证据关联/冲突/未验证声明校验；关键 Claim 不达标阻断",
     "assembly_output": ["项目质量规则", "校验报告", "阻断项与整改项"]},
    {"id": "reuse_strategy", "core_domain": "复用策略",
     "assembly_input": ["资产类型", "领域", "版本", "适用条件", "授权", "时效和验证记录"],
     "assembly_method": "评估语义匹配/版本兼容/来源可信/时效/权限/验证状态；选复用/参数化/扩展/重建/拒绝",
     "mismatch_handling": "不因单字段判定整模板失效；按字段/依赖粒度评估并记录兼容/扩展/拒绝原因",
     "assembly_output": ["复用决策清单", "资产来源", "兼容性报告"]},
    {"id": "entity_relation", "core_domain": "实体与关系模型",
     "assembly_input": ["新项目实体", "实体类型", "属性", "关系", "来源和标识"],
     "assembly_method": "实体匹配历史本体类型；解析消歧；建实例与关系；连事实/Claim/证据",
     "mismatch_handling": "新增 Claim 需加类型/属性及与证据/来源/论证的关系；先扩 Schema 再建实例",
     "assembly_output": ["项目实体图", "关系实例", "实体映射和消歧记录"]},
    {"id": "cost_risk", "core_domain": "成本／风险计算方法",
     "assembly_input": ["成本项", "风险因子", "公式", "参数", "单位", "阈值和历史方法"],
     "assembly_method": "复用计算方法/风险分类/公式；映射数据；更新参数/基准/范围；样本测试",
     "mismatch_handling": "新增 Claim 仅影响成本/风险输入才改模型；纯论点进论证流程不当计算变量",
     "assembly_output": ["项目成本模型", "风险模型", "参数表", "计算与校验结果"]},
]


def emit_reuse(root: Path, graph: dict, outline: dict | None = None) -> dict:
    """reuse/domains.yaml —— 16 个可复用资产域（知识通用化沉淀）。

    描述字段（装配输入/方法/不一致处理/输出）为领域无关模板；
    reusable_form 用本语料包的实际 ontology/rules/variables/outline 填充。
    """
    # 从 graph 提取可复用形态（借形不借值：只给结构/规则/关系，不含项目专属数值）
    entity_types = sorted({f.get("subject", "") for f in graph.get("facts", []) if f.get("subject")})
    variables = {
        "inputs": [{"label": f.get("subject"), "unit": f.get("unit", ""), "kind": _infer_kind(f.get("value"))}
                   for f in graph.get("facts", [])],
        "computed": [{"label": r.get("label") or r.get("id", ""), "formula": r.get("expr", "")}
                     for r in graph.get("rules", [])],
    }
    reusable_form_by_id = {
        "ontology": {"entity_types": entity_types, "relations": list(TEN_RELATIONS)},
        "variable": variables,
        "rule": graph.get("rules", []),
        "entity_relation": graph.get("relations", []),
        "report_structure": outline if outline else {},
        "task_dag": {"stages": ["解析", "抽取", "建图", "回放", "质量", "写作"]},
        "function": {"functions": ["emit_nodes", "emit_rules", "emit_reasoning", "instantiate_project", "build_work_package", "gate_check_draft"]},
        "skill": {"skills": ["document-parsing-skill", "fact-extraction-skill", "semantic-graph-compilation-skill", "graph-deductive-writing-skill", "knowledge-generalization-skill"]},
        "invariant": {"invariants": ["同一 (subject,predicate) 数值一致", "relation from/to 指向存在节点", "claim evidence 引用存在", "数值冲突只待审不裁决", "UNDEFINED 不得填 0/估值"]},
        "scenario": {"scenario_types": ["基准", "变化", "极端"]},
        "argument_chain": {"claim_types": ["judgment", "prediction", "causal", "suggestion", "risk"], "edge_types": ["supports", "contradicts", "depends_on"]},
        "report_form": {"fields": [{"name": f.get("subject"), "type": _infer_kind(f.get("value"))} for f in graph.get("facts", [])]},
        "prompt": {"templates": ["extraction_prompt", "writing_discipline"], "dynamic": ["项目 meta", "变量字典", "术语表"]},
        "quality_gate": {"gates": ["字面数值禁用", "undefined 不得当数用", "must_cover 覆盖", "不变式满足", "冲突待审"]},
        "reuse_strategy": {"strategies": ["直接复用", "参数化复用", "扩展", "重建", "拒绝"]},
        "cost_risk": {"cost_methods": [], "risk_factors": []},
    }
    domains = []
    for spec in DOMAIN_SPECS:
        domains.append({**spec, "reusable_form": reusable_form_by_id.get(spec["id"], {})})
    rdir = root / "reuse"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "domains.yaml").write_text(json.dumps({"domains": domains}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"domains": len(domains)}


# --------------------------------------------------------------------------- #
# reemit：把每个发射器单独暴露为可调用工具（按需重发单产物）
# --------------------------------------------------------------------------- #
def load_corpus(root) -> dict:
    """从语料包读回全部状态，供 reemit_* 使用。"""
    root = Path(root)

    def jl(rel):
        p = root / rel
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l] if p.exists() else []

    def jf(rel):
        p = root / rel
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    chunks = jl("chunks/chunks.jsonl")
    graph = jf("graph/graph.yaml")
    outline = jf("outline.yaml")
    from .ontology import replay as _replay
    rp = _replay(graph)
    conflicts = rp["contradictions"]
    gaps = outline.get("missing", [])
    ev_ids = {e.get("id") for e in graph.get("evidence", [])}
    dangling = [c for c in graph.get("claims", []) for ev in c.get("evidence", []) if ev and ev not in ev_ids]
    gate = "PASS" if not conflicts and not gaps and not dangling else "REVIEW"
    quality = {"conflicts": conflicts, "gaps": gaps, "dangling_evidence": dangling, "invariant_ok": not dangling, "gate": gate}
    raw = (root / "source" / "normalized.md").read_text(encoding="utf-8") if (root / "source" / "normalized.md").exists() else ""
    return {"chunks": chunks, "graph": graph, "outline": outline, "replay": rp, "quality": quality, "raw": raw}


def reemit_meta(root):
    s = load_corpus(root)
    return emit_meta(Path(root), s["raw"])


def reemit_provenance(root):
    s = load_corpus(root)
    return emit_provenance(Path(root), s["graph"], s["chunks"])


def reemit_invariants(root):
    return emit_invariants(Path(root))


def reemit_evidence(root):
    s = load_corpus(root)
    return emit_evidence(Path(root), s["graph"], s["chunks"])


def reemit_reasoning(root):
    s = load_corpus(root)
    return emit_reasoning(Path(root), s["replay"], s["graph"], [{"stage": "5", "event": "reemit", "detail": "replayed"}])


def reemit_quality(root):
    s = load_corpus(root)
    return emit_quality_split(Path(root), s["quality"])


def reemit_style(root):
    s = load_corpus(root)
    return emit_style(Path(root), s["chunks"], s["outline"])


def reemit_index(root):
    s = load_corpus(root)
    p = Path(root)
    skeletons = [json.loads(l) for l in (p / "chunks" / "skeletons.jsonl").read_text(encoding="utf-8").splitlines() if l]
    return emit_index(p, s["graph"], s["chunks"], skeletons)
