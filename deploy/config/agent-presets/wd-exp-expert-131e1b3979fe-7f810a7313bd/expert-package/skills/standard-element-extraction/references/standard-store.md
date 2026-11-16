# 标准要素落库（多标准 / 多报告）

抽取结果不能只停在文件里。每个标准按 standard_id 独立入库；一份检测报告可以关联多个标准，审核时按 report_id 一次取回全部规则。

## 1 存储模型（以运行时实际建表为准）

两个库，都是 SQLite。`load_library` 是唯一写入入口：

| 库 | 表 | 作用 |
|---|---|---|
| `library/standards.db` | `standards` | 标准主表：指纹、rule_set_id、counts、载入时间 |
| | `rules` | 规则卡（payload 存整卡：predicate / check_targets / anchor） |
| | `tasks` | 槽位任务（报告侧要填的每个槽） |
| | `gaps` | 缺口（含 pending_class，未补齐不会变"已补齐"） |
| | `findings` | 自审结果（每个 standard_id 只留一行，覆写） |
| | `span_refs` | 条款 → `span_id` 映射（结构侧，不含原文） |
| | `nodes` | SOP 图节点（node_id / type / clauses / params / done_when / basis / payload） |
| | `edges` | SOP 图边（src / dst / type） |
| | `rule_node` | **规则 → 节点反向索引**（link=criteria / qualitative） |
| `library/spans.db` | `spans` | 只存原文，主键 `span_id = <text sha>:<start>-<end>`，附 `idx_clause` |

> 更正：本节此前列过 `standard_package / clause / element / doc_field / report / audit_run` 等表，代码里从未创建过（`init_db.py` 无 DDL、无 `.sql`）。不要按那张表找数据，按上面 9 张表。

### 1.1 图必须进库，不能只留 JSON

`sop-graph.json` 是生成物；下游要按 `node_id` 分组、沿边找记录，必须查 `nodes` / `edges` / `rule_node`，**不许再读 JSON 文件**（instance 之间会读错、也无法 join）。

挂不上节点的规则不是"可以不管"，而是缺口：`load_library` 会把它们写进 `machine/graph_gaps.json`（`reason=MISSING_NODE`，附应按 C 类补哪类节点）。门禁 `--node sop` 与 `--node handoff` 都查这一条：**未挂且未登记 = FAIL**。

`load_library` 打印里的 `graph_missing: true` 表示该标准根本没产图（不是 0 个缺口）——此时不写 gaps 文件，门禁直接判"图缺失"。


## 2 入库流程

1. 抽取完成，产出 ses/<standard_id>.ses.json（同一 schema）。
2. 运行 scripts/load_standard.py --db standards.db --ses ...，只覆盖该 standard_id，其他标准不受影响。
3. 首次建库用 scripts/init_db.py --db standards.db。
4. 报告入库时用 scripts/link_report.py 关联一个或多个标准；自动选择该标准下 status=PROVIDED 的方法与规则集。
5. 审核按 scripts/query_report_rules.py --report 展开多标准规则。

## 2.1 单标准库（按标准名称命名）

全局库仍是审核主库；每个标准另外导出一份独立 SQLite 库，放在 by-standard/，文件名：

~~~text
标准名称（标准号）.db
~~~

示例：水质 氨氮的测定 纳氏试剂分光光度法（HJ 535-2009）.db。

单标准库只保留该标准的 standard/clause/element/rule/method/formula_card/performance_data 等标准表；project/report/audit 表为空。用于检索、分发、归档；跨标准审核继续用全局库。

~~~bash
python3 scripts/export_per_standard_dbs.py --db standards.db --outdir by-standard --schema schema.sqlite.sql
python3 scripts/search_standards.py --db standards.db --keyword 氨氮
python3 scripts/search_standards.py --db standards.db --list
~~~

## 3 命令

运行时入口是 `run_contract.py --util`（不再依赖散装脚本）：

~~~
# 抽取产物 → 两个库（含 nodes/edges/rule_node + graph_gaps 登记）
python3 scripts/run_contract.py --util load_library --out <out>

# 按库看每个标准挂了多少节点、多少规则没落点
python3 scripts/run_contract.py --util graph_index --out <out>

# 下游读图：给规则取节点与边 / 给节点取规则与边（零 JSON 读取）
python3 scripts/run_contract.py --util graph_lookup --out <out> --rule ARC-C2-7.1-01
python3 scripts/run_contract.py --util graph_lookup --out <out> --node-id SOP-P1

# 门禁（含图挂载与 trail_present）
python3 scripts/validate_node.py --node sop --out <out>
python3 scripts/validate_node.py --node handoff --out <out>
~~~

历史脚本 `load_standard.py / init_db.py / query_standard.py` 保留但不再是主路径；`query_report_rules.py`、`link_report.py` 仍用于多报告关联。

## 4 多标准规则

同一报告关联多个标准时，v_report_rules 会返回每个标准下的全部规则；规则 ID 在不同标准内唯一（ARC-{分类}-{条款}-{序号}），跨标准以 standard_id + rule_id 定位。审核结果写入 audit_result 时必须同时带 standard_id 与 rule_id，避免不同标准同号冲突。

## 5 数据库选择

当前交付以 SQLite 落库（无外部服务、随包可带走）；schema.postgres.sql 为同构 DDL，字段使用 JSONB/TIMESTAMPTZ。迁移时替换连接与占位符即可，表结构与查询不变。

## 6 边界

- 落库不改变抽取内容，只做持久化；覆盖导入按 standard_id 幂等。
- 未上传引用、缺口、待补字段原样保留，不因入库变成"已补齐"。
- 报告与标准的关联是显式声明，不根据报告文本自动猜标准。
