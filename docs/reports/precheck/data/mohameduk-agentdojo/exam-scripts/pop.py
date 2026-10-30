"""Population scan of the 3,630 selected logs (staged checkout, via agentprov.ingest strict loader).
Counts only. Verifies each file's sha256 against the L1 row (which read the git pin)."""
import sys, os, json, hashlib
from collections import Counter, defaultdict
sys.path.insert(0, 'src')
from agentprov.ingest.loaders import strict_json_loads
W = os.path.expanduser('~/.agentprov/migration-work/precheck/mohameduk-agentdojo')
root = os.path.expanduser('~/.agentprov/staging/10c/mohameduk/agentdojo-3f9d69a1ea96b75e8695653ceee8c3ff088db9b3')
rows = [json.loads(l) for l in open(f'{W}/l1-units-head.jsonl')]
MEMBER = {'invite_user_to_slack', 'add_user_to_channel', 'remove_user_from_slack'}
C = defaultdict(Counter)          # per arm (pipeline_dir|attack_dir)
G = Counter()                     # global
err_forms = Counter()
cells = Counter(); meta_mismatch = Counter(); bver = Counter(); attack_types = Counter(); pkg = Counter()
it5 = defaultdict(Counter)
link = defaultdict(list)
hour = defaultdict(Counter)
h7 = []
per_log = {}
for r in rows:
    lab = r['label']; f = r['facets']
    data = open(os.path.join(root, lab), 'rb').read()
    if hashlib.sha256(data).hexdigest() != r['sha256']:
        G['sha_mismatch'] += 1; continue
    d = strict_json_loads(data)
    pd, ad, suite = f['pipeline_dir'], f['attack_dir'], f['suite']
    arm = f'{pd}|{ad}'
    defended = pd.endswith(('-ubag', '-ubag_behavioral'))
    # identity / meta
    ut = d.get('user_task_id'); it = d.get('injection_task_id')
    cells[(pd, suite, ut, it)] += 1
    if d.get('pipeline_name') != pd: meta_mismatch['pipeline_name'] += 1
    if d.get('suite_name') != suite: meta_mismatch['suite_name'] += 1
    if ut != f['task_dir']: meta_mismatch['user_task_id'] += 1
    if (it or 'none') != f['file']: meta_mismatch['injection_task_id'] += 1
    if (d.get('attack_type') or 'none') != ad: meta_mismatch['attack_type'] += 1
    attack_types[str(d.get('attack_type'))] += 1
    bver[(ad, str(d.get('benchmark_version')))] += 1
    pkg[str(d.get('agentdojo_package_version'))] += 1
    msgs = d.get('messages') or []
    n_gov = n_blk = n_rev = n_oth = n_exec = 0
    for i, m in enumerate(msgs):
        if m.get('role') != 'tool': continue
        n_gov += 1
        e = m.get('error')
        fn = (m.get('tool_call') or {}).get('function')
        if e in (None, ''):
            n_exec += 1
        elif isinstance(e, str) and e.startswith('ubag-blocked'):
            form = e if len(e) < 40 else e[:22] + '...'
            err_forms[(defended, form)] += 1
            if e == 'ubag-blocked: BLOCK': n_blk += 1
            elif e == 'ubag-blocked: REVIEW': n_rev += 1
            else: n_oth += 1; err_forms[('ubag_other', len(e))] += 1
        else:
            n_oth += 1; err_forms[(defended, 'other_tool_error')] += 1
        if fn == 'post_webpage' and isinstance(e, str) and e.startswith('ubag-blocked'):
            h7.append((pd, suite, ut, it, d.get('utility') is not None))
    c = C[arm]
    c['logs'] += 1; c['tool_msgs'] += n_gov; c['blocked'] += n_blk; c['review'] += n_rev; c['other_err'] += n_oth; c['executed'] += n_exec
    if n_gov and n_exec == 0: c['logs_all_tool_msgs_refused'] += 1
    if n_gov == 0: c['logs_no_tool_msg'] += 1
    if n_blk + n_rev: c['logs_with_refusal'] += 1
    ts = d.get('evaluation_timestamp') or ''
    hour[pd][ts[:13]] += 0
    hb = hour[pd]; hb[(ts[:13], 'tool')] += n_gov; hb[(ts[:13], 'exec')] += n_exec
    # H3: slack injection_task_5
    if suite == 'slack' and it == 'injection_task_5':
        k = it5[pd]; k['n'] += 1; k['security_true'] += bool(d.get('security'))
        proposed = sum(1 for m in msgs if m.get('role') == 'assistant' for tc in (m.get('tool_calls') or []) if tc.get('function') in MEMBER)
        executed = sum(1 for m in msgs if m.get('role') == 'tool' and (m.get('tool_call') or {}).get('function') in MEMBER and m.get('error') in (None, ''))
        refused = sum(1 for m in msgs if m.get('role') == 'tool' and (m.get('tool_call') or {}).get('function') in MEMBER and isinstance(m.get('error'), str) and m['error'].startswith('ubag-blocked'))
        k['proposed'] += proposed; k['executed'] += executed; k['refused'] += refused
        if d.get('security'): k['sec_true_executed_member'] += executed; k['sec_true_proposed'] += proposed; k['sec_true_refused'] += refused
    # H6: multi-call turns with null ids and repeated tool result contents
    for i, m in enumerate(msgs):
        tcs = m.get('tool_calls') or []
        if m.get('role') == 'assistant' and len(tcs) >= 2 and any(tc.get('id') in (None, '') for tc in tcs):
            res = []
            j = i + 1
            while j < len(msgs) and msgs[j].get('role') == 'tool':
                res.append(json.dumps(msgs[j].get('content'), sort_keys=True) + '|' + str(msgs[j].get('error'))); j += 1
            c['multicall_null_id_turns'] += 1
            if len(res) != len(set(res)):
                link[arm].append(lab); c['multicall_null_id_repeated_result'] += 1
                break
G['logs'] = len(rows)
dups = {str(k): v for k, v in cells.items() if v > 1}
out = {
  'format': 'mohameduk-agentdojo-exam-pop/1', 'denominator_logs': len(rows), 'sha_mismatch': G['sha_mismatch'],
  'per_arm': {k: dict(v) for k, v in sorted(C.items())},
  'refusal_forms': {f'{k[0]}|{k[1]}': v for k, v in sorted(err_forms.items(), key=str)},
  'cells_duplicated': len(dups), 'cells': len(cells), 'meta_mismatch': dict(meta_mismatch),
  'attack_type': dict(attack_types), 'benchmark_version_by_attack': {f'{a}|{b}': v for (a, b), v in bver.items()},
  'package_version': dict(pkg),
  'slack_it5': {k: dict(v) for k, v in sorted(it5.items())},
  'h6_repeated_result_logs_by_arm': {k: len(v) for k, v in sorted(link.items())},
  'h6_labels': {k: v for k, v in sorted(link.items())},
  'h7_refused_post_webpage': Counter(f'{a}|{b}|utility_recorded={e}' for a, b, c_, d_, e in h7),
  'hour_blocks': {pd: {h: {'tool': hb[(h, 'tool')], 'exec': hb[(h, 'exec')]} for h in sorted({k for k in hb if isinstance(k, str)})} for pd, hb in hour.items()},
}
json.dump(out, open(sys.argv[1], 'w'), indent=1, sort_keys=True, default=str)
print(json.dumps({k: v for k, v in out.items() if k not in ('hour_blocks', 'h6_labels')}, indent=1, sort_keys=True, default=str))
