# 标准要素落库（多标准 / 多报告）

抽取结果不能只停在文件里。每个标准按 standard_id 独立入库；一份检测报告可以关联多个标准，审核时按 report_id 一次取回全部规则。

## 1 存储模型

| 表 | 作用 |
|---|---|
| standard | 标准主表：版本、发布/实施、来源指纹、页数 |
| standard_package | 完整 SES JSON 与图谱 JSON 快照，可重建 |
| clause / node / edge | 条款、图谱节点、关系边 |
| element / rule / doc_field | 要素、审核规则卡、报告/过程文档字段 |
| reference_doc / gap / method / rule_set | 引用、缺口、方法族、规则集 |
| report / report_standard | 报告与标准的多对多关联 |
| audit_run / audit_result | 审核批次与逐条判定（预留给审核专家） |

规则按 C1–C8 分类，含 predicate_json、check_target_json、on_missing、anchor_page、source_layer；detail_status 区分 full / rule_text / graph_only，未抽到的字段保持 NULL，不编造。

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

~~~
python3 scripts/init_db.py --db standards.db
python3 scripts/load_standard.py --db standards.db --ses ses/HJ671-2013.ses.json
python3 scripts/query_standard.py --db standards.db --standard "HJ 671-2013" --rules
python3 scripts/link_report.py --db standards.db --report R-2026-0001 --standard "HJ 671-2013"
python3 scripts/query_report_rules.py --db standards.db --report R-2026-0001
~~~

## 4 多标准规则

同一报告关联多个标准时，v_report_rules 会返回每个标准下的全部规则；规则 ID 在不同标准内唯一（ARC-{分类}-{条款}-{序号}），跨标准以 standard_id + rule_id 定位。审核结果写入 audit_result 时必须同时带 standard_id 与 rule_id，避免不同标准同号冲突。

## 5 数据库选择

当前交付以 SQLite 落库（无外部服务、随包可带走）；schema.postgres.sql 为同构 DDL，字段使用 JSONB/TIMESTAMPTZ。迁移时替换连接与占位符即可，表结构与查询不变。

## 6 边界

- 落库不改变抽取内容，只做持久化；覆盖导入按 standard_id 幂等。
- 未上传引用、缺口、待补字段原样保留，不因入库变成"已补齐"。
- 报告与标准的关联是显式声明，不根据报告文本自动猜标准。
