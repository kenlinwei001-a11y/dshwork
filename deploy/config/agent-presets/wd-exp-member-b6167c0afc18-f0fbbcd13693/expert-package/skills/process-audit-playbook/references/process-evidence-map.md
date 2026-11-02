# 过程文档审核证据字段

## 1 文档

sample_log、raw_record、environment、instrument_log、calibration_cert、reagent（原始记录内）、commission、contract_review、task_order、risk_assessment。

## 2 记录字段

| 分类 | 字段 |
|---|---|
| C2 样品 | 容器、固定剂、pH、保存温度、采样/接收/测定时间、前处理步骤 |
| C3 仪器 | 仪器编号、型号、参数、使用日期、校准日期/有效期 |
| C4 试剂 | 名称、等级、浓度、称样量、配制日期、有效期、贮存条件 |
| C5 流程 | 校准点、顺序、温度、时间、体积、波长、比色皿 |
| C7 质控 | 空白数/值、r、连续校准、平行比例/偏差、加标比例/回收、质控样、系统性能 |

## 3 定位

- 原始记录表格：doc_id + page + block_id（表-行-列）+ quote。
- 仪器/环境记录：doc_id + page + 行标签 + quote。
- 证书：doc_id + 证书编号 + 有效期 + quote。

## 4 缺件判定

按项目方法应有：原始记录、校准记录、空白、平行、加标、仪器运行、环境、试剂配制、样品流转、校准证书。缺一项登记一项，不用报告正文替代。
