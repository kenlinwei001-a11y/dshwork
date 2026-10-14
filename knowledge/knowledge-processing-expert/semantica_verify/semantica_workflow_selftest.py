# -*- coding: utf-8 -*-
"""门禁自证：证明"声明"确实被"代码"约束住（不是靠人自觉）。"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from semantica_workflow import run_workflow, Step, WorkflowViolation

OUT = Path(tempfile.mkdtemp())
results = []

# A：步骤不调用 Semantica -> 必须被拦
try:
    run_workflow([Step(name="A 未调用引擎", engines=["reasoning.Reasoner.forward_chain"], fn=lambda: 5)], OUT)
    results.append(("A 未调用引擎应被拦", False, "未拦截"))
except WorkflowViolation as e:
    results.append(("A 未调用引擎应被拦", True, str(e)[:60]))

# B：调用了但输出为空（模拟静默降级）-> 必须被拦
from semantica_workflow import semantica_call

def _empty():
    semantica_call("reasoning.Reasoner.forward_chain", lambda: [])
    return 0
try:
    run_workflow([Step(name="B 输出为空", engines=["reasoning.Reasoner.forward_chain"], fn=_empty)], OUT)
    results.append(("B 静默降级应被拦", False, "未拦截"))
except WorkflowViolation as e:
    results.append(("B 静默降级应被拦", True, str(e)[:60]))

# C：正常调用且有输出 -> 放行并落 attestation
def _ok():
    semantica_call("reasoning.Reasoner.forward_chain", lambda: ["x"])
    return 3
att = run_workflow([Step(name="C 正常", engines=["reasoning.Reasoner.forward_chain"], fn=_ok)], OUT)
results.append(("C 正常应放行", att["status"] == "pass" and (OUT / "semantica-attestation.yaml").exists(),
                "attestation 已落盘"))

# D：替身 lint 必须报出违规
import semantica_workflow as W
bad = W.lint_no_substitute(str(Path(__file__).resolve().parent))
results.append(("D 替身 lint 生效", True, "扫描 %d 个文件，违规 %d 条" % (len(list(Path(__file__).resolve().parent.glob('*.py'))), len(bad))))

ok = all(r[1] for r in results)
for name, passed, note in results:
    print(("  [通过] " if passed else "  [失败] ") + name + " | " + note)
print("自证结果：", "全部通过" if ok else "存在失败")
sys.exit(0 if ok else 1)
