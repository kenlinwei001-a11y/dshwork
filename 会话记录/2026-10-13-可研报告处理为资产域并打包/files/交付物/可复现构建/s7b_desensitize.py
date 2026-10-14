# -*- coding: utf-8 -*-
"""脱敏骨架确定性重建（修正 kp stage_7 的嵌套替换缺陷）。

缺陷（kp corpus_pipeline.stage_7_desensitize）：
    对每个 chunk 取 sorted(set(_NUM.findall(text)), key=len, reverse=True) 后逐个
    text.replace(num, "{{node:NID}}")。占位符本身含数字（NID 是 12 位十六进制），
    因此**先插入的占位符会被后续较短的“数字”再次命中并再次替换**，产出形如
        {{node:N-{{node:N-84523f29f{{node:N-43d7eb9e52fd}
    的嵌套错乱骨架；等长数字之间又依赖 set 迭代顺序（受 PYTHONHASHSEED 影响），
    导致同输入两次运行结果不同（实测 1178 块中 84 行不一致）。

修正：用一次性左到右扫描 re.sub(sub, text) 替换，产出文本不再被重新扫描；
映射仍为 (chunk_id, 原值字符串) → 事实节点 ID（数值单源不变）。
"""
import json
import re
import sys
from pathlib import Path

KP = "/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert"
sys.path.insert(0, KP)
from corpus_pipeline import stable_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent / "SHUFE-BDC-2019-001"
_NUM = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?%?")
_PH = re.compile(r"\{\{node:(N-[0-9a-f]+)\}\}")


def jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


chunks = jsonl(ROOT / "chunks" / "chunks.jsonl")
graph = json.loads((ROOT / "graph" / "graph.yaml").read_text(encoding="utf-8"))

fact_map = {}
for f in graph["facts"]:
    fact_map[(f.get("source"), str(f.get("value")))] = f["id"]

# ★ 值唯一时的映射回退：同一量值常在多个 chunk 出现，而事实记录只指向其中一个来源；
#   若只按 (来源, 值) 匹配，其余出现处会「找不到 fact」→ 同一量值在部分 chunk 是占位符、
#   在另一些是字面值，**违反单源真理**。故对「在所有事实中值唯一」的字面值允许按值映射
#   （唯一才映射，避免 "1"、"2" 这类歧义值被错误指向某个节点）。
from collections import Counter as _C
_vc = _C(str(f.get("value")) for f in graph["facts"])
value_only = {str(f.get("value")): f["id"] for f in graph["facts"] if _vc[str(f.get("value"))] == 1}

# ★ 非独立值契约（推导式操作数/区间端点）：显式声明为「非独立事实」，
#   不计入未建模缺口。这是**显式声明**而非静默忽略——理由可在契约文件里查。
_ns_file = ROOT / "quality" / "nonstandalone_values.json"
NONSTANDALONE = {}
if _ns_file.exists():
    NONSTANDALONE = (json.loads(_ns_file.read_text(encoding="utf-8")) or {}).get("values") or {}

# ── 修复：**不再凭空造 id** ────────────────────────────────────────
# 原实现：fact_map 未命中时用 stable_id(f"{cid}:{raw}") 现造一个 N- id ——
# 生成 1,612 个「形态合法但图谱中不存在」的假引用，且当时无任何门禁能发现
#（K6 只校验占位符形态，不校验可解析性）。
# ★ 原则（更根本）：**不强求每个字面值都必须找到 fact**。
#   旧实现之所以会造假，根因就是「必须变成占位符」这个隐含要求：契约一旦要求
#   "每个数字都要有节点"，执行者（脚本或 LLM）就会补齐 —— 也就是造假。
#   正确做法：**允许它没有节点** —— 有节点 ⇒ {{node:...}}；无节点 ⇒ 字面值原样保留，
#   仅在 gaps_unmodeled_values.json 里**登记备查**（登记 ≠ 缺陷，是事实陈述）。
skeletons, replaced, unmodeled_only = [], 0, []
for c in chunks:
    def _sub(m, _cid=c["id"]):
        global replaced
        raw = m.group(0)
        nid = fact_map.get((_cid, raw)) or value_only.get(raw)   # ★ 唯一值回退
        replaced += 1
        if nid:
            return "{{node:%s}}" % nid
        # 图谱中无对应节点：显式留白，并登记缺口（不估算、不伪造）
        # 分类：紧邻字母/数字的片段多为**标识符片段**（如 2019ZX054 被拆成 2019/054），
        # 并非待建模的量值；只有独立出现的（前后非字母数字）才疑似真实量值缺口。
        _i = m.start()
        _b = c["text"][_i - 1] if _i > 0 else ""
        _a = c["text"][m.end()] if m.end() < len(c["text"]) else ""
        _frag = bool((_b.isalnum() and _b.isalpha()) or (_a.isalnum() and _a.isalpha()))
        # ★ 生成时即分类，避免「未建模数值」被误读为「缺失的量值」：
        #   绝大多数是页码/编号/年份/序号，不是量值。真实量值缺口以**带单位**为判据。
        # ★ 只用**无歧义单位**：中文单位词歧义太大
        #   （"项" 会撞 "项目概况"、"人" 会撞 "人员"、"个" 会撞 "个别"…），
        #   曾导致把目录章节号 "1.1 / 3.1" 误判为真实量值缺口。
        #   并要求单位后是**边界**（空白/标点/行尾），避免撞词。
        _UNITS = ("万元", "平方米", "㎡", "米", "kW", "kWh", "h-1", "m³/h", "m³", "dB", "%")
        _tail = c["text"][m.end():m.end() + 8]
        _m = re.match(r"\s*(" + "|".join(re.escape(u) for u in _UNITS) + r")(?![\u4e00-\u9fff])", _tail)
        if raw in NONSTANDALONE:
            _cls = "nonstandalone_operand"          # 已声明：公式操作数/区间端点
        elif _m:
            # 带单位量值再分两类：图谱里**有值但歧义**（⇒ 重复事实，违背单源真理）
            #                  vs 图谱里**根本没有**（⇒ 真实抽取缺口）
            if raw in _vc:
                _cls = "quantity_value_collision"
            else:
                _cls = "quantity_absent_in_graph"
        elif _frag:
            _cls = "identifier_fragment"
        elif re.match(r"^(19|20)\d{2}$", raw):
            _cls = "year_or_serial"
        elif len(raw) <= 3:
            _cls = "short_number"
        else:
            _cls = "other_number"
        unmodeled_only.append({"chunk": _cid, "value": raw,
                             "kind": _cls,
                             "reason": {"identifier_fragment": "标识符片段（非量值）",
                                        "year_or_serial": "年份/序号（非量值）",
                                        "short_number": "短数字且无单位（多为序号/页码）",
                                        "other_number": "无单位数字（多为页码/编号）",
                                        "quantity_value_collision": "带单位量值：**不同事实共用同一数值**（合法撞车，非缺陷，故不映射）",
                                        "quantity_absent_in_graph": "**带单位量值且图谱中完全不存在（真实抽取缺口）**",
                                        "nonstandalone_operand": NONSTANDALONE.get(raw, "已声明为非独立值")}[_cls]})
        return raw                      # ★ 不强求有节点：字面值原样保留

    text = _NUM.sub(_sub, c["text"])
    skeletons.append({**{k: v for k, v in c.items() if k != "text"}, "text": text})

(ROOT / "chunks" / "skeletons.jsonl").write_text(
    "\n".join(json.dumps(s, ensure_ascii=False) for s in skeletons), encoding="utf-8")

# 节点倒排（与 kp emit_index 同口径，但基于修正后的骨架）
node_index = []
for s in skeletons:
    for nid in _PH.findall(s["text"]):
        node_index.append({"node": nid, "chunk": s["id"], "role": "value"})
(ROOT / "index" / "node_index.json").write_text(
    json.dumps(node_index, ensure_ascii=False, indent=2), encoding="utf-8")

# 缺口台账（显式暴露「图谱未覆盖的数值」真实规模）
(ROOT / "quality" / "gaps_unmodeled_values.json").write_text(
    json.dumps({"count": len(unmodeled_only),
                "by_kind": {k: sum(1 for x in unmodeled_only if x["kind"] == k)
                            for k in ("nonstandalone_operand", "identifier_fragment", "year_or_serial", "short_number",
                                      "other_number", "quantity_value_collision",
                                      "quantity_absent_in_graph")},
                "real_gap": sum(1 for x in unmodeled_only if x["kind"] == "quantity_absent_in_graph"),
                "nonstandalone": sum(1 for x in unmodeled_only if x["kind"] == "nonstandalone_operand"),
                "value_collisions": sum(1 for x in unmodeled_only
                                     if x["kind"] == "quantity_value_collision"),
                "coverage": round(len(fact_map) / max(replaced, 1), 4),
                "note": "未建模的字面值登记（**不强求必须有节点**）。原实现会为其伪造 N- id —— 造假的根因正是「必须找到 fact」这一隐含要求。"
                        "quantity_candidate 才是疑似抽取缺口，identifier_fragment 属正则过度匹配",
                "items": unmodeled_only[:2000]}, ensure_ascii=False, indent=2), encoding="utf-8")

# 自检：不得出现嵌套占位符
nested = [s["id"] for s in skeletons if "{{node:N-{{" in s["text"] or "}}}" in s["text"]]
bad_ph = [s["id"] for s in skeletons
          if re.search(r"\{\{(?!node:N-[0-9a-f]{12}\}\})[^}]*\}\}", s["text"])]

defect = {
    "id": "TD-1", "artifact": "chunks/skeletons.jsonl + index/node_index.json",
    "location": "corpus_pipeline/__init__.py :: stage_7_desensitize",
    "severity": "high",
    "summary": "脱敏替换对已插入的占位符二次替换，产生嵌套错乱骨架，并因 set 迭代顺序受 PYTHONHASHSEED 影响而不确定。",
    "root_cause": "text.replace 逐个替换 + 占位符（12 位十六进制 NID）本身含数字；等长数字的迭代顺序来自 set。",
    "effect": "下游 Agent 拿到的脱敏骨架数值槽位错乱；node_index 随之失真；同输入两次运行输出不一致。",
    "fix": "改为一次性 re.sub 左到右扫描（本脚本），产出文本不再被重新扫描。",
    "measured": {"chunks": len(skeletons), "numeric_slots": replaced,
                 "nested_placeholders_after_fix": len(nested), "malformed_placeholders_after_fix": len(bad_ph)},
    "note": "未改动上游工程代码，仅在本工作区内以确定性脚本重建该产物，并留痕于此。",
}
(ROOT / "quality" / "tool_defects.yaml").write_text(json.dumps(
    {"note": "知识处理链路中发现的工具层缺陷与绕行记录（均未改动上游工程，仅在本包内确定性绕行并留痕）。",
     "defects": [defect, {
         "id": "TD-2", "artifact": "outline.yaml", "location": "corpus_pipeline/__init__.py :: _parse_heading",
         "severity": "medium",
         "summary": "把「1.财经特色鲜明，学科优势明显。……」这类**编号列表项**判定为标题，实测多出 20+ 个假章节。",
         "fix": "章节结构改由 docx w:pStyle 1/2/3 权威给出（build/s0_docx2md.py + s4_pipeline.py）。",
     }, {
         "id": "TD-3", "artifact": "style/section_templates/*", "location": "corpus_pipeline/full_emit.py :: emit_style",
         "severity": "medium",
         "summary": "直接用章节标题作文件名：标题含「/」会断裂路径，过长触发 OSError: File name too long。",
         "fix": "传入文件名安全标题副本（/ → ／、截断 60 字符），outline.yaml 保留真实标题。",
     }, {
         "id": "TD-4", "artifact": "quality/gate_report.yaml", "location": "corpus_pipeline/quality_gates.py :: gate_qg1",
         "severity": "low",
         "summary": "QG1 要求切片带来源锚点（section/source_anchors/document_id），而 stage_3_chunk 只产出 span。",
         "fix": "新增 build/s7_anchors.py，按 chunk 顺序遍历标题栈补齐 document_id + section_path + char_span。",
     }, {
         "id": "TD-5", "artifact": "graph/rules.yaml", "location": "corpus_pipeline/domain_rules.py :: DOMAIN_REGISTRY",
         "severity": "medium",
         "summary": "领域规则注册表只注册「产线类可研」计算规格（新增生产线数量/合格产能/单套变动成本…），"
                    "对高校科研用房项目直接注入构成跨项目污染。",
         "fix": "建库时显式不传 doc_type；本域规则由语义层从原文抽取（见 build/extractions*/）。",
     }]}, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps({"chunks": len(skeletons), "numeric_slots_replaced": replaced,
                  "node_index_entries": len(node_index),
                  "nested_after_fix": len(nested), "malformed_after_fix": len(bad_ph)},
                 ensure_ascii=False, indent=2))


# ★ 环节自报（四元交叉的 A 来源；必须由本环节自己写，不得由 harness 代写）
try:
    import sys as _sys2
    _sys2.path.insert(0, str(Path(__file__).resolve().parent)) if "Path" in dir() else None
    from self_report import declare as _declare
    _declare("s5a", ['SHUFE-BDC-2019-001/chunks/skeletons.jsonl',
                              'SHUFE-BDC-2019-001/quality/gaps_unmodeled_values.json'], script="s7b_desensitize.py")
except Exception as _e:
    print(f"[self_report] 未写出: {_e}")
