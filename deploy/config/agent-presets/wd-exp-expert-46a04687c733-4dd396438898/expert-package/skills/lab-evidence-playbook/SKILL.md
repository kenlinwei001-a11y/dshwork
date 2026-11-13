---
name: lab-evidence-playbook
description: 按槽位任务单与 slots_candidate 把检测报告与过程文档填成 report_slots.json 与 report_spans.json：只填值、只定位，不判 PASS/FAIL。
---

# 实验室证据抽取 playbook（v3：候选槽驱动）

本技能已作为全局技能发布（`~/.agents/skills/lab-evidence-playbook`），本目录仅作专家包内的占位声明，避免重复维护。

- 执行入口：`python3 toolchain/run.py ev.*`（逻辑名见 `contracts/scripts.json`）
- 输入：`contracts/derived/slots_candidate.jsonl`、`machine/audit_tasks.jsonl`
- 输出：`report_slots.json`、`report_spans.json`、`tables.json`、`slot_hits.jsonl`、`qc_coverage.json`、`missing.json`
- 硬口径：不判 PASS/FAIL；ND 原样；不可辨标 unlocated；**桥接默认不写槽**

详细口径见全局技能 `lab-evidence-playbook`。
