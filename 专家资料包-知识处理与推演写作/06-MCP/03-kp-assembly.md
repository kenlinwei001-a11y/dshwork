# MCP 连接：kp-assembly

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 配置

| 字段 | 值 |
|---|---|
| 显示名 | kp-assembly |
| 连接 key | custom-kp-assembly |
| connectorId | __custom__ |
| serverName | kp-assembly |
| 传输 | stdio |
| 端点 | stdio · /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python |
| 启用状态 | true |
| 注入模式 | 始终注入 |
| 作用域 | 全局 |
| 鉴权模式 | none |
| 连接策略 | inherit |
| 健康状态 | healthy |
| 最近成功检查 | 2026-10-13T07:33:04.875Z |
| 诊断码 / 说明 | ok · 最近一次可用性检查通过 |

## 2. 该 server 的业务角色

语料包装配与成包（契约文件组装、清单与索引）

## 3. 工具清单（16 个）

| 公开工具名（publicName） | 工具名 | 说明 |
|---|---|---|
| mcp__kp-assembly__check_number_consistency | check_number_consistency | 写作查数：核实正文数字与事实源一致，检测前后不一致与口径存疑 |
| mcp__kp-assembly__schema_diff | schema_diff | Schema 结构差异分析：新增/缺失/类型变化/改名 + 语义分类 |
| mcp__kp-assembly__bootstrap_ontology | bootstrap_ontology | 从新旧 Schema 差异生成 16 域可执行装配变更集（本体/论证链/任务DAG/规则/Skill/表单/提示词/质量闸门/复用策略/实体关系） |
| mcp__kp-assembly__check_requirements | check_requirements | 需求完备性检查：对比已提供事实与必需变量，输出缺失清单（不编造） |
| mcp__kp-assembly__sensitivity_analysis | sensitivity_analysis | 敏感性分析：对输入变量做 ±Δ 扰动重算派生值，识别敏感变量（哪些变量变化显著影响结论） |
| mcp__kp-assembly__validate_shacl | validate_shacl | SHACL 约束执行：检查节点是否符合本体约束（枚举/必填），输出违规清单 |
| mcp__kp-assembly__project_where_written | project_where_written | 查节点在本项目已写草稿中的位置（project/drafts/node_mentions.jsonl） |
| mcp__kp-assembly__wp_get_facts | wp_get_facts | 工作包 facts 分页（facts>30 时编排器按页拉取；未落盘工作包时按 section 过滤图谱事实分页） |
| mcp__kp-assembly__instantiate_project | instantiate_project | 新项目图库实例化：输入新事实 + 借用语料规则/推导链/风格，输出重绑定图库（借形不借值、缺值守卫、回放检矛盾） |
| mcp__kp-assembly__build_work_package | build_work_package | 编排器组装章节工作包（outline/facts≤30/claims/conflicts/undefined/返回契约，落盘 project/work_packages/<section>.json） |
| mcp__kp-assembly__gate_check_draft | gate_check_draft | 编排器草稿闸门（由编排器调用，非 Agent 自评）：查字面数值、undefined 引用、must_cover 缺项，返回 verdict |
| mcp__kp-assembly__impacted_assets | impacted_assets | 资产依赖图影响传播：给定变更资产，沿依赖图返回受影响的下游资产（取代按域静态判断） |
| mcp__kp-assembly__decide_reuse | decide_reuse | 复用决策：根据新旧 Schema 差异决定 7 种复用策略之一（直接复用/参数化/向后兼容扩展/依赖联动/分支/重建/拒绝） |
| mcp__kp-assembly__run_quality_gates | run_quality_gates | 三质量关口 QG1/QG2/QG3：来源可信度/语义完整性/资产可复用性，返回汇总与失败关口 |
| mcp__kp-assembly__assess_capability | assess_capability | 知识≠能力评估：区分「归纳的候选方法」与「登记的真实能力」，含候选缺口时 actionable=False |
| mcp__kp-assembly__validate_source_anchor | validate_source_anchor | 校验 SourceAnchor 定位完整性（document_id 必填 + table_cell/char 精确定位） |

## 4. 使用方式

- 在会话/项目的连接器选择中选中该连接后，Host 在 agent/created 生命周期开放对应 mcp__ kp-assembly __* 命名空间。
- 项目「团队知识库」以连接器 kp-mcp（知识处理工具层）的形式引用了知识处理工具层；实际展开为上述 server。
- 没有连接选择时，这些工具不出现在模型的工具面上。

## 5. 边界

- 本包不采集、不保存任何凭据或本机密钥。
- 工具是否存在与工具是否被授权调用是两件事：策略（Tool > Server > Connection）与会话可见性逐层生效。
