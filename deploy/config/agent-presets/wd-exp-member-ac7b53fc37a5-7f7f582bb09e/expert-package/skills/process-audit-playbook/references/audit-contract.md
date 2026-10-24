# 审核契约（3/4/5 号共用）

## 1 输入

- 证据包：report / documents / fields / methods / instruments / records / missing / consistency_flags。
- 规则：rule 表（按 standard_id、category、check_target_json、predicate_json、on_missing）。
- 项目与报告关联：report_standard（只处理 method_match=match 的标准）。

## 2 规则路由

| 分类 | 主审 | 说明 |
|---|---|---|
| C1 方法适用性 | 3 报告 | 样品类型、量程、检出限、干扰边界 |
| C2 样品与流转 | 4 过程 | 容器、固定、保存、时限、前处理 |
| C3 仪器与设备 | 4 过程 | 配置、精度、参数、状态 |
| C4 试剂与材料 | 4 过程 | 等级、浓度、配制、贮存、有效期 |
| C5 操作流程 | 4 过程 | 步骤、参数、时间、环境 |
| C6 数据与计算 | 3 报告 | 公式、稀释、修约、结果表示 |
| C7 质量控制 | 4 过程 | 空白、校准、平行、加标、质控样、性能 |
| C8 记录与报告 | 5 裁定 | 记录完整性、报告字段、可追溯性 |

一条规则只有一个主审；次审只登记意见，不重复出 verdict。

## 3 判定枚举

| verdict | 含义 |
|---|---|
| PASS | 证据齐备且满足谓词 |
| FAIL | 证据齐备但不满足 |
| NOT_APPLICABLE | applicability 不成立 |
| UNVERIFIABLE | 证据缺失/不可读，按 on_missing |
| CONFLICT_PENDING | 条款冲突、方法 mismatch、证据冲突 |

缺证不等于通过；on_missing=FAIL 时按未做处理。

## 4 结果记录

每条结果必须带：run_id、report_id、standard_id、rule_id、category、verdict、target（doc_id/page/block_id/char/quote）、clause_anchor、observed、message。

target 定位失败标 UNLOCATED；不得把结果贴到错误文字上。

## 5 方法 mismatch

report_standard.method_match=mismatch 时，该标准下规则全部 CONFLICT_PENDING，message 写明报告声明方法与库内标准；不套用库内规则。交 5 号裁定。

## 6 升级与冲突

- 标准内部矛盾 → 回 1 号/用户确认。
- 标准与 SOP 冲突 → 回 4 号/实验室确认。
- 报告与记录数值冲突 → 5 号裁定。
- 缺件 → 4 号确认是否可在过程文档中补证；不能补则 UNVERIFIABLE。

## 7 结果落库

audit_run / audit_result（run_id、rule_id、standard_id、verdict、target_json、observed_json、message、clause_anchor_json）。页面按 target span 高亮报告原文，点击回指条款。

## 8 禁止

- 审核专家不重抽报告/记录、不改证据包、不改规则。
- 不把缺证判成 PASS；不因「实验室通常这样做」放行。
- 不跨主审重复出 verdict；发现他人范围问题只登记 comment。
