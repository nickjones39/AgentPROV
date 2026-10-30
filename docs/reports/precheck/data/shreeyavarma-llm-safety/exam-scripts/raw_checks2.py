import sys, collections, json
sys.path.insert(0, sys.argv[1])
from rawload import load
C=collections.Counter
reach=C(); local_final=C(); local_shape=C(); gpt_final=C(); asst_none=C()
MARK='This is an important message from me'
def text_of(c):
    if c is None: return None
    if isinstance(c,str): return c
    return ''.join(x.get('content') or '' for x in c if isinstance(x,dict))
for label,row,o in load():
    f=row['facets']; pdir=f['pipeline_dir']; att=f['attack_dir']
    msgs=o.get('messages') or []
    tool_text='\n'.join(text_of(m.get('content')) or '' for m in msgs if m['role']=='tool')
    if att=='tool_knowledge':
        reach[(pdir, MARK in tool_text, 'security' in o and bool(o['security']))]+=1
    asst=[m for m in msgs if m['role']=='assistant']
    for m in asst:
        asst_none[(pdir, 'none' if m.get('content') is None else ('empty' if not (text_of(m.get('content')) or '').strip() else 'text'), bool(m.get('tool_calls')))]+=1
    if pdir!='gpt-4o-2024-05-13':
        shape=tuple(m['role'] for m in msgs)
        local_shape[(f['results_dir'], shape)]+=1
        if asst:
            c=asst[-1].get('content')
            local_final[('None' if c is None else type(c).__name__+':'+str(len(c)), repr(asst[-1].get('tool_calls')))]+=1
    else:
        if asst:
            c=asst[-1].get('content'); gpt_final['None' if c is None else ('empty' if not (text_of(c) or '').strip() else 'text')]+=1
print(json.dumps({'reach(pdir,marker_in_tool_output,security)':{str(k):v for k,v in reach.items()},
 'assistant_turns(pdir,content,has_calls)':{str(k):v for k,v in asst_none.items()},
 'local_shapes':{str(k):v for k,v in local_shape.items()},
 'local_final_content':{str(k):v for k,v in local_final.items()},
 'gpt_final':dict(gpt_final)},indent=1))
