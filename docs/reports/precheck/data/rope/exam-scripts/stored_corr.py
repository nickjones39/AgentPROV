import json, collections, sys
from pathlib import Path
O = Path('~/.agentprov/corpora/rope-p10.partial').expanduser()
C = collections.Counter
out = {}
cells = collections.defaultdict(C)
for l in (O / 'executions.jsonl').read_bytes().splitlines():
    r = json.loads(l)
    lines = (O / r['paths']['aer']).read_bytes().splitlines()
    e = json.loads(lines[0]); path = e['artifacts'][0]['origin']['path']
    seg = path.split('/')
    md = '/'.join(seg[1:3]) if seg[1] in ('ablation', 'router') else seg[1]
    suite, ut, att, it = seg[-4], seg[-3], seg[-2], seg[-1][:-5]
    J = {}
    for x in lines:
        if b'"judgement"' in x:
            j = json.loads(x)
            if j.get('k') == 'judgement': J[(j['name'], j.get('origin'), bool(j.get('revises')))] = j['value']
    rs = J.get(('security', 'checker', False)); rc = J.get(('security', 'recomputed', True))
    c = cells[(md, att, suite)]
    c['n'] += 1
    if att != 'none':
        c['raw_true'] += rs is True
        c['corr_true'] += (rc if rc is not None else rs) is True
        if rc is not None:
            c['recomputed'] += 1
            c[f'recomputed:{suite}:{it}'] += 1
            c[f'raw_true:{suite}:{it}'] += rs is True
            c[f'corr_true:{suite}:{it}'] += rc is True
res = {'|'.join(k): dict(v) for k, v in sorted(cells.items())}
json.dump(res, open(sys.argv[1], 'w'), indent=1)
tot = C()
for k, v in cells.items():
    for kk, vv in v.items():
        if ':' in kk or kk == 'recomputed': tot[kk] += vv
    tot[f'raw_true|{k[1]}'] += v['raw_true']; tot[f'corr_true|{k[1]}'] += v['corr_true']
print(dict(sorted(tot.items())))
