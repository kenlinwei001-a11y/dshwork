# 调度说明：本专家只做调度，脚本由工作区 toolchain 提供

> 自 2026-11-16 起，**专家包内不再承载执行脚本**。包内 `references/` 只说明「调什么、怎么判、产物长什么样」；
> 真正被执行的是工作区的 `toolchain/run.py` + `skill-update/scripts/*`。

## 一、三条命令（全部经工作区 toolchain 调用）

```bash
# ① 标准抽取全链：route→clauses→merge→elements→rules→graph→slots→pack
python3 toolchain/run.py std.extract_standard --out <run> --text <标准文本> --standard <编号>
python3 toolchain/run.py std.run_graph       --out <run> --text <标准文本> --standard <编号> [--rules <手写规则>]

# ② 报告按被测项目拆桶（只按报告声明的方法配规则，禁止跨方法套用）
python3 toolchain/run.py std.split_analytes --out <run> --packs-dir docs/判定包

# ③ 分桶判定（从各项目原始记录抽 QC 实测值，与该桶谓词比较）
python3 toolchain/run.py std.bucket_judge --out <run> --records-dir <记录目录> [--nd-policy pass|unverifiable]
```

辅助：

```bash
python3 toolchain/run.py std.pack_split --out <run> --dest <目录> [--graph]   # 出 rules.jsonl + meta.json
python3 toolchain/run.py std.check_cross_clause --out <run> --text <标准文本>   # 查阈值是否跨条款
python3 toolchain/run.py std.run_contract --util verify --out <run> --node <n> # 门禁
python3 toolchain/which.py                                                    # 原子自检
```

## 二、调度顺序（与工作流图一致）

```
clauses → elements → rules → sop → toolchain → audit →（fix 循环）→ handoff
```

- `clauses` 由 `std.extract_standard` 一条命令跑完 8 步，产出 9 个文件 + `trail.jsonl`；
- `audit` 给 `VERDICT: fail` 时进 `fix`，修完重跑 `audit`，直到 pass；
- 每步过后跑门禁，不过不得标完成。

## 三、工作区不可用时怎么办

若当前会话没有工作区 `toolchain/`：

1. **不要伪造脚本或结果**；
2. 把缺口写成 `GAP-EXTERNAL`，说明"执行脚本不在本包内，需在工作区运行 `toolchain/run.py`"；
3. 仍可交付结构与判据：条款登记册、规则卡设计、判定口径，但**标注"未实跑"**。

## 四、产物与交付

| 产物 | 文件 |
|---|---|
| 条款登记册 / 引用登记册 | `01-clauses.json` |
| 要素包 / 公式卡 / 流程与依赖图 | `02-elements.json` |
| 规则卡（C1–C8 + 谓词 + 定位线索） | `03-rules.json` |
| SOP 图 | `sop-graph.json` |
| 槽位任务 / 类型 | `audit_tasks.jsonl` / `slots.schema.json` |
| 机器判定包 | `machine/sop-graph.packed.yaml` |
| 交付给审核专家 | `rules.jsonl` + `meta.json` + `manifest.json` |
| 执行留痕 | `trail.jsonl` / `run_state.json` |

## 五、两条红线（与判定口径一致）

- **ND 口径**：上限类阈值判 PASS，带 `verdict_basis=derived_from_ND`；下限类、未声明定义、单位不一致 → UNVERIFIABLE。详见 `nd-policy.md`。
- **方法族**：报告声明哪个标准号就用哪套规则；无规则集 → `PENDING_UPLOAD` + `NOT_APPLICABLE`，不得套用同被测物的其他方法。

---

## 九、接入新标准（通用口径，与本包已内置的 4 水标准无关）

> 本包对所有**环境监测**标准通用：抽取链不认标准号；判定链只认规则自己声明的 `requires`。

### 9.1 三步走

```bash
# ① 抽取（无手写规则时走自举，出结构骨架）
python3 scripts/run_graph.py --out <run> --text <标准.md> --standard <编号> --mode extract

# ② 结构质检（这两道门与标准无关，任何标准都适用）
python3 scripts/coverage_gate.py --packs <run> --std-dir <标准md目录> --waivers <豁免表> --strict
python3 scripts/check_threshold_support.py --packs <run> --std-dir <标准md目录> --strict

# ③ 判定（每条规则必须声明 requires，否则跳过并登记）
python3 scripts/judge_from_rules.py --packs <run> --docs <本批文档目录> --out <run>
```

### 9.2 新标准要补什么

| 补什么 | 文件 | 说明 |
|---|---|---|
| 规范字段 | `references/fields.yaml` | 39 个通用字段（校准/质控/适用域/样品/仪器/试剂/计算/记录）+ 介质特定（土壤/固废/空气/废气） |
| 规则 requires | 规则集 | 每条规则写 `requires: [QC.平行偏差]`；不写则只能做结构抽取 |
| 章节豁免 | `contracts/coverage_waivers.json` | 无判定要求的章（原理/术语/引用）逐章登记理由 |
| 值归一化 | `references/value_normalize.json` | 枚举同义词、单位换算、空值语义 |

### 9.3 判定器不认标准号（硬约束）

`judge_from_rules.py` 里**没有** `BIND`（标准→被测物）、**没有** `CONCEPT`（概念→关键词）：
字段抽取模式只来自 `fields.yaml`，规则通过 `requires` 声明依赖。
新增标准不需要改判定器代码，只要规则带 `requires`。

### 9.4 验证过的通用性边界

| 能力 | 状态 |
|---|---|
| 结构抽取（条款/要素/图谱/槽位） | ✅ 对任意环境标准成立（HJ700/HJ620 实测跑通） |
| 结构质检（章节覆盖/阈值回检/文档定位） | ✅ 与标准无关 |
| 判定 | ⚠️ 受规则质量约束：自举规则无 `requires` 时全部跳过，只能出结构 |

---

## 十、包的读取纪律（不让上下文被整包撑爆）

| 要做的事 | 用什么 | 成本 |
|---|---|---|
| 核对一句话/一个函数 | 直接 `read` / `grep` 落盘目录的单文件 | ~1 KB |
| 看包结构 | `ls` | ~0.5 KB |
| 整包内容核对 | **只在发布前做一次** | ~300 KB |

**禁止用「整包读取」接口去核对单点内容**——该接口无路径过滤，一次返回全部制作稿（含脚本源码）。
落盘目录（发布后）：`~/.agents/.workdsh-state/experts/presets/<id>/expert-package/`，可直接 grep。
