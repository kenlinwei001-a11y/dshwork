# 技能：math-modeling

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | math-modeling |
| description | 当用户要求数学建模、建模竞赛、建模分析、代码求解、结果可视化或生成数学建模论文时使用。支持完整三阶段流程、单独执行任一角色，以及在关键节点使用独立 Subagent 进行阶段内质检；默认只启用质检 Subagent，用户可明确选择额外协作。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/math-modeling |
| 所属插件 | （非插件内置） |
| 文件数 | 106 |
| 体积 | 869.4 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：**未被范围内专家配备**
- 全部专家引用（含范围外）：无

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: math-modeling
description: 当用户要求数学建模、建模竞赛、建模分析、代码求解、结果可视化或生成数学建模论文时使用。支持完整三阶段流程、单独执行任一角色，以及在关键节点使用独立 Subagent 进行阶段内质检；默认只启用质检 Subagent，用户可明确选择额外协作。
---

# 数学建模

本 Skill 用三个独立角色完成数学建模。生成的论文仅供用户参考，不作为可直接提交的作品。论文结构与格式必须以目标竞赛当届官方规则和官方模板为准，不能用往届经验替代官方要求。

**使用前**：请先阅读根目录 `使用指南.md`，明确本 Skill 的交付物使用边界，并把它复制到工作区（`PROJECT_ROOT`）：

**PowerShell（Windows）：**
```powershell
Copy-Item "<SKILL_ROOT>\使用指南.md" "<PROJECT_ROOT>\使用指南.md"
```

**bash（macOS/Linux）：**
```bash
cp "<SKILL_ROOT>/使用指南.md" "<PROJECT_ROOT>/使用指南.md"
```

> `<SKILL_ROOT>` 是本 Skill 的安装目录（含 `SKILL.md` 的目录），`<PROJECT_ROOT>` 是你的题目/项目目录。

## 强制执行协议

用户明确点名本 Skill 或任务命中本 Skill 时，严格执行以下协议；不要把它降级为建议：

1. 在首次进度更新中回显：已激活本 Skill、`SKILL_ROOT`、`PROJECT_ROOT`、当前阶段、目标竞赛与届次、计划读取的角色和工具入口。未确认的官方规则明确标为待核验。
2. 开始每个阶段前，实际读取该角色的 `SKILL.md`；使用 PDF、Excel、论文搜索、DOCX 或 LaTeX 时，再实际读取对应工具的 `SKILL.md`。知道文件路径不等于已经执行。
3. 严格调用 Skill 提供的脚本和模板。已有初始化、转换、编译或校验工具时，禁止为了省时手写替代实现。
4. 把任何校验预警视为未完成。只有当届官方规则或用户明确要求允许偏离时，才能记录“规则来源、偏离项、理由”后继续；不得自行降低篇幅、图表、公式、引用或编译质量目标。
5. 环境缺少引擎、搜索源、渲染器或依赖时，报告阻塞并继续完成仍可验证的部分；禁止静默换工具、跳过验证或用较差产物冒充完成。
6. 运行环境支持 Subagent 且任务会生成或修改固定交付物时，按 `references/Subagent调度.md` 在关键节点立即派发独立质检；禁止等全流程结束后才首次派发，作者自检不能替代独立验收。除固定质检外，不主动派发其他 Subagent；仅在用户明确启用具体协作任务时按所选范围执行。
7. 交付前运行当前角色规定的全部完成门禁。任一命令未运行、退出码非零、独立验收未通过、仍有未处理问题或产物在门禁后发生变化时，不得声称“已完成”。
8. 真实竞赛或其他有明确截止时间的任务，必须读取 `references/交付与截止时间协议.md`，核验当届官方截止时间与提交约束，尽早走通完整导出链路并维护可立即提交的 Checkpoint V1；后续优化不得破坏该版本。
9. 最终回复列出实际读取的入口、实际运行的关键命令、退出码、Subagent 门禁状态、核心质量指标和仍存在的阻塞；不得只说“已检查”。

## Subagent 默认策略与阶段门禁

- 默认模式只派发 `M1/P1/P2/W1/W2` 质检 Subagent；调研、原型和并行实验等可选协作默认关闭，不询问、不暂停流程。
- 用户可用自然语言启用一个或多个可选任务，也可随时关闭；未明确选择的类别保持关闭。
- 主 Agent 负责调度和权威产物写入；质检 Subagent 必须未参与被审产物的编写或修正，默认只读并返回证据。
- 完整流程依次通过 `M1` 建模终检、`P1` 最小可运行结果、`P2` 编程终检、`W1` 证据大纲和 `W2` 论文终检。`P1` 通过后才能全量计算与正式出图，`P2` 通过后进入论文规划，`W1` 通过后才开始长篇正文和双格式排版。
- `FAIL` 必须按证据返回对应角色修正并复验；被审产物发生实质变化时，相关 `PASS` 立即失效。
- 单阶段任务只运行对应门禁。环境不支持 Subagent 时，只能标记为 `BLOCKED` 或受限交付并明确报告“独立验收未完成”，不得把主 Agent 自检描述为独立通过或声称完整完成。

详细的默认开关、可选协作任务、派发输入、固定回执和并行边界见 `references/Subagent调度.md`。

## 根目录契约

- `SKILL_ROOT`：本文件所在目录，只读。角色说明、算法资料、脚本和模板都从这里读取。
- `PROJECT_ROOT`：用户题目和项目所在目录，所有新产物只能写入这里。
- 两个根目录必须不同；默认禁止覆盖 `SKILL_ROOT` 内任何文件。
- 输入附件只读。确需修改模板时，先复制到 `PROJECT_ROOT` 再处理。

## 路由

| 用户意图 | 加载入口 | 是否要求前一阶段已完成 |
|---|---|---|
| 完整建模、完成整题 | `references/roles/建模手/SKILL.md` → `references/roles/编程手/SKILL.md` → `references/roles/论文手/SKILL.md` | 按顺序执行 |
| 只做题目分析、选模型 | `references/roles/建模手/SKILL.md` | 否 |
| 只写代码、跑结果、出图 | `references/roles/编程手/SKILL.md` | 需要题目和可执行的模型说明；缺失时先补齐必要分析 |
| 只写或修改论文 | `references/roles/论文手/SKILL.md` | 需要题目、模型、真实运行结果和图表；缺失时回退到对应阶段 |

不要在单阶段任务中强制执行完整流程。

## 固定交付物

### 建模手

只交付：

1. `题目分析报告.md`
2. `术语表格.md`

### 编程手

交付：

1. 可运行的 Python（`.py`）或 MATLAB（`.m`）代码；可同时交付两种语言。
2. 代码运行结果表格，如 `.csv`、题目要求的 `.xlsx`。
3. 原始数据图、模型运行过程图、模型最终结果图每类至少 3 张候选图，合计至少 9 张；还必须覆盖题目全部子问题，每个子问题在三类中各至少 1 张。文件名使用 `raw_q1_*`、`process_q1_*`、`result_q1_*` 等格式，不设上限。相同内容的 SVG、PNG 和灰度预览按 1 张逻辑图计数。
4. **必须至少 1 幅总体建模流程图**，覆盖输入、子问题依赖、模型、求解、验证与输出；子问题存在独立分支、循环或三步以上求解链时，补充对应子问题流程图。文件名使用 `flow_overall_model.*`、`flow_qN_model.*`，与三类候选图分开计数，不替代结果图。
5. `results/复现清单.json`，含随机种子、输入文件 SHA-256、运行时和依赖版本、关键参数、唯一复现命令。

### 论文手

默认交付 Word 论文；用户显式要求时才生成 LaTeX 论文。

- Word：`完整论文.docx`；由 LaTeX 转换时同时保留哈希绑定的 `.conversion.json`。
- LaTeX（可选）：`完整论文-LaTeX/` 源码项目、由其实际编译得到的 `完整论文.pdf` 和哈希绑定的 `.build.json`。

用户明确要求 LaTeX 时，同时生成两种格式且正文内容、数据、图表和结论保持一致。内部检查记录不作为额外交付物。

无论目标竞赛为何，论文默认至少包含 8 幅正式图；当届官方规则或用户明确要求与此冲突时，以其要求为准并记录依据。

## 阶段反馈闭环

- 任一 Subagent 门禁返回 `FAIL` 时，按回执中的文件、命令、数值或来源证据回到对应角色；修正后重跑受影响门禁，不得由主 Agent 口头覆盖。
- 编程手发现公式不完整、约束冲突或模型不可实现时，停止猜测，在对话中列出证据并回到建模手修正两个 Markdown 交付物。
- 论文手发现关键结论没有真实结果、图表或文献支撑时，回到编程手或建模手补齐，禁止编造。
- 修正后从被阻断阶段继续，不重复已通过的阶段。

## 建模约束

1. 先完整理解题目、附件、目标、约束和评价口径，再形成结论与模型方案。
2. 每道子问题最多使用两个独立模型体系。物理题中，同一控制方程或同一物理机制在不同近似阶次、边界条件或精度下的展开，计为一个模型族，不机械拆成多个模型；只有控制机理、状态变量或求解目标实质不同才另计模型。辅助的灵敏度分析、误差检验和可视化不计作独立模型。
3. 避免直接套用过于常见的简单模型来冒充创新；创新必须来自问题结构、数据处理、约束设计、算法改进或验证方式，并说明依据。
4. 数据判定标准按题目、官方规则、领域文献或数据分析结果确定。
5. 不因两个模型得到相近结论就强制删除其中一个；是否保留由研究目的和证据价值决定。

## 渐进式加载

先读当前阶段的 `SKILL.md`，再按其中“何时加载”表读取所需参考，禁止一次性加载全部资料。

| 当前任务 | 额外读取 |
|---|---|
| 选模型或查算法 | `references/算法索引.md`，再读取一个或少数几个相关 `assets/*.md` |
| 搜索论文 | `tools/paper_search/SKILL.md` |
| 读取题目 PDF | `tools/pdf/SKILL.md` |
| 处理 Excel | `tools/xlsx/SKILL.md` |
| 画图 | `tools/figure/SKILL.md` |
| 生成 Word 论文 | `tools/docx/SKILL.md` |
| 生成 LaTeX 论文 | `tools/latex/SKILL.md` |
| LaTeX 论文转 Word | `tools/docx/SKILL.md` |
| 派发 Subagent 或阶段质检 | `references/Subagent调度.md` |
| 真实竞赛、截止时间或最终提交 | `references/交付与截止时间协议.md` |

完整导航见 `references/README.md`。

## 完成判定

- 先满足“强制执行协议”，并提供可复核的门禁结果。
- 声称完整完成时，当前任务涉及的独立 Subagent 门禁均为 `PASS`，且通过后产物未发生未经复验的实质变化；缺少 Subagent 能力时只能报告 `BLOCKED` 或受限交付。
- 所有计算结论来自实际运行结果。
- 公式、表格和图表与代码结果一致。
- 引用可由 OpenAlex、AnySearch 或原始出版页面追溯。
- 论文已按目标竞赛当届官方规则配置，篇幅目标已经确认，公式/非空图表数量与全部子问题图覆盖经过检查，图表编号与正文引用连续，参考文献与正文引用双向对应。Word 分支还须通过原生 OMML、DOCX 结构、转换警告门禁和渲染页数检查；LaTeX 分支还须通过环境诊断、真实编译、日志、权威资源—源码—PDF 哈希绑定、正文与附录页数、空白页、页面尺寸、字体嵌入和图片 DPI 检查。
- 所有产物位于 `PROJECT_ROOT`，`SKILL_ROOT` 未被改写。
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| .github/workflows/update-star-history.yml | 872 | 123e11072a52e661 |
| .gitignore | 79 | 60cf3c74225281d1 |
| CHANGELOG.md | 35856 | 65915d0787499d2f |
| README.md | 16225 | 373015cf34ffe858 |
| SKILL.md | 10755 | 3cbb7985e91d97ce |
| VERSION | 6 | 64d23f858ef51b0f |
| assets/README.md | 9339 | 12688aeb56346fa8 |
| imgs/star-history.json | 9222 | 23deff86c41e95a3 |
| imgs/star-history.svg | 7388 | eeca09a93e05333a |
| references/README.md | 2139 | 41208ab34ec51368 |
| scripts/sync_dsh_plugin.py | 7471 | 7b3781ff35cffb4b |
| tests/test_delivery_protocol.py | 2215 | feea1fb67ce9a28f |
| tests/test_docx_tools.py | 2684 | 92ec737e547e766a |
| tests/test_equations.py | 11399 | 349d869f466e2cf4 |
| tests/test_figure_tools.py | 12880 | c1b5dd43dbd9e043 |
| tests/test_latex_paper.py | 41980 | 292d2e1c3c30e3e1 |
| tests/test_paper_format.py | 8163 | 8652d8ba103b7940 |
| tests/test_paper_search.py | 6823 | 288b91c6daa4d756 |
| tests/test_recalc.py | 1798 | 0b9060d40e3152c7 |
| tests/test_reproducibility.py | 2796 | d6eb17008d4d6273 |
| tests/test_star_history.py | 2383 | 50cd0af8a6f9f7c2 |
| tests/test_subagent_protocol.py | 3046 | f405ccf9908713bb |
| tests/test_xlsx_read.py | 1307 | 8fb66e9c3d75618d |
| tools/docx/LICENSE.txt | 1467 | 79f6d8f5b427252f |
| tools/docx/SKILL.md | 6764 | f81aa71a841ed285 |
| tools/docx/scripts/__init__.py | 1 | 01ba4719c80b6fe9 |
| tools/docx/scripts/accept_changes.py | 4981 | 735646d6f2376ef7 |
| tools/docx/scripts/check_env.py | 972 | 0c6fd7a2cad7da59 |
| tools/docx/scripts/comment.py | 11496 | f17900815781c0c5 |
| tools/docx/scripts/equations.py | 51095 | b822831e5c7c0df2 |
| tools/docx/scripts/inspect_template_format.py | 7400 | 1ac06042f92e28d0 |
| tools/docx/scripts/office/helpers/__init__.py | 0 | e3b0c44298fc1c14 |
| tools/docx/scripts/office/helpers/merge_runs.py | 5567 | 7c40ed838b88639c |
| tools/docx/scripts/office/helpers/simplify_redlines.py | 5754 | 560cb55978a834c5 |
| tools/docx/scripts/office/pack.py | 4991 | b1800987e568261a |
| tools/docx/scripts/office/soffice.py | 5380 | 0c1d10d9465feff5 |
| tools/docx/scripts/office/unpack.py | 4052 | 83f69cecc8791018 |
| tools/docx/scripts/office/validate.py | 3902 | c2333bef79104ecc |
| tools/docx/scripts/office/validators/__init__.py | 336 | 83e0f035c5abea23 |
| tools/docx/scripts/office/validators/base.py | 35067 | a9f6ad2d007794a1 |
| tools/docx/scripts/office/validators/docx.py | 16376 | 0ef04ce86b2e6b6a |
| tools/docx/scripts/office/validators/pptx.py | 9824 | f937961e62a5fa0d |
| tools/docx/scripts/office/validators/redlining.py | 8918 | f4c33fdb9da0651d |
| tools/docx/scripts/paper_format.py | 20379 | d046ff7e27294bda |
| tools/docx/scripts/self_check.py | 4308 | 536046c262fbb734 |
| tools/docx/scripts/templates/comments.xml | 2603 | a08ba83ee8790ac9 |
| tools/docx/scripts/templates/commentsExtended.xml | 2611 | 544eeecfeceed4b4 |
| tools/docx/scripts/templates/commentsExtensible.xml | 2707 | bad10b3283e6ad6e |
| tools/docx/scripts/templates/commentsIds.xml | 2619 | db20f9616e004ec4 |
| tools/docx/scripts/templates/people.xml | 115 | 056f63aa1197fd8c |
| tools/figure/SKILL.md | 13010 | 540e6b1ada2f6c6a |
| tools/figure/references/api-templates/api.md | 8885 | 22306e56fcc4c6d1 |
| tools/figure/references/api-templates/plot_recipes.md | 25038 | dc0209b9d6f436a5 |
| tools/figure/references/api-templates/template_catalog.md | 3858 | d0d9d9fba4d6e223 |
| tools/figure/references/chart-types/chart_selection.md | 15579 | d830e922c6b17416 |
| tools/figure/references/chart-types/chart_types.md | 7001 | 3d81372103c400e4 |
| tools/figure/references/chart-types/flowchart.md | 3427 | b2bd70f115354e29 |
| tools/figure/references/design/common_patterns.md | 8079 | 46c408a97f093bd4 |
| tools/figure/references/design/design_theory.md | 15913 | 5b5ec4e3aed2b51a |
| tools/figure/references/design/viz_pitfalls.md | 17149 | 36293fd60e50ac2c |
| tools/figure/references/guides/asset_adaptation.md | 3785 | 5535fa0b376262a6 |
| tools/figure/references/guides/data_profiling.md | 8566 | ec2f87a5a09db0db |
| tools/figure/references/guides/figure_contract.md | 4590 | 7c69c2f6c03157d2 |
| tools/figure/references/guides/figure_legend_conventions.md | 2347 | 0b1d8a8b5ffd0519 |
| tools/figure/references/guides/nature_2026_observations.md | 3049 | c141fdfcc0247b88 |
| tools/figure/references/guides/tutorials.md | 7456 | fcad4ee2f09e4524 |
| tools/figure/references/quality/journal_specs.md | 7428 | a8e9654f55994d69 |
| tools/figure/references/quality/publication_checklist.md | 6217 | 3eb979927e88e139 |
| tools/figure/references/quality/qa_contract.md | 2556 | 9806b5ce99aa0628 |
| tools/figure/references/quality/visual_review.md | 7330 | c4ca4a28a315e7de |
| tools/figure/scripts/check_figure.py | 9709 | 861191858ff47c5a |
| tools/figure/scripts/export_figure.py | 6450 | 40ce3bcd31dfc4b3 |
| tools/figure/scripts/layout_tools.py | 9351 | 68e1d25774148fe7 |
| tools/figure/scripts/profile_data.py | 17764 | d8a2a72c2607c390 |
| tools/figure/scripts/setup_style.py | 11794 | d58ef81684577bb6 |
| tools/figure/scripts/style_constants.py | 7098 | d574969063fc1fb0 |
| tools/figure/scripts/validate_figure.py | 19402 | 1886d3cb050c9e0e |
| tools/figure/scripts/visual_qa.py | 12677 | 67675709e523c76e |
| tools/figure/static/core/contract.md | 3941 | 17314f0914712ce0 |
| tools/figure/static/core/stance.md | 3371 | 46d1a49608ccf240 |
| tools/latex/SKILL.md | 8872 | 0b7486727a8593e5 |
| tools/latex/assets/templates/cumcm/main.tex | 845 | d606c76d66e26729 |
| tools/latex/assets/templates/cumcm/references.bib | 66 | c85fa9f8c7cdb3b0 |
| tools/latex/assets/templates/mcm-icm/main.tex | 848 | de74c3cdd704c9a8 |
| tools/latex/assets/templates/mcm-icm/references.bib | 51 | c0401239e1bf74dc |
| tools/latex/scripts/latex_paper.py | 65793 | b8b0f4bf9e7901ce |
| tools/paper_search/SKILL.md | 1921 | 3cf7a34e9762eedf |
| tools/paper_search/scripts/anysearch_academic.py | 10562 | 736b35d909fa6925 |
| tools/paper_search/scripts/hybrid_scholar.py | 23245 | a07e7638f8a27d61 |
| tools/paper_search/scripts/openalex_scholar.py | 14683 | 5070c2e52a6ba855 |
| tools/pdf/LICENSE.txt | 1467 | 79f6d8f5b427252f |
| tools/pdf/SKILL.md | 8072 | 6c29abbce8b2dd34 |
| tools/pdf/forms.md | 11854 | 9530b3f57034792e |
| tools/pdf/reference.md | 16692 | 03a5f964f8abecbb |
| tools/pdf/scripts/check_bounding_boxes.py | 2774 | 0ced522402dd7b3c |
| tools/pdf/scripts/check_fillable_fields.py | 268 | 1fe10b9980a5493c |
| tools/pdf/scripts/convert_pdf_to_images.py | 1008 | 7f58e292a67e18a8 |
| tools/pdf/scripts/extract_form_field_info.py | 4300 | bb235b36f497bbb1 |
| tools/pdf/scripts/extract_form_structure.py | 3945 | 6814e3fe8f78c2b1 |
| tools/pdf/scripts/fill_fillable_fields.py | 3819 | d140872c2e92e41b |
| tools/pdf/scripts/fill_pdf_form_with_annotations.py | 4118 | 8c321928a3b7b974 |
| tools/update_star_history.py | 6388 | 56edb26ec75ed274 |
| tools/xlsx/LICENSE.txt | 1467 | 79f6d8f5b427252f |
| tools/xlsx/SKILL.md | 2325 | 582e00a939b2d3ca |
| tools/xlsx/scripts/read_rows.py | 896 | ab15b3bd0d0c9b36 |
| tools/xlsx/scripts/recalc.py | 4690 | 950e427a07f6c66c |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/math-modeling/`（未改写；已用 SHA-256 复算校验）。
