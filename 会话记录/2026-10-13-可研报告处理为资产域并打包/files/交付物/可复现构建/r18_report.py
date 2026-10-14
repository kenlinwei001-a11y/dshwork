# -*- coding: utf-8 -*-
"""把语料包装配成可读报告（确定性装配器）。

分层：
  · 散文（论证、方案说明、评价）= LLM 层，写在 report_prose.py，**不出现任何字面数字**
  · 数字 / 表格 / 推导 / 冲突 / 缺口 / 依据 = 工具层，由本脚本从语料包注入

散文里的槽位语法：
  {N-xxxxxxxxxxxx}          注入该节点的「值 单位」
  {T:章|小节}               注入该(章,小节)的事实表
  {TB:表名}                 注入具名表
  {C:主体·属性}             注入「⚠ 待审」冲突框
  {G:G-xxx}                 注入缺口留白句
  {B:B-xx}                  注入依据判定（条款 + 判定 + 分支）
  {R:规则ID}                注入推导与复核结论
  {X:任意键}                注入 report_prose.py 的 EXTRA 常量
未解析槽位一律渲染为【待补】，不静默丢弃。
"""
import json
import re
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
OUTDIR = WS / "交付物" / "报告"
OUTDIR.mkdir(parents=True, exist_ok=True)


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


nodes = J(ROOT / "graph" / "nodes.yaml")
rules = J(ROOT / "graph" / "rules.yaml")
claims = J(ROOT / "graph" / "claims.yaml")
outline = J(ROOT / "outline.yaml")
conflicts = J(ROOT / "quality" / "conflicts.yaml")
gaps = J(ROOT / "quality" / "gaps.yaml")
derivation = J(ROOT / "reasoning" / "derivation.yaml")
judgements = J(ROOT / "reasoning" / "judgements.yaml")
EXT_MANDATES = {m["id"]: m for m in J(ROOT / "external" / "mandates.yaml")["mandates"]}
COMPLIANCE = {r["binding"]: r for r in J(ROOT / "external" / "compliance.yaml")["results"]}
chunks = [json.loads(l) for l in (ROOT / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
chunk_by_id = {c["id"]: c for c in chunks}
RULE_BY_ID = {r["id"]: r for r in rules}
DERIV_BY_RULE = {d["rule"]: d for d in derivation["derivation_diff"]}
DERIV_OK = {d["rule"]: d for d in derivation["closure_ok"]}
DERIV_NOSTATED = {d["rule"]: d for d in derivation.get("derivation_nostated", [])}
BLOCKED = {u["rule"]: u for u in derivation["unresolved_rules"] if u.get("reason") == "blocked_by_conflict"}
MISSING_R = {u["rule"]: u for u in derivation["unresolved_rules"] if u.get("reason") == "missing_deps"}

# 节点索引：同 (subject,predicate) 多值 → 保留全部（供冲突呈现）
BY_ID = {}
for n in nodes:
    BY_ID.setdefault(n["id"], n)
BY_KEY = {}
for n in nodes:
    BY_KEY.setdefault((n["subject"], n["predicate"]), []).append(n)


def val(nid, with_unit=True):
    """★ 取不到值时必须**显式留白**，不得静默输出空串。

    理由：`""` 与「本来就没有这项」在成稿里看起来一样，读者无法区分「漏引」与「原文没给」。
    显式标记让缺失可被看见、可被核对（与「缺值显式留白，不估算」同一原则）。
    """
    n = BY_ID.get(nid)
    if not n:
        return "【待补：图谱中无此节点】"
    v = str(n.get("value") or "").strip()
    if not v:
        return "【原文未给出，待补充】"          # ← 节点在、值空 ⇒ 显式留白
    return f"{v} {n['unit']}".strip() if with_unit and n.get("unit") else v


def chapter_of(cid):
    sp = (chunk_by_id.get(cid, {}).get("section_path") or [])
    return sp[0] if sp else "（未归属）"


def sec_of(cid):
    sp = (chunk_by_id.get(cid, {}).get("section_path") or [])
    return sp[1] if len(sp) > 1 else ""


for n in nodes:
    n["_ch"] = chapter_of(n.get("source", ""))
    n["_sec"] = sec_of(n.get("source", ""))


def autotable(ch, sec=None, cols=("主题", "属性", "值", "单位")):
    rows = [n for n in nodes if n["_ch"] == ch and (sec is None or n["_sec"] == sec)]
    seen, out = set(), []
    for n in sorted(rows, key=lambda x: (x["subject"], x["predicate"])):
        k = (n["subject"], n["predicate"], str(n["value"]))
        if k in seen:
            continue
        seen.add(k)
        out.append([n["subject"], n["predicate"], str(n["value"]).replace("|", "\\|")[:120], n["unit"]])
    if not out:
        return "【本草无可用事实节点】"
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols)
    body = "\n".join("| " + " | ".join(r) + " |" for r in out)
    return head + "\n" + body


def md_table(cols, rows, caption=None):
    s = ""
    if caption:
        s += f"\n**{caption}**\n\n"
    s += "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    s += "\n".join("| " + " | ".join(str(x) for x in r) + " |" for r in rows)
    return s


def take(subject_like, pred=None, ch=None):
    out = []
    for n in nodes:
        if ch and n["_ch"] != ch:
            continue
        if subject_like in n["subject"] and (pred is None or n["predicate"] == pred):
            k = (n["subject"], n["predicate"])
            if all(x["id"] != n["id"] for x in out):
                out.append(n)
    return out


TABLES = {}


def T(name):
    def deco(fn):
        TABLES[name] = fn
        return fn
    return deco


@T("技术经济指标")
def _t1():
    rows = []
    for pred in ("总建筑面积", "地上建筑面积", "地下建筑面积", "容积率", "绿地率"):
        for n in nodes:
            if n["subject"] == "本项目" and n["predicate"] == pred:
                rows.append([pred, n["value"], n["unit"]])
                break
    return md_table(["指标名称", "数量", "单位"], rows)


@T("规划人数")
def _t2():
    rows = []
    for c in ("管理科学与量化信息研究中心", "理论计算机研究中心", "应用统计研究中心", "数据科研与统计研究院"):
        r = [c]
        for pred in ("规划科研人员", "规划研究生博士生访问学者", "规划人数合计"):
            hit = [n for n in nodes if n["subject"] == c and n["predicate"] == pred]
            r.append(hit[0]["value"] if hit else "—")
        rows.append(r)
    for pred in ("科研人员规划人数", "研究生博士生访问学者规划人数", "总规划人数"):
        hit = [n for n in nodes if n["subject"] == "本项目" and n["predicate"] == pred]
        if hit:
            rows.append(["合计（表5-6 口径）" if pred == "总规划人数" else "合计",
                         hit[0]["value"] if pred != "科研人员规划人数" else hit[0]["value"], ""])
    return md_table(["科研机构", "科研人员（人）", "研究生/博士生/访问学者（人）", "合计（人）"], rows)


@T("配套用房")
def _t3():
    rows = []
    for n in nodes:
        if n["subject"].startswith("公共服务配套用房·"):
            name = n["subject"].split("·")[1]
            r = next((x for x in rows if x[0] == name), None)
            if not r:
                r = [name, "", "", "", ""]
                rows.append(r)
            idx = {"间数": 1, "单间用房标准": 2, "面积需求": 3}.get(n["predicate"])
            if idx:
                r[idx] = n["value"]
    for n in nodes:
        if n["subject"] == "公共服务配套用房" and n["predicate"] in ("使用面积需求合计", "综合平面利用系数", "建筑面积需求"):
            rows.append([n["predicate"], "", "", n["value"] + " " + n["unit"], ""])
    return md_table(["用房功能", "数量（间）", "用房标准（㎡/间）", "面积需求（㎡）", "备注"], rows)


@T("规模需求汇总")
def _t4():
    rows = []
    for n in nodes:
        if n["subject"] == "本项目" and n["predicate"] == "科研人员用房需求建筑面积":
            rows.append(["科研人员用房", "315", "16", n["value"]])
        if n["subject"] == "本项目" and n["predicate"] == "研究生用房需求建筑面积":
            rows.append(["研究生、博士生、访问学者用房", "1350", "8", n["value"]])
        if n["subject"] == "公共服务配套用房" and n["predicate"] == "建筑面积需求":
            rows.append(["公共服务配套用房", "/", "/", n["value"]])
        if n["subject"] == "本项目" and n["predicate"] == "地上总建筑面积需求":
            rows.append(["合计", "1665", "", n["value"]])
    return md_table(["序号", "用房功能", "规划人数（人）", "人均建筑面积指标（㎡/人）", "需求建筑面积（㎡）"],
                    [["" if i == 0 else i] + r for i, r in enumerate(rows)])


@T("投资估算")
def _t5():
    rows = []
    for pred_subj in ["建筑安装工程费用", "单体工程", "土建工程", "桩基工程", "基坑围护工程", "地下建筑结构工程",
                      "地上建筑结构工程", "装配式结构增加费", "室内装饰工程", "外立面及屋面装饰工程",
                      "安装工程", "给排水工程", "消防工程", "通风、空调工程", "强电工程", "弱电工程", "电梯工程",
                      "室外总体工程", "道路、广场、硬地、铺装", "绿化、景观", "室外安装工程", "标识工程",
                      "抗震支架", "绿色二星增量费用", "工程建设其他费", "基本预备费", "拆除费", "总计"]:
        hit = [n for n in nodes if n["subject"] == pred_subj and n["predicate"] == "估算金额"]
        if hit:
            rows.append([pred_subj, hit[0]["value"]])
    for pred in ("单位造价（总投资口径）", "单位造价（建安口径）"):
        h = [n for n in nodes if n["subject"] == "本项目" and n["predicate"] == pred]
        if h:
            rows.append([pred, h[0]["value"] + " " + h[0]["unit"]])
    return md_table(["工程和费用名称", "估算金额（万元）／单位造价"], rows)


@T("其他费明细")
def _t6():
    rows = []
    for n in nodes:
        if n["predicate"] == "估算金额" and n["_ch"] == "投资估算及资金筹措" and n["subject"] not in (
                "建筑安装工程费用", "单体工程", "土建工程", "桩基工程", "基坑围护工程", "地下建筑结构工程",
                "地上建筑结构工程", "装配式结构增加费", "室内装饰工程", "外立面及屋面装饰工程", "安装工程",
                "给排水工程", "消防工程", "通风、空调工程", "强电工程", "弱电工程", "电梯工程", "室外总体工程",
                "道路、广场、硬地、铺装", "绿化、景观", "室外安装工程", "标识工程", "抗震支架",
                "绿色二星增量费用", "工程建设其他费", "基本预备费", "拆除费", "总计"):
            rows.append([n["subject"], n["value"]])
    return md_table(["工程建设其他费 明细科目", "估算金额（万元）"], rows)


@T("资金年度需求")
def _t7():
    rows = []
    for n in nodes:
        if n["subject"] in ("本项目",) and n["predicate"] in ("国拨资金", "学校自筹资金", "总投资", "国拨资金占比"):
            rows.append([n["predicate"], n["value"] + " " + n["unit"] if n["unit"] else n["value"]])
    for n in nodes:
        if n["subject"] in ("上海财经大学",) and n["predicate"] in ("资产总额", "负债总额", "净资产总额", "资产负债率",
                                                                  "总收入", "总支出"):
            rows.append([n["subject"] + "·" + n["predicate"], n["value"] + " " + n["unit"]])
    return md_table(["项目", "数值"], rows)


@T("荷载取值")
def _t8():
    rows = []
    for n in nodes:
        if n["predicate"] == "取值区间":
            rows.append([n["subject"], n["predicate"], f"{n['value']} {n['unit']}".strip()])
        if n["predicate"] in ("楼面活荷载标准值", "屋面活荷载标准值",
                              "基本雪压", "基本风压", "多遇水平地震影响系数"):
            rows.append([n["subject"], n["predicate"], n["value"] + " " + n["unit"]])
    return md_table(["房间/部位", "类别", "标准值"], rows)


@T("室外气象参数")
def _t9():
    rows = [[n["subject"], n["value"] + " " + n["unit"]]
            for n in nodes if n["_ch"] == "项目规划设计方案" and (
                "室外" in n["subject"] or "项目所在地" in n["subject"]) and n["unit"]]
    return md_table(["参数", "取值"], rows)


@T("室内空气参数")
def _t10():
    rows = []
    for n in nodes:
        if n["subject"] in ("科研用房", "交流讨论用房", "交流讨论大厅", "门厅", "休息厅、休息大厅") and \
                n["predicate"] in ("夏季室内温度", "夏季相对湿度上限", "冬季室内温度", "人均使用面积", "新风量",
                                   "噪声标准", "排风换气次数"):
            rows.append([n["subject"], n["predicate"], n["value"] + " " + n["unit"]])
    return md_table(["房间", "参数", "取值"], rows)


@T("空调负荷")
def _t11():
    rows = []
    for pred in ("单位面积冷负荷指标", "冷负荷", "单位面积热负荷指标", "热负荷"):
        hit = [n for n in nodes if n["subject"] == "本项目" and n["predicate"] == pred]
        if hit:
            rows.append([pred, hit[0]["value"] + " " + hit[0]["unit"]])
    return md_table(["指标", "取值"], rows)


@T("主要设备")
def _t12():
    rows = []
    for n in nodes:
        if n["predicate"] in ("台数", "单台制冷量") and ("机组" in n["subject"] or "风机" in n["subject"]):
            rows.append([n["subject"], n["predicate"], n["value"] + " " + n["unit"]])
        if n["subject"] in ("加压送风机", "排烟机组", "多联机室内机组") and n["predicate"] == "台数":
            rows.append([n["subject"], "台数", n["value"] + " " + n["unit"]])
    return md_table(["设备", "参数", "取值"], rows)


@T("用水量")
def _t13():
    rows = []
    for n in nodes:
        if n["subject"] in ("科研学生", "办公", "教师用水", "学生用水") and n["predicate"] in (
                "用水定额", "用水人数", "日用水量", "用水面积"):
            rows.append([n["subject"], n["predicate"], n["value"] + " " + n["unit"]])
    for pred in ("最高日用水量", "最大小时用水量", "最高日排水量", "最大时排水量", "未预见系数"):
        hit = [n for n in nodes if n["subject"] == "本项目" and n["predicate"] == pred]
        if hit:
            rows.append(["本项目", pred, hit[0]["value"] + " " + hit[0]["unit"]])
    return md_table(["用水部门/项目", "参数", "取值"], rows)


@T("消防用水量")
def _t14():
    rows = []
    for subj in ("室外消火栓系统", "室内消火栓系统", "自动喷水灭火系统"):
        r = [subj]
        for pred in ("用水量", "一次灭火用水量", "喷水强度", "作用面积", "设计最小用水量"):
            hit = [n for n in nodes if n["subject"] == subj and n["predicate"] == pred]
            r.append((hit[0]["value"] + " " + hit[0]["unit"]) if hit else "—")
        rows.append(r)
    for pred in ("消防用水量总计", "消防一次灭火用水量总计"):
        hit = [n for n in nodes if n["subject"] == "本项目" and n["predicate"] == pred]
        if hit:
            rows.append([pred, hit[0]["value"] + " " + hit[0]["unit"], "—", "—", "—"])
    return md_table(["系统", "用水量", "一次灭火用水量", "喷水强度", "作用面积/其它"], rows)


@T("年用电量")
def _t15():
    rows = []
    for subj in ("科研用房", "公共配套服务用房"):
        r = [subj]
        for pred in ("用电面积", "用电指标", "需要系数", "同时使用系数"):
            hit = [n for n in nodes if n["subject"] == subj and n["predicate"] == pred]
            r.append((hit[0]["value"] + " " + hit[0]["unit"]) if hit else "—")
        rows.append(r)
    for pred in ("年工作天数", "日均工作小时数", "年总耗电量"):
        hit = [n for n in nodes if n["subject"] == "本项目" and n["predicate"] == pred]
        if hit:
            rows.append([pred, hit[0]["value"] + " " + hit[0]["unit"]])
    return md_table(["分项", "用电面积", "用电指标", "需要系数", "同时使用系数"], rows)


@T("综合能耗")
def _t16():
    rows = []
    for pred in ("年总用水量", "年总耗电量", "综合能耗（当量值）", "综合能耗（等价值）",
                 "单位面积综合能耗（当量值）", "单位面积综合能耗（等价值）", "单位建筑面积电耗"):
        hit = [n for n in nodes if n["subject"] == "本项目" and n["predicate"] == pred]
        if hit:
            rows.append([pred, hit[0]["value"] + " " + hit[0]["unit"]])
    for n in nodes:
        if n["subject"].startswith("综合能耗·") and "折标系数" in n["predicate"]:
            rows.append([n["subject"] + "·" + n["predicate"], n["value"] + " " + n["unit"]])
    return md_table(["能耗项", "取值"], rows)


@T("进度计划")
def _t17():
    rows = []
    for pred in ("方案设计与可研编制", "初步设计及概算", "施工图设计", "施工招标", "开工建设", "竣工验收"):
        hit = [n for n in nodes if n["subject"] == "本项目" and n["predicate"] == pred]
        if hit:
            rows.append([pred, hit[0]["value"]])
    return md_table(["工作内容", "进度"], rows)


@T("招标情况")
def _t18():
    rows = []
    for subj in ("勘察", "设计", "监理", "建安工程"):
        hit = [n for n in nodes if n["subject"] == subj and n["predicate"] == "招标估算金额"]
        if hit:
            method = "不采用招标方式" if subj == "勘察" else "全部招标 / 委托招标 / 公开招标"
            rows.append([subj, method, hit[0]["value"]])
    return md_table(["项目", "招标范围与方式", "招标估算金额（万元）"], rows)


@T("学科情况")
def _t19():
    rows = []
    for n in nodes:
        if n["subject"] == "上海财经大学" and n["predicate"] in (
                "国家“双一流”建设学科", "国家重点学科", "一级学科", "学科门类", "一级学科博士学位授权点",
                "一级学科硕士学位授权点", "硕士专业学位授权点", "博士后科研流动站"):
            rows.append([n["predicate"], n["value"] + " " + n["unit"]])
    return md_table(["项目", "数量/内容"], rows)


@T("办学规模")
def _t20():
    rows = []
    for n in nodes:
        if n["predicate"] == "2018年合同经费":
            rows.append([n["subject"] + "·2018 年合同经费", str(n["value"]) + " " + n["unit"]])
        elif n["subject"] == "上海财经大学" and n["predicate"] in (
                "各类在校生", "全日制在校生", "本科生", "预科生", "研究生在校生", "硕士生", "博士生",
                "双证硕士", "在校留学生", "专职教师", "校园占地", "校区数量"):
            rows.append([n["predicate"], n["value"] + " " + n["unit"]])
    return md_table(["项目", "数值"], rows)


@T("结构材料")
def _t21():
    rows = []
    for n in nodes:
        if n["_ch"] == "项目规划设计方案" and n["predicate"] in (
                "基础垫层混凝土强度等级", "框架柱剪力墙混凝土强度等级", "梁板混凝土强度等级",
                "钢筋牌号", "钢材牌号", "上部结构形式", "基础形式", "基础埋深", "地下室顶板厚度",
                "结构计算软件", "预制率", "绿色建筑设计标准", "建筑结构安全等级", "地基基础安全等级",
                "地基基础设计等级", "抗震设防类别", "框架抗震等级", "剪力墙抗震等级"):
            rows.append([n["predicate"], n["value"] + (" " + n["unit"] if n["unit"] else "")])
    return md_table(["项目", "取值"], rows)


@T("建筑设计要点")
def _t22():
    rows = []
    for n in nodes:
        if n["_ch"] == "项目规划设计方案" and n["_sec"] in ("建筑设计", "设计总说明") and n["predicate"] in (
                "层数", "建筑高度控制", "一层层高", "标准层层高", "建筑类别", "设计使用年限", "耐火等级",
                "抗震设防烈度", "地下层数", "基础垫层混凝土强度等级"):
            rows.append([n["predicate"], n["value"] + (" " + n["unit"] if n["unit"] else "")])
    return md_table(["项目", "取值"], rows)


@T("节能措施依据")
def _t23():
    rows = []
    for n in nodes:
        if n["_ch"] == "节能设计" and n["predicate"] in ("用水定额", "年工作天数", "用电指标", "需要系数", "同时使用系数"):
            rows.append([n["subject"], n["predicate"], n["value"] + " " + n["unit"]])
    return md_table(["对象", "参数", "取值"], rows)


@T("环境标准")
def _t24():
    rows = []
    for n in nodes:
        if n["predicate"] in ("与环境敏感目标间距", "底部离地面高度"):
            rows.append([n["subject"], n["predicate"], n["value"] + " " + n["unit"]])
    return md_table(["对象", "参数", "取值"], rows)


@T("风险清单")
def _t25():
    rows = []
    for c in claims:
        if chapter_of(c.get("source", "")) == "社会稳定风险分析" and c.get("type") == "risk":
            t = c.get("toulmin") or {}
            rows.append([c["id"], t.get("claim", c["text"][:40]), t.get("qualifier", "—")])
    return md_table(["编号", "风险因素", "程度"], rows)



@T("待审冲突汇总")
def _t26():
    rows = []
    for i, c in enumerate(conflicts, 1):
        rows.append([i, c["type"], f"{c['subject']} · {c['predicate']}", " / ".join(c["values"]),
                     (c.get("note") or "")[:60]])
    return md_table(["#", "类型", "主体 · 属性", "并列取值", "说明"], rows)


@T("缺口汇总")
def _t27():
    rows = []
    for i, g in enumerate(gaps, 1):
        rows.append([g["id"], g["type"], g.get("subject") or g.get("label") or g.get("rule") or "",
                     (g.get("note") or "")[:70]])
    return md_table(["编号", "类型", "对象", "说明"], rows)


@T("依据复核汇总")
def _t28():
    rows = []
    for r in COMPLIANCE.values():
        rows.append([r["binding"], r["verdict"], r["report"]["rule"],
                     "；".join(r["basis_titles"])[:70], r["role"]])
    return md_table(["绑定", "判定", "报告取值", "依据条款", "角色"], rows)


# 原稿表号映射（沿用原报告编号，保证「表题闭环」可判）
CAPTION = {
    "技术经济指标": "表1-2 项目主要技术指标表",
    "学科情况": "表2-1 学科基本情况表",
    "办学规模": "表2-2 办学规模与教职工情况（本稿新增，原稿为正文叙述）",
    "规划人数": "表5-1、表5-2、表5-3、表5-4 各研究中心规划人数（本稿合并呈现；表5-1 管理科学与量化信息研究中心、表5-2 理论计算机研究中心、表5-3 应用统计研究中心、表5-4 数据科研与统计研究院）",
    "配套用房": "表5-5 公共服务配套用房规模需求",
    "规模需求汇总": "表5-6 项目规模需求汇总表",
    "建筑设计要点": "表6-1 主要技术指标表",
    "结构材料": "表6-2 结构设计主要取值",
    "荷载取值": "表6-3 主要荷载取值",
    "设备材料": "表6-4 主要设备材料表",
    "负荷等级": "表6-5 负荷等级表",
    "室外气象参数": "表6-6 室外空气计算参数",
    "室内空气参数": "表6-7 室内空气计算参数",
    "用水量": "表6-2a 主要用水项目及其用水指标表（原表6-2）",
    "消防用水量": "表6-3a 消防用水量表（原表6-3）",
    "空调负荷": "表6-9 空调系统",
    "主要设备": "表6-11 主要设备表",
    "年用水量": "表7-1 年用水量汇总表",
    "年用电量": "表7-2 年用电量汇总表",
    "综合能耗": "表7-3 项目综合能耗及能耗指标",
    "进度计划": "表11-1 项目进度计划表",
    "招标情况": "表12-1 项目招标基本情况",
    "投资估算": "表13-1 项目投资估算表",
    "其他费明细": "表13-1 附表 工程建设其他费明细",
    "资金年度需求": "表13-5 项目建设资金年度需求表",
    "风险清单": "表10-1 项目社会稳定风险因素清单（本稿新增）",
    "待审冲突汇总": "附表A-1 待审事项汇总",
    "缺口汇总": "附表A-2 缺口事项汇总",
    "依据复核汇总": "附表B-1 外部依据与合规复核汇总",
}


@T("设备材料")
def _t29():
    rows = []
    for n in nodes:
        if (n.get("auto_extracted") or n["predicate"] == "铭牌参数"
                or n["predicate"] == "消防水泵接合器"):
            rows.append([n["subject"], "铭牌/技术参数", str(n["value"])[:70]])
    if not rows:
        return "【本稿未取到设备参数节点】"
    return md_table(["设备名称", "参数类别", "规格参数"], rows)


@T("负荷等级")
def _t30():
    rows = []
    for n in nodes:
        if "负荷" in n["predicate"] or "负荷等级" in n["subject"]:
            rows.append([n["subject"], n["predicate"], str(n["value"]) + " " + n["unit"]])
    return md_table(["用电负荷", "属性", "取值"], rows[:20])


@T("年用水量")
def _t31():
    return autotable("节能设计", "能耗状况和能耗指标分析")



def render(text):
    """槽位替换。"""
    text = re.sub(r"\{T:([^}]+)\}", lambda m: render_table(m.group(1).strip()), text)
    text = re.sub(r"\{TB:([^}]+)\}", lambda m: TABLES.get(m.group(1).strip(), lambda: "【表缺失】")(), text)
    text = re.sub(r"\{N-([0-9a-f]+)\}", lambda m: val("N-" + m.group(1)), text)
    text = re.sub(r"\{V:([^}|]+)\|([^}]+)\}", lambda m: vslot(m.group(1).strip(), m.group(2).strip()), text)
    text = re.sub(r"\{VN:([^}|]+)\|([^}]+)\}", lambda m: vslot(m.group(1).strip(), m.group(2).strip(), False), text)
    text = re.sub(r"\{C:([^}]+)\}", lambda m: conflict_box(m.group(1).strip()), text)
    text = re.sub(r"\{G:([^}]+)\}", lambda m: gap_line(m.group(1).strip()), text)
    text = re.sub(r"\{B:([^}]+)\}", lambda m: basis_block(m.group(1).strip()), text)
    text = re.sub(r"\{R:([^}]+)\}", lambda m: rule_block(m.group(1).strip()), text)
    text = re.sub(r"\{A:([^}]*)\}", "", text)
    return text


def vslot(subj, pred, with_unit=True):
    """按 (主体, 属性) 注入值；同键多值时并列呈现，不取其一。"""
    hits = BY_KEY.get((subj, pred), [])
    if not hits:
        for k, v in BY_KEY.items():
            if subj in k[0] and pred in k[1]:
                hits = v
                break
    if not hits:
        return "【待补】"
    vals = list(dict.fromkeys(
        (f"{h['value']} {h['unit']}".strip() if with_unit and h.get("unit") else str(h["value"])) for h in hits))
    out = " / ".join(vals) if len(vals) > 1 else vals[0]
    out = re.sub(r"\s+([%℃°])", r"\1", out)
    return out


def render_table(key):
    ch, _, sec = key.partition("|")
    return "\n\n" + autotable(ch.strip(), sec.strip() or None) + "\n"


def captioned(name, body):
    c = CAPTION.get(name)
    return ("\n\n**" + c + "**\n\n" + body) if c else "\n\n" + body


def conflict_box(key):
    subj, _, pred = key.partition("·")
    hits = [c for c in conflicts if c["subject"] == subj.strip() and c["predicate"] == pred.strip()]
    if not hits:
        return "【冲突未登记】"
    c = hits[0]
    return (f"\n\n> **⚠ 待审**：{c['subject']} · {c['predicate']} 在报告不同章节取值不一致，"
            f"现并列呈现为 **{' / '.join(c['values'])}**。"
            f"本稿不判断哪一个正确，也不取其一；须由建设单位与编制单位核实后统一口径。\n\n")


def gap_line(gid):
    g = next((x for x in gaps if x["id"] == gid), None)
    if not g:
        return "【缺口未登记】"
    return f"**（{g.get('subject') or g.get('label') or g.get('rule')}：待补充——{g['note']}）**"


def basis_block(bid):
    r = COMPLIANCE.get(bid)
    if not r:
        return "【依据未登记】"
    icon = {"合规": "✅", "不合规": "❌", "待审": "⚠️", "待核查": "🔍"}.get(r["verdict"], "")
    s = f"\n\n> **{icon} 依据复核（{r['binding']}）**：{r['finding']}\n"
    for br in r.get("branches", []):
        s += f"> - 若 {br['假设']} ⇒ {br['结论']}\n"
    if r.get("needs_to_verify"):
        s += "> - 须核对：" + "；".join(r["needs_to_verify"]) + "\n"
    s += "\n"
    return s


def rule_block(rid):
    r = RULE_BY_ID.get(rid)
    if not r:
        return "【规则未登记】"
    if rid in DERIV_BY_RULE:
        d = DERIV_BY_RULE[rid]
        return (f"按 {rid}（{r.get('label')}）重算得 **{d['computed']:g}**，"
                f"报告原文写 **{d['stated']:g}**，差 {d['delta']:g}（{d['delta_pct']}%）。"
                f"该差异按「待审」处理，本稿不改数。")
    if rid in DERIV_OK:
        d = DERIV_OK[rid]
        return f"按 {rid}（{r.get('label')}）复算为 **{d['computed']:g}**，与报告声明一致（闭合）。"
    if rid in BLOCKED:
        u = BLOCKED[rid]
        dep = "；".join(f"{d['dep']}={'/'.join(d['values'])}" for d in u["detail"])
        return f"**{rid}（{r.get('label')}）因依赖存在未裁决冲突而无法计算**（{dep}），本稿不给单一值。"
    if rid in MISSING_R:
        return f"**{rid}（{r.get('label')}）因缺口径未解析**，本稿留白。"
    # 判定类（select）规则 → 引用已登记的判定结论
    JUMP = {"R-规模符合性": "J-规模符合性", "R-投资闭合校核": "J-投资构成闭合",
            "R-建安工程费口径核对": "J-建安费口径", "R-节能合规判定": None,
            "R-稳评等级判定": None, "R-供电容量匹配": None}
    jid = JUMP.get(rid)
    j = next((x for x in judgements if x["id"] == jid), None) if jid else None
    if j:
        return (f"**判定结论：{j['verdict']}**。前提 {json.dumps(j['premises'], ensure_ascii=False)}；"
                f"{j['note']}")
    if r.get("kind") == "select":
        return f"判定条件为：{r.get('expr')}；该判定所需的量化前提未全部满足，本稿按「待审」处理。"
    return f"{r.get('label')}：{r.get('expr')}"


def build():
    import report_prose as P
    parts = [render(P.HEAD)]
    total_chars = 0
    for ch_blocks in P.BODY:
        for kind, payload in ch_blocks:
            if kind == "h1":
                parts.append("# " + payload)
            elif kind == "h2":
                parts.append("## " + payload)
            elif kind == "h3":
                parts.append("### " + payload)
            elif kind == "p":
                parts.append(render(payload))
            elif kind == "raw":
                parts.append(payload)
            elif kind == "table":
                parts.append(captioned(payload, render(TABLES[payload]())))
    text = "\n\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


if __name__ == "__main__":
    txt = build()
    cn = len(re.findall(r"[\u4e00-\u9fff]", txt))
    (OUTDIR / "上海财经大学中山北一路校区大数据研究中心可行性研究报告（还原稿）.md").write_text(txt, encoding="utf-8")
    print(json.dumps({"chars_total": len(txt), "chars_chinese": cn,
                      "tables_defined": len(TABLES),
                      "placeholders_left": len(re.findall(r"\{(?:T|TB|C|G|B|R|V|VN):", txt)) + len(re.findall(r"\{N-[0-9a-f]+\}", txt))},
                     ensure_ascii=False, indent=2))
