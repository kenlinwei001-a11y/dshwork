---
name: standard-element-extraction
description: 把技术标准解构为可执行要素、判定规则与图谱，供审核智能体判报告。用于标准条款抽取、抽取准入闸、引用闭包、实验室文件对齐、规则化与方法族对照。
---

> **agent 入口是脚本，不是本文。** `python3 skill-update/scripts/run_contract.py --util check --node <name> --out <产出目录>`
> 本文供人阅读：说明每一步在做什么、口径为什么这样。执行以门禁 exit 码与 verify 留痕为准，md 不作为判据。

# 标准要素抽取（执行手册）

**目标**：抽出来的东西能判一份检测报告，并能回指条款页码原文。判不了的叫摘要，不叫抽取。

## 一、怎么跑（agent 唯一入口）

> **单源说明**：执行入口只有工作区的脚本；本文只说明调用方式，命令里的脚本路径统一指向工作区。

**不读文档，只读指令。** 执行器直接把该跑什么吐出来：

```bash
python3 skill-update/scripts/run_contract.py --util check  --node <name> --out <out>   # 必做命令（路径已展开）+ 缺失前置输入
python3 skill-update/scripts/run_contract.py --node <name>  --out <out>                # 按契约跑，成功即自动留痕
python3 skill-update/scripts/run_contract.py --util verify --node <name> --out <out>   # 写留痕（只认本节点带 node 标记的记录）
python3 skill-update/scripts/validate_node.py --node <name> --out <out>                # 门禁，exit≠0 不得标完成
```

节点顺序：`clauses → elements → rules → sop → toolchain → audit →（fix 循环）→ handoff`。

`check` 输出的命令可以照抄执行：不要再自己拼路径，也不要读 `references/node-contracts.md`（那是给人审计用的）。契约改了而 `check` 没跟着变，就是契约写错。

## 二、三条纪律

1. **出指令，不出转述**：产物是一条可执行命令或一次结构化写入，不是「我读了 A/B/C，结论是……」。「读了 N 个文件只产出一条命令」就是错的。
2. **填槽靠引用，不靠检索**：用 `rule_id` / `span_id`（`sha:start-end`）/ `clause` 直接定位。取原文按 `span_id` 主键查切片库；查图用 `--util graph_lookup --rule/--node-id`。**禁止现场检索、禁止整份加载 JSON**。
3. **产物只进 `machine/`**：`human/` 由 JSON 渲染，agent 禁读。

模型只做三类事：**归类判断**（模态、要素族、定性三档、冲突是否人裁）、**生成叙述**、**ReAct 下一步**。算数、比较、计数一律交给脚本。

## 三、九件套

| # | 产物 | 文件 |
|---|---|---|
| 1 | 条款登记册 clause_registry | `01-clauses.json` |
| 2 | 引用登记册 reference_register（含 PENDING_UPLOAD → GAP-REF） | 同上 |
| 3 | 要素包 SE-12 | `02-elements.json` |
| 4 | 公式卡 | 同上 |
| 5 | 流程与流路 procedure_graph | 同上 |
| 6 | 依赖推演 dependency_graph | 同上 |
| 7 | 实验室对齐 lab_alignment | `03-rules.json` |
| 8 | 规则卡 C1–C8 + 定位线索 | `03-rules.json` |
| 9 | 质量与交接 + 缺口 | `05-handoff.md` / `ses.json` |
| — | **SOP 图与落库** | `sop-graph.json` + `library/{standards.db,spans.db}` |

## 四、SOP 图是执行骨架，不是附图

- 每条规则必须在图上有落点（`rule_node`）；挂不上的写 `machine/graph_gaps.json`，**不许造节点**。
- 挂法按 `(条款, 类型偏好)`：C1→constraint/step/failure_mode，C2/C5→step，C3→instrument，C4→reagent，C6→result/constraint，C7→qc_gate，C8→record。
- `justification` / `analyte` 节点**永不接收规则**（依据不得当判据）；某条款只抽出 PERF 依据时，登记 `ONLY_JUSTIFICATION_NODE`，回要素层补 constraint。
- 下游按 `node_id` 分组、沿 `requires/uses/verifies` 边找记录，**不要写成逐条 rule_id 的平铺列表**。

## 五、判定权限

本技能**不签发**报告合格/不合格结论。只提供：规则（带谓词与阈值）、证据要求、定位线索、缺口与最小补充请求。

判定枚举由审核侧给出：`PASS / FAIL / NOT_APPLICABLE / UNVERIFIABLE / CONFLICT_PENDING`。

红线：缺证 ≠ 不合格；不可辨区不出数值谓词；「供参考」类只 `NO_FAIL`；定性卡 `NO_PASS`。

## 六、验收只认机器证据

`check` 有缺失前置输入 → 不许开跑；`verify` 不合格 → 不许标完成；门禁 FAIL → 修完重跑。
没有留痕的「已完成」不算完成。

## 七、细节在哪（人读）

- 字段与枚举：`references/standard-element-schema.md`
- 规则卡语法：`references/audit-rule-card-spec.md`
- 引用闭包与实验室文件对齐：`references/reference-closure-and-lab-docs.md`
- 落库与多标准：`references/standard-store.md`
- 端到端示范与全量图谱：`references/hj671-2013-worked-example.md`、`references/hj671-2013-graph.md`
- 交接契约：`references/handoff-contract.md`
- **审计用**（agent 不读）：`references/node-contracts.md`
