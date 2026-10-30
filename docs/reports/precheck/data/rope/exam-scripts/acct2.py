import re, os, sys, hashlib
from agentprov.ingest.loaders import strict_json_loads
ROOT=os.path.expanduser('~/Desktop/PhD/Labs/AgentPROV-upstream/rope')
rx=re.compile(r"/(?:home|Users)/([^/\s\"'<>\\]{1,64})/")
for lab in sys.argv[1:]:
    obj=strict_json_loads(open(os.path.join(ROOT,lab),'rb').read())
    msgs=obj['messages']
    prompt=' '.join(str(m.get('content')) for m in msgs if m.get('role') in ('system','user')).lower()
    tools=' '.join(str(m.get('content')) for m in msgs if m.get('role')=='tool').lower()
    names=set()
    for m in msgs:
        for c in (m.get('tool_calls') or []):
            for mm in rx.finditer(str(c.get('args'))): names.add(mm.group(1))
    for n in names:
        first_tool_idx = next((i for i,m in enumerate(msgs) if m.get('role')=='tool' and n.lower() in str(m.get('content')).lower()), None)
        first_call_idx = next((i for i,m in enumerate(msgs) if m.get('role')=='assistant' and n in str(m.get('tool_calls'))), None)
        print(lab.split('/')[1:4], 'acct#'+hashlib.sha256(n.encode()).hexdigest()[:8], 'name_in_prompt', n.lower() in prompt, 'name_in_env_output_before_call', first_tool_idx is not None and first_call_idx is not None and first_tool_idx < first_call_idx, 'generic', n.lower() in ('user','ubuntu','root','admin'))
