# -*- coding: utf-8 -*-
"""skill_evolution（RSI 自我进化核心）回归测试。"""
from __future__ import annotations
from .skill_evolution import classify_changes, check_guards, draft_skill_patch, suggest_evolution, EVO_HEADER


def _changes():
    return [
        # fact 级：数值修改 → 只进图谱，不进 skill
        {"id": "N-1", "action": "edit_number", "before": "18319", "after": "18320", "note": "客户改面积"},
        # pattern 级：口径修改，出现 2 次（同 target）→ 沉淀
        {"id": "CL-口径-1", "action": "edit_claim", "before": "上限口径按最高日用水量", "after": "上限口径按设计日用水量", "why": "口径统一", "author": "user"},
        {"id": "CL-口径-1", "action": "edit_claim", "before": "上限口径按最高日用水量", "after": "上限口径按设计日用水量", "why": "第二处同样修改", "author": "user"},
        # pattern 冲突：同 target 被改成两个不同 after → 待审
        {"id": "CL-句式-1", "action": "edit_wording", "before": "满足规范要求", "after": "符合 GB50009-2012", "why": "补标准号"},
        {"id": "CL-句式-1", "action": "edit_wording", "before": "满足规范要求", "after": "符合 GB50011-2010", "why": "另一个标准号"},
        # 单次 pattern 候选 → candidate，不沉淀
        {"id": "CL-术语-1", "action": "edit_wording", "before": "大楼", "after": "实验楼", "why": "术语归一"},
        # AI 扩写产物 → ai 级，永不沉淀 skill
        {"id": "CL-AI-1", "action": "add", "after": "预计施工期可能对师生出行造成影响", "author": "ai"},
    ]


def test_classify():
    r = classify_changes(_changes())
    assert len(r["fact"]) == 1, r
    assert len(r["pattern"]) == 2, r          # 口径 2 次 → pattern
    assert len(r["candidates"]) == 1, r       # 术语 1 次 → candidate
    assert len(r["conflicts"]) == 1, r        # 句式冲突 → 待审
    assert len(r["ai_generated"]) == 1, r     # AI 扩写 → ai 级
    print(f"[OK] classify → {r['summary']}")


def test_suggest():
    s = suggest_evolution(_changes())
    assert s["propose"] is True, s
    assert s["ai_skipped"] == 1, s
    print(f"[OK] suggest → {s['message']}（ai 跳过 {s['ai_skipped']} 条）")


def test_guards():
    ok = check_guards([{"id": "x", "after": "新写法", "why": "口径统一"}])
    assert ok == [], ok
    bad = check_guards([{"id": "y", "after": ""}])
    assert any("缺 after" in p for p in bad), bad
    bad2 = check_guards([{"id": "z", "after": "同", "before": "同"}])
    assert any("无实质修改" in p for p in bad2), bad2
    print("[OK] guards：缺 after / 无实质修改 / 缺溯源 均被拦截")


def test_draft_patch():
    cur = "# demo skill\n\n## 用法\n\n正文内容……\n"
    r = draft_skill_patch("demo-skill", cur,
                          [{"id": "a", "hint": "口径", "before": "上限口径按最高日",
                            "after": "上限口径按设计日", "why": "口径统一", "source": "user_edit"}],
                          meta={"date": "2026-11-02"})
    assert r["changed"] is True, r
    assert EVO_HEADER in r["new_markdown"], "应有修订记录小节"
    assert "口径" in r["new_markdown"] and "设计日" in r["new_markdown"]
    # 幂等：再次 patch 追加不重复小节
    r2 = draft_skill_patch("demo-skill", r["new_markdown"],
                           [{"id": "b", "hint": "句式", "before": "满足规范", "after": "符合 GB50009",
                             "why": "补标准号", "source": "user_edit"}])
    assert r2["new_markdown"].count(EVO_HEADER) == 1, "小节不得重复"
    print("[OK] draft_skill_patch：增量修订 + 幂等追加")


if __name__ == "__main__":
    test_classify()
    test_suggest()
    test_guards()
    test_draft_patch()
    print("skill_evolution 全部通过 ✓")

