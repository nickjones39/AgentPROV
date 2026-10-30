"""initial_checklist string classes (counts only)."""
import sys, os, collections, json
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
t=tree(); r=Reader(); c=collections.Counter()
for p in sorted(p for p in t if p.startswith('runs/') and p.endswith('.json')):
    s=r.json(t[p])['initial_checklist'].strip()
    if s=='None': c['str_None']+=1; continue
    try: v=json.loads(s); c['str_parses_json:'+type(v).__name__]+=1
    except Exception: c['str_other_text:'+('fenced' if s.startswith('```') else 'plain')]+=1
print(json.dumps(dict(c)))
