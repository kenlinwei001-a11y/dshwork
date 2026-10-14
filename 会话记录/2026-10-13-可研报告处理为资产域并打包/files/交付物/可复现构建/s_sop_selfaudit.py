# -*- coding: utf-8 -*-
"""s9 —— SOP 自审 + 不一致触发（产卡片）。L0 缺口交由链路尾部阻断。"""
import json, sys
from pathlib import Path
WS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WS / "build" / "sop"))
import decision_packet, trigger  # noqa: E402
p = decision_packet.build_packet(include_compliance=False)
t = trigger.build_cards()
print(json.dumps({"tickets": p["tickets"], "L1": t["summary"]["L1"],
                  "L2": t["summary"]["L2"]}, ensure_ascii=False, indent=2))
# 链内**只导出卡片**：链尚未跑完，此处判定无意义（会拿半成品比标准）。
# 权威判定统一在链尾（run_all 收尾）执行 —— 那里 36 环节已全部完成。
print(json.dumps({"in_chain": True,
                  "note": "链内仅导出卡片；权威 L0 判定在链尾执行"}, ensure_ascii=False))
