# evoontology MCP 完整参考（v1.1.1 本机调整版）

## 部署事实

| 项 | 值 |
|---|---|
| 代码 | `~/.claude/plugins/cache/evoontology/evoontology/1.1.1/`（**调整版**） |
| 解释器 | `/Users/apple/Desktop/EvoOntology/.venv/bin/python`（3.11.15） |
| PYTHONPATH | 上面的 1.1.1 目录 |
| serverName | `evoontology` · global 注入 |
| **workspace** | **每次调用必传**（1.1.1 不再用 `--store` 默认值） |
| 当前 workspace | `/Users/apple/Desktop/项目/中咨国际/上财大数据研究中心-可研本体/.evoontology` |
| 当前 active | `ontology_v3`（439 terms / 263 mappings / 718 relations / 19 constraints / 45 evidence） |

**注意**：`/Users/apple/Desktop/EvoOntology` 是 **1.1.0 原始版**（我最初 clone 的）。
**1.1.1 调整版**在 Claude Code 插件缓存里，两者 `renderer.py` 差异就是 6 种扩展关系。

## v1.1.1 相对官方版的两个扩展

### ① 关系类型 5 → 11 种

受控 5（schema 原定）：
```
association / hierarchy / composition / equivalence / derivation
```

扩展 6（本地 `renderer.py` 支持）：
| 类型 | 语义 | source → target |
|---|---|---|
| `reasoning` | claim 由 guard/gate 推导 | claim ← basis |
| `reuse` | claim 复用报告规则/指标/限值 | reuser ← reused |
| `citation` | clause/claim 引用标准或条款 | citing ← cited |
| `has_limit` | metric 挂报告限值 | metric ← limit |
| `tests` | gate 测计算函数或目标 | test ← tested |
| `guards` | guard 监视 gate | guard ← guarded |

**`validate_semantics` 不校验 relation_type 取值** —— 只查：
active.json / 目录存在 / 五文件存在 / JSON 合法 / 是 list / 有 id / id 不重复 /
evidence 可解析 / relation 端点可解析 / mapping term_id 可解析 / constraint target 可解析。

**所以 264 条扩展关系合法**（`passed: true, errors: []`）。

### ② `extraction_policy.yaml`

放在项目根，控制下次 build/evolve 的抽取范围：

```yaml
include_term_types: []        # entity/metric/concept/category
exclude_term_types: []
include_relation_types: []
exclude_relation_types: []
include_reference_documents: true
include_calculation_functions: true
include_only_term_ids: []
exclude_term_ids: []
exclude_term_id_prefixes: []  # 如 [ref_std_]
exclude_name_patterns: []     # Python re.search 语义
max_terms: 0                  # 0 = 不限制
```

**删 term 时必须一并清理依赖引用**，否则 `validate_semantics` 报未解析引用。
桥接里 `evo_bridge.apply_policy()` + `_prune()` 已实现这一点。

## 术语类型（v3 实测）

```
entity 139 / clause 81 / metric 78 / gate 39 / limit 29
concept 25 / guard 19 / claim 19 / category 10
```

**关键**：`clause` / `limit` / `gate` / `guard` / `claim` **都是 term**，
统一用 `browse_semantics` / `resolve_semantics` 查，不需要按文件路径找。

**`definition` 承载结构化内容**（不是拆字段）：
```json
{"id": "gate_calc_total_investment_sum", "type": "gate",
 "definition": "calculation 门禁；状态：active；表达式：total_investment == ...；输入：...；失败信息：13032 = 建安11188 + ..."}
```

## 29 个工具分组

| 组 | 工具 |
|---|---|
| **查询** | `browse_semantics` `resolve_semantics` `execute_ontology_query` `resolve_ontology_task` |
| **校验** | `validate_semantics` |
| **可视化** | `visualize_ontology` |
| **版本** | `list_versions` `save_version` `set_active_version` `publish_ontology_build` `annotate_ontology_version` |
| **演化** | `start_evolution_run` `resume_evolution_run` `begin_evolution_round` `record_evolution_round` `record_evolution_evaluation` `confirm_trajectory_sources` `accept_evolution` `mark_evolution_incomplete` `extend_evolution_budget` `finalize_evolution_run` `evolution_status` `evolution_run_status` |
| **工作流** | `configure_ontology_project` `prepare_ontology_workload` `ontology_workflow_status` `start_ontology_task` `record_ontology_task_event` `finish_ontology_task` |

## 两个最常用

```python
# 找概念（只回相关项，limit 1-6）
browse_semantics(workspace="<ws>", query="总投资", kind="term", limit=5)

# 取五层完整链路（mentions ≤ 5）
resolve_semantics(workspace="<ws>", mentions=["总投资","gate_xxx","limit_xxx"])
# → {term, mappings, relations(含扩展6种), constraints, evidence, coverage_status}
```

## 已知坑

1. **`mcp_connector_health_check` 对 custom 连接报「未连接」是假警报** —— 它按市场 connectorId 查。判断接上要 `mcp_connector_export_config` 看 `enabled`，或**直接调一次工具**。
2. **1.1.1 必须传 `workspace`** —— 用 `--store` 起服务后，工具调用仍报 `workspace is required`。
3. **`Term.from_dict()` 只读 `data["evidence"]`**，不是 `evidence_refs`（`Mapping` 才读 `evidence_refs`）。
4. **records 必须是 list**，给 dict 报 `TypeError: string indices must be integers`。
5. **Python 需 ≥3.10**，系统默认 3.9.6 装不上。

## 与形包的分工

| | evoontology v3 | 形包 |
|---|---|---|
| terms | **439**（含 clause/limit/gate/guard/claim） | 0（只 13 类类型定义） |
| relations | **718**（11 种） | 7 类类型（无实例） |
| 限值 | **29 个**（都有值） | 21 个（值待抽） |
| 门禁 | **39 个**（30 有表达式） | 51 条 |
| 守卫 | **19 个** | **0** |
| 证据 | **45 条**（带 validation_method） | 0 |
| 条款原文 | **0**（81 个空槽） | 54 条 |
| 跨项目复用 | ❌ 含 328 处上财专名 | ✅ **0 处** |
| chunk 级溯源 | ❌ 只到 table/column | ✅ 骨架带 chunk_ids |
| 质量审计 | ✅ **0 孤立 0 缺证据** | 未做 |

**互补，不替代。**
