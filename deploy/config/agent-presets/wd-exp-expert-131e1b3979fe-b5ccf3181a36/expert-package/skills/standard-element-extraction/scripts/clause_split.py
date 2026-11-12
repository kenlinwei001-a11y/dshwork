# -*- coding: utf-8 -*-
"""B3 条款切分：把标准文本切成 clause_registry（目次驱动 + 编号正则）

输入：pdftext 产出的纯文本（含 "===== PAGE n =====" 分页）
输出：{"clauses":[{clause,heading,page,text}], "toc":{章号:标题}}
规则：
  1 目次段（含 "……" 或 "......" 的行）用于建 章号→标题 映射，不计入正文
  2 正文条款起点：行首 1~4 段编号 + 空白 + 文字
  3 续行并入当前条款，直到下一个编号或分页
用法：python3 clause_split.py --text HJ671.txt --out toc.json [--min-level 1]
"""
import argparse, json, re, sys

PAGE = re.compile(r"^===== PAGE (\d+) =====")
NUMLINE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,3}){0,3})\s*[、.．]?\s+(\S.{0,60})$")
TOCLINE = re.compile(r"(\d{1,2}(?:\.\d{1,3})?)\.{3,}|…{2,}")

def split(text, min_level=1):
    page = 0; toc = {}; clauses = {}; cur = None; in_toc = False
    for raw in text.splitlines():
        line = raw.rstrip()
        m = PAGE.match(line)
        if m: page = int(m.group(1)); in_toc = False; continue
        if "目次" in line: in_toc = True; continue
        if in_toc:
            t = TOCLINE.search(line)
            if t:
                num = t.group(1)
                head = re.sub(r"[.…]{3,}.*$", "", line).strip()
                head = re.sub(r"^\s*" + re.escape(num) + r"\s*", "", head).strip()
                if head: toc[num] = head
                continue
            if line.strip() and not TOCLINE.search(line) and page > 0 and "前" not in line:
                in_toc = False
        if not line.strip(): continue
        mm = NUMLINE.match(line)
        if mm:
            num, head = mm.group(1), mm.group(2).strip()
            # 排除：数值行（1.00 mg/L）、单字符标签（图内 1 S）、单位开头
            if len(head) < 2 or not re.match(r"^[\u4e00-\u9fffA-Za-z]", head):
                if cur: clauses[cur]["text"] += " " + line.strip()
                continue
            if re.match(r"^\d+(\.\d+)?\s*(mg/L|%|ml|mL|μg)", line.strip()):
                if cur: clauses[cur]["text"] += " " + line.strip()
                continue
            if len(num.split(".")) - 1 >= min_level or "." in num or num.isdigit():
                if num not in clauses:
                    clauses[num] = {"clause": num, "heading": head[:60], "page": page, "text": line.strip()}
                cur = num
                continue
        if cur:
            clauses[cur]["text"] += " " + line.strip()
    out = [c for c in clauses.values() if c["clause"] not in ("0",)]
    for c in out:
        c["text"] = re.sub(r"\s+", " ", c["text"])[:600]
    return {"clauses": out, "toc": toc, "n": len(out)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--min-level", type=int, default=0)
    a = ap.parse_args()
    d = split(open(a.text, encoding="utf-8").read(), a.min_level)
    json.dump(d, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{a.text}: 条款 {d['n']}，目次 {len(d['toc'])} 章")
    for c in d["clauses"][:8]:
        print(f"  {c['clause']:6s} p{c['page']:<3} {c['heading'][:30]}")
