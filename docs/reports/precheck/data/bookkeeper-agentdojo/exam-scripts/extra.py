"""Sample gate decisions vs raw denials; L1-03 variation-selector / zero-width locations (codepoint classes only); counts only.
usage: python -I extra.py <l2-sample.json> <out.json>"""
import sys, os, collections, json, unicodedata
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
t=tree(); r=Reader(); DEN="Declined by the account's money gate. "
S=json.load(open(sys.argv[1])); labels=[u['label'] if isinstance(u,dict) else u for u in (S.get('labels') or [x for st in S['strata'].values() for x in st] if 'strata' in S else S['labels'])]
c=collections.Counter(); vs=collections.Counter(); zw=collections.Counter()
def txt(cc): return ''.join((b.get('content') or '') for b in cc) if isinstance(cc,list) else (cc or '')
for p in labels:
    x=r.json(t[p]); ms=x['messages']
    for m in ms:
        c['tool_calls']+=len(m.get('tool_calls') or [])
        if m.get('role')=='tool':
            c['tool_msgs']+=1; e=m.get('error')
            if e is None: c['tool_ok']+=1
            elif e.startswith(DEN): c['denials']+=1
            else: c['other_error']+=1
for p in sorted(x for x in t if x.startswith('runs/agentdojo/') and x.endswith('.json') and x.count('/')==7):
    x=r.json(t[p])
    for m in x['messages']:
        role=m.get('role')
        s=txt(m.get('content'))
        for i,ch in enumerate(s):
            if ch in '\ufe0e\ufe0f':
                prev=s[i-1] if i else ''
                vs[f"{role}|{p.split('/')[3].split('-')[0]}|{p.split('/')[6]}|prev={unicodedata.category(prev) if prev else 'none'}|U+{ord(prev):04X}" if prev else 'start']+=1
            if ch in '\u200b\u200c\u200d\u2060\ufeff': zw[f"{role}|U+{ord(ch):04X}|{p.split('/')[3].split('-')[0]}"]+=1
out=dict(sample_labels=len(labels),sample_raw=dict(c),variation_selector_by_model_prevchar=dict(vs),zero_width=dict(zw))
json.dump(out,open(sys.argv[2],'w'),indent=1); print(json.dumps(out))
