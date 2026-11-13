---
name: lab-evidence-playbook
description: 按抽取侧槽位任务单（audit_tasks.jsonl + slots.schema.json）把检测报告与过程文档填成 report_slots.json 与 report_spans.json：只填值、只定位，不判 PASS/FAIL。校验脚本内嵌在 SKILL.md。
---

# 实验室证据抽取 playbook（v2：槽位填充器）

本技能已作为**全局技能**发布（`~/.agents/skills/lab-evidence-playbook`），含完整的校验脚本与字段说明。
本目录仅作专家包内的占位声明，避免重复维护：

- 执行入口：`lab-evidence-playbook` 技能正文（含 `verify_slots.py` 内嵌代码）
- 输入：`machine/audit_tasks.jsonl`、`machine/slots.schema.json`、`machine/ses.json`
- 输出：`machine/report_slots.json`、`machine/report_spans.json`、`missing_documents`、`consistency_flags`
- 硬口径：不判 PASS/FAIL、不引 rule_id、不读标准；ND 原样保留；不可辨标 unlocated

详细口径见全局技能 `lab-evidence-playbook`。
