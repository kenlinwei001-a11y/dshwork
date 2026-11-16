# 交接契约：审核专家与审核结果页面

本文件规定本专家交付给下游的两方如何使用产物：后台的**审核专家**（判定）与前台**审核结果页面**（展示并回贴报告文字）。契约的目标是让「规则 → 判定 → 页面高亮 → 条款回指」全程可追、可复现。

## 一、交付清单

| 文件 | 内容 | 消费方 |
|---|---|---|
| standard-element-package.json | 条款、要素、公式、图、规则卡、方法族、缺口 | 审核专家（只读） |
| hj671-2013-graph.json | 全量图谱：240 节点 / 260 边 / 5 个视图 | 审核专家与页面 |
| clause_registry.json | 条款号、页码、原文、模态 | 页面（回指原文） |
| audit-rule-cards.json | 规则卡全集（含 check_targets） | 审核专家 |
| coverage-matrix.csv | 条款 × 要素 × 规则 × 缺口 | 质量复核 |
| README / 缺口清单 | 待上传文件与口径说明 | 用户、审核专家 |

文件命名固定，按 standard_id + 版本目录存放；同一标准不同版本不得混放。

## 二、读取顺序（审核专家）

1. 读 standard_id、source_fingerprint、rule_set_id；按 method → ruleset → contains 取规则集。
2. 读 method_family，确认报告声明的方法与规则集匹配；不匹配则不执行判定，返回「方法族不匹配」。
3. 读 clause_registry 与 audit_rule_cards，按 C1–C8 分组装载。
4. 读 gaps：规则若依赖 PENDING_UPLOAD 的引用文件，执行时只能给 UNVERIFIABLE 并提示「待补依据」。

## 三、规则执行协议

对每条规则：

1. **取观测值**：按 check_targets 在报告/过程记录中定位字段；记录 span 与 confidence。
2. **判适用**：applicability 不成立 → NOT_APPLICABLE（记录理由）。
3. **判谓词**：观测值 + 谓词 → PASS / FAIL；定性规则 → 人工确认，默认 UNVERIFIABLE 直至人工判定。
4. **缺失**：按 on_missing；on_missing=FAIL 即按未做处理。
5. **冲突**：条款冲突、标准与 SOP 松紧冲突 → CONFLICT_PENDING，回传本专家，不自行选边。

判定枚举固定为：PASS / FAIL / NOT_APPLICABLE / UNVERIFIABLE / CONFLICT_PENDING。

## 四、结果记录（页面渲染的唯一输入）

~~~json
{
  "report_id": "R-2026-0001",
  "standard_id": "HJ 671-2013",
  "rule_set_id": "RS-HJ671-2013",
  "rule_id": "ARC-C7-11.2-01",
  "category": "C7",
  "verdict": "PASS",
  "target": {
    "page": 2,
    "block_id": "p-07",
    "char_start": 42,
    "char_end": 76,
    "quote": "相关系数 r=0.9992（6 个浓度点）",
    "method": "keyword",
    "confidence": 0.98
  },
  "clause_anchor": { "clause": "11.2", "page": 6, "quote": "校准曲线的相关系数γ≥0.995" },
  "observed": { "field": "校准曲线相关系数", "value": 0.9992, "unit": "1" },
  "message": "相关系数 0.9992 ≥ 0.995",
  "suggestion": null,
  "evidence_refs": ["原始记录-2026-03-11-p2"]
}
~~~

必填：report_id、standard_id、rule_id、verdict、target（至少 page + quote 或 block_id）、clause_anchor、message。
target 允许 UNLOCATED：此时 quote 可为空，页面显示「未定位」，不得隐藏该条结果。

## 五、页面契约

1. **分组**：按 C1–C8 分类展示；分类不是严重度，不做红黄绿分级。
2. **高亮**：用 target 的 page/block/char 范围高亮报告原文；表格单元格用 block_id 定位。
3. **回指**：点击结果打开条款原文（clause_anchor 的 page/quote）。
4. **缺证**：UNVERIFIABLE 与 FAIL 视觉区分；缺证提示「补证据」，不显示为通过。
5. **未定位**：单独列出，便于人工补标。
6. **多方法**：页面顶部显示报告声明的方法与规则集；方法族内可切换查看差异，但不得混用判定。
7. **只读**：页面不修改规则与结论；人工复核意见另存，不覆盖审核结果。

## 六、版本与变更

- 标准换版：source_fingerprint 变化 → 条款级 diff → 受影响要素与规则 → 输出变更影响清单（rule_id、变更类型、是否需重判）。
- 规则修订：保留 rule_id，版本号递增；旧判定标注规则版本，不追溯覆盖。
- 引用文件补齐：只更新受影响的规则与状态，不整体重抽。
- 实验室文件更新：按 lab_alignment 的 alignment_id 增量更新，不重写标准条款。

## 七、验收清单

- [ ] 每条规则可执行（有谓词或定性判据、有证据、有定位线索）
- [ ] 缺证口径写死，未出现「默认通过」
- [ ] 所有结果带 rule_id 与 clause_anchor
- [ ] 页面能高亮到报告文字，未定位项可见
- [ ] 方法族匹配检查已执行
- [ ] 引用缺口与实验室文件缺口在页面可见
- [ ] 版本变化有影响清单
