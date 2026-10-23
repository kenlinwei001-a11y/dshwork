# -*- coding: utf-8 -*-
"""kp_toolkit.vague_refs —— 扫描「只写基于GB/符合规范、没给具体标准号」的引用。

这是真缺陷：读者无法核验引的是哪一版哪一条，也无法判是否现行有效。

三类必须排除的误报：
  ① 警示语（「不得据此判定符合规范」「状态待核」）—— 那是标注，不是引用
  ② 规范内部引用（「本规范」「本标准」）—— 指自己，不是外部引用
  ③ 同句已给标准号或书名号 —— 已明确，不算模糊

对外：
    scan(nodes, relations=None)  -> {count, by_word, by_source, items}
"""
import re
from collections import Counter

VAGUE = ["基于GB", "依据GB", "按GB", "符合GB", "根据GB", "按照GB",
         "符合规范", "按规范", "依据规范", "根据规范", "按照规范",
         "符合标准", "按标准", "依据标准", "根据标准",
         "相关规范", "相关标准", "现行规范", "现行标准", "规范要求", "标准要求",
         "有关规定", "有关标准"]
STD_NO = re.compile(r"(GB\s*/?\s*T?\s*\d{4,5}(?:[-—]\d{4})?|JGJ\s*\d+(?:[-—]\d{4})?|"
                    r"DGJ\s*[\dA-Z]+(?:[-—]\d{4})?|CJJ\s*\d+|建标\s*\d+(?:[-—]\d{4})?)")
WARN = re.compile(r"(不得据此判定|状态待核|未取到条款)")
SELF = re.compile(r"本规范|本标准|本办法|本规定")


def vague_hits(text):
    """返回真正模糊的引用片段（已排除三类误报）。"""
    t = str(text or "")
    if WARN.search(t): return []
    out = []
    for w in VAGUE:
        for m in re.finditer(re.escape(w), t):
            tail = t[m.start():m.start() + 30]
            if STD_NO.search(tail): continue            # 后接编号
            if "《" in tail: continue                    # 后接书名号
            ss = max(t.rfind("。", 0, m.start()), t.rfind("；", 0, m.start())) + 1
            se_cands = [x for x in (t.find("。", m.end()), t.find("；", m.end())) if x > 0]
            se = min(se_cands) if se_cands else len(t)
            sent = t[ss:se]
            if STD_NO.search(sent) or "《" in sent: continue   # 同句已明确
            seg = t[max(0, m.start() - 8):m.start()]
            if SELF.search(seg) or SELF.search(tail): continue  # 规范内部引用
            out.append({"word": w,
                        "context": t[max(0, m.start() - 40):m.start() + 50].replace("\n", " ")})
    return out


def scan(nodes, relations=None):
    """扫描节点（fact/claim）与关系的模糊引用。"""
    items = []
    for n in nodes:
        if n.get("kind") not in ("quantity", "text", "fact", "claim", "judgment"): continue
        for h in vague_hits(n.get("value")):
            items.append({"object": n.get("id"), "object_kind": n.get("kind"),
                          "section": n.get("section"),
                          "text": str(n.get("value"))[:150],
                          "vague_word": h["word"], "context": h["context"][:130],
                          "source": "node"})
    for r in (relations or []):
        q = str((r.get("source") or {}).get("quote") or "")
        for h in vague_hits(q):
            items.append({"object": str(r.get("from")) + " → " + str(r.get("to")),
                          "object_kind": "relation:" + str(r.get("type")),
                          "section": None, "text": q[:150],
                          "vague_word": h["word"], "context": h["context"][:130],
                          "source": "relation"})
    seen, uniq = set(), []
    for x in items:
        k = (x["object"], x["vague_word"])
        if k in seen: continue
        seen.add(k); uniq.append(x)
    return {"count": len(uniq),
            "by_word": dict(Counter(x["vague_word"] for x in uniq)),
            "by_source": dict(Counter(x["source"] for x in uniq)),
            "items": uniq}
