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
  "clauses": {
    "inputs": [
      "{out}/standards/*"
    ],
    "steps": [
      {
        "run": "script",
        "cmd": "python3 toolchain/run.py std.extract_standard --out {out} --text \"{text}\" --standard \"{standard}\" --node clauses"
      },
      {
        "run": "script",
        "cmd": "python3 toolchain/run.py std.check_cross_clause --out {out} --text \"{text}\" --node clauses"
      },
      {
        "run": "gate",
        "cmd": "python3 toolchain/run.py std.run_contract --util verify --out {out} --node clauses"
      }
    ],
    "id": "clauses"
  },
  "elements": {
   "inputs": ["{out}/01-clauses.json"],
   "steps": [
    {"run": "script", "cmd": "python3 toolchain/run.py std.rows_split --out {out} --size 20"},
    {"run": "llm", "call": "elements.judge", "chunk": "by_slice", "max_items": 20,
     "instruction": "逐片回填/判定要素族与锚；只产出判定价，不改整份"},
    {"run": "script", "cmd": "python3 toolchain/run.py std.merge_judged --out {out}"},
    {"run": "gate", "cmd": "python3 toolchain/run.py std.run_contract --util verify --out {out} --node elements"}
   ],
   "id": "elements"
  },
  "rules": {
   "inputs": ["{out}/01-clauses.json", "{out}/02-elements.json"],
   "steps": [
    {"run": "llm", "call": "rules.judge", "chunk": "by_slice", "max_items": 20,
     "instruction": "逐片给 category/predicate/on_missing/check_targets"},
    {"run": "script", "cmd": "python3 toolchain/run.py std.merge_judged --out {out}"},
    {"run": "gate", "cmd": "python3 toolchain/run.py std.run_contract --util verify --out {out} --node rules"}
   ],
   "id": "rules"
  },
  "sop": {
    "inputs": [
      "{out}/03-rules.json"
    ],
    "steps": [
      {
        "run": "script",
        "cmd": "python3 toolchain/run.py std.run_contract --util sop_graph --out {out} --node sop"
      },
      {
        "run": "script",
        "cmd": "python3 toolchain/run.py std.run_contract --util load_library --out {out} --node sop"
      },
      {
        "run": "gate",
        "cmd": "python3 toolchain/run.py std.run_contract --util verify --out {out} --node sop"
      }
    ],
    "id": "sop"
  },
  "toolchain": {
    "inputs": [],
    "steps": [
      {
        "run": "script",
        "cmd": "python3 toolchain/which.py"
      },
      {
        "run": "gate",
        "cmd": "python3 toolchain/run.py std.run_contract --util verify --out {out} --node toolchain"
      }
    ],
    "id": "toolchain"
  },
  "audit": {
    "inputs": [
      "{out}/02-elements.json",
      "{out}/03-rules.json"
    ],
    "steps": [
      {
        "run": "llm",
        "call": "audit.judge",
        "max_items": 5,
        "instruction": "只读 5 条抽样，逐条判 B/D/W；最后给 VERDICT"
      },
      {
        "run": "gate",
        "cmd": "python3 toolchain/run.py std.run_contract --util verify --out {out} --node audit"
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
        "instruction": "只改被点名条目，revision_log 加一行"
      },
      {
        "run": "gate",
        "cmd": "python3 toolchain/run.py std.run_contract --util verify --out {out} --node fix"
      }
    ],
    "id": "fix"
  },
  "handoff": {
    "inputs": [
      "{out}/ses.json"
    ],
    "steps": [
      {
        "run": "script",
        "cmd": "python3 toolchain/run.py std.run_contract --util handoff_state --out {out} --node handoff"
      },
      {
        "run": "llm",
        "call": "handoff.model",
        "instruction": "只写带占位符的结论段，禁止裸数字"
      },
      {
        "run": "script",
        "cmd": "python3 toolchain/run.py std.render_handoff --out {out} --node handoff"
      },
      {
        "run": "gate",
        "cmd": "python3 toolchain/run.py std.run_contract --util verify --out {out} --node handoff"
      }
    ],
    "id": "handoff"
  },
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
    toc = _re.compile(r'^\s*#*\s*(?:\d{1,3}(?:\.\d{1,2})*|表\s?[0-9]{1,2}|附录\s?[A-Z])[^\n]{0,70}(?:\.{3,}|…{2,}|·{3,})\s*\d+\s*$')
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
        if toc.match(ln):                   # 目录行：只取条款号当章标记，正文不取这行
            m2 = num.match(ln)
            if m2: flush(); cur = m2.group(1); buf = []
            continue
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
    # 章节完整性按「本文实际最大章」判断，不假定 HJ84 的 11 章结构（标准各自章数不同）
    _tops=sorted({int(h.split('.')[0]) for h in have if h.split('.')[0].isdigit()})
    _max=_tops[-1] if _tops else 0
    _expect=[str(i) for i in range(1,_max+1)]
    key=[k for k in _expect if not any(h==k or h.startswith(k+'.') for h in have)]
    # 必备锚：第 1 章（适用范围）与结果/质控所在章（有则必到）
    key=[k for k in key if k=='1' or k in ('5','8','9')] if _max>=9 else [k for k in key if k=='1']
    selfcheck={'bad_numbers':bad_num[:5],'missing_chapters':key,'chapters_found':_tops,
               'total':len(rows),'min_expected':30}
    assert_ok = (not bad_num) and (not key) and len(rows)>=20
    out = {'standard': None, 'shard': shard, 'selfcheck': selfcheck, 'selfcheck_ok': assert_ok, 'total': len(rows),
           'needs_llm': len(todo), 'shard_size': len(part),
           'skipped_non_clause': len(skipped), 'skipped_sample': skipped[:5],
           'clauses': rows, 'llm_todo': part}
    json.dump(out, open(os.path.join(O, f'clause_candidates_{i}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({'total': len(rows), 'needs_llm': len(todo), 'shard': shard, 'shard_size': len(part),
                      'skipped': len(skipped), 'selfcheck': selfcheck, 'ok': assert_ok}, ensure_ascii=False))
    return 0 if assert_ok else 2

def util_clause_merge(O, shards=3, text='', standard=''):
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
    if not doc.get('standard_id'):
        doc['standard_id']=(standard or os.path.basename(os.path.dirname(O.rstrip('/'))))
    json.dump(doc, open(os.path.join(O, '01-clauses.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({'clauses': len(out), 'llm_fixed': len(judged), 'gaps': len(doc['gaps'])}, ensure_ascii=False)); return 0



def util_sop_graph(O):
    """SOP 图为主产物：procedure 步骤为唯一主干；PROC 要素去重合并；
    reagent/instrument/qc 挂 requires；规则挂 constrains；PERF 挂 justifies。"""
    import collections
    c=json.load(open(os.path.join(O,'01-clauses.json'),encoding='utf-8'))
    # 立刻快照：函数体内多处用 c 作循环变量，读到时 c 已被遮蔽（真实 bug，靠下面的断言才暴露）
    _STD=(c.get('standard_id') or '').strip()
    e=json.load(open(os.path.join(O,'02-elements.json'),encoding='utf-8'))
    r=json.load(open(os.path.join(O,'03-rules.json'),encoding='utf-8'))
    cmap={str(x['clause']):x for x in c.get('clause_registry') or []}
    cards=collections.defaultdict(list)
    for k in r.get('audit_rule_cards') or []: cards[str(k.get('clause'))].append(k)
    def anchor(cl):
        k=str(cl); x=cmap.get(k)
        if not x:                                   # 章级锚回落到第一条子条款（9 ← 9.1）
            for kk in sorted(cmap):
                if kk.startswith(k+'.'):
                    x=cmap[kk]; k=kk; break
        return {'clause':k,'page':x.get('page'),'quote':x.get('quote')} if x else None
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
    # ② 失效传播：qc_gate → invalidates → 测定/计算步骤；verifies → 质控步骤
    # 章号不写死（不同标准章节不同）：优先 8.x/11.x（HJ84/HJ671），回落到 7.x/9.x/10.x（HJ535/HJ636）
    def _ch(st): return [str(c).split('.')[0] for c in (st.get('clauses') or [])]
    # 只挂「测定章」的步骤：优先 8（HJ84/671），无则 9（HJ636），再则 7（HJ535）
    # 不挂样品接收/前处理，避免"空白超限把收样也作废"这类语义错误
    _meas_ch = next((ch for ch in ('8','9','7') if any(ch in _ch(st) for st in steps)), None)
    meas=[st for st in steps if _meas_ch in _ch(st)][:3]
    for n in nodes:
        if n['type']=='qc_gate' and meas:
            for st in meas:
                edges.append({'from':n['node_id'],'to':st['node_id'],'type':'invalidates'})
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
    # ⑦ 兜底挂载：没被任何节点接住的规则，按（条款 + 类型偏好）挂到唯一节点；
    #    C8 记录类在该条款无 record 节点时，派生一个 record 节点并接 records 边。
    #    条款本身没有任何节点 → 才算真缺口（留空，由 graph_gaps 登记）。
    CAT2TYPE={'C1':['constraint','step','failure_mode'],'C2':['step'],'C3':['instrument'],'C4':['reagent'],
              'C5':['step'],'C6':['result','constraint'],'C7':['qc_gate'],'C8':['record']}
    attached={rid for n in nodes for rid in (n.get('criteria') or [])+(n.get('qualitative') or [])}
    by_clause=collections.defaultdict(list)
    for n in nodes:
        if n['type'] in ('justification','analyte'): continue
        for cl in n.get('clauses') or []: by_clause[str(cl)].append(n)
    rec_by_clause={}
    for n in nodes:
        if n['type']=='record':
            for cl in n.get('clauses') or []: rec_by_clause.setdefault(str(cl),n)
    _ekey={(e['from'],e['to'],e['type']) for e in edges}
    unattached=[]
    for k in r.get('audit_rule_cards') or []:
        rid=k['rule_id']
        if rid in attached: continue
        cl=str(k.get('clause')); cat=k.get('category')
        cand=by_clause.get(cl) or []
        host=None
        for t in CAT2TYPE.get(cat,[]):
            host=next((n for n in cand if n['type']==t),None)
            if host: break
        if host is None: host=cand[0] if cand else None
        if host is None:
            unattached.append(rid); continue
        target=host
        if cat=='C8' and host['type']!='record':
            target=rec_by_clause.get(cl)
            if target is None:
                target={'node_id':'REC-'+cl.replace('.','_'),'type':'record',
                        'field':(k.get('title') or '')[:40],'clauses':[cl],
                        'anchors':host.get('anchors') or [],'criteria':[],'qualitative':[]}
                nodes.append(target); rec_by_clause[cl]=target; by_clause[cl].append(target)
            if (host['node_id'],target['node_id'],'records') not in _ekey:
                edges.append({'from':host['node_id'],'to':target['node_id'],'type':'records'})
                _ekey.add((host['node_id'],target['node_id'],'records'))
        target.setdefault('criteria',[]); target.setdefault('qualitative',[])
        (target['criteria'] if k.get('predicate') else target['qualitative']).append(rid)
        attached.add(rid)
    # ⑧ 失效传播打通：原链断在步骤上（qc_gate→step），无法回答「哪批结果作废」
    res_ids = [n['node_id'] for n in nodes if n['type'] == 'result']
    def _add_edge(a, b, t):
        if (a, b, t) not in _ekey:
            edges.append({'from': a, 'to': b, 'type': t}); _ekey.add((a, b, t))
    for n in nodes:
        if n['type'] == 'qc_gate':
            for r in res_ids:
                _add_edge(n['node_id'], r, 'invalidates')      # 质控门 → 结果
    for st in steps:
        if any(str(c).startswith('8.') for c in (st.get('clauses') or [])):
            for r in res_ids:
                _add_edge(st['node_id'], r, 'computes')        # 测定步骤 → 结果
    _calib = [x for x in steps if any(str(c) == '8.2' for c in (x.get('clauses') or []))]
    _meas = [x for x in steps if any(str(c) == '8.3' for c in (x.get('clauses') or []))]
    for c in _calib:
        for m in _meas:
            _add_edge(m['node_id'], c['node_id'], 'requires')  # 校准不成立则测定不成立

    # ⑨ 边带锚与条件：只给会改变判定的边加，条件不确定的一律不编
    _COND = {'invalidates': '触发节点不通过时，目标节点作废'}
    _anc = {n['node_id']: ((n.get('anchors') or [None])[0]) for n in nodes}
    for e in edges:
        t = e.get('type')
        if t in ('uses', 'requires', 'records', 'invalidates', 'precedes', 'computes', 'reports_as'):
            a = _anc.get(e['from']) or {}
            if a.get('clause') and 'anchor' not in e:
                e['anchor'] = {'clause': a.get('clause'), 'page': a.get('page')}
        if t in _COND and 'condition' not in e:
            e['condition'] = _COND[t]

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
    # 边去重：同一 (from,to,type) 只留一条，保证图与库计数一致
    _seen_edges=set(); _dedup=[]
    for e in edges:
        k=(e['from'],e['to'],e['type'])
        if k in _seen_edges: continue
        _seen_edges.add(k); _dedup.append(e)
    edges=_dedup
    counts=dict(collections.Counter(n['type'] for n in nodes))
    # 断言：standard 必填。缺失就报错退出，绝不静默写 null——
    # 图靠 node_id 走才不会坏，但 YAML/看板/前端按 standard 显示时会空白，
    # 且这类缺失一旦静默，后续所有消费方都在用一张"没有身份"的图。
    if not _STD:
        _hint = ('01-clauses.json 缺 standard_id。'
                 '若是手写或旧版产物，请先补 standard_id（或重跑 clauses 节点）再建图。')
        print(json.dumps({'error': 'STANDARD_ID_MISSING', 'detail': _hint,
                          'file': '01-clauses.json', 'nodes': len(nodes), 'edges': len(edges)},
                         ensure_ascii=False))
        return 2
    doc={'standard':_STD,'nodes':nodes,'edges':edges,'counts':counts,
         'merged_proc_elements':merged,'unattached_rules':unattached,
         'rule_nodes':len(attached),
         'invariant_errors':errs[:40],'invariant_error_count':len(errs)}
    json.dump(doc,open(os.path.join(O,'sop-graph.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps({'nodes':len(nodes),'edges':len(edges),'types':counts,'merged':len(merged),
                      'rule_nodes':len(attached),'unattached':len(unattached),
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

def _coverage_gate(O, t, res):
    """批级覆盖率闸门：按标准给出的比例判，不按"越多越好"。
    HJ 84-2016 11.4：每批次(≤20个)至少 10% 平行双样，<10 个时至少 1 个。
    HJ 84-2016 11.5：每批次(≤20个)至少 1 个加标回收率。
    只做「PASS → UNVERIFIABLE」的升级，不降级、不造 FAIL。
    """
    import json as _j, math as _m, os as _o
    p = _o.path.join(O, 'machine', 'qc_coverage.json')
    if not _o.path.exists(p):
        return
    try:
        cov = _j.load(open(p, encoding='utf-8'))
    except Exception:
        return
    total = cov.get('total_samples') or 0
    label = str(t.get('label') or '')
    need = None; have = None; kind = None
    if '平行双样' in label:
        kind = 'parallel'
        need = max(1, _m.ceil(0.1 * total)) if total else 1
        have = (cov.get('parallel') or {}).get('count') or 0
    elif '加标回收率' in label:
        kind = 'spike'
        need = 1
        have = (cov.get('spike') or {}).get('count') or 0
    if kind is None:
        return
    if have < need:
        prev = res.get('verdict')
        res['verdict'] = 'UNVERIFIABLE'
        res['message'] = (res.get('message') or '') +             f"｜覆盖率不足：{kind} {have}/{total}，本批({total} 个样品)按 11.x 至少需 {need} 个"
        res['coverage'] = {'kind': kind, 'have': have, 'need': need, 'total': total,
                           'untested': (cov.get('untested') or {}).get(kind, [])}
        if prev == 'PASS':
            res['downgraded'] = 'coverage_insufficient'
    # 批次上限：每批次 ≤20 个样品
    if total > 20 and res.get('verdict') == 'PASS':
        # 11.1/11.4/11.5 都限定「每批次（≤20个）」；超批未分批，则整批质控不成立
        res['verdict'] = 'UNVERIFIABLE'
        res['message'] = (res.get('message') or '') + f"｜批次超限：{total} 个样品超过每批 20 个上限，需分批分别质控"
        res['batch_overflow'] = {'total': total, 'limit': 20,
                                 'note': '单批超过 20 个样品，需按键分批分别质控'}


def util_eval_slots(O, slots_file):
    """按填好的槽位直接出判定，不做“阅读”"""
    import re
    def num(x):
        try: return float(x)
        except Exception: return None
    tasks=[json.loads(l) for l in open(os.path.join(O,'audit_tasks.jsonl'),encoding='utf-8') if l.strip()]
    slots=json.load(open(slots_file,encoding='utf-8')) if slots_file and os.path.exists(slots_file) else {}
    out=[]
    for t in tasks:
        v=slots.get(t['slot']); res={'rule_id':t['rule_id'],'slot':t['slot'],'label':t['label']}
        if v is None or v=='':
            # 缺证≠不合格（红线）：只有 C8 记录与报告类，「没有记录」本身即不符合；
            # C1–C7 缺证一律 UNVERIFIABLE，不得因 on_missing=FAIL 判成不合格。
            if t.get('on_missing')=='FAIL' and str(t.get('category'))=='C8':
                res['verdict']='FAIL'; res['message']='缺证（C8 记录类，缺失即不符合）：未提供 '+str(t['label'])
            else:
                res['verdict']='UNVERIFIABLE'; res['message']='缺证：未提供 '+str(t['label'])
                if t.get('on_missing')=='FAIL':
                    res['on_missing_downgraded']=True
        elif t.get('op') and t.get('value') is not None:
            a,b=num(v),num(t['value'])
            ok={"exists":(v not in (None,'',[])), "regex":(re.search(str(t['value']),str(v)) is not None) if str(t['value']) else False,
                '>=':a is not None and b is not None and a>=b,'<=':a is not None and b is not None and a<=b,
                '>':a is not None and b is not None and a>b,'<':a is not None and b is not None and a<b,
                '==':(num(v)==num(t['value'])) if (num(v) is not None and num(t['value']) is not None) else (str(v)==str(t['value'])),
                'in': (v in t['value']) if isinstance(t['value'],list) else (str(v) in str(t['value'])),
                'between': (a is not None and isinstance(t['value'],list) and len(t['value'])==2
                            and t['value'][0] <= a <= t['value'][1]),
                'range': (a is not None and isinstance(t['value'],list) and len(t['value'])==2
                          and t['value'][0] <= a <= t['value'][1]),
                'not_in': (v not in t['value']) if isinstance(t['value'],list) else (str(v) not in str(t['value']))}.get(t['op'], None)
            if not ok and t['op']=='in' and isinstance(t['value'],list):
                partial=[x for x in t['value'] if str(v) and str(v) in str(x)]
                if partial:
                    res['verdict']='UNVERIFIABLE'
                    res['message']=f"{t['label']}={v} 表述过宽，可落入 {partial}，需人判"
                    res['ambiguous']=partial
                else:
                    res['verdict']='FAIL'; res['message']=f"{t['label']}={v} {t['op']} {t['value']}"
            else:
                if ok is None:
                    res['verdict']='UNVERIFIABLE'; res['message']=f"{t['label']}：算子 {t['op']} 未实现，需人判"
                else:
                    res['verdict']='PASS' if ok else 'FAIL'; res['message']=f"{t['label']}={v} {t['op']} {t['value']}"
        else:
            res['verdict']='UNVERIFIABLE'; res['message']='定性卡：需人工按三档判断'
        if res['verdict']=='FAIL' and t.get('ceiling')=='NO_FAIL': res['verdict']='CONFLICT_PENDING'
        res['basis']=t.get('basis'); res['anchor']=t.get('anchor')
        _coverage_gate(O, t, res)          # 批级覆盖率：只做 PASS→UNVERIFIABLE 的升级
        out.append(res)
    json.dump(out,open(os.path.join(O,'audit_results.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    import collections; print(json.dumps(dict(collections.Counter(x['verdict'] for x in out)),ensure_ascii=False)); return 0



_REQ_BY_TYPE = {
    'GAP-DATA': '请提供该区域可辨版本或原始文件（当前不可辨，不出数值）',
    'GAP-REF': '请上传被引标准全文',
    'GAP-AMB': '请确认采用哪种解释（列出候选与各自后果）',
    'GAP-CONFLICT': '请裁定以哪一条为准（并列原文）',
    'GAP-EXTERNAL': '请上传对应仪器说明书 / 实验室 SOP',
    'GAP-PERF': '标准未给阈值，请确认是否按记录性检查处理',
}


def util_route(O, text=''):
    """取字路由：standards/ 下已有正文 → PDF_TEXT 直通；没有才要求 --pdf 走探测/OCR。
    有正文时不调 OCR、不猜字，把来源与指纹记进 00-provenance.json。"""
    import hashlib, datetime
    p=text or _guess_text(O)
    if not p:
        print(json.dumps({'route':'NEED_INPUT','hint':'standards/ 下没有唯一 txt；请给 --text 或 --pdf'},ensure_ascii=False)); return 2
    t=open(p,encoding='utf-8').read()
    sha=hashlib.sha256(t.encode()).hexdigest()[:12]
    pv=os.path.join(O,'00-provenance.json')
    doc={}
    if os.path.exists(pv):
        try: doc=json.load(open(pv,encoding='utf-8'))
        except Exception: doc={}
    doc['text_route']={'route':'PDF_TEXT','text':os.path.basename(p),'sha256_12':sha,
                       'chars':len(t),'at':datetime.datetime.now().isoformat(timespec='seconds')}
    os.makedirs(O,exist_ok=True)
    json.dump(doc,open(pv,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps({'route':'PDF_TEXT','text':p,'sha256_12':sha,'chars':len(t)},ensure_ascii=False)); return 0


def util_ref_gaps(O):
    """引用闭包与缺口补齐：PENDING_UPLOAD → GAP-REF；每条缺口必须有最小补充请求。"""
    p=os.path.join(O,'01-clauses.json')
    c=json.load(open(p,encoding='utf-8'))
    gaps=c.get('gaps') or []
    have={g.get('gap_id') for g in gaps}
    added=[]
    for r in c.get('reference_register') or []:
        if r.get('status')!='PENDING_UPLOAD': continue
        gid='GAP-REF-'+str(r.get('ref_id'))
        if gid in have: continue
        no=r.get('standard_no') or r.get('title') or r.get('ref_id')
        cls=', '.join(str(x) for x in (r.get('referenced_by') or [])[:6])
        gaps.append({'gap_id':gid,'type':'GAP-REF','ref_id':r.get('ref_id'),
                     'pending_class':'PENDING_REF',
                     'request':f'请上传 {no} 全文'+(f'（被引条款 {cls}）' if cls else ''),
                     'affects':r.get('affected_rules') or [],
                     'note':r.get('scope') or '','owner':'标准归口 / 用户'})
        added.append(gid)
    fixed=[]
    for g in gaps:
        if not g.get('request'):
            g['request']=_REQ_BY_TYPE.get(g.get('type') or '','请补充该项材料或说明')
            fixed.append(g.get('gap_id'))
    c['gaps']=gaps
    json.dump(c,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps({'ref_gaps_added':len(added),'request_filled':len(fixed),
                      'gaps_total':len(gaps),'added':added},ensure_ascii=False)); return 0


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
        st.execute('DELETE FROM findings WHERE standard_id=?',(sid,))
        st.execute('INSERT INTO findings VALUES (?,?)',(sid,open(os.path.join(O,'audit_findings.json'),encoding='utf-8').read()))
    # SOP 图进库：nodes / edges / rule_node；挂不上节点的规则登记为缺口，不静默丢
    sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
    import graph_index
    gc=graph_index.load(st,sid,O)
    um=graph_index.unmapped(st,sid) if gc['nodes'] else []
    gp=graph_index.write_gaps(O,sid,um) if um else None
    if not um:
        stale=os.path.join(O,'machine','graph_gaps.json')
        if os.path.exists(stale): os.remove(stale)
    st.commit(); st.close()
    print(json.dumps({'standard_id':sid,'rules':len(ses.get('audit_rule_cards') or []),'span_refs':nspan,
                      'nodes':gc['nodes'],'edges':gc['edges'],'rule_node':gc['rule_node'],
                      'unmapped':len(um),'graph_gaps':gp,
                      'graph_missing':gc['nodes']==0,'lib':lib},ensure_ascii=False)); return 0


def _open_lib(lib):
    import sqlite3
    p=os.path.join(lib,'standards.db')
    if not os.path.exists(p):
        print(json.dumps({'error':f'{p} 不存在，先跑 load_library'},ensure_ascii=False)); return None,None
    return sqlite3.connect(p),p


def util_graph_index(O, lib='library'):
    """按库读：每个标准挂了几个节点、几条边、几条规则，多少规则没落点。"""
    sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
    import graph_index
    con,p=_open_lib(lib)
    if not con: return 2
    out=[]
    for sid,*_ in con.execute('select standard_id from standards'):
        n=con.execute('select count(*) from nodes where standard_id=?',(sid,)).fetchone()[0]
        e=con.execute('select count(*) from edges where standard_id=?',(sid,)).fetchone()[0]
        l=con.execute('select count(distinct rule_id) from rule_node where standard_id=?',(sid,)).fetchone()[0]
        um=graph_index.unmapped(con,sid)
        out.append({'standard_id':sid,'nodes':n,'edges':e,'rules_mapped':l,
                    'rules_unmapped':len(um),
                    'unmapped':[{'rule_id':x['rule_id'],'category':x['category'],
                                 'need_node':graph_index.EXPECT_NODE.get(x['category'] or '','step')} for x in um]})
    con.close(); print(json.dumps({'lib':p,'standards':out},ensure_ascii=False,indent=1)); return 0


def util_graph_lookup(O, rule='', node_id='', lib='library'):
    """下游读图：给 rule_id 返回节点与边；给 node_id 返回规则与边。零 JSON 文件读取。
    多标准并存时按 standard 逐库返回，不默认取第一行。"""
    sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
    import graph_index
    con,p=_open_lib(lib)
    if not con: return 2
    sids=[r[0] for r in con.execute('select standard_id from standards')]
    if not rule and not node_id:
        con.close(); print(json.dumps({'error':'需要 --rule 或 --node-id'},ensure_ascii=False)); return 2
    hits=[]
    for sid in sids:
        r=graph_index.lookup_rule(con,sid,rule) if rule else graph_index.lookup_node(con,sid,node_id)
        if r.get('mapped') or r.get('found') or r.get('rule_found'):
            hits.append(r)
    con.close()
    print(json.dumps({'lib':p,'query':{'rule':rule,'node_id':node_id},'hits':hits},ensure_ascii=False,indent=1)); return 0



def _trail(O, rec):
    with open(os.path.join(O,'trail.jsonl'),'a',encoding='utf-8') as f:
        f.write(json.dumps(rec,ensure_ascii=False)+'\n')

def util_trail(O, step, exit_code, outputs='', node=''):
    import datetime
    rec={'step':step,'exit':int(exit_code),'outputs':[x for x in outputs.split(',') if x],
         'at':datetime.datetime.now().isoformat(timespec='seconds')}
    if node: rec['node']=node
    _trail(O, rec)
    print(json.dumps({'trail':step,'node':node,'exit':exit_code},ensure_ascii=False)); return 0

def _guess_text(O):
    """按 01-clauses.json 的 slug 在 out/standards 下定位正文；再退到唯一 txt。"""
    import glob as _glob
    if not os.path.exists(os.path.join(O,'01-clauses.json')):
        only=sorted(_glob.glob(os.path.join(O,'standards','*.txt')))
        return only[0] if len(only)==1 else ''
    try:
        c=json.load(open(os.path.join(O,'01-clauses.json'),encoding='utf-8'))
        d=os.path.join(O,'standards'); slug=c.get('standard_slug') or ''
        cands=[os.path.join(d,slug+'.txt'),os.path.join(d,slug+'.TXT')] if slug else []
        if os.path.isdir(d):
            only=sorted(f for f in os.listdir(d) if f.lower().endswith('.txt'))
            if len(only)==1: cands.append(os.path.join(d,only[0]))
        for p in cands:
            if os.path.exists(p): return p
    except Exception: pass
    return ''


def _step_name(st):
    cmd=st.get('cmd','')
    return cmd.split('--util ')[-1].split()[0] if '--util ' in cmd else st['run']


def util_check(O, node):
    """开跑前唯一入口：直接给出可执行命令与缺失项，agent 不需要读任何 md。"""
    C=CONTRACTS['contracts'][node]
    skill=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ctx={'out':O,'skill':skill,'text':_guess_text(O) or '<需 --text 指向标准正文 txt>','pdf':'<需 --pdf>'}
    print(f'== MUST RUN ({node})')
    print(f'== out={O}')
    for i,st in enumerate(C['steps'],1):
        if st['run']=='llm':
            print(f'{i}. [llm] 写 {os.path.join(O, str(st.get("call"))+".json")}  schema={st.get("schema")}'
                  f'  chunk={st.get("chunk")}  max_items={st.get("max_items")}')
            if st.get('instruction'): print(f'   指令：{st["instruction"]}')
        else:
            print(f'{i}. [{st["run"]}] {st["cmd"].format(**ctx)}')
    miss=[]
    for p in (C.get('inputs') or []):
        q=p.format(**ctx)
        if '<' in q: continue
        if not os.path.exists(q): miss.append(q)
    print('== 前置输入缺失：' + ('无' if not miss else ', '.join(miss)))
    print(f'== 完成后留痕：python3 {skill}/scripts/run_contract.py --util verify --node {node} --out {O}')
    print(f'== 判定门禁：python3 {skill}/scripts/validate_node.py --node {node} --out {O}')
    return 0


def util_verify(O, node):
    """判定本节点是否真按契约跑过：只认 trail 里带 node=<本节点> 的记录。
    gate 步骤不计入（它由 validate_node 单独执行），但 trail 为空一律不通过。"""
    import datetime, collections
    tp=os.path.join(O,'trail.jsonl')
    if not os.path.exists(tp):
        print(json.dumps({'node':node,'status':'NO_TRAIL','hint':'未发现 trail.jsonl：视为未执行'},ensure_ascii=False)); return 2
    recs=[json.loads(l) for l in open(tp,encoding='utf-8') if l.strip()]
    C=CONTRACTS['contracts'][node]
    need=collections.Counter(_step_name(st) for st in C['steps'] if st['run'] not in ('llm','gate'))
    tagged=[r for r in recs if r.get('node')==node]
    done=collections.Counter(r['step'] for r in tagged if r.get('exit')==0)
    attested=sum(1 for r in tagged if r.get('exit')==0 and r.get('attested'))
    missing=[f'{n}×{c}(已{done.get(n,0)})' for n,c in need.items() if done.get(n,0)<c]
    if not tagged:
        missing=missing or ['本节点无任何带 node 标记的执行留痕（trail 未记录 node）']
    elif not need:
        missing=[]
    ok=not missing
    _trail(O,{'step':'verify','node':node,'pass':ok,'missing':missing,'need':dict(need),
              'attested':attested,'at':datetime.datetime.now().isoformat(timespec='seconds')})
    print(json.dumps({'node':node,'verify':'PASS' if ok else 'FAIL','need':dict(need),
                      'done':dict(done),'attested':attested,'missing':missing},ensure_ascii=False)); return 0 if ok else 1


def util_fix_log(O):
    """fix 节点留痕：从 audit_result 派生本轮处置数，写进 02/03 的 revision_log。
    只记录"有没有处置项"，不伪造改动；有 blockers 时必须由 fix 节点改完再写。"""
    import datetime
    ar=os.path.join(O,'audit_result.json')
    if not os.path.exists(ar):
        print(json.dumps({'error':'audit_result.json 缺失，fix 无法判定处置数'},ensure_ascii=False)); return 2
    a=json.load(open(ar,encoding='utf-8'))
    blockers=a.get('blockers') or []
    n=len(blockers) if isinstance(blockers,list) else int(blockers or 0)
    ent={'at':datetime.datetime.now().isoformat(timespec='seconds'),'round':a.get('round'),
         'blockers':n,'changes':0 if n==0 else None,
         'reason':'audit_result.blockers=0，本轮无 B-xx 处置项' if n==0 else f'有 {n} 项 blocker，需 fix 节点实际改完再写',
         'source':'derived-from-audit_result'}
    if n!=0:
        print(json.dumps({'refused':True,'blockers':n,'hint':ent['reason']},ensure_ascii=False)); return 1
    touched=[]
    for name in ('02-elements.json','03-rules.json'):
        p=os.path.join(O,name)
        if not os.path.exists(p): continue
        d=json.load(open(p,encoding='utf-8'))
        log=d.get('revision_log') or []
        if not isinstance(log,list): log=[log]
        log.append(ent)
        d['revision_log']=log
        json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
        touched.append(name)
    print(json.dumps({'round':a.get('round'),'blockers':n,'revision_log_written':touched},ensure_ascii=False)); return 0


def util_attest(O, node):
    """历史 run 补录留痕：内容门禁必须真过（跳过留痕项），才允许写 attested 记录。
    记录带 basis=artifact_exists，与 auto 记录可区分，不冒充本次执行。"""
    import subprocess, collections
    skill=os.path.dirname(os.path.abspath(__file__))
    env=dict(os.environ, SKIP_TRAIL_CHECK='1')
    r=subprocess.run([sys.executable, os.path.join(skill,'validate_node.py'),
                      '--node',node,'--out',O], capture_output=True, text=True, env=env)
    if r.returncode!=0:
        bad=[l.strip() for l in r.stdout.splitlines() if l.strip().startswith('FAIL')][:6]
        print(json.dumps({'node':node,'attest':'REFUSED',
                          'reason':'内容门禁未过，不许补录留痕','fails':bad},ensure_ascii=False)); return 1
    C=CONTRACTS['contracts'][node]
    need=collections.Counter(_step_name(st) for st in C['steps'] if st['run'] not in ('llm','gate'))
    if not need:
        llm=[st.get('call') for st in C['steps'] if st['run']=='llm']
        need=collections.Counter({'llm:'+(str(x) if x else 'output'):1 for x in llm} or {'node_output':1})
    n=0
    for name,cnt in need.items():
        for _ in range(cnt):
            _trail(O,{'step':name,'node':node,'exit':0,'attested':True,'basis':'artifact_exists'})
            n+=1
    print(json.dumps({'node':node,'attest':'OK','records':n,'need':dict(need),
                      'note':'已写补录留痕（artifact_exists），verify 会单独统计条数'},ensure_ascii=False)); return 0


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



def util_ocr_plan(O, slug=''):
    """打印 OCR 接入方案：有文本层走文本；无文本层且 MCP 已部署→调 MCP；否则登记 GAP-DATA。"""
    cfgp=os.path.join(O,'ocr.config.json')
    cfg=json.load(open(cfgp,encoding='utf-8')) if os.path.exists(cfgp) else {}
    en=bool(cfg.get('enabled'))
    plan={'slug':slug or '<slug>',
          'steps':[
            '1) 取字探测：python3 {skill}/scripts/cap.py probe <pdf> → route=PDF_TEXT | OCR',
            '2) route=PDF_TEXT：直接用文本层，不调 OCR（省时且准确）',
            '3) route=OCR 且 OCR MCP 已部署：agent 调用 MCP 工具逐页识别（dpi=%s, lang=%s），把每页结果落到 %s/page-NNN.txt（可附 page-NNN.json 带 confidence）' % (cfg.get('dpi',600),cfg.get('lang','chi_sim+eng'),os.path.join(O,'ocr-pages')),
            '4) 汇总：run_contract.py --util ocr_ingest --out <out> --pages <out>/ocr-pages --slug <slug>',
            '5) 后续：00-provenance.json 记 route=OCR + 均值置信度；低于 min_conf=%s 的页登记 GAP-DATA，不猜字' % cfg.get('min_conf',0.5)],
          'ocr_enabled':en,'mcp':cfg.get('mcp') or {'server':'<未配置>','tool':'<未配置>'},
          'fallback':'OCR 不可用时：登记 GAP-DATA 并要求上传可选文本 PDF 或人工校订文本'}
    print(json.dumps(plan,ensure_ascii=False,indent=2)); return 0

def util_ocr_ingest(O, pages, slug):
    """把逐页 OCR 结果汇总成带 PAGE 标记的文本 + source.json（含均值置信度）"""
    import glob, json as J, os as _os
    files=sorted(glob.glob(_os.path.join(pages,'page-*.txt')))
    if not files:
        print(json.dumps({'error':'未找到页面结果','pages_dir':pages},ensure_ascii=False)); return 2
    out=[]; confs=[]
    for i,f in enumerate(files,1):
        txt=open(f,encoding='utf-8').read().rstrip('\n')
        out.append(f'===== PAGE {i} =====\n'+txt)
        jf=f[:-4]+'.json'
        if _os.path.exists(jf):
            try: confs.append(float(J.load(open(jf,encoding='utf-8')).get('confidence')))
            except Exception: pass
    text='\n\n'.join(out)+'\n'
    d=_os.path.join(O,'standards'); _os.makedirs(d,exist_ok=True)
    tp=_os.path.join(d,f'{slug}.txt'); open(tp,'w',encoding='utf-8').write(text)
    import hashlib
    sha=hashlib.sha256(text.encode()).hexdigest()[:12]
    src={'route':'OCR','pages':len(files),'sha256_12':sha,'mean_confidence':round(sum(confs)/len(confs),3) if confs else None,
         'low_conf_pages':[i+1 for i,c in enumerate(confs) if c<float(__import__('os').environ.get('OCR_MIN_CONF','0.5'))],
         'source':'ocr-ingest'}
    json.dump(src,open(_os.path.join(d,f'{slug}.source.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps({'text':tp,'pages':len(files),'sha':sha,'mean_conf':src['mean_confidence'],'low_conf_pages':src['low_conf_pages']},ensure_ascii=False)); return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--node', default=''); ap.add_argument('--out', required=True)
    ap.add_argument('--text', default=''); ap.add_argument('--pdf', default=''); ap.add_argument('--skill', default='')
    ap.add_argument('--util', default=''); ap.add_argument('--next', default=''); ap.add_argument('--changed', action='append', default=[])
    ap.add_argument('--shard', default='0/1'); ap.add_argument('--shards', type=int, default=3)
    ap.add_argument('--standard', default='')
    ap.add_argument('--slots', default='')
    ap.add_argument('--rule', default=''); ap.add_argument('--node-id', dest='node_id', default='')
    ap.add_argument('--step', default=''); ap.add_argument('--exit', dest='exit_code', type=int, default=0)
    ap.add_argument('--outputs', default=''); ap.add_argument('--pages', default='')
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
    if a.util == 'ocr_plan': return util_ocr_plan(os.path.abspath(a.out), a.step)
    if a.util == 'ocr_ingest': return util_ocr_ingest(os.path.abspath(a.out), a.pages, a.step)
    if a.util == 'load_library': return util_load_library(os.path.abspath(a.out))
    if a.util == 'fix_log': return util_fix_log(os.path.abspath(a.out))
    if a.util == 'route': return util_route(os.path.abspath(a.out), a.text)
    if a.util == 'attest': return util_attest(os.path.abspath(a.out), a.node)
    if a.util == 'ref_gaps': return util_ref_gaps(os.path.abspath(a.out))
    if a.util == 'graph_index': return util_graph_index(os.path.abspath(a.out))
    if a.util == 'graph_lookup': return util_graph_lookup(os.path.abspath(a.out), a.rule, a.node_id)
    if a.util == 'trail': return util_trail(os.path.abspath(a.out), a.step, a.exit_code, a.outputs, a.node)
    if a.util == 'check': return util_check(os.path.abspath(a.out), a.node)
    if a.util == 'verify': return util_verify(os.path.abspath(a.out), a.node)
    if a.util == 'split_dirs': return util_split_dirs(os.path.abspath(a.out))
    if a.util == 'backfill_spans': return util_backfill_spans(os.path.abspath(a.out))
    if not a.node:
        print('need --node or --util', file=sys.stderr); return 2
    c = CONTRACTS['contracts'][a.node]
    ctx = {'out': os.path.abspath(a.out), 'text': a.text or _guess_text(os.path.abspath(a.out)),
           'pdf': a.pdf, 'skill': skill}
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
        # 成功即留痕：不让「忘了写 trail」变成门禁不可过
        _trail(ctx['out'], {'step': _step_name(st), 'node': c['id'], 'exit': r.returncode, 'auto': True})
        if not ok:
            print(r.stdout[-500:]); print(r.stderr[-500:]); return 1
    print('CONTRACT: PASS')
    return 0

if __name__ == '__main__':
    sys.exit(main())
