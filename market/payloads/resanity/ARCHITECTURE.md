# Resanity 0.2 架构

> 代码版本：`0.2.1`（正式发行版）。精确验证状态与运行边界见 [`validation/v2/README.md`](validation/v2/README.md)。
> 工程通过、机械收据闭合、安装身份一致或有限 A/B 达线，都不等于研究效果、Alpha 或 PMF。

## 根原则

**模型拥有全部研究语义；确定性外壳只守不需要理解结论的机械边界。**

```text
用户问题
  ↓
canonical SKILL.md：原子主张协议 + 条件路由
  ├─ references/investing.md      投资 profile
  ├─ references/anchors.md        锚生命周期
  └─ references/formal-audit.md   正式机械审计
  ↓
模型：观察 → 可推出 → 不可推出 → 决策影响
  ↓
用户可读研究报告（第一交付物与语义真相）
  ├─ 可选持久化为 report.md
  └─ 可选机械审计：hash / as-of / 引用 / 血缘 / 预算 / 安装身份
```

当前架构不把长篇投资格式、锚持久化或正式收据放进所有请求的热路径，但每次研究都必须交付最小可读报告。是否加载某个 reference，由本次问题决定。

## 语义所有权

| 内容 | 所有者 | 代码是否可改 |
|---|---|---|
| 问题定义、假设、可能性地图 | 模型 | 否 |
| 原子主张卡及证据标签 | 模型 | 否 |
| 结论、反例、下一验证 | 模型 | 否 |
| 锚命题与 active/refuted/realized/archived 状态 | 模型与用户 | 否 |
| 文件 hash、引用是否闭合、声明的来源日期/覆盖期是否满足 as-of | 外壳 | 只读检查 |
| 声明的来源血缘、预算、宿主计量 | 外壳 | 只读检查 |
| active locator、canonical/profile hash | 外壳 | 只读检查 |

如果一条规则需要理解“结论说得对不对”，它属于模型或验证 rubric，不属于外壳。

## 数据源选择边界

模型按主张类型判断监管原件、发行人披露、结构化行情、聚合页或实时网页是否有资格承重，并负责解释来源对结论的意义。确定性代码不得把“取得更方便”解释成“证据等级更高”。

`scripts/free_market_observations.py` 只对 A 股日线自动采集执行一次操作选择：本地可用时按 `TUSHARE > BAOSTOCK > AKSHARE_TENCENT` 选择，显式降级必须记录原因。选择不探测网络，采集失败不自动回退；请求、数据包和采集回执绑定同一 `provider_policy`。这是一条可复核的数据获取策略，不生成主张、不改变证据边界，也不替代交易所、监管或发行人原件。

## canonical Skill 与 profiles

仓库根目录的 `SKILL.md` 是唯一 canonical Skill。它只包含保守触发边界、原子主张卡协议、证据不变量、reference 路由、输出模块和禁止事项。

profiles 是条件加载文件的机械组合，不是第二个 Skill，也不是语义状态：

- `core`：只含 `SKILL.md`；
- `investing`：core + `references/investing.md`；
- `anchors`：core + `references/anchors.md`；
- `formal-audit`：core + `references/formal-audit.md`；
- 组合 profile：按需合并相应 references。

`tools/skill_identity.py` 对上述有序文件清单做规范化 hash。profile hash 只证明本次加载了哪组方法文件，不评价输出语义。

## 触发策略

- 投资研究可以隐式触发，因为投资 profile 是已有产品能力。
- 非投资任务只有在用户明确说 Resanity、可能性地图、承重主张审计或更新锚时才触发。
- 普通总结、编码、写作、翻译和一般问答不触发。

这些规则依赖 Skill metadata 与宿主选择，不能由仓库代码伪装成确定性分类器。`validation/v2` 冻结正反触发样本，必须在真实宿主中验证。

## 安装身份与遮蔽

正式验证必须同时冻结：

1. 宿主实际返回的 `active_locator`；
2. canonical `SKILL.md` hash；
3. active `SKILL.md` hash；
4. 本次 profile hash；
5. active 副本的 profile hash。

宿主报告的实际 locator 优先于路径猜测。没有宿主 locator 时，身份工具按显式候选顺序解析：项目副本 > 用户副本 > portable/bundled 副本。DSH bundled provider rank 仍允许本地/项目同名 Skill 遮蔽；Codex 或其他宿主也必须以它们实际返回的 locator 为准。

任何 active/canonical/profile 不一致都失败关闭。它只阻断“正式验证结果可归属于该方法版本”，不阻断用户在清楚边界下阅读普通回答。

## 锚生命周期

锚只有四种语义状态：`active`、`refuted`、`realized`、`archived`。只有 `active` 参与日期提醒。

插件与 `tools/anchor_check.py` 只读取状态和日期、跳过非 active 锚、把错过日期保持为 overdue，并在用户显式启用系统通知时提醒。它们不更新状态、不移动日期、不创建锚、不删历史。默认系统通知关闭。

## 正式审计

报告交付与机械审计是两条独立轴。未知、未闭合、`INSUFFICIENT`、文件写入失败或审计失败都不能阻断报告；它们只能作为报告内容或审计披露。用户要求保存时先写 `report.md`，再生成来源快照和收据。最终回答中的完整报告是文件失败时的保底交付，不建立 `formal_report_allowed`、收敛终态或候选晋级状态。

`tools/research_check.py` 接受 `resanity.audit-receipt.v2`，并检查：

1. canonical/active Skill 与 profile hash；
2. 报告、提示、来源快照和宿主收据 hash；
3. 主张时态、来源日期依据/覆盖期与报告 as-of 的兼容矩阵；
4. `[C#]` / `[E#]` 引用闭合；
5. 声明的上游 lineage、`NO_RESULT` 范围和 `INSUFFICIENT` gap；
6. 宿主计量与预声明预算。

`AUDIT_RECEIPT_OK` 只表示这些机械字段闭合。检查器不读取主张含义，不生成修复，不运行搜索，也不自动重试。

## 验证分层

当前验证协议使用七层，详见 `validation/v2/README.md`：core contract、investing profile、open network、anchor lifecycle、trigger、install identity、same-hash final A/B。路径和 schema 中的 `v2` 表示机械合同代际，与产品版本 `0.2.1` 无关。源码树只保留可复用协议；历史运行证据留在 Git 历史。

## 发布门槛

发布阻断的大问题：

- 代码理解、生成或改写研究语义；
- 自动补证据、重试、晋级或外部行动；
- 非投资普通任务被广泛抢占；
- active/canonical/profile 身份不一致仍可进入正式评分；
- refuted/realized/archived 锚仍被当作 active 提醒；
- 旧版本或不同身份的结果被表述为当前成绩；
- 工程通过被表述为研究有效、Alpha 或 PMF。

可接受但必须记录的小问题：非关键措辞/排版差异；不影响 identity/hash 的路径展示差异；不改变根结论和行动的 `MAJOR_NON_P0`；未完成真实 A/B，因此不得宣称当前版本已完成研究有效性基准测试。

0.2.1 的发布门槛只接受当前 checkout、当前 Skill/profile hash 和当前宿主身份产生的结果。工程测试与机械源检查必须通过，但不能替代同版本、独立完成的研究有效性验证；历史候选记录不随当前发布树分发，也不能替代新的完整 A/B。

## 明确不做

- 研究状态机、候选晋级或语义数据库；
- 以证据收敛、文件写入或审计闭环作为报告资格闸门；
- 固定多 Agent 编排或自动 Judge；
- 自动交易、订单、仓位、目标价或回报承诺；
- 以机械合同通过替代真实用户价值验证。
