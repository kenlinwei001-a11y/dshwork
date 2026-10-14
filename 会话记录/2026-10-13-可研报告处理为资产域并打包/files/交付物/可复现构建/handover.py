# -*- coding: utf-8 -*-
"""handover —— 环节间「基于文档的四元交接校验」。

四份清单来自**四个独立来源**，故意不互相引用：

  A  上游自报清单      handover/<stage>/manifest_A.json（+ README.md 解释文档）
                       上游说「我产出了这些」——**可能虚报**（本会话已发生过伪造 id）
  B  下游独立清点      handover/<stage>/manifest_B.json
                       下游**不读 A**，只按 SOP 契约去**实际读产物**（扫盘 + 哈希 +
                       可解析性 + 行数），即「我亲眼看到这些」
  C  产物自述清单      handover/<stage>/manifest_C.json
                       从**产物内容本身**读出的元数据（manifest.status / 节点数 /
                       闸门 verdict / jsonl 行数）——即「产物自己怎么说」
  SOP 该环节 outputs 声明——契约说「应该有这些」

差异分类（每条都指向一个具体的失败模式）：
  A∖B  上游虚报：自报有、实际不存在            ⇒ 幻觉/未落盘
  B∖A  上游漏报：实际有、未自报                ⇒ 记录不全
  B∖SOP 契约外产物：实际有、SOP 未声明          ⇒ 规范漏项
  SOP∖B 契约未兑现：SOP 声明、实际没有          ⇒ 未产出
  C≠A/B 产物自述与清单不符（如 manifest.status 与声称状态不一致）⇒ 自相矛盾

交接门：四元比对通过 ⇒ 写 CONFIRMED（下游方可开工）；不通过 ⇒ BLOCKED + 工单。
目的：**用几个独立来源的交叉替代单 agent 自证**，把幻觉挡在环节边界上。
"""
from __future__ import annotations

import hashlib
import json
from fnmatch import fnmatch
from pathlib import Path

HANDOVER_VERSION = "v4-20261014"      # 诊断标志：确认链路加载的是哪份实现
WS = Path(__file__).resolve().parent.parent
PKG = WS / "SHUFE-BDC-2019-001"
HD = PKG / "handover"
REC = PKG / "quality" / "run_record"


SOP_YAML = WS / "build" / "sop" / "sop.yaml"


def _write_gate(d: Path, res: dict) -> None:
    """★ 门禁落盘必须**互斥**：先删掉两个标记再写当前结果。

    缺陷（实测）：原实现只写 CONFIRMED 或 BLOCKED，不删另一个 ⇒ 旧一轮的标记残留，
    **陈旧证据与当前证据无法区分** —— 我据此做出过整套虚假判断（把上一轮的 BLOCKED
    当成最新结果，编出"8 项差异/三处取数不一致"）。
    另加 generated_at 与 run 标识，使陈旧性可被检出。
    """
    from datetime import datetime
    res = dict(res)
    res["generated_at"] = datetime.now().isoformat(timespec="seconds")
    for name in ("CONFIRMED", "BLOCKED", "INVALID"):
        f = d / name
        if f.exists():
            f.unlink()
    (d / res["gate"]).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "gate.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:32]
    except Exception:
        return ""


def _jit(path: Path):
    """可解析性探测：json/yaml/jsonl 能否解析。"""
    try:
        t = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"parsable": False, "error": f"{type(e).__name__}: {e}"}
    try:
        if path.suffix == ".jsonl":
            n = sum(1 for l in t.splitlines() if l.strip())
            for l in t.splitlines():
                if l.strip():
                    json.loads(l)
            return {"parsable": True, "records": n}
        if path.suffix == ".json":
            d = json.loads(t)
            return {"parsable": True, "keys": (list(d)[:8] if isinstance(d, dict) else f"list[{len(d)}]")}
        if path.suffix in (".yaml", ".yml"):
            import yaml
            d = yaml.safe_load(t)
            return {"parsable": True, "keys": (list(d)[:8] if isinstance(d, dict) else f"list[{len(d)}]")}
    except Exception as e:
        return {"parsable": False, "error": f"parse: {type(e).__name__}: {e}"}
    return {"parsable": True, "text_chars": len(t)}


# ───────────────────────────────── A：上游自报（+ README 解释文档）
def declare(stage: str, record: dict) -> dict:
    d = HD / stage
    d.mkdir(parents=True, exist_ok=True)
    a = {"stage": stage, "script": record.get("script"),
         "exit_code": record.get("exit_code"),
         "declared_outputs": record.get("declared_outputs") or [],
         "produced": [{"path": o["path"], "sha256": o["sha256"], "bytes": o["bytes"]}
                      for o in (record.get("outputs") or [])],
         "produced_by": "stage:self_report",        # 来源标记（元检查用）
         "source": "A=环节自报（可能虚报，故须与 B/C/SOP 交叉）"}
    (d / "manifest_A.json").write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = f"""# 环节 {stage} 交接说明（README）

- 脚本：`{record.get('script')}`　退出码：{record.get('exit_code')}　耗时：{record.get('elapsed_s')}s
- 是否产生变更：{"否（幂等）" if record.get('noop') else "是"}　must_change：{record.get('must_change')}

## 我产出了什么（自报，见 manifest_A.json）
"""
    for o in (record.get("outputs") or [])[:20]:
        readme += f"- `{o['path']}`（{o['bytes']} B）\n"
    if not (record.get("outputs") or []):
        readme += "- （未观察到产物）\n"
    readme += f"""
## 给下游的说明
- 声明的产物 glob：{json.dumps(record.get('declared_outputs') or [], ensure_ascii=False)}
- 检查项：{json.dumps(record.get('checks') or [], ensure_ascii=False)}
- 已知缺口/备注：{(record.get('stdout_tail') or '')[-300:].strip()}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
"""
    (d / "README.md").write_text(readme, encoding="utf-8")
    return a


# ───────────────────────────────── B：下游独立清点（不读 A）
def derive_b(entry: dict) -> dict:
    items = []
    for pat in entry.get("outputs") or []:
        for p in sorted(WS.glob(pat)):
            if not p.is_file():
                continue
            items.append({"path": str(p.relative_to(WS)), "pattern": pat,
                          "bytes": p.stat().st_size, "sha256": _sha(p),
                          "probe": _jit(p)})
    return {"stage": entry["id"], "patterns": entry.get("outputs") or [],
            "items": items, "count": len(items),
            "missing_patterns": [p for p in (entry.get("outputs") or [])
                                 if not list(WS.glob(p))],
            "produced_by": "harness:scan",             # 来源标记（元检查用）
            "source": "B=独立清点（实际读盘，不读 A 的 claim）"}


# ───────────────────────────────── C：产物自述（读内容里的元数据）
def derive_c(b: dict) -> dict:
    meta = {}
    _HM = ("/handover/", "/quality/run_record/", "/quality/self_reports/",
           "/quality/calibration_", "/quality/sop_compliance", "/quality/handover_")
    for it in b["items"]:
        p = WS / it["path"]
        name = p.name
        if name == "manifest.yaml":
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
                meta[it["path"]] = {"status": m.get("status"),
                                    "gate_summary": (m.get("gate_summary") or {}).get("verdict")}
            except Exception:
                pass
        elif name.startswith("verify_pipeline") or name in ("stage_gates.yaml", "objective_verify.yaml",
                                                            "closure_report.yaml", "id_resolution.yaml",
                                                            "prompt_reuse.yaml", "sop_compliance.yaml"):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
                meta[it["path"]] = {"verdict": m.get("verdict"), "summary": {
                    k: v for k, v in m.items() if k in ("pass", "FAIL", "invalid", "gap_count")}}
            except Exception:
                pass
        elif name in ("nodes.yaml", "relations.yaml", "evidence.yaml", "graph.yaml"):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
                meta[it["path"]] = {"count": len(m) if isinstance(m, list) else
                                    {k: len(v) for k, v in m.items() if isinstance(v, list)}}
            except Exception:
                pass
        elif it["probe"].get("records") is not None:
            meta[it["path"]] = {"records": it["probe"]["records"]}
        # ★ C 的内部自洽：产物**自述的计数**是否等于**自身内容的计数**。
        #   标定发现原 C_count_mismatch 按构造不可达（死代码），故改为**内容自洽**判定：
        #   只要产物同时声明 count 与列表/条数，即可自查；不需要与 B 配对。
        if p.suffix == ".json" and not any(m in ("/" + it["path"]) for m in _HM):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except Exception:                                  # noqa: BLE001
                j = None
            if isinstance(j, dict):
                sc = {}
                # 只比「count 与**同名列表** items」（原为"第一个列表"，太粗 ⇒ 误报）
                if isinstance(j.get("count"), int) and isinstance(j.get("items"), list):
                    sc = {"declared_count": j["count"], "items_len": len(j["items"]),
                          "ok": j["count"] == len(j["items"])}
                d = j.get("dedup")
                if isinstance(d, dict) and all(k in d for k in ("before", "after", "merged_facts")):
                    sc = {"before": d["before"], "after": d["after"], "merged": d["merged_facts"],
                          "ok": d["before"] - d["after"] == d["merged_facts"]}
                if sc:
                    meta.setdefault(it["path"], {})["self_consistency"] = sc
    return {"stage": b["stage"], "self_declared": meta,
            "produced_by": "artifact:content",         # 来源标记（元检查用）
            "source": "C=产物自述（从内容读出，不采信外部声明）"}


# ───────────────────────────────── 比对 + 交接门
def source_independence(*manifests) -> dict:
    """★ 元检查：四元交叉的有效性**取决于来源是否真独立**。

    本会话同一坑踩过两次：
      · B 取「下游自己的产物」→ 与 A 不同源，通过率 0%（全 BLOCKED）
      · A 取「采集器观察」  → 与 B 同源，通过率 100%（全 CONFIRMED）
    两次都不是逻辑错，而是**源错**。故：来源标签相同 ⇒ 交叉无效，判 invalid（**不得判 pass**）。
    """
    tags = [m.get("produced_by") for m in manifests if m]
    dup = [t for t in set(tags) if tags.count(t) > 1]
    if dup or len(set(tags)) < len(tags):
        return {"ok": False, "reason": f"来源不独立：{tags}（重复 {dup}）⇒ 交叉退化为自证",
                "tags": tags}
    if len(tags) < 3:
        return {"ok": False, "reason": f"清单不足三份（{len(tags)}）⇒ 四元不成立", "tags": tags}
    return {"ok": True, "tags": tags}


def derive_b_from_record(record: dict) -> dict:
    """B = harness **实际观测**（快照差分），**独立于 A（环节自报）与 SOP（契约）**。

    关键排除：观测集里混有 **harness 自己写**的文件（handover/*、run_record/*、self_reports/*）。
    若不排除，B 会包含"检查器自己产出的东西"，B∖SOP 泛滥成噪声，交叉失去意义。
    """
    # ★ 按**路径片段**排除，而非按前缀：镜像副本（交付物/<pkg>/**）里同样含 harness 产物，
    #   只用前缀会漏掉镜像 → B 把 harness 自己的 manifest 当产物 → C 误报（实测发生）。
    HARNESS_MARKERS = ("/handover/", "/quality/run_record/", "/quality/self_reports/",
                       "/quality/calibration_", "/quality/sop_compliance",
                       "/quality/handover_")
    seen, items = set(), []
    for path in (record.get("observed_outputs") or []):
        if any(m in ("/" + path) for m in HARNESS_MARKERS):
            continue                                  # 排除 harness 自己的产物（含镜像）
        if path in seen:
            continue
        seen.add(path)
        p_ = WS / path
        items.append({"path": path, "bytes": (p_.stat().st_size if p_.exists() else 0),
                      "sha256": _sha(p_) if p_.exists() else "",
                      "probe": _jit(p_) if p_.exists() else {}})
    return {"stage": record.get("stage_id"), "items": items, "count": len(items),
            "missing_patterns": [], "produced_by": "harness:scan",
            "source": "B=harness 实际观测（快照差分，已排除 harness 自身产物）"}


def within_stage(entry: dict, record: dict) -> dict:
    """★ 环节**内部**四元交叉：SOP 契约 / A 环节自报 / B 采集器清点 / C 产物自述。

    A 必须是**环节自己写出的**声明（self_report），不能由采集器代写——否则与 B 同源。
    环节未自报 ⇒ A 缺失 ⇒ **判 invalid**（不判 pass），如实反映"该环节尚未自报"。
    """
    d = HD / entry["id"]; d.mkdir(parents=True, exist_ok=True)
    sop = {"produced_by": "contract:sop", "outputs": entry.get("outputs") or []}
    b = derive_b_from_record(record)          # ★ B = 实际观测（独立于 A 与 SOP）
    c = derive_c(b)
    # A：环节自报 —— 按**约定路径**读取（self_reports/<stage>_self_report.json）。
    #   该文件必须由环节脚本自己写出（self_report.declare），不得由 harness 代写；
    #   否则 A 与 B 同源，交叉退化为自证。
    a = {"produced_by": "stage:self_report", "produced": [], "found": False}
    _sr = PKG / "quality" / "self_reports" / f"{entry['id']}_self_report.json"
    if _sr.exists():
        try:
            j = json.loads(_sr.read_text(encoding="utf-8")) or {}
            a = {"produced_by": "stage:self_report", "found": True,
                 "path": str(_sr.relative_to(WS)),
                 "written_by": j.get("written_by"),
                 "produced": j.get("declared_outputs") or [],
                 "counts": j.get("counts") or {}}
        except Exception as _e:                            # noqa: BLE001
            a["error"] = f"{type(_e).__name__}: {_e}"
    ind = source_independence(a if a.get("found") else None, b, c)
    diffs = []
    if not a.get("found"):
        diffs.append({"kind": "A_missing_self_report", "path": entry["id"],
                      "meaning": "环节未写自报文件 ⇒ 内部四元不成立（判 invalid，不判 pass）"})
    else:
        A = set(a["produced"]); B = {x["path"] for x in b["items"]}
        for x in sorted(A - B):
            diffs.append({"kind": "A_not_in_B", "path": x, "meaning": "环节虚报（自报有、实际无）"})
        for x in sorted(B - A):
            diffs.append({"kind": "B_not_in_A", "path": x, "meaning": "环节漏报（实际有、未自报）"})
    # 契约层差异：SOP 声明 vs 实际观测
    import fnmatch as _fn
    _sop_pats = entry.get("outputs") or []
    _B = {x["path"] for x in b["items"]}
    for pat in _sop_pats:
        if not any(_fn.fnmatch(x, pat) or x == pat for x in _B) and not list(WS.glob(pat)):
            diffs.append({"kind": "SOP_not_delivered", "path": pat,
                          "meaning": "契约声明未兑现（SOP 声明但未产出）"})
    for x in sorted(_B):
        if _sop_pats and not any(_fn.fnmatch(x, pat) or x == pat for pat in _sop_pats):
            diffs.append({"kind": "B_not_in_SOP", "path": x,
                          "meaning": "**契约外产物**（实际产出但 SOP 未声明）"})
    for it in b["items"]:
        if it["probe"] and not it["probe"].get("parsable", True):
            diffs.append({"kind": "unparsable_artifact", "path": it["path"],
                          "meaning": f"产物不可解析：{it['probe'].get('error')}"})
    for _p, _m in (c.get("self_declared") or {}).items():
        _sc = _m.get("self_consistency")
        if _sc and not _sc.get("ok", True):
            diffs.append({"kind": "C_self_inconsistent", "path": _p,
                          "meaning": f"C 内部自洽失败：{ {k: v for k, v in _sc.items() if k != 'ok'} }"})
    gate = "INVALID" if not ind["ok"] else ("CONFIRMED" if not diffs else "BLOCKED")
    res = {"stage": entry["id"], "scope": "within_stage",
           "SOP_patterns": len(sop["outputs"]), "A": len(a.get("produced") or []),
           "diff_kinds": sorted({x["kind"] for x in diffs}),
           "B": len(b["items"]), "C": len(c["self_declared"]),
           "independence": ind, "diffs": diffs, "diff_count": len(diffs), "gate": gate,
           "rule": "SOP 契约 / A 环节自报 / B 采集器清点 / C 产物自述；来源不独立 ⇒ invalid"}
    (d / "within_stage_check.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "within").mkdir(parents=True, exist_ok=True)
    _write_gate(d / "within", res)
    return res


def compare(entry: dict, upstream_entries: dict) -> dict:
    """四元交叉：**逐个上游依赖**核对被交接的那批产物。

    修正（原实现的致命错误）：
      原先 derive_b(entry) 用「下游自己的产物」当 B，而 A 是「上游的产物」——
      两者不同源，必然全 BLOCKED（实测通过率 0%）。正确做法是：
      对每个依赖 dep，在 **dep 声明的产物** 上独立清点得 B_dep。
    """
    d = HD / entry["id"]
    d.mkdir(parents=True, exist_ok=True)
    all_diffs = []
    per_dep = []
    _forced_invalid = False          # ★ 自检失败后必须**粘性 INVALID**（不得被末尾覆盖成 BLOCKED）
    for dep in entry.get("depends_on") or []:
        ent_dep = upstream_entries.get(dep)
        if not ent_dep:
            continue
        # ★ 防御性副本 + 身份断言：
        #   实测出现过 B 的 patterns 是**三个不同环节产物的并集**（说明上游 dict 被污染），
        #   而单独加载时又是正确的 —— 属于"同一对象在链路中被改"的假判断源。
        import copy as _copy
        ent_dep = _copy.deepcopy(ent_dep)
        assert ent_dep.get("id") == dep, (
            f"harness bug: upstream_entries['{dep}'] 的 id 字段是 {ent_dep.get('id')!r}")
        # ★ A 取自**环节自己写的自报**（不是 harness 的 run_record）：
        #   run_record 的产物清单是"SOP 声明展开"，与 B（当前扫盘）不同时刻，
        #   SOP 声明一变就产生假"虚报"（实测发生）。自报才是真正独立的 A 来源。
        _sr = PKG / "quality" / "self_reports" / f"{dep}_self_report.json"
        if _sr.exists():
            _j = json.loads(_sr.read_text(encoding="utf-8")) or {}
            a = {"produced_by": "stage:self_report", "found": True,
                 "path": str(_sr.relative_to(WS)),
                 "produced": [{"path": x} for x in (_j.get("declared_outputs") or [])]}
        else:
            fa = d / f"manifest_A_{dep}.json"
            a = json.loads(fa.read_text(encoding="utf-8")) if fa.exists() else {}
            a = {"produced_by": "harness:record", "found": False,
                 "note": "该环节未自报 ⇒ A 退化为 harness 记录（来源独立性不足，应判 invalid）",
                 "produced": a.get("produced") or []}
        # ★ 检查器自检：**先验证自己的输入**，再对别人下判断。
        #   实测：链路内 ent_dep 的 outputs 与 sop.yaml 内容不一致
        #   （得到的是 s3/s5a/s7k 三个环节产物的并集），单载却是正确的 —— 属 harness 缺陷。
        #   原则：**无法验证自己输入的检查器，不得对上游下判断** ⇒ 判 INVALID，不发假指控。
        _sopy = SOP_YAML.read_bytes() if SOP_YAML.exists() else b""
        try:
            import yaml as _yaml
            _doc = _yaml.safe_load(_sopy.decode("utf-8")) or {}
            _declared = next((st.get("outputs") or [] for st in (_doc.get("stages") or [])
                              if st.get("id") == dep), None)
        except Exception:                                   # noqa: BLE001
            _declared = None
        _in_mem = [str(x) for x in (ent_dep.get("outputs") or [])]
        _self_ok = (_declared is not None and sorted(_declared) == sorted(_in_mem))
        if not _self_ok:
            _res = {"stage": entry["id"], "depends_on": entry.get("depends_on") or [],
                    "per_dep": [{"dep": dep, "ent_outputs": [x.split("/")[-1] for x in _in_mem],
                                 "sop_file_outputs": [str(x).split("/")[-1] for x in (_declared or [])],
                                 "self_check": "FAIL"}],
                    "diffs": [{"kind": "checker_input_mismatch", "dep": dep, "path": dep,
                               "meaning": "**检查器自检失败**：链路内的上游声明与 sop.yaml 文件内容不一致"
                                          " ⇒ harness 缺陷；**不得据此指控上游**（判 invalid，不判 BLOCKED）"}],
                    "diff_count": 1, "gate": "INVALID",
                    "rule": "检查器必须先验证自身输入；输入不可信 ⇒ 不产出判断"}
            _forced_invalid = True
            all_diffs.append(_res["diffs"][0])
            per_dep.extend(_res["per_dep"])
            continue
        b = derive_b(ent_dep)                      # ★ B：对**上游**声明的产物独立清点
        c = derive_c(b)
        (d / f"manifest_B_{dep}.json").write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")
        (d / f"manifest_C_{dep}.json").write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
        A = {x["path"] for x in a.get("produced", [])}
        B = {x["path"] for x in b["items"]}
        diffs = []
        for p_ in sorted(A - B):
            diffs.append({"kind": "A_not_in_B", "dep": dep, "path": p_,
                          "meaning": "上游虚报（自报有、下游实际读不到）"})
        for p_ in sorted(B - A):
            diffs.append({"kind": "B_not_in_A", "dep": dep, "path": p_,
                          "meaning": "上游漏报（实际有、未自报）"})
        for pat in b["missing_patterns"]:
            diffs.append({"kind": "SOP_not_delivered", "dep": dep, "path": pat,
                          "meaning": "契约声明未兑现"})
        for it in b["items"]:
            if not it["probe"].get("parsable", True):
                diffs.append({"kind": "unparsable_artifact", "dep": dep, "path": it["path"],
                              "meaning": f"产物不可解析：{it['probe'].get('error')}"})
        # ★ C 参与比对（原实现只写 manifest_C 却从不比对 ⇒ 名为四元实为三元）
        #   C = 产物**自述**（从内容读出的元数据）。可比对的两个实质点：
        #     (a) 自述状态与门禁结论矛盾（如 status=validated 而 verdict=blocked）
        #     (b) 自述计数与实际记录数不符
        _sd = c.get("self_declared") or {}
        _status = _verdict = _counts = None
        for _path, _meta in _sd.items():
            if _path.endswith("manifest.yaml") and _meta.get("status"):
                _status = _meta["status"]
            if _meta.get("verdict"):
                _verdict = _meta["verdict"]
            if isinstance(_meta.get("count"), int):
                _counts = (_path, _meta["count"])
        if _status in ("validated", "published") and _verdict in ("blocked", "FAIL"):
            diffs.append({"kind": "C_internal_contradiction", "dep": dep, "path": "manifest.yaml",
                          "meaning": f"C 自述矛盾：manifest.status={_status} 而门禁 verdict={_verdict}"
                                     f"（blocked 必须回 draft，不得留 validated）"})
        for _p, _m in _sd.items():
            _sc = _m.get("self_consistency")
            if _sc and not _sc.get("ok", True):
                diffs.append({"kind": "C_self_inconsistent", "dep": dep, "path": _p,
                              "meaning": f"C 内部自洽失败：{ {k: v for k, v in _sc.items() if k != 'ok'} }"
                                         f" ⇒ 产物自述的计数与其自身内容不符"})
        all_diffs += diffs
        per_dep.append({"dep": dep, "A": len(A), "B": len(B), "C": len(c["self_declared"]),
                        "SOP_patterns": len(ent_dep.get("outputs") or []),
                        "diffs": len(diffs),
                        # ★ 诊断字段：直接报告上游 entry 的实际声明与实现来源
                        "ent_id": ent_dep.get("id"),
                        "ent_outputs": [str(x).split("/")[-1] for x in (ent_dep.get("outputs") or [])],
                        "impl": str(Path(__file__).resolve()),
                        "ver": HANDOVER_VERSION})
    ok = not all_diffs and not _forced_invalid
    res = {"stage": entry["id"], "depends_on": entry.get("depends_on") or [],
           "per_dep": per_dep, "diffs": all_diffs, "diff_count": len(all_diffs),
           "gate": "INVALID" if _forced_invalid else ("CONFIRMED" if ok else "BLOCKED"),
           "rule": "逐依赖四元交叉：A 上游自报 / B 下游对上游产物独立清点 / C 产物自述 / SOP 契约",
           "C_compared": True, "C_checks": ["自述状态 vs 门禁结论", "自述计数 vs 实际记录数"]}
    _write_gate(d, res)
    return res
