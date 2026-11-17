# ND（未检出）判定口径

## 口径（2026-11-16 定）

报告以 **ND / 未检出** 表述某测定值时，判 **PASS**，但必须带三件事：

1. `verdict_basis: derived_from_ND`——标明这是**推定**，不是实测比较；
2. `message` 写明「据 ND 推定，非实测值」；
3. `anchor.quote` 指向报告/记录里那句 ND（定位仍要可命中）。

## 理由

- 标准原文（如 HJ 84-2016 11.1）要求「空白值不得超出方法检出限（0.005 mg/L）」。
- 实验室以 ND 报出，含义是**低于检出限**；低于检出限 ⇒ 必然 ≤ 检出限 ⇒ 满足该条。
- 因此结论可由「实验室自己的表述 + 标准定义」推出，属 `derived`，不是编数。

## 不适用（必须判 UNVERIFIABLE）

下列任一成立时，ND 不能推定 PASS：

| 条件 | 处理 |
|---|---|
| 报告未说明 ND 的定义（是 <检出限 还是 <测定下限） | UNVERIFIABLE，要求实验室声明 |
| 该条阈值是**下限类**（如「不得低于 X」「≥X」） | ND 反而可能不满足，UNVERIFIABLE |
| 阈值单位与 ND 判定口径不一致（如以浓度报 ND，条款以吸光度判） | UNVERIFIABLE |
| 同批同时存在 ND 与 0 两种写法 | CONFLICT_PENDING，先统一写法 |

## 实现

`std.bucket_judge --nd-policy pass|unverifiable`，默认 `pass`；判定结果里带
`policy: nd-policy-2026-11-16`，便于回溯当时用的是哪版口径。
