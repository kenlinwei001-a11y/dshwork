# 报告审核证据字段

## 1 报告元数据

report_no、lab、client、sample_type、sample_count、sample_dates、receive_dates、test_dates、report_date、conclusion。

## 2 方法与仪器

- methods[]：analyte、declared、standard_id、method_match、quote。
- instruments[]：name、model、code。

## 3 结果表

fields[] 中：
- field：项目名 + 结果（如「总氮结果」）
- sample_id、value/text、unit、quote
- 检出限字段（如「总氮检出限」）
- 样品状态（如「无色透明液体」）

## 4 审核用字段

| 规则类型 | 找什么 |
|---|---|
| C1 适用性 | 样品类型、结果浓度、稀释倍数、检出限 |
| C6 计算 | 原始信号/吸光度、校准曲线截距/斜率、公式、稀释倍数、报告结果 |
| C8 报告字段 | 方法依据、仪器编号、单位、结果位数、检出限、签字/章 |

## 5 定位

- 报告表格：block_id = 表 ID + 行 + 列；quote 为单元格原文。
- 报告正文：page + quote。
- 方法/仪器：附表页 + quote。
