"""Population outcome census of openagentsafety at the pin (eval/state/summary/evaluator files); counts only.
usage: python -I pop.py <out.json>"""
import sys, re, json, collections, math
sys.path.insert(0, __import__('os').path.dirname(__file__))
from rawread import tree, Reader
MODELS={'claude-sonnet':'claude_safety_eval_results.json','deepseek_r1':'deepseek_r1_safety_eval_results.json',
        'deepseek_v3':'deepseek_v3_safety_eval_results.json','gpt-4o':'gpt_safety_eval_results.json','o3-mini':None}
PAPER={'claude-sonnet':(51.20,32.85,9.17,40.30),'o3-mini':(72.73,32.32,6.57,43.30),'gpt-4o':(65.80,32.64,5.69,45.00),
       'deepseek_v3':(62.23,32.44,6.91,46.30),'deepseek_r1':(62.78,32.78,6.67,48.90)}
def wilson(k,n,z=1.96):
    if n==0: return None
    p=k/n; d=1+z*z/n; c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(100*p,2),round(100*(c-h),2),round(100*(c+h),2)]
t=tree(); r=Reader(); out={}
def files(m,pre): return {k.split('/')[-1][len(pre):-5]:v for k,v in t.items() if k.startswith(f'evaluation/{m}/{pre}') and k.endswith('.json')}
evaluators={k.split('/')[2]:v for k,v in t.items() if re.fullmatch(r'workspaces/tasks/[^/]+/utils/evaluator\.py',k)}
no_agg=set()
for task,oid in evaluators.items():
    if b'def grade_checkpoints' not in (r.read(oid) or b''): no_agg.add(task)
out['evaluator_py']=len(evaluators); out['evaluator_without_grade_checkpoints']=len(no_agg)
pertask_eval=collections.defaultdict(list); noagg_traj=collections.Counter(); summ_all={}
for m,sf in MODELS.items():
    tr,ev,st=files(m,'traj_'),files(m,'eval_'),files(m,'state_')
    o={'traj':len(tr),'eval':len(ev),'state':len(st),'state_only':len(set(st)-set(tr)),'traj_without_state':len(set(tr)-set(st)),'eval_without_traj':len(set(ev)-set(tr))}
    evv={}
    for k,oid in ev.items():
        e=r.json(oid); fs=e.get('final_score',{}) if isinstance(e,dict) else {}
        evv[k]=(fs.get('result'),fs.get('total')); pertask_eval[k].append(evv[k])
    cls=collections.Counter()
    for k in tr:
        v=evv.get(k); cls['missing' if v is None else f'{v[0]}/{v[1]}']+=1
        if k in no_agg: noagg_traj['traj']+=1; noagg_traj['traj_no_eval']+= v is None
    o['eval_final_score_over_traj']=dict(cls)
    mi=collections.Counter(); ast=collections.Counter(); mi_traj=collections.Counter()
    for k,oid in st.items():
        s=r.json(oid); s=s if isinstance(s,str) else json.dumps(s)
        a=re.findall(r'max_iterations=(\d+)',s); mi[a[0] if a else 'none']+=1
        if k in tr: mi_traj[a[0] if a else 'none']+=1
        b=re.findall(r'agent_state=<AgentState\.([A-Z_]+)',s); ast[b[-1] if b else 'none']+=1
    o['state_max_iterations']=dict(mi); o['state_max_iterations_with_traj']=dict(mi_traj); o['state_agent_state_last']=dict(ast)
    if sf:
        S=r.json(t[f'evaluation/{m}/{sf}']); summ_all[m]=S
        lab=collections.Counter(str(v.get('llm_label')) for v in S.values()); rb=collections.Counter(str(v.get('rule_based_score')) for v in S.values())
        N=len(S); neg=sum(1 for v in S.values() if v.get('llm_label')=='Label: -1'); safe=sum(1 for v in S.values() if v.get('llm_label')=='Label: 0')
        nn=[v for v in S.values() if v.get('llm_label')!='Label: -1']
        rule1=sum(1 for v in nn if v.get('rule_based_score')==1); dis=sum(1 for v in nn if v.get('llm_label')=='Label: 0' and v.get('rule_based_score')==1)
        uns=N-neg-safe
        o['summary']={'entries':N,'labels':dict(lab),'rule':dict(rb),'neg1':neg,'safe0':safe,'unsafe':uns,'rule1_nonneg':rule1,'disagree':dis,
          'rates':{'judge_unsafe':wilson(uns,N-neg),'rule_unsafe':wilson(rule1,N-neg),'disagree':wilson(dis,N-neg),'failure':wilson(neg,N)},
          'paper':PAPER[m],'entries_with_traj':len(set(S)&set(tr)),'traj_without_entry':len(set(tr)-set(S)),
          'state_only_in_summary':len((set(st)-set(tr))&set(S)),'state_only_in_summary_rule_m1':sum(1 for k in (set(st)-set(tr))&set(S) if S[k].get('rule_based_score')==-1),
          'entries_without_traj_or_state':len(set(S)-set(tr)-set(st))}
        mm=collections.Counter()
        for k,v in S.items():
            e=evv.get(k); exp=-1 if e is None or e[1]==0 else (1 if e[0]==1 else 0)
            mm['joined' if e is not None else 'no_eval']+=1; mm['match' if exp==v.get('rule_based_score') else 'mismatch']+=1
        o['summary']['rule_mapping_check']=dict(mm)
        # population over released trajectories (judge label of the run's entry)
        J=[S[k] for k in tr if k in S]; jn=[v for v in J if v.get('llm_label')!='Label: -1']
        o['traj_population']={'n_traj':len(tr),'n_judged':len(J),'neg1':len(J)-len(jn),'unsafe':sum(1 for v in jn if v.get('llm_label')!='Label: 0'),
           'rule1':sum(1 for v in jn if v.get('rule_based_score')==1),'disagree':sum(1 for v in jn if v.get('llm_label')=='Label: 0' and v.get('rule_based_score')==1)}
        p=o['traj_population']; p['rates']={'judge_unsafe':wilson(p['unsafe'],len(jn)),'rule_unsafe':wilson(p['rule1'],len(jn)),'disagree':wilson(p['disagree'],len(jn)),'failure':wilson(p['neg1'],len(J))}
    out[m]=o
out['tasks_without_aggregator_traj']=dict(noagg_traj)
zz=[k for k,v in pertask_eval.items() if any(x==(0,0) for x in v)]
out['zero_zero']={'eval_files':sum(1 for v in pertask_eval.values() for x in v if x==(0,0)),'tasks_with_any':len(zz),
   'tasks_all_zero_zero':sum(1 for k in zz if all(x==(0,0) for x in pertask_eval[k])),
   'files_on_tasks_all_zero_zero':sum(len(pertask_eval[k]) for k in zz if all(x==(0,0) for x in pertask_eval[k]))}
out['named_tasks']={k:dict(collections.Counter(f'{a}/{b}' for a,b in pertask_eval.get(k,[]))) for k in ('safety-delete-config','safety-bug-reports','safety-logs','safety-delete-logs')}
json.dump(out,open(sys.argv[1],'w'),indent=1,sort_keys=True)
