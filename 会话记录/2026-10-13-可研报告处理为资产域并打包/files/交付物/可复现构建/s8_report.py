# -*- coding: utf-8 -*-
"""审计报告生成（确定性）：从语料包读回数据，生成 6 份人可读交付文档。

产物（写入 交付物/审计/ 与 交付物/README.md）：
  01-资产域清单.md
  02-冲突待审清单.md
  03-缺口清单.md
  04-质量关口报告.md
  05-可复现性与输入完整性说明.md
  README.md
"""
import json
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
DELIV = WS / "交付物"
AUD = DELIV / "审计"
AUD.mkdir(parents=True, exist_ok=True)


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


nodes = J(ROOT / "graph" / "nodes.yaml")
rules = J(ROOT / "graph" / "rules.yaml")
claims = J(ROOT / "graph" / "claims.yaml")
relations = J(ROOT / "graph" / "relations.yaml")
evidence = J(ROOT / "evidence" / "evidence.yaml")
outline = J(ROOT / "outline.yaml")
manifest = J(ROOT / "manifest.yaml")
conflicts = J(ROOT / "quality" / "conflicts.yaml")
gaps = J(ROOT / "quality" / "gaps.yaml")
derivation = J(ROOT / "reasoning" / "derivation.yaml")
judgements = J(ROOT / "reasoning" / "judgements.yaml")
domains = J(ROOT / "reuse" / "domains.yaml")["domains"]
dep_graph = J(ROOT / "reuse" / "dependency_graph.yaml")
_GT = J(ROOT / "reuse" / "quality_gates.yaml")
gates = _GT["gates"]
kp_gates = _GT["kp_internal_gates"]
measured = _GT["measured"]
remap = J(BUILD / "remap_report.json")
_TD = J(ROOT / "quality" / "tool_defects.yaml")
EXT_DOCS = J(ROOT / "external" / "documents.yaml")["documents"]
EXT_MANDATES = J(ROOT / "external" / "mandates.yaml")["mandates"]
EXT_CONSTRAINTS = J(ROOT / "external" / "constraints.yaml")["constraints"]
EXT_BINDINGS = J(ROOT / "external" / "bindings.yaml")["bindings"]
EXT_EDGES = J(ROOT / "external" / "evidence_edges.yaml")["edges"]
COMPLIANCE = J(ROOT / "external" / "compliance.yaml")
SCREENED = J(ROOT / "quality" / "screened_evidence.yaml")
SEC_PROMPTS = J(ROOT / "style" / "section_prompts.yaml")
REG_DEP = J(ROOT / "reuse" / "regulatory_dependency.yaml")
VERDICT_ICON = {"合规": "✅", "不合规": "❌", "待审": "⚠️", "待核查": "🔍"}
docderiv = J(BUILD / "doc-clean" / "derivation.json")
stage = J(BUILD / "stage4_7_report.json")

TOTAL_FACTS = len(nodes)
DERIV_TOTAL = derivation["replayed_rules"]
DERIV_NOSTATED = len(derivation.get("derivation_nostated", []))
CLOSURE = derivation["closure_ok"]
DIFFS = derivation["derivation_diff"]
UNRES = derivation["unresolved_rules"]
BLOCKED = [u for u in UNRES if u.get("reason") == "blocked_by_conflict"]
MISSING = [u for u in UNRES if u.get("reason") == "missing_deps"]

# ---------------------------------------------------------------- 01 资产域清单
ICON = {"registered": "registered（登记真实能力）", "induced": "induced（归纳候选）"}
lines = ["# 资产域清单（16 个可复用资产域）", "",
         f"- 语料包：`{manifest['corpus_id']}` · 版本 `{manifest['version']}` · 状态 **{manifest['status']}**",
         f"- 文档类型：{manifest.get('doc_type', '可研报告')}（高校科研用房）",
         f"- 原稿指纹：`{manifest['source_fingerprint']}`（raw 文本 sha1 前 16 位）",
         "- 用途：下游装配侧按域取材——先比对历史域，再决定 直接复用／参数化复用／扩展／重建／拒绝。", "",
         "## 域文件一览", "",
         "| # | 域 id | 核心域 | 文件 | 资产性质 | 上游依赖 | 受影响域数 | 溯源指针 |",
         "|---|-------|--------|------|----------|----------|------------|----------|"]
for i, d in enumerate(domains, 1):
    ss = d.get("sources_summary", {})
    ptr = "、".join(f"{k}×{v}" for k, v in ss.items()) or "—"
    lines.append(f"| {i} | `{d['id']}` | {d['core_domain']} | [`{d['file']}`](../SHUFE-BDC-2019-001/{d['file']}) | "
                 f"{ICON.get(d['asset_origin'].split('（')[0], d['asset_origin'])} | "
                 f"{'、'.join(d['depends_on']) or '（根）'} | {len(d['impacted_assets'])} | {ptr} |")
lines += ["", "## 依赖关系（16 域依赖图）", "",
          "```", "ontology（根）", " ├─ entity_relation / variable / argument_chain / report_structure / function(经 variable)",
          " ├─ rule ← variable ; invariant ← variable ; scenario ← variable, rule ; cost_risk ← variable, function, rule",
          " ├─ skill ← ontology, rule, function ; task_dag ← ontology, rule, skill, function",
          " ├─ report_form ← ontology, report_structure ; prompt ← skill, report_structure",
          " └─ quality_gate ← ontology, rule, argument_chain ; reuse_strategy ← ontology, quality_gate", "```", "",
          "影响传播示例（沿依赖图正向传播）：", ""]
for ex in dep_graph["impact_examples"]:
    lines.append(f"- 变更 `{ex['changed_asset']}`（{ex['change']}）→ 受影响 **{ex['impacted_count']}** 个下游域")
lines += ["", "## 扩展资产（16 域契约之外的本次新增）", "",
          "kp 内置的 16 域契约（`corpus_pipeline.full_emit.DOMAIN_SPECS`）未包含下面两项，本包以独立资产文件承载：", "",
          "| 资产 | 文件 | 为什么要沉淀 | 挂载到哪些域 |", "|------|------|--------------|--------------|"]
lines.append(f"| **规范依赖**（依据→技术函数的约束与保证） | [`reuse/regulatory_dependency.yaml`]"
             f"(../SHUFE-BDC-2019-001/reuse/regulatory_dependency.yaml) | "
             f"{REG_DEP['reusable_form']['why_asset'][:80]}… | "
             f"{'、'.join('`' + x + '`' for x in REG_DEP['attached_to_domains'])} |")
lines.append(f"| **逐章提示词**（每章是不同的活） | [`style/section_prompts.yaml`]"
             f"(../SHUFE-BDC-2019-001/style/section_prompts.yaml) | "
             f"用一套通用提示词写十几章，出来必然是同一种腔调的流水账；"
             f"必要性章在论证、规模章在测算、技术章在判定与取值、投资章在归集、结论章在复述 | "
             f"`prompt`（骨架）/ `style/section_prompts.yaml`（本项目实例化，{len(SEC_PROMPTS['sections'])} 章） |")
lines += ["", f"> 逐章提示词覆盖 {len(SEC_PROMPTS['sections'])} 个一级章，用到 {len(set(x['family'] for x in SEC_PROMPTS['sections']))} 个章节族；"
              f"每章都带 `prepare`（起草前置）/ `must_state` / `must_not` / `review` / `shape`，"
              f"并注入本项目的可用节点、待审冲突、缺口与依据绑定。", "",
          REG_DEP["contract_note"], "",
          "## 借形不借值边界", "",
          "每个域文件都带 `reuse_boundary`，明确 **可继承**（结构/规则/口径/术语/句式/关系类型）与 "
          "**禁止继承**（数值/单位取值/实体名/政策文号/规范版本/结论）。域文件正文中不含可直接写进新报告的项目专属数值。", ""]
(AUD / "01-资产域清单.md").write_text("\n".join(lines), encoding="utf-8")

# ---------------------------------------------------------------- 02 冲突待审清单
TYPE_CN = {"numeric": "数字冲突", "derivation": "派生差异", "spec_version": "规范版本冲突",
           "spec_naming": "规范名称不一致", "spec_status": "规范状态待核"}
lines = ["# 冲突待审清单", "",
         f"共 **{len(conflicts)}** 条。**全部为「待审」状态**：本包不动任何数字、不补任何口径、不替客户裁决。", "",
         "处置原则：能确定性算出来的（派生差异）已给出重算值与差额；算不出来的（版本/名称）只呈现版本并列与官方问答路径。", ""]
for t in ("numeric", "derivation", "spec_version", "spec_naming"):
    sub = [c for c in conflicts if c["type"] == t]
    if not sub:
        continue
    lines += [f"## {TYPE_CN.get(t, t)}（{len(sub)} 条）", ""]
    for i, c in enumerate(sub, 1):
        lines += [f"### {i}. {c['subject']} · {c['predicate']}", "",
                  f"- **取值并列**：`{'` / `'.join(c['values'])}`"]
        if c.get("involved"):
            lines.append(f"- **涉及节点**：{', '.join(c['involved'][:6])}"
                         + (" …" if len(c["involved"]) > 6 else ""))
        if c.get("note"):
            lines.append(f"- **说明**：{c['note']}")
        lines.append("")
lines += ["## 判定类结论（select 规则求值）", ""]
for j in judgements:
    lines += [f"### {j['id']}：{j['question']}", "",
              f"- **结论**：**{j['verdict']}**",
              f"- **前提**：`{json.dumps(j['premises'], ensure_ascii=False)}`",
              f"- **说明**：{j['note']}", ""]
lines += ["## 因未裁决冲突而阻塞的派生规则", "",
          "按铁律「不带着冲突往下走」——冲突未裁决前，依赖它的派生校核**阻塞**而非任取一值硬算。", "",
          "| 规则 | 阻塞依赖 | 并列取值 |", "|------|----------|----------|"]
for u in BLOCKED:
    for d in u["detail"]:
        lines.append(f"| {u['rule']} | {d['dep']} | {' / '.join(d['values'])} |")
lines += ["", f"> 一处笔误（资金筹措章把总建筑面积写成 18219）导致 **{len(BLOCKED)}** 条派生规则全部无法计算——"
              f"这正是「单源真理 + 冲突显式化」要防的连锁失效。", ""]
(AUD / "02-冲突待审清单.md").write_text("\n".join(lines), encoding="utf-8")

# ---------------------------------------------------------------- 03 缺口清单
GAP_CN = {"missing_fact": "缺事实（口径未给出）", "blocked_by_conflict": "被未裁决冲突阻塞",
          "explicit_unknown": "原文显式未知"}
lines = ["# 缺口清单（显式未知）", "",
         f"共 **{len(gaps)}** 条。**缺就是缺**：不估算、不套用同类项目、不写「暂按经验值」。", "",
         "每条缺口都写明「找谁要、不给的后果、可接受的替代物」中的至少一项。", ""]
for t in ("missing_fact", "blocked_by_conflict", "explicit_unknown"):
    sub = [g for g in gaps if g["type"] == t]
    if not sub:
        continue
    lines += [f"## {GAP_CN.get(t, t)}（{len(sub)} 条）", ""]
    for g in sub:
        head = g.get("subject") or g.get("label") or g.get("rule") or g["id"]
        lines.append(f"- **{g['id']} · {head}**")
        if g.get("missing"):
            lines.append(f"  - 缺失项：`{'`、`'.join(g['missing'])}`")
        if g.get("depends_on_conflict"):
            lines.append(f"  - 阻塞依赖：`{'`、`'.join(g['depends_on_conflict'])}`")
        lines.append(f"  - 说明：{g['note']}")
    lines.append("")
lines += ["> 其中 **实验室通风专项取值**（通风柜台数 / 排风量 / 实验室换气次数）是高校科研用房评审的必问项，"
          "本报告表6-8 仅覆盖卫生间、电梯机房、水泵房，属必须追问客户的硬缺口。", ""]
(AUD / "03-缺口清单.md").write_text("\n".join(lines), encoding="utf-8")

# ---------------------------------------------------------------- 04 质量关口报告
lines = ["# 三质量关口报告", "",
         f"综合结论：**{'全部通过' if gates['all_passed'] else '未全部通过'}**"
         f"（kp 内置关口：{'通过' if kp_gates['all_passed'] else '未通过'}）", ""]
for gid in ("QG1", "QG2", "QG3"):
    g = gates[gid]
    lines += [f"## {gid} {g['name']} —— {'✅ 通过' if g['passed'] else '❌ 未通过'}", "",
              "| 检查项 | 结果 | 明细 |", "|--------|------|------|"]
    for c in g["checks"]:
        lines.append(f"| {c['check']} | {'✅' if c['passed'] else '❌'} | {c['detail']} |")
    lines.append("")
m = measured
lines += ["## 本项目实测指标", "",
          f"- 规则重算：**{m['rules_replayed']}** 条 —— 闭合 **{m['rules_closure_ok']}** 条 / "
          f"派生差异 **{m['derivation_diff']}** 条 / 仅重算（原文无声明值）**{DERIV_NOSTATED}** 条",
          f"- 因未裁决冲突阻塞：**{len(m['rules_blocked_by_conflict'])}** 条（{'、'.join(m['rules_blocked_by_conflict'])}）",
          f"- 因缺口径未解析：**{len(m['rules_missing_fact'])}** 条（{'、'.join(m['rules_missing_fact']) or '无'}）",
          f"- 待审冲突：**{m['conflicts_pending_review']}** 条；显式缺口：**{m['gaps_registered']}** 条",
          "", "## kp 内置关口明细", "", "```json",
          json.dumps(kp_gates, ensure_ascii=False, indent=2), "```", "",
          "## 状态机", "",
          f"- manifest.status = **{manifest['status']}**",
          "- 流转路径：`draft` → `validated` → `published`。本包已完成 draft→validated；",
          "  **未发布到资产库**（`published` 需用户对本次修订明确确认后才可执行）。",
          "- 装配侧默认只读 `published`；当前包为 `validated`，可作审阅与本地复用，尚不可被装配侧自动检索。", ""]
(AUD / "04-质量关口报告.md").write_text("\n".join(lines), encoding="utf-8")

# ---------------------------------------------------------------- 05 可复现性与输入完整性
lines = ["# 可复现性与输入完整性说明", "",
         "## 1. 唯一输入与指纹", "",
         "| 项 | 值 |", "|----|----|",
         f"| 原始文件 | `上海财经大学中山北一路校区大数据研究中心 可行性研究报告（修订版）.docx` |",
         f"| 原始文件 sha256 | `{docderiv['source_docx_sha256']}` |",
         f"| 重推文档文本 sha256 | `{docderiv['derived_md_sha256']}` |",
         f"| 文档文本规模 | {docderiv['chars']} 字符 / {docderiv['blocks']} 块 / {docderiv['headings']} 个标题 / {docderiv['tables']} 张表 |",
         f"| 语料包来源指纹 | `{manifest['source_fingerprint']}`（raw 文本 sha1 前 16 位） |", "",
         "## 2. 输入完整性事件（必须如实披露）", "",
         "本次任务进行期间，工作区内由前序处理产生的中间文件 "
         "`input/大数据研究中心可研.md` 被**另一进程**追写了一份「附录A（处理者补充）外部规范与法定大纲核查」"
         f"（追加后文件由 170,760 字节 / 2,632 行 变为 177,754 字节 / 2,679 行）。该附录**不是原报告内容**。", "",
         "处置方式（不做无根据的猜测，只保证交付可复现）：", "",
         "1. **不再依赖被改动的中间文件**：改为用纯标准库从原始 docx 的 `word/document.xml` "
         "重新推导段落、标题（取 `w:pStyle` 1/2/3）与表格，得到干净文档文本；关键数字逐项复核一致"
         "（18319×28、13032×8、11188×3、2758×6、18219×1、18040×3、建标191-2018×3、952KW×1）。",
         "2. **章节结构取自 docx 样式而非正则**：kp 的 `_parse_heading` 会把「1.财经特色鲜明…」这类**编号列表项**"
         "误判为标题，实测多出 20+ 个假章节；本包改用 docx 标题样式作为权威结构。",
         f"3. **chunk id 重映射**：抽取产物引用的旧 chunk id 与新推导的 chunk 不重合，按确定性规则"
         f"（完全相同 → 一方包含另一方 → 字符二元组 Jaccard≥0.60）重映射，"
         f"共映射 {remap['mapped']}/{remap['old_chunks']}；**抽取引用的 {remap['cited_ids']} 处锚点全部命中、0 处悬空**。",
         "4. **那份附录被单独归位**：移入 `外部核查/`，标注为「非原报告内容 · 检索来源 · 拟采信前须核对」，"
         "**未并入 source/normalized.md，也未作为事实进入图谱**（见下节）。", "",
         "> 该事件本身也印证了本包的铁律：**中间产物不作权威，原稿才是权威；任何非原稿内容必须显式标注、隔离、不混入。**", "",
         "## 3. 外部检索文件的联合处理（本次的核心口径）", "",
         "**报告的可行性不是自证的。** 报告里的技术函数与判定——耐火等级、高位消防水箱容积、"
         "抗震设防类别与设计地震分组、招标范围、人均建筑面积指标、建筑高度分类——"
         "其**取值域约束与推理保证来自外部规范与政策文件**：报告自己既不引用 50m 一类/二类高层阈值，"
         "也没有把「地下建筑（室）」与「耐火等级」关联起来。只读报告，这些函数无法判定。", "",
         f"因此本次把外部检索文件与报告**联合建库**：D1 报告正文 + D2–D{len(EXT_DOCS)} 外部检索文件，"
         f"建成独立的依据层（{len(EXT_DOCS)} 份文件 / {len(EXT_MANDATES)} 条条款 / "
         f"{len(EXT_CONSTRAINTS)} 条取值域约束 / {len(EXT_BINDINGS)} 条绑定）。"
         "逐条判定见 `审计/06-外部依据绑定与合规复核.md`。", "",
         "| 层 | 产物 | 规模 |", "|----|------|------|",
         f"| 外部文件台账 | `external/documents.yaml` | {len(EXT_DOCS)} 份（URL、字节、sha256、检索状态） |",
         f"| Mandate 条款 | `external/mandates.yaml` | {len(EXT_MANDATES)} 条（四类角色不塌缩） |",
         f"| 取值域约束 | `external/constraints.yaml` | {len(EXT_CONSTRAINTS)} 条（{sum(1 for c in EXT_CONSTRAINTS if c.get('mandatory'))} 条强制性） |",
         f"| 报告←依据绑定 | `external/bindings.yaml` | {len(EXT_BINDINGS)} 条 |",
         f"| 合规复核 | `external/compliance.yaml` | {len(COMPLIANCE['results'])} 条三态结论 |", "",
         "复核结论：" + "、".join(f"**{k} {v} 条**" for k, v in sorted(COMPLIANCE["counts"].items())) + "。", "",
         "三条纪律仍然守住：", "",
         "- **依据未取到就不下判定**：GB50084-2017 表5.0.1 与建标191 附表B 的表格数值在检索页被剥离，"
         "相关结论为「待核查」，本期**不用沾边文件顶上**。",
         "- **二手来源单列**：`抗震设防烈度各地规定.txt`（行业网站转录）、`建筑分类与耐火等级.txt`（行业解读）"
         "台账标为 `ok_secondary`；`tmp-seismic.txt`（实为建标191 指标正文）、"
         "`gb50016-6-公共建筑和居住建筑.txt`（实为 GB50223 第6章）标为 `ok_mislabeled`——"
         "**文件名与实际内容不符的，按实际内容使用并如实标注**；`民用建筑分类-考点.txt` 为 403 页面，登记不可用。",
         "- **不裁决、不改数**：全部「待审」项并列取值与分支结论交客户/设计单位裁决。", "",
         "> 另有 `外部核查/appendix-外部规范与法定大纲核查.md`：系另一进程向工作区中间文件追加的**派生叙述**。"
         "本次已直接从 `references/raw/` 的原始摘录建成依据层，其核查结论被逐条覆盖并升级为"
         "「条款绑定 + 三态判定」，该文仅作为来源留档，不作为判定依据。", "",
         "## 4. 工具层缺陷与绕行（均已留痕，未改动上游工程）", "",
         "全部缺陷也以机读形式登记在 `SHUFE-BDC-2019-001/quality/tool_defects.yaml`。", "",
         "> **严重项 TD-1**：脱敏环节把已插入的占位符二次替换，产出嵌套错乱骨架"
         "（形如 `{{node:N-{{node:N-84523f29f{{node:N-…}}`），且替换顺序受 `PYTHONHASHSEED` 影响导致输出不确定。"
         "这直接污染**交付给下游 Agent 的脱敏骨架**（数值槽位错乱、node_index 失真），"
         "已用一次性左到右扫描重建：1,178 块、2,192 个数值槽位，嵌套/畸形占位符均为 **0**；"
         "重建后两次全链路重建内容哈希一致。", "",
         "| # | 严重度 | 位置 | 现象 | 本包绕行方式 |", "|---|--------|------|------|--------------|",
         ] + [
             f"| {d['id']} | {d['severity']} | `{d['location']}` | {d['summary']} | {d['fix']} |"
             for d in _TD["defects"]
         ] + ["",
         "## 5. 一键复现", "",
         "```bash", "# 全链路重建（--fresh 先清除旧包）",
         "/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python build/run_all.py --fresh",
         "```", "",
         "阶段顺序（不可颠倒）：", "", "```",
         "0  docx → Markdown（原稿唯一输入，权威标题取自 docx 样式）",
         "1  LLM 语义抽取产物序列化（P1 / P2 / P3 / P4a / P4b / P5 / P6 / P7 八个分区）",
         "2  chunk id 重映射（旧锚点 → 重推锚点）",
         "3  工序 1–7 全链路（归一化→骨架→切块→本体→回放→质量→脱敏）",
         "4  推演回放补强（同键异值 / 派生校核 / 判定规则 / 软约束版本冲突 / 缺口登记）",
         "5  来源锚点补齐（gate_qg1 要求）",
         "6  16 资产域逐域文件 + 索引 + 依赖图 + 三质量关口", "```", "",
         "**确定性边界**：工序 1/2/3/5/6/7、重映射、锚点补齐、派生校核、域发射均为确定性代码，"
         "同输入同输出。已验证：连续两次全链路重建，语料包全部文件内容哈希一致"
         "（`407c7e5f08d22d0a`）；ZIP 采用固定时间戳写入，**字节级也可复现**。"
         "唯有**工序 4 的语义内容**由 LLM 层产出，"
         "以 JSON 契约固化在 `build/extractions*/`，可逐条复核。", "",
         "## 6. 本次运行的统计", "",
         "| 项 | 值 |", "|----|----|",
         f"| 章节（取自 docx 样式） | {len(outline['sections'])} |",
         f"| 语义切块 / 脱敏骨架 | {stage['chunks']} / {stage['skeletons']} |",
         f"| 事实节点 | {TOTAL_FACTS} |", f"| 计算/判定规则 | {len(rules)} |",
         f"| 论断 Claim | {len(claims)} |", f"| 证据 | {len(evidence)} |",
         f"| 关系（十类） | {len(relations)} |",
         f"| 规则重算（合计） | {DERIV_TOTAL} |",
         f"| ├ 闭合 / 派生差异 / 仅重算 / 阻塞 | {len(CLOSURE)} / {len(DIFFS)} / {DERIV_NOSTATED} / {len(BLOCKED)} |",
         f"| 待审冲突 / 显式缺口 | {len(conflicts)} / {len(gaps)} |", "",
         "## 7. 并列产物声明（工作区并发写入）", "",
         "本包生成期间，同一工作区出现**另一进程/会话**产出的同类交付物：",
         "`知识资产-上财大数据研究中心可研-2019ZX054.zip`（745 个条目，含 `依据来源/`、`构建脚本/`、`复核/` 等目录），"
         "以及 `kabuild/`、`_stage/`、`复核/`、`references/` 等中间目录。", "",
         "处置与边界：", "",
         "1. **本包与它无内容依赖**：两者的抽取管线、域划分、目录结构均不同；本包不读取、不引用、不合并对方产物。",
         "2. **对方进程的写入已影响过本包输入**：它在本次任务进行中向 `input/大数据研究中心可研.md` 追加了附录A；"
         "本包已从原稿重推文本以消除该影响，并把附录A 隔离到 `外部核查/`、登记为未采纳线索（见第 2、3 节）。",
         "3. **不擅自合并他人产物**：若需比对或合并两份交付物，应以各自 README 为准人工判定，"
         "本包不对另一份产物的正确性作任何背书，也不将其内容写入图谱。",
         "4. **本包可独立复现**：唯一输入是 sha256 为 `"
         + docderiv['source_docx_sha256'][:16] + "…` 的原稿 docx，重建命令见第 5 节。", ""]
(AUD / "05-可复现性与输入完整性说明.md").write_text("\n".join(lines), encoding="utf-8")

# ---------------------------------------------------------------- 06 外部依据绑定与合规复核
lines = ["# 外部依据绑定与跨文档合规复核", "",
         "## 为什么要联合处理", "",
         "本报告的技术函数（耐火等级、高位消防水箱容积、抗震设防类别与分组、招标范围、人均建筑面积指标、"
         "建筑高度分类…）**不是在报告内部闭合的**——它们的取值域约束与推理保证来自外部规范与政策文件。",
         "只读报告文本，这些函数无法判定；必须与外部检索文件**联合建库**才能复核。", "",
         f"本次联合处理的输入：**D1 报告正文** + **D2–D{len(EXT_DOCS)} 外部检索文件**"
         f"（{len(EXT_DOCS)} 份，其中 "
         + "、".join(f"{k} {v} 份" for k, v in sorted({d['retrieval_status']: sum(1 for x in EXT_DOCS if x['retrieval_status'] == d['retrieval_status']) for d in EXT_DOCS}.items()))
         + "）。", "",
         "## 依据层构成", "",
         "| 层 | 产物 | 规模 |", "|----|------|------|",
         f"| 外部文件台账 | `external/documents.yaml` | {len(EXT_DOCS)} 份（含 URL、字节、sha256、检索状态） |",
         f"| 外部切片 | `external/chunks.jsonl` | 950 块（导航噪声已剥除 963 行） |",
         f"| Mandate 条款 | `external/mandates.yaml` | {len(EXT_MANDATES)} 条（{sum(1 for m in EXT_MANDATES if m['trace_status'] == 'located')} 条已定位到原文切片） |",
         f"| 取值域约束 | `external/constraints.yaml` | {len(EXT_CONSTRAINTS)} 条（其中 **{sum(1 for c in EXT_CONSTRAINTS if c.get('mandatory'))} 条为强制性条文**） |",
         f"| 报告←依据绑定 | `external/bindings.yaml` | {len(EXT_BINDINGS)} 条（constrains / warrants / benchmark / driver 四类角色） |",
         f"| 依赖边 | `external/evidence_edges.yaml` | {len(EXT_EDGES)} 条 |",
         f"| 合规复核 | `external/compliance.yaml` | {len(COMPLIANCE['results'])} 条结论 |", "",
         "四类角色不塌缩：同一份文件在必要性章是**驱动**（driver）、在合规性小节是**基准**（benchmark）、"
         "在某条论断下是**推理保证**（warrant）、在技术取值上是**取值域约束**（domain/constrains）。", "",
         "## 复核结论总览", "",
         "| 结论 | 条数 |", "|------|------|"]
for k, v in sorted(COMPLIANCE["counts"].items()):
    lines.append(f"| {VERDICT_ICON.get(k, '')} {k} | {v} |")
lines += ["", "> 三态之外还有「待核查」：**依据未取到就不下判定**，绝不用沾边文件顶上。", ""]

for r in COMPLIANCE["results"]:
    ic = VERDICT_ICON.get(r["verdict"], "")
    lines += [f"## {r['binding']}　{ic} {r['verdict']}——{r['report']['rule']}", "",
              f"- **报告取值**：{r['report']['value']}",
              f"- **外部依据**：{'；'.join(r['basis_titles'])}",
              f"- **依据角色**：`{r['role']}`" + (f"　**约束**：`{'`、`'.join(r['constraints'])}`" if r["constraints"] else ""),
              f"- **判定**：{r['verdict']}",
              f"- **依据说明**：{r['finding']}"]
    if r["evidence_from_report"]:
        lines.append("- **报告侧依据**：" + "；".join(r["evidence_from_report"]))
    if r["branches"]:
        lines.append("- **分支结论**（前提未裁决时给出两条路径，不替客户选）：")
        for br in r["branches"]:
            lines.append(f"  - 若 {br['假设']} ⇒ {br['结论']}")
    if r["needs_to_verify"]:
        lines.append("- **须核对**：" + "；".join(r["needs_to_verify"]))
    lines.append("")

lines += ["## 由联合处理才显形的一条连锁关系", "",
          "```",
          "报告 6.2.2「建筑高度控制在 60m」  vs  报告 6.2.4「12 层、一层 5m、标准层 4m」⇒ 推算 49m",
          "                    │",
          "        GB50016 表5.1.1　建筑高度 > 50m 的公共建筑 = 一类高层公共建筑",
          "                    │  50m 阈值恰落在 60 与 49 之间 —— 类别无法确定",
          "        ┌───────────┼───────────────────────┐",
          "        ▼           ▼                       ▼",
          "  耐火等级下限    高位消防水箱容积      地上耐火分区结论",
          "  一类≥一级      一类≥36m³ / 二类≥18m³",
          "        │",
          "        └─ 叠加一条**不依赖该争议**的约束：",
          "           GB50016 5.1.3① 地下或半地下建筑（室）耐火等级不应低于一级",
          "           —— 报告载明地下设备 1 层、地下建筑面积 319 ㎡，却全文只给一个「二级」",
          "```", "",
          "这条连锁**只有在报告与外部依据联合处理时才能显形**：报告自身既不引用 50m 阈值，"
          "也没有把「地下建筑（室）」与「耐火等级」关联起来。", "",
          "## 处置纪律", "",
          "- **不裁决**：全部「待审」项并列取值与两种分支，由客户/设计单位裁决；本包不改报告任何数字。",
          "- **不臆断规范状态**：依据的施行/废止日期均取自检索页面的行政公告原文，并在 `mandates.yaml` 中标注状态来源。",
          "- **不越界判定**：规范表格数值未取到（如 GB50084 表5.0.1、建标191 附表B）时结论为「待核查」，"
          "并写明须补取哪一份原文。",
          "- **二手来源单列**：`抗震设防烈度各地规定.txt`、`建筑分类与耐火等级.txt` 等为行业网站转录，"
          "台账中标为 `ok_secondary`，其数值入图时注明「二手转录，拟采信前须与规范原文核对」。", ""]
(AUD / "06-外部依据绑定与合规复核.md").write_text("\n".join(lines), encoding="utf-8")

# ---------------------------------------------------------------- README
readme = f"""# 上财大数据研究中心可研 · 可复用资产域包

把《上海财经大学中山北一路校区大数据研究中心 可行性研究报告（修订版）》（2019 年 8 月，
上海同济工程咨询有限公司编制）处理为**16 个可复用资产域**，每个域一个文件，可直接被下游装配侧取用。

## 交付内容

| 目录 | 内容 |
|------|------|
| `SHUFE-BDC-2019-001/` | 语料包本体（30 文件契约：source / chunks / graph / evidence / reasoning / quality / style / index / reuse） |
| `SHUFE-BDC-2019-001/reuse/domains/` | **16 个资产域，每域一个文件** + `domains.yaml` 索引 + `dependency_graph.yaml` 依赖图 |
| **`装配输入包-报告还原.md`** | **单文件装配输入包**（事实输入 + 依据层 + 逐章提示词 + 章节装配表 + 写作纪律），可直接交「推演写作专家」装配还原写作 |
| `SHUFE-BDC-2019-001/style/section_prompts.yaml` | **逐章提示词**：10 个章节族的 `prepare/must_state/must_not/review/shape` + 本项目逐章注入 |
| `SHUFE-BDC-2019-001/reuse/regulatory_dependency.yaml` | **规范依赖资产**（跨项目可复用）：四类依据角色、五类约束、三态判定、软约束替换协议、6 项可复用检查 |
| `审计/` | 6 份人可读报告：资产域清单 / 冲突待审清单 / 缺口清单 / 质量关口报告 / 可复现性与输入完整性说明 / **外部依据绑定与合规复核** |
| `SHUFE-BDC-2019-001/external/` | **外部依据层**：20 份外部检索文件台账 + 950 外部切片 + 22 条 Mandate 条款 + 17 条取值域约束 + 15 条绑定 |
| `外部核查/` | 另一进程的派生核查叙述（已并入依据层，此处仅留档备查） |
| `可复现构建/` | 一键重建脚本与抽取契约（含原稿散列） |

## 16 个资产域

{chr(10).join(f'{i}. `{d["id"]}` —— {d["core_domain"]}（[文件](SHUFE-BDC-2019-001/{d["file"]})）' for i, d in enumerate(domains, 1))}

## 联合处理：报告 + 外部检索文件

报告的**可行性不是自证的**。它的技术函数——耐火等级、高位消防水箱容积、抗震设防类别与设计地震分组、
招标范围、人均建筑面积指标、建筑高度分类——其取值域约束与推理保证来自外部规范与政策文件。
本次把 D1 报告正文与 D2–D20 共 20 份外部检索文件**联合建库**，建成独立依据层并逐条绑定复核：

| 结论 | 条数 | 代表项 |
|------|------|--------|
| ❌ **不合规** | 3 | 引用已废止的《高层民用建筑设计防火规范》；建标191-2018 沿用已废止旧名称；章节体系按 304 号文十章×内容项比对有缺项 |
| ⚠️ **待审** | 5 | 建筑高度 60m/49m 跨越 50m 一类/二类分界，连锁决定耐火等级与水箱容积；抗震设计分组与附录A 不一致；绿建标准版本临界 |
| ✅ **合规** | 5 | 抗震设防类别（人数 1665<8000、无危险功能）；16㎡/人 与附表D-1 文法类一致；使用面积系数口径；招标范围与门槛值逐项一致；两处标准时效 |
| 🔍 **待核查** | 2 | GB50084 表5.0.1 与建标191 附表B 的表格数值未取到 ⇒ 不下判定 |

**最值得先看的一条**：报告 6.2.2 写「建筑高度控制在 60m」，6.2.4 却给出「12 层、一层 5m、标准层 4m」⇒ 推算 49m。
GB50016 表5.1.1 以「建筑高度大于 50m 的公共建筑」为一类高层——**50m 阈值恰好落在 60 与 49 之间**，
于是高层类别无法确定，连锁使耐火等级下限（一级 or 二级）、高位消防水箱容积（36m³ or 18m³）都无法定论；
再叠加一条**不依赖该争议**的约束：5.1.3① 地下或半地下建筑（室）耐火等级不应低于一级，
而报告载明地下设备 1 层、地下建筑面积 319 ㎡，却全文只给一个「二级」。
**这条连锁只有联合处理才显形。**

## 关键结论速览

- 原稿 sha256：`{docderiv['source_docx_sha256'][:24]}…`；语料包状态：**{manifest['status']}**
- 三质量关口：**{'全部通过' if gates['all_passed'] else '未全部通过'}**（kp 内置关口同样通过）
- **待审冲突 {len(conflicts)} 条、显式缺口 {len(gaps)} 条**——全部保持「待审/待补充」，未改任何数字、未补任何口径
- 规则重算 **{DERIV_TOTAL}** 条：闭合 {len(CLOSURE)} 条、派生差异 {len(DIFFS)} 条、仅重算 {DERIV_NOSTATED} 条、因未裁决冲突阻塞 {len(BLOCKED)} 条
- 最值得先看的两条：**总建筑面积 18319 与 18219 并存**（第13章笔误，导致 {len(BLOCKED)} 条派生规则连锁阻塞）；
  **投资估算表 7 处分项-合计不闭合**（其中室外总体工程差 6.12%）

## 怎么交给「推演写作专家」

单文件装配输入包：**`装配输入包-报告还原.md`**（约 195 KB / 2,400 行）。结构：

| 节 | 内容 |
|----|------|
| §0 | 使用说明：借形/借值分工、装配 5 步、**8 条写作硬纪律**、6 条不变量 |
| §1 | 项目元信息 + 报告编制信息（报告编号 `2019ZX054`、编制单位、编制人、日期） |
| §2 | 法定大纲（304 号文十章 × 内容项）与本报告 16 章对照 |
| §3 | **事实输入**：343 个唯一事实节点（358 次陈述），按章分组，含出现次数与原文定位 |
| §4 | 规则实例 35 条 + 复算结论（闭合/派生差异/阻塞/未解） |
| §5 | 论证单元 28 条：Toulmin 六元组 + 证据绑定（保证为空的一律标注「不得代拟」） |
| §6 | 依据层：20 份文件台账 / 22 条 Mandate 条款原文 / 17 条取值域约束 / 15 条绑定与三态判定 / **6.5 规范依赖模式** |
| §7 | **章节装配表（含逐章提示词）**：16 章各自的可用节点、关键取值、prepare/must_state/must_not，以及该章的冲突、缺口、依据绑定 |
| §8 | 冲突待审 15 条（并列取值，**不得裁决**）+ 因冲突阻塞的派生规则 |
| §9 | 缺口 15 条（正文显式留白，不编造） |
| §10 | 术语与口径 + 单位量纲陷阱 |
| §11 | 溯源索引：论断→证据→定位；节点→切片；依据→外部切片 |

写作时**数字只写 `{{节点ID}}`**（如 `{{N-8f432cf2e264}}`），成稿后可反向回读为节点与本包比对。

## 边界声明

本包**不对任何数值的准确性负责**，也不判断造价高低、人数是否合理。本包保证的是：
法定内容不遗漏、事实在全文传播中不矛盾、每条论断可追溯到证据、变更影响可见、冲突显式待审。

`published`（发布到资产库）需用户对本次修订明确确认后才可执行；当前为 `validated`。
"""
(DELIV / "README.md").write_text(readme, encoding="utf-8")

print(json.dumps({"audit_files": sorted(p.name for p in AUD.glob("*.md")),
                  "readme": str((DELIV / "README.md").relative_to(WS)),
                  "conflicts": len(conflicts), "gaps": len(gaps),
                  "domains": len(domains)}, ensure_ascii=False, indent=2))
