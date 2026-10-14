# -*- coding: utf-8 -*-
"""外部依据层发射器（确定性）：台账 + 切块 + Mandate 条款 + 取值域约束 + 绑定。

同输入同输出：文件哈希、切块 id（sha1）、条款与绑定的溯源指针均由本脚本确定性生成。
"""
import hashlib
import json
import re
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
sys.path.insert(0, str(BUILD))
from external_source import BINDINGS, CONSTRAINTS, DOCS, MANDATES  # noqa: E402

EXT = ROOT / "external"
EXT.mkdir(parents=True, exist_ok=True)

_NAV = re.compile(r"^[\s\u3000]*$|^(首页|返回|上节|下节|目录|查找|检索|关闭|分享|打印|字体|收藏|书签|评论|"
                  r"微信|微博|联系我们|无障碍|登录|退出|注册|搜索|目录\s*返回)\s*$")


def sid(text, prefix):
    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"


def clean_lines(text):
    """剥网页导航噪声：去空行、去纯导航串、折叠超长空白。保留条文与表体。"""
    out = []
    for line in text.split("\n"):
        s = re.sub(r"[\u00a0\u3000]+", " ", line).strip()
        if not s or _NAV.match(s):
            continue
        out.append(s)
    return out


docs_out, chunks, dropped = [], [], 0
for d in DOCS:
    p = WS / d["file"]
    if not p.exists():
        d = {**d, "retrieval_status": "missing", "sha256": "", "bytes": 0, "kept_chunks": 0}
        docs_out.append(d)
        continue
    raw_bytes = p.read_bytes()
    text = raw_bytes.decode("utf-8", errors="replace")
    if d["retrieval_status"] == "failed_403" or text.lstrip().startswith("403 Forbidden"):
        d = {**d, "retrieval_status": "failed_403", "sha256": hashlib.sha256(raw_bytes).hexdigest(),
              "bytes": len(raw_bytes), "kept_chunks": 0}
        docs_out.append(d)
        continue
    if d["file"].endswith(".html"):
        text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", text)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = text.replace("&nbsp;", " ").replace("&ldquo;", "“").replace("&rdquo;", "”") \
                   .replace("&sup2;", "²").replace("&middot;", "·").replace("&le;", "≤") \
                   .replace("&times;", "×").replace("&gt;", ">").replace("&lt;", "<") \
                   .replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    lines = clean_lines(text)
    kept = [l for l in lines if len(l) >= 12]
    dropped += len(lines) - len(kept)
    # 段落级切块：连续短行合并为一块，长行独立成块
    buf, doc_chunks = [], []
    for l in kept:
        if len(l) < 40 and not re.match(r"^\s*(\d+\.\d+|\d+）|（\d+）|[一二三四五六七八九十]、)", l):
            buf.append(l)
            if len(" ".join(buf)) >= 240:
                doc_chunks.append(" ".join(buf)); buf = []
        else:
            if buf:
                doc_chunks.append(" ".join(buf)); buf = []
            doc_chunks.append(l)
    if buf:
        doc_chunks.append(" ".join(buf))
    doc_chunks = [c for c in doc_chunks if len(c) >= 20]
    for i, c in enumerate(doc_chunks):
        chunks.append({"id": sid(f"{d['id']}:{i}:{c}", "xc"), "document_id": d["id"],
                       "index": i, "type": "clause" if re.match(r"^\d+\.\d+", c) else "paragraph",
                       "text": c, "source_doc": d["file"], "source_url": d.get("url", ""),
                       "retrieval_status": d["retrieval_status"]})
    docs_out.append({**d, "sha256": hashlib.sha256(raw_bytes).hexdigest(), "bytes": len(raw_bytes),
                     "kept_chunks": len(doc_chunks)})

(EXT / "documents.yaml").write_text(json.dumps(
    {"note": "外部检索文件台账。与报告（D1）联合处理：报告的技术函数/规则，其取值域约束与推理保证由这些文件提供。"
             "检索状态含 ok / ok_secondary（二手转录）/ ok_partial（表格被剥离）/ ok_mislabeled（文件名与实际内容不符）"
             "/ duplicate / failed_403（不可用）/ missing。",
     "documents": docs_out, "count": len(docs_out)}, ensure_ascii=False, indent=2), encoding="utf-8")

(EXT / "chunks.jsonl").write_text(
    "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding="utf-8")

# Mandate → 溯源到外部 chunk（按条文关键词定位，命中不到则显式留空）
chunk_by_doc = {}
for c in chunks:
    chunk_by_doc.setdefault(c["document_id"], []).append(c)

defs = []
for m in MANDATES:
    cands = chunk_by_doc.get(m["doc"], [])
    probe = re.sub(r"\s+", "", m["text"])[:24]
    hit = [c for c in cands if probe and probe[:14] in re.sub(r"\s+", "", c["text"])]
    if not hit and cands:
        key = re.findall(r"[A-Za-z0-9．.]+", m["clause"])
        if key:
            k = key[0].replace("．", ".")
            hit = [c for c in cands if k and k in c["text"]][:3]
    defs.append({**m, "chunks": [c["id"] for c in hit[:3]],
                 "source_doc": next((d["file"] for d in docs_out if d["id"] == m["doc"]), ""),
                 "source_url": next((d.get("url", "") for d in docs_out if d["id"] == m["doc"]), ""),
                 "trace_status": "located" if hit else "not_located"})

(EXT / "mandates.yaml").write_text(json.dumps(
    {"note": "Mandate 节点（条款级）。role 表示该依据在报告论证中承担的角色："
             "driver 强制驱动 / benchmark 合规基准 / warrant 推理保证 / domain 取值域约束——"
             "同一份文件在不同章节可承担不同角色，不塌缩。",
     "mandates": defs, "count": len(defs),
     "located": sum(1 for d in defs if d["trace_status"] == "located")},
    ensure_ascii=False, indent=2), encoding="utf-8")

(EXT / "constraints.yaml").write_text(json.dumps(
    {"note": "取值域约束：可由代码判定的阈值 / 集合 / 日期约束。mandatory=true 表示规范中标注为强制性条文。",
     "constraints": CONSTRAINTS, "count": len(CONSTRAINTS),
     "mandatory": sum(1 for c in CONSTRAINTS if c.get("mandatory"))},
    ensure_ascii=False, indent=2), encoding="utf-8")

(EXT / "bindings.yaml").write_text(json.dumps(
    {"note": "绑定：报告的技术函数/取值 → 外部依据（Mandate/Constraint）。"
             "这是「报告技术函数依赖关系基于外部检索文件」的机读落地："
             "每条绑定写明 why（为什么该取值必须依赖该依据）与 check（确定性复核入口）。"
             "方向：外部依据 --constrains--> 报告取值；"
             "外部依据 --warrants--> 报告论证；外部依据 --benchmark--> 报告引用；外部依据 --driver--> 报告结构。",
     "bindings": BINDINGS, "count": len(BINDINGS),
     "by_role": {r: sum(1 for b in BINDINGS if b["role"] == r)
                 for r in sorted({b["role"] for b in BINDINGS})}},
    ensure_ascii=False, indent=2), encoding="utf-8")

# 依赖边（供 graph/relations 与依赖图使用）
edges = []
for b in BINDINGS:
    for m in b["basis"]:
        edges.append({"from": m, "to": b["report"]["rule"], "type": "constrains"
                      if b["role"] == "constrains" else ("supports" if b["role"] == "warrants" else "depends_on"),
                      "binding": b["id"], "role": b["role"]})
    for c in b["constraints"]:
        edges.append({"from": c, "to": b["id"], "type": "depends_on", "binding": b["id"]})
(EXT / "evidence_edges.yaml").write_text(json.dumps(
    {"note": "外部依据 → 报告技术函数的依赖边（十类关系内取用）。",
     "edges": edges, "count": len(edges)}, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps({
    "documents": len(docs_out), "external_chunks": len(chunks),
    "chunks_dropped_as_nav": dropped,
    "mandates": len(defs), "mandates_located": sum(1 for d in defs if d["trace_status"] == "located"),
    "constraints": len(CONSTRAINTS), "mandatory_constraints": sum(1 for c in CONSTRAINTS if c.get("mandatory")),
    "bindings": len(BINDINGS), "edges": len(edges),
    "by_status": {s: sum(1 for d in docs_out if d["retrieval_status"] == s)
                  for s in sorted({d["retrieval_status"] for d in docs_out})},
}, ensure_ascii=False, indent=2))
