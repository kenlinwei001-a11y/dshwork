#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计留痕：让报告的每一个数字都能倒查。

可研要过评审、要备案，出了问题要能说清楚"这个数是怎么来的"。
人写的报告答不上来——它只有结论没有过程。图驱动的报告能答上来，
但前提是过程被记下来了。这个脚本负责记。

三样东西：
  派生轨迹  每个计算值用了哪条规则、引用了哪些节点、上溯到哪些叶子
  变更日志  谁在什么时候改了什么、影响了什么、谁确认的
  指纹      对图状态与轨迹取哈希，事后可验证是否被改动过

指纹用 HMAC-SHA256。密钥由调用方通过环境变量 FSR_AUDIT_KEY 提供；
未提供时退化为纯 SHA256（仍可验完整性，但无法证明来源）。

用法：
    python3 scripts/audit.py trace <project.yaml> -o audit/
    python3 scripts/audit.py log <project.yaml> --entry entry.json -o audit/
    python3 scripts/audit.py verify audit/
"""

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from impact import ImpactAnalyzer  # noqa: E402
from assets import load_l0, guard  # noqa: E402
import validators as V  # noqa: E402

KEY_ENV = "FSR_AUDIT_KEY"


def fingerprint(payload_bytes):
    key = os.environ.get(KEY_ENV)
    if key:
        return {"alg": "HMAC-SHA256",
                "value": hmac.new(key.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest(),
                "keyed": True}
    return {"alg": "SHA256", "value": hashlib.sha256(payload_bytes).hexdigest(),
            "keyed": False,
            "note": f"未设置 {KEY_ENV}，指纹只能验完整性，不能证明来源"}


def _json_default(o):
    """YAML 会把 2024-01-01 解析成 date 对象，JSON 不认。统一转 ISO 字符串。"""
    import datetime
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=_json_default).encode("utf-8")


# =============================================================================
def build_trace(proj):
    """派生轨迹：每个计算值的完整来源链。"""
    core, argu, deriv = load_l0()
    v = V.Validator(core, argu, deriv, proj)
    v.run()
    an = ImpactAnalyzer(proj, core, argu, deriv)

    rules = {r.get("id"): r for r in (proj.get("rules") or []) if isinstance(r, dict)}
    ev = proj.get("evidence") or {}
    entries = []

    for node, t in v.trace.items():
        r = rules.get(t["rule"], {})
        info = an.explain(node)
        leaves = []
        for leaf in info["leaves"]:
            n = (proj.get("nodes") or {}).get(leaf) or {}
            leaves.append({"node": leaf, "value": n.get("value"), "unit": n.get("unit"),
                           "provenance": n.get("provenance"), "source": n.get("source")})
        basis = r.get("basis")
        entries.append({
            "node": node,
            "value": round(t["value"], 6) if isinstance(t["value"], float) else t["value"],
            "unit": r.get("unit"),
            "rule": t["rule"],
            "formula": r.get("formula"),
            "direct_inputs": t["used"],
            "leaf_inputs": leaves,
            "basis": basis,
            "basis_evidence": ev.get(basis) if basis else None,
            "serves": r.get("serves"),
        })

    given = [{"node": k, "value": n.get("value"), "unit": n.get("unit"),
              "provenance": n.get("provenance"), "source": n.get("source")}
             for k, n in sorted((proj.get("nodes") or {}).items())
             if (n or {}).get("provenance") in ("E1_given", "E2_normative",
                                                "E3_external", "E6_administrative")]

    return {
        "project": (proj.get("project") or {}).get("id"),
        "derived": sorted(entries, key=lambda x: x["node"]),
        "given_inputs": given,
        "check_summary": {
            "errors": sum(1 for f in v.findings if f.severity == "error"),
            "warnings": sum(1 for f in v.findings if f.severity == "warning"),
            "passed": len(v.passed),
        },
    }


def write_trace(proj, out_dir):
    tr = build_trace(proj)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    body = canonical(tr)
    (out / "trace.json").write_bytes(body)
    fp = fingerprint(body)
    fp["file"] = "trace.json"
    (out / "trace.fingerprint.json").write_text(
        json.dumps(fp, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"派生轨迹已写入 {out/'trace.json'}")
    print(f"  派生节点 {len(tr['derived'])} 个，给定输入 {len(tr['given_inputs'])} 个")
    print(f"  指纹 {fp['alg']}: {fp['value'][:32]}…")
    if not fp["keyed"]:
        print(f"  {fp['note']}")

    unbacked = [e["node"] for e in tr["derived"] if not e["basis"]]
    if unbacked:
        print(f"\n  {len(unbacked)} 个派生值未绑定依据（basis），审计时无法说明计算规则的出处：")
        for n in unbacked[:8]:
            print(f"    · {n}")
    return 0


# =============================================================================
def append_log(proj, entry, out_dir):
    """追加一条变更日志。链式哈希——改中间任何一条，后面全部失配。"""
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    log_path = out / "changelog.jsonl"
    prev_hash = "0" * 64
    if log_path.exists():
        lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if lines:
            prev_hash = json.loads(lines[-1])["hash"]

    required = ["at", "actor", "source", "node", "old", "new"]
    missing = [f for f in required if f not in entry]
    if missing:
        print(f"变更日志缺必填字段：{missing}")
        print("必填：at 时间 / actor 确认人 / source 变更来源(客户编辑|图上修改) / node / old / new")
        return 2

    core, argu, deriv = load_l0()
    an = ImpactAnalyzer(proj, core, argu, deriv)
    try:
        imp = an.analyze({entry["node"]: entry["new"]})
        entry["impact"] = {
            "derived_changed": list(imp["delta"].keys()),
            "sections_to_rewrite": [s["id"] for s in imp["affected_sections"]],
            "new_errors": len(imp["errors_after_change"]),
        }
    except Exception as e:
        entry["impact"] = {"error": str(e)}

    entry["prev_hash"] = prev_hash
    entry["hash"] = hashlib.sha256(canonical(
        {k: v for k, v in entry.items() if k != "hash"})).hexdigest()

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"已追加变更日志：{entry['node']} {entry['old']} → {entry['new']}")
    print(f"  影响：派生 {len(entry['impact'].get('derived_changed', []))} 项，"
          f"章节 {len(entry['impact'].get('sections_to_rewrite', []))} 章")
    print(f"  链式哈希 {entry['hash'][:32]}…")
    return 0


# =============================================================================
def verify(out_dir):
    out = Path(out_dir)
    ok = True

    tp, fp_path = out / "trace.json", out / "trace.fingerprint.json"
    if tp.exists() and fp_path.exists():
        rec = json.loads(fp_path.read_text(encoding="utf-8"))
        now = fingerprint(tp.read_bytes())
        if rec["alg"] != now["alg"]:
            print(f"派生轨迹：算法不匹配（记录 {rec['alg']}，当前 {now['alg']}）")
            print(f"  多半是 {KEY_ENV} 与生成时不一致")
            ok = False
        elif rec["value"] != now["value"]:
            print("派生轨迹：指纹不符 —— trace.json 在生成后被改动过")
            ok = False
        else:
            print(f"派生轨迹：指纹一致 ({rec['alg']})")
    else:
        print("派生轨迹：未找到 trace.json 或指纹文件")

    log_path = out / "changelog.jsonl"
    if log_path.exists():
        prev = "0" * 64
        n = 0
        for i, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("prev_hash") != prev:
                print(f"变更日志：第 {i} 条断链 —— 前序哈希不匹配")
                ok = False
                break
            calc = hashlib.sha256(canonical(
                {k: v for k, v in e.items() if k != "hash"})).hexdigest()
            if calc != e.get("hash"):
                print(f"变更日志：第 {i} 条被篡改 —— 内容哈希不符")
                ok = False
                break
            prev = e["hash"]
            n += 1
        else:
            print(f"变更日志：{n} 条记录链式校验通过")
    else:
        print("变更日志：未找到 changelog.jsonl")

    print("\n审计结果：" + ("完整" if ok else "存在异常，需人工核查"))
    return 0 if ok else 1


# =============================================================================
@guard
def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    out = argv[argv.index("-o") + 1] if "-o" in argv else "audit"

    if cmd == "verify":
        return verify(argv[2] if len(argv) > 2 else "audit")

    if len(argv) < 3:
        print("需要 <project.yaml>")
        return 2
    proj = yaml.safe_load(Path(argv[2]).read_text(encoding="utf-8"))

    if cmd == "trace":
        return write_trace(proj, out)
    if cmd == "log":
        if "--entry" not in argv:
            print("需要 --entry entry.json")
            return 2
        entry = json.loads(Path(argv[argv.index("--entry") + 1]).read_text(encoding="utf-8"))
        return append_log(proj, entry, out)

    print(f"未知命令 {cmd}。可用：trace / log / verify")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
