# -*- coding: utf-8 -*-
"""RSI 自我进化核心（确定性，零 LLM）：把「用户对文件的修改」归纳为「skill 修订草稿」。

输入：改稿回读协议产出的 changes[]（diff→classify 之后，含 action/id/before/after）。
输出：
  1. classify_changes   —— 区分 fact 级（只改图谱）与 pattern 级（沉淀为 skill 补丁）
  2. draft_skill_patch  —— 生成修订后的 SKILL.md（增量修订 + 修订记录，绝不覆盖原文）
  3. check_guards       —— 防退化红线检查（不通过不得提草稿）

铁律（与知识处理/推演写作体系一致）：
  · 绝不自动发布——本模块只产草稿，发布必须用户显式确认（workdsh_publish_skill_draft）。
  · fact 级修改永不进 skill（「不把某次任务答案写成永久规则」）。
  · 同类 pattern 修改首次只记 candidate，≥2 次才提草稿（防单次偏好过拟合）。
  · 同口径被不同方式修改 → 待审，不沉淀。
  · 每条修订必须带溯源（来源修改 before/after + 理由）。
"""
from __future__ import annotations

# pattern 级修改的线索词：修改内容命中这些域 → 视为「方法/口径/句式」级，可沉淀
PATTERN_HINTS = [
    "口径", "句式", "写法", "格式", "术语", "单位", "规则", "标准", "规范",
    "判定", "阈值", "流程", "步骤", "禁用", "约束", "引用体例", "编号",
]

# 目标 skill 的修订记录小节标题（追加到 SKILL.md 末尾附近）
EVO_HEADER = "## 自我进化修订记录（RSI）"

FACT_ACTIONS = {"edit_number", "add", "delete", "move"}


def endorse_ai_authored(ai_ledger: list[dict], review_changes: list[dict]) -> dict:
    """AI 写过的片段，人工评审未改动 → 默认认可（可沉淀）；改动/删除 → 不沉淀。

    ai_ledger:      专家做 AI 扩写/缩写时记录的 [{id/anchor, after, hint, why, ...}]
    review_changes: 下次改稿回读的 changes[]（含 action/anchor）
    返回 {endorsed, modified, deleted}：
      endorsed  —— 未被任何 review 触碰的 AI 片段（author 转为 ai_endorsed）
      modified  —— 被人工改过（人工版本走 user 通道，原 AI 片段作废）
      deleted   —— 被人工删除（负反馈，永不沉淀）
    """
    touched, deleted = set(), set()
    for c in review_changes or []:
        anchor = str(c.get("anchor_before") or c.get("id") or c.get("target") or "")
        if not anchor:
            continue
        (deleted if c.get("action") == "delete" else touched).add(anchor)
    endorsed, modified, removed = [], [], []
    for item in ai_ledger or []:
        anchor = str(item.get("anchor") or item.get("id") or "")
        if anchor and anchor in deleted:
            removed.append(item)
        elif anchor and anchor in touched:
            modified.append(item)
        else:
            endorsed.append({**item, "author": "ai_endorsed",
                             "source": "ai_endorsed(人工未改动，默认认可)"})
    return {"endorsed": endorsed, "modified": modified, "deleted": removed}


def classify_changes(changes: list[dict], extra_hints: list[str] | None = None) -> dict:
    """把 changes 分为 fact 级 / pattern 级 / conflict 级 / ai 级。

    判据（确定性，零 LLM）：
      1. author == "ai"（AI 扩写/缩写产物，未经评审）→ ai 级：只进图谱 draft/candidate，
         不沉淀 skill（尚未获得人工认可）。
      2. author == "ai_endorsed"（AI 写法，人工评审未改动 = 默认认可）→ 与 user 同级，
         且存活 1 次评审即可升 pattern（认可本身就是跨轮次的确认信号）。
      3. 其余（user 手工改）命中 PATTERN_HINTS 线索词 → pattern 候选；同类 ≥2 次升 pattern。
      4. 同一条目标被不同 after 修改 → conflict 级（待审，不沉淀）。
      5. 数值/增删/搬移且不命中线索词 → fact 级（只改图谱）。
    """
    hints = list(PATTERN_HINTS) + list(extra_hints or [])
    fact, pattern, conflict, candidates, ai_generated = [], [], [], [], []
    seen = {}          # (target, hint) -> [after 列表]
    endorsed_groups: set = set()   # 含 ai_endorsed 的 (target, hint) 组：阈值降为 1
    for c in changes or []:
        author = str(c.get("author", "")).lower()
        if author == "ai":
            ai_generated.append(c)
            continue  # 未经评审的 AI 产物不进 skill 归纳通道
        text = " ".join(str(c.get(k, "")) for k in ("after", "before", "note", "why"))
        hit = next((h for h in hints if h in text), None)
        if hit:
            key = (c.get("id") or c.get("target") or c.get("anchor_before") or str(c), hit)
            seen.setdefault(key, []).append(c.get("after"))
            candidates.append({**c, "hint": hit, "source": c.get("source", "user_edit")})
            if author == "ai_endorsed":
                endorsed_groups.add(key)
        else:
            fact.append(c)
    # 冲突：同一 (target, hint) 被改成多个不同 after → 待审，不沉淀
    for (target, hint), afters in seen.items():
        uniq = {str(a) for a in afters}
        if len(uniq) > 1:
            conflict.append({"target": target, "hint": hint,
                             "variants": sorted(uniq), "action": "待审"})
    conflict_keys = {cf["target"] for cf in conflict}
    # 频次确认：非冲突候选按 (target, hint) 计数；ai_endorsed 组阈值 1，其余 2
    counts: dict = {}
    for c in candidates:
        key = (c.get("id") or c.get("target") or c.get("anchor_before") or str(c), c["hint"])
        counts[key] = counts.get(key, 0) + 1
    keep_candidates = []
    for c in candidates:
        key = (c.get("id") or c.get("target") or c.get("anchor_before") or str(c), c["hint"])
        if key[0] in conflict_keys:
            continue  # 冲突项一律不沉淀
        threshold = 1 if key in endorsed_groups else 2
        (pattern if counts[key] >= threshold else keep_candidates).append(c)
    return {"fact": fact, "pattern": pattern, "candidates": keep_candidates,
            "conflicts": conflict, "ai_generated": ai_generated,
            "summary": (f"fact={len(fact)} pattern={len(pattern)} candidate={len(keep_candidates)} "
                        f"conflict={len(conflict)} ai={len(ai_generated)}")}


def suggest_evolution(changes: list[dict], ai_ledger: list[dict] | None = None,
                      review_changes: list[dict] | None = None, threshold: int = 2) -> dict:
    """自动建议（供改稿回读后自动调用，替代「等用户说进化」）。

    ai_ledger + review_changes：AI 扩写/缩写的片段经 endorse_ai_authored 判定，
    人工未改动的并入候选（author=ai_endorsed，阈值 1）——「人工没改 = 默认认可」。

    返回 {propose, patterns, conflicts, ai_skipped, endorsed}：
      propose=True 当且仅当 pattern 级修改 ≥ threshold 条且 guards 全部通过。
    只提议，不自动发布——发布仍须用户显式确认。
    """
    merged = list(changes or [])
    endorsed: list[dict] = []
    if ai_ledger:
        e = endorse_ai_authored(ai_ledger, review_changes or [])
        endorsed = e["endorsed"]
        merged.extend(endorsed)
    r = classify_changes(merged)
    patterns = r["pattern"]
    guards = check_guards(patterns)
    propose = len(patterns) >= threshold and not guards
    return {"propose": propose,
            "patterns": patterns,
            "conflicts": r["conflicts"],
            "ai_skipped": len(r["ai_generated"]),
            "endorsed": endorsed,
            "guards": guards,
            "message": (f"发现 {len(patterns)} 处同类口径/句式修改（含人工未改动的 AI 写法），建议沉淀为技能修订"
                        if propose else "无可沉淀的修改（不足频次或未过红线）")}


def check_guards(pattern_changes: list[dict]) -> list[str]:
    """防退化红线检查；返回问题清单（空 = 可提草稿）。"""
    problems = []
    for c in pattern_changes or []:
        if not c.get("after"):
            problems.append(f"{c.get('id', '?')}: 缺 after（无修改后内容）")
        if not (c.get("source") or c.get("note") or c.get("why")):
            problems.append(f"{c.get('id', '?')}: 缺溯源（哪次修改/为什么）")
        if str(c.get("after", "")).strip() == str(c.get("before", "")).strip():
            problems.append(f"{c.get('id', '?')}: before==after，无实质修改")
    return problems


def draft_skill_patch(target_skill: str, current_md: str, pattern_changes: list[dict],
                      meta: dict | None = None) -> dict:
    """把 pattern 级修改归纳为修订后的 SKILL.md（增量，不覆盖原文）。

    策略（保守）：在 SKILL.md 末尾追加「## 自我进化修订记录（RSI）」小节，
    每条修订一行：- [日期][技能] 修改前「before」→ 修改后「after」（理由；来源）。
    若 current_md 已有该小节，追加到该小节末尾（幂等）。
    绝不改写原有正文（大改需人工；本函数只做记录式增量）。
    """
    lines = []
    m = meta or {}
    for c in pattern_changes or []:
        before = str(c.get("before", "")).replace("\n", " ")[:120]
        after = str(c.get("after", "")).replace("\n", " ")[:120]
        why = str(c.get("why") or c.get("note") or "用户修改沉淀").replace("\n", " ")[:160]
        src = str(c.get("source") or "user_edit")
        hint = c.get("hint", "")
        line = (f"- [{m.get('date', '')}] {hint}: 「{before}」→「{after}」（{why}；来源 {src}）"
                .replace("（）", "").replace("（；", "（"))
        lines.append(line)
    if not lines:
        return {"target_skill": target_skill, "changed": False, "reason": "无可沉淀的 pattern 修改"}
    block = "\n".join(lines) + "\n"
    if EVO_HEADER in current_md:
        # 追加到该小节末尾（在下一个 ## 小节之前）
        idx = current_md.index(EVO_HEADER)
        tail = current_md[idx:]
        nxt = tail.find("\n## ", len(EVO_HEADER))
        if nxt == -1:
            new_md = current_md.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n"
        else:
            new_md = current_md[: idx + nxt] + "\n" + block + current_md[idx + nxt:]
    else:
        new_md = current_md.rstrip("\n") + "\n\n" + EVO_HEADER + "\n\n" + block
    return {"target_skill": target_skill, "changed": True,
            "patch": {"added_lines": lines, "meta": m},
            "new_markdown": new_md,
            "guards": check_guards(pattern_changes)}
