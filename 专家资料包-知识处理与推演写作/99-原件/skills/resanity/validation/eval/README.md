# 单臂轻量评估套件（resanity eval）

评估是"效果提升"的唯一裁判。8 案例付费 A/B（`validate:v2:ab:dsh`）是完整仪式；
本套件是零成本单臂版：**同一批题目反复跑，用人工评分表测三个指标**，
为方法修订提供可复核基线。工程收据不证明研究有效——本套件的产出是
**评分记录**，不是有效性结论。

## 三个指标

| 指标 | 测量什么 | 何时打分 |
|---|---|---|
| ① 结论推翻率 | 承重主张后来被事实推翻/确认/悬置的比例 | 验证日复盘（第二轮） |
| ② INSUFFICIENT 诚实性 | 该说"不知道"时是否明写 INSUFFICIENT；是否把"未找到"写成"不存在"；是否伪装闭合 | 交付轮 |
| ③ 唯一下一验证质量 | 是否单一外部证据单元；能否裁决一个承重分叉；是否最低成本 | 交付轮 |

## 流程（每轮）

1. 在「散修研究」预设开一个会话，工作目录设为 `validation/eval/runs/<case-id>/`；
2. 把 `questions.md` 中该题的完整 prompt 交给模型（封闭题禁止外部检索）；
3. 交付后保存 `report.md`，跑 `/resanity-report` 与 `/resanity-audit`（有条件时），
   机械结果记入 `delivery.json`；
4. 评审人按 `rubric.md` 打分，写入 `scores.json`；
5. 题目带验证日期的，到期后读 `rubric.md` 的复盘轮逐条对照，追加 `review.json`；
6. 跑 `python3 validation/eval/collect.py` 聚合总表。

## 目录约定

```text
validation/eval/
  README.md        本说明
  questions.md     题目集（复用 validation/v2 的 8 案例 prompt）
  rubric.md        评分表与评分标准
  collect.py       聚合 runs/ 下所有 delivery.json / scores.json / review.json
  runs/<case-id>/  每轮工作区（gitignore 建议排除）
```

## 诚实边界

- 单臂：没有基线对比，只能测"随时间/版本的变化"，不能测"比不用 Resanity 好多少"；
- 评分表是人工的，评分者一致性本身需要校准（两人同评一题对分）；
- 样本量小、题目固定 → 结果只支持方法修订假设，不支持有效性声明。
