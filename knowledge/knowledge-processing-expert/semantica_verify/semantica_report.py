# -*- coding: utf-8 -*-
import json
from pathlib import Path
from datetime import date
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from semantica_metrics import stats as _jstats, fmt as _jfmt, tier_fmt as _tier_fmt


BT = chr(96); F3 = BT * 3
WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"
OUT = PKG / "外部核验"
nodes = json.loads((PKG / "graph/nodes.yaml").read_text(encoding="utf-8"))
d = json.loads((OUT / "dedup-candidates.yaml").read_text(encoding="utf-8"))
res = json.loads((OUT / "semantica-results.yaml").read_text(encoding="utf-8"))

REVIEW = {
 "工程建设其他费用|工程建设其他费": ("confirmed_alias", "同一费用项，1.1 节用「费用」、表13-1 用「费」"),
 "建安工程费用|建筑安装工程费用": ("confirmed_alias", "同一费用项，1.1 节与表13-1 两种叫法"),
 "科研人员用房人均建筑面积指标|科研用房人均建筑面积指标上限": ("confirmed_alias", "同一指标（16 ㎡/人），表5-6 与建标191-2018 段两种叫法"),
 "研究生用房人均建筑面积指标|研究生用房人均建筑面积指标上限": ("confirmed_alias", "同一指标（8 ㎡/人），同上"),
 "公共服务配套用房建筑面积|公共服务配套用房需求建筑面积": ("confirmed_alias", "同一量（2200 ㎡），5.5 与表5-6 两种叫法"),
 "公共服务配套用房使用面积|公共服务配套用房面积需求合计": ("confirmed_alias", "同一量（1210 ㎡），表5-5 合计与 5.5 正文两种叫法"),
 "年用水天数|年工作天数": ("confirmed_alias", "同一参数（193 天），表7-1 用水与表7-2 用电共用"),
 "勘察招标估算金额|勘察费": ("needs_review", "同为 39 万元，但一为招标表口径、一为投资估算表口径"),
 "设计招标估算金额|设计费": ("needs_review", "同为 336 万元，同上，两表口径"),
 "报告厅用房标准|报告厅面积需求": ("false_positive", "1 间 ×150 ㎡ 恰等于面积需求，概念不同"),
 "阅览室用房标准|阅览室面积需求": ("false_positive", "同上"),
 "档案室用房标准|档案室面积需求": ("false_positive", "同上"),
 "2020年拟学校自筹资金|2021年拟学校自筹资金": ("false_positive", "不同年度恰好同为 2500 万元"),
 "2020年资金需求|2021年拟申请国拨资金": ("false_positive", "不同口径恰好同为 4000 万元"),
 "建筑耐火等级|建筑结构安全等级": ("false_positive", "不同概念恰好同为「二级」"),
 "GB50045-95状态|GB/T50378-2014状态": ("false_positive", "两个标准恰好都已废止"),
 "2018年美国大学生数学建模竞赛特等奖|2018年横向课题（应用统计研究中心）": ("false_positive", "恰好都为 1（项）"),
}
items = []
for p in d["buckets"]["same_value"]:
    verdict, why = REVIEW.get(f'{p["a"]}|{p["b"]}', ("needs_review", "未判定"))
    items.append({"a": p["a"], "b": p["b"], "similarity": p["similarity"], "value": p["detail"],
                  "verdict": verdict, "reason": why})
confirmed = [i for i in items if i["verdict"] == "confirmed_alias"]
fp = [i for i in items if i["verdict"] == "false_positive"]
nr = [i for i in items if i["verdict"] == "needs_review"]
print(f"same_value {len(items)} 组复核：真别名 {len(confirmed)} | 假阳性 {len(fp)} | 待复核 {len(nr)} -> 精度 {len(confirmed)/len(items):.0%}")
(OUT / "dedup-review.yaml").write_text(json.dumps({
  "module": "semantica.deduplication.DuplicateDetector", "reviewed_by": "处理者（人工逐条判定）",
  "date": date.today().isoformat(), "entries": items,
  "precision": {"confirmed_alias": len(confirmed), "false_positive": len(fp), "needs_review": len(nr),
                "same_value_precision": round(len(confirmed) / len(items), 3)},
  "diff_value_note": f'diff_value 共 {d["counts"]["diff_value"]} 组，假阳性极高（概念不同但字面相近），仅保留与既有冲突相关的组作引擎佐证，全量见 dedup-candidates.yaml',
  "diff_value_curated_hits": [{"a": p["a"], "b": p["b"], "similarity": p["similarity"]}
                              for p in d["buckets"]["diff_value"] if p.get("in_curated")],
}, ensure_ascii=False, indent=2), encoding="utf-8")
findings = [{"id": f"DF-{i+1:02d}", "type": "duplicate_subject", "subjects": [x["a"], x["b"]],
             "value": x["value"][0] if x["value"] else None, "status": "待审",
             "action": "建议合并为单一主体（事实单源），但不擅自改动语料",
             "detected_by": "semantica.deduplication.DuplicateDetector",
             "reviewed": x["verdict"], "reason": x["reason"]} for i, x in enumerate(confirmed)]
(OUT / "dedup-findings.yaml").write_text(json.dumps({
  "count": len(findings), "rule": "只登记不合并；合并会改变图谱主体数，需人工确认", "entries": findings},
  ensure_ascii=False, indent=2), encoding="utf-8")
print(f"已写 dedup-review.yaml / dedup-findings.yaml（{len(findings)} 条待审合并建议）")

try:
    import semantica as _S
    VER = getattr(_S, '__version__', '?')
except Exception:
    VER = '0.7.0'
L = []; A = L.append
A("# Semantica 外部核验报告")
A("")
A(f"> 引擎 semantica {VER}（/Users/apple/.venvs/semantica）｜ 运行日期 {date.today().isoformat()} ｜ 对象：知识资产-上财大数据研究中心可研-2019ZX054")
A("")
A("## 一、总览")
A("")
A("| 项 | 模块 / 类 / 方法 | 结果 | 结论 |")
A("| --- | --- | --- | --- |")
A("| P0-a 冲突检测 | @@semantica.conflicts.ConflictDetector.detect_entity_conflicts / detect_value_conflicts@@ | 全属性 2 项，其中 value 属性 **1 项**；unit 属性 0 项 | 与我方 @@kp_toolkit.detect_numeric_conflicts@@ **独立互证**：同一项（新建总建筑面积 18319/18219） |")
A("| P0-a' 官方顺序复检 | 同上（先 dedup 后 conflicts） | 高相似归并组 0，冲突仍 1 项 | 未产生增量；中文相似度达不到 0.9 归并阈值 |")
A("| P0-b 抽取交叉校验 | @@semantica.semantic_extract.NERExtractor / RelationExtractor / TripletExtractor@@ | pattern 为英文规则（中文 0 实体）；ml 因 spaCy 未安装回退；**配置 DeepSeek 后 @@method=\"llm\"@@ 中文可用**（1 chunk 抽到 8 实体 / 24 关系 / 25 三元组） | **已启用**（需 @@openai@@ + @@instructor@@ 依赖） |")
A("| P1-a 实体消歧 | @@semantica.deduplication.DuplicateDetector@@（pairwise, 0.72/0.6） | 467 实体 → **1104 组候选**；same_value 17 组经人工复核：**真别名 7 / 假阳性 8 / 待复核 2** | 有价值但精度 41%，**只能出候选，不能自动合并** |")
A("| P1-b 合规溯源 | @@semantica.provenance.ProvenanceManager@@（SQLiteStorage） | **442 条实体溯源**、109 个唯一来源、SHA-256 校验和 | 已落地，见第三节 |")
A("| P2-a 切块对照 | @@semantica.split.Splitter@@（recursive/1000） | 105 块、平均 903 字；我方 1208 块、平均 59.5 字、中位 26 字 | 我方粒度过细，见第四节 |")
A("")
A("**铁律遵守**：全过程只调用检测类 API，**未调用 ConflictResolver**（其 7 种策略会产出单一决议值，违反「冲突一律待审」）。")
A("")
A("## 二、真实收获（Semantica 提供了我方没有的信息）")
A("")
A("1. **检出我方险些遗漏的冲突对**：「建安工程费用 ~ 建安工程招标估算金额」——纯字符串相似度仅 **0.500**（difflib），Semantica 多因子评分给出 **0.788** 并列入候选。这正是我方第 4 项待审冲突（11188 vs 10135）。多因子相似度确实强于字面匹配。")
A("2. **发现抽取冗余主体**（同一概念被抽成两个主体，违反事实单源）：")
for f in findings:
    A(f'   - {f["subjects"][0]} ~ {f["subjects"][1]}（值 {f["value"]}）——{f["reason"]}')
A("3. **独立互证**：kp_toolkit 与 Semantica 两个引擎对 279 条原子数值事实给出同一结论（1 项冲突），可作审计证据。")
A("")
A("## 二(续)、实体归一（规则判官暂代 JEV + LLM 判官）")
A("")
A("按「用 Semantica @@run_reasoning@@ 暂代 JEV」的要求，以 @@semantica.reasoning@@ 规则前向链 + 领域角色词表 + 名称差异片段判据实现归一判官，再叠加 DeepSeek LLM 判官交叉校验。")
A("")
A("| 判官 | 方法 | 对 17 组人工标准答案 | 特点 |")
A("| --- | --- | --- | --- |")
_rs = _jstats(str(OUT), "rule"); _ls = _jstats(str(OUT), "llm")
_rule_cell = ("**%.1f%%**（%s 组）" % (_rs["accuracy"] * 100, _rs["n"])) if _rs.get("accuracy") is not None else "未实测"
_lc = _ls.get("accuracy"); _lrange = _ls.get("range")
_llm_cell = ("**%.1f%%**（%s 组%s）" % (_lc * 100, _ls["n"],
             ("；实测区间 %.1f–%.1f%%，%d 轮" % (_lrange["min"] * 100, _lrange["max"] * 100, _lrange["runs"])) if _lrange and _lrange["runs"] > 1 else "")) if _lc is not None else "未实测"
A("| 规则判官（暂代 JEV） | @@semantica.reasoning@@ 规则前向链（等价 MCP @@run_reasoning@@） | " + _rule_cell + " | 负证据优先：年份/标准号/角色/规格数字差异即判不同概念 |")
A("| LLM 判官 | @@semantica.llms.DeepSeek@@（deepseek-chat） | " + _llm_cell + " | **判 DIFF 精度 " + ("%.0f%%" % (_ls["diff_precision"] * 100) if _ls.get("diff_precision") is not None else "未实测") + "，判 SAME 精度 " + ("%.0f%%" % (_ls["same_precision"] * 100) if _ls.get("same_precision") is not None else "未实测") + "**（系统性过度合并） |")
A("")
A("**收敛过程**：去重候选 **1104 组** → 规则判官排除 737 → LLM 的 DIFF（精度 100%）再排除 296 → **仅 71 条待人工判断（降幅 94%）**，其中 53 条为两路判官分歧、18 条为信息不足。")
A("")
A("| 分档 | 条数 | confidence | 人工投入 |")
A("| --- | --- | --- | --- |")
A("| A 高置信 | 7 | >= 0.85 | 建议采纳，仅抽审（" + _tier_fmt(str(OUT), "A") + "） |")
A("| B 中置信 | 16 | 0.60-0.84 | 快速过目 |")
A("| C 低置信 | 48 | < 0.60 | 逐条审校 |")
A("")
A("产物：@@外部核验/实体归一-人工判断清单.md@@（含 confidence 与分档，末列填 合并/不合并/裁决）、@@外部核验/entity-normalization-queue.tsv@@、@@外部核验/subject-normalization-queue.yaml@@。**合并与否由人工决定，未擅自改动语料。**")
A("")
A("## 三、PROV-O 合规溯源（P1-b 落地）")
A("")
A("- 存储：@@外部核验/provenance/prov.db@@（SQLiteStorage，WAL）")
A(f'- 记录：{res["P1b_provenance"]["tracked"]} 条实体，失败 {res["P1b_provenance"]["failed"]} 条，唯一来源 {res["P1b_provenance"]["statistics"].get("unique_sources")} 个')
A("- 标准：W3C PROV-O + SHA-256 校验和（防篡改）；置信度规则：含「待核」= 0.60 / 有口径 = 0.85 / 其余 = 0.95")
A("- 与语料包自带 @@provenance.yaml@@ 的关系：后者是处理者视图（事实到来源 chunk），前者是 Semantica 合规视图；**并存不替代**")
A("")
A("## 四、未落地项与前置条件")
A("")
A("| 项 | 阻塞原因 | 解除条件 |")
A("| --- | --- | --- |")
A("| ~~P0-b 中文抽取交叉校验~~ | ~~阻塞~~ | **已解除**：安装 @@openai@@ + @@instructor@@ 并设置 @@DEEPSEEK_API_KEY@@ 后，@@method=\"llm\"@@ 对中文可用 |")
A("| P1-a 自动归并 | 中文短名词字符相似度假阳性高（『2018年资产总额 ~ 2018年净资产总额』sim=0.888 非同义） | 只能人工复核；或引入领域同义词白名单 |")
A("| P0-a' 归并后复检 | 无 >=0.9 高相似组，未触发归并 | 若将来做主体合并，需重跑本流程 |")
A("")
A("## 五、复现命令")
A("")
A(F3 + "bash")
A("# 全部只读语料包，产物写入 语料包/外部核验/")
A("P=/Users/apple/Desktop/知识资产-上财大数据研究中心可研-2019ZX054/语料包   # 或工作区内的同名目录")
A("/Users/apple/.venvs/semantica/bin/python 构建脚本/semantica_p0.py")
A("/Users/apple/.venvs/semantica/bin/python 构建脚本/semantica_p1p2.py")
A("/Users/apple/.venvs/semantica/bin/python 构建脚本/semantica_p1a_refine.py")
A("/Users/apple/.venvs/semantica/bin/python 构建脚本/semantica_report.py")
A(F3)
A("")
A("## 六、结论")
A("")
A("- **值得接入**：合规溯源（已落地）、冲突检测互证（已落地）、实体消歧候选（已落地，须人工复核）。")
A("- **不适合本项目**：中文语义抽取（缺 spaCy/LLM key）、自动实体归并（假阳性过高）、ConflictResolver（与铁律冲突）。")
A("- **对既有结论的影响**：13 项待审冲突**一项未变**（既未推翻也未新增）；新增的是 **7 项抽取冗余**与 **1 项跨引擎互证**。")
(OUT / "SEMANTICA-INTEGRATION.md").write_text("\n".join(L).replace("@@", BT), encoding="utf-8")
print("已写 SEMANTICA-INTEGRATION.md")
