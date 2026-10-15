# -*- coding: utf-8 -*-
"""change_classify —— 客户改稿的 **diff → 分类 → action**

分两层做，各用其长（**确定性步骤交给工具**）：
  ① **结构 diff（difflib，确定性）**：得到 inserted / deleted / replaced 区块 ——
     回答"哪里多了、少了、变了"。判据是**内容在不在另一稿里**，不是位置。
  ② **身份映射（锚，确定性）**：用 doc_span/quote 把逻辑对象（claim/evidence/node）
     在两稿之间配对 —— 回答"是同一个对象的移动，还是新对象"。

两类结果合起来定 action：

| diff 形态 | 锚映射 | action | ID 处理 |
|---|---|---|---|
| 位置变了、内容相同 | 同一锚 | **move** | **不分配新 ID，只改 anchor** |
| 内容新增、旧稿中不存在 | 无 | **add** | 分配新 ID（draft/candidate） |
| 内容消失、新稿中不出现（且非被移动） | 锚失效 | **delete** | 标 deprecated，**ID 不回收** |
| 数值变 | 同一锚 | **edit_number** | ID 不变；更新 fact 并重算依赖 |
| 文本变、数值未变 | 同一锚 | **edit_claim** | ID 不变；复查 premise_refs/derived_from/证据 |
| 归一化后相同 | 同一锚 | **edit_wording** | 不动图谱 |
| 无法配对 | 无锚可依 | **untraced** | **显式标注，不得默认归因** |

本模块**零 LLM**（可复现）；需要语义判断的部分（新论述该归为何种 claim_type、
删改是否影响结论链）由 LLM 层另行承担，本层只给确定性事实与分类。
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
NUM = re.compile(r"\d+(?:[.,]\d+)?")
WSRE = re.compile(r"[\s，。、；：（）()\[\]【】\"'“”‘’·\-—…]+")


def _norm(s: str) -> str:
    return WSRE.sub("", str(s or ""))


def _nums(s: str) -> set:
    return set(NUM.findall(str(s or "")))


def _lines(t: str):
    return [x for x in (t or "").split("\n")]


def locate(rec: dict, doc: str) -> int:
    """按**锚优先**定位：quote → text → doc_span 校验。失败 -1。"""
    a = rec.get("anchor") or {}
    for cand in (a.get("quote"), rec.get("quote"), rec.get("text")):
        c = str(cand or "").strip()
        if len(c) >= 6:
            p = doc.find(c[:40])
            if p >= 0:
                return p
    ds = a.get("doc_span")
    if isinstance(ds, list) and len(ds) == 2 and 0 <= ds[0] < ds[1] <= len(doc):
        t = _norm(rec.get("text") or rec.get("quote") or "")
        if t and t in _norm(doc):
            return ds[0]
    return -1


def classify(old_text: str, new_text: str, records: list, threshold: float = 0.72) -> dict:
    """返回 {counts, changes}。**确定性**：同输入同输出。"""
    ol, nl = _lines(old_text), _lines(new_text)
    sm = difflib.SequenceMatcher(None, [_norm(x) for x in ol], [_norm(x) for x in nl], autojunk=False)
    inserted, deleted, replaced = [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert":
            inserted.append((i1, i2, j1, j2))
        elif tag == "delete":
            deleted.append((i1, i2, j1, j2))
        elif tag == "replace":
            replaced.append((i1, i2, j1, j2))

    # 位置映射：旧行号 → 新行号（用于判定"内容相同但位置变了"= move）
    def _line_start(lines, k):
        return sum(len(l) + 1 for l in lines[:k])

    old_norm_all = {_norm(l) for l in ol if _norm(l)}
    new_norm_all = {_norm(l) for l in nl if _norm(l)}

    changes = []
    for (i1, i2, j1, j2) in inserted:                       # 新稿中多出的行
        for k in range(j1, j2):
            n = _norm(nl[k])
            if not n:
                continue
            if n in old_norm_all:                            # 旧稿里有 ⇒ 是**搬到别处**
                changes.append({"action": "move_block", "text": nl[k][:60],
                                "anchor_after": {"line": k, "doc_span": [_line_start(nl, k), _line_start(nl, k) + len(nl[k])]},
                                "id_policy": "内容未新增 ⇒ 对应逻辑对象**只改 anchor**"})
            else:
                changes.append({"action": "add", "text": nl[k][:60],
                                "anchor_after": {"line": k, "doc_span": [_line_start(nl, k), _line_start(nl, k) + len(nl[k])]},
                                "id_policy": "分配**新** ID（状态 draft/candidate）",
                                "need_review": True})
    for (i1, i2, j1, j2) in deleted:                         # 旧稿中被删的行
        for k in range(i1, i2):
            n = _norm(ol[k])
            if not n:
                continue
            if n in new_norm_all:                             # 新稿里还在 ⇒ 只是搬走了
                continue
            changes.append({"action": "delete_block", "text": ol[k][:60],
                            "anchor_before": {"line": k, "doc_span": [_line_start(ol, k), _line_start(ol, k) + len(ol[k])]},
                            "id_policy": "对应逻辑对象标 deprecated，**ID 不回收**",
                            "need_review": True})
    for (i1, i2, j1, j2) in replaced:                        # 逐行的替换
        m = min(i2 - i1, j2 - j1)
        for d in range(m):
            o, n = ol[i1 + d], nl[j1 + d]
            if _norm(o) == _norm(n):
                continue
            if _nums(o) != _nums(n):
                changes.append({"action": "edit_number", "old": o[:60], "new": n[:60],
                                "nums_before": sorted(_nums(o)), "nums_after": sorted(_nums(n)),
                                "id_policy": "ID 不变；更新 fact 值并**重算依赖**", "need_replay": True})
            else:
                ratio = difflib.SequenceMatcher(None, _norm(o), _norm(n)).ratio()
                changes.append({"action": "edit_wording" if ratio >= threshold else "edit_claim",
                                "old": o[:60], "new": n[:60], "similarity": round(ratio, 3),
                                "id_policy": "ID 不变" + ("" if ratio >= threshold else "；复查 premise_refs/derived_from/证据"),
                                "need_replay": ratio < threshold})

    # ── 身份映射：用锚把逻辑对象在两稿间配对 ──
    for rec in records:
        rid = str(rec.get("id"))
        p_old, p_new = locate(rec, old_text), locate(rec, new_text)
        if p_new < 0 and p_old < 0:
            changes.append({"action": "untraced", "id": rid,
                            "reason": "两稿均无法按锚定位（文本非逐字）⇒ **不得默认归因**",
                            "need_review": True})
        elif p_new < 0 <= p_old:
            changes.append({"action": "delete", "id": rid,
                            "anchor_before": {"doc_span": [p_old, p_old + 40]},
                            "id_policy": "标 deprecated，**ID 不回收**", "need_review": True})
        elif p_old < 0 <= p_new:
            changes.append({"action": "untraced", "id": rid,
                            "reason": "新稿命中、旧稿无对应 ⇒ 待人工确认是否同一对象", "need_review": True})
        elif p_old != p_new:
            changes.append({"action": "move", "id": rid,
                            "anchor_before": {"doc_span": [p_old, p_old + 40]},
                            "anchor_after": {"doc_span": [p_new, p_new + 40]},
                            "id_policy": "★ **同一对象 ⇒ 只改 anchor，ID 不变**",
                            "need_replay": True})
    counts = {}
    for c in changes:
        counts[c["action"]] = counts.get(c["action"], 0) + 1
    return {"counts": counts, "changes": changes,
            "policy": {"identity": "ID 是身份（不因位置变）", "position": "anchor 是位置（可重绑）",
                       "move": "只改 anchor", "delete": "标 deprecated，ID 不回收",
                       "add": "新 ID（draft/candidate）", "untraced": "显式标注，不默认归因"}}


if __name__ == "__main__":
    R = WS / "SHUFE-BDC-2019-001"
    doc = (R / "source" / "normalized.md").read_text(encoding="utf-8")
    claims = json.loads((R / "graph" / "claims.yaml").read_text(encoding="utf-8"))
    print(json.dumps({"classify_ready": True, "records": len(claims)}, ensure_ascii=False))
