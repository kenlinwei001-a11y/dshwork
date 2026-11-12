---
name: standard-element-extraction
description: 把技术标准解构为可执行要素、判定规则与图谱，供审核智能体判报告。用于标准条款抽取、抽取准入闸、引用闭包、实验室文件对齐、规则化与方法族对照。
---

# 标准要素抽取（随包技能）

本技能是「标准要素抽取专家」的操作手册。目标只有一个：**标准解构到"审核智能体能判"**，而不是"人能读懂"。

## 何时使用

- 把一份标准（HJ/GB/JJF/ISO/企业规范）变成可执行流程、设备清单、试剂配制、公式与质控阈值。
- 生成能逐条判定检测报告与过程记录的规则卡。
- 梳理规范性引用、提醒补充未上传文件。
- 做同族方法标准对照、标准换版增量重抽。
- **规模化抽取**（数十到上千份标准）时定义统一口径。

## 执行顺序（14 步，顺序不可颠倒）

| # | 步骤 | 产出 | 门 |
|---|---|---|---|
| **0** | **过两道门**：① 本体校验 `validate_ontology.py` ② 准入闸 `cap.py gate` | 载体清单 R/P/M/G/B/A/SKIP + 四项指标 | ① ERROR=0 ② ρ∈[0.6,2.0]、e≥0.95、a∈[0.1,0.4]、b∈[0.05,0.25] |
| 1 | 建档 + **文本层判定与取字分流** | standard_id、指纹、页数、取字路径 | 指纹可复现；扫描件标 OCR 置信与不可辨区 |
| 2 | 条款登记（**章节角色由目次解析**） | clause_registry | 编号条款 100% 登记；模态枚举合法 |
| 3 | 引用闭包（递归） | reference_register + 待上传清单 | 每个引用有状态与受影响规则 |
| 4 | 要素抽取（SE-12） | elements | 12 族齐；normative 全覆盖；verbatim/derived 分层 |
| 5 | 参数提升（阈值成节点） | parameters | 每个阈值带 unit + 来源三元组（表/行/列/页） |
| 6 | 公式与数值自洽 | formula_cards + 反算校验 | 反算全中；量纲闭合 |
| 7 | 图转拓扑 | procedure_graph | 节点带参数与完成判据；边带语义 |
| 8 | 规则化（C1–C8 + 算子集合，见规则卡规范 §3） | audit_rule_cards | 每条有 predicate.op 或 qualitative_check、on_missing、定位线索 |
| 9 | 图型编译 | graph（nodes/edges/AST） | 每条边有 operator；规则 AST 可求值 |
| 10 | 求值回归 | exec-trace | golden case 全绿 |
| 11 | **报告侧绑定** | 字段别名/证据位置/勾选映射/计算链规则 | ≥20% 规则能绑定到真实材料 |
| 12 | 隔离落库 | 项目库（一项目一库） | 计数一致、0 重复 |
| 13 | 质量审计 | audit 报表 | 见「交付前检查」 |
| 14 | 交接 | SES 包 + 规则卡 + 缺口 + 定位契约 | 审核智能体可直接消费 |

## 硬性口径

1. **先过闸，再抽取**。没进载体清单的内容不抽；抽了也不进运行层。
2. **规则不分级，只分类**（C1–C8）；每张卡至少 1 个可判定谓词（predicate.op 取规范 §3 枚举）或 qualitative_check 三档。
3. **缺证不默认通过**；`on_missing` 必须写死（FAIL / UNVERIFIABLE）。
4. **三层分离**：verbatim / derived / convention；derived 必写 derive_from。
5. **未上传的引用不得凭记忆补全**；未上传的实验室文件不得假设等效。
6. **所有数值必须能回到原文**（条款+页码+引文；表格回到行列坐标）。
7. **报告定位 quote 必须命中原文**；命中不了标 UNLOCATED，不标错位置。
8. **合并抽取必须登记 `source_clauses[]`**，且每条源条款可独立回指。
9. **资料性数据只进参照层**：标 `reference_only`，禁止作为判定阈值；必要时配一条护栏规则。
10. **规则集不跨标准混用**；方法族差异必须显式列表（见下）。

## 文本层判定与取字分流（第 1 步的强制规则）

| 情形 | 判定依据 | 取字方式 | 附加要求 |
|---|---|---|---|
| 有文本层 | PDF 内 `/Font` 对象 > 0 | PDFKit 直取文本 | 抽查 3 页与图像比对 |
| 无文本层（转曲/扫描） | `/Font` = 0 | 300 dpi 栅格化 + OCR | 标 OCR 置信；数值回到图像逐格核读 |
| 手写件 | OCR 输出不成句 | 不抽内容，标 `manual_only` | 审核时判「需人工核」 |

**数值来源只认图像，OCR 只做定位**——已发生过 `0.051→0051`、峰序整体读错。

## 章节角色从目次解析（第 2 步）

- **章节号不固定**：HJ 84 第 2 章=规范性引用，HJ 535 第 2 章=方法原理。按编号判必错。
- 从**目次页**解析「章号 → 章标题」，再用标题分词定角色：

| 章标题含 | 角色 |
|---|---|
| 范围 / 适用范围 | R + P2（基质、被测物） |
| 规范性引用 / 引用文件 | B（引用转移，闭包） |
| 原理 / 术语 / 定义 | SKIP |
| 干扰 | R + P2（处置手段集合） |
| 试剂 / 材料 | R + P1（浓度、等级、保存期） |
| 仪器 / 设备 | R + P1（配置、性能） |
| 样品 | R + P5（容器、固定、时限） |
| 分析步骤 / 测定 | R + P1（条件、点数、顺序） |
| 计算 / 表示 | R + P1（公式、修约） |
| 精密度 / 准确度 | A（参照数据） |
| 质量保证 / 质量控制 | R + P6（配额、阈值） |
| 注意 | R + P5（风险约束） |

- **子条款继承父章角色**；自身标题命中则覆盖。
- **表格/图不归章**，按内容判：判据型 → R+A；性能数据 → A（+护栏）；峰序 → M+R。

## 资料性内容处理（第 8 步的特例）

资料性 ≠ 不可判，也 ≠ 可当阈值。三种处理：

| 内容 | 处理 |
|---|---|
| 含可判信息（如附录 B 峰序） | 抽 M 映射表 + 规则（不同体系峰序不同，标错即错） |
| 纯性能数据（精密度/准确度） | 抽 A 档案 + **G 护栏**（"不得作日常判据"） |
| 与正文冲突 | 登记 GAP-CONFLICT，不擅自裁决 |

## 报告侧绑定（第 11 步，四件套）

标准只给"判什么"，真实报告给"到哪取"。四件缺一不可：

| 件 | 内容 | 例 |
|---|---|---|
| 字段别名 | 规则字段 ↔ 报告/记录实际叫法 | "检测结果" ↔ 报告值 / 仪器读数 |
| 证据位置 | 规则 → 文档/页/栏/定位方式 | `ARC-C7-11.1-01` → 原始记录·空白行 |
| 勾选映射 | 表单勾选项 → 条款 | "0.45 μm 滤膜" → 6.2 / 7.2 |
| 计算链等价 | 仪器直读浓度时须证明等价标准公式 | ρ=(h−h₀−a)/b×f |

## 方法族对照：口径差异必须显式

同一批样品常对应多个方法标准，要求互相矛盾。已实测差异：

| 项 | HJ 84 阴离子 | HJ 535 氨氮 | HJ 671 总磷 | HJ 636 总氮 |
|---|---|---|---|---|
| 相关系数 | 0.995 | 未规定 | 0.995 | **0.999** |
| 加标回收 | 80–120% | 未规定 | 80–120% | **90–110%** |
| 修约(<1) | 三位小数 | — | 三位小数 | **两位小数** |
| 样品保存 | **不加固定剂** | 酸化 pH<2 | 酸化 pH≤2 | 酸化 pH 1~2 |

→ 规则集按"报告声明的方法"选择；差异表进 method_family，**不得跨标准套用**。

## 能力件（`scripts/`，确定性、零 LLM、可进 CI）

| 命令 | 作用 | 何时用 |
|---|---|---|
| `cap.py probe <pdf>` | 文本层判定 → `PDFKIT / OCR / MANUAL` | 第 1 步 |
| `clause_split.py --text x.txt` | 文本 → 条款登记册（目次驱动） | 第 2 步 |
| `cap.py gate --ses x.json --toc t.json` | 准入闸回测（漏判/多判） | 第 0 步 / 交付前 |
| `cap.py patternize --ses x.json` | 29 个模式 → 候选规则 + 两级召回 | 第 8 步起草 |
| `table_from_pdf.py --pdf … --table …` | PDF → 网格 → 逐格 OCR → 表格 spec | 第 5 步（判据型表格） |
| `table_store.py ingest-cells --spec x.json` | 通用入库（标准表/报告表同一路径） | 第 5 步 |
| `table_store.py lookup/row/col/verify` | 表格窄接口（带单元格溯源） | 判定期取数 |
| `cap.py lint --ses …` | 8 类一致性检查 | 第 13 步 |
| `validate_ontology.py --ses … --graph …` | 本体约束校验（类/关系/不变式） | 第 0 步 / 交付前 |
| `benchmark.py --manifest m.json` | 冻结指标 + 回归比较（退化即失败） | 每次发布 |
| `run_all.sh --root <根>` | 一键回归：本体 → lint → benchmark | CI |
| `ocr_adapter.py` | OCR 三后端：`vision` / `local`（留白）/ `none` | 取字 |

**OCR 留白契约**：`recognize(单格PNG) -> {text, conf}`；不得改写数字位数（`0.00` 不得输出 `0.0`）；识别不了返回空串。
设 `OCR_LOCAL_ENDPOINT=http://127.0.0.1:PORT/ocr` 即切换，其余零改动。

**数值来源只认图像**：表格入库前必须逐格图像核读；OCR 只做定位，且每格标 `value_source=IMAGE|OCR`。

## 工具段与能力注册表（v1.1 新增）

图只保留语义节点；取字、指标、合并、图谱由 `scripts/run_all.py` 统一调度，能力定义在 `scripts/registry/capabilities.json`。

| 能力 | 执行器 | 用途 |
|---|---|---|
| `text.probe` | tool | 取字路由与指纹 |
| `ocr.engine` | tool | OCR 引擎选择（`apple-vision` / `user-model` / `fallback-none`）+ dpi + endpoint，带 fallback 链 |
| `clause.split` | tool | 目次驱动条款切分（仅干净文本） |
| `audit.lint` | tool | 规则卡一致性检查 |
| `audit.ontology` | tool | 本体校验（v1.1：predicate 与 qualitative_check 二选一） |
| `merge.ses` | tool | 确定性合并 01/02/03 + audit_result → ses.json |
| `graph.semantica` | mcp | 只读共享图摘要；写入未挂载，只做命名空间 dry-run |
| `llm.semantic` | llm | 语义节点（角色/要素/规则），schema + validator 约束 |

硬规则：工具段产物必须附 `runner-*.json` 执行记录（能力/版本/exit/stdout 哈希）；缺记录视为未经脚本，按未完成处理。

## 交付前检查（确定性）

| 检查 | 判据 |
|---|---|
| **本体校验** | 类/关系/不变式 **ERROR = 0**（`validate_ontology.py`） |
| 闸回测 | 漏判（该抽未抽）= **0**；多判 ≤5% |
| 条款覆盖 | normative 条款 100% 有要素或说明为何不抽 |
| 规则可判 | 可求值率 ≥95%；每条有锚 + 定位策略 |
| 数值自洽 | 反算/区间/分档全过；每个数值可回原文 |
| ID 唯一 | rule_id / element_id 无冲突（构建期断言） |
| 模态一致 | 应/宜/可/不应 → MUST/SHOULD/MAY/MUST_NOT，不漂移 |
| 参照隔离 | 资料性数据标 reference_only，未进判定链 |
| 缺口 | 每条缺口写明影响规则 + 最小补证请求 + 责任方 |

## 资料

- `references/scope-gate.md`：准入闸（八原语、六载体、决策树、陷阱库、回测）
- `references/standard-element-schema.md`：字段级 schema、ID 方案、validator 必检项
- `references/audit-rule-card-spec.md`：规则卡字段、C1–C8、谓词、定位契约
- `references/reference-closure-and-lab-docs.md`：引用闭包、实验室文件对齐、方法族
- `references/hj671-2013-worked-example.md` / `hj671-2013-graph.md`：端到端示范
- `references/handoff-contract.md`：审核侧契约（结果记录、span、换版）
- `references/standard-store.md`：落库与多标准/多报告模型
- `scripts/ontology.json`：轻本体（6 类 / 21 关系 / 7 不变式，只做约束不做推理）
- `scripts/`：能力件 12 个（见上表）+ 标准库脚本（建库/导入/查询/导出/检索）+ runner/run_all/verify/merge/semantica
- `CHANGES.md`：v1.1 契约变更与验收

## 一句话

**抽得对不算完成，抽到"审核智能体拿着能判、判完能解释、判不了知道缺什么"才算完成。**
