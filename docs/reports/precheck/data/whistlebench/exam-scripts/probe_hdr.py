"""Header structure probe: key paths of header.json/eval of one .eval (keys only, no values)."""
import io, sys, json
sys.path.insert(0, __file__.rsplit('/',1)[0])
from gitread import tree, read
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
t={k:v for k,v in tree().items() if k.endswith('.eval')}
lab=sorted(t)[int(sys.argv[1]) if len(sys.argv)>1 else 0]
with open_zip(io.BytesIO(read(t[lab])),IngestLimits(),release=False) as z:
    ms=list(iter_zip_members(z)); print(sorted({m.label.split('/')[0] for m in ms}))
    h=strict_json_loads(z.read_member(next(m for m in ms if m.label=='header.json')))
    ev=h['eval']; print(sorted(ev)); print('task_args', {k:(v if not isinstance(v,(dict,list)) else type(v).__name__) for k,v in (ev.get('task_args') or {}).items()})
    p=(ev.get('task_args') or {}).get('params')
    print('params', json.dumps(p)[:600] if p else None)
    print('revision keys', sorted(ev.get('revision') or {}), 'model_roles', sorted(ev.get('model_roles') or {}))
