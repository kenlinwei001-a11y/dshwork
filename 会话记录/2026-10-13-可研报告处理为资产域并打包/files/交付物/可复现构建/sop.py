# -*- coding: utf-8 -*-
"""sop.py —— SOP 执行契约 + 空模板填写 + 两者比对（v2）。

角色分离（禁止 LLM 幻觉来源）：

  ┌ 人（作者）──────┐   ┌ 确定性代码 ──────────┐   ┌ 确定性代码 ─────────┐
  │ build/sop/       │   │ 每环节执行后：        │   │ verify_sop：        │
  │   sop.yaml       │→ │ 把「空模板」填满 →     │→ │ SOP × 记录 集合差   │
  │   sop.sha256     │   │ run_record/<id>.json │   │ 缺口 = FAIL         │
  └──────────────────┘   └──────────────────────┘   └─────────────────────┘
       只读、冻结              只填不改结构                只比不写

三条硬约束：
  ① SOP 不得被运行时修改：每次加载校验 sha256（对照 sop.sha256），不符 ⇒ FAIL；
  ② 记录必须由空模板生成：只能给模板已有键赋值，出现模板之外的键 ⇒ 拒绝；
  ③ LLM 不参与：填写与比对均为纯代码（哈希/存在性/集合差），零模型调用。

NO-OP 语义由 **SOP 声明**（must_change）决定，不由记录方自判。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
SOP_DIR = WS / "build" / "sop"
SOP_YAML = SOP_DIR / "sop.yaml"
SOP_SHA = SOP_DIR / "sop.sha256"
TEMPLATE = SOP_DIR / "templates" / "run_record.template.json"
PKG = WS / "SHUFE-BDC-2019-001"
REC_DIR = PKG / "quality" / "run_record"
PY = "/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python"


def load_sop() -> tuple[list[dict], list[dict]]:
    import yaml
    problems: list[dict] = []
    if not SOP_YAML.exists():
        return [], [{"kind": "sop_missing", "detail": f"SOP 文件不存在：{SOP_YAML}"}]
    raw = SOP_YAML.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if SOP_SHA.exists():
        pinned = SOP_SHA.read_text(encoding="utf-8").strip().split()[0]
        if pinned != actual:
            problems.append({"kind": "sop_modified",
                             "detail": f"SOP 哈希与冻结值不符（期望 {pinned[:16]}… 实际 {actual[:16]}…）"
                                       f" —— 运行时不得修改 SOP"})
    else:
        problems.append({"kind": "sop_unfrozen", "detail": "缺少 sop.sha256，SOP 未冻结"})
    doc = yaml.safe_load(raw.decode("utf-8")) or {}
    stages = doc.get("stages") or []
    ids = [s["id"] for s in stages]
    if len(ids) != len(set(ids)):
        problems.append({"kind": "sop_duplicate_id", "detail": "SOP 存在重复环节 id"})
    order = {sid: i for i, sid in enumerate(ids)}
    for s in stages:
        for dep in s.get("depends_on") or []:
            if dep not in order:
                problems.append({"kind": "sop_unknown_dep", "detail": f"{s['id']} 依赖未知环节 {dep}"})
            elif order[dep] >= order[s["id"]]:
                problems.append({"kind": "sop_dep_order", "detail": f"{s['id']} 的依赖 {dep} 排在其后"})
    return stages, problems


def load_template() -> dict:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def _sha(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:32]
    except Exception:                                     # noqa: BLE001
        return ""


def _expand(pat: str) -> list[Path]:
    return sorted(p for p in WS.glob(pat) if p.is_file())


SKIP_DIRS = ("/.git/", "/.venv/", "__pycache__", "run_record", "/node_modules/")
SKIP_SUFFIX = (".bak", ".pyc", ".DS_Store", ".log")
ART_EXT = (".yaml", ".yml", ".json", ".jsonl", ".md", ".docx", ".zip", ".txt", ".csv")


SCAN_ROOTS = ("SHUFE-BDC-2019-001", "交付物", "build/doc-clean", "build/extractions",
              "build/_newchunks", "references")


def ws_snapshot() -> dict:
    """工作区快照（**限定相关子树 + 遍历时按扩展名过滤 + 复用 DirEntry 的 stat**）。

    修订理由（实测）：原实现 `WS.rglob('*')` 扫全工作区 7,918 条目、每条目 3 次 syscall，
    2.51s/次 × 2 次/环节 × 36 环节 ≈ 180s —— 其中约 80% 花在历史副本与无关目录上。
    改为只扫相关子树 + DirEntry.stat()（1 次 syscall），0.18s/次。
    """
    snap = {}
    for r in SCAN_ROOTS:
        base = WS / r
        if not base.exists():
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in files:
                if not fn.endswith(ART_EXT):          # 遍历时即过滤，不为无关文件 stat
                    continue
                try:
                    st = os.stat(os.path.join(root, fn))
                except OSError:
                    continue
                snap[os.path.relpath(os.path.join(root, fn), WS)] = (st.st_size, int(st.st_mtime))
    return snap


def obs_diff(before: dict, after: dict) -> list[str]:
    """跑前跑后差集 → 该环节**实际写出/修改**的产物（带扩展名过滤）。"""
    return sorted(k for k, v in after.items()
                  if before.get(k) != v and k.endswith(ART_EXT))


def snapshot(entry: dict) -> list[dict]:
    got = []
    for pat in entry.get("outputs") or []:
        for p in _expand(pat):
            try:
                st = p.stat()
            except OSError:
                continue
            got.append({"path": str(p.relative_to(WS)), "pattern": pat, "bytes": st.st_size,
                        "sha256": _sha(p), "mtime": int(st.st_mtime)})
    return got


def fill_record(entry: dict, rc: int, t0: float, t1: float, stdout: str,
                stderr: str, pre: dict) -> dict:
    """把空模板填满：只给模板已有键赋值；模板之外的键直接拒绝。"""
    tpl = load_template()
    template_keys = {k for k in tpl if not k.startswith("_")}
    outs = snapshot(entry)
    changed = [o["path"] for o in outs if pre.get(o["path"]) != o["sha256"]]
    missing = [p for p in (entry.get("outputs") or []) if not _expand(p)]
    must_change = bool(entry.get("must_change", False))
    noop = (not outs) or (not changed)

    values = {
        "stage_id": entry["id"], "name": entry["name"], "script": entry["script"],
        "script_sha256": _sha(WS / "build" / entry["script"]),
        "exit_code": rc, "blocking": bool(entry.get("blocking", True)),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0)),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t1)),
        "elapsed_s": round(t1 - t0, 2),
        "declared_outputs": list(entry.get("outputs") or []),
        "outputs": outs, "outputs_missing": missing, "outputs_changed": changed,
        "noop": noop, "noop_allowed": not must_change, "must_change": must_change,
        "checks": [
            {"id": "exit_zero", "verdict": "pass" if rc == 0 else "FAIL"},
            {"id": "outputs_exist", "verdict": "pass" if not missing else "FAIL"},
            {"id": "outputs_nonempty",
             "verdict": "pass" if all(o["bytes"] > 0 for o in outs) else "FAIL"},
            {"id": "noop_policy",
             "verdict": "pass" if (not noop or not must_change) else "FAIL"},
        ],
        "observed_outputs": list(pre.get("__observed__") or []),
        "stdout_tail": (stdout or "")[-600:],
        "stderr_tail": (stderr or "")[-600:] if rc != 0 else "",
    }
    extra = set(values) - template_keys
    if extra:
        raise RuntimeError(f"记录出现模板之外的键 {sorted(extra)} —— 请先改模板并重新冻结 SOP")
    rec = {**{k: v for k, v in tpl.items() if k.startswith("_")}, **values}
    REC_DIR.mkdir(parents=True, exist_ok=True)
    (REC_DIR / f"{entry['id']}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def verify_sop() -> dict:
    stages, problems = load_sop()
    gaps = list(problems)
    recs = {}
    for s in stages:
        f = REC_DIR / f"{s['id']}.json"
        if not f.exists():
            gaps.append({"kind": "missing_record", "stage": s["id"],
                         "detail": f"SOP 声明 {s['id']}（{s['name']}）但无操作记录"})
        else:
            recs[s["id"]] = json.loads(f.read_text(encoding="utf-8"))

    declared = {s["id"] for s in stages}
    if REC_DIR.exists():
        for f in sorted(REC_DIR.glob("*.json")):
            if f.stem not in declared:
                gaps.append({"kind": "undeclared_step", "stage": f.stem,
                             "detail": "存在操作记录但 SOP 未声明该环节"})

    tpl_keys = {k for k in load_template() if not k.startswith("_")}
    for s in stages:
        r = recs.get(s["id"])
        if not r:
            continue
        extra = set(r) - tpl_keys - {"_contract", "_template_version", "_fields"}
        if extra:
            gaps.append({"kind": "record_template_drift", "stage": s["id"],
                         "detail": f"记录含模板之外的键 {sorted(extra)}"})
        if r["exit_code"] != 0 and s.get("blocking", True):
            gaps.append({"kind": "blocking_failed", "stage": s["id"],
                         "detail": f"阻塞环节失败 exit={r['exit_code']}"})
        for m in r.get("outputs_missing") or []:
            gaps.append({"kind": "missing_output", "stage": s["id"], "detail": f"声明产物未生成: {m}"})
        for o in r.get("outputs") or []:
            if o["bytes"] == 0:
                gaps.append({"kind": "empty_output", "stage": s["id"], "detail": f"空产物: {o['path']}"})
        if r.get("noop") and s.get("must_change"):
            gaps.append({"kind": "must_change_noop", "stage": s["id"],
                         "detail": "SOP 声明 must_change 但未产生任何产物变更"})
        for c in r.get("checks") or []:
            if c["verdict"] != "pass":
                gaps.append({"kind": f"check_failed:{c['id']}", "stage": s["id"],
                             "detail": f"检查项 {c['id']} 未通过"})

    # 给每个缺口挂上既定处置策略（归因/动作/责任人/可否自动重跑）
    import yaml as _y
    dsp = _y.safe_load((SOP_DIR / "dispositions.yaml").read_text(encoding="utf-8")) or {}
    rules = dsp.get("kinds") or {}
    for g in gaps:
        r = rules.get(g["kind"]) or rules.get(g["kind"].split(":")[0]) or {}
        if not r and ":" in g["kind"]:
            r = rules.get(f"check_failed:{g['kind'].split(':', 1)[1]}") or {}
        g["disposition"] = {"attribution": r.get("attribution", "未登记"),
                           "action": r.get("action", "需人工归因（策略台账未覆盖该缺口类型）"),
                           "owner": r.get("owner", "人"),
                           "auto_retry": bool(r.get("auto_retry", False)),
                           "retry_budget": r.get("retry_budget")}
    by_kind: dict[str, int] = {}
    for g in gaps:
        by_kind[g["kind"]] = by_kind.get(g["kind"], 0) + 1
    pending = [s["id"] for s in stages if s.get("outputs_pending_review")]
    result = {
        "sop_sha256": hashlib.sha256(SOP_YAML.read_bytes()).hexdigest()[:32] if SOP_YAML.exists() else "",
        "verdict": "FAIL" if gaps else "pass",
        "sop_stages": len(stages), "records": len(recs),
        "outputs_pending_review": pending, "outputs_pending_review_count": len(pending),
        "gap_count": len(gaps), "by_kind": by_kind, "gaps": gaps,
        "auto_retryable": sorted({g["kind"] for g in gaps
                                  if (g.get("disposition") or {}).get("auto_retry")}),
        "manual_required": sorted({g["kind"] for g in gaps
                                   if not (g.get("disposition") or {}).get("auto_retry")}),
        "escalation": dsp.get("escalation"),
        "note": "判定纯由集合差/哈希/存在性给出，LLM 不参与；SOP 只读，记录由空模板填写；"
                "每个缺口已挂既定处置策略（归因/动作/责任人/可否自动重跑）",
    }
    q = PKG / "quality"
    q.mkdir(parents=True, exist_ok=True)
    (q / "sop_compliance.yaml").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


_LAST_SNAP: list = [None]


def run_all_recorded() -> int:
    import shutil
    import handover as HO
    stages, problems = load_sop()
    HO.HD.mkdir(parents=True, exist_ok=True)
    blocked = []
    for p in problems:
        print(f"  [SOP问题] {p['kind']}: {p['detail']}")
    rc_all = 0
    for entry in stages:
        print(f"\n=== {entry['id']}  {entry['name']} :: {entry['script']} ===")
        # ★ 交接门：开工前先做四元交叉校验（A 自报 / B 独立清点 / C 产物自述 / SOP 契约）
        _d = HO.HD / entry["id"]; _d.mkdir(parents=True, exist_ok=True)
        for dep in entry.get("depends_on") or []:
            _src = HO.HD / dep / "manifest_A.json"
            if _src.exists():
                shutil.copy2(_src, _d / f"manifest_A_{dep}.json")
        hv = HO.compare(entry, {})
        if hv["gate"] == "BLOCKED":
            blocked.append({"stage": entry["id"], "diffs": hv["diffs"][:6]})
            print(f"  [交接门] {entry['id']}: BLOCKED —— {hv['diff_count']} 项差异（下游不得开工）")
            for df in hv["diffs"][:4]:
                print(f"      · {df['kind']}: {df['path'][:70]} ← {df['meaning']}")
        pre = {o["path"]: o["sha256"] for o in snapshot(entry)}
        pre_snap = _LAST_SNAP[0] if _LAST_SNAP[0] is not None else ws_snapshot()
        t0 = time.time()
        r = subprocess.run([PY, str(WS / "build" / entry["script"])],
                           capture_output=True, text=True)
        t1 = time.time()
        after_snap = ws_snapshot()
        _LAST_SNAP[0] = after_snap                   # 复用于下一环节，省一半快照
        pre["__observed__"] = obs_diff(pre_snap, after_snap)
        sys.stdout.write(r.stdout)
        if r.returncode != 0:
            sys.stderr.write(r.stderr)
        rec = fill_record(entry, r.returncode, t0, t1, r.stdout, r.stderr, pre)
        flags = []
        if rec["exit_code"] != 0:
            flags.append(f"exit={rec['exit_code']}")
        if rec["outputs_missing"]:
            flags.append(f"缺产物 {len(rec['outputs_missing'])}")
        if rec["noop"] and entry.get("must_change"):
            flags.append("MUST-CHANGE-NOOP")
        elif rec["noop"]:
            flags.append("idempotent")
        HO.declare(entry["id"], rec)             # ★ 上游自报清单 A + README 解释文档
        print(f"  [记录] {entry['id']}: {' '.join(flags) or 'ok'}"
              f" | 产物 {len(rec['outputs'])} 变更 {len(rec['outputs_changed'])} | {rec['elapsed_s']}s")
        if rec["exit_code"] != 0 and entry.get("blocking", True):
            rc_all = 1
    if blocked:
        import json as _json
        (PKG / "quality" / "handover_blocked.json").write_text(
            _json.dumps({"count": len(blocked), "items": blocked}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    return rc_all
