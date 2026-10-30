"""L1-06 generic-credential-assignment hits: keyword, suite, role, distinct value digests (never values)."""
import sys, os, collections, json, re, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
RX=re.compile(r"(?i)(api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s{0,3}[:=]\s{0,3}[\"']?([A-Za-z0-9_\-/+=.]{16,})")
t=tree(); r=Reader(); kw=collections.Counter(); where=collections.Counter(); vals=collections.defaultdict(set); files=collections.Counter()
for p in sorted(p for p in t if p.startswith('runs/') and p.endswith('.json')):
    suite=p.split('/')[2]; d=r.json(t[p]); hit=False
    def scan(s,loc):
        global hit
        for m in RX.finditer(s):
            hit=True; kw[(suite,m.group(1).lower())]+=1; where[(suite,loc)]+=1
            vals[hashlib.sha256(m.group(2).encode()).hexdigest()[:12]].add(p)
    scan(d['initial_checklist'],'initial_checklist')
    for m in d['conversations']:
        c=m.get('content'); scan(c if isinstance(c,str) else json.dumps(c), m['role']+'.content')
        for tc in ([m['tool_call']] if isinstance(m.get('tool_call'),dict) else [])+list(m.get('tool_calls') or []):
            scan(json.dumps(tc.get('args')), m['role']+'.call_args')
    files[suite]+=hit
spread=collections.Counter(min(len(v),10) for v in vals.values())
out={'files_with_hit':dict(files),'by_keyword':{'|'.join(k):v for k,v in kw.items()},'by_location':{'|'.join(k):v for k,v in where.items()},
     'distinct_values':len(vals),'files_per_distinct_value_hist(capped10)':dict(sorted(spread.items())),
     'top_value_file_counts':sorted((len(v) for v in vals.values()),reverse=True)[:8]}
json.dump(out,open(sys.argv[1],'w'),indent=1); print(json.dumps(out))
