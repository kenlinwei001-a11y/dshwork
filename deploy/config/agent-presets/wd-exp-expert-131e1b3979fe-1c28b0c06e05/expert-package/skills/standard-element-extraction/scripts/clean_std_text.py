#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境标准文本归一化：去目录行 / 识别介质与分析物 / 标注表与附录标题。

问题背景：标准 md 开头有「1 适用范围....1」这类目录行，抽取器若不过滤，
会把目录当条款正文，产出「requirement = '1 适用范围....1'」的垃圾规则。
本脚本输出 <slug>.clean.md + <slug>.meta.json，供后续所有节点消费。
用法: python3 clean_std_text.py --text <std.md> --out <dir> [--slug 名称]
"""
import argparse,json,os,re,sys

TOC=re.compile(r'^\s*#*\s*(?:\d{1,2}(?:\.\d{1,2})*)\s+\S.{0,60}?(?:\.{3,}|…{2,}|·{3,})\s*\d+\s*$')
TOC_TAB=re.compile(r'^\s*#*\s*(?:表|附录)\s?[0-9A-Z][^\n]{0,50}(?:\.{3,}|…{2,})\s*\d+\s*$')
MEDIA=[('生活污水','废水'),('工业废水','废水'),('废水','废水'),('地表水','水'),('地下水','水'),
       ('饮用水','水'),('海水','水'),('底泥','底泥'),('沉积物','底泥'),('土壤','土壤'),
       ('固体废物','固废'),('固体废弃物','固废'),('环境空气','环境空气'),('空气质量','环境空气'),
       ('废气','废气'),('排气筒','废气'),('生物','生物')]

def strip_toc(text):
    out=[]; removed=0
    for line in text.splitlines():
        if TOC.match(line) or TOC_TAB.match(line): removed+=1; continue
        out.append(line)
    return '\n'.join(out), removed

def detect_media(text):
    head=text[:4000]
    found=[]
    for kw,dom in MEDIA:
        if kw in head and dom not in found: found.append(dom)
    return found or ['水']

def detect_analytes(text):
    """从第 1 章/标题里抓被测物清单：65 种元素 / 8 种离子 / A、B、C 列表"""
    res={'count':None,'items':[]}
    m=re.search(r'(\d+)\s*种(元素|离子|化合物|有机物|农药|多环芳烃|重金属)',text[:6000])
    if m: res['count']=int(m.group(1)); res['kind']=m.group(2)
    # 形如「F⁻、Cl⁻、NO₂⁻」的顿号列表
    seg=re.search(r'((?:[A-Za-z\u4e00-\u9fa5]{1,6}[⁻⁺]?[、，,]){4,}[A-Za-z\u4e00-\u9fa5]{1,8}[⁻⁺]?)',text[:8000])
    if seg:
        items=[x.strip() for x in re.split(r'[、，,]',seg.group(1)) if x.strip()]
        res['items']=items[:80]
    return res

def tables_and_annexes(text):
    tabs=sorted(set(re.findall(r'表\s?([0-9]{1,2})',text)),key=lambda x:int(x))
    apps=sorted(set(re.findall(r'附录\s?([A-Z])',text)))
    return tabs,apps

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--text',required=True)
    ap.add_argument('--out',required=True); ap.add_argument('--slug',default='')
    a=ap.parse_args()
    raw=open(a.text,encoding='utf-8',errors='ignore').read()
    clean,removed=strip_toc(raw)
    slug=a.slug or os.path.splitext(os.path.basename(a.text))[0]
    os.makedirs(os.path.join(a.out,'standards'),exist_ok=True)
    cp=os.path.join(a.out,'standards',slug+'.clean.md')
    open(cp,'w',encoding='utf-8').write(clean)
    media=detect_media(clean); ana=detect_analytes(clean); tabs,apps=tables_and_annexes(clean)
    meta={'slug':slug,'toc_lines_removed':removed,'chars_before':len(raw),'chars_after':len(clean),
          'media':media,'analytes':ana,'tables':tabs,'annexes':apps,
          'clean_text':cp}
    json.dump(meta,open(os.path.join(a.out,'standards',slug+'.meta.json'),'w',encoding='utf-8'),
              ensure_ascii=False,indent=1)
    print(json.dumps({'slug':slug,'toc_removed':removed,'media':media,
                      'analytes':{'count':ana['count'],'items':len(ana['items'])},
                      'tables':len(tabs),'annexes':len(apps)},ensure_ascii=False))
    return 0

if __name__=='__main__': sys.exit(main())
