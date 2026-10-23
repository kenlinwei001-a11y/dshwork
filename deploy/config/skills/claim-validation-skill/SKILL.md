---
name: claim-validation-skill
description: "验证 Claim 的证据支持、时间一致性、事实依赖、推理完整性和语义范围。"
---

# Claim Validation Skill

## Skill ID
SK-12

## Purpose
验证 Claim 的证据支持、时间一致性、事实依赖、推理完整性和语义范围。

## Input
- `project_id`
- `document_id`
- `version_id`
- 上游 Skill 输出
- 原文或结构化中间结果

## Output
必须输出稳定 ID、结构化结果以及 provenance/来源关联字段。

## Execution Rules
1. 只使用输入中存在或可由明确规则推导的信息，不编造事实。
2. 所有结果尽可能绑定 `project_id`、`document_id`、`version_id`。
3. Fact、Claim、Evidence、Reasoning 必须保留来源链。
4. 发现冲突时输出冲突状态，不擅自裁决。
5. 不得在没有复用策略的情况下跨项目复制项目专属事实。

## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。


## falsifiable_by：论断的必填项（V2.8）

### 为什么必填

```
claim 说不清「什么能推翻它」→ 不是判断，是口号
```

**实测**：19 条 claim 全部补了 `falsifiable_by`，缺失的视为口号不抽。

### 四类 claim 的 falsifiable_by

| claim_type | falsifiable_by |
|---|---|
| `conclusion` | 找到一条证据表明该判断不成立 |
| `recommendation` | 找出更优方案或证明该建议不可行 |
| `hypothesis` | 实际结果与预测不符 |
| `inference` | 证明前提成立但结论不成立，或存在其他原因 |

### 验证时的三个检查

```python
① claim_type 在四类枚举内
② falsifiable_by 非空
③ status 与证据一致：
     supported     → 至少 1 条 SUPPORT 证据
     contradicted  → 至少 1 条 CONTRADICT
     unverified    → 证据为空或不足
```

### 必要性推导实测（3/4 成立）

```
CL-必要性-01  引 十三五规划          ✓
CL-必要性-02  引 大数据发展纲要      ✓
CL-必要性-03  【无依据】            ✗ ← 断点
CL-必要性-04  引 双一流支持通知      ✓
      ↓
CL-结论-02「综上所述…十分必要」
```

**判定：不完全成立** —— 缺一条前提的依据，「综上所述」的归纳有断点。

**另发现**：结论把「**推动**双一流」改成「**响应**双一流」——从主动贡献降为被动配合，语义弱化。

### 工具

```bash
scripts/validate_graph.py
  · claim_type 不在四类 → ERROR
  · falsifiable_by 缺失 → WARN（视为口号）
```

## 工序（四段式）

**契约**

```json
{"validation": {"required": ["claim", "status", "reason"],
                "status": {"enum": ["supported", "contradicted", "unverified"]}}}
```

**执行**

```python
def validate(claim, graph) -> dict:
    reasons = []
    if not claim.get("falsifiable_by"): reasons.append("缺 falsifiable_by")
    if claim["claim_type"] not in CLAIM_TYPES: reasons.append("claim_type 越界")
    ev = graph.evidence_of(claim)
    status = ("supported" if all_support(ev) else
              "contradicted" if any_contradict(ev) else "unverified")
    return {"claim": claim["id"], "status": status, "reason": "; ".join(reasons)}

assert validation["status"] in ("supported", "contradicted", "unverified")
```

**门禁 P13 · 验证三态**

```
每条 claim 有 status；supported 必须有至少 1 条 SUPPORT；缺 falsifiable_by 直接拒
```

**代价（实测）**

```
19 条 claim 逐条标 falsifiable_by
必要性推导 3/4 前提有依据 → 结论「综上所述」仍写死
另发现结论把「推动双一流」改成「响应双一流」→ 语义弱化
```
