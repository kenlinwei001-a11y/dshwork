# -*- coding: utf-8 -*-
"""改稿后的推演链重放（确定性，零 LLM）——推演出「文件其他内容需要修改的部分」。

输入：语义图谱（八类节点）+ change_classify 分类结果（changes）。
输出：
  affected_nodes    —— 沿 reasoning 依赖图正向传播出的全部受影响节点
  affected_sections —— 受影响节点聚合出的章节清单（= 文件里需要改的段落位置）
  replay_plan       —— 每条受影响推演的处置：可重算的给出新旧值；缺输入的给出待补清单
  downgraded        —— 因上游删除而需降级为待审的结论清单

铁律：只传播、只标注，不改数值、不裁决冲突；重算出的值与原文不一致 → 标待审。
"""
from __future__ import annotations
import re


def build_reverse_index(items: dict) -> dict:
    """反向依赖索引：node_id -> [(reasoning_id, output_id)]（谁依赖我）。"""
    rev: dict = {}
    for r in items.get("reasoning", []):
        out = r.get("output")
        for inp in r.get("inputs", []):
            rev.setdefault(inp, []).append((r.get("id"), out))
    return rev


def build_label_index(items: dict) -> dict:
    """标签反向索引：subject/label -> [reasoning_id]（公式占位符或缺失标签引用它的规则）。

    关键：新增事实往往补上规则缺的输入（deps_labels / formula {占位符}），
    这些规则此前 inputs 未绑定、id 反向索引查不到——必须按标签匹配才能重放。
    """
    lrev: dict = {}
    for r in items.get("reasoning", []):
        labels = set(re.findall(r"\{([^{}]+)\}", r.get("formula") or ""))
        labels |= {str(x) for x in (r.get("deps_labels") or [])}
        for lab in labels:
            lrev.setdefault(lab, []).append(r.get("id"))
    return lrev


def parse_added_facts(changes: list[dict]) -> list[dict]:
    """把 add 变更的文本解析为 (subject, value, unit)，供标签级重放。

    复用 doc_facts.facts_from_text（确定性）——同一解析口径与建图一致。
    """
    try:
        from .doc_facts import facts_from_text
    except Exception:
        return []
    out = []
    for c in changes or []:
        if c.get("action") != "add":
            continue
        text = c.get("text") or ""
        for f in facts_from_text(text):
            out.append({"action": "add", "id": c.get("id") or "", "text": text,
                        "subject": f["label"], "value": f["value"], "unit": f.get("unit", "")})
    return out


def _fact_env(facts: list[dict]) -> dict:
    env = {}
    for f in facts:
        subj = f.get("subject")
        if subj and f.get("value") is not None:
            env[subj] = f["value"]
    return env


def _recompute(formula: str, facts: list[dict], overrides: dict):
    """按 instantiate 的约定重算：{标签} → v0/v1 安全标识符 + safe_eval。

    返回 (新值 | None, 缺失标签列表)。"""
    import re
    from .instantiate import safe_eval
    labels = re.findall(r"\{([^{}]+)\}", formula or "")
    env: dict = {}
    missing: list = []
    for lab in labels:
        if lab in overrides:
            env[lab] = overrides[lab]
            continue
        hit = next((f for f in facts if f.get("subject") == lab or f.get("label") == lab), None)
        if hit is None or hit.get("value") is None:
            missing.append(lab)
            continue
        env[lab] = hit["value"]
    if missing:
        return None, missing
    expr, safe_env = formula, {}
    for i, lab in enumerate(labels):
        safe = f"v{i}"
        expr = expr.replace("{" + lab + "}", safe)
        safe_env[safe] = env[lab]
    try:
        return float(safe_eval(expr, safe_env)), []
    except Exception:
        return None, []


def _norm_action(action: str) -> str:
    """change_classify 与协议两套命名归一：move_block→move、delete_block→delete。"""
    a = str(action or "")
    return {"move_block": "move", "delete_block": "delete"}.get(a, a)


def replay_changes(graph: dict, changes: list[dict]) -> dict:
    """重放改稿：changes 每条的 action ∈ {edit_number, add, delete/delete_block,
    edit_claim, move/move_block, ...}。

    graph：语义图谱 dict（含 items 八类节点），或直接传 items。
    """
    items = graph.get("items", graph) if isinstance(graph, dict) else {}
    rev = build_reverse_index(items)
    label_rev = build_label_index(items)
    facts = {f.get("id"): f for f in items.get("facts", [])}
    reasoning = {r.get("id"): r for r in items.get("reasoning", [])}
    claims = {c.get("id"): c for c in items.get("claims", [])}

    def _section_of(nid):
        if nid in facts:
            return facts[nid].get("section", "§?")
        if nid in claims:
            return claims[nid].get("section", "§?")
        if nid in reasoning:
            return reasoning[nid].get("section", "§?")
        return "§?"

    affected_nodes: list[str] = []
    replay_plan: list[dict] = []
    downgraded: list[dict] = []
    seen: set = set()
    planned: set = set()          # 已入 replay_plan 的 reasoning id（去重）
    queue: list = []

    def _plan_recompute(r: dict, cause: dict, subj: str | None, override_label: str | None = None):
        """把规则 r 的重算写入 replay_plan，并把其输出入队传播。"""
        rid = r.get("id")
        if rid in planned:
            return
        planned.add(rid)
        out = r.get("output")
        entry: dict = {"reasoning": rid, "desc": r.get("desc", ""), "output": out,
                       "cause": f"{cause.get('action')}:{cause.get('id') or subj}", "kind": "重算"}
        overrides: dict = {}
        key = override_label or subj
        if key and cause.get("value") is not None:
            overrides[key] = cause["value"]
        newval, missing = _recompute(r.get("formula", ""), list(facts.values()), overrides)
        entry["old"] = r.get("result")
        entry["recomputed"] = newval
        if newval is None:
            entry["note"] = (f"输入不齐（缺 {missing}），无法重算 → 待补" if missing
                             else "缺计算规格或求值失败 → 待补")
        elif r.get("result") is not None and newval != r.get("result"):
            entry["note"] = "重算值与原文不一致 → 待审"
        else:
            entry["note"] = "重算一致"
        replay_plan.append(entry)
        affected_nodes.extend([rid, out])
        if out:
            queue.append((out, {"action": "derived", "id": out,
                                "value": newval if newval is not None else cause.get("value")}))

    # 把 add 文本解析成 (subject, value)，并让标签级匹配参与重放
    for c in changes or []:
        action = _norm_action(c.get("action"))
        nid = c.get("id") or c.get("target") or ""
        if action == "move":
            # 位置变了、内容相同：ID 不变、只改锚；重放叙述顺序。
            sec = _section_of(nid) if nid else None
            replay_plan.append({"kind": "叙述顺序重放", "object": nid or c.get("text", ""),
                                "section": sec,
                                "anchor_before": c.get("anchor_before"), "anchor_after": c.get("anchor_after"),
                                "note": "位置变了不改 ID，只改 anchor；重放受影响章节的叙述顺序"})
            if nid:
                affected_nodes.append(nid)
            continue
        if not nid:
            continue
        if action in ("edit_number", "add"):
            queue.append((nid, c))
        elif action == "delete":
            for (rid, out) in rev.get(nid, []):
                downgraded.append({"reasoning": rid, "output": out,
                                   "reason": f"上游 {nid} 被删除，本结论同步降级为待审"})
                affected_nodes.extend([rid, out])
        elif action == "edit_claim":
            for (rid, out) in rev.get(nid, []):
                replay_plan.append({"reasoning": rid, "desc": reasoning.get(rid, {}).get("desc", ""),
                                    "output": out, "kind": "复查依赖与证据",
                                    "reason": f"claim {nid} 被修改，下游推演需复查 premise_refs/derived_from"})
                affected_nodes.extend([rid, out])

    # 新增事实 → 标签级匹配：公式/缺失标签引用它的规则立即重算并传播下游
    # （新节点 id 不在 id 反向索引里，但它的 subject 会补上规则缺的输入）。
    # 匹配用宽容规则：精确 或 相互包含（别名差异如「学生用水定额」vs「定额」，
    # 建图侧由 ALIAS/概念字典归一，重放侧用子串兜底，零 LLM）。
    for af in parse_added_facts(changes or []):
        subj = af.get("subject")
        if not subj or af.get("value") is None:
            continue
        for r in items.get("reasoning", []):
            labels = set(re.findall(r"\{([^{}]+)\}", r.get("formula") or ""))
            labels |= {str(x) for x in (r.get("deps_labels") or [])}
            matched = [lab for lab in labels if lab and (lab == subj or lab in subj or subj in lab)]
            if not matched:
                continue
            # 精确优先，否则取最长公共标签（别名兜底），并用它作为 override 键（对齐公式占位符）
            best = subj if subj in labels else max(matched, key=len)
            _plan_recompute(r, af, subj, override_label=best)

    # BFS 正向传播 edit_number/add
    while queue:
        nid, cause = queue.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        for (rid, out) in rev.get(nid, []):
            r = reasoning.get(rid)
            if not r:
                continue
            subj = facts.get(nid, {}).get("subject") if nid in facts else None
            _plan_recompute(r, cause, subj)

    node_sections: dict = {}
    for f in items.get("facts", []):
        node_sections[f["id"]] = f.get("section", "§?")
    for r in items.get("reasoning", []):
        node_sections[r["id"]] = r.get("section", "§?")
    for c in items.get("claims", []):
        node_sections[c["id"]] = c.get("section", "§?")

    uniq_nodes = sorted(set(affected_nodes))
    sections = sorted({node_sections.get(n, "§?") for n in uniq_nodes})
    return {"affected_nodes": uniq_nodes,
            "affected_sections": sections,
            "replay_plan": replay_plan,
            "downgraded": downgraded,
            "summary": (f"受影响节点 {len(uniq_nodes)} 个（章节 {sections}），"
                        f"待重算 {len(replay_plan)} 条，降级 {len(downgraded)} 条")}
