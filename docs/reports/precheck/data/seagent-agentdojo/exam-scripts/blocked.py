"""Blocked-call anatomy: the tool message answering a `<fn>BLOCKED_BY_SEAGENT` call (error field, content shape) and
the skipped calls of its batch (counts per arm). Result prefixes (24 chars) are counted by digest; only the most common is
printed, fenced by quote_untrusted."""
import collections, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import units, raw, result_id
from agentprov.ingest.quote import quote_untrusted
import hashlib
PFX = {}
BL = "BLOCKED_BY_SEAGENT"; o = collections.defaultdict(collections.Counter)
for u in units():
    a = u['facets']['arm'].replace('seagent-rf', 'seagent-RF'); x = raw(u['sha256']); ms = x['messages']
    for i, m in enumerate(ms):
        cs = m.get('tool_calls') or []
        bl = [c for c in cs if str(c.get('function', '')).endswith(BL)]
        if not bl: continue
        o['blocked_batches'][a] += 1; o['blocked_calls_per_batch'][len(bl)] += 1
        o['batch_size'][len(cs)] += 1
        j = i + 1; rs = []
        while j < len(ms) and ms[j].get('role') == 'tool': rs.append(ms[j]); j += 1
        o['results_in_batch'][len(rs)] += 1
        o['blocked_is_last_assistant'][str(all(mm.get('role') != 'assistant' for mm in ms[i + 1:]))] += 1
        for r in rs:
            fn = (r.get('tool_call') or {}).get('function', '')
            o['result_fn_blocked'][str(fn.endswith(BL))] += 1
            o['result_error_null'][str(r.get('error') is None)] += 1
            c = r.get('content'); txt = c if isinstance(c, str) else ''.join(b.get('content', '') for b in (c or []) if isinstance(b, dict))
            h = hashlib.sha256(txt[:24].encode()).hexdigest()[:12]; PFX.setdefault(h, txt[:24]); o['result_prefix24_digest'][h] += 1
        o['skipped_calls'][a] += len(cs) - len(rs)
        o['next_role'][ms[j].get('role') if j < len(ms) else 'end'] += 1
r = {k: dict(v.most_common(8)) for k, v in o.items()}
top = o['result_prefix24_digest'].most_common(1)
if top: print(quote_untrusted(PFX[top[0][0]], 'seagent:blocked-result-prefix24'))
json.dump(r, open(sys.argv[1], 'w'), indent=1); print(json.dumps(r))
