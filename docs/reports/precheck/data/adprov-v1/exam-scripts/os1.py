import json, re, sys, collections, math
sys.path.insert(0, 'tools/analysis2')
from exam2_lib import wilson
rows=[json.loads(l) for l in open(sys.argv[1])]
M={'prov-deepseek-chat':'deepseek-chat','google_gemini-2.5-flash':'gemini-2.5-flash','prov-gpt-5-nano':'gpt-5-nano','meta-llama_llama-3.3-70b-instruct':'llama-3.3-70b','qwen_qwen-2.5-72b-instruct':'qwen-2.5-72b','z-ai_glm-4.6':'glm-4.6'}
paper={'deepseek-chat':(84.0,84.2,87.6,78.4,4.3,4.4,(4.3,5.3)),'gemini-2.5-flash':(39.0,39.0,55.7,29.2,8.6,8.7,(8.6,9.6)),'gpt-5-nano':(73.5,73.5,75.3,68.9,1.5,1.5,(1.5,2.5)),'llama-3.3-70b':(36.2,36.3,40.2,33.1,8.8,8.8,(8.7,9.8)),'qwen-2.5-72b':(40.3,40.2,50.5,30.6,14.5,14.6,(14.5,15.5)),'glm-4.6':(83.5,83.6,88.7,75.8,7.5,7.6,(7.5,8.5))}
def fmt(k,n):
    lo,hi=wilson(k,n); return dict(k=k,n=n,rate=round(100*k/n,2) if n else None,wilson95=[round(100*lo,2),round(100*hi,2)])
out={}
agg=collections.defaultdict(lambda:[0,0])
for r in rows:
    m=M[r['facets']['model_folder']]; a=r['facets']['attack']; o=r['outcomes']
    lab=r['label'].split('/')[-1]
    mm=re.search(r'_x_injectiontask(\d+)_',lab); it=mm.group(1) if mm else None
    ut=re.search(r'_user_task_(\d+)',lab).group(1)
    def add(key,val):
        agg[key][1]+=1; agg[key][0]+= 1 if val is True else 0
    add(('util',m,'all'),o['utility'])
    add(('util',m,a),o['utility'])
    add(('util','all',a),o['utility'])
    add(('util','all','all'),o['utility'])
    if a!='benign':
        add(('asr',m,'attacked'),o['security'])
        add(('asr','all',a),o['security'])
        add(('asr',m,a),o['security'])
        add(('asr','all','attacked'),o['security'])
        if r['facets']['suite']=='workspace' and it=='0':
            add(('ws_it0',m,'all'),o['security'])
    if o['security'] is None and a!='benign': agg[('sec_null_attacked',m,'')][0]+=1
    if o['security'] is not None and a=='benign': agg[('sec_nonnull_benign',m,'')][0]+=1
    if o['run_error_present']: agg[('run_error',m,'')][0]+=1
res={'|'.join(k):fmt(*v) if v[1] else {'k':v[0]} for k,v in sorted(agg.items())}
# gap rule vs logged and paper
gaps=[]
for m,(ul,up,ub,ui,al,ap,bounds) in paper.items():
    u=agg[('util',m,'all')]; s=agg[('asr',m,'attacked')]; b=agg[('util',m,'benign')]; ii=agg[('util',m,'important_instructions')]
    for metric,(k,n),logged,pap in (('utility',u,ul,up),('asr',s,al,ap),('benign_utility',b,ub,ub),('imp_instr_utility',ii,ui,ui)):
        rate=100*k/n; lo,hi=wilson(k,n)
        gap=max(abs(rate-logged),abs(rate-pap))
        excl=max(0,100*lo-pap, pap-100*hi)
        flag=(n>=20 and abs(rate-pap)>15) or excl>5
        gaps.append(dict(model=m,metric=metric,k=k,n=n,rate=round(rate,2),wilson95=[round(100*lo,2),round(100*hi,2)],logged_e2=logged,paper=pap,gap_pp_vs_paper=round(rate-pap,2),gap_pp_vs_logged=round(rate-logged,2),excluded_by_more_than_5pp=round(excl,2),flag=flag))
json.dump(dict(rates=res,gap_rule=gaps),open(sys.argv[2],'w'),indent=1)
for g in gaps: print(g)
for k in res:
    if k.startswith(('ws_it0','asr|all','util|all','sec_','run_')): print(k,res[k])
