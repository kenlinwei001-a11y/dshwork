# -*- coding: utf-8 -*-
"""evo_eval_ext —— 还原能力评估扩展（P0/P1/P2，确定性，零 LLM）。

补的是原 4 层 27 项评估没有覆盖的 6 个维度：

    P0-1 语义对位      原文每段 ↔ 还原每项，词集 Jaccard + 字符序列相似度
    P0-2 跨节一致性    同一概念在多节出现时值是否一致
    P1   标准时效      正文引用的标准号是否已废止/已被替代
    P2-1 术语一致性    同一概念是否混用多个叫法
    P2-2 证据链完整    有数值的句子是否绑定 〔P-xxx〕
    P2-3 可读性        段落长度分布、连续重复开头、过渡词覆盖

纪律：
    * 不 import / 不修改 evo_diffscore / evo_loop / evo_origin_check / evo_origin_slots
    * 不裁决冲突：跨节不一致只标「待审（不裁决）」
    * 查不到的标准标 UNKNOWN，不编造废止信息
    * 每个函数都可单独调用，返回 JSON 可序列化 dict

依赖：仅标准库；PyYAML 可选（用于读取 fact-aliases.yaml，缺失时用内置同义组）。
"""
from __future__ import annotations

import difflib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# 通用常量
# ---------------------------------------------------------------------------

CITATION_RE = re.compile(r"〔P-[0-9a-fA-F]+〕")

_NUM = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_UNIT = (r"(?:万元|万m³|万立方米|万千瓦时|万千瓦·时|平方米|㎡|m³|立方米|"
         r"%|人|个月|月|年|天|d|h|吨标煤|元)")

ORG_NAMES = (
    "华东理工大学人工智能与智能制造研究院",
    "上海财经大学中山北一路校区大数据研究中心",
    "上海同济工程咨询有限公司",
    "华东理工大学",
    "上海财经大学",
    "中山北一路校区",
    "徐汇校区",
)

# 领域词表：用于无 jieba 时的最长匹配分词。宁可少收，不收泛词。
DOMAIN_TERMS = tuple(sorted({
    "项目概况", "项目名称", "项目编号", "建设单位", "编制单位", "编制时间",
    "建设地点", "建设条件", "建设内容", "建设规模", "投资估算", "资金筹措",
    "实施进度", "总投资", "总投资额", "投资构成", "资金构成", "建设工期",
    "开工时间", "竣工时间", "建安工程费用", "建筑安装工程费用", "建安工程费",
    "建安费", "工程建设其他费用", "工程建设其他费", "预备费", "基本预备费",
    "原建筑拆除费用", "拆除费用", "国拨资金", "学校自筹资金", "自筹资金",
    "总建筑面积", "新建总建筑面积", "地上建筑面积", "地下建筑面积", "建筑面积",
    "科研用房", "公共配套服务用房", "公共服务配套用房", "科研工作", "研究中心",
    "人工智能", "智能制造", "机器人", "自动化", "智能感知", "研究院",
    "可行性研究报告", "编制依据", "政府投资项目", "编写通用大纲", "发改投资规",
    "用水量", "用电量", "年用水量", "年总用水量", "年用电量", "年总耗电量",
    "用水定额", "用电指标", "需要系数", "同时使用系数", "日均工作小时数",
    "年工作天数", "日用水量", "教师用水", "学生用水", "不可预计水量",
    "不可预计用水量", "年用水量汇总表", "年用电量汇总表", "用水天数",
    "用电面积", "科研用房用电面积", "公共配套服务用房用电面积",
    "单位建筑面积电耗", "单位面积电耗", "综合能耗", "当量值", "折标系数",
    "电力折标系数", "水折标系数", "节能设计", "能耗指标", "能耗指标分析",
    "能耗指标计算", "投资估算表", "工程和费用名称", "技术经济指标",
    "单位造价", "合价", "数量", "单价", "备注", "建筑工程", "安装工程",
    "土建工程", "桩基工程", "基坑围护工程", "地下建筑结构工程",
    "地上建筑结构工程", "装配式结构增加费", "室内装饰工程",
    "外立面及屋面装饰工程", "给排水工程", "消防工程", "通风空调工程",
    "强电工程", "弱电工程", "电梯工程", "室外总体工程",
    "道路广场硬地铺装", "绿化景观", "室外安装工程", "标识工程", "抗震支架",
    "绿色二星增量费用", "建设单位管理费", "前期工程咨询费", "勘察费", "设计费",
    "招标代理费", "清单及标底编制费", "施工监理费", "施工图审图费",
    "竣工图编制费", "场地准备及临时设施费", "低压电缆", "人防易地建设费",
    "单体工程", "项目投资", "建筑高度", "耐火等级", "抗震设计", "绿色建筑",
    "无障碍设计", "设计依据", "规范", "标准", "条款", "客户报表", "规则重算",
    "分项加总", "核对通过", "待客户提供", "待审", "不裁决", "室外总体",
}))
_DOMAIN_BY_LEN = tuple(sorted(DOMAIN_TERMS, key=len, reverse=True))

STOP_TERMS = {
    "本项目", "项目", "其中", "以及", "如下", "所示", "根据", "按照", "因此",
    "本工程", "主要", "相关", "进行", "建设", "内容", "情况", "工作", "单位",
    "名称", "时间", "地点", "条件", "要求", "通过", "合计", "总计", "约",
    "为", "是", "的", "了", "和", "与", "及", "等", "其", "该", "本", "按",
    "对", "将", "由", "从", "到", "有", "在", "中", "上", "下", "内", "外",
    "个", "项", "这", "那", "何", "以", "并", "且", "或", "但", "因", "所",
    "于", "之", "人民币", "万元", "平方米",
}
STOP_CHARS = set("的了着和与及等其该本按对将由从到是有在为于之或并且但因所以这那个项")

_GENERIC_CONCEPTS = {
    "其中", "本项目", "项目", "该", "本", "经测算", "测算", "合计", "总计",
    "共计", "约为", "约", "数值", "金额", "客户值", "表列", "分项加总",
    "相差", "规则重算", "差额", "差值", "原稿", "已更正",
}


# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------

def _chars(s: str) -> int:
    return len(re.sub(r"\s", "", s or ""))


def _head(s: str, n: int = 42) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s[:n] + ("…" if len(s) > n else "")


def _clean_markup(s: str) -> str:
    s = (s or "").replace("**", "").replace("__", "")
    s = re.sub(r"^\s*[-*+]\s*", "", s)
    s = re.sub(r"^\s*\d+(?:\.\d+)*\s*[、.)）]?\s*", "", s)
    s = re.sub(r"^\s*[>#]+\s*", "", s)
    return s.strip()


def _value_mask(s: str) -> str:
    """去值：数字/单位/项目名/标准号 → 占位符，保留句式。"""
    s = CITATION_RE.sub("", s or "")
    s = _clean_markup(s)
    # 标准号整体占位（先于数字）
    s = re.sub(r"(?:GB\s*/\s*T|GB|JGJ|DGJ|CJJ|建标)\s*[-]?\s*\d+(?:[.\-–—]\d+)*", "#STD#", s)
    s = re.sub(r"人民币", "#CUR#", s)
    # 项目名/机构名
    for name in sorted(ORG_NAMES, key=len, reverse=True):
        s = s.replace(name, "#ORG#")
    # 数字 + 单位
    s = re.sub(_NUM, "#NUM#", s)
    s = re.sub(_UNIT, "#UNIT#", s)
    # 只保留中文/字母/数字/占位符
    s = re.sub(r"[^一-鿿#A-Za-z0-9]", "", s)
    return s


def _topic_terms(s: str) -> set:
    """中文主题词：领域词最长匹配 + 未匹配段 2 字 n-gram + 停用词过滤。"""
    masked = _value_mask(s)
    masked = re.sub(r"#(?:NUM|UNIT|ORG|STD|CUR)#", "", masked)
    terms: set = set()
    for run in re.findall(r"[一-鿿]{2,}", masked):
        i = 0
        while i < len(run):
            hit = None
            for term in _DOMAIN_BY_LEN:
                if run.startswith(term, i):
                    hit = term
                    break
            if hit:
                if hit not in STOP_TERMS:
                    terms.add(hit)
                i += len(hit)
                continue
            if i + 2 <= len(run):
                bg = run[i:i + 2]
                if bg not in STOP_TERMS and bg[0] not in STOP_CHARS and bg[1] not in STOP_CHARS:
                    terms.add(bg)
            i += 1
    return {t for t in terms if len(t) >= 2 and t not in STOP_TERMS}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _pair_score(src: str, mine: str) -> float:
    """词集 Jaccard + 包含度 + 字符序列相似度。

    还原稿常把原文两个短段合并成一段（或反之），纯 Jaccard 会因长度差
    误判。包含度 = 交集 / 较短一侧词集，用来承认「短段被长段覆盖」。
    """
    ta, tb = _topic_terms(src), _topic_terms(mine)
    inter = len(ta & tb)
    ja = _jaccard(ta, tb)
    contain = (inter / min(len(ta), len(tb))) if ta and tb else 0.0
    term_sim = max(ja, 0.70 * contain)
    sa, sb = _value_mask(src), _value_mask(mine)
    try:
        seq = difflib.SequenceMatcher(None, sa, sb).ratio() if sa and sb else 0.0
    except Exception:
        seq = 0.0
    return round(0.60 * term_sim + 0.40 * seq, 6)


def split_paragraphs(text: str, include_tables: bool = False) -> list:
    """按行切段：跳过标题/代码块/表格（默认），保留正文段落与表题。"""
    out = []
    in_code = False
    for raw in (text or "").splitlines():
        s = raw.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not s:
            continue
        if s.startswith("#") or re.fullmatch(r"[-=_*]{3,}", s):
            continue
        if s.startswith("|") and not include_tables:
            continue
        s = _clean_markup(s)
        if s:
            out.append(s)
    return out


def _prose_lines(text: str) -> list:
    """只取正文行（跳过表格/标题/代码），用于跨节一致性与证据链。"""
    return split_paragraphs(text, include_tables=False)


def _split_sentences(para: str) -> list:
    parts = re.split(r"(?<=[。；;！？!?])", para)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# P0-1 段落级语义对位
# ---------------------------------------------------------------------------

MATCH_FLOOR = 0.12          # 低于此分不认为匹配成功
PASS_AVG = 0.35
PASS_MIN = 0.15


def _hungarian_max(w: list) -> list:
    """最大权匹配（经典匈牙利算法，矩形补零）。返回 [(row, col), ...]。"""
    if not w or not w[0]:
        return []
    n, m = len(w), len(w[0])
    size = max(n, m)
    # cost = -w，补零
    u = [0.0] * (size + 1)
    v = [0.0] * (size + 1)
    p = [0] * (size + 1)
    way = [0] * (size + 1)
    for i in range(1, size + 1):
        p[0] = i
        j0 = 0
        minv = [float("inf")] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = 0
            for j in range(1, size + 1):
                if used[j]:
                    continue
                wij = w[i0 - 1][j - 1] if (i0 - 1 < n and j - 1 < m) else 0.0
                cur = -wij - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(size + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    pairs = []
    for j in range(1, size + 1):
        i = p[j]
        if 1 <= i <= n and 1 <= j <= m:
            pairs.append((i - 1, j - 1))
    return pairs


def semantic_alignment(source_paras: list, mine_items: list) -> dict:
    """原文段落 ↔ 还原项 的语义对位。

    做法：去值 → 主题词 → 两两相似度 → 匈牙利一对一 → 顺序/覆盖率判定。
    """
    src = [str(x) for x in (source_paras or []) if str(x).strip()]
    mine = [str(x) for x in (mine_items or []) if str(x).strip()]
    n, m = len(src), len(mine)
    if n == 0 or m == 0:
        return {
            "pairs": [], "avg_score": 0.0, "min_score": 0.0,
            "unmatched_src": [{"idx": i, "head": _head(x)} for i, x in enumerate(src)],
            "unmatched_mine": [{"idx": j, "head": _head(x)} for j, x in enumerate(mine)],
            "order_ok": False, "pass": False,
            "source_count": n, "mine_count": m, "match_floor": MATCH_FLOOR,
            "note": "原文段落或还原项为空，无法对位",
        }
    w = [[_pair_score(s, t) for t in mine] for s in src]
    raw_pairs = _hungarian_max(w)
    pairs = []
    unmatched_src = set(range(n))
    unmatched_mine = set(range(m))
    for i, j in raw_pairs:
        sc = w[i][j]
        if sc < MATCH_FLOOR:
            continue
        pairs.append({
            "src_idx": i, "mine_idx": j, "score": round(sc, 4),
            "src_head": _head(src[i]), "mine_head": _head(mine[j]),
            "shared_terms": sorted(_topic_terms(src[i]) & _topic_terms(mine[j])),
        })
        unmatched_src.discard(i)
        unmatched_mine.discard(j)
    # 重复小标题（如两个「项目基地」）会让匈牙利算法给出交叉匹配；
    # 只在「原文完全相同且还原项也完全相同」的组内按顺序重排，消除假阳性。
    dup = defaultdict(list)
    for p in pairs:
        dup[_value_mask(src[p["src_idx"]])].append(p)
    for _, group in dup.items():
        if len(group) < 2:
            continue
        mine_keys = {_value_mask(mine[p["mine_idx"]]) for p in group}
        if len(mine_keys) != 1:
            continue
        indices = sorted(p["mine_idx"] for p in group)
        for p, mi in zip(sorted(group, key=lambda x: x["src_idx"]), indices):
            p["mine_idx"] = mi
    pairs.sort(key=lambda x: x["src_idx"])
    order_ok = all(
        pairs[k]["mine_idx"] < pairs[k + 1]["mine_idx"]
        for k in range(len(pairs) - 1)
    )
    avg = sum(p["score"] for p in pairs) / len(pairs) if pairs else 0.0
    min_score = min((p["score"] for p in pairs), default=0.0)
    ok = (avg >= PASS_AVG and min_score >= PASS_MIN and order_ok
          and not unmatched_src)
    return {
        "pairs": pairs,
        "avg_score": round(avg, 4),
        "min_score": round(min_score, 4),
        "unmatched_src": [
            {"idx": i, "head": _head(src[i])} for i in sorted(unmatched_src)
        ],
        "unmatched_mine": [
            {"idx": j, "head": _head(mine[j])} for j in sorted(unmatched_mine)
        ],
        "order_ok": order_ok,
        "pass": bool(ok),
        "source_count": n,
        "mine_count": m,
        "match_floor": MATCH_FLOOR,
        "criteria": {"avg_score": PASS_AVG, "min_score": PASS_MIN,
                     "order_ok": True, "unmatched_src": 0},
    }


# ---------------------------------------------------------------------------
# P0-2 跨节一致性
# ---------------------------------------------------------------------------

# 人工规范名（优先级高于 yaml）：variant -> canonical
_MANUAL_CONCEPTS = [
    ("项目总投资", "总投资"),
    ("总投资额", "总投资"),
    ("总投资", "总投资"),
    ("投资总额", "总投资"),
    ("建筑安装工程费用", "建筑安装工程费用"),
    ("建筑安装工程费", "建筑安装工程费用"),
    ("建安工程费用", "建筑安装工程费用"),
    ("建安工程费", "建筑安装工程费用"),
    ("建安费", "建筑安装工程费用"),
    ("工程建设其他费用", "工程建设其他费用"),
    ("工程建设其他费", "工程建设其他费用"),
    ("其他费用", "工程建设其他费用"),
    ("其他费", "工程建设其他费用"),
    ("二类费", "工程建设其他费用"),
    ("基本预备费", "预备费"),
    ("预备费", "预备费"),
    ("原建筑拆除费用", "原建筑拆除费用"),
    ("拆除费用", "原建筑拆除费用"),
    ("国拨资金", "国拨资金"),
    ("学校自筹资金", "学校自筹资金"),
    ("自筹资金", "学校自筹资金"),
    ("学校自筹", "学校自筹资金"),
    ("新建总建筑面积", "总建筑面积"),
    ("总建筑面积", "总建筑面积"),
    ("建筑面积", "总建筑面积"),
    ("地上建筑面积", "地上建筑面积"),
    ("地上面积", "地上建筑面积"),
    ("地下建筑面积", "地下建筑面积"),
    ("地下面积", "地下建筑面积"),
    ("年总用水量", "年总用水量"),
    ("年用水量", "年总用水量"),
    ("总用水量", "年总用水量"),
    ("年总耗电量", "年总耗电量"),
    ("年用电量", "年总耗电量"),
    ("年耗电量", "年总耗电量"),
    ("总耗电量", "年总耗电量"),
    ("单位建筑面积电耗", "单位建筑面积电耗"),
    ("单位面积电耗", "单位建筑面积电耗"),
    ("综合能耗（当量值）", "综合能耗"),
    ("综合能耗", "综合能耗"),
    ("总能耗", "综合能耗"),
    ("土建工程", "土建工程"),
    ("安装工程", "安装工程"),
    ("单体工程", "单体工程"),
    ("室外总体工程", "室外总体工程"),
    ("抗震支架", "抗震支架"),
    ("绿色二星增量费用", "绿色二星增量费用"),
    ("建设单位管理费", "建设单位管理费"),
    ("前期工程咨询费", "前期工程咨询费"),
    ("勘察费", "勘察费"),
    ("设计费", "设计费"),
    ("招标代理费", "招标代理费"),
    ("清单及标底编制费", "清单及标底编制费"),
    ("施工监理费", "施工监理费"),
    ("施工图审图费", "施工图审图费"),
    ("竣工图编制费", "竣工图编制费"),
    ("场地准备及临时设施费", "场地准备及临时设施费"),
    ("低压电缆", "低压电缆"),
    ("人防易地建设费", "人防易地建设费"),
]


def _canonical_map() -> tuple:
    """返回 (exact_map, substring_list)。substring_list 按 variant 长度降序。"""
    exact = {}
    pairs = list(_MANUAL_CONCEPTS)
    for variant, canon in pairs:
        exact[variant] = canon
    substr = sorted(set(pairs), key=lambda x: len(x[0]), reverse=True)
    return exact, substr


_EXACT_CONCEPT, _SUBSTR_CONCEPT = _canonical_map()
_GENERIC_SUBSTR = ("规则重算", "分项加总", "表列", "相差", "差额",
                   "原稿", "已更正", "万元与")


def _canon_concept(raw: str):
    s = re.sub(r"[\s*_`]", "", raw or "").strip("，。；：、（）()")
    if not s or s in _GENERIC_CONCEPTS:
        return None
    if s in _EXACT_CONCEPT:
        return _EXACT_CONCEPT[s]
    if any(g in s for g in _GENERIC_SUBSTR):
        return None
    # 「建筑面积」是总建筑面积的别名，但不能把科研用房/配套用房/地上/地下
    # 的面积都吸成「总建筑面积」——先按限定词细分。
    if "建筑面积" in s or "面积指标" in s:
        if "人均" in s:
            return "人均建筑面积指标"
        if "地上" in s:
            return "地上建筑面积"
        if "地下" in s:
            return "地下建筑面积"
        if "科研用房" in s or "研究用房" in s:
            return "科研用房建筑面积"
        if ("配套用房" in s or "配套服务用房" in s
                or "公共服务" in s or "公共配套" in s):
            return "公共服务配套用房建筑面积"
        if "总建筑面积" in s or "新建总建筑面积" in s:
            return "总建筑面积"
        if s in ("建筑面积", "项目建筑面积"):
            return "总建筑面积"
        if "需求" in s:
            return "建筑面积需求"
        return "建筑面积（未细分）"
    for variant, canon in _SUBSTR_CONCEPT:
        if variant in s:
            return canon
    return s if len(s) >= 2 else None


def _normalize_unit(value: float, unit: str):
    unit = (unit or "").strip()
    if unit == "万元":
        return value * 10000.0, "元"
    if unit == "元":
        return value, "元"
    if unit in ("万m³", "万立方米"):
        return value * 10000.0, "m³"
    if unit in ("m³", "立方米"):
        return value, "m³"
    if unit in ("万千瓦时", "万千瓦·时"):
        return value, "万千瓦时"
    if unit in ("㎡", "平方米"):
        return value, "㎡"
    return value, unit


def _extract_values(text: str) -> list:
    """从正文抽取「数值 + 紧邻名词」。跳过表格行。"""
    out = []
    for line in _prose_lines(text):
        # 先去掉证据角标：〔P-d3694a…〕里的 d 会被误当成单位「天」。
        line = CITATION_RE.sub("", line)
        for m in re.finditer(r"(?P<num>%s)\s*(?P<unit>%s)" % (_NUM, _UNIT), line):
            num_s, unit = m.group("num"), m.group("unit")
            pre = line[max(0, m.start() - 48):m.start()]
            pre = re.split(r"[，。；;：:、|（）()\[\]【】]", pre)[-1]
            # 只取紧邻数字的中文词组，避免跨过前一个「数值+单位」。
            # 「公共服务配套用房 建筑面积需求」被空格切成两段时，把限定词补回来。
            runs = re.findall(r"[一-鿿]{2,}", pre)
            if (len(runs) >= 2 and runs[-1].startswith(("建筑面积", "面积"))
                    and len(runs[-1]) <= 12):
                raw = runs[-2] + runs[-1]
            else:
                raw = runs[-1] if runs else ""
            raw = raw.strip(" *-—_")
            raw = re.sub(
                r"^(?:其中|本项目|项目|该|本|拟|经测算|测算|约为|约|共计|合计|计|为|是|达|达到|人民币)+",
                "", raw)
            raw = re.sub(
                r"(?:为|是|达|达到|约|共计|合计|计|人民币|客户值|数值|金额)+$",
                "", raw)
            raw = raw.strip(" *-—_")
            if len(raw) < 2 or raw in _GENERIC_CONCEPTS:
                continue
            # 百分数只接受明确的率/比例/系数/占比概念，避免把
            # 「不可预计用水量按总用水量的 10%」误当成「年总用水量」。
            if unit == "%" and not re.search(r"(率|比例|系数|百分比|占比)$", raw):
                continue
            canon = _canon_concept(raw)
            if not canon:
                continue
            try:
                val = float(num_s.replace(",", ""))
            except ValueError:
                continue
            base, unit_group = _normalize_unit(val, unit)
            out.append({
                "concept": canon, "raw_concept": raw,
                "value": val, "value_text": num_s, "unit": unit,
                "base_value": base, "unit_group": unit_group,
            })
    return out


def cross_section_consistency(restored_sections: dict) -> dict:
    """跨节一致性：同一概念在多节有值且不等 → inconsistent（待审，不裁决）。"""
    sections = {str(k): (v or "") for k, v in (restored_sections or {}).items()}
    occ = defaultdict(list)
    for sec, text in sections.items():
        for item in _extract_values(text):
            item = dict(item)
            item["section"] = sec
            occ[item["concept"]].append(item)

    consistent, inconsistent, single, intra = [], [], [], []
    for concept, items in occ.items():
        secs = sorted({x["section"] for x in items})
        keys = {(round(x["base_value"], 6), x["unit_group"]) for x in items}
        if len(secs) >= 2:
            if len(keys) == 1:
                first = items[0]
                consistent.append({
                    "concept": concept,
                    "value": first["value_text"],
                    "unit": first["unit"],
                    "sections": secs,
                    "occurrences": len(items),
                })
            else:
                values = []
                seen = set()
                for x in items:
                    k = (x["section"], x["value_text"], x["unit"])
                    if k in seen:
                        continue
                    seen.add(k)
                    values.append({
                        "section": x["section"], "value": x["value_text"],
                        "unit": x["unit"], "raw_concept": x["raw_concept"],
                    })
                base_vals = [x["base_value"] for x in items]
                units = {x["unit"] for x in items}
                if len(units) == 1:
                    unit0 = next(iter(units))
                    raw_vals = [x["value"] for x in items]
                    delta = max(raw_vals) - min(raw_vals)
                    delta_unit = unit0
                else:
                    delta = max(base_vals) - min(base_vals)
                    delta_unit = "base"
                inconsistent.append({
                    "concept": concept, "values": values, "sections": secs,
                    "delta": round(delta, 6),
                    "delta_unit": delta_unit,
                    "note": "待审（不裁决，不自动改数）",
                })
        else:
            if len(keys) > 1:
                vals = []
                seen = set()
                for x in items:
                    k = (x["value_text"], x["unit"])
                    if k in seen:
                        continue
                    seen.add(k)
                    vals.append({"value": x["value_text"], "unit": x["unit"],
                                 "raw_concept": x["raw_concept"]})
                intra.append({"concept": concept, "section": secs[0],
                              "values": vals,
                              "note": "同节多值（待审，不裁决）"})
            first = items[0]
            single.append({
                "concept": concept, "section": secs[0],
                "value": first["value_text"], "unit": first["unit"],
            })

    inconsistent.sort(key=lambda x: x["concept"])
    return {
        "consistent": sorted(consistent, key=lambda x: x["concept"]),
        "inconsistent": inconsistent,
        "single": sorted(single, key=lambda x: x["concept"]),
        "intra_section_conflicts": sorted(intra, key=lambda x: x["concept"]),
        "total_concepts": len(occ),
        "consistent_count": len(consistent),
        "inconsistent_count": len(inconsistent),
        "single_count": len(single),
        "pass": len(inconsistent) == 0,
        "note": "只比较出现在 ≥2 个不同节的概念；同节多值另列 intra_section_conflicts。",
    }


# ---------------------------------------------------------------------------
# P1 标准版本时效
# ---------------------------------------------------------------------------

_EXPIRED = "expired"
_SUPERSEDED = "superseded"
_CURRENT = "current"
_UNKNOWN = "UNKNOWN"

# 来源：用户给定的 9 条 + Semantica graph.json 26 条 decision 中可读的标准信息。
_STANDARD_DB = {
    "GB50034-2004": {
        "status": _SUPERSEDED, "replacement": "GB50034-2013",
        "note": "GB50034-2013 替代 GB50034-2004（Semantica 决策 16）",
        "source": "semantica",
    },
    "GB50019-2003": {
        "status": _SUPERSEDED, "replacement": "GB50736-2012",
        "note": "GB50019-2003 暖通部分已被 GB50736-2012 替代（Semantica 决策 17）",
        "source": "semantica",
    },
    "GB/T50378-2014": {
        "status": _EXPIRED, "replacement": None,
        "note": "GB/T50378-2014 已于 2019-08-01 废止（Semantica 决策 12）；替代版本未在给定清单中给出，未编造",
        "source": "semantica",
    },
    "GB50045-95": {
        "status": _EXPIRED, "replacement": None,
        "note": "GB50045-95 已自 2015-05-01 起废止（Semantica 决策 8）；替代版本未在给定清单中给出，未编造",
        "source": "semantica",
    },
    "GB50673-2002": {
        "status": _EXPIRED, "replacement": "GB50763-2012",
        "note": "GB50673-2002 已废止，应统一为 GB50763-2012（Semantica 决策 14）",
        "source": "semantica",
    },
    "JGJ50-2001": {
        "status": _SUPERSEDED, "replacement": "GB50763-2012",
        "note": "JGJ50-2001 为旧行业标准，应统一为 GB50763-2012（Semantica 决策 14）",
        "source": "semantica",
    },
    "DGJ08-107-2012": {
        "status": _SUPERSEDED, "replacement": "DGJ08-107-2015",
        "note": "DGJ08-107-2015 为现行上海标准（Semantica 决策 15）",
        "source": "semantica",
    },
    "GB50189-2005": {
        "status": _SUPERSEDED, "replacement": "GB50189-2015",
        "note": "GB50189-2005 已被 GB50189-2015 替代（Semantica 决策 15）",
        "source": "semantica",
    },
    "建标191": {
        "status": _SUPERSEDED, "replacement": "建标191-2018《普通高等学校建筑面积指标》",
        "note": "旧名《普通高等学校建筑规划面积指标》已于 2018-09-01 废止；新名为《普通高等学校建筑面积指标》（Semantica 决策 9/18）",
        "source": "semantica",
    },
    "建标191-2018": {
        "status": _SUPERSEDED, "replacement": "建标191-2018《普通高等学校建筑面积指标》",
        "note": "编号本身为 2018 版；若正文仍用旧名《普通高等学校建筑规划面积指标》则需改名（Semantica 决策 9/18）",
        "source": "semantica",
    },
    "DGJ08-9-2003": {
        "status": _SUPERSEDED, "replacement": "DGJ08-9-2013",
        "note": "DGJ08-9-2013 为现行版；DGJ08-9-2003 为旧版（Semantica 决策 22/25）",
        "source": "semantica",
    },
    # 决策中作为现行/核查依据出现的版本
    "GB50034-2013": {"status": _CURRENT, "replacement": None,
                     "note": "Semantica 决策中的现行替代版本", "source": "semantica"},
    "GB50736-2012": {"status": _CURRENT, "replacement": None,
                     "note": "Semantica 决策中的现行替代版本", "source": "semantica"},
    "GB50763-2012": {"status": _CURRENT, "replacement": None,
                     "note": "Semantica 决策中的现行替代版本", "source": "semantica"},
    "DGJ08-107-2015": {"status": _CURRENT, "replacement": None,
                       "note": "Semantica 决策中的现行上海标准", "source": "semantica"},
    "GB50189-2015": {"status": _CURRENT, "replacement": None,
                     "note": "Semantica 决策中的现行替代版本", "source": "semantica"},
    "DGJ08-9-2013": {"status": _CURRENT, "replacement": None,
                     "note": "Semantica 决策中的现行版", "source": "semantica"},
    "GB50011-2010": {"status": _CURRENT, "replacement": None,
                     "note": "Semantica 决策中的核查依据", "source": "semantica"},
    "GB50016-2014": {"status": _CURRENT, "replacement": None,
                     "note": "GB50016-2014(2018年版)，Semantica 决策中的核查依据", "source": "semantica"},
    "GB50974-2014": {"status": _CURRENT, "replacement": None,
                     "note": "Semantica 决策中的核查依据", "source": "semantica"},
}

_STD_ALIAS = {
    "GB50011": "GB50011-2010",
    "GB50763": "GB50763-2012",
    "GB50974": "GB50974-2014",
    "GB50016": "GB50016-2014",
}

_STD_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<prefix>GB\s*/\s*T|GB|JGJ|DGJ|CJJ|DB\s*\d*|建标)"
    r"\s*[-]?\s*"
    r"(?P<body>\d+(?:\.\d+)?(?:[-–—]\d+(?:\.\d+)?)*)"
)


def _norm_std(prefix: str, body: str) -> str:
    prefix = re.sub(r"\s+", "", prefix or "").upper()
    body = re.sub(r"[–—]", "-", body or "").strip("-")
    return prefix + body


def _lookup_std(std_no: str):
    if std_no in _STANDARD_DB:
        return std_no, _STANDARD_DB[std_no]
    if std_no in _STD_ALIAS:
        key = _STD_ALIAS[std_no]
        return key, _STANDARD_DB[key]
    # 年份前缀匹配（如 GB50011 附录A）
    cands = [k for k in _STANDARD_DB if k.startswith(std_no + "-")]
    if len(cands) == 1:
        return cands[0], _STANDARD_DB[cands[0]]
    return std_no, None


def standard_currency_check(text: str) -> dict:
    """检查正文引用的标准是否现行版。查不到 → UNKNOWN，不编造。"""
    text = text or ""
    refs_by_no = {}
    for m in _STD_RE.finditer(text):
        std_no = _norm_std(m.group("prefix"), m.group("body"))
        if std_no in refs_by_no:
            refs_by_no[std_no]["count"] += 1
            continue
        ctx = text[max(0, m.start() - 36):m.end() + 36].replace("\n", " ")
        key, info = _lookup_std(std_no)
        if info is None:
            status, replacement, note, source = (
                _UNKNOWN, None,
                "未在已废止/已替代清单中查到该标准号；不判定时效，不编造",
                "not_found",
            )
        else:
            status = info["status"]
            replacement = info.get("replacement")
            note = info.get("note", "")
            source = info.get("source", "semantica")
            # 建标191：只有旧名才判 superseded；新名/无名称则标 UNKNOWN 待核
            if key.startswith("建标191"):
                if "建筑规划面积指标" in text:
                    status, replacement = _SUPERSEDED, "《普通高等学校建筑面积指标》（建标191-2018）"
                    note = "正文使用旧名《普通高等学校建筑规划面积指标》，2018-09-01 已废止"
                elif "建筑面积指标" in text:
                    status, replacement = _CURRENT, None
                    note = "正文使用 2018 新名《普通高等学校建筑面积指标》"
                else:
                    status, replacement = _UNKNOWN, None
                    note = "仅见建标191编号，未见标准名称；无法判定新旧名，待核"
        refs_by_no[std_no] = {
            "std_no": std_no, "status": status, "replacement": replacement,
            "note": note, "source": source, "context": ctx.strip(), "count": 1,
        }

    # 标准名称（无编号）也要查：旧名「建筑规划面积指标」。
    # 若正文同时给了建标191编号，编号 ref 已覆盖该问题，不重复计数。
    name_refs = []
    has_jianbiao = any(r["std_no"].startswith("建标191") for r in refs_by_no.values())
    if "建筑规划面积指标" in text and not has_jianbiao:
        name_refs.append({
            "std_no": "普通高等学校建筑规划面积指标（旧名）",
            "status": _SUPERSEDED,
            "replacement": "《普通高等学校建筑面积指标》（建标191-2018）",
            "note": "2018-09-01 已废止旧名，应改为新名（Semantica 决策 9/18）",
            "source": "semantica",
        })

    refs = sorted(refs_by_no.values(), key=lambda x: x["std_no"])
    expired = [r for r in refs if r["status"] == _EXPIRED]
    superseded = [r for r in refs if r["status"] == _SUPERSEDED]
    current = [r for r in refs if r["status"] == _CURRENT]
    unknown = [r for r in refs if r["status"] == _UNKNOWN]
    expired += [r for r in name_refs if r["status"] == _EXPIRED]
    superseded += [r for r in name_refs if r["status"] == _SUPERSEDED]
    return {
        "refs": refs,
        "name_refs": name_refs,
        "expired": expired,
        "superseded": superseded,
        "current": current,
        "unknown": unknown,
        "standard_count": len(refs),
        "expired_count": len(expired),
        "superseded_count": len(superseded),
        "unknown_count": len(unknown),
        "pass": len(expired) == 0,
        "note": "expired 为硬错；superseded 可接受但建议更新；未查到的标 UNKNOWN。",
    }


# ---------------------------------------------------------------------------
# P2-1 术语一致性
# ---------------------------------------------------------------------------

_SUPPLEMENT_ALIASES = {
    "建筑安装工程费用": ["建筑安装工程费用", "建筑安装工程费", "建安工程费用",
                         "建安工程费", "建安费"],
    "工程建设其他费用": ["工程建设其他费用", "工程建设其他费", "其他费用",
                         "其他费", "二类费"],
    "预备费": ["预备费", "基本预备费"],
    "总投资": ["总投资", "项目总投资", "总投资额", "投资总额"],
    "总建筑面积": ["总建筑面积", "新建总建筑面积"],
    "年总用水量": ["年总用水量", "年用水量"],
    "年总耗电量": ["年总耗电量", "年用电量", "年耗电量"],
    "单位建筑面积电耗": ["单位建筑面积电耗", "单位面积电耗"],
    "综合能耗（当量值）": ["综合能耗（当量值）", "综合能耗", "总能耗"],
    "可行性研究报告": ["可行性研究报告", "可研报告"],
}


def _load_alias_groups(aliases_path=None, project_dir=None) -> dict:
    """读取 fact-aliases.yaml；失败则返回空 dict（由内置补充组兜底）。"""
    cands = []
    if aliases_path:
        cands.append(Path(aliases_path))
    if project_dir:
        p = Path(project_dir)
        cands += [
            p / "形-可复用知识资产-v1.0" / "ontology" / "fact-aliases.yaml",
            p / "projects" / "ecust-ai" / "shape" / "ontology" / "fact-aliases.yaml",
        ]
        cands += sorted(p.glob("形-可复用知识资产-v1.0*/**/fact-aliases.yaml"))[:3]
    for c in cands:
        try:
            if not c.is_file():
                continue
            text = c.read_text(encoding="utf-8")
            try:
                import yaml  # type: ignore
            except Exception:
                return {}
            data = yaml.safe_load(text) or {}
            aliases = data.get("aliases") or {}
            if isinstance(aliases, dict):
                return {str(k): [str(x) for x in (v or [])]
                        for k, v in aliases.items() if isinstance(v, list)}
        except Exception:
            continue
    return {}


_CANON_EQUIV = {
    "建安工程费用": "建筑安装工程费用",
    "建安工程费": "建筑安装工程费用",
    "建安费": "建筑安装工程费用",
    "基本预备费": "预备费",
    "项目总投资": "总投资",
    "年用水量": "年总用水量",
    "年用电量": "年总耗电量",
    "年耗电量": "年总耗电量",
}


def _merge_term_groups(yaml_groups: dict) -> list:
    groups = {k: list(v) for k, v in (yaml_groups or {}).items()}
    # 先把「建安工程费用」等规范名并入正式长名，避免同一 variant 被两个组
    # 同时拥有而在去歧义时整组丢掉。
    for src, dst in list(_CANON_EQUIV.items()):
        if src in groups:
            vals = groups.pop(src)
            cur = groups.setdefault(dst, [])
            for v in [src] + vals:
                if v not in cur:
                    cur.append(v)
    for canon, variants in _SUPPLEMENT_ALIASES.items():
        cur = groups.setdefault(canon, [])
        for v in variants:
            if v not in cur:
                cur.append(v)
    # 统计每个 variant 归属几个组；歧义 variant 丢弃（如「建筑面积」）
    owners = defaultdict(set)
    for canon, variants in groups.items():
        for v in variants:
            owners[v].add(canon)
        owners[canon].add(canon)
    merged = []
    for canon, variants in groups.items():
        vals = {canon}
        for v in variants:
            if len(owners[v]) == 1:
                vals.add(v)
        vals = [v for v in vals if len(v) >= 2]
        if len(vals) >= 2:
            merged.append((canon, sorted(vals, key=len, reverse=True)))
    return merged


def term_consistency(texts: dict, aliases_path=None, project_dir=None) -> dict:
    """术语一致性：同一同义组内出现 ≥2 个不同叫法 → inconsistent。"""
    texts = {str(k): (v or "") for k, v in (texts or {}).items()}
    yaml_groups = _load_alias_groups(aliases_path=aliases_path, project_dir=project_dir)
    groups = _merge_term_groups(yaml_groups)
    out_groups, inconsistent = [], []
    by_section = {sec: {"inconsistent_count": 0, "groups": []} for sec in texts}
    for canon, variants in groups:
        pattern = re.compile("|".join(re.escape(v) for v in variants))
        counts = Counter()
        secs = defaultdict(set)
        sec_counts = defaultdict(Counter)
        for sec, text in texts.items():
            for m in pattern.finditer(text or ""):
                name = m.group(0)
                counts[name] += 1
                secs[name].add(sec)
                sec_counts[sec][name] += 1
        if not counts:
            continue
        for sec, cc in sec_counts.items():
            if len(cc) >= 2:
                by_section[sec]["inconsistent_count"] += 1
                by_section[sec]["groups"].append(canon)
        variants_out = [
            {"name": name, "count": counts[name],
             "sections": sorted(secs[name])}
            for name in variants if counts.get(name)
        ]
        variants_out.sort(key=lambda x: (-x["count"], x["name"]))
        item = {
            "canonical": canon,
            "variants": variants_out,
            "variant_count": len(variants_out),
            "total": sum(counts.values()),
        }
        out_groups.append(item)
        if len(variants_out) >= 2:
            inconsistent.append(item)
    out_groups.sort(key=lambda x: (-x["total"], x["canonical"]))
    inconsistent.sort(key=lambda x: (-x["variant_count"], -x["total"], x["canonical"]))
    for sec, item in by_section.items():
        item["groups"].sort()
    return {
        "groups": out_groups,
        "inconsistent": inconsistent,
        "by_section": by_section,
        "groups_checked": len(groups),
        "groups_with_hits": len(out_groups),
        "inconsistent_count": len(inconsistent),
        "pass": len(inconsistent) == 0,
        "note": "同义组来自 fact-aliases.yaml + 内置补充；只统计出现 ≥2 种叫法的组。",
    }


# ---------------------------------------------------------------------------
# P2-2 证据链完整性
# ---------------------------------------------------------------------------

_ARITH_KEYWORDS = ("核对", "复算", "验算", "加总", "相差", "差额", "表列",
                   "等式", "误算", "更正", "原稿")
_MATH_CHARS = ("=", "+", "×", "÷", "—")


def _data_numbers(sentence: str) -> list:
    s = CITATION_RE.sub("", sentence or "")
    s = re.sub(r"§\s*\d+(?:\.\d+)+", "", s)
    s = re.sub(r"[表图]\s*\d+[-–—]\d+", "", s)
    # 标准号整体排除（不是数据值）
    s = re.sub(r"(?:GB\s*/\s*T|GB|JGJ|DGJ|CJJ|建标)\s*[-]?\s*\d+(?:[.\-–—]\d+)*", "", s)
    return re.findall(_NUM, s)


def _is_arithmetic_check(sentence: str, numbers: list) -> bool:
    if len(numbers) < 2:
        return False
    if any(k in sentence for k in _ARITH_KEYWORDS):
        return True
    return any(ch in sentence for ch in _MATH_CHARS)


def evidence_completeness(text: str) -> dict:
    """证据链完整性：有数值的句子是否绑定 〔P-xxx〕。"""
    paras = _prose_lines(text)
    total_sentences = 0
    with_number = 0
    bound = 0
    unbound = []
    arithmetic = []
    for pi, para in enumerate(paras):
        for sent in _split_sentences(para):
            total_sentences += 1
            nums = _data_numbers(sent)
            if not nums:
                continue
            with_number += 1
            if CITATION_RE.search(sent):
                bound += 1
                continue
            if _is_arithmetic_check(sent, nums):
                arithmetic.append({"sentence": _head(sent, 90), "numbers": nums,
                                   "para_idx": pi})
                continue
            unbound.append({
                "sentence": _head(sent, 120),
                "numbers": nums,
                "para_idx": pi,
            })
    considered = with_number - len(arithmetic)
    ratio = (bound / considered) if considered else 1.0
    return {
        "total_sentences": total_sentences,
        "sentences_with_number": with_number,
        "sentences_bound": bound,
        "arithmetic_checks": arithmetic,
        "arithmetic_check_count": len(arithmetic),
        "unbound": unbound,
        "unbound_count": len(unbound),
        "bound_ratio": round(ratio, 4),
        "pass": len(unbound) == 0,
        "note": "纯算式/核对句（含 = + × 或「核对/复算/加总/相差」且有 ≥2 个数）不计 unbound。",
    }


# ---------------------------------------------------------------------------
# P2-3 可读性
# ---------------------------------------------------------------------------

_TRANSITIONS = (
    "因此", "据此", "综上", "综上所述", "其中", "此外", "同时", "但是",
    "然而", "所以", "另外", "一方面", "另一方面", "首先", "其次", "最后",
    "由此可见", "总的来说", "总体而言", "进而", "从而", "由于", "鉴于",
)
_OPENING_MIN = 3          # 3 字即可覆盖「本项目」这类主语开头


def _common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _readability_paras(text: str) -> list:
    """可读性只看正文段落：排除表题和很短的小标题。"""
    out = []
    for p in _prose_lines(text):
        s = p.strip()
        if re.match(r"^[表图]\s*\d+[-–—]\d+", s):
            continue
        # 参考文献清单：连续以《…》开头的条目不是叙述段
        if s.startswith("《") and len(s) < 80:
            continue
        if len(s) <= 8 and re.search(r"(计算|分析|概况|说明|依据|小结|结论)$", s):
            continue
        out.append(p)
    return out


def readability(text: str) -> dict:
    """可读性：段落长度分布 / 连续重复开头 / 过渡词覆盖。"""
    paras = _readability_paras(text)
    clean = []
    for p in paras:
        s = CITATION_RE.sub("", p)
        s = re.sub(r"[\s*_`]", "", s)
        clean.append(s)
    lengths = [_chars(p) for p in clean]
    n = len(lengths)
    if n:
        avg = sum(lengths) / n
        var = sum((x - avg) ** 2 for x in lengths) / n
        stats = {
            "min": min(lengths), "max": max(lengths),
            "avg": round(avg, 2), "std": round(math.sqrt(var), 2), "n": n,
        }
    else:
        stats = {"min": 0, "max": 0, "avg": 0.0, "std": 0.0, "n": 0}

    # 连续重复开头：相邻段公共前缀 >= 3 视为一段连续组
    runs = []
    start = 0
    for i in range(1, n):
        cp = _common_prefix_len(clean[i - 1], clean[i])
        if cp < _OPENING_MIN:
            if i - start >= 2:
                runs.append((start, i))
            start = i
    if n - start >= 2:
        runs.append((start, n))

    repeated = []
    for a, b in runs:
        prefix = clean[a]
        for k in range(a + 1, b):
            cp = _common_prefix_len(prefix, clean[k])
            prefix = prefix[:cp]
        opening = prefix[:_OPENING_MIN] if len(prefix) >= _OPENING_MIN else prefix
        repeated.append({
            "opening": opening,
            "count": b - a,
            "paras": list(range(a, b)),
            "severe": (b - a) >= 3,
        })

    trans_hits = [
        i for i, p in enumerate(paras)
        if any(w in p for w in _TRANSITIONS)
    ]
    ratio = (len(trans_hits) / n) if n else 0.0
    severe = [r for r in repeated if r["severe"]]
    return {
        "para_len_stats": stats,
        "repeated_openings": repeated,
        "repeated_opening_count": len(repeated),
        "severe_repeat_count": len(severe),
        "transition_hits": trans_hits,
        "transition_ratio": round(ratio, 4),
        "pass": len(severe) == 0,
        "note": "相邻段开头 ≥3 字相同即记 repeated；连续 ≥3 段记 severe。",
    }


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------

SECTION_TITLE_HINTS = {
    "1.1": "项目概况",
    "7.2.2": "各类能耗指标计算",
    "13.3": "投资估算",
}

# 普通文本小标题没有层级，extract_section 需要显式告诉它下一节从哪开始。
# 否则 7.2.2 会把 7.2.3「能耗指标分析」一并吞入（实测 11 段 / 3 表）。
SOURCE_STOP_TITLES = {
    "1.1": ["研究内容和编制依据"],
    "7.2.2": ["能耗指标分析"],
    "13.3": ["资金筹措", "资金筹措方案"],
    "13.4": ["学校财务状况", "项目资金筹措方案"],
}


def _find_normalized_md(project: Path):
    cands = [
        project / "SHUFE-BDC-2019-001" / "source" / "normalized.md",
        project / "chain" / "upstream-201909" / "report" / "source" / "normalized.md",
    ]
    cands += sorted(project.glob("**/source/normalized.md"))[:5]
    for c in cands:
        if c.is_file():
            return c
    return None


def _section_title(project: Path, sec: str) -> str:
    if sec in SECTION_TITLE_HINTS:
        return SECTION_TITLE_HINTS[sec]
    hits = sorted(project.glob("还原正文-%s*.md" % sec))
    if hits:
        stem = hits[0].stem  # 还原正文-7.2.3能耗指标分析
        m = re.match(r"还原正文-%s(.*)$" % re.escape(sec), stem)
        if m and m.group(1):
            return m.group(1)
    return sec


def _extract_source(project: Path, sec: str, source) -> dict:
    """返回 {text, paras, tables, found, mode, title}。"""
    if isinstance(source, dict):
        val = source.get(sec) or source.get(str(sec))
        if val is None:
            return {"text": "", "paras": [], "tables": [], "found": False,
                    "mode": "dict", "title": ""}
        if isinstance(val, (list, tuple)):
            return {"text": "\n".join(map(str, val)),
                    "paras": [str(x) for x in val], "tables": [],
                    "found": True, "mode": "dict_list", "title": ""}
        text = str(val)
        return {"text": text, "paras": split_paragraphs(text),
                "tables": [], "found": True, "mode": "dict_text", "title": ""}

    path = None
    if source:
        p = Path(source)
        if p.is_file():
            path = p
    if path is None:
        path = _find_normalized_md(project)
    if path is None:
        return {"text": "", "paras": [], "tables": [], "found": False,
                "mode": "missing", "title": ""}

    if path.suffix == ".jsonl":
        recs = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if str(obj.get("section") or obj.get("section_id") or "") == sec:
                recs.append(str(obj.get("text") or obj.get("content") or ""))
        text = "\n".join(recs)
        return {"text": text, "paras": split_paragraphs(text),
                "tables": [], "found": bool(text), "mode": "jsonl", "title": ""}

    text = path.read_text(encoding="utf-8")
    title = _section_title(project, sec)
    titles = [title]
    if "各类" not in title and "能耗指标" in title:
        titles.append("各类" + title)
    if title != SECTION_TITLE_HINTS.get(sec):
        titles.append(SECTION_TITLE_HINTS.get(sec, ""))
    try:
        from corpus_pipeline.evo_source_section import extract_section
    except Exception:
        extract_section = None
    stop_titles = SOURCE_STOP_TITLES.get(sec, [])
    for t in titles:
        if not t or extract_section is None:
            continue
        r = extract_section(text, t, stop_titles=stop_titles)
        if r.get("found") and r.get("paras"):
            return {
                "text": "\n".join(r.get("paras") or []),
                "paras": [str(x) for x in (r.get("paras") or [])],
                "tables": r.get("tables") or [],
                "found": True, "mode": "normalized:" + t, "title": t,
                "path": str(path),
            }
    # 标题兜底：找包含标题核心词的 heading
    heads = re.findall(r"^#{1,6}\s+(.+)$", text, re.M)
    for h in heads:
        if any(tok in h for tok in re.findall(r"[一-鿿]{2,}", title)):
            if extract_section:
                r = extract_section(text, h.strip(), stop_titles=stop_titles)
                if r.get("found") and r.get("paras"):
                    return {
                        "text": "\n".join(r.get("paras") or []),
                        "paras": [str(x) for x in (r.get("paras") or [])],
                        "tables": r.get("tables") or [],
                        "found": True, "mode": "heading:" + h.strip(), "title": h.strip(),
                        "path": str(path),
                    }
    return {"text": "", "paras": [], "tables": [], "found": False,
            "mode": "not_found", "title": title, "path": str(path)}


def _resolve_restored(project: Path, sections: list, restored_texts) -> tuple:
    out, missing = {}, []
    if isinstance(restored_texts, dict):
        for sec in sections:
            val = restored_texts.get(sec) or restored_texts.get(str(sec))
            if val:
                out[sec] = str(val)
            else:
                missing.append(sec)
        return out, missing
    for sec in sections:
        hits = sorted(project.glob("还原正文-%s*.md" % sec))
        if not hits:
            hits = sorted(project.glob("**/还原正文-%s*.md" % sec))[:3]
        if hits:
            out[sec] = hits[0].read_text(encoding="utf-8")
        else:
            out[sec] = ""
            missing.append(sec)
    return out, missing


def evaluate_all(project_dir, sections, source_chunks=None,
                 restored_texts=None) -> dict:
    """跑全部 6 个新维度，返回汇总。"""
    project = Path(project_dir)
    sections = [str(s).strip() for s in (sections or []) if str(s).strip()]
    restored, missing_restored = _resolve_restored(project, sections, restored_texts)

    semantic, standard, evidence, readable = {}, {}, {}, {}
    source_meta = {}
    errors = []
    if missing_restored:
        errors.append("缺少还原正文：%s" % ",".join(missing_restored))

    for sec in sections:
        src = _extract_source(project, sec, source_chunks)
        source_meta[sec] = {
            "found": src.get("found"), "mode": src.get("mode"),
            "title": src.get("title"), "paras": len(src.get("paras") or []),
        }
        if not src.get("found"):
            errors.append("找不到原文节：%s" % sec)
        mine_paras = split_paragraphs(restored.get(sec, ""), include_tables=False)
        semantic[sec] = semantic_alignment(src.get("paras") or [], mine_paras)
        standard[sec] = standard_currency_check(restored.get(sec, ""))
        evidence[sec] = evidence_completeness(restored.get(sec, ""))
        readable[sec] = readability(restored.get(sec, ""))

    cross = cross_section_consistency(restored)
    terms = term_consistency(restored, project_dir=str(project))

    p01_pass = all(v["pass"] for v in semantic.values()) and bool(sections)
    p02_pass = cross["pass"]
    p1_pass = all(v["pass"] for v in standard.values())
    p21_pass = terms["pass"]
    p22_pass = all(v["pass"] for v in evidence.values())
    p23_pass = all(v["pass"] for v in readable.values())

    dims = {
        "P0-1_semantic_alignment": p01_pass,
        "P0-2_cross_section": p02_pass,
        "P1_standard_currency": p1_pass,
        "P2-1_term_consistency": p21_pass,
        "P2-2_evidence_completeness": p22_pass,
        "P2-3_readability": p23_pass,
    }
    failed = [k for k, v in dims.items() if not v]
    grade = "A" if not failed else ("B" if len(failed) == 1
                                    else ("C" if len(failed) == 2 else "D"))

    summary = {
        "P0-1_semantic_alignment": {
            "avg_scores": {s: v["avg_score"] for s, v in semantic.items()},
            "min_scores": {s: v["min_score"] for s, v in semantic.items()},
            "order_ok": {s: v["order_ok"] for s, v in semantic.items()},
            "unmatched_src_total": sum(len(v["unmatched_src"]) for v in semantic.values()),
        },
        "P0-2_cross_section": {
            "total_concepts": cross["total_concepts"],
            "consistent_count": cross["consistent_count"],
            "inconsistent_count": cross["inconsistent_count"],
            "inconsistent": [x["concept"] for x in cross["inconsistent"]],
        },
        "P1_standard_currency": {
            "standard_count": {s: v["standard_count"] for s, v in standard.items()},
            "expired_total": sum(v["expired_count"] for v in standard.values()),
            "superseded_total": sum(v["superseded_count"] for v in standard.values()),
            "unknown_total": sum(v["unknown_count"] for v in standard.values()),
        },
        "P2-1_term_consistency": {
            "groups_checked": terms["groups_checked"],
            "groups_with_hits": terms["groups_with_hits"],
            "inconsistent_count": terms["inconsistent_count"],
            "inconsistent": [x["canonical"] for x in terms["inconsistent"]],
            "by_section": terms["by_section"],
        },
        "P2-2_evidence_completeness": {
            "sentences_with_number": {s: v["sentences_with_number"] for s, v in evidence.items()},
            "unbound_total": sum(v["unbound_count"] for v in evidence.values()),
            "arithmetic_checks_total": sum(v["arithmetic_check_count"] for v in evidence.values()),
            "bound_ratio": {s: v["bound_ratio"] for s, v in evidence.items()},
        },
        "P2-3_readability": {
            "para_count": {s: v["para_len_stats"]["n"] for s, v in readable.items()},
            "repeated_opening_count": {s: v["repeated_opening_count"] for s, v in readable.items()},
            "severe_repeat_total": sum(v["severe_repeat_count"] for v in readable.values()),
            "transition_ratio": {s: v["transition_ratio"] for s, v in readable.items()},
        },
        "failed_dimensions": failed,
        "errors": errors,
    }

    return {
        "project_dir": str(project),
        "sections": sections,
        "source_meta": source_meta,
        "P0-1_semantic_alignment": semantic,
        "P0-2_cross_section": cross,
        "P1_standard_currency": standard,
        "P2-1_term_consistency": terms,
        "P2-2_evidence_completeness": evidence,
        "P2-3_readability": readable,
        "pass": not failed,
        "grade": grade,
        "summary": summary,
    }


__all__ = [
    "semantic_alignment", "cross_section_consistency",
    "standard_currency_check", "term_consistency",
    "evidence_completeness", "readability", "evaluate_all",
    "split_paragraphs",
]
