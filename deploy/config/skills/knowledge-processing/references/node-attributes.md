# 节点四属性：值从哪来 / 怎么产生 / 是否必填 / 口径唯一

## 为什么需要

EvoOntology 的 term 原本只有 7 个字段：
`id / name / type / scope / definition / aliases / evidence`

**没有「必须客户给」的标记** —— 下游分不清「这个数要问客户」还是「可以自己算」。

## 四个正交维度（不能合并）

| 字段 | 取值 | 回答什么问题 |
|---|---|---|
| `source_type` | CUSTOMER / STANDARD / JUDGMENT / DERIVED / INTERMEDIATE | 值**从哪来** |
| `node_role` | INPUT / INTERMEDIATE / DERIVED | 值**怎么产生** |
| `must_input` | true / false | **是否必须客户填空** |
| `caliber_status` | unique / ambiguous / missing | **口径是否唯一** |

## 判据表（`evo_bridge._infer_source_role`，零 LLM）

| 状况 | source_type | node_role | must_input | caliber_status |
|---|---|---|---|---|
| `status=undefined`（缺值） | CUSTOMER | INPUT | **true** | missing |
| `status=provided` + calibers | CUSTOMER | INPUT | false | **ambiguous** |
| `status=provided` | CUSTOMER | INPUT | false | unique |
| `status=computed` + calibers | DERIVED | **INTERMEDIATE** | false | **ambiguous** |
| `status=computed` | DERIVED | DERIVED | false | unique |

## 关键判据：`computed + calibers` 为什么是 INTERMEDIATE

以「总建筑面积」为例：

```json
{"id": "P-00ace9526aba", "subject": "总建筑面积", "value": 15600,
 "status": "computed", "rule": "R-建筑面积构成",
 "mapping": {"calibers": ["含地下","不含地下","含人防","不含人防"], "default": "含地下不含人防"},
 "caliber": "含地下不含人防"}
```

- **不能标纯 DERIVED** —— 口径有 4 种，客户确认前不能当定值
- **不能标 `must_input=true`** —— 值本身不用客户直接给（地上+地下算出来），
  **但它的依赖（地上/地下）要客户给**
- **正确**：`DERIVED + INTERMEDIATE + must_input=false + ambiguous`

## 实测（华东理工 graph）

```
source_type     CUSTOMER 125 / DERIVED 50 / JUDGMENT 21
node_role       INPUT 125 / INTERMEDIATE 10 / DERIVED 61
caliber_status  unique 115 / ambiguous 23 / missing 3
must_input      false 138 / true 3
```

**`must_input=true` 的 3 个，正好是那 3 处硬约束**：
```
研究生博士生访问学者规划人数     missing
地上总建筑面积需求              missing
基本预备费                     missing
```

## 下游用法

| 组合 | 怎么做 |
|---|---|
| `must_input=true` | **向客户要**。不许猜、不许填 0、不许用同类项目值 |
| `must_input=false` + `ambiguous` | **算完但标待审**；正文写两侧口径与数值，不裁决 |
| `source_type=DERIVED` | **绝不能问客户要**；缺依赖就问依赖 |
| `source_type=STANDARD` | 可检索标准库/法规，**不要问客户** |
| `source_type=JUDGMENT` | 客户声明了，但**必须绑证据** |

## EvoOntology 侧要做的

**四字段必须写进 term**（`save_version` 时带上），否则 `browse_semantics` /
`resolve_semantics` 返回时看不到，下游又会退回到「只有 type」。

```python
# save_version 的 terms 每项应含：
{"id": "...", "name": "...", "type": "metric",
 "definition": "...", "scope": "...", "aliases": [], "evidence": [],
 "source_type": "DERIVED", "node_role": "INTERMEDIATE",
 "must_input": False, "caliber_status": "ambiguous"}
```

**注意**：`validate_semantics` 不校验这四个字段（只查引用完整性），
所以补它们不会破坏现有版本，但**不补就等于没有**。
