# 抽取 / 审核 边界与交接（v1）

本专家**只负责抽取**，不取值、不比对、不签发 PASS/FAIL。判定由审核侧三个专家执行。

## 一、本专家交付什么

| 交付物 | 内容 | 审核侧怎么用 |
|---|---|---|
| 条款登记册 | 条款号 · 页码 · 模态 · 原文 | 回指原文 |
| 要素包 | SE-12 要素 + 条款锚 | 理解流程与判据来源 |
| 规则卡 | `predicate`(算子/阈值/单位) + `requires`(要哪个字段) + `check_targets`(去哪份文档哪一栏) + `anchor` + `kind` + `criticality` + `missing_kind` | 按 `requires` 取值 → 按 `predicate` 比对 |
| 字段词汇表 | `fields.yaml`（45 个规范字段 + 抽取正则 + 聚合语义 + 单位） | 抽值时按字段定义取 |
| 规则集 | `references/rule-sets/<标准号>.json` | 按报告声明的方法选规则集 |
| 质量报告 | 章节覆盖 · 阈值原文回检 · 可审核性准入 · 字段-原文一致性 | 判断这份规则集能不能用 |

## 二、本专家不做什么（越界即错）

| 不做什么 | 归属 |
|---|---|
| 从报告/记录里取值 | 检测报告审核专家 / 过程文档审核专家 |
| 数值归一化后比对（mg/L↔μg/L、ND 语义） | 同上（`value_normalize.py` 已移交） |
| 曲线量级校验、批次顺序校验 | 过程文档审核专家 |
| 出 PASS / FAIL / 缺证 / 待补证 | 审核裁定专家 |
| 合并报告与过程审核结果、假通过复核 | 审核裁定专家 |

## 三、审核侧脚本已迁出（本包不再包含）

| 脚本 | 现属 |
|---|---|
| `judge_from_rules.py`、`value_normalize.py`、`doc_element_locator.py` | `report-audit-playbook` |
| `magnitude_check.py`、`check_procedure_order.py` | `process-audit-playbook` |
| `bucket_judge_v2.py`、`judge_query.py`、`judge_brief.py`、`pack_index.py` | `adjudication-playbook` |

## 四、唯一保留的“跑一遍”是抽取验收，不是判定

```
目的：证明抽出来的规则能被判据驱动跑通
判据：可判定条数 / 跳过率 / 字段缺口
产出：machine/extraction_acceptance.json（不含 verdict）
禁止：在抽取阶段出 PASS/FAIL，或把抽样结果当审核结论
```

## 五、交接契约

1. 交付时给出 `standard_id` + 规则集路径 + 准入率 + 未覆盖章节清单。
2. 审核侧按 `rule.requires` 取字段、按 `predicate` 比对；取不到时按 `criticality × missing_kind` 定处置。
3. 审核侧发现「规则本身写错」（阈值错、字段错），回传 `rule_id` + 证据给本专家修订，不在审核侧改规则。
