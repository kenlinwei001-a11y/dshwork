# 节点契约（v1.1）

本文件是「节点怎么执行」的唯一口径。工作流图里的节点只写「按本文件某节执行」，不复制内容。
每个节点四个要素：**执行清单（伪代码）· 输出 schema · 门禁 · 语义判断点**。

门禁统一入口：`python3 scripts/validate_node.py --node <name> --out <out目录> [--text <正文>]`；
**exit≠0 时该节点不得标记完成**，按失败项修后重跑。

## clauses（技能第 1–3 步）

- 输入：标准文本路径、`standards/<slug>.source.json`、工具段 `00-provenance.json`。
- 清单：
  1. 读 `00-provenance.json`；route=OCR 时按 OCR 口径（数值不可辨登记 GAP-DATA，不改写原文）。
  2. 核对取字：`python3 scripts/cap.py probe <PDF>`，与 00-provenance 不一致以 probe 为准并记日志。
  3. `clause_split.py` 出条款骨架（编号/页码/quote），LLM 只改差异（补漏、判模态、定角色）；按章分片（每片 ≤20 条）。
  4. 写 `01-clauses.json`（standard-element-schema.md）。
  5. 门禁：`validate_node.py --node clauses`。
- 判断点：章节角色、模态、注是否强制、引用状态、缺口分类、method_family。
- 禁止：改写原文、猜数值、跳过门禁、重写工具段产物。

## elements（技能第 4–7 步）

三段式：**脚本抽候选 → LLM 只写判断 + ref → 脚本组装/解析**。

- 输入：`01-clauses.json`、`standards/<slug>.txt`、`00-provenance.json`。
- 清单：
  1. `standard_store.py --clauses 01-clauses.json --text <正文> --db store.db`
     —— 实际产物是**不可变**的 `store-<文本sha>.db`：已存在且 sha 匹配则复用，否则写临时文件后原子替换（并发安全）。
  2. `extract_candidates.py --clauses … --text … --out candidates.json`（可抄字段 + 覆盖率）
  3. LLM 只写判断与引用：族、statement、obligation、applicability、origin、合并/拆分；
     参数一律用 `{"ref":"<clause>#<序号>"}` 引用候选，**不重抄数值**；derived 值才写 `value`+`derive_from`。
     产出 `judgments.json`。
  4. `assemble_elements.py --clauses … --candidates … --judgments … --out 02-elements.json`
  5. `convert_refs.py --elements 02-elements.json --db standard.db --out 02-elements.refs.json`（未覆盖的转 value_ref）
  6. `resolve.py --elements 02-elements.refs.json --db store-<sha>.db --out 02-elements.resolved.json`
     —— 展开并校验**库 sha = ref.sha** 且 span 原文一致；任一不符标 DANGLING；**DANGLING 必须为 0**。
  7. 门禁：`validate_node.py --node elements`（含 ref 可解析率、assemble.errors=0、无 DANGLING）。
- 批处理：单批即可（判断量小）；仅 `judgments.json` > 80 KB 时退两批并记日志。
- 判断点：族归属、干扰因果、图转拓扑、公式符号与适用域、缺口归类。
- 禁止：重抄候选数值、从不可辨区取值、无 unit 参数、跳过门禁、留分片。

## rules（技能第 8–9 步）

- 输入：`01/02`、`00-provenance.json`。
- 清单：
  1. 读 01 的 standard_type，按类型调权重。
  2. 条款 > 40 条时分片写 `out/parts/`，每批落盘，合并后删除。
  3. 逐条可判定要求出规则卡；有阈值写 predicate（带 unit），纯定性写 qualitative_check（且不得带 predicate，`verdict_ceiling=NO_PASS`）。
  4. 覆盖矩阵**不手写**：`build_coverage.py --clauses 01 --rules 03 --write` 由卡片反推（rules/covers_clauses→judgeable）。
  5. PENDING_UPLOAD 补齐 GAP-REF；写 `03-rules.json`；门禁：`validate_node.py --node rules`。
- 判断点：判据选择、定性三档、定位线索、受影响规则。
- 禁止：谓词数值无出处、定性卡带 predicate、覆盖矩阵缺行、跳过门禁。

## toolchain（工具段）

- 统一入口：`scripts/run_all.py`，按可用产物依次跑 provenance → metrics → package → semantica。
- 缺前置就 `skip` 并如实报告；exit≠0 停线；每次写 `runner-*.json` 溯源。
- 门禁：`validate_node.py --node toolchain`（要求 `audit_metrics.json` gate=PASS + runner 记录）。
- 禁止：补造产物、改写命令输出、用已有旧记录冒充本轮。

## audit（技能第 13 步）

**轻量审计**：确定性项由工具算，LLM 只读结论、抽验、分类。

- 输入：`audit_findings.json`（工具段产出，约 1–6 KB）、`04-audit.md` 模板；**不要重读 01/02/03 全文**。
- 清单：
  1. 读 `audit_findings.json`：锚命中、覆盖缺口、谓词脱靶、ID 重复、缺口无 affected_rules、样本数字。
  2. 抽验：从 `sample_numbers` 里挑 5 个回原文核对（只看这 5 处，不扫全表）。
  3. 判级：B 阻塞 / D 待裁决 / W 非阻塞；每条一行，≤60 行。
     每条必须三段式：**哪里不合规 + 缺少什么 + 依据（basis）**；basis 取自 `sop-graph.json` 节点的 `basis`（论证节点声明），无依据时写「标准未给依据」。
  4. 写 `04-audit.md` 与 `audit_result.json`（verdict + 计数）。
  5. 门禁：`validate_node.py --node audit`。
- 判断点：B/D/W 的归类、待裁决项识别。
- 禁止：重跑全量检查、采信作者自述、改上游文件、写超过 60 行。

## semantica（旁路，不阻塞）

- 读：`semantica://graph/summary` / `decisions`，超时记 `available:false`，不阻塞交付。
- 写：MCP 当前无写入工具 → **只生成 payload 到 `out/semantica-queue/`**（命名空间 `std:<slug>`），
  `--apply` 返回 `applied:false` 并列出所需工具；工具挂载后再推送，不在抽取链里硬写共享图。


## 性能与执行模式（v1.3 默认）

| 环节 | 默认执行方式 | 并行/分片 | 说明 |
|---|---|---|---|
| 取字 | OCR 按页并行；二轮只重跑低置信页 | 4 页并发 | 缓存键 PDF sha |
| 条款切分 | `clause_split` 出骨架 → LLM 只改差异 | 按章分片 | 定位用 quote+token 双匹配 |
| 要素 | 候选预填（`extract_candidates`）→ LLM 只写判断+ref | 按族三分片 | 图由脚本按算子编译 |
| 规则 | LLM 出卡片；**覆盖矩阵由 `build_coverage.py` 生成** | 按 C 类三分片 | 矩阵不再手写 |
| 审计 | `audit_findings` + 抽 5 样本 | 无 | 不重读全文 |
| 合并/交接 | `merge_ses` 合并；说明/看板模板生成 | 可并行 | 说明与看板互不依赖 |

规则：
1. 并行只在“输入相同、输出不相交”时启用；合并后必须重跑全套门禁；
2. 任一步 10 分钟无产物增长 → 判卡住，只重做当前片；45 分钟绝对上限兜底；
3. 缓存一律以 sha 为键，文本变化即失效。

## 小调用与强制落盘（v1.6，防卡死）

任何 LLM 步骤必须满足：

1. **单次 ≤5 条**：一次调用只判 5 条以内，输入只给这几条（不塞整份 candidates）。
2. **每 5 条落盘**：判完立即 append 到 `out/<step>.parts/<i>.json`，并打印 `done i/N`。
3. **心跳**：每 60 s 写 `out/.heartbeat`（内容=时间戳）。
4. **Lead 接管判据**：5 分钟无心跳或 10 分钟无新增落盘 → 中止，只重做当前 5 条。
5. **先验证再并行**：并行前先让 1 个分片跑通，再 fan-out。

## 并行与分片（v1.2）

**可并行**（输入相同、输出不相交）：
| 单元 | 依赖 | 边界 |
|---|---|---|
| 跨标准 | 无 | 每标准一实例 |
| elements 按族 | 01 + candidates | MATL / PROC+APPA / SAMP+QC+其余 |
| rules 按 C 类 | 01 + 02 | C1–C3 / C4–C6 / C7–C8 |
| 工具段 | 各自产物 | probe / lint / ontology / findings |

**不可并行**：clauses→elements→rules 的 ID 依赖；audit 需 rules；package 需 audit_result；handoff 需 ses。

**分片规则（防全量重做）**：
1. 只在条款边界切；每片 ≤30 条、产出 ≤50 KB；
2. 每片写 `out/parts/<step>-<shard>.json`，写完即落盘；
3. ID 由条款号确定性生成（`SE-族-条款-序号`），合并不重编号；
4. 合并脚本幂等；合并后**必须重跑全套门禁**（lint/ontology/validate_node）；
5. 某片失败只重做该片，不影响其他片。

**缓存**（跨标准复用，键=sha）：
| 缓存 | 键 | 失效条件 |
|---|---|---|
| 取字结果 | PDF sha256 | 文件变 |
| 引用库 | 标准号+版本 | 版本变 |
| candidates/store | 文本 sha | 文本变 |
| 规则模式 | 方法族+C 类 | 方法族变 |

**看门狗（无进展检测，非时间阈值）**：某步 10 分钟内 `out/` 下该步产物与 `parts/` 的 size/mtime 均不变 → 判卡住，中止并只重做当前片；45 分钟绝对上限兜底。

## 输入输出纪律（v1.5，消除重复）

1. **单次阅读**：每条条款原文只被 LLM 读一次（clauses 步）。elements/rules 只读 `rows.json`（clause/page/modality/numbers/chems/actions），不读 01 原文。
2. **交接只传引用**：节点间传 `handoff_state.json`（out 路径 + derived 计数 + changed 列表），不转述内容、不重写要点。
3. **派生工具单一入口**：`audit_findings` / `merge_ses` / handoff 数字一律先读 `facts.json` 与 `derived.json`，读视图仅作回退并打印 `source=views`。
4. **中间态即产即删**：`02-elements.{assembled,refs,resolved}`、`_split.json`、`parts/` 用完由 `cleanup_intermediates.py` 清理。
5. **单向**：`facts → 视图`。导出后写 `.views_exported`；`facts_build` 发现该标记且无 facts 时拒绝重建（需 `--force`）。

## 事实层与派生视图（v1.4，唯一写入口）

**只有 4 类对象可写**（`facts.json`），其余一律脚本派生，模型不得写：

| 可写事实 | 内容 | 谁写 |
|---|---|---|
| `clauses` | 条款号、页、原文引文、模态、类型 | LLM（判断）+ 脚本（骨架） |
| `bindings` | 参数 → `value_ref`（clause/span/raw/sha） | 脚本（convert_refs） |
| `judgments` | 要素族/义务/origin；规则类别/上限/on_missing | LLM（填槽） |
| `gaps` | 缺口类型、pending_class、受影响规则 | LLM + 脚本分类 |

**派生视图（禁止手写）**：`counts`、`coverage_matrix`、`categories`、`pending_class` 统计、handoff 中的数字、看板、`audit_findings`。

执行：`facts_build.py --out <out>` → `facts.json` + `derived.json` + 完整性报告（外键/引用/ID 重复）。完整性非 0 即失败，不进入下一步。

理由：同一事实若有两个写入口，不一致是必然的；门禁只能事后发现，构造上禁止才根治。

## 缺口分级（pending_class，v1.3）

缺口不是都要人裁决；每条 gap 必须带 `pending_class`：

| 类别 | 含义 | 处置 | 是否阻塞交付 |
|---|---|---|---|
| `PENDING_USER` | 两种读法都成立且结论方向相反 | 交用户裁决 | 阻塞相关规则 |
| `PENDING_DATA` | 缺原文/原图/源文件 | 请求补件，不猜 | 相关规则 UNVERIFIABLE |
| `PENDING_REF` | 引用标准未上传 | 待上传清单 | 相关规则 UNVERIFIABLE |
| `PENDING_DOC` | 需仪器说明书/实验室文件 | 待补 | 相关规则 UNVERIFIABLE |
| `LAB_POLICY` | 标准留白，需实验室内规定 | 出补件单，SOP 发布后升级规则 | 不阻塞（判 UNVERIFIABLE） |
| `REGISTERED_CONFLICT` | 标准自身矛盾 | 登记，按更硬锚判，规则规避冲突处 | 不阻塞 |

原则：**能登记的不裁决，能补件的不猜测，能内规的不等标准。**

## fix

- 输入：`04-audit.md`、`02/03`。
- 清单：逐条 B-xx 处置（改掉 / 升级为 gaps）；D-xx 只登记不裁决；就地更新并在 `revision_log` 各加一行。
- 门禁：`validate_node.py --node fix`（revision_log 非空）。
- 禁止：引入原文没有的数值；为过审删条目。

## handoff（技能第 14 步）

- 输入：`ses.json`、`04-audit.md`、`01/02/03`、`00-provenance.json`。
- 清单：
  1. 先跑工具段：`run_all.py --stages package`（需 audit_result.json）→ `ses.json`；再 `--stages semantica`（dry-run）。
  2. 若 `ses.json` 缺失或 `audit_result.verdict≠pass` → 停线，不得手写。
  3. 写 `05-handoff.md`（七节）与 `dashboard.html`（数据取自 ses.json）。
  4. 门禁：`validate_node.py --node handoff`。
- 判断点：说明文字、风险表述、看板叙事。
- 禁止：重算计数、改 ses.json、签发报告结论。

## SOP 图为主产物（v1.7）

**主产物是 `sop-graph.json`，01/02/03 降级为它的视图。**

| 节点类型 | 来源（唯一） | 说明 |
|---|---|---|
| `step` | `procedure_graph` 节点 | 步骤 + params + done_when + clause；**PROC 要素同 clause 合并进来，不再单列** |
| `reagent` / `instrument` / `qc_gate` | MATL / APPA / QC 要素 | 作为步骤属性，连 `requires` |
| `constraint` | INTR 等 | 干扰/边界约束 |
| `justification` | PERF 要素（精密度/准确度/验证） | **禁止作为判据**，`usage=reference_only` |

**边类型**：`precedes`（步骤先后）、`requires`（步骤→试剂/仪器）、`constrains`（规则→节点）、`verifies`（质控门→步骤）、`justifies`（论证→节点）、`cites`（节点→条款锚）。

**不变量（门禁）**：
1. 每个节点 ≥1 anchor（clause+page+quote）；
2. 参数必须有 ref 或 raw；
3. 非 justification 节点必须有 criteria，或显式 `no_threshold=true`；
4. justification 节点不得出现在任何 criteria 里；
5. step 节点数 = procedure_graph 节点数（PROC 要素只能合并，不得新增 step）。

执行：`run_contract.py --util sop_graph --out <out>`；产出 `sop-graph.json` 并打印不变量错误。

## 图谱 v1.8：节点/关系全集与不变量

**节点类型（10 类）**：`step`、`reagent`、`instrument`、`qc_gate`、`constraint`、`interference`、`failure_mode`、`result`、`record`、`analyte`、`justification`。

**关系（12 类）**：`precedes`、`uses`、`requires`、`determines`、`computes`、`reports_as`、`records`、`verifies`、`invalidates`、`interferes_with`、`eliminated_by`、`avoids`、`prepared_from`、`justifies`。

**按类型的不变量**：
| 类型 | 不变量 |
|---|---|
| step | ≥1 anchor；有 done_when 则生成 record 节点 |
| reagent/instrument | ≥1 `uses`/`prepared_from` 入边（否则记录孤立实体数） |
| qc_gate | ≥1 `verifies` 或 `invalidates` 出边 |
| interference | ≥1 `interferes_with` 出边 |
| result | ≥1 `reports_as` 出边（挂修约/单位约束） |
| record | 由 step.done_when 派生，不得手写 |
| justification | `usage=reference_only`，不得进入任何 criteria |

**basis（论证备注）**：每个带约束的节点挂 `basis[]`（论证节点 id + claim + anchor）；审计输出的每条结论必须三段式**哪里不合规 + 缺什么 + 依据（basis）**。

## 交付目录与执行留痕（v1.9）

**目录分离**：`out/machine/`（JSON/JSONL，程序与 agent 唯一可读区）与 `out/human/`（md/html，仅供人）。
**agent 禁读 `human/`**：不得把 md 中叙述当作判据；md 由 JSON 渲染生成，不作为任何步骤输入。
生成：`run_contract.py --util split_dirs --out <out>`。

**执行留痕（trail）**：每完成一个 script/gate 步骤追加一行
`{"step":"<name>","exit":0,"outputs":[...],"at":"..."}` → `out/trail.jsonl`。
命令：`run_contract.py --util trail --step <name> --exit <code> [--outputs a,b]`。

**开跑前自检**：`run_contract.py --util check --node <node>` 打印该节点必须运行的命令与判据。
**完成前校验**：`run_contract.py --util verify --node <node>`，写 `verify` 记录；**没有 verify 记录，门禁判 FAIL，不得标 done**。
`validate_node` 已内置 `trail_present` 检查。
