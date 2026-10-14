#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键重建整个语料包（按 SOP 执行 + 逐环节记录 + 链尾比对）。

与旧版的区别（**这是防「降级/跳过」的关键**）：
  · 环节清单不再散落在本文件，而是取自 sop.py 的 **SOP 表**（单一真理）；
  · 每个环节执行后自动写「操作记录」quality/run_record/<id>.json
    （退出码 / 脚本哈希 / 产物哈希与大小 / 检查项 / 是否 NO-OP）；
  · 链尾执行 **SOP × 操作记录 比对**（verify_sop），任一缺口 → 非零退出。
    · SOP 有而记录无      → 缺记录
    · 记录有而 SOP 未声明  → 偷偷加/减步骤
    · 声明产物未生成/为空  → 缺产物
    · 跑了但没产生变更     → unexpected_noop（**本次「手工跑过→--fresh 后失效」事故的信号**）
    · 依赖顺序违反        → dependency_violated
连「跑完 exit=0 但门禁变差」这种情况也不再可能悄悄通过。
"""
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parent
# ★ 禁用字节码：本会话实测——在同一秒内反复改源码+跑链路时，
#   Python 的 mtime 粒度（1 秒）会判 __pycache__ 仍有效 ⇒ 加载**旧版字节码** ⇒
#   检查器基于过期逻辑持续发出**假指控**（"上游虚报"），排查多轮无果。
sys.dont_write_bytecode = True
import shutil as _sh
for _pc in BUILD.rglob("__pycache__"):
    _sh.rmtree(_pc, ignore_errors=True)

sys.path.insert(0, str(BUILD))
import sop  # noqa: E402

if "--fresh" in sys.argv:
    import shutil
    pkg = BUILD.parent / "SHUFE-BDC-2019-001"
    if pkg.exists():
        shutil.rmtree(pkg)
        print(f"[fresh] 已清除 {pkg.name}")
    rec = BUILD.parent / "SHUFE-BDC-2019-001" / "quality" / "run_record"
    print(f"[fresh] 操作记录目录将重建: {rec.name}")

rc = sop.run_all_recorded()

print("\n=== 链尾：SOP × 操作记录 比对 ===")
res = sop.verify_sop()
print(f"  SOP 环节 {res['sop_stages']} | 操作记录 {res['records']}"
      f" | 缺口 {res['gap_count']} | 判定 {res['verdict']}")
if res["by_kind"]:
    for k, v in sorted(res["by_kind"].items(), key=lambda x: -x[1]):
        print(f"    {k}: {v}")
if res["outputs_pending_review"]:
    print(f"  产物待人工确认的环节 {res['outputs_pending_review_count']} 个"
          f"（SOP 显式标注，不计为通过）：{res['outputs_pending_review']}")
for g in res["gaps"][:15]:
    print(f"    · [{g['kind']}] {g.get('stage','SOP')}: {g['detail'][:100]}")
print(f"\n  比对结果: {res['verdict']}  （明细 quality/sop_compliance.yaml）")

if rc != 0:
    raise SystemExit(f"[FAIL] 有阻塞环节失败，链路中止（SOP 比对见上）")
# 权威分级判定（链已跑完，此处才具备判定条件）
sys.path.insert(0, str(BUILD / "sop"))
import decision_packet as DP, trigger as TG  # noqa: E402
DP.build_packet(include_compliance=True)          # 按最终完成态重建工单
tv = TG.build_cards()
print(f"  触发分级：L0 {tv['summary']['L0']} / L1 {tv['summary']['L1']} / L2 {tv['summary']['L2']}")
for c in tv["cards"]:
    if c["level"] == "L0":
        print(f"    🔴 {c['id']} {c['title'][:50]} — {c['inconsistency'][:70]}")
if tv["blocking_count"] > 0:
    raise SystemExit(f"[FAIL] 权威判定：{tv['blocking_count']} 项 L0 阻塞 —— 人工确认后方可收尾")

if res["verdict"] != "pass":
    raise SystemExit("[FAIL] SOP 比对未通过 —— 拒绝以「完成」收尾（这正是本次要堵的洞）")
print("\n=== 全链路完成（SOP 比对通过）===")
