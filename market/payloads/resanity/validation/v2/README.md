# Resanity 分层验证协议

> 目录名和 schema 中的 `v2` 表示机械验证合同的第二代结构，不是 Resanity 产品版本。
> `suite.json` 是未预填结果的可复用协议模板，`result_status` 保持 `NOT_RUN`；
> 方法状态保持 `UNBENCHMARKED_CURRENT`。历史候选与运行产物留在 Git 历史，不进入当前发布树。

## 运行前冻结

每次候选运行必须记录：git commit、工作树状态、active locator、canonical Skill hash、active Skill hash、profile name/hash、宿主版本、精确模型、工具权限、as-of、预算和全部 prompt hash。身份不一致先停止，不补跑。

## 七层

### 1. core contract

使用封闭材料验证原子主张卡能否稳定区分“观察 / 可推出 / 不可推出 / 决策影响”。样本覆盖产品决策、政策执行和技术排障，非投资任务全部显式调用 Resanity。

阻断：把未观察事实写成 FACT；遗漏“不能推出”；结论不服从最弱主张；强制加入投资价格/载体语言。

### 2. investing profile

验证投资 profile 的经济暴露链、市场已定价层与 `WATCH_ONLY / NOT_EVALUABLE` 降级，不污染 core。

阻断：主题相关替代收入/利润/现金；无可靠价格或经济暴露仍制造 setup；遗漏可改写结论的官方披露。

### 3. open network

在真实网络中覆盖产品、政策与投资课题。所有承重事实核到一手/原始来源并保存快照；失败动作不自动重试。

阻断：越过 as-of、违反题目声明的来源资格、同源转载升级、把公司汇总指标拼成某产品或订单的同一血缘链、搜索失败后编造、模型自报宿主计量，或超过冻结预算。

### 4. anchor lifecycle

用三个独立工作区、每组两个连续全新会话覆盖 `active → refuted`、`active → realized` 与 `active → archived`，共 6 个案例。原命题和履历必须保留，代码只能读和提醒。

阻断：删除历史、自动改状态、非 active 仍提醒、把 realized 当作 refuted。

### 5. trigger

在真实 Codex 与 DSH 宿主运行 `suite.json` 的正反样本。投资研究应可隐式触发；显式非投资审计应触发；普通总结、编码、写作、翻译和一般问答不得触发。

trigger 题保留原始用户请求，不前置 Resanity 指令；runner 只添加不含候选方法名称的中性宿主预算说明。这样普通任务即使不加载 Skill，也知道同一冻结工具上限，预算失败不会因缺失宿主说明而混入触发判断。

阻断：任一普通任务被系统性抢占，或显式 Resanity 请求无法加载 canonical Skill。单个边缘措辞误判可记录为小问题，但不得形成类别性误触发。

### 6. install identity

在 Codex、DSH、项目副本、用户副本和 bundled 副本中验证遮蔽。以宿主实际 locator 为准，核对 canonical/profile hash。

阻断：验证文件与实际加载文件不一致仍返回成功；缺 reference 却宣称完整 profile；路径猜测覆盖宿主 locator。

### 7. final A/B

只在前六层通过后运行。使用同一冻结问题、as-of、宿主、模型、工具、预算和一次性失败政策：

- `B`：强通用研究提示，包含引用、as-of、反证和决策边界；
- `R`：canonical Resanity，按题选择 profile。

报告做身份遮蔽，人类先建立事实索引，再核验最承重三条主张。比较事实 P0、承重遗漏、决策效用、成本和触发污染，不奖励长度或格式。

最低入口：`suite.json` 中 `final_ab.case_ids` 的 8 个案例全部产生两臂原始产物；任一臂失败都计入，不自动重跑。完成前状态持续为 `UNBENCHMARKED_CURRENT`。

每个案例/臂保存 `task-prompt.md`、`arm-instruction.md`、`composed-prompt.md`、`report.md`、`sources/`、`host-receipt.json`、原始会话和 `skill-identity.json`。两臂使用完全相同、不含 Resanity 术语的中性 task prompt：B 臂只前置 `prompts/strong-baseline.md` 且环境中不安装 Resanity；R 臂只前置 `prompts/candidate-instruction.md` 并核对 canonical identity。不要给 B 臂暴露 Skill，也不要给任一臂暴露评分规则。

候选晋级线：8/8 两臂都有原始产物或如实失败；R 臂 identity/profile 与冻结版本 100% 一致；R 无事实 P0 负回归；至少 6/8 案例的决策效用优于 B；中位非缓存 token 不超过 B 的 1.25 倍。达标只允许说“当前协议在这组有限 A/B 中通过”，仍不证明 Alpha 或 PMF。

## 大问题与小问题

发布阻断：语义所有权越界、自动重试/补证据/行动、身份错配、类别性误触发、锚历史破坏、旧身份成绩冒充当前成绩、任何事实 P0 负回归。

允许记录后继续：不影响根结论的措辞/排版差异、可定位的 `MAJOR_NON_P0`、宿主显示路径但 hash 完全一致、最终 A/B 尚未运行（但必须保持 `UNBENCHMARKED_CURRENT`）。

## 当前能运行的机械检查

以下命令只在包含 `.git` 与内部 suites 的源码 checkout 中运行；npm tarball 故意不带内部 prompts：

```sh
python3 tools/validation_source_check.py
python3 tools/skill_identity.py --host generic --profile core
```

它们只验证源合同与身份；语义层和最终 A/B 必须由新鲜会话与独立评审完成。

单入口机械预检：

```sh
npm run validate:v2 -- --active-skill /actual/loaded/resanity/SKILL.md \
  --host codex --output /tmp/resanity-v2-mechanical-receipt.json
```

没有 `--active-skill` 时只核对 canonical 源，收据会明确标记安装身份未验证。可选的真实 Tushare 只读 smoke 必须显式传入新建请求文件；脚本不自动发现请求、不读取仓库历史临时文件，也不重试：

```sh
npm run validate:v2 -- --active-skill /actual/loaded/resanity/SKILL.md \
  --host codex --tushare-request /tmp/request.json \
  --tushare-output /tmp/observations.json \
  --output /tmp/resanity-v2-mechanical-receipt.json
```

入口始终保留 `semantic_layers=NOT_RUN`、`final_ab=NOT_RUN` 与
`method_status=UNBENCHMARKED_CURRENT`。它不能替代七层新鲜会话或人工盲评。

## 启动 8 案例最终 A/B

先做零模型 dry-run；它只核对 8 个案例、两臂提示、当前候选 hash 和 Codex CLI，不创建会话：

```sh
npm run validate:v2:ab -- --model gpt-5.6-sol
```

真实运行固定为 8 案例 × 2 臂 = 16 个全新会话。启动前先复制
`prelayers-receipt-template.json`，由人工基于前六层原始证据填写；只有六层均为
`PASS`、状态为 `PRELAYERS_PASS` 且 candidate Skill hash 与 core/investing/anchors/formal-audit
四个 profile hash 都与本次冻结身份一致时，
脚本才会运行。`evidence` 必须为六层各绑定一个绝对文件路径及其 SHA-256；脚本只核对
文件与 hash，不替人工判断语义是否通过。当前 DSH 预检存在阻断时不得把模板改成 PASS。

```sh
python3 validation/v2/run_final_ab.py \
  --run \
  --model gpt-5.6-sol \
  --reasoning-effort xhigh \
  --expected-skill-sha256 <64-hex-frozen-hash> \
  --prelayers-receipt /absolute/path/prelayers-pass.json \
  --output /absolute/new/path/resanity-final-ab
```

脚本为每个会话创建不含用户配置的临时 Codex home，只复制 `auth.json` 且运行结束即删除；
候选 Skill 从当前 npm tarball 安装到 R 臂独立项目工作区，B 臂同时检查项目和临时
home 中都不存在 Resanity。每个会话只启动一次，默认并发 2，失败不会自动重跑。
`operator/` 保存 arm 映射、精确提示、身份、原始 JSONL、宿主计量和工作区；
`review/` 只按 opaque arm id 保存报告与来源快照，供独立盲评。脚本只会返回
`COLLECTION_COMPLETE_AWAITING_BLIND_REVIEW` 或 `COLLECTION_INCOMPLETE`，不会判定哪一臂更好，
也不会改变 `UNBENCHMARKED_CURRENT`。

### 在 DSH headless 中启动同一组 A/B

DSH 使用独立入口 `run_final_ab_dsh.py`。先在同一个 `DSH_HOME` 中准备两个从同一
headless profile 复制出的 profile：`headless-baseline` 不得安装或激活 Resanity；
`headless-resanity` 只能比前者多一个 `resanity` dependency、末尾的 `resanity`
bundle 和由该 bundle 生成的顶层 `id: resanity` 配置项。脚本不会安装、复制或改写 profile。DSH 用户 Skill
`$DSH_HOME/skills/resanity/SKILL.md` 也必须不存在，否则两臂都会被污染。

在最终 A/B 前，用同一 B/R profile 运行 25 个一次性前置会话。其中 `T11-natural-investing-delivery` 保留自然投资提问，不显式提及 Resanity，用于人工复核自动触发、聊天内报告、否定语义、单边界、时态和唯一证据对象：

```sh
python3 validation/v2/run_dsh_prelayers.py \
  --run \
  --output /absolute/new/path/resanity-dsh-prelayers \
  --dsh-home "$DSH_HOME" \
  --baseline-profile headless-baseline \
  --candidate-profile headless-resanity \
  --active-skill "$DSH_HOME/profiles/headless-resanity/node_modules/resanity/SKILL.md" \
  --expected-provider deepseek-official \
  --expected-model deepseek-v4-pro \
  --expected-reasoning-effort max \
  --expected-skill-sha256 "$RESANITY_SHA"
```

采集器只返回 `HOST_COLLECTION_COMPLETE_AWAITING_SEMANTIC_REVIEW` 或机械不完整；它不生成
`PRELAYERS_PASS`。core、investing、open、anchor 必须人工审阅原始报告和工作区产物，
trigger 与 install identity 必须核对宿主收据。六层评审证据齐备后，才填写 v2 prelayers
收据并交给最终 A/B runner。

若一次完整前置采集已把失败收敛到少数明确根因，可以先做变更影响分析，再用
`--case` 重复指定受影响案例。定向运行必须绑定当前 identity、使用全新输出目录并保留
一次性失败；它是诊断证据，不得与旧 hash 的结果拼成当前同 hash 成绩：

```sh
python3 validation/v2/run_dsh_prelayers.py \
  --output /absolute/new/path/resanity-dsh-targeted \
  --case <case-id> \
  <其余冻结身份与宿主参数>
```

定向通过不等于六层重新取得同 hash 全量成绩，也不改变
`UNBENCHMARKED_CURRENT`。

先运行零模型 dry-run；把 provider、model 和 reasoning effort 填成 DSH 新会话原始
receipt 中实际出现的精确值：

```sh
export DSH_HOME=/absolute/path/to/your/dsh-home
export RESANITY_SHA='<64-hex-frozen-candidate-hash>'

python3 validation/v2/run_final_ab_dsh.py \
  --dsh-home "$DSH_HOME" \
  --baseline-profile headless-baseline \
  --candidate-profile headless-resanity \
  --active-skill "$DSH_HOME/profiles/headless-resanity/node_modules/resanity/SKILL.md" \
  --expected-provider deepseek-official \
  --expected-model deepseek-v4-pro \
  --expected-reasoning-effort max \
  --expected-skill-sha256 "$RESANITY_SHA" \
  --prelayers-receipt /absolute/path/prelayers-pass.json
```

只有 dry-run 返回 `DRY_RUN_READY` 才增加 `--run` 和全新的输出目录：

```sh
python3 validation/v2/run_final_ab_dsh.py \
  --run \
  --dsh-home "$DSH_HOME" \
  --baseline-profile headless-baseline \
  --candidate-profile headless-resanity \
  --active-skill "$DSH_HOME/profiles/headless-resanity/node_modules/resanity/SKILL.md" \
  --expected-provider deepseek-official \
  --expected-model deepseek-v4-pro \
  --expected-reasoning-effort max \
  --expected-skill-sha256 "$RESANITY_SHA" \
  --prelayers-receipt /absolute/path/prelayers-pass.json \
  --output /absolute/new/path/resanity-dsh-final-ab
```

每个案例/臂的 DSH session-persistence 根目录由一次性 patch 定向到自己的 artifact
目录；同一 patch 禁用 `llm-retry`、spawn/fork subagent 及依赖这些服务的工作流工具，
并为两个 profile 加载同一个只用于验证的 `resanity-validation-budget`
依赖。该外壳在工具体执行前机械拒绝超额调用，并在下一 step 移除耗尽的工具表面；
原始会话同时保留模型已发出但未执行的拒绝尝试，runner 分别记录 attempt 与
execution，预算以真实 execution 为准。该依赖必须在 B/R profile 中完全相同，
不得成为 Resanity treatment 的一部分。
并在一次性会话中关闭文件热加载 watcher、固定 Chokidar polling，避免 macOS FSEvents
句柄余量污染验证。脚本把合格 stdout 作为用户已收到的最终报告；若 stdout 缺失、只有过程说明或泄漏工具协议，但工作区已有 `REPORT.md`，脚本同时保留诊断副本并提升为 canonical `report.md`，标记 `report_origin=workspace_recovery` 和宿主交付失败。报告可用不等于宿主交付、审计或整臂成功。脚本保留
`raw-session.jsonl.zstd`、宿主签名、Skill 调用次数和来源快照，并逐案例核对两臂的
provider/model/reasoning/permission/tool catalog 是否相同。默认不把 `TUSHARE_TOKEN` 或
`RESANITY_CREDENTIALS` 传入会话；这组 8 案例评估研究方法，不替代 Tushare 专项验证。
只有明确要把市场数据能力纳入 treatment 时才可加 `--inherit-market-data-credentials`，
且必须在运行清单中保留这一差异。
