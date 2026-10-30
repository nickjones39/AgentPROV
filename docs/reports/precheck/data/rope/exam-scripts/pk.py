import json, re, os, hashlib, subprocess, sys
from pathlib import Path
N = Path('~/.agentprov/migration-work/precheck/rope/l2-rope-slice-j2.partial').expanduser()
rx = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)
hdr = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
ROOT = Path('~/Desktop/PhD/Labs/AgentPROV-upstream/rope').expanduser()
blocks = {}
for l in open(N / 'executions.jsonl'):
    r = json.loads(l)
    for x in (N / r['paths']['aer']).read_bytes().splitlines():
        a = json.loads(x); s = json.dumps(a, ensure_ascii=False)
        if hdr.search(s):
            lab = json.loads((N / r['paths']['aer']).read_bytes().splitlines()[0])['artifacts'][0]['origin']['path']
            txt = json.dumps(a)  # escaped
            for m in rx.finditer(json.loads(json.dumps(a)) and s.replace('\\n', '\n')):
                b = m.group(0); h = hashlib.sha256(b.encode()).hexdigest()[:12]
                blocks.setdefault(h, set()).add((lab, a['k'], a.get('role'), len(b)))
            if not rx.search(s.replace('\\n', '\n')): blocks.setdefault('header-only', set()).add((lab, a['k'], a.get('role'), 0))
for h, v in blocks.items(): print(h, sorted(v))
# search vendored benchmark sources (autodojo/**, src/**) for the same blocks, by digest only
found = {}
for p in list((ROOT / 'autodojo').rglob('*')) :
    if p.is_file() and p.suffix in ('.yaml', '.yml', '.json', '.py', '.txt', '.md'):
        try: t = p.read_bytes().decode('utf-8', 'replace')
        except Exception: continue
        if 'PRIVATE KEY' in t:
            for m in rx.finditer(t.replace('\\n', '\n')):
                found.setdefault(hashlib.sha256(m.group(0).encode()).hexdigest()[:12], 0)
                found[hashlib.sha256(m.group(0).encode()).hexdigest()[:12]] += 1
print('vendored-benchmark block digests:', len(found), {h: (h in found) for h in blocks})
