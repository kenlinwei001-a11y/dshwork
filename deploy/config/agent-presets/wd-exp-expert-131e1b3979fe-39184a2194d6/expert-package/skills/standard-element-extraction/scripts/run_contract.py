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
            'head':q[:80],'numbers':[m.group(0) for m in NUM.finditer(q)],
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--node', default=''); ap.add_argument('--out', required=True)
    ap.add_argument('--text', default=''); ap.add_argument('--pdf', default=''); ap.add_argument('--skill', default='')
    ap.add_argument('--util', default=''); ap.add_argument('--next', default=''); ap.add_argument('--changed', action='append', default=[])
    a = ap.parse_args()
    skill = a.skill or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if a.util == 'fact_rows': return util_fact_rows(os.path.abspath(a.out))
    if a.util == 'handoff_state': return util_handoff_state(os.path.abspath(a.out), a.next, a.changed)
    if a.util == 'cleanup_intermediates': return util_cleanup(os.path.abspath(a.out))
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
