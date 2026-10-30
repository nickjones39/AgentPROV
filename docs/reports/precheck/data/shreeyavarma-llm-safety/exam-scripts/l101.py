import sys, json, collections, os
from pathlib import Path
sys.path.insert(0, str(Path(os.environ['PRECHECK_REPO'])/'tools'/'precheck'))
import l1_scan
src=l1_scan.GitSource(Path.home()/'.agentprov/staging/10c/shreeyavarma/llm_safety.git','78d22e4a3daa5e76c77b75076c30ceb1faab22c1')
ents=src.entries()
sel={json.loads(l)['label'] for l in open(Path.home()/'.agentprov/migration-work/precheck/shreeyavarma-llm-safety/l1-units-head.jsonl')}
C=collections.Counter()
for e in ents:
    top=e.label.split('/')[0]
    if e.label in sel: k='selected'
    elif top=='runs': k='runs'
    elif e.label in ('LICENSE','README.md','pyproject.toml','uv.lock'): k='context'
    else: k='other'
    C[(k, e.disposition, e.label.rsplit('.',1)[-1].lower() if '.' in e.label.rsplit('/',1)[-1] else '<noext>' if k=='other' else '')]+=1
print(len(ents), len(src.rejected), collections.Counter(c for _,c in src.rejected))
print(sum(v for (k,d,x),v in C.items() if k=='other' and x=='json' and d=='listed'), 'other json listed')
print(sum(v for (k,d,x),v in C.items() if k=='runs'), 'runs', sum(v for (k,d,x),v in C.items() if k=='runs' and d=='absent_blob'))
print(sum(v for (k,d,x),v in C.items() if d=='absent_blob' and x=='json'), 'absent json')
