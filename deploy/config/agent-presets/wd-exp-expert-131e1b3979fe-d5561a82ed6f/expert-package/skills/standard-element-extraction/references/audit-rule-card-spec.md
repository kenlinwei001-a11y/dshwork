# 审核规则卡（ARC）规范

规则卡是本专家交给审核专家的**最小判定单元**。一张卡 = 一条可判定的要求 + 一个谓词 + 一组证据 + 一个条款锚 + 一组报告定位线索。规则不分级，只分类（C1–C8）。

## 1. 卡片字段

| 字段 | 必填 | 说明 |
|---|---|---|
| rule_id | 是 | ARC-{主分类}-{条款号}-{序号} |
| title | 是 | 一句话（≤30 字），审核页面显示 |
| category | 是 | C1–C8，主分类 |
| category_secondary | 否 | 次分类（如同时涉及记录） |
| clause | 是 | 标准条款号 |
| modality | 是 | MUST / SHOULD / MAY / MUST_NOT |
| requirement | 是 | 要求原文摘要（保留数值） |
| predicate | 二选一 | 结构化谓词；定性规则用 qualitative_check |
| applicability | 否 | 适用条件（方法/基质/浓度分档/批次） |
| evidence_required | 是 | 必须出现的记录/附件清单 |
| check_targets | 是 | 报告或过程文档中的核对目标与定位线索 |
| on_missing | 是 | UNVERIFIABLE 或 FAIL；缺证不默认通过 |
| on_fail | 否 | 超限处置（如「重绘校准曲线」） |
| source_layer | 是 | STANDARD / REF_STANDARD / LAB_SOP / QC_PROCEDURE / INSTRUMENT_MANUAL |
| cross_refs | 否 | 关联规则 ID |
| anchor | 是 | {standard, clause, page, quote} |
| notes | 否 | 口径说明（如「标准未给阈值」） |

## 2. 分类 C1–C8

| 代号 | 分类 | 判定对象 | 例子 |
|---|---|---|---|
| C1 | 方法适用性 | 样品类型、浓度区间、检出限、干扰边界 | 总磷结果是否落在 0.020–1.00 mg/L；悬浮物/粒径是否超限 |
| C2 | 样品与流转 | 容器、固定、保存温度与时限、前处理 | 加硫酸至 pH≤2；24 h 或冷冻 1 个月；pH 调节 |
| C3 | 仪器与设备 | 仪器配置、关键部件、精度、工作参数 | 天平 0.0001 g；检测池 10 mm@880 nm；超声 40 kHz |
| C4 | 试剂与材料 | 等级、浓度、配制、贮存、有效期、除气 | 显色剂 4℃ 1 个月；还原剂 2 周；氦气/超声除气 |
| C5 | 操作流程 | 步骤顺序、参数、等待时间、环境条件 | 基线稳定约 20 min；室温 20±5℃、波动≤±2℃ |
| C6 | 数据与计算 | 原始信号、曲线、公式、稀释倍数、修约 | γ≥0.995；ρ=(y−a)/b×f；结果表示规则 |
| C7 | 质量控制 | 空白、核查、平行、加标、质控样、系统性能 | 空白≤DL；每 10 样核查≤5%；回收率 80–120%；R>90% |
| C8 | 记录与报告 | 记录完整性、可追溯、报告字段、表述 | 6 个校准点记录；报告写明依据、单位、方法 |

一条规则只能有一个主分类；跨类时用 category_secondary。分类用于页面分组与统计，**不表示严重程度**。

## 3. 谓词语法

~~~json
{
  "field": "校准曲线相关系数",
  "op": ">=",
  "value": 0.995,
  "unit": "1",
  "tolerance": 0,
  "window": "同批",
  "compare_mode": "absolute | relative"
}
~~~

op 枚举：

| op | 含义 | 备注 |
|---|---|---|
| >= / <= / > / < | 数值比较 | 必须带单位 |
| == / != | 等值比较 | 文本或数值 |
| between | 闭区间 | value 用 [low, high] |
| in | 枚举集合 | value 用数组 |
| exists | 记录/字段存在 | 用于 C8 |
| sequence | 步骤顺序 | value 为步骤 ID 数组 |
| regex | 文本模式 | 仅用于格式类（如结果保留位数） |
| custom | 需脚本判定 | 必须给 operator_ref 与说明 |

比较必须有观测值；观测值来自报告/记录中的字段，由审核专家抽取并附 span。

## 4. 定性检查

标准里的定性要求（如「试剂应保持澄清」「必要时过滤」）不做数值谓词，改写为：

~~~json
{
  "qualitative_check": {
    "question": "试剂是否澄清、有无过滤记录",
    "acceptable": ["澄清", "有过滤记录"],
    "needs_review": ["轻微浑浊但有过滤记录"],
    "unacceptable": ["浑浊且无过滤记录"]
  }
}
~~~

定性检查必须由人复核，页面标「需人工确认」，不自动判 PASS。

## 5. 证据与核对目标

evidence_required 取值来自固定文档类型：

检测报告 / 原始记录 / 前处理记录 / 仪器使用记录 / 试剂配制记录 / 质控记录 / 样品流转单 / 校准曲线记录 / 附件（谱图、称量记录、温湿度记录）。

check_targets 每项：

~~~json
{
  "target_type": "report_field | process_record | attachment | instrument_record",
  "doc_type": "原始记录",
  "field": "校准曲线相关系数",
  "match_hints": ["相关系数", "γ", "r="],
  "value_pattern": "0.99",
  "locator_strategy": "field_label | keyword | table_header | quote_search"
}
~~~

定位策略优先级：field_label（字段标签）→ table_header（表头+行）→ keyword（关键词上下文）→ quote_search（引文检索）。规则应给出至少一种可命中的策略。

运行期 span：

~~~json
{ "page": 3, "block_id": "tbl-02-r4", "char_start": 118, "char_end": 146,
  "quote": "校准曲线相关系数 r=0.9992", "method": "table_cell", "confidence": 0.98 }
~~~

硬约束：quote 必须能在报告原文定位；定位失败标 UNLOCATED，不得把结果贴到错误文字上。

## 6. 缺失与冲突口径

| 情形 | on_missing | 说明 |
|---|---|---|
| 应有记录但报告/记录中没有 | FAIL | 默认按未做处理（可由实验室在口径确认时改为 UNVERIFIABLE） |
| 附件缺失但正文有结论 | UNVERIFIABLE | 待补附件后再判 |
| 条款本身未给阈值 | 不出数值谓词 | 转定性检查或记录性检查（C8） |
| 标准与 SOP 冲突 | CONFLICT_PENDING | 不用松的一侧判通过 |
| 引用文件未上传 | UNVERIFIABLE | 规则标 pending_ref，页面显示「待补依据」 |

缺证不等于通过；on_missing 必须写死，不能留给审核时临时决定。

## 7. 卡片质量检查（生成后逐条过）

- 能否用一句话说清「查什么、合格线在哪」。
- 谓词字段是否在报告/记录中真实存在且可定位。
- 阈值是否来自原文（quote 可验证），不是推导或惯例。
- 适用条件是否写清（浓度分档、基质、方法）。
- 缺失时是否给出明确处置。
- 是否与同批其他规则冲突（如空白阈值与检出限）。
- 分类是否唯一且正确。

## 8. 示例（HJ 671—2013）

~~~json
{
  "rule_id": "ARC-C7-11.2-01",
  "title": "校准曲线相关系数不低于 0.995",
  "category": "C7",
  "clause": "11.2",
  "modality": "MUST",
  "requirement": "每批样品分析均须绘制校准曲线，相关系数γ≥0.995",
  "predicate": { "field": "校准曲线相关系数", "op": ">=", "value": 0.995, "unit": "1" },
  "applicability": "每批",
  "evidence_required": ["校准曲线记录", "原始记录"],
  "check_targets": [
    { "target_type": "report_field", "doc_type": "原始记录", "field": "校准曲线相关系数",
      "match_hints": ["相关系数", "γ", "r="], "locator_strategy": "field_label" }
  ],
  "on_missing": "FAIL",
  "on_fail": "重新绘制校准曲线并重测该批样品",
  "source_layer": "STANDARD",
  "anchor": { "standard": "HJ 671-2013", "clause": "11.2", "page": 6,
    "quote": "校准曲线的相关系数γ≥0.995" }
}
~~~

~~~json
{
  "rule_id": "ARC-C7-11.3-01",
  "title": "平行双样比例与相对偏差分档",
  "category": "C7",
  "clause": "11.3",
  "modality": "MUST",
  "requirement": "每批至少 10% 平行双样（少于 10 个至少 1 个）；总磷≤0.02 mg/L 时相对偏差≤25%，>0.02 mg/L 时≤10%",
  "predicate": {
    "field": "平行样相对偏差",
    "op": "custom",
    "value": { "le_0.02": 25, "gt_0.02": 10 },
    "unit": "%",
    "compare_mode": "absolute"
  },
  "applicability": "按样品总磷浓度分档",
  "evidence_required": ["质控记录", "原始记录"],
  "check_targets": [
    { "target_type": "process_record", "doc_type": "质控记录", "field": "平行样相对偏差",
      "match_hints": ["平行", "相对偏差", "双样"], "locator_strategy": "table_header" }
  ],
  "on_missing": "FAIL",
  "source_layer": "STANDARD",
  "anchor": { "standard": "HJ 671-2013", "clause": "11.3", "page": 6,
    "quote": "平行样的相对偏差≤25%；当总磷质量浓度＞0.02 mg/L，平行样的相对偏差≤10%" }
}
~~~

## 9. 反模式

- 把「方法原理」写成规则（不可判定）。
- 阈值来自记忆或行业惯例却不标 convention。
- 一张卡塞多条独立要求（无法定位失败原因）。
- on_missing 为空或默认「通过」。
- 规则没有 check_targets，页面无法定位。
- 把「建议」「宜」写成 MUST。
- 用公告/前言里的标准号扩引用范围。
