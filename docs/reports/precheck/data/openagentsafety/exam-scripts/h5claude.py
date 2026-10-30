"""H5 mismatches in claude-sonnet's judge summary: summary rule_based_score vs the llm_as_judge mapping of the eval file; counts only.
usage: python -I h5claude.py"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(__file__))
from rawread import tree, Reader
t=tree(); r=Reader(); m='claude-sonnet'
S=r.json(t[f'evaluation/{m}/claude_safety_eval_results.json'])
c=collections.Counter()
for k,v in S.items():
    oid=t.get(f'evaluation/{m}/eval_{k}.json'); e=r.json(oid) if oid else None
    fs=(e or {}).get('final_score') if e else None
    exp=-1 if fs is None or fs.get('total')==0 else (1 if fs.get('result')==1 else 0)
    if exp!=v.get('rule_based_score'):
        c[(f"summary={v.get('rule_based_score')}", f"eval={'none' if fs is None else str(fs.get('result'))+'/'+str(fs.get('total'))}", f"traj={'yes' if f'evaluation/{m}/traj_{k}.json' in t else 'no'}", f"label={v.get('llm_label')}")]+=1
print(json.dumps({' '.join(k):n for k,n in c.items()}))
