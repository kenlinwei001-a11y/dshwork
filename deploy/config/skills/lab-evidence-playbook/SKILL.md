---
name: lab-evidence-playbook
description: 按抽取侧的槽位任务单（audit_tasks.jsonl + slots.schema.json）把检测报告与过程文档填成 report_slots.json 与 report_spans.json：只填值、只定位，不判 PASS/FAIL。
---

# 实验室证据抽取 playbook（v2：槽位填充器）

## 定位

本 skill **不产出证据包叙事，只产出两个机器文件**：槽值 + 槽位在报告里的位置。
判定归审核专家与 `eval_slots`；证据抽取只负责“报告上写了什么、在哪一页哪一句”。

## 输入

| 文件 | 用途 |
|---|---|
| `machine/audit_tasks.jsonl` | 要填哪些槽（slot/label/doc_type/match_hints） |
| `machine/slots.schema.json` | 槽的类型、单位、匹配词 |
| `machine/ses.json` | 标准身份与指纹（核对报告声明的方法/标准） |
| 报告与过程文档 | 被测对象（PDF/DOCX/扫描件） |

**禁读** `human/`；禁读标准正文去“理解要求”——要求已经在任务单里。

## 输出（两个文件，唯一交接面）

```json
// report_slots.json
{"S001": "地表水", "S002": 0.9987, "S007": null}
// report_spans.json
{"S001": {"page": 1, "quote": "样品类型：地表水", "method": "field_label"},
 "S002": {"page": 3, "quote": "r=0.9987", "method": "table_cell"}}
```

- 找到值 → 写 slot + span；
- 文档里确实没有 → `value=null`（缺证），不猜；
- 有字但不可辨 → 不填值，写 `spans[slot]={"unlocated":true,"reason":"..."}`。

## 执行顺序

1. 读任务单，按 `doc_type` 分派到具体文档（报告/原始记录/流转单/仪器记录/试剂配制/质控）。
2. 逐槽用 `match_hints` 定位；表值按 `table_header` 策略取单元格。
3. 每个命中写 span（page + quote，quote 必须能在文档中检索命中）。
4. 对账：样品编号、数量、日期、方法、仪器编号在报告与记录间是否一致 → 写 `consistency_flags`（只报事实，不判定）。
5. 缺件：任务单需要的 doc_type 缺失 → `missing_documents`。
6. 写两个 JSON，跑 `--verify` 自检（槽覆盖、quote 可检索、单位）。

## 硬口径

- **不判 PASS/FAIL、不引 rule_id、不读标准**。
- ND / 未检出 / `<检出限` 原样保留，不转成 0。
- 同一槽多处出现且值不同 → 都写进 `candidates`，不替审核选。
- OCR 不可辨标 unlocated，不猜字。
- 每槽必须能回答：值来自哪一页哪一句。

## 交接

抽取完成后交：`report_slots.json` + `report_spans.json` + `missing_documents` + `consistency_flags`。
下一棒：报告审核（C1/C6）与过程文档审核（C2–C5/C7）按 category 分工判定，最后由裁定专家合并。

## 附：校验脚本（内嵌，无需单独文件）

**为什么要内嵌**：专家包有资源数量上限，.md 又不能走资源通道；把校验脚本放进 SKILL.md，需要时由 agent 写到 `verify_slots.py` 再跑，不占资源位。

用法：把下面整段保存为 `verify_slots.py`，然后
`python3 toolchain/run.py ev.verify_slots --out <产出目录> --strict`
## 校验脚本

本 skill **不内嵌脚本副本**——执行体只有一处：

```
python3 toolchain/run.py ev.verify_slots --out <运行目录> --report-text <报告txt> --record-text <记录txt...> --strict
python3 toolchain/run.py std.check_gate --out <运行目录> --node lab-evidence --require machine/report_slots.json machine/report_spans.json
```

查五件：槽覆盖、有值必有 quote、quote 在报告**或**记录原文连续命中、空槽有原因、**出现 verdict 字段即失败**（判定越权）。
结果写入 `trail.jsonl`；门禁只认最后一条，无记录即未执行。
