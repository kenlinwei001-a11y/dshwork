# 历史资产装配引擎 · 五形态边界与分层声明

> 本文档是知识处理 + 推演写作体系的架构收口声明。它明确「哪类能力属于哪种工程形态」、
> 「各层的职责与边界」，防止能力被塞进错误的形态、或跨越层级边界直接耦合。

---

## 一、五形态边界

所有能力必须归入以下五种形态之一，不得混用。判断标准：**「这个能力是确定性计算、还是语义判断、还是受控访问、还是规划决策、还是流程调度？」**

| 形态 | 职责 | 应该做 | 不应该做 | 现有实现 |
|---|---|---|---|---|
| **确定性代码** | 结构比对、字段校验、DAG 排序、版本比较、事务发布 | Schema Diff、拓扑排序、JSON Schema 校验、内容哈希、乐观锁 | 靠模糊语义自行判断复杂业务含义 | `schema_diff.py`、`contracts.py`、`orchestrator.topological_order` |
| **Skill** | 有明确输入输出契约的语义任务 | Claim 抽取、语义映射、证据关联、论证构建 | 绕过权限访问数据库、独立决定全局发布 | `claim-extraction-skill` 等 + `runtime.SkillRegistry` |
| **MCP** | 将授权后的资产/查询/函数/系统操作暴露为标准接口 | 查询资产、读取定义、调用函数、写入图谱 | 负责整个项目的流程规划与全局调度 | `kp-mcp`（48 工具） |
| **Agent** | 根据项目目标提计划、选路径、处理需推理的决策 | 提出任务计划、选择复用策略、处理语义歧义 | 无约束修改资产、绕过验证与审批 | 推演写作专家（`expert-a0a771c8b0da`） |
| **Workflow／规则引擎** | 调度、依赖、重试、审批、事务边界、质量闸门 | DAG 执行、依赖管理、审批分流、闸门拦截 | 自由生成无结构约束的执行流程 | `runtime.DAGRuntime` + `orchestrator` |

**核心红线（来自智演装配引擎文档）**：

- MCP 适合暴露「查询资产、读取定义、调用函数、写入图谱」，**不应把所有处理步骤都实现成 MCP 工具**。
- Schema Diff、DAG 拓扑排序、JSON Schema 校验 **必须用确定性代码**（可复现、可测试）。
- Claim 抽取、语义映射 **用 Skill 调 LLM**（有输入输出契约 + validator）。
- 历史资产检索 **通过 MCP 暴露受控接口**（不直接开数据库给 Agent）。
- 复用决策、影响分析 **用规则引擎 + 确定性代码**，不靠单个大模型凭直觉。

---

## 二、系统分层（六层）

```
┌─ 应用层        项目工作台 · 历史资产库 · 装配差异预览 · 审批与发布
│               → 推演写作专家（对话入口）、corpus-library（历史资产库）
├─ 编排层        Planner Agent · Workflow Orchestrator · DAG Runtime · Approval Workflow
│               → runtime.DAGRuntime、orchestrator、AssetPublisher（审批/回滚）
├─ 装配服务层    Schema Diff · Asset Resolver · Asset Assembler · Dependency Analyzer · Validation Engine
│               → schema_diff.py、library.py、instantiate.py、ontology_schema.py、validate.py
├─ 能力执行层    Skills · 函数执行器 · 规则引擎 · LLM Gateway · MCP Client
│               → runtime.SkillRegistry、domain_rules（规则）、kp-mcp（MCP Client）
├─ 受控工具接口层  Asset Registry MCP · Historical Knowledge MCP · Ontology Graph MCP · Reasoning Tools MCP · Report Runtime MCP · Governance/Audit MCP
│               → kp-mcp（合并部署，按权限域/数据域拆分工具组：library / processing / agent_access / reemit / ontology）
└─ 数据存储层    PostgreSQL · 图数据库 · 向量检索 · 对象存储 · Skill Artifact Registry
                → 当前：文件系统（corpus-library / project 目录），预留 DB/图/向量升级位
```

**分层原则**：上层只能调用下层；禁止跨层直连（如应用层直接读文件而不经 MCP/装配服务）。第一阶段多个确定性组件合并在同一进程（`corpus_pipeline` 包）中，保留模块边界与接口即可。

---

## 三、数据契约（显式，禁止散落 JSON）

装配各节点之间传递**结构化契约**，不允许只传自然语言。

| 契约 | 字段 | 现有实现 |
|---|---|---|
| `SchemaDiff` | added / removed / type_changed / renamed / semantic | `schema_diff.diff_schemas` |
| `ReuseDecision` | strategy / reason / modify_template | `schema_diff.decide_change_strategy` |
| `ImpactGraph` | 16 域 `{affected, action}` | `schema_diff.analyze_schema_impact` |
| `AssetPatch` | target_asset / operation / payload / base_version | `contracts.make_patch` |
| `AssemblyManifest` | project_id / based_on / reuse_mode / reused_assets | `instantiate` → `assembly_manifest.yaml` |
| `Bundle` | project_id / version / content_hash / published | `contracts.bundle_version` |
| `ValidationReport` | gate / undefined / replay_conflicts | `instantiate` → `gate_report.yaml` |
| `ReuseLineage` | corpus_node_id / project_node_id / status / note | `instantiate` → `reuse_lineage.yaml` |

**8 个操作类型**（`contracts.PATCH_OPERATIONS`）：`REUSE` / `PARAMETERIZE` / `ADD` / `MODIFY` / `MAP` / `DEPRECATE` / `REBUILD` / `REJECT`。

**硬约束**：
- 每个 `AssetPatch` 必须带 `base_version`（乐观锁，防并发覆盖）。
- 资产变更用明确操作，不允许 Agent 自由生成任意修改语句。
- 历史模板版本**不可被项目级装配直接覆盖**（`modify_template` 恒为 False）。

---

## 四、确定性主链路 vs LLM 辅助

**确定性主链路（零 LLM，可复现）**：

```
Schema Diff → Asset Resolver → Reuse Policy → Asset Assembler → Validation Engine → Asset Publisher
（schema_diff） （library）   （decide_strategy）（assemble_domain_changes）（validate+gate）（AssetPublisher）
```

**LLM 辅助（仅语义判断，且必须经 validator）**：

- 语义映射（`resolve_concept`，Ossie 概念字典命中，未命中交语义分类器）
- 语义分类（`semantic_classify`，默认确定性，Jev 预留 MCP 插槽）
- Claim 抽取/论证（Skill 调 LLM + 结构化输出 + 失败重试）

**可插拔对接的开源框架**（对齐格式，不硬编码）：

| 框架 | 用途 | 对接方式 |
|---|---|---|
| Apache Ossie | 语义对齐标准字典 | `import_ossie_yaml` / `export_ossie_yaml` |
| Jev（TypeSafe） | 语义分类决策模型 | `semantic_classify` 预留 MCP 插槽 |
| Semantica | 本体管理（OWL/SHACL/SKOS） | `ontology_schema` + `bootstrap_claim_ontology`（预留 `semantica_client`） |

---

## 五、边界红线（违反即缺陷）

1. **不裁决冲突**：冲突一律「待审」，不补数字、不改口径。
2. **借形不借值**：可继承骨架/推导逻辑/句式，一律不继承历史数值。
3. **缺值守卫**：`undefined` 节点不按 0 计算，写「待……后测算」并挂 gap。
4. **引用即绑定**：每处数值写 node 引用，不写字面量。
5. **未验证不标已证**：`status=unverified` 不得写成已验证/事实。
6. **不开放原文**：`chunks.jsonl`/`normalized.md`/`original` 永不返回字面数值。
7. **审批才发布**：`AssetPublisher.publish` 无审批人拒绝发布；`base_version` 过期拒绝并发覆盖。
8. **默认拒绝**：`check_access` fail-closed，未授权即拒绝。

---

## 六、验收标准（回归测试即验收）

每条验收标准都有对应测试（`corpus_pipeline/test_*.py`，17 个文件全部通过）：

1. 新增 `claims` → 识别新增字段 + 兼容性分析（`test_impact_analysis` / `test_domain_changes`）
2. 缺非必填字段 → 允许装配并记录缺失（`test_assembly_artifacts`）
3. 同名异义 → 不直接映射，`rebuild`（`test_contracts`）
4. Skill 不接受新字段 → 报 Schema 不兼容，不静默丢弃（`test_runtime` 输入校验）
5. 新增 Claim 无证据 → 保留 `unverified`，不升级为事实（`test_claim_schema`）
6. 新增字段影响多节点 → 完整影响清单（`test_impact_analysis` 16 域）
7. DAG 失败 → 不发布，下游跳过（`test_runtime` / `test_p2`）
8. 版本冲突 → `base_version` 过期检测（`test_contracts`）
9. 无权限 → 拒绝读取/复用（`test_runtime` / `test_contracts`）
10. 同输入同配置 → 等价结果（`content_hash` 确定性，`test_contracts`）
