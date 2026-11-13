#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 JSON 契约执行节点：script/gate 直接跑，llm 步骤停在这里等填。
用法: python3 run_contract.py --node rules --out <out> --text <txt> [--skill <skill目录>]
"""
import argparse, json, os, subprocess, sys

def vcheck(schema, data, path='$'):
    errs=[]
    t=schema.get('type')
    tm={'object':dict,'array':list,'string':str,'integer':int,'number':(int,float),'boolean':bool}
    if t and not isinstance(data, tm[t]): return [f'{path}: 期望 {t}']
    if 'enum' in schema and data not in schema['enum']: errs.append(f'{path}: 不在枚举 {schema["enum"]}')
    if t=='object':
        for k in schema.get('required',[]):
            if k not in data: errs.append(f'{path}.{k}: 缺失')
        for k,sub in (schema.get('properties') or {}).items():
            if isinstance(data,dict) and k in data: errs+=vcheck(sub,data[k],f'{path}.{k}')
    if t=='array':
        if 'minItems' in schema and len(data)<schema['minItems']: errs.append(f'{path}: 少于 {schema["minItems"]} 项')
        if 'items' in schema:
            for i,x in enumerate(data): errs+=vcheck(schema['items'],x,f'{path}[{i}]')
    return errs

CONTRACTS = {
 "contracts": {
  "handoff": {
   "inputs": [
    "{out}/ses.json"
   ],
   "steps": [
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/run_all.py --out {out} --stages package"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/run_all.py --out {out} --stages semantica"
    },
    {
     "run": "llm",
     "call": "handoff.write",
     "schema": "handoff.schema.json",
     "max_items": 1,
     "instruction": "数字一律取自 derived.json；先跑 handoff_state.py 生成交接引用"
    },
    {
     "run": "gate",
     "cmd": "python3 {skill}/scripts/validate_node.py --node handoff --out {out}"
    }
   ],
   "id": "handoff"
  },
  "audit": {
   "inputs": [
    "{out}/audit_findings.json"
   ],
   "steps": [
    {
     "run": "llm",
     "call": "audit.judge",
     "schema": "audit_result.schema.json",
     "max_items": 5,
     "instruction": "读 findings，抽 5 个样本回原文；判 B/D/W；写 04-audit.md 与 audit_result.json"
    },
    {
     "run": "gate",
     "cmd": "python3 {skill}/scripts/validate_node.py --node audit --out {out}"
    }
   ],
   "id": "audit"
  },
  "fix": {
   "inputs": [
    "{out}/04-audit.md"
   ],
   "steps": [
    {
     "run": "llm",
     "call": "fix.apply",
     "schema": "fix_plan.schema.json",
     "max_items": 20,
     "instruction": "只改被点名条目，revision_log 加一行"
    },
    {
     "run": "gate",
     "cmd": "python3 {skill}/scripts/validate_node.py --node fix --out {out}"
    }
   ],
   "id": "fix"
  },
  "elements": {
   "inputs": [
    "{out}/01-clauses.json"
   ],
   "steps": [
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/standard_store.py --clauses {out}/01-clauses.json --text {text} --db {out}/store.db"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/extract_candidates.py --clauses {out}/01-clauses.json --text {text} --out {out}/candidates.json"
    },
    {
     "run": "llm",
     "call": "elements.judge",
     "schema": "judgments.schema.json",
     "chunk": "by_family",
     "max_items": 30,
     "instruction": "只写判断：family/statement/obligation/applicability/origin；参数用 ref，不重抄数值｜只读 rows.json（含 numbers/chems/actions），不读 01 原文"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/assemble_elements.py --clauses {out}/01-clauses.json --candidates {out}/candidates.json --judgments {out}/judgments.json --out {out}/02-elements.json"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/convert_refs.py --elements {out}/02-elements.json --db {out}/store-*.db --out {out}/02-elements.refs.json"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/resolve.py --elements {out}/02-elements.refs.json --db {out}/store-*.db --out {out}/02-elements.resolved.json",
     "assert": "dangling==0"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/facts_build.py --out {out}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/facts_export.py --out {out}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/run_contract.py --util fact_rows --out {out}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/run_contract.py --util cleanup_intermediates --out {out}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/run_contract.py --util backfill_spans --out {out}"
    },
    {
     "run": "gate",
     "cmd": "python3 {skill}/scripts/validate_node.py --node elements --out {out} --text {text}"
    }
   ],
   "id": "elements"
  },
  "rules": {
   "inputs": [
    "{out}/01-clauses.json",
    "{out}/02-elements.json"
   ],
   "steps": [
    {
     "run": "llm",
     "call": "rules.cards",
     "schema": "rule_card.schema.json",
     "chunk": "by_category",
     "max_items": 30,
     "instruction": "只出卡片判定字段；覆盖矩阵不写｜只读 rows.json（含 numbers/chems/actions），不读 01 原文"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/build_coverage.py --clauses {out}/01-clauses.json --rules {out}/03-rules.json --write"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/classify_gaps.py --rules {out}/03-rules.json --write"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/facts_build.py --out {out}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/facts_export.py --out {out}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/run_contract.py --util fact_rows --out {out}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/run_contract.py --util cleanup_intermediates --out {out}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/run_contract.py --util backfill_spans --out {out}"
    },
    {
     "run": "gate",
     "cmd": "python3 {skill}/scripts/validate_node.py --node rules --out {out} --text {text}"
    }
   ],
   "id": "rules"
  },
  "toolchain": {
   "inputs": [
    "{out}/03-rules.json"
   ],
   "steps": [
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/run_all.py --out {out} --stages metrics --text {text}"
    },
    {
     "run": "gate",
     "cmd": "python3 {skill}/scripts/validate_node.py --node toolchain --out {out}"
    }
   ],
   "id": "toolchain"
  },
  "clauses": {
   "inputs": [
    "{text}"
   ],
   "steps": [
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/cap.py probe {pdf}",
     "when": "{pdf}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/clause_split.py --text {text} --out {out}/_split.json"
    },
    {
     "run": "llm",
     "call": "clauses.judge",
     "schema": "clause_registry.schema.json",
     "chunk": "by_chapter",
     "max_items": 20,
     "instruction": "只改差异：补漏条款、判 modality/type、章节角色、引用状态、缺口分类"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/facts_build.py --out {out}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/facts_export.py --out {out}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/run_contract.py --util fact_rows --out {out}"
    },
    {
     "run": "script",
     "cmd": "python3 {skill}/scripts/run_contract.py --util build_spans --out {out} --text {text}"
    },
    {
     "run": "gate",
     "cmd": "python3 {skill}/scripts/validate_node.py --node clauses --out {out} --text {text}"
    }
   ],
   "id": "clauses"
  }
 },
 "schemas": {
  "audit_result.schema.json": {
   "type": "object",
   "required": [
    "verdict",
    "blockers",
    "pending"
   ],
   "properties": {
    "verdict": {
     "enum": [
      "pass",
      "fail"
     ]
    },
    "blockers": {
     "type": "integer"
    },
    "pending": {
     "type": "integer"
    },
    "warnings": {
     "type": "integer"
    },
    "findings": {
     "type": "array"
    }
   }
  },
  "handoff.schema.json": {
   "type": "object",
   "required": [
    "sections"
   ],
   "properties": {
    "sections": {
     "type": "array",
     "minItems": 7,
     "items": {
      "type": "object",
      "required": [
       "title",
       "body"
      ],
      "properties": {
       "title": {
        "type": "string"
       },
       "body": {
        "type": "string"
       }
      }
     }
    }
   }
  },
  "judgments.schema.json": {
   "type": "object",
   "required": [
    "elements"
   ],
   "properties": {
    "elements": {
     "type": "array",
     "items": {
      "type": "object",
      "required": [
       "element_id",
       "clause",
       "family",
       "statement"
      ],
      "properties": {
       "element_id": {
        "type": "string"
       },
       "clause": {
        "type": "string"
       },
       "family": {
        "enum": [
         "META",
         "SCOPE",
         "PRIN",
         "SAMP",
         "PROC",
         "APPA",
         "MATL",
         "INTR",
         "CALC",
         "QC",
         "PERF",
         "RISK"
        ]
       },
       "statement": {
        "type": "string"
       },
       "obligation": {
        "enum": [
         "MUST",
         "SHOULD",
         "MAY",
         "MUST_NOT",
         "INFO"
        ]
       },
       "origin": {
        "enum": [
         "verbatim",
         "derived",
         "convention"
        ]
       },
       "applicability": {
        "type": "string"
       },
       "params": {
        "type": "array",
        "items": {
         "type": "object",
         "properties": {
          "ref": {
           "type": "string"
          },
          "name": {
           "type": "string"
          },
          "value": {
           "type": "number"
          },
          "unit": {
           "type": "string"
          }
         }
        }
       }
      }
     }
    }
   }
  },
  "fix_plan.schema.json": {
   "type": "object",
   "required": [
    "changes"
   ],
   "properties": {
    "changes": {
     "type": "array",
     "items": {
      "type": "object",
      "required": [
       "rule_id",
       "action"
      ],
      "properties": {
       "rule_id": {
        "type": "string"
       },
       "action": {
        "enum": [
         "update",
         "drop",
         "add",
         "reclassify"
        ]
       },
       "reason": {
        "type": "string"
       }
      }
     }
    }
   }
  },
  "clause_registry.schema.json": {
   "type": "object",
   "required": [
    "clause_registry"
   ],
   "properties": {
    "clause_registry": {
     "type": "array",
     "items": {
      "type": "object",
      "required": [
       "clause",
       "page",
       "quote",
       "modality",
       "type"
      ],
      "properties": {
       "clause": {
        "type": "string"
       },
       "page": {
        "type": "integer"
       },
       "quote": {
        "type": "string"
       },
       "modality": {
        "enum": [
         "MUST",
         "SHOULD",
         "MAY",
         "MUST_NOT",
         "INFO"
        ]
       },
       "type": {
        "enum": [
         "normative",
         "informative"
        ]
       },
       "heading": {
        "type": "string"
       }
      }
     }
    },
    "reference_register": {
     "type": "array"
    },
    "gaps": {
     "type": "array"
    }
   }
  },
  "rule_card.schema.json": {
   "type": "object",
   "required": [
    "audit_rule_cards"
   ],
   "properties": {
    "audit_rule_cards": {
     "type": "array",
     "items": {
      "type": "object",
      "required": [
       "rule_id",
       "category",
       "clause",
       "check_targets",
       "on_missing"
      ],
      "properties": {
       "rule_id": {
        "type": "string"
       },
       "category": {
        "enum": [
         "C1",
         "C2",
         "C3",
         "C4",
         "C5",
         "C6",
         "C7",
         "C8"
        ]
       },
       "clause": {
        "type": "string"
       },
       "predicate": {
        "type": "object"
       },
       "qualitative_check": {
        "type": "object"
       },
       "verdict_ceiling": {
        "enum": [
         "PASS",
         "NO_FAIL",
         "NO_PASS"
        ]
       },
       "check_targets": {
        "type": "array"
       },
       "on_missing": {
        "enum": [
         "FAIL",
         "UNVERIFIABLE"
        ]
       },
       "covers_clauses": {
        "type": "array"
       }
      }
     }
    }
   }
  },
  "sop_graph.schema.json": {
   "type": "object",
   "required": [
    "nodes",
    "edges"
   ],
   "properties": {
    "nodes": {
     "type": "array",
     "items": {
      "type": "object",
      "required": [
       "node_id",
       "type",
       "anchors"
      ],
      "properties": {
       "node_id": {
        "type": "string"
       },
       "type": {
        "enum": [
         "step",
         "reagent",
         "instrument",
         "qc_gate",
         "constraint",
         "justification"
        ]
       },
       "clauses": {
        "type": "array"
       },
       "params": {
        "type": "array"
       },
       "done_when": {
        "type": "string"
       },
       "criteria": {
        "type": "array"
       },
       "qualitative": {
        "type": "array"
       },
       "anchors": {
        "type": "array",
        "minItems": 1
       },
       "usage": {
        "enum": [
         "normative",
         "reference_only"
        ]
       },
       "no_threshold": {
        "type": "boolean"
       }
      }
     }
    },
    "edges": {
     "type": "array",
     "items": {
      "type": "object",
      "required": [
       "from",
       "to",
       "type"
      ],
      "properties": {
       "from": {
        "type": "string"
       },
       "to": {
        "type": "string"
       },
       "type": {
        "enum": [
         "precedes",
         "requires",
         "constrains",
         "verifies",
         "justifies",
         "cites"
        ]
       }
      }
     }
    }
   }
  }
 }
}



# ---- 内嵌工具（受技能资源数量上限约束，合并到本文件）----
def util_fact_rows(O):
    import re as _re
    F=json.load(open(os.path.join(O,'facts.json'),encoding='utf-8'))
    NUM=_re.compile(r'(\d+(?:\.\d+)?)\s*(mg/L|μg/L|ug/L|mol/L|mmol/L|g/L|ml|mL|L|μl|g|mg|μg|ug|℃|°C|nm|min|h|d|%|倍)')
    CHEM=_re.compile(r'([A-Z][a-z]?(?:\d+)?(?:[A-Z][a-z]?\d*)+)')
    VERB=_re.compile(r'(称取|量取|移取|吸取|溶解|稀释|定容|混匀|摇匀|静置|加热|冷却|过滤|蒸馏|离心|调节|保存|贮存|干燥|洗涤|加入|注入|测定|绘制|计算|记录)')
    binds={}
    for b in F.get('bindings') or []: binds.setdefault(b['clause'],[]).append(b['ref'].get('raw'))
    rows=[]
    for c in F.get('clauses') or []:
        q=c.get('quote') or ''
        rows.append({'clause':c['clause'],'page':c.get('page'),'modality':c.get('modality'),'type':c.get('type'),
            'head':q[:200],'numbers':[m.group(0) for m in NUM.finditer(q)],
            'chems':sorted({m.group(0) for m in CHEM.finditer(q)})[:6],
            'actions':sorted({m.group(1) for m in VERB.finditer(q)})[:6],
            'bound_params':sorted({x for x in binds.get(c['clause'],[]) if x})})
    json.dump({'standard':F.get('standard'),'rows':rows,'counts':{'rows':len(rows)}},
              open(os.path.join(O,'rows.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps({'rows':len(rows)},ensure_ascii=False)); return 0

def util_handoff_state(O, nxt, changed):
    dv=json.load(open(os.path.join(O,'derived.json'),encoding='utf-8')) if os.path.exists(os.path.join(O,'derived.json')) else {}
    st={'out':os.path.abspath(O),'next':nxt,'changed':changed,'derived':dv.get('counts') or {},
        'facts':os.path.abspath(os.path.join(O,'facts.json')),'rows':os.path.abspath(os.path.join(O,'rows.json')),
        'note':'下游直接读 facts/rows/derived；不要转述、不要重读视图'}
    json.dump(st,open(os.path.join(O,'handoff_state.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps({'handoff_state':st['derived'],'next':nxt},ensure_ascii=False)); return 0

def util_cleanup(O):
    import glob
    pats=['02-elements.*.json','_split.json','clauses.split.raw.json','parts/*']
    removed=[]
    for pat in pats:
        for f in glob.glob(os.path.join(O,pat)):
            if os.path.isfile(f): os.remove(f); removed.append(os.path.basename(f))
    print('removed',len(removed),removed[:6]); return 0



def util_clause_preclassify(O, text, shard='0/1'):
    """①-③：模态/类型/表图下沉到脚本，只把需判断的条款留给 LLM；支持分片并发。"""
    import re as _re
    txt = open(text, encoding='utf-8').read()
    lines = txt.splitlines()
    # 章角色映射（可配置）：1 范围/2 引用/3 原理/12-13 其他/附录
    role = {'1':'SCOPE','2':'META','3':'PRIN','12':'META','13':'META'}
    tbl = _re.compile(r'^\s*表\s*[0-9A-Za-z.]+')
    fig = _re.compile(r'^\s*图\s*[0-9A-Za-z.]+')
    note = _re.compile(r'^\s*注\s*[:：]')
    num = _re.compile(r'^\s*(\d{1,3}(?:\.\d{1,2}){0,3})\s*(?=[\u4e00-\u9fa5A-Za-z])')
    MUST = _re.compile(r'应|须'); MUSTNOT = _re.compile(r'不得|不应'); SHOULD = _re.compile(r'宜'); MAY = _re.compile(r'可')
    chapters={m.group(1) for m in _re.finditer(r'(?m)^\s*(\d{1,2})\s+[\u4e00-\u9fa5A-Za-z]', txt)}
    cand, skipped = [], []
    cur = None; buf = []
    def flush():
        nonlocal cur, buf
        if cur:
            q = _re.sub(r'\s+', ' ', ' '.join(buf)).strip()[:200]
            cand.append((cur, q))
        cur, buf = None, []
    for ln in lines:
        if ln.startswith('===== PAGE'): continue
        if tbl.match(ln) or fig.match(ln) or note.match(ln):
            skipped.append(ln.strip()[:20]); continue
        m = num.match(ln)
        if m:
            flush(); cur = m.group(1); buf = [ln]
        elif cur:
            buf.append(ln)
    flush()
    rows = []
    for no, q in cand:
        top = no.split('.')[0]
        if MUSTNOT.search(q): mod = 'MUST_NOT'
        elif MUST.search(q): mod = 'MUST'
        elif SHOULD.search(q): mod = 'SHOULD'
        elif MAY.search(q): mod = 'MAY'
        else: mod = 'INFO'
        typ = 'normative' if top in ('1','4','5','6','7','8','9','10','11') else 'informative'
        # 需 LLM 的：无关键词但属规范性章；或关键词冲突（既是 应 又是 可）
        needs = (mod == 'INFO' and typ == 'normative') or (MUST.search(q) and MAY.search(q))
        # 编号合理性自检：≤2 位主号、段数≤4、不得是表值（三位小数/前导 0）
        # 归一化：OCR 重复前导数字（111.1 → 11.1、88 → 8）
        main, _, rest = no.partition('.')
        if main not in chapters:
            if len(main) > 2 and main[0] == main[1]: main = main[1:]      # 111→11
            elif len(main) == 2 and main[0] == main[1]: main = main[0]   # 55→5
        no = main + ('.' + rest if rest else '')
        if not _re.match(r'^[1-9]\d?(\.\d{1,2}){0,3}$', no) or len(no.split('.')) > 4:
            skipped.append(no); continue
        rows.append({'clause': no, 'page': None, 'quote': q, 'modality': mod, 'type': typ,
                     'section_role': role.get(top, 'BODY'), 'needs_llm': bool(needs)})
    # 分片
    i, n = (int(x) for x in shard.split('/'))
    todo = [r for r in rows if r['needs_llm']]
    part = todo[i::n] if n > 1 else todo
    # 自检：① 无表值污染 ② 关键锚存在 ③ 条数下限
    bad_num=[r['clause'] for r in rows if _re.match(r'^0\d|\d{3,}$', r['clause']) or len(r['clause'].split('.'))>4]
    have={r['clause'] for r in rows}
    key=[k for k in ('1','5','8','9','11') if not any(h==k or h.startswith(k+'.') for h in have)]
    selfcheck={'bad_numbers':bad_num[:5],'missing_chapters':key,'total':len(rows)}
    assert_ok = (not bad_num) and (not key) and len(rows)>=60
    out = {'standard': None, 'shard': shard, 'selfcheck': selfcheck, 'selfcheck_ok': assert_ok, 'total': len(rows),
           'needs_llm': len(todo), 'shard_size': len(part),
           'skipped_non_clause': len(skipped), 'skipped_sample': skipped[:5],
           'clauses': rows, 'llm_todo': part}
    json.dump(out, open(os.path.join(O, f'clause_candidates_{i}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({'total': len(rows), 'needs_llm': len(todo), 'shard': shard, 'shard_size': len(part),
                      'skipped': len(skipped), 'selfcheck': selfcheck, 'ok': assert_ok}, ensure_ascii=False))
    return 0 if assert_ok else 2

def util_clause_merge(O, shards=3, text=''):
    """合并预分类 + LLM 判断 → 01-clauses.json（表/图/注 转为 GAP-DATA 占位）"""
    cand = None; fixes = {}
    for i in range(shards):
        p = os.path.join(O, f'clause_candidates_{i}.json')
        if os.path.exists(p):
            d = json.load(open(p, encoding='utf-8')); cand = cand or d
            for r in d.get('llm_todo') or []: fixes[r['clause']] = r
    import re as _re
    T = open(text, encoding='utf-8').read() if text else ''
    def rederive(no, q):
        if not T: return q
        nq = _re.sub(r'\s+','',q or '')
        if nq and nq in _re.sub(r'\s+','',T): return q
        m = _re.search(r'(?m)^\s*'+_re.escape(no)+r'(?![\d.])', T)
        if not m: return q
        raw = T[m.start():m.start()+320]
        for stop in ('===== PAGE','HJ 84—2016','HJ 84-2016'):
            i = raw.find(stop, 1)
            if i > 0: raw = raw[:i]
        return _re.sub(r'\s+',' ',raw).strip()[:200]
    base = os.path.join(O, 'clause_candidates_0.json')
    if cand is None: print('no candidates'); return 1
    judged = {}
    import glob as _g
    for jf in [os.path.join(O,'clauses.judgments.json')] + sorted(_g.glob(os.path.join(O,'clauses.judgments.part*.json'))):
        if os.path.exists(jf):
            d = json.load(open(jf, encoding='utf-8'))
            for r in (d.get('clauses') or d if isinstance(d, list) else d.get('clauses') or []): judged[r['clause']] = r
    out = []
    seen = {}
    for r in cand['clauses']:
        j = judged.get(r['clause']) or {}
        no = r['clause']
        if no in ('10.0',) or (no == '1' and '表4' in (j.get('heading') or '')):
            continue
        rec = {'clause': no, 'page': j.get('page', r.get('page')),
                    'quote': rederive(no, j.get('quote') or r['quote']), 'modality': j.get('modality') or r['modality'],
                    'type': j.get('type') or r['type'], 'heading': j.get('heading', ''),
                    'section_role': r.get('section_role')}
        # 同号去重：保留正文（page 更大）或非目次
        prev = seen.get(no)
        if prev is None or (rec.get('page') or 0) > (prev.get('page') or 0):
            seen[no] = rec
    out = list(seen.values())
    old={}
    try: old=json.load(open(os.path.join(O,'01-clauses.json'),encoding='utf-8'))
    except Exception: pass
    doc = {'standard_id': old.get('standard_id'), 'standard_slug': old.get('standard_slug'),
           'standard_type': old.get('standard_type'), 'source_fingerprint': old.get('source_fingerprint'),
           'clause_registry': out,
           'gaps': [{'gap_id': f'GAP-DATA-TBL-{i:02d}', 'type': 'GAP-DATA',
                     'description': f'表/图/注未单列条款：{x}', 'pending_class': 'PENDING_DATA'}
                    for i, x in enumerate(cand.get('skipped_sample') or [], 1)]}
    json.dump(doc, open(os.path.join(O, '01-clauses.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({'clauses': len(out), 'llm_fixed': len(judged), 'gaps': len(doc['gaps'])}, ensure_ascii=False)); return 0



def util_sop_graph(O):
    """SOP 图为主产物：procedure 步骤为唯一主干；PROC 要素去重合并；
    reagent/instrument/qc 挂 requires；规则挂 constrains；PERF 挂 justifies。"""
    import collections
    c=json.load(open(os.path.join(O,'01-clauses.json'),encoding='utf-8'))
    e=json.load(open(os.path.join(O,'02-elements.json'),encoding='utf-8'))
    r=json.load(open(os.path.join(O,'03-rules.json'),encoding='utf-8'))
    cmap={str(x['clause']):x for x in c.get('clause_registry') or []}
    cards=collections.defaultdict(list)
    for k in r.get('audit_rule_cards') or []: cards[str(k.get('clause'))].append(k)
    def anchor(cl):
        x=cmap.get(str(cl))
        return {'clause':str(cl),'page':x.get('page'),'quote':x.get('quote')} if x else None
    nodes,edges=[],[]
    pg=e.get('procedure_graph') or {}
    step_clauses=set()
    for pn in pg.get('nodes') or []:
        cl=str(pn.get('clause') or '')
        clset=[x.strip() for x in cl.replace('~','-').split('/') if x.strip()]
        # 区间写法 5.13-5.21 → 取起点锚
        exp=[]
        for x in clset:
            if x.count('-')==1:
                a,b=[t.strip() for t in x.split('-')]
                try:
                    pa,pb=a.split('.'),b.split('.')
                    if pa[0]==pb[0] and len(pa)==len(pb)==2:
                        exp+= [f"{pa[0]}.{i}" for i in range(int(pa[1]),int(pb[1])+1)]
                    else: exp.append(a)
                except Exception: exp.append(a)
            else: exp.append(x)
        clset=exp
        step_clauses|=set(clset)
        crit=[k['rule_id'] for cx in clset for k in cards.get(cx,[]) if k.get('predicate')]
        qual=[k['rule_id'] for cx in clset for k in cards.get(cx,[]) if not k.get('predicate')]
        nodes.append({'node_id':'SOP-'+str(pn['id']),'type':'step','step':pn.get('step'),
                      'clauses':clset,'params':pn.get('params') or [],'done_when':pn.get('done_when'),
                      'criteria':crit,'qualitative':qual,'conditional':bool(pn.get('conditional')),
                      'anchors':[a for a in (anchor(x) for x in clset) if a]})
    # PROC 要素：同 clause 合并且不入图（记录 merged）
    merged=[]
    for el in e.get('elements') or []:
        fam=el.get('family'); cl=str((el.get('anchor') or {}).get('clause'))
        if fam=='PROC':
            if cl in step_clauses:
                for n in nodes:
                    if n['type']=='step' and cl in n['clauses']:
                        n['params']=sorted(set(list(n['params'])+[p.get('raw') or str(p.get('value')) for p in (el.get('parameters') or []) if (p.get('raw') or p.get('value'))]))
                        n.setdefault('merged_from',[]).append(el['element_id']); merged.append(el['element_id'])
            else:
                nodes.append({'node_id':el['element_id'],'type':'step','step':(el.get('statement') or '')[:40],
                              'clauses':[cl],'params':[p.get('raw') or str(p.get('value')) for p in (el.get('parameters') or [])],
                              'criteria':[],'qualitative':[],'anchors':[el.get('anchor')]})
            continue
        typ={'MATL':'reagent','APPA':'instrument','QC':'qc_gate','INTR':'interference','PERF':'justification',
             'RISK':'failure_mode'}.get(fam,'constraint')
        if fam=='CALC': typ='result' if str(cl).startswith('9.1') else 'constraint'
        nodes.append({'node_id':el['element_id'],'type':typ,'family':fam,'statement':(el.get('statement') or '')[:80],
                      'clauses':[cl],'anchors':[el.get('anchor')],
                      'criteria':[k['rule_id'] for k in cards.get(cl,[]) if k.get('predicate')],
                      'usage':'reference_only' if typ=='justification' else 'normative'})
    steps=[n for n in nodes if n['type']=='step']
    # analyte：从任一引文里抓“（F-、Cl-…”这类被测物清单，否则用标准号兜底
    import re as _re2
    analytes=[]
    for x in (c.get('clause_registry') or []):
        q=x.get('quote') or ''
        m=_re2.search(r'[（(]([^）)]*[、][^）)]{4,})[）)]', q)
        if m and _re2.search(r'[-+]', m.group(1)):
            parts=[p.strip() for p in m.group(1).split('、') if p.strip()]
            if len(parts)>=3: analytes=parts; break
    if analytes:
        for i,a in enumerate(analytes,1):
            nodes.append({'node_id':f'AN-{i:02d}','type':'analyte','name':a,'clauses':['1'],'anchors':[anchor('1')] if anchor('1') else []})
    else:
        nm=c.get('standard_id') or (c.get('standard_slug') or '被测物（未命名）')
        nodes.append({'node_id':'AN-01','type':'analyte','name':nm,'clauses':['1'],'anchors':[anchor('1')] if anchor('1') else []})
    an_ids=[n['node_id'] for n in nodes if n['type']=='analyte']
    for st in steps:
        for a in an_ids: edges.append({'from':st['node_id'],'to':a,'type':'determines'})
    # 边
    for ed in pg.get('edges') or []:
        a,b='SOP-'+str(ed.get('from') or ed.get('source')),'SOP-'+str(ed.get('to') or ed.get('target'))
        ids={n['node_id'] for n in nodes}
        if a in ids and b in ids: edges.append({'from':a,'to':b,'type':'precedes'})
    steps=[n for n in nodes if n['type']=='step']
    # uses：步骤文本里出现（5.x）/（6.x）→ 连到对应条款的试剂/仪器
    ent_by_clause={}
    for n in nodes:
        if n['type'] in ('reagent','instrument'):
            for cl in n.get('clauses') or []: ent_by_clause.setdefault(str(cl),[]).append(n['node_id'])
    import re as _re
    for st in steps:
        blob=' '.join(str(x) for x in (st.get('params') or []))+' '+str(st.get('step') or '')
        for cl in (st.get('clauses') or []):
            blob+=' '+(cmap.get(str(cl),{}).get('quote') or '')
        for m in _re.finditer(r'[（(](\d+(?:\.\d+)+)[）)]', blob):
            for tgt in ent_by_clause.get(m.group(1),[]):
                edges.append({'from':st['node_id'],'to':tgt,'type':'uses'})
    # 兼容旧启发式（名称匹配）作为补充
    for n in nodes:
        if n['type'] in ('reagent','instrument'):
            key=(n.get('statement') or '')[:6]
            hit=[x['node_id'] for x in steps if key and any(key in str(p) for p in x['params'])]
            for h in hit: edges.append({'from':h,'to':n['node_id'],'type':'requires'})
        if n['type']=='justification':
            for x in steps:
                edges.append({'from':n['node_id'],'to':x['node_id'],'type':'justifies'})
    # ① 干扰：interferes_with → analyte；eliminated_by → 步骤
    for n in nodes:
        if n['type']=='interference':
            for a in [x for x in nodes if x['type']=='analyte']:
                edges.append({'from':n['node_id'],'to':a['node_id'],'type':'interferes_with'})
            for st in steps:
                if any(str(c).startswith(('4','7')) for c in st.get('clauses') or []):
                    edges.append({'from':n['node_id'],'to':st['node_id'],'type':'eliminated_by'})
    # ② 失效传播：qc_gate → invalidates → 校准/测定步骤
    for n in nodes:
        if n['type']=='qc_gate':
            for st in steps:
                if any(str(c).startswith(('8.2','8.3')) for c in st.get('clauses') or []):
                    edges.append({'from':n['node_id'],'to':st['node_id'],'type':'invalidates'})
            for st in steps:
                if any(str(c).startswith('11') for c in st.get('clauses') or []):
                    edges.append({'from':n['node_id'],'to':st['node_id'],'type':'verifies'})
    # ③ 输出：步骤 computes result；result reports_as → 修约/单位约束
    results=[n for n in nodes if n['type']=='result']
    rounders=[n for n in nodes if n['type']=='constraint' and any(str(c).startswith('9.2') for c in n.get('clauses') or [])]
    for rn in results:
        for st in steps:
            if any(str(c).startswith('9.1') for c in st.get('clauses') or []): edges.append({'from':st['node_id'],'to':rn['node_id'],'type':'computes'})
        for rd in rounders: edges.append({'from':rn['node_id'],'to':rd['node_id'],'type':'reports_as'})
    # ④ 记录：done_when 提到记录 → records 边 + 记录节点
    for st in steps:
        dw=str(st.get('done_when') or '')
        if '记录' in dw:
            rid='REC-'+st['node_id'].replace('SOP-','')
            nodes.append({'node_id':rid,'type':'record','field':dw[:40],'clauses':st.get('clauses') or [],'anchors':st.get('anchors') or []})
            edges.append({'from':st['node_id'],'to':rid,'type':'records'})
    # ⑤ 失效模式：failure_mode → avoids → 步骤（同章或全局）
    for n in nodes:
        if n['type']=='failure_mode':
            for st in steps:
                edges.append({'from':n['node_id'],'to':st['node_id'],'type':'avoids'})
    # ⑥ 试剂来源：statement 里出现（5.x）→ prepared_from
    for n in nodes:
        if n['type']=='reagent':
            blob=str(n.get('statement') or '')
            for m in _re.finditer(r'[（(](5\.\d+(?:\.\d+)*)[）)]', blob):
                for tgt in ent_by_clause.get(m.group(1),[]):
                    edges.append({'from':n['node_id'],'to':tgt,'type':'prepared_from'})
    # 不变量
    errs=[]
    for n in nodes:
        if not n.get('anchors'): errs.append(f"{n['node_id']}: 缺 anchor")
        if n['type']=='interference' and not any(e['from']==n['node_id'] and e['type']=='interferes_with' for e in edges):
            errs.append(f"{n['node_id']}: 干扰节点无 interferes_with")
        if n['type']=='result' and not any(e['from']==n['node_id'] and e['type']=='reports_as' for e in edges):
            errs.append(f"{n['node_id']}: 结果节点无 reports_as")
        if n['type']=='qc_gate' and not any(e['from']==n['node_id'] and e['type'] in ('verifies','invalidates') for e in edges):
            errs.append(f"{n['node_id']}: 质控门无 verifies/invalidates")
        if n['type'] not in ('justification','record','analyte','interference','failure_mode','result') and not (n.get('criteria') or n.get('qualitative')):
            n['no_threshold']=True
    just={n['node_id'] for n in nodes if n['type']=='justification'}
    for n in nodes:
        for rid in n.get('criteria') or []:
            if rid in just: errs.append(f"{rid}: justification 被当判据")
    just_nodes=[n for n in nodes if n['type']=='justification']
    for n in nodes:
        if n['type'] in ('step','reagent','instrument','qc_gate','constraint') and (n.get('criteria') or n.get('qualitative')):
            n['basis']=[{'node_id':j['node_id'],'claim':(j.get('statement') or '')[:40],'anchor':j.get('anchors')} for j in just_nodes]
    counts=dict(collections.Counter(n['type'] for n in nodes))
    doc={'standard':c.get('standard_id'),'nodes':nodes,'edges':edges,'counts':counts,
         'merged_proc_elements':merged,'invariant_errors':errs[:40],'invariant_error_count':len(errs)}
    json.dump(doc,open(os.path.join(O,'sop-graph.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps({'nodes':len(nodes),'edges':len(edges),'types':counts,'merged':len(merged),
                      'invariant_errors':len(errs),'sample':errs[:4]},ensure_ascii=False)); return 0



def util_build_slots(O):
    """把规则卡变成“可填槽位的任务单”：audit_tasks.jsonl + slots.schema.json（人不用读文档）"""
    r=json.load(open(os.path.join(O,'03-rules.json'),encoding='utf-8'))
    g={}
    sp=os.path.join(O,'sop-graph.json')
    if os.path.exists(sp):
        for n in json.load(open(sp,encoding='utf-8')).get('nodes') or []:
            g[n['node_id']]=n.get('basis') or []
    tasks=[]; props={}; i=0
    for k in r.get('audit_rule_cards') or []:
        i+=1
        ct=(k.get('check_targets') or [{}])[0]
        slot='S%03d'%i
        label=ct.get('field') or k.get('rule_id')
        pred=k.get('predicate') or {}
        props[slot]={'label':label,'doc_type':ct.get('doc_type'),'unit':pred.get('unit'),
                     'type':'number' if isinstance(pred.get('value'),(int,float)) else 'string',
                     'match_hints':ct.get('match_hints') or [],'rule_id':k['rule_id']}
        tasks.append({'task_id':'T-%03d'%i,'rule_id':k['rule_id'],'slot':slot,'label':label,
                      'doc_type':ct.get('doc_type'),'match_hints':ct.get('match_hints') or [],
                      'op':pred.get('op'),'value':pred.get('value'),'unit':pred.get('unit'),
                      'qualitative':k.get('qualitative_check'),'on_missing':k.get('on_missing'),
                      'ceiling':k.get('verdict_ceiling') or 'PASS','anchor':k.get('anchor'),
                      'basis':g.get(k['rule_id']) or [],'category':k.get('category')})
    with open(os.path.join(O,'audit_tasks.jsonl'),'w',encoding='utf-8') as f:
        for t in tasks: f.write(json.dumps(t,ensure_ascii=False)+'\n')
    json.dump({'type':'object','properties':props,'required':[]},
              open(os.path.join(O,'slots.schema.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps({'tasks':len(tasks),'slots':len(props)},ensure_ascii=False)); return 0

def util_eval_slots(O, slots_file):
    """按填好的槽位直接出判定，不做“阅读”"""
    def num(x):
        try: return float(x)
        except Exception: return None
    tasks=[json.loads(l) for l in open(os.path.join(O,'audit_tasks.jsonl'),encoding='utf-8') if l.strip()]
    slots=json.load(open(slots_file,encoding='utf-8')) if slots_file and os.path.exists(slots_file) else {}
    out=[]
    for t in tasks:
        v=slots.get(t['slot']); res={'rule_id':t['rule_id'],'slot':t['slot'],'label':t['label']}
        if v is None or v=='':
            res['verdict']='FAIL' if t['on_missing']=='FAIL' else 'UNVERIFIABLE'; res['message']='缺证：未提供 '+str(t['label'])
        elif t.get('op') and t.get('value') is not None:
            a,b=num(v),num(t['value'])
            ok={' >=':a is not None and b is not None and a>=b,'<=':a is not None and b is not None and a<=b,
                '>':a is not None and b is not None and a>b,'<':a is not None and b is not None and a<b,
                '==':str(v)==str(t['value']),
                'in': (v in t['value']) if isinstance(t['value'],list) else (str(v) in str(t['value'])),
                'not_in': (v not in t['value']) if isinstance(t['value'],list) else (str(v) not in str(t['value']))}.get(t['op'],False)
            res['verdict']='PASS' if ok else 'FAIL'; res['message']=f"{t['label']}={v} {t['op']} {t['value']}"
        else:
            res['verdict']='UNVERIFIABLE'; res['message']='定性卡：需人工按三档判断'
        if res['verdict']=='FAIL' and t.get('ceiling')=='NO_FAIL': res['verdict']='CONFLICT_PENDING'
        res['basis']=t.get('basis'); res['anchor']=t.get('anchor')
        out.append(res)
    json.dump(out,open(os.path.join(O,'audit_results.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    import collections; print(json.dumps(dict(collections.Counter(x['verdict'] for x in out)),ensure_ascii=False)); return 0



def util_emit_machine(O):
    """把面向人的 md 全部转成机器可直读的 JSON（md 只是它的 render）"""
    import collections
    ses=json.load(open(os.path.join(O,'ses.json'),encoding='utf-8'))
    dv=json.load(open(os.path.join(O,'derived.json'),encoding='utf-8')) if os.path.exists(os.path.join(O,'derived.json')) else {}
    F=json.load(open(os.path.join(O,'audit_findings.json'),encoding='utf-8')) if os.path.exists(os.path.join(O,'audit_findings.json')) else {}
    cats=dict(sorted(collections.Counter(c['category'] for c in ses.get('audit_rule_cards') or []).items()))
    gaps=[]
    for g in ses.get('gaps') or []:
        gaps.append({'gap_id':g.get('gap_id'),'type':g.get('type'),'pending_class':g.get('pending_class'),
                     'request':g.get('request'),'owner':g.get('owner'),'affected_rules':g.get('affected_rules') or []})
    handoff={'standard':{'id':ses.get('standard_id'),'fingerprint':ses.get('source_fingerprint'),
                         'type':ses.get('standard_type'),'rule_set_id':ses.get('rule_set_id')},
             'counts':dv.get('counts') or {},
             'coverage':dv.get('coverage') or {},
             'categories':cats,
             'deliverables':[{'file':'ses.json','role':'context'},{'file':'audit_tasks.jsonl','role':'tasks'},
                             {'file':'slots.schema.json','role':'slot schema'},{'file':'sop-graph.json','role':'ontology+basis'},
                             {'file':'audit_results.json','role':'verdicts'},{'file':'lab_requests.json','role':'pending'}],
             'usage':{'order':['audit_tasks.jsonl','report_slots.json','audit_results.json'],
                      'verdicts':['PASS','FAIL','NOT_APPLICABLE','UNVERIFIABLE','CONFLICT_PENDING'],
                      'message_format':'哪里不合规 + 缺什么 + 依据(basis)'},
             'gaps':gaps,
             'quality':{'anchors':F.get('anchors'),'predicate_not_in_text':F.get('predicate_not_in_text')},
             'risks':['表/图/公式不可辨区仅出定性卡','孤立实体待补 prepared_from','引用未上传']}
    json.dump(handoff,open(os.path.join(O,'handoff.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    lab=[{'gap_id':g['gap_id'],'pending_class':g.get('pending_class'),'request':g.get('request'),
          'owner':g.get('owner'),'affected_rules':g.get('affected_rules') or []}
         for g in gaps if g.get('pending_class')!='REGISTERED_CONFLICT']
    json.dump({'standard':ses.get('standard_id'),'items':lab},open(os.path.join(O,'lab_requests.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    ar=json.load(open(os.path.join(O,'audit_result.json'),encoding='utf-8')) if os.path.exists(os.path.join(O,'audit_result.json')) else {}
    ar['findings']={'anchors':F.get('anchors'),'predicate_not_in_text':F.get('predicate_not_in_text'),
                    'ids':F.get('ids'),'gaps':F.get('gaps')}
    json.dump(ar,open(os.path.join(O,'audit_record.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps({'handoff.json':len(gaps),'lab_requests.json':len(lab),'audit_record.json':1},ensure_ascii=False)); return 0



def util_build_spans(O, text):
    """为每条引文预计算切片（字符区间+sha），供直接引用，不再临时检索。"""
    import re as _re
    T=open(text,encoding='utf-8').read()
    sha=__import__('hashlib').sha256(T.encode()).hexdigest()[:12]
    def nmap(t):
        out=[];idx=[]
        for i,ch in enumerate(t):
            if ch.isspace(): continue
            out.append(ch);idx.append(i)
        return ''.join(out),idx
    NT,NI=nmap(T)
    c=json.load(open(os.path.join(O,'01-clauses.json'),encoding='utf-8'))
    spans=[];miss=0
    for x in c.get('clause_registry') or []:
        q=x.get('quote') or ''
        nq,_=nmap(q)
        k=NT.find(nq) if nq else -1
        if k<0: miss+=1; spans.append({'clause':x['clause'],'status':'MISS'}); continue
        st,en=NI[k],NI[k+len(nq)-1]+1
        spans.append({'clause':str(x['clause']),'page':x.get('page'),'start':st,'end':en,
                      'sha':sha,'text':T[st:en],'status':'OK'})
    json.dump({'sha':sha,'text':text,'spans':spans},open(os.path.join(O,'spans.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    ref={x['clause']:f"{sha}:{x['start']}-{x['end']}" for x in spans if x.get('status')=='OK'}
    json.dump({'standard_sha':sha,'by_clause':ref},open(os.path.join(O,'span_refs.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    # 写回 store
    import sqlite3,glob
    dbs=glob.glob(os.path.join(O,'store-*.db'))
    if dbs:
        con=sqlite3.connect(dbs[0]); con.execute('CREATE TABLE IF NOT EXISTS quote_spans(clause TEXT PRIMARY KEY,start INT,end INT,sha TEXT,page INT)')
        for s2 in spans:
            if s2.get('status')=='OK': con.execute('INSERT OR REPLACE INTO quote_spans VALUES (?,?,?,?,?)',(s2['clause'],s2['start'],s2['end'],s2['sha'],s2.get('page')))
        con.commit(); con.close()
    print(json.dumps({'spans':len(spans),'miss':miss,'db':bool(dbs)},ensure_ascii=False)); return 0



def util_backfill_spans(O):
    """给 02/03 的 anchor 回填 quote_span（引用切片库，保留 quote 作文本缓存）"""
    import glob
    sp=os.path.join(O,'span_refs.json')
    if not os.path.exists(sp):
        print(json.dumps({'error':'span_refs.json 缺失，先跑 build_spans'},ensure_ascii=False)); return 2
    ref=json.load(open(sp,encoding='utf-8')); by=ref['by_clause']; sha=ref['standard_sha']
    n2=n3=0
    for name,key,out in (('02-elements.json','elements','02-elements.json'),('03-rules.json','audit_rule_cards','03-rules.json')):
        p=os.path.join(O,name)
        if not os.path.exists(p): continue
        d=json.load(open(p,encoding='utf-8'))
        for x in d.get(key) or []:
            cl=str((x.get('anchor') or {}).get('clause') or x.get('clause'))
            sid=by.get(cl)
            if not sid: continue
            a=x.setdefault('anchor',{})
            st=sid.split(':')[1].split('-')
            a['quote_span']={'span_id':sid,'sha':sha,'start':int(st[0]),'end':int(st[1])}
            if name.startswith('02'): n2+=1
            else: n3+=1
        json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps({'elements_with_span':n2,'rules_with_span':n3,'sha':sha},ensure_ascii=False)); return 0



def util_load_library(O, lib='library'):
    """一次抽取 → 两个库：结构库(不含原文) + 切片库(只存原文)"""
    import sqlite3, datetime
    os.makedirs(lib, exist_ok=True)
    ses=json.load(open(os.path.join(O,'ses.json'),encoding='utf-8'))
    sid=ses.get('standard_id') or ses.get('standard_slug') or 'UNKNOWN'
    st=sqlite3.connect(os.path.join(lib,'standards.db'))
    st.executescript("""
CREATE TABLE IF NOT EXISTS standards(standard_id TEXT PRIMARY KEY, fingerprint TEXT, rule_set_id TEXT, counts TEXT, loaded_at TEXT);
CREATE TABLE IF NOT EXISTS rules(standard_id TEXT, rule_id TEXT, category TEXT, clause TEXT, on_missing TEXT, ceiling TEXT, payload TEXT, PRIMARY KEY(standard_id,rule_id));
CREATE TABLE IF NOT EXISTS tasks(standard_id TEXT, task_id TEXT, slot TEXT, label TEXT, doc_type TEXT, payload TEXT, PRIMARY KEY(standard_id,task_id));
CREATE TABLE IF NOT EXISTS gaps(standard_id TEXT, gap_id TEXT, type TEXT, pending_class TEXT, request TEXT, payload TEXT, PRIMARY KEY(standard_id,gap_id));
CREATE TABLE IF NOT EXISTS span_refs(standard_id TEXT, clause TEXT, span_id TEXT, PRIMARY KEY(standard_id,clause));
CREATE TABLE IF NOT EXISTS findings(standard_id TEXT, payload TEXT);""")
    st.execute('INSERT OR REPLACE INTO standards(standard_id,fingerprint,rule_set_id,counts,loaded_at) VALUES (?,?,?,?,?)',
               (sid,json.dumps(ses.get('source_fingerprint'),ensure_ascii=False),ses.get('rule_set_id'),
                json.dumps(ses.get('counts') or {},ensure_ascii=False),datetime.datetime.now().isoformat(timespec='seconds')))
    for k in ses.get('audit_rule_cards') or []:
        st.execute('INSERT OR REPLACE INTO rules VALUES (?,?,?,?,?,?,?)',
                   (sid,k['rule_id'],k.get('category'),str(k.get('clause')),k.get('on_missing'),k.get('verdict_ceiling'),json.dumps(k,ensure_ascii=False)))
    for g in ses.get('gaps') or []:
        st.execute('INSERT OR REPLACE INTO gaps VALUES (?,?,?,?,?,?)',
                   (sid,g.get('gap_id'),g.get('type'),g.get('pending_class'),g.get('request'),json.dumps(g,ensure_ascii=False)))
    if os.path.exists(os.path.join(O,'audit_tasks.jsonl')):
        for line in open(os.path.join(O,'audit_tasks.jsonl'),encoding='utf-8'):
            if not line.strip(): continue
            t=json.loads(line); st.execute('INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?)',
                (sid,t['task_id'],t['slot'],t['label'],t.get('doc_type'),json.dumps(t,ensure_ascii=False)))
    nspan=0
    if os.path.exists(os.path.join(O,'span_refs.json')):
        ref=json.load(open(os.path.join(O,'span_refs.json'),encoding='utf-8'))
        for cl,sp in (ref.get('by_clause') or {}).items():
            st.execute('INSERT OR REPLACE INTO span_refs VALUES (?,?,?)',(sid,cl,sp)); nspan+=1
        sp_db=sqlite3.connect(os.path.join(lib,'spans.db'))
        sp_db.executescript('CREATE TABLE IF NOT EXISTS spans(span_id TEXT PRIMARY KEY, standard_sha TEXT, clause TEXT, page INT, start INT, "end" INT, text TEXT); CREATE INDEX IF NOT EXISTS idx_clause ON spans(standard_sha, clause);')
        for x in json.load(open(os.path.join(O,'spans.json'),encoding='utf-8')).get('spans') or []:
            if x.get('status')!='OK': continue
            sp_db.execute('INSERT OR REPLACE INTO spans VALUES (?,?,?,?,?,?,?)',
                          (f"{x['sha']}:{x['start']}-{x['end']}",x['sha'],x['clause'],x.get('page'),x['start'],x['end'],x['text']))
        sp_db.commit(); sp_db.close()
    if os.path.exists(os.path.join(O,'audit_findings.json')):
        st.execute('INSERT INTO findings VALUES (?,?)',(sid,open(os.path.join(O,'audit_findings.json'),encoding='utf-8').read()))
    st.commit(); st.close()
    print(json.dumps({'standard_id':sid,'rules':len(ses.get('audit_rule_cards') or []),'span_refs':nspan,'lib':lib},ensure_ascii=False)); return 0



def _trail(O, rec):
    with open(os.path.join(O,'trail.jsonl'),'a',encoding='utf-8') as f:
        f.write(json.dumps(rec,ensure_ascii=False)+'\n')

def util_trail(O, step, exit_code, outputs=''):
    import datetime
    _trail(O, {'step':step,'exit':int(exit_code),'outputs':[x for x in outputs.split(',') if x],
               'at':datetime.datetime.now().isoformat(timespec='seconds')})
    print(json.dumps({'trail':step,'exit':exit_code},ensure_ascii=False)); return 0

def util_check(O, node):
    C=CONTRACTS['contracts'][node]
    print(f'== MUST RUN ({node})')
    for i,st in enumerate(C['steps'],1):
        if st['run']=='llm':
            print(f'{i}. [llm] {st.get("call")} → 产出 {st.get("schema")}；判据：schema 校验通过')
        else:
            print(f'{i}. [{st["run"]}] {st.get("cmd","")}')
    print('== 完成后必须运行：run_contract.py --util verify --node '+node)
    return 0

def util_verify(O, node):
    import datetime, glob
    tp=os.path.join(O,'trail.jsonl')
    if not os.path.exists(tp):
        print(json.dumps({'node':node,'status':'NO_TRAIL','hint':'未发现 trail.jsonl：视为未执行'},ensure_ascii=False)); return 2
    recs=[json.loads(l) for l in open(tp,encoding='utf-8') if l.strip()]
    C=CONTRACTS['contracts'][node]
    need=[st.get('cmd','').split('--util ')[-1].split()[0] if '--util' in st.get('cmd','') else st['run'] for st in C['steps'] if st['run']!='llm']
    done={r['step'] for r in recs if r.get('exit')==0}
    missing=[n for n in need if n not in done and n not in ('script','gate')]
    ok=not missing
    _trail(O,{'step':'verify','node':node,'pass':ok,'missing':missing,'at':datetime.datetime.now().isoformat(timespec='seconds')})
    print(json.dumps({'node':node,'verify':'PASS' if ok else 'FAIL','missing':missing},ensure_ascii=False)); return 0 if ok else 1

def util_split_dirs(O):
    import shutil
    M=os.path.join(O,'machine'); H=os.path.join(O,'human')
    os.makedirs(M,exist_ok=True); os.makedirs(H,exist_ok=True)
    json_ext=('.json','.jsonl'); human_ext=('.md','.html')
    nm=nh=0
    for f in os.listdir(O):
        p=os.path.join(O,f)
        if not os.path.isfile(p): continue
        if f.endswith(json_ext): shutil.copy2(p,os.path.join(M,f)); nm+=1
        elif f.endswith(human_ext): shutil.copy2(p,os.path.join(H,f)); nh+=1
    print(json.dumps({'machine':nm,'human':nh},ensure_ascii=False)); return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--node', default=''); ap.add_argument('--out', required=True)
    ap.add_argument('--text', default=''); ap.add_argument('--pdf', default=''); ap.add_argument('--skill', default='')
    ap.add_argument('--util', default=''); ap.add_argument('--next', default=''); ap.add_argument('--changed', action='append', default=[])
    ap.add_argument('--shard', default='0/1'); ap.add_argument('--shards', type=int, default=3)
    ap.add_argument('--slots', default='')
    ap.add_argument('--step', default=''); ap.add_argument('--exit', dest='exit_code', type=int, default=0)
    ap.add_argument('--outputs', default='')
    a = ap.parse_args()
    skill = a.skill or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if a.util == 'fact_rows': return util_fact_rows(os.path.abspath(a.out))
    if a.util == 'handoff_state': return util_handoff_state(os.path.abspath(a.out), a.next, a.changed)
    if a.util == 'cleanup_intermediates': return util_cleanup(os.path.abspath(a.out))
    if a.util == 'clause_preclassify': return util_clause_preclassify(os.path.abspath(a.out), a.text, a.shard)
    if a.util == 'clause_merge': return util_clause_merge(os.path.abspath(a.out), a.shards, a.text)
    if a.util == 'sop_graph': return util_sop_graph(os.path.abspath(a.out))
    if a.util == 'build_slots': return util_build_slots(os.path.abspath(a.out))
    if a.util == 'eval_slots': return util_eval_slots(os.path.abspath(a.out), a.slots)
    if a.util == 'emit_machine': return util_emit_machine(os.path.abspath(a.out))
    if a.util == 'build_spans': return util_build_spans(os.path.abspath(a.out), a.text)
    if a.util == 'load_library': return util_load_library(os.path.abspath(a.out))
    if a.util == 'trail': return util_trail(os.path.abspath(a.out), a.step, a.exit_code, a.outputs)
    if a.util == 'check': return util_check(os.path.abspath(a.out), a.node)
    if a.util == 'verify': return util_verify(os.path.abspath(a.out), a.node)
    if a.util == 'split_dirs': return util_split_dirs(os.path.abspath(a.out))
    if a.util == 'backfill_spans': return util_backfill_spans(os.path.abspath(a.out))
    if not a.node:
        print('need --node or --util', file=sys.stderr); return 2
    c = CONTRACTS['contracts'][a.node]
    ctx = {'out': os.path.abspath(a.out), 'text': a.text, 'pdf': a.pdf, 'skill': skill}
    for i, st in enumerate(c['steps'], 1):
        run = st['run']
        if run == 'llm':
            out_json = os.path.join(ctx['out'], st['call'] + '.json')
            sch = CONTRACTS['schemas'].get(st.get('schema') or '')
            sch_path = ''
            if os.path.exists(out_json) and (sch or os.path.exists(sch_path)):
                schv = sch if sch else json.load(open(sch_path, encoding='utf-8'))
                errs = vcheck(schv, json.load(open(out_json, encoding='utf-8')))
                if errs:
                    print(json.dumps({'step': i, 'status': 'SCHEMA_FAIL', 'errors': errs[:8]}, ensure_ascii=False))
                    return 1
                print(json.dumps({'step': i, 'status': 'VALIDATED', 'file': out_json}, ensure_ascii=False))
                continue
            print(json.dumps({'step': i, 'run': 'llm', 'call': st['call'], 'schema': st.get('schema'),
                              'chunk': st.get('chunk'), 'max_items': st.get('max_items'),
                              'instruction': st.get('instruction'), 'status': 'AWAITING_LLM'}, ensure_ascii=False))
            return 0
        cmd = st['cmd'].format(**ctx)
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        ok = r.returncode == 0
        print(f"[{i}] {run} exit={r.returncode} {cmd[:80]}")
        if not ok:
            print(r.stdout[-500:]); print(r.stderr[-500:]); return 1
    print('CONTRACT: PASS')
    return 0

if __name__ == '__main__':
    sys.exit(main())
