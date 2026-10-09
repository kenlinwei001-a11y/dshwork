# -*- coding: utf-8 -*-
"""
新项目图库实例化引擎（链路 2 的块①）——借形不借值。

输入：
  corpus_dir    语料包目录（借「形」来源：规则/推导链/narrative_zh/骨架/风格）
  project_dir   新项目图库目录（输出）
  provided_facts  用户输入的新事实 [{label, value, unit, caliber, as_of, kind}]
  meta          项目元信息 {project_id, title, data_cutoff}

输出（project_dir 下）：
  meta.yaml                 项目元信息（based_on 语料包指纹）
  graph/nodes.yaml          新节点：status ∈ provided / computed / undefined
  graph/rules.yaml          语料规则重绑定（deps/target → 新节点 id，guard 缺值守卫）
  reasoning/derivation.yaml 重绑定推演链 + 借用 narrative_zh + 回放结果
  bindings.yaml             旧节点 id ↔ 新节点 id（写作时骨架槽位重绑定用）
  quality/gate_report.yaml  实例化闸门（undefined 清单 + 回放冲突待审）
  index/node_index.json     新节点倒排
  project/work_packages/    编排器工作包落盘目录（占位）

铁律：语料中的数值一律不进入新图；inheritable=never 的节点只转移「形式」
（风险/待审表述），不转移值；依赖缺失时输出 UNDEFINED + instruction，
永不按 0 计算。
"""
from __future__ import annotations
import ast
import hashlib
import json
import math
from pathlib import Path

# 领域规则库（单一事实源）：计算规格 + 展示规则从知识处理侧 import，不再此处硬编码
from .domain_rules import COMPUTE_SPEC, DISPLAY_RULES


# --------------------------------------------------------------------------- #
# 安全表达式求值（ast 白名单，零 eval）
# --------------------------------------------------------------------------- #
_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}
_FUNCS = {"max": max, "min": min, "round": round, "floor": math.floor, "ceil": math.ceil, "abs": abs}


def safe_eval(expr: str, env: dict) -> float:
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            raise KeyError(node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ValueError(f"unsupported node: {ast.dump(node)}")
    return ev(ast.parse(expr, mode="eval"))


# --------------------------------------------------------------------------- #
# 计算规格（COMPUTE_SPEC）与展示规则（DISPLAY_RULES）已下沉到
# corpus_pipeline/domain_rules.py（知识处理侧单一事实源），在文件顶部 import。
# --------------------------------------------------------------------------- #


def new_id(label: str, value) -> str:
    return "P-" + hashlib.sha1(f"{label}|{value}".encode("utf-8")).hexdigest()[:12]


def _jf(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _jl(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l] if p.exists() else []


def _jw(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except (ValueError, AttributeError):
        return None


def instantiate_project(corpus_dir: str, project_dir: str, provided_facts: list[dict], meta: dict | None = None,
                        old_schema: dict | None = None, new_schema: dict | None = None) -> dict:
    cdir = Path(corpus_dir)
    pdir = Path(project_dir)
    pdir.mkdir(parents=True, exist_ok=True)

    corpus_nodes = _jf(cdir / "graph" / "nodes.yaml") or []
    corpus_rules = _jf(cdir / "graph" / "rules.yaml") or []
    corpus_deriv = _jf(cdir / "reasoning" / "derivation.yaml") or {}
    corpus_manifest = _jf(cdir / "manifest.yaml") or {}
    corpus_style = _jf(cdir / "style" / "style_profile.yaml") or {}

    label_of = {n["id"]: n["subject"] for n in corpus_nodes}
    meta = meta or {}
    pmeta = {
        "project_id": meta.get("project_id", "NEW-PROJECT"),
        "title": meta.get("title", "新项目（借形不借值）"),
        "data_cutoff": meta.get("data_cutoff", "2026-09-18"),
        "based_on": {
            "corpus_id": corpus_manifest.get("corpus_id", ""),
            "version": corpus_manifest.get("version", ""),
            "source_fingerprint": corpus_manifest.get("source_fingerprint", ""),
        },
        "constraints": corpus_manifest.get("constraints", []),
    }
    _jw(pdir / "meta.yaml", pmeta)

    # ---- 1. 新事实节点（provided）----
    provided = {}
    for f in provided_facts:
        label = f["label"]
        node = {
            "id": new_id(label, f["value"]),
            "label": label,
            "kind": f.get("kind", "quantity"),
            "value": f["value"],
            "unit": f.get("unit", ""),
            "caliber": f.get("caliber", ""),
            "as_of": f.get("as_of", pmeta["data_cutoff"]),
            "confidence": f.get("confidence", 0.9),
            "status": "provided",
            "rule": None,
            "inherited_from": None,
        }
        provided[label] = node

    nodes = list(provided.values())

    # ---- 2. 规则重绑定 + 缺值守卫 + 重算 ----
    rebound_rules = []
    undefined_notes = []
    replay_conflicts = []
    computed_values = {}   # label -> value（回放比对用）

    def compute_label(label: str) -> float | None:
        spec = COMPUTE_SPEC.get(label)
        if not spec:
            return None
        tpl = spec["spec"]
        var_labels = __import__("re").findall(r'\{([^{}]+)\}', tpl)
        env = {}
        for vl in var_labels:
            if vl not in computed_values and vl not in provided:
                return None                       # 缺依赖 → 缺值守卫
            v = computed_values[vl] if vl in computed_values else provided[vl]["value"]
            n = _num(v)
            if n is None:
                return None
            env[vl] = n
        # {主语} → 主语名（中文标识符，Python 合法 Name），再进 ast 白名单求值
        expr = tpl
        for vl in var_labels:
            expr = expr.replace("{" + vl + "}", vl)
        return float(safe_eval(expr, env))

    # 判定式/展示规则直通（不参与重算）；计算规则进不动点队列
    compute_queue = []
    for r in corpus_rules:
        if r.get("kind") == "select":
            # 判定式规则：只转移形式（决策模板），不重算
            rebound_rules.append({
                "id": r["id"], "kind": "select", "target": None,
                "expr": r.get("expr", ""), "deps": [], "guard": r.get("guard"),
                "on_dep_change": "rejudge", "note": "判定式规则随语料借形：新项目须有同口径冲突记录才触发",
            })
            continue
        if r["id"] in DISPLAY_RULES:
            rebound_rules.append({**r, "kind": "compute", "deps": [], "note": "展示规则，随风格借形"})
            continue
        compute_queue.append(r)

    node_by_label = {n["label"]: n["id"] for n in nodes}

    def target_label_of(r):
        old_target = r.get("target")
        if isinstance(old_target, str) and old_target.startswith("N-") and old_target in label_of:
            return label_of[old_target]
        return r.get("label") or r["id"]

    def add_undefined_node(label, instruction, rule_id, old_target):
        """UNDEFINED 节点也入图：value=null + instruction，写作 Agent 可查、闸门可抓。"""
        if label in node_by_label:
            return
        node = {
            "id": new_id(label, "undefined"),
            "label": label,
            "kind": "quantity",
            "value": None,
            "unit": COMPUTE_SPEC.get(label, {}).get("unit", ""),
            "caliber": "未提供依赖，按缺值守卫保持 UNDEFINED",
            "as_of": pmeta["data_cutoff"],
            "confidence": 0.0,
            "status": "undefined",
            "rule": rule_id,
            "instruction": instruction,
            "inherited_from": old_target if isinstance(old_target, str) else None,
        }
        nodes.append(node)
        node_by_label[label] = node["id"]

    def process_rule(r):
        """处理一条计算规则；依赖齐备时执行并返回 True，否则返回 False。"""
        old_dep_ids = r.get("deps", [])
        dep_labels = [label_of.get(d, d) for d in old_dep_ids]
        target_label = target_label_of(r)
        old_target = r.get("target")
        missing = [l for l in dep_labels if l not in provided and l not in computed_values]
        if missing:
            return False
        nr = {
            "id": r["id"], "kind": "compute", "expr": r.get("expr", ""),
            "guard": r.get("guard", "missing_any_dep => undefined"),
            "on_dep_change": "recompute",
            "deps": [], "target": None, "target_label": target_label,
        }
        recomputed = compute_label(target_label) if target_label in COMPUTE_SPEC else None
        provided_val = provided.get(target_label)

        def add_computed(value, rule_id):
            display = int(value) if float(value).is_integer() else round(value, 2)
            node = {
                "id": new_id(target_label, display),
                "label": target_label,
                "kind": "quantity",
                "value": display,
                "unit": COMPUTE_SPEC[target_label]["unit"],
                "caliber": "重算值·按语料规则 " + rule_id,
                "as_of": pmeta["data_cutoff"],
                "confidence": 0.9,
                "status": "computed",
                "rule": rule_id,
                "inherited_from": old_target if isinstance(old_target, str) else None,
            }
            nodes.append(node)
            node_by_label[target_label] = node["id"]
            nr["status"] = "computed"
            nr["target"] = node["id"]

        if recomputed is not None and provided_val is not None:
            # 回放比对：用户提供值 vs 规则重算值
            if abs(_num(provided_val["value"]) - recomputed) > 0.01:
                replay_conflicts.append({
                    "type": "numeric", "subject": target_label, "status": "待审",
                    "provided": provided_val["value"],
                    "recomputed": round(recomputed, 2),
                    "reason": f"用户提供值与规则 {r['id']} 重算值不一致，回放检出不裁决",
                })
                nr["status"] = "conflict"
                nr["recomputed"] = round(recomputed, 2)
                nr["target"] = provided_val["id"]
                add_computed(recomputed, r["id"])   # 同时保留重算节点，供报告双节点引用
                nr["status"] = "conflict"           # add_computed 会改写 status/target，恢复冲突语义
                nr["target"] = provided_val["id"]
                node_by_label[target_label] = provided_val["id"]  # 依赖传播仍锚定提供值（冲突不裁决）
            else:
                nr["status"] = "provided"
                nr["target"] = provided_val["id"]
            computed_values[target_label] = _num(provided_val["value"])
        elif recomputed is not None:
            computed_values[target_label] = recomputed
            add_computed(recomputed, r["id"])
        elif provided_val is not None:
            nr["status"] = "provided"
            nr["target"] = provided_val["id"]
            computed_values[target_label] = _num(provided_val["value"])
        else:
            nr["status"] = "undefined"
            nr["instruction"] = f"待提供「{target_label}」或其依赖后测算（规则 {r['id']}）"
            undefined_notes.append({"rule": r["id"], "target_label": target_label, "missing": ["输出未提供且无计算规格"], "instruction": nr["instruction"]})
            add_undefined_node(target_label, nr["instruction"], r["id"], old_target)

        # deps 重绑定到新节点（provided/computed 均按 label 定位）
        for l in dep_labels:
            if l in node_by_label:
                nr["deps"].append(node_by_label[l])
        rebound_rules.append(nr)
        return True

    # 不动点迭代：依赖顺序任意，多轮扫描直到无新计算值产生
    def mark_undefined(r, missing):
        """确定性缺依赖：登记 undefined 节点 + 规则记录（缺值守卫，绝不静默丢弃）。"""
        target_label = target_label_of(r)
        old_target = r.get("target")
        dep_labels = [label_of.get(d, d) for d in r.get("deps", [])]
        instruction = f"待提供/测算「{'、'.join(missing) or '未知依赖'}」后按 {r['id']} 计算；不得填 0、不得估值"
        undefined_notes.append({"rule": r["id"], "target_label": target_label, "missing": missing, "instruction": instruction})
        add_undefined_node(target_label, instruction, r["id"], old_target)
        rebound_rules.append({
            "id": r["id"], "kind": "compute", "expr": r.get("expr", ""),
            "guard": r.get("guard", "missing_any_dep => undefined"),
            "on_dep_change": "recompute",
            "deps": [node_by_label[l] for l in dep_labels if l in node_by_label],
            "target": None, "target_label": target_label,
            "status": "undefined", "instruction": instruction,
        })

    pending = list(compute_queue)
    progressed = True
    while progressed and pending:
        progressed = False
        next_round = []
        for r in pending:
            dep_labels = [label_of.get(d, d) for d in r.get("deps", [])]
            missing = [l for l in dep_labels if l not in provided and l not in computed_values]
            producible = {target_label_of(x) for x in pending if x is not r}
            if missing and any(m in producible for m in missing):
                next_round.append(r)          # 依赖可由后续规则产出 → 下一轮
                continue
            if process_rule(r):
                progressed = True
            elif missing:
                mark_undefined(r, missing)    # 依赖无生产者 → 定判 undefined
        pending = next_round
    # 不动点后仍 pending：兜底判 undefined（依赖链缺口）
    for r in pending:
        dep_labels = [label_of.get(d, d) for d in r.get("deps", [])]
        missing = [l for l in dep_labels if l not in provided and l not in computed_values]
        mark_undefined(r, missing)

    # provided 中带规则输出语义的节点，登记 target 指向
    by_label = {n["label"]: n for n in nodes}
    for nr in rebound_rules:
        if nr.get("status") == "provided" and nr.get("target_label") in by_label:
            nr["target"] = by_label[nr["target_label"]]["id"]

    # ---- 3. 推导链（借用 narrative_zh + 重绑定）----
    narr = {d.get("label"): d.get("narrative_zh", "") for d in corpus_deriv.get("nodes", [])}
    derivation = {"nodes": [], "replayed": len(nodes), "contradictions": replay_conflicts}
    for nr in rebound_rules:
        if nr.get("kind") != "compute" or not nr.get("target_label"):
            continue
        derivation["nodes"].append({
            "node": nr.get("target"),
            "label": nr["target_label"],
            "rule": nr["id"],
            "status": nr.get("status"),
            "chain": [{"step": 1, "rule": nr["id"], "expr": nr.get("expr", "")}],
            "narrative_zh": narr.get(nr["target_label"], ""),
            "instruction": nr.get("instruction", ""),
        })

    # ---- 4. bindings：旧节点 id → 新节点（骨架槽位重绑定）----
    bindings = {}
    for n in corpus_nodes:
        lbl = n["subject"]
        if lbl in provided:
            bindings[n["id"]] = {"label": lbl, "new_node_id": provided[lbl]["id"], "status": "provided"}
        elif lbl in computed_values or any(nd["label"] == lbl for nd in nodes):
            hit = next((nd for nd in nodes if nd["label"] == lbl), None)
            bindings[n["id"]] = {"label": lbl, "new_node_id": hit["id"] if hit else None, "status": hit["status"] if hit else "undefined"}
        elif n.get("inheritable") == "never":
            bindings[n["id"]] = {"label": lbl, "new_node_id": None, "status": "form_only",
                                 "note": "inheritable=never：仅借其待审/风险表述形式，不转移值"}
        else:
            bindings[n["id"]] = {"label": lbl, "new_node_id": None, "status": "undefined",
                                 "note": "新项目未提供该事实，写作时按缺值守卫处理"}
    _jw(pdir / "bindings.yaml", {"bindings": bindings})

    _jw(pdir / "graph" / "nodes.yaml", nodes)
    _jw(pdir / "graph" / "rules.yaml", rebound_rules)
    _jw(pdir / "reasoning" / "derivation.yaml", derivation)
    gate = {
        "gate": "REVIEW" if (undefined_notes or replay_conflicts) else "PASS",
        "undefined": undefined_notes,
        "replay_conflicts": replay_conflicts,
        "invariant_ok": not replay_conflicts,
    }
    _jw(pdir / "quality" / "gate_report.yaml", gate)
    node_index = {
        n["id"]: {"label": n["label"], "status": n.get("status"), "rule": n.get("rule"),
                  "chunks": [], "as_subject_of": [], "downstream": [], "upstream": [], "conflicts": []}
        for n in nodes
    }
    _jw(pdir / "index" / "node_index.json", node_index)
    (pdir / "project" / "work_packages").mkdir(parents=True, exist_ok=True)
    (pdir / "project" / "drafts").mkdir(parents=True, exist_ok=True)

    # ---- 6 类装配产物（P1）：assembly_manifest / schema_diff / asset_patch / reuse_lineage ----
    # ① assembly_manifest：复用了哪些历史资产 + 复用方式 + 版本
    assembly_manifest = {
        "project_id": pmeta.get("project_id", ""),
        "based_on": pmeta.get("based_on", {}),
        "reuse_mode": "借形不借值",
        "constraints": pmeta.get("constraints", []),
        "reused_assets": [
            {"asset": "rules", "source": "corpus", "mode": "rebind", "count": len(rebound_rules)},
            {"asset": "derivation_narrative_zh", "source": "corpus", "mode": "borrow_form", "count": len(derivation.get("nodes", []))},
            {"asset": "style", "source": "corpus", "mode": "inherit", "applied": bool(corpus_style)},
        ],
    }
    _jw(pdir / "assembly_manifest.yaml", assembly_manifest)

    # ② schema_diff：新旧 Schema 差异（若提供）+ 16 域影响分析 + 可执行装配变更集
    if old_schema is not None and new_schema is not None:
        from .schema_diff import diff_schemas, summarize, analyze_schema_impact
        from .ontology_schema import assemble_domain_changes
        diffs = diff_schemas(old_schema, new_schema)
        _jw(pdir / "schema_diff.yaml", {
            "diffs": diffs,
            "summary": summarize(diffs),
            "impact_analysis": analyze_schema_impact(diffs),
            "domain_changes": assemble_domain_changes(diffs),
        })

    # ③ asset_patch：带 operation + base_version 的变更集（文档第四节 AssetPatch 契约）
    from .contracts import make_patch, bundle_version
    corpus_version = f"{pmeta['based_on']['corpus_id']}@{pmeta['based_on']['version']}"
    patches = [
        make_patch("rules", "PARAMETERIZE", rebound_rules, corpus_version),
        make_patch("derived_nodes", "ADD", [n for n in nodes if n.get("status") == "computed"], corpus_version),
        make_patch("facts", "REUSE",
                   [{"label": f["label"], "value": f["value"], "unit": f.get("unit", "")} for f in provided_facts],
                   corpus_version),
    ]
    if undefined_notes:
        patches.append(make_patch("facts", "MODIFY", undefined_notes, corpus_version))
    if replay_conflicts:
        patches.append(make_patch("validation", "REJECT", replay_conflicts, corpus_version))
    _jw(pdir / "asset_patch.yaml", {"base_version": corpus_version, "patches": patches})

    # ④ reuse_lineage：每个资产来源 + 改动 + 状态（可回溯、可审计）
    reuse_lineage = {
        "lineage": [
            {"corpus_node_id": old_id, "label": v.get("label"), "project_node_id": v.get("new_node_id"),
             "status": v.get("status"), "note": v.get("note", "")}
            for old_id, v in bindings.items()
        ],
    }
    _jw(pdir / "reuse_lineage.yaml", reuse_lineage)

    # ⑤ bundle：版本固化（version + content_hash，Asset Publisher 最小版）
    bundle = bundle_version(pmeta["project_id"], "1.0", pmeta["based_on"], patches, reuse_lineage["lineage"])
    _jw(pdir / "bundle.yaml", bundle)

    return {
        "project_dir": str(pdir),
        "provided": len(provided),
        "computed": sum(1 for n in nodes if n.get("status") == "computed"),
        "undefined_notes": len(undefined_notes),
        "replay_conflicts": len(replay_conflicts),
        "rebound_rules": len(rebound_rules),
        "bindings": len(bindings),
        "gate": gate["gate"],
        "style_inherited": bool(corpus_style),
        "bundle": bundle,
    }
