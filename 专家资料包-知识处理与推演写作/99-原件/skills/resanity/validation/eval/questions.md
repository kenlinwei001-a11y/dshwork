# 单臂评估题目集

题目复用 `validation/v2` 的 8 案例 prompt 文件，另附每题的打分上下文。
封闭题（mode: closed）不得外部检索；开放题（mode: open）允许网络与数据工具。
所有题目的 as-of 与决策边界以对应 prompt 文件为准。

## 投资 profile（默认场景，优先跑）

### I01 公司经济暴露（closed）
- prompt：`validation/v2/prompts/investing-company.md`
- 测点：沿样品→客户验证→订单→交付→收入→毛利→回款逐段标注；工程事实/公司暴露/市场定价分离；唯一最低成本下一验证。
- 指标侧重：①②③ 全测。

### I02 行业利润池（closed）
- prompt：`validation/v2/prompts/investing-profit-pool.md`
- 测点：需求约束→价值捕获→替代路线→公司归属→as-of 定价；同源转载不得冒充多源。
- 指标侧重：②③，以及"最弱环节"是否被正确命名。

### O03 投资暴露（open）
- prompt：`validation/v2/prompts/network-investing.md`
- 测点：真实网络环境下的一手来源纪律与数据工具使用；价格锚是否由工具采集而非搜索摘要。
- 指标侧重：②③，额外记录数据工具调用是否正确（见 rubric 备注）。

## 核心 profile（方法泛化观察）

### C01 产品主张（closed）
- prompt：`validation/v2/prompts/core-product.md`
- 测点：非投资问题的最小主张卡应用。

### C02 政策落地（closed）
- prompt：`validation/v2/prompts/core-policy.md`
- 测点：政策传导链的"已观察/未知"划分。

## 纵向题（验证日复盘专用）

### A01 锚生命周期（longitudinal）
- prompt：`validation/v2/prompts/anchor-active.md`（首次）
- 测点：锚更新只复核会改变原判断的事实；`/resanity-check` 观察包是否被使用；
  验证日按 rubric 复盘轮记录 推翻/确认/悬置 与失效类型。
