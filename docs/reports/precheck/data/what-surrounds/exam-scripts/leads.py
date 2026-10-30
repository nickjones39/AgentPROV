"""Leads: silent csv vs meta (incl. the 16 short-shape runs), double attacker sends, tool_result runs without read,
H-10 cell, toolConfig count without run 0001. Labels and counts only."""
import sys, csv, io, json, collections, re, hashlib
sys.path.insert(0, sys.argv[1]); from rawzip import members, runs, js
from agentprov.ingest.loaders import strict_json_loads
C = collections.Counter; mem = members(); R = runs(mem)
rows = {r['run_id']: r for r in csv.DictReader(io.StringIO(mem['results.csv'].decode('utf-8'), newline=''))}
A = C(js(f['meta.json']).get('attacker_address') for f in R.values()).most_common(2); A = [a for a, _ in A if a][0]
out = C(); dbl = C(); noread = []; h10 = []; cfg = C(); sil = C()
for d, f in R.items():
    model, arm, num = re.fullmatch(r'(.+?)__(.+)__(\d{4})', d).groups(); meta = js(f['meta.json']); r = rows[d]
    tc = [l.partition(' ') for l in f['tools_called.txt'].decode().splitlines() if l.strip()]
    to = []
    for n, _, a in tc:
        if n == 'send_email':
            try: to.append(strict_json_loads(a.encode()).get('to'))
            except Exception: to.append(None)
    if to.count(A) > 1: dbl[f'{model}|{arm}'] += 1
    if r['channel'] == 'tool_result' and arm != 'clean' and not any(n == 'read_file' for n, _, _ in tc): noread.append(f'{model}|{arm}|{num}|sends={len(to)}|hijack={r["hijack"]}')
    if f['outcome.txt'].decode().strip().startswith('forwarded') and r['hijack'] == '0': h10.append(f'{model}|{arm}|{num}')
    if arm == 'mcptox_p2' and model.startswith('claude'):
        short = 'disclosed_send' not in meta
        sil[(model, 'short' if short else 'full', 'hij=' + r['hijack'], 'csv_sil=' + r['silent'], 'meta_sil=' + str(meta.get('silent')), 'has_fut=' + str('final_user_text.txt' in f))] += 1
    if 'silent' in meta: out['meta_vs_csv_silent_' + ('eq' if (bool(meta['silent']) == (r['silent'] == '1')) else 'ne')] += 1
    for q in js(f['request.json']):
        if num != 1: cfg[hashlib.sha256(json.dumps(q.get('toolConfig'), sort_keys=True).encode()).hexdigest()[:12]] += 1
print(json.dumps({'meta_vs_csv': dict(out), 'double_attacker_send_cells': dict(dbl), 'tool_result_no_read': noread, 'h10_forward_label_no_hijack': h10,
                  'toolconfigs_excluding_run_0001': len(cfg), 'claude_p2_silent': {'|'.join(k): v for k, v in sorted(sil.items())}}, indent=0))
