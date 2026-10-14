# -*- coding: utf-8 -*-
"""客观判据 objective_criteria（确定性，零 LLM）。

**为什么需要**：verify 必须有客观标准，不能依赖 LLM 去「觉得没问题」。
本模块的 12 条判据全部是确定性算法，输出固定结构，判定**不消费 LLM 的意见**。

判据类型仅允许 8 种：
  集合差 / 守恒等式 / 正则计数 / 数值比较 / 哈希一致 / 图算法 / 枚举成员 / 覆盖率比值

**无法客观化的项不得冒充 pass**：标记 `judgment_required`，
既不进自动门禁也不计为通过，交人工。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .closure_verify import (_SKIP_PRED, _j, apply_waivers, load_package,
                             load_waivers)   # fix31-waivers
from .units import same_quantity

CRITERIA: list[dict] = [
    {'id': 'K1', 'kind': '守恒等式', 'name': '解析守恒', 'algo': 'docx <w:tbl> = md 表块；word/media ≥ md 图注', 'threshold': '差 = 0'},
    {'id': 'K2', 'kind': '守恒等式', 'name': '切块守恒', 'algo': 'Σchunk 去空白字符 = 原稿去空白字符', 'threshold': '偏差 ≤ 15%'},
    {'id': 'K3', 'kind': '集合差', 'name': '引用闭环', 'algo': 'set(原稿《》) − set(evidence.doc) − 豁免 = ∅', 'threshold': '依据类缺口 = 0'},
    {'id': 'K4', 'kind': '集合差', 'name': '数值闭环', 'algo': 'set(原稿「数字+单位」) − set(节点值) − 量纲等价 = ∅', 'threshold': '关键单位类缺口 = 0'},
    {'id': 'K5', 'kind': '覆盖率比值', 'name': '关系闭环', 'algo': '应有 claim 关系 − 已有边 = ∅', 'threshold': '四类各 100%'},
    {'id': 'K6', 'kind': '正则计数', 'name': '占位符合规', 'algo': '剥离 {{node:…}} 后手打数字 = 0；占位符形须匹配 ^\\{\\{node:N-[0-9a-f]{12}\\}\\}$', 'threshold': '违规 = 0', 'draft_only': True},
    {'id': 'K7', 'kind': '枚举成员', 'name': '值域合法', 'algo': 'claim_type/status/kind/relation.type ∈ 词表', 'threshold': '越界 = 0'},
    {'id': 'K8', 'kind': '图算法', 'name': '图完整性', 'algo': '每条 relation 端点可寻址；无孤立节点；依赖无环', 'threshold': '违规 = 0'},
    {'id': 'K9', 'kind': '哈希一致', 'name': '溯源可复现', 'algo': 'source_original_sha256 = 实际文件哈希', 'threshold': '一致'},
    {'id': 'K10', 'kind': '覆盖率比值', 'name': '装配覆盖', 'algo': '|defined 且非明细节点 ∩ 成稿引用| / |…|', 'threshold': '≥ 95%', 'draft_only': True},
    {'id': 'K11', 'kind': '数值比较', 'name': '派生闭合', 'algo': '|规则重算值 − 报告声明值| ≤ 容差', 'threshold': '超差项必须登记为待审'},
    {'id': 'K13', 'kind': '集合差', 'name': '事实用逻辑·函数用值', 'algo': 'K13a 事实类字面值 ∩ 资产 = ∅；K13b 函数类值 ⊆ 资产', 'threshold': '残留 = 0 且 丢失 = 0'},
    {'id': 'K14', 'kind': '数值比较', 'name': '依据时效标注', 'algo': 'K14a 生效时间必填（原文无则待核）；K14b 窗口合法；K14c 同月切换单列；K14d 超前核查', 'threshold': '有而未标/越窗/超前 = 0；待核项单列'},
    {'id': 'K12', 'kind': '正则计数', 'name': '论证要件实质存在', 'algo': 'toulmin.warrant/backing 非占位（未写出|不代拟|待补充|无|—|N/A）', 'threshold': '占位率须显式登记，不得计为通过'},
]

PLACEHOLDER = re.compile(r"未写出|不代拟|待补充|^无$|^—$|N/A|^$")
# fix31: K14 判定用——依据原文是否含该标准（含则可判，不含则待核）
RAW_HINT = None
CLAIM_TYPE = {"fact", "hypothesis", "inference", "conclusion", "recommendation"}
CLAIM_STATUS = {"unverified", "supported", "contradicted", "verified"}
NODE_KIND = {"quantity", "judgment", "text"}
_CITE_STD = re.compile(r"标准|规范|规程|通则|办法|规定|通知|规划|纲要|条例|法$|决定|意见|定额|图集|规则|指南|指标|措施|GB|DGJ|JGJ")


def _res(cid, total, covered, missing, thr, note=""):
    missing = list(missing)
    rec = round(covered / max(total, 1) * 100, 1)
    return {"id": cid, "total": total, "covered": covered, "missing_count": len(missing),
            "missing": missing[:50], "recall_pct": rec, "threshold": thr,
            "verdict": "pass" if not missing else "FAIL", "note": note}


def run_objective_criteria(corpus_dir, *, draft_path=None, source_md=None,
                           source_docx=None, declared_sha256=None,
                           compile_point="", effective_dates=None) -> dict:
    root = Path(corpus_dir)
    pk = load_package(corpus_dir)
    led = pk["ledger"] or {}
    src = Path(source_md).read_text(encoding="utf-8") if source_md and Path(source_md).exists() else ""
    draft = Path(draft_path).read_text(encoding="utf-8") if draft_path and Path(draft_path).exists() else ""
    dn = re.sub(r"[\s　]", "", draft)
    R = []

    # K1
    m = []
    if led.get("docx_tables", -1) not in (-1, led.get("tables", -2)):
        m.append(f"docx 表 {led.get('docx_tables')} ≠ md 表块 {led.get('tables')}")
    n_fig = len([c for c in led.get("captions", []) if str(c).startswith("图")])
    if led.get("images_in_docx", -1) > n_fig:
        m.append(f"docx 内嵌图 {led.get('images_in_docx')} > md 图注 {n_fig}")
    R.append(_res("K1", max(led.get("tables", 1), 1),
                  max(led.get("tables", 1) - len(m), 0), m, "差 = 0"))

    # K2
    c_ns = 0
    cf = root / "chunks" / "chunks.jsonl"
    if cf.exists():
        c_ns = sum(len(re.sub(r"\s", "", json.loads(l)["text"]))
                   for l in cf.read_text(encoding="utf-8").splitlines() if l.strip())
    o_ns = len(re.sub(r"\s", "", src)) if src else 0
    dev = abs(c_ns - o_ns) / max(o_ns, 1)
    R.append(_res("K2", o_ns or 1, min(c_ns, o_ns) or 1,
                  ([f"偏差 {dev*100:.1f}% > 15%"] if (o_ns and dev > 0.15) else []), "偏差 ≤ 15%"))

    # K3
    ev_names = " ".join((e.get("doc") or "") + (e.get("quote") or "") for e in pk["evidence"])
    bi = [c for c in led.get("citations", []) if _CITE_STD.search(c)]
    m3 = [c for c in bi if c[:6] not in ev_names and c not in ev_names]
    R.append(_res("K3", len(bi), len(bi) - len(m3), m3, "依据类缺口 = 0"))

    # K4（含量纲归一）
    gv = {re.sub(r"[^\d.]", "", str(n.get("value", ""))) for n in pk["nodes"]}
    tot4, m4 = 0, []
    for item in led.get("valued_numbers", []):
        v, _, u = item.partition(" ")
        if not re.match(r"^\d", v):
            continue
        tot4 += 1
        if v.replace(",", "") in gv:
            continue
        if any(same_quantity(v, u, str(n.get("value", "")), n.get("unit") or "")
               for n in pk["nodes"] if n.get("unit")):
            continue
        m4.append(item)
    R.append(_res("K4", tot4, tot4 - len(m4), m4, "关键单位类缺口 = 0"))

    # K5
    from .relations_ext import derive_expected_relations
    exp = derive_expected_relations(pk["claims"], pk["relations"])
    have = {k: sum(1 for r in pk["relations"] if r.get("type") == k) for k in exp["expected"]}
    m5 = [f"{k}: {have.get(k,0)}/{exp['expected'][k]}" for k in exp["expected"]
          if have.get(k, 0) < exp["expected"][k]]
    R.append(_res("K5", sum(exp["expected"].values()),
                  sum(min(have.get(k, 0), exp["expected"][k]) for k in exp["expected"]), m5, "四类各 100%"))

    # K6（仅成稿版）
    _has_ph = re.search(r"\{\{node:N-[0-9a-f]+\}\}", draft or "") is not None
    if draft and not _has_ph:
        # fix32-K6：成稿不含占位符 ⇒ 这是「已注入值」的可读版，K6 判据对象不适用
        R.append({"id": "K6", "total": 1, "covered": 0, "missing_count": 0, "missing": [],
                  "recall_pct": 100.0, "threshold": "违规 = 0", "verdict": "invalid",
                  "note": "成稿为「已注入值」的可读版（无 {{node:…}} 占位符）；"
                          "K6 只对占位符版成稿有效，本项不适用"})
    elif draft:
        stripped = re.sub(r"\{\{node:N-[0-9a-f]+\}\}", " ", draft)
        # fix31: 白名单——表号(表13-1)/图号/规范编号(GB50016-2014)/条款号(5.1.3)/日期(2019-08)
        _wl = re.compile(r"(表|图)\s?\d+-\d+|GB[/\s]?\d{4,5}(-\d{4})?|JGJ\d+|DGJ\d+|"
                         r"\d+\.\d+\.\d+|\d{4}[-年]\d{1,2}|第\d+条|〔\d{4}〕|\[\d{4}\]")
        _nwl = _wl.sub(" ", stripped)
        bad_num = re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])", _nwl)
        bad_ph = re.findall(r"\{\{(?!node:N-[0-9a-f]{12}\}\})[^}]*\}\}", draft)
        R.append(_res("K6", max(len(bad_num) + len(bad_ph), 1), 0 if (bad_num or bad_ph) else 1,
                      ([f"手打数字 {len(bad_num)} 处"] if bad_num else []) +
                      ([f"占位符形违规 {len(bad_ph)}"] if bad_ph else []), "违规 = 0",
                      "注：对本项目「已注入值」的可读版，此判据仅在占位符版上严格成立"))
    else:
        R.append({"id": "K6", "total": 1, "covered": 0, "missing_count": 1,
                  "missing": ["未提供成稿"], "recall_pct": 0.0, "threshold": "违规 = 0",
                  "verdict": "invalid", "note": "成稿缺失"})

    # K7
    from .relations_ext import CLAIM_RELATIONS
    REL_OK = {"has_value", "has_attribute", "instance_of", "part_of", "causes", "depends_on",
              "supports", "contradicts", "temporal", "located_in"} | set(CLAIM_RELATIONS)
    m7 = [f"claim_type: {c.get('id')}" for c in pk["claims"]
          if c.get("claim_type") and c["claim_type"] not in CLAIM_TYPE]
    m7 += [f"status: {c.get('id')}" for c in pk["claims"]
           if c.get("status") and c["status"] not in CLAIM_STATUS]
    m7 += [f"kind: {n.get('id')}" for n in pk["nodes"] if n.get("kind") and n["kind"] not in NODE_KIND]
    m7 += [f"relation: {r.get('type')}" for r in pk["relations"] if r.get("type") not in REL_OK]
    R.append(_res("K7", len(pk["claims"]) + len(pk["nodes"]) + len(pk["relations"]),
                  len(pk["claims"]) + len(pk["nodes"]) + len(pk["relations"]) - len(m7), m7, "越界 = 0"))

    # K8
    ids = {n.get("id") for n in pk["nodes"]} | {c.get("id") for c in pk["claims"]} | \
          {e.get("id") for e in pk["evidence"]}
    m8 = [f"{r.get('type')}: {r.get('from')}→{r.get('to')}" for r in pk["relations"]
          if (str(r.get("from")) not in ids and not str(r.get("from")).startswith("REF:"))
          or (str(r.get("to")) not in ids and not str(r.get("to")).startswith("REF:"))]
    n_ref = sum(1 for r in pk["relations"] if str(r.get("to", "")).startswith("REF:"))
    R.append(_res("K8", len(pk["relations"]), len(pk["relations"]) - len(m8), m8, "违规 = 0",
                  f"另有 {n_ref} 条指向 REF: 伪节点（依据库未覆盖），单列不判"))

    # K9
    if source_docx and Path(source_docx).exists() and declared_sha256:
        h = hashlib.sha256(Path(source_docx).read_bytes()).hexdigest()
        R.append(_res("K9", 1, 1 if h == declared_sha256 else 0,
                      [] if h == declared_sha256 else ["原稿 sha256 与声明不一致"], "一致"))
    else:
        R.append({"id": "K9", "total": 1, "covered": 0, "missing_count": 1,
                  "missing": ["未提供 source_docx 或声明哈希"], "recall_pct": 0.0,
                  "threshold": "一致", "verdict": "invalid", "note": ""})

    # K10
    if draft:
        tot10, m10 = 0, []
        for n in pk["nodes"]:
            v = re.sub(r"[\s　]", "", str(n.get("value", "")))
            # fix34：外部依据节点不计入装配覆盖分母（语义：依据 ≠ 待引用取值）
            if (len(v) < 3 or _SKIP_PRED.search(n.get("predicate", ""))
                    or n.get("status", "defined") != "defined"
                    or n.get("doc_layer") == "external" or n.get("ext_source")):
                continue
            tot10 += 1
            if v not in dn:
                mm = re.match(r"([\d,]+(?:\.\d+)?)", v)
                ok = bool(mm and (mm.group(1) in dn or mm.group(1).replace(",", "") in dn))
                # fix33：文本量（长值）逐字匹配不可能，按前 10 字前缀判定
                if not ok and n.get("kind") == "text" and len(v) > 20:
                    ok = v[:10] in dn
                if not ok:
                    m10.append(f"{n.get('subject')}·{n.get('predicate')}")
        R.append(_res("K10", tot10, tot10 - len(m10), m10, "≥ 95%"))
    else:
        R.append({"id": "K10", "total": 1, "covered": 0, "missing_count": 1,
                  "missing": ["未提供成稿"], "recall_pct": 0.0, "threshold": "≥ 95%",
                  "verdict": "invalid", "note": ""})

    # K11
    deriv = _j(root / "reasoning" / "derivation.yaml", {})
    diffs = deriv.get("derivation_diff", [])
    # fix31: 超差本身不算缺陷；**未登记为待审**才算（登记即满足纪律）
    _cf = _j(root / "quality" / "conflicts.yaml", [])
    _reg = {(c.get("subject"), c.get("predicate")) for c in _cf}
    over = []
    for d in diffs:
        if abs(d.get("delta", 0)) <= 1.0001:
            continue
        if (d.get("rule"), "重算值 vs 声明值") not in _reg and (d.get("rule"), "派生差异") not in _reg:
            over.append(f"{d.get('rule')}: 重算 {d.get('computed')} vs 声明 {d.get('stated')}"
                        f"（差 {d.get('delta')}）—— **未登记为待审**")
    R.append(_res("K11", max(len(diffs), 1), max(len(diffs) - len(over), 0), over,
                  "超差项必须登记为待审"))

    # K12
    wph = [c.get("id") for c in pk["claims"]
           if PLACEHOLDER.search(str((c.get("toulmin") or {}).get("warrant", "")).strip())]
    bph = [c.get("id") for c in pk["claims"]
           if PLACEHOLDER.search(str((c.get("toulmin") or {}).get("backing", "")).strip())]
    R.append(_res("K12", len(pk["claims"]), len(pk["claims"]) - len(set(wph + bph)),
                  sorted(set(wph + bph)), "占位率须显式登记",
                  f"warrant 占位 {len(wph)}、backing 占位 {len(bph)}"))

    # K13 事实用逻辑·函数用值
    asset_files = sorted((root / "reuse" / "domains").glob("*.yaml")) + \
        [root / "reuse" / "domains.yaml", root / "style" / "section_prompts.yaml"] + \
        sorted((root / "style" / "section_templates").glob("*.yaml"))
    k13 = borrow_form_criterion(pk["nodes"], asset_files)
    R.append(_res("K13", k13["K13a"]["total"], k13["K13a"]["total"] - len(k13["K13a"]["missing"]),
                  [f"事实类残留: {x}" for x in k13["K13a"]["missing"]] +
                  [f"函数类丢失: {x}" for x in k13["K13b"]["missing"]],
                  "残留 = 0 且 丢失 = 0",
                  f"资产文件 {len(asset_files)} 个；K13a 残留 {len(k13['K13a']['missing'])}、"
                  f"K13b 丢失 {len(k13['K13b']['missing'])}"))

    # K14 时效标注
    # 未显式传入时，自动读 external/effective_dates.yaml（生效时间台账）
    if effective_dates is None:
        led2 = _j(root / "external" / "effective_dates.yaml", {})
        effective_dates = {e.get("standard", ""): e.get("effective_date", "")
                           for e in (led2.get("entries") or []) if e.get("standard")}
        compile_point = compile_point or led2.get("compile_point", "")
    k14 = timeliness_criterion(pk["evidence"], compile_point=compile_point,
                               effective_dates=effective_dates)
    R.append(_res("K14", len(pk["evidence"]) or 1,
                  len(pk["evidence"]) - len(k14["K14a"]["missing"]),
                  [f"未标生效时间: {x}" for x in k14["K14a"]["missing"][:20]] +
                  [f"引用窗口越界: {x}" for x in k14["K14b"]["missing"][:20]] +
                  [f"超前引用: {x}" for x in k14["K14d"]["missing"][:20]],
                  "缺失/越窗/超前 = 0",
                  f"同月切换 {len(k14['K14c']['items'])} 条（单列待审，不判 FAIL）"))

    # judgment_required：不进自动判定
    judgment_required = [
        "论证是否成立（用 NLP 打分仍是不确定判定）",
        "证据支持等级 SUPPORT/PARTIAL_SUPPORT/CONTRADICT 的语义判断",
        "取舍是否可接受（业务判断，须客户/编制单位确认）",
    ]
    _w = load_waivers(corpus_dir)
    R = [apply_waivers(r, _w) for r in R]
    crit = {c["id"]: c for c in CRITERIA}
    return {"criteria": [{**r, "kind": crit[r["id"]]["kind"], "name": crit[r["id"]]["name"],
                          "algo": crit[r["id"]]["algo"]} for r in R],
            "judgment_required": judgment_required,
            "summary": {"pass": sum(1 for r in R if r["verdict"] in ("pass", "pass_with_waivers")),
                        "pass_with_waivers": sum(1 for r in R if r["verdict"] == "pass_with_waivers"),
                        "FAIL": sum(1 for r in R if r["verdict"] == "FAIL"),
                        "invalid": sum(1 for r in R if r["verdict"] == "invalid")},
            "policy": "全部判据为确定性算法；判定不消费 LLM 的意见；无法客观化者标 judgment_required"}


def save_objective_report(result: dict, out_path) -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


if __name__ == "__main__":
    import sys
    r = run_objective_criteria(sys.argv[1],
                               draft_path=sys.argv[2] if len(sys.argv) > 2 else None,
                               source_md=sys.argv[3] if len(sys.argv) > 3 else None)
    for x in r["criteria"]:
        print(f"{x['id']:4s} {x['name']:14s} {x['verdict']:8s} 缺 {x['missing_count']}")
    print(r["summary"], "| judgment_required:", len(r["judgment_required"]))

# ------------------------------------------------------------------ K14 时效标注
# 标准/规范/政策有**时间效应**：引用是否成立取决于引用时点是否落在该版本生效窗口内。
K14_FIELDS = ["effective_date", "effective_clause", "supersedes", "time_window"]
K14_VERDICTS = ["生效期内", "未生效·超前引用", "已废止", "同月切换", "待核"]


def timeliness_criterion(evidence, compile_point: str = "", effective_dates: dict | None = None):
    """K14：a 生效时间必填 / b 引用窗口合法 / c 同月切换单列 / d 反向核查。

    compile_point 形如 "2019-08"；effective_dates 形如 {标准名: "2019-08-01"}。
    无法判定者标 `待核`，**不得计为 pass**（与 K14-c 的纪律一致）。
    """
    eff = effective_dates or {}
    a_miss, b_bad, c_switch, d_early, a_pending = [], [], [], [], []
    for e in evidence:
        if (e.get("kind") or "") not in ("standard", "policy", "regulation"):
            continue
        doc = (e.get("doc") or "")
        ed = e.get("effective_date") or next((v for k, v in eff.items() if k and k in doc), "")
        if not ed:
            # fix31: 区分「有而未标」（FAIL）与「原文本来没有」（待核）
            import os
            raw_dir = Path(__file__).resolve().parents[2] / "references" / "raw"
            in_raw = False
            try:
                for rf in raw_dir.glob("*.txt"):
                    t = rf.read_text(encoding="utf-8", errors="replace")
                    if doc.strip("《》")[:10] and doc.strip("《》")[:10] in t:
                        in_raw = True
                        break
            except Exception:                              # noqa: BLE001
                in_raw = False
            (a_miss if in_raw else a_pending).append(doc or e.get("id"))
            continue
        if compile_point and ed[:7] == compile_point[:7]:
            c_switch.append(f"{doc} 生效 {ed} 与编制时点 {compile_point} 同月")
        if compile_point and ed[:7] > compile_point[:7]:
            d_early.append(f"{doc} 生效 {ed} 晚于编制时点 {compile_point}")
        if e.get("superseded_date") and compile_point and e["superseded_date"] <= compile_point:
            b_bad.append(f"{doc} 在编制时点已被替代")
    return {"K14a": {"total": len(evidence), "missing": a_miss[:40],
                     "pending_review": a_pending[:40],
                     "verdict": "FAIL" if a_miss else ("pending_review" if a_pending else "pass"),
                     "note": f"有而未标 {len(a_miss)}、原文无从而待核 {len(a_pending)}"},
            "K14b": {"missing": b_bad[:40], "verdict": "FAIL" if b_bad else "pass"},
            "K14c": {"items": c_switch[:40], "verdict": "pending_review" if c_switch else "pass",
                     "note": "同月切换不直接 FAIL——报告可能确按新版编制；机器无法判定，只能标待审"},
            "K14d": {"missing": d_early[:40], "verdict": "FAIL" if d_early else "pass"}}

# ------------------------------------------------------------------ K13 事实用逻辑·函数用值
# 用户规则：**作为事实输入信息，用它的「逻辑」而不是「值」；但对应函数等等，就需要用它的值。**
# 分界线不是「数字 vs 非数字」，而是「事实 vs 函数」：
#   事实类（某项目专属取值）→ 资产中必须槽位化，**不得残留字面值**
#   函数类（方法/规范/公式常数）→ **必须保留**，剥离则资产不可用
FACT_PRED = re.compile(
    r"^总建筑面积|^地上建筑面积|^地下建筑面积|规划人数|规划科研人员|规划研究生|规划人数合计|"
    r"估算金额|^总投资|建筑面积需求|^层数|用水人数|人数合计|在校生|专职教师|资产总额|收入|"
    r"拆除面积|建筑面积缺口")
FUNC_PRED = re.compile(
    r"系数|费率|指标|定额|标准值|限值|单价|折标|利用率|预备费|未预见|装配率|间距|高度控制|"
    r"换气次数|允许|不小于|不大于|密度|目标|人均")

_STRIP_CTX = re.compile(r"(https?://\S+)|(N-[0-9a-f]{6,})|(\d{4}[-年]\d{1,2}[-月]\d{0,2})")


def _asset_literals(asset_files):
    """资产文件中的字面数值集合（剥离占位符/URL/节点ID/日期后）。"""
    out = set()
    for f in asset_files:
        f = Path(f)
        if not f.exists():
            continue
        t = _PH.sub(" ", f.read_text(encoding="utf-8"))
        t = _STRIP_CTX.sub(" ", t)
        out |= {m.replace(",", "") for m in re.findall(r"\d[\d,]*(?:\.\d+)?", t)}
    return out


_PH = re.compile(r"\{\{node:[^}]+\}\}")


def borrow_form_criterion(nodes, asset_files, *, allowlist=()):
    """K13：事实类不得残留字面值（K13a）；函数类不得丢失（K13b）。

    注意口径：**只看资产文件正文**，不把 JSON 元数据字段（seq/char_len）计入，
    否则会把元数据里的数字误报成泄漏（本项目曾因此把 0 误报为 4150）。
    """
    lits = _asset_literals(asset_files)
    allow = set(allowlist)
    a_leak, b_lost = [], []
    for n in nodes:
        pred = n.get("predicate") or ""
        raw = str(n.get("value") or "")
        key = re.sub(r"[^\d.]", "", raw)
        if len(key.replace(".", "")) < 3 or key in allow:
            continue
        # fix33：**按类别分别匹配**——事实类从严（值+单位），函数类从宽（值或值+单位）
        #   事实类严：避免裸数字碰撞造成假残留
        #   函数类宽：常数常以「0.55」「5%」等裸形式出现在方法描述里，过严会误判为丢失
        unit = (n.get("unit") or "").strip()
        strict = (f"{raw} {unit}".strip() in lits) if unit else (raw in lits)

        def _parts_ok(v):
            """区间/复合值（如 10~15、2.5-3.5）按数字分量分别匹配。"""
            parts = [x for x in re.split(r"[^\d.]+", str(v)) if x]
            return bool(parts) and all(x in lits for x in parts)

        loose = strict or (raw in lits) or (key in lits) or _parts_ok(raw)
        if FACT_PRED.search(pred):
            if strict:
                a_leak.append(f"{n.get('subject')}·{pred} = {raw} {n.get('unit') or ''}".strip())
        elif FUNC_PRED.search(pred) and not loose:
            b_lost.append(f"{n.get('subject')}·{pred} = {raw} {n.get('unit') or ''}".strip())
    return {"K13a": {"total": sum(1 for n in nodes if FACT_PRED.search(n.get("predicate") or "") and
                                  len(re.sub(r"[^\d.]", "", str(n.get("value") or "")).replace(".", "")) >= 3),
                     "missing": a_leak[:40], "verdict": "FAIL" if a_leak else "pass",
                     "note": "事实类取值不得继承——出现字面值即泄漏"},
            "K13b": {"total": sum(1 for n in nodes if FUNC_PRED.search(n.get("predicate") or "") and
                                  len(re.sub(r"[^\d.]", "", str(n.get("value") or "")).replace(".", "")) >= 3),
                     "missing": b_lost[:40], "verdict": "FAIL" if b_lost else "pass",
                     "note": "函数类常数必须继承——丢失则资产不可用（比泄漏更严重：下游无法重算）"}}
