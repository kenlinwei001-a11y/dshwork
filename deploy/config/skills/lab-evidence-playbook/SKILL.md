---
name: lab-evidence-playbook
description: 按抽取侧的槽位任务单（audit_tasks.jsonl + slots.schema.json）把检测报告与过程文档填成 report_slots.json 与 report_spans.json：只填值、只定位，不判 PASS/FAIL。校验脚本内嵌在本文，不占专家资源位。
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
**不整份加载文档**：先按文档画像（P1–P10）切出候选行（label/value），再逐槽映射。

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
6. 写两个 JSON，跑本文附录的校验脚本（槽覆盖、quote 可检索、单位）。

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

把下面整段保存为 `verify_slots.py` 再跑：`python3 verify_slots.py --out <产出目录> --strict`

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""证据抽取校验：只查确定性项，不判 PASS/FAIL。

校验五件事：
  1. 覆盖率：audit_tasks.jsonl 的每个 slot 在 report_slots.json 里有键（值可为 null）
  2. 定位：有值的槽必须有 report_spans 条目且 quote 非空；quote 能在报告正文命中（给了 --report-text 才查）
  3. 类型：schema 声明 number 的槽，值必须是数字或可解析数字
  4. 缺失清单：值为 null 的槽必须出现在 missing 里，并带原因
  5. 不越权：本包内不得出现 verdict 字段（判定归审核专家）
"""
import argparse
import json
import os
import sys


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def norm(s):
    return ''.join((s or '').split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--report-text', default='')
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    O = a.out

    tasks = []
    tp = os.path.join(O, 'audit_tasks.jsonl')
    if os.path.exists(tp):
        tasks = [json.loads(l) for l in open(tp, encoding='utf-8') if l.strip()]

    slots = load(os.path.join(O, 'machine', 'report_slots.json'), {}) or {}
    spans = load(os.path.join(O, 'machine', 'report_spans.json'), {}) or {}
    missing = load(os.path.join(O, 'machine', 'missing.json'), []) or []
    schema = load(os.path.join(O, 'slots.schema.json'), {}) or {}
    props = (schema.get('properties') or {})

    errs, warns = [], []
    task_slots = [t.get('slot') for t in tasks if t.get('slot')]

    no_key = [s for s in task_slots if s not in slots]
    if no_key:
        errs.append({'check': 'coverage', 'detail': f'{len(no_key)} 个槽没有键：{no_key[:8]}'})

    no_span = []
    for s in task_slots:
        v = slots.get(s)
        if v in (None, '', []):
            continue
        sp = spans.get(s) or {}
        if not sp.get('quote'):
            no_span.append(s)
        elif sp.get('unlocated'):
            warns.append({'check': 'locator', 'detail': f'{s} 标为 unlocated（不可辨），已登记'})
    if no_span:
        errs.append({'check': 'locator', 'detail': f'有值但无 quote：{no_span[:8]}'})

    if a.report_text:
        text = norm(open(a.report_text, encoding='utf-8').read())
        miss = [s for s in task_slots
                if (spans.get(s) or {}).get('quote') and norm(spans[s]['quote']) not in text]
        if miss:
            errs.append({'check': 'quote_hit', 'detail': f'{len(miss)} 条 quote 未命中报告原文：{miss[:8]}'})

    bad_type = []
    for s in task_slots:
        v = slots.get(s)
        if v in (None, '', []):
            continue
        want = (props.get(s) or {}).get('type')
        if want == 'number' and not isinstance(v, (int, float)):
            try:
                float(str(v))
            except Exception:
                bad_type.append({'slot': s, 'value': v, 'want': 'number'})
    if bad_type:
        errs.append({'check': 'type', 'detail': bad_type[:8]})

    null_slots = [s for s in task_slots if slots.get(s) in (None, '', [])]
    miss_ids = {m.get('slot') for m in missing if isinstance(m, dict)}
    undeclared = [s for s in null_slots if s not in miss_ids]
    if undeclared:
        errs.append({'check': 'missing_declared', 'detail': f'{len(undeclared)} 个空槽未登记原因：{undeclared[:8]}'})
    no_reason = [m for m in missing if isinstance(m, dict) and not m.get('reason')]
    if no_reason:
        errs.append({'check': 'missing_reason', 'detail': f'{len(no_reason)} 条缺失没有 reason'})

    verdict_keys = [k for k in slots if 'verdict' in str(k).lower()]

    out = {
        'out': O,
        'slots_total': len(task_slots),
        'slots_filled': len([s for s in task_slots if slots.get(s) not in (None, '', [])]),
        'missing_declared': len(missing),
        'errors': errs,
        'warnings': warns,
        'verdict_field_present': bool(verdict_keys),
        'status': 'OK' if not errs else 'FAIL',
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if verdict_keys:
        print('提示：证据包内不应出现 verdict 字段，判定归审核专家。', file=sys.stderr)
    if a.strict and errs:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
```
