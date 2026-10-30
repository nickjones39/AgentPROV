"""Locate L1-10 account digests in non-JSON auxiliary/task files at the pin; prints file kind (basename class), task and a masked window.
usage: python -I acctaux.py digest ..."""
import sys, os, re, hashlib, pathlib
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[6] / 'tools' / 'precheck'))
from rawread import tree, Reader
import l1_scan
want=set(sys.argv[1:]); dig=lambda s: hashlib.sha256(s.encode()).hexdigest()[:12]
t=tree(); r=Reader()
for k,v in t.items():
    if k.lower().endswith(('.png','.json')): continue
    s=(r.read(v) or b'').decode('utf-8','replace')
    for m in l1_scan.ACCOUNT_PATTERNS['home-dir'].finditer(s):
        if dig(m.group(1)) in want:
            w=s[max(0,m.start()-60):m.end()+60].replace(m.group(1),'<NAME>')
            print(dig(m.group(1)), k.split('/')[2] if k.startswith('workspaces/tasks/') else k.split('/')[0], k.rsplit('/',1)[-1], '|', re.sub(r'[^\x20-\x7e]','.',w)); break
