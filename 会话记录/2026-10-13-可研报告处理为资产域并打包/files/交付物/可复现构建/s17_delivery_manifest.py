# -*- coding: utf-8 -*-
"""投递清单生成（确定性）：把语料包每个路径归类为「注入 / 按节推送 / 工具读取 / 按需借形 / 禁止」。

依据包内真实文件枚举，给出精确条数与体积；同输入同输出。
"""
import json
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
DELIV = WS / "交付物"
ROOT = DELIV / "SHUFE-BDC-2019-001"
W = DELIV / "写作输入"


def sz(p):
    p = Path(p)
    if p.is_dir():
        fs = [f for f in p.rglob("*") if f.is_file()]
        return len(fs), sum(f.stat().st_size for f in fs)
    return 1, p.stat().st_size


def kb(b):
    return f"{b/1024:.1f} KB" if b < 1024 * 1024 else f"{b/1024/1024:.2f} MB"


# 分类规则：(匹配函数, 形式, 时机, 说明)
INJECT = {
    "写作输入/推演写作输入包.md": ("粘贴为上下文（每章恒定）", "开局一次",
                                     "写作纪律 8 条 + 项目信息 + 304 章覆盖核销 + 逐章索引 + 冲突 15 条 + 缺口 15 条 + 依据判定 15 条 + 术语口径 + 投递分层"),
    "写作输入/章节提示词索引.md": ("粘贴为上下文（每章恒定）", "开局一次",
                                     "10 个章节族各一次（prepare/must_state/must_not/review/shape）+ 16 章族归属与本项目注入"),
    "写作输入/知识资产索引.md": ("粘贴为上下文（每章恒定）", "开局一次",
                                  "16 域 + 2 项扩展资产的索引与路径；**只给索引，不要注入域文件本身**"),
    "写作输入/交接说明-给推演写作专家.md": ("给人看，不注入", "你自己照着做",
                                              "流程、MCP 启动、可粘贴提示词、验收清单"),
}
INJECT_AUTO = {
    "SHUFE-BDC-2019-001/manifest.yaml": ("MCP 入口 + constraints 段注入", "开局一次",
                                          "30 文件契约、指纹、constraints 四条硬约束、writing_contract"),
    "SHUFE-BDC-2019-001/meta.yaml": ("注入", "开局一次", "文档元信息"),
    "SHUFE-BDC-2019-001/style/style_profile.yaml": ("注入", "开局一次",
                                                      "数字格式、术语归一、禁用词、引用格式、占位符形式"),
    "SHUFE-BDC-2019-001/index/term_index.json": ("注入（术语表段）", "开局一次", "术语归一表"),
    "SHUFE-BDC-2019-001/quality/gate_report.yaml": ("注入（仅结论行）", "开局一次", "上游闸门结论"),
}
PUSH = {"SHUFE-BDC-2019-001/project/work_packages": ("MCP 读 / 编排器逐节推", "每到一节推一个", None)}
TOOL_SINGLE = {  # 工具读取；禁止整文件读的要单独标
    "SHUFE-BDC-2019-001/chunks/chunks.jsonl": ("工具按 chunk id 取单条", "需要逐字原文时",
                                                "**禁止整文件读**（830 KB 原文，整文件读会让 Agent 从「写」变「抄」）"),
    "SHUFE-BDC-2019-001/chunks/skeletons.jsonl": ("工具按 chunk id 取单条", "需要结构参照时",
                                                   "**禁止整文件读**（874 KB）；数值已替换为 {{node:N-xxx}}"),
    "SHUFE-BDC-2019-001/evidence/evidence.yaml": ("工具读取（evidence_get）", "每节取证据时", None),
    "SHUFE-BDC-2019-001/graph/graph.yaml": ("**禁止**", "—", "220 KB 整包图，不给"),
}


def classify(rel):
    if rel in INJECT:
        return INJECT[rel]
    if rel in INJECT_AUTO:
        return INJECT_AUTO[rel]
    if rel in TOOL_SINGLE:
        return TOOL_SINGLE[rel]
    if rel.startswith("SHUFE-BDC-2019-001/project/work_packages"):
        return ("编排器逐节推送（对应 SKILL 通道③内嵌）", "每到一节推一个",
                "含 outline.must_cover / facts≤30 + 分页 / claims / conflicts / gaps / undefined / 返回契约")
    if rel.startswith("SHUFE-BDC-2019-001/graph/"):
        return ("工具读取（graph_query / graph_get_node / graph_explain / graph_why / graph_impact）", "每节按需", None)
    if rel.startswith("SHUFE-BDC-2019-001/style/section_templates"):
        return ("工具读取（corpus_get_skeleton）", "每节一次", "章节骨架：段落顺序 / 表格列结构 / 论证句式槽位")
    if rel.startswith("SHUFE-BDC-2019-001/style/"):
        return ("工具/注入（风格与逐章提示）", "开局或每节", None)
    if rel.startswith("SHUFE-BDC-2019-001/index/"):
        return ("工具读取（corpus_where_used 等）", "按需", None)
    if rel.startswith("SHUFE-BDC-2019-001/quality/"):
        return ("注入（conflicts/gaps 内嵌）+ 工具（gate_check）", "开局 + 收尾", None)
    if rel.startswith("SHUFE-BDC-2019-001/external/"):
        return ("工具读取（依据条款与判定）", "写技术章 / 核引用时", "条文全文按需取；判定表开局可注入要点")
    if rel.startswith("SHUFE-BDC-2019-001/reuse/"):
        return ("按需读文件（借形，走知识资产索引）", "需要某域形态时**只读那一个文件**", "**不要整目录注入**")
    if rel.startswith("SHUFE-BDC-2019-001/reasoning/"):
        return ("工具读取（graph_explain 的 narrative_zh 来源）", "每节", None)
    if rel.startswith("SHUFE-BDC-2019-001/source/") or rel.endswith("provenance.yaml"):
        return ("不给（仅留档）", "—", "原文二进制与全程溯源链，Agent 不需要")
    if rel.startswith("SHUFE-BDC-2019-001/wp/"):
        return ("给人看的镜像（工具读的是 project/work_packages/）", "—", "YAML 版工作包，便于人工查阅")
    if rel.startswith("交付物/写作输入/chapters/"):
        return ("路线 B 才用：逐章粘贴（一次一章）", "无 MCP 通道时", None)
    if rel.startswith("交付物/写作输入/"):
        return ("见上方注入清单", "—", None)
    if rel.startswith("交付物/审计/") or rel.startswith("交付物/外部核查/") or rel.startswith("交付物/可复现构建/"):
        return ("给人看，不注入", "人工复核时", None)
    if rel.endswith("装配输入包-报告还原.md"):
        return ("给人看的全文版，**不注入**", "人工检索时", "200 KB；注入档已覆盖其要点")
    return ("其他", "—", None)


rows = []
# 写作输入（交付物层）
for f in sorted(W.glob("*.md")):
    rel = str(f.relative_to(DELIV))
    form, when, note = classify(rel)
    _, b = sz(f)
    rows.append((rel, form, when, kb(b), note or ""))
ch = sorted((W / "chapters").glob("*.md"))
_, b = sz(W / "chapters")
rows.append(("写作输入/chapters/（16 个按章切片）", "路线 B 才用：逐章粘贴", "无 MCP 通道时", kb(b),
             "单章 1.3–25.6 KB；有 MCP 时改读 project/work_packages/"))
# 语料包
for p in sorted(ROOT.rglob("*")):
    if p.is_dir():
        continue
    rel = str(p.relative_to(DELIV))
    form, when, note = classify(rel)
    if rel.startswith("SHUFE-BDC-2019-001/style/section_templates/"):
        continue
    if rel.startswith("SHUFE-BDC-2019-001/project/work_packages/"):
        continue
    if rel.startswith("SHUFE-BDC-2019-001/evidence/excerpts/"):
        continue
    if rel.startswith("SHUFE-BDC-2019-001/wp/"):
        continue
    rows.append((rel, form, when, kb(p.stat().st_size), note or ""))
for d, label in [("SHUFE-BDC-2019-001/style/section_templates", "章节骨架（被 corpus_get_skeleton 读取）"),
                 ("SHUFE-BDC-2019-001/project/work_packages", "每节工作包（被 wp_get_facts 读取）"),
                 ("SHUFE-BDC-2019-001/evidence/excerpts", "证据摘录（工具按 id 取单条）"),
                 ("SHUFE-BDC-2019-001/wp", "工作包 YAML 镜像（给人看）")]:
    n, b = sz(ROOT.parent / d)
    form, when, note = classify(d)
    rows.append((f"{d}/（{n} 个文件）", form, when, kb(b), note or label))

# ────────────────────────────────────────── 生成 MD
L = []
A = L.append
A("# 投递清单：给「推演写作专家」输入什么、以什么形式")
A("")
A("> 一句话：**注入 3 个文件（约 52 KB / 27K tokens）+ 起 2 个 MCP 指向语料包 + 逐节推 16 个工作包**。")
A("> 其余一律「工具按需取」，不要粘贴。")
A("")
A("---")
A("")
A("## 甲、注入（粘贴为上下文，开局一次）")
A("")
A("| 文件 | 体积 | 形式 | 内容 |")
A("|------|------|------|------|")
for r in rows:
    if r[0].startswith("写作输入/") and r[1].startswith("粘贴"):
        A(f"| `{r[0]}` | {r[3]} | {r[1]} | {r[4]} |")
A("")
A("**另外这几项由 MCP 的开局调用自动进入注入段**（你不用手工粘）：")
A("")
A("| 文件 | 形式 | 内容 |")
A("|------|------|------|")
INJECT_ADJACENT = {
    "SHUFE-BDC-2019-001/manifest.yaml": "30 文件契约、指纹、constraints 四条硬约束、writing_contract",
    "SHUFE-BDC-2019-001/meta.yaml": "文档元信息",
    "SHUFE-BDC-2019-001/style/style_profile.yaml": "数字格式、术语归一、禁用词、引用格式、占位符形式",
    "SHUFE-BDC-2019-001/index/term_index.json": "术语归一表",
    "SHUFE-BDC-2019-001/quality/gate_report.yaml": "上游闸门结论（仅结论行）",
    "SHUFE-BDC-2019-001/quality/conflicts.yaml": "15 条待审冲突（必须全程可见，不可裁决）",
    "SHUFE-BDC-2019-001/quality/gaps.yaml": "15 条缺口（必须全程可见，正文留白）",
}
for rel, desc in INJECT_ADJACENT.items():
    form = next((r[1] for r in rows if r[0] == rel), "注入")
    A(f"| `{rel}` | {form} | {desc} |")
A("")
A("---")
A("")
A("## 乙、按节推送（编排器每到一节推一个）")
A("")
A("| 文件 | 形式 | 时机 | 内容 |")
A("|------|------|------|------|")
for r in rows:
    if r[0].startswith("SHUFE-BDC-2019-001/project/work_packages"):
        A(f"| `{r[0]}` | {r[1]} | {r[2]} | {r[4]} |")
A("")
A(f"16 个节 id：")
A("")
A("```")
wps = sorted((ROOT / "project" / "work_packages").glob("*.json"))
for f in wps:
    A(f.stem)
A("```")
A("")
A("---")
A("")
A("## 丙、工具按需取（**不粘贴**，Agent 用函数取）")
A("")
A("| 路径 | 形式 | 时机 | 说明 |")
A("|------|------|------|------|")
for r in rows:
    if r[0].startswith("SHUFE-BDC-2019-001/") and r[1].startswith(("工具", "编排器逐节推送")):
        A(f"| `{r[0]}` | {r[1]} | {r[2]} | {r[4]} |")
A("")
A("对应函数：`corpus_get_skeleton` `corpus_get_chunk` `corpus_where_used` `graph_query` `graph_get_node` "
  "`graph_explain` `graph_why` `graph_impact` `evidence_get` `gate_check` `wp_get_facts`。")
A("")
A("---")
A("")
A("## 丁、按需读单个文件（借形，走知识资产索引）")
A("")
A("| 路径 | 形式 | 时机 |")
A("|------|------|------|")
for r in rows:
    if r[0].startswith("SHUFE-BDC-2019-001/reuse/"):
        A(f"| `{r[0]}` | {r[1]} | {r[2]} |")
A("")
A("> **不要整目录注入** `reuse/`（141 KB）。上下文里只有 `知识资产索引.md`。")
A("")
A("---")
A("")
A("## 戊、不给（Agent 不需要，给了会变抄写）")
A("")
A("| 路径 | 体积 | 原因 |")
A("|------|------|------|")
BAN_REASON = {
    "SHUFE-BDC-2019-001/graph/graph.yaml": "220 KB 整包图，工具已提供按节点/规则检索，整包给无收益",
    "SHUFE-BDC-2019-001/source/normalized.md": "归一化全文 —— Agent 要原文时按 chunk id 取，不整文件给",
    "SHUFE-BDC-2019-001/source/offset_map.json": "字符偏移映射，仅供溯源工具内部使用",
    "SHUFE-BDC-2019-001/source/original.docx": "原稿二进制（1.07 MB），仅留档",
    "SHUFE-BDC-2019-001/source/assets/（0 个文件）": "图片/资产，本报告无",
    "SHUFE-BDC-2019-001/provenance.yaml": "全程溯源链（工具内部用）",
    "SHUFE-BDC-2019-001/evidence/excerpts/（343 个文件）": "证据摘录全量 318 KB —— 用 evidence_get 按 id 单取",
    "SHUFE-BDC-2019-001/index/signature.yaml": "语料包指纹，工具内部用",
    "写作输入/交接说明-给推演写作专家.md": "给**你**看的操作说明，不注入给写作 Agent",
    "写作输入/投递清单.md": "给**你**看的投递清单",
    "交付物/装配输入包-报告还原.md": "**全文版（200 KB）**，给人检索用；其要点已被注入档覆盖，不要整份注入",
}
for rel, reason in BAN_REASON.items():
    hit = next((r for r in rows if r[0] == rel), None)
    if hit:
        size = hit[3]
    else:
        cand = rel.replace("（0 个文件）", "").replace("（343 个文件）", "").replace("（全文版 §3 事实表）", "")
        f = ROOT.parent / cand
        size = kb(sz(f)[1]) if f.exists() else "—"
    A(f"| `{rel}` | {size} | {reason} |")
for r in rows:
    if r[0].startswith("交付物/审计/") or r[0].startswith("交付物/可复现构建/") \
            or r[0].startswith("交付物/外部核查/") or r[0].endswith("装配输入包-报告还原.md"):
        A(f"| `{r[0]}` | {r[3]} | 人工复核材料，不注入 |")
A("")
A("---")
A("")
A("## 己、没有 MCP 通道时（路线 B 降级）")
A("")
A("| 文件 | 形式 | 体积 |")
A("|------|------|------|")
A("| `写作输入/chapters/NN-*.md`（16 个） | 逐章粘贴，一次一章 | 合计 "
  + kb(sz(W / "chapters")[1]) + " |")
A("")
A("代价：丢掉 `graph_explain` 的推导句、`graph_why` 的冲突决策依据、`gate_check_draft` 机器闸门。"
  "**闸门丢失是主要风险**，须人工补做三项检查（字面数值 / must_cover 缺项 / undefined 引用）。")
A("")
A("---")
A("")
A("## 庚、体积总账")
A("")
A("| 环节 | 体积 |")
A("|------|------|")
inj = sum(sz(W / f)[1] for f in ["推演写作输入包.md", "章节提示词索引.md", "知识资产索引.md"])
A(f"| 注入（3 个文件，一次性） | {kb(inj)} |")
n_wp, b_wp = sz(ROOT / "project" / "work_packages")
A(f"| 每节工作包（{n_wp} 个，逐个推） | 单节 "
  + kb(max(f.stat().st_size for f in (ROOT / 'project' / 'work_packages').glob('*.json'))) + " 以内 |")
A(f"| 工具按需（单次调用） | 100–800 tokens |")
n_all, b_all = sz(ROOT)
A(f"| **语料包全量（不可整包注入）** | **{n_all} 文件 / {kb(b_all)}** |")
A(f"| 整包 ZIP | {kb((WS / '上财大数据研究中心可研-资产域包-v1.zip').stat().st_size)} |")
A("")
A("> 注入 52 KB 对比全量 " + kb(b_all) + " —— 这就是「按需取」的意义。")
A("")

(W / "投递清单.md").write_text("\n".join(L), encoding="utf-8")
print(json.dumps({
    "file": "写作输入/投递清单.md", "bytes": (W / "投递清单.md").stat().st_size,
    "inject_kb": round(inj / 1024, 1),
    "corpus_files": n_all, "corpus_kb": round(b_all / 1024, 1),
    "workpackages": n_wp,
}, ensure_ascii=False, indent=2))
