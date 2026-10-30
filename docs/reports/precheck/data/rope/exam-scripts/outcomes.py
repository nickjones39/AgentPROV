import json, sys, collections, importlib.util
spec = importlib.util.spec_from_file_location("lib", "tools/analysis2/exam2_lib.py")
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
S = sys.argv[1]
L1 = json.load(open(f'{S}/l1_cells.json')); ST = json.load(open(f'{S}/stored_cells.json'))
DOJO = ('banking', 'slack', 'travel'); DYN = ('github', 'shopping', 'dailylife')
def cell(md, att, su):
    a = L1.get(f'{md}|{att}|{su}', {}); b = ST.get(f'{md}|{att}|{su}', {})
    return {'n': a.get('n', 0), 'u': a.get('utility:True', 0), 's': a.get('security:True', 0) if att != 'none' else 0, 'sc': b.get('corr_true', 0)}
def w(k, n): lo, hi = lib.wilson(k, n); return f"[{100*lo:.1f}, {100*hi:.1f}]"
rows = []
def add(arm, level, n, k, metric, paper, src, extra=''):
    rate = 100 * k / n if n else float('nan')
    gap = None if paper is None else rate - paper
    lo, hi = lib.wilson(k, n)
    flag = False
    if paper is not None:
        if level == 'L1-population':
            flag = abs(gap) > 15 and n >= 20 or (paper / 100 < lo - 0.05 or paper / 100 > hi + 0.05)
        else:
            flag = n >= 20 and (abs(gap) > 15 or paper / 100 < lo - 0.05 or paper / 100 > hi + 0.05)
    rows.append({'arm': arm, 'level': level, 'n': n, 'k': k, 'metric': metric, 'rate': f"{rate:.2f}", 'wilson95': w(k, n),
                 'paper': 'n/a' if paper is None else f"{paper:.2f} ({src})", 'gap_pp': 'n/a' if gap is None else f"{gap:+.2f}", 'flag': bool(flag), 'note': extra})
# AP micro raw rates (Tables 6/9)
AP = {('gpt-4o-mini', 'important_instructions', 'agentdojo'): (6.4, 45.5), ('gpt-4o-mini', 'autodojo', 'agentdojo'): (4.4, 49.6),
      ('gemini-2.5-flash', 'important_instructions', 'agentdojo'): (3.3, 51.7), ('gemini-2.5-flash', 'autodojo', 'agentdojo'): (3.9, 50.6),
      ('gpt-4o-mini', 'important_instructions', 'agentdyn'): (2.1, 36.1), ('gpt-4o-mini', 'autodojo', 'agentdyn'): (2.9, 33.6),
      ('gemini-2.5-flash', 'important_instructions', 'agentdyn'): (1.6, 20.9), ('gemini-2.5-flash', 'autodojo', 'agentdyn'): (0.7, 12.3)}
for (md, att, bm), (asr, ua) in AP.items():
    su = DOJO if bm == 'agentdojo' else DYN
    cs = [cell(md, att, s) for s in su]; n = sum(c['n'] for c in cs)
    add(f'{md}|rope|{att}|{bm}', 'L1-population', n, sum(c['s'] for c in cs), 'ASR raw (micro, AP)', asr, 'AP T6/T9')
    add(f'{md}|rope|{att}|{bm}', 'L1-population', n, sum(c['u'] for c in cs), 'UA (micro, AP)', ua, 'AP T6/T9')
# RP macro corrected (unweighted mean of 3 suites) and CU
RPc = {('gpt-4o-mini','important_instructions','agentdojo'): None}
RPmacro = {  # (md, att, bm): (corrected ASR macro, UA macro)
    ('qwen3-235b','important_instructions','agentdojo'): (4.6, 57.6), ('qwen3-235b','autodojo','agentdojo'): (5.0, 58.5),
    ('qwen3-235b','important_instructions','agentdyn'): (2.6, 46.3), ('gpt-4o','important_instructions','agentdyn'): (2.4, 45.0),
    ('gpt-4o-mini','important_instructions','agentdyn'): (None, 36.6), ('gemini-2.5-flash','important_instructions','agentdyn'): (None, 20.9),
    ('gpt-4o-mini','autodojo','agentdyn'): (None, 34.3), ('gemini-2.5-flash','autodojo','agentdyn'): (None, 12.5), ('qwen3-235b','autodojo','agentdyn'): (None, 39.1),
    ('gpt-4o-mini','important_instructions','agentdojo'): (None, 45.6), ('gemini-2.5-flash','important_instructions','agentdojo'): (None, 51.7),
    ('gpt-4o-mini','autodojo','agentdojo'): (None, 50.2), ('gemini-2.5-flash','autodojo','agentdojo'): (None, 52.2)}
macro_rows = []
for (md, att, bm), (asr, ua) in RPmacro.items():
    su = DOJO if bm == 'agentdojo' else DYN
    cs = [cell(md, att, s) for s in su]
    m_ua = sum(100 * c['u'] / c['n'] for c in cs) / 3; m_sc = sum(100 * c['sc'] / c['n'] for c in cs) / 3
    macro_rows.append({'arm': f'{md}|rope|{att}|{bm}', 'level': 'L1-population (macro)', 'n': sum(c['n'] for c in cs), 'UA_macro': f"{m_ua:.2f}", 'UA_paper': ua,
                       'ASRcorr_macro': f"{m_sc:.2f}", 'ASRcorr_paper': asr, 'gap_UA_pp': f"{m_ua-ua:+.2f}", 'gap_ASR_pp': 'n/a' if asr is None else f"{m_sc-asr:+.2f}"})
CU = {'gpt-4o-mini': {'banking': 50.0, 'slack': 66.7, 'travel': 60.0, 'github': 60.0, 'shopping': 35.0, 'dailylife': 35.0},
      'gemini-2.5-flash': {'banking': 50.0, 'slack': 85.7, 'travel': 40.0, 'github': 20.0, 'shopping': 15.0, 'dailylife': 40.0}}
for md, d in CU.items():
    for su, p in d.items():
        c = cell(md, 'none', su); add(f'{md}|rope|none|{su}', 'L1-population', c['n'], c['u'], 'CU', p, 'AP T6/T9; RP T2/T13')
for md, bm, p in (('qwen3-235b', 'agentdyn', 53.3), ('gpt-4o', 'agentdyn', 53.3)):
    cs = [cell(md, 'none', s) for s in DYN]; add(f'{md}|rope|none|{bm}', 'L1-population', sum(c['n'] for c in cs), sum(c['u'] for c in cs), 'CU', p, 'RP T2/T11')
cs = [cell('qwen3-235b', 'none', s) for s in DOJO]
macro_rows.append({'arm': 'qwen3-235b|rope|none|agentdojo', 'level': 'L1-population (macro)', 'n': 57, 'CU_macro': f"{sum(100*c['u']/c['n'] for c in cs)/3:.2f}", 'CU_paper': 67.9})
# LH
for md in ('gpt-4o-mini', 'gemini-2.5-flash', 'qwen3-235b'):
    cs = [cell(md, 'agentlab_longhorizon', s) for s in DOJO]; add(f'{md}|rope|long_horizon|agentdojo', 'L1-population', sum(c['n'] for c in cs), sum(c['s'] for c in cs), 'ASR raw', 0.0, 'RP T3', 'n includes the 2 empty logs (security null) for gpt-4o-mini/qwen')
# Ablation T4 and router T5 (corrected ASR, CU), per suite
T4 = {'ablation/always-fully-specified': {'github': (40.0, 0.0), 'shopping': (20.0, 5.0), 'dailylife': (20.0, 0.5)},
      'ablation/always-action-open': {'github': (65.0, 35.0), 'shopping': (30.0, 28.9), 'dailylife': (35.0, 68.0)},
      'router/gemini-3-flash': {'github': (55.0, 1.7), 'shopping': (35.0, 5.0), 'dailylife': (30.0, 6.0)},
      'router/gpt-oss-20b': {'github': (40.0, 1.1), 'shopping': (40.0, 7.2), 'dailylife': (35.0, 0.5)},
      'router/gemini-3-flash-clamp': {'dailylife': (None, 0.0)}, 'router/gpt-oss-20b-clamp': {'dailylife': (None, 0.5)}}
for md, d in T4.items():
    for su, (cu, asr) in d.items():
        c = cell(md, 'none', su); a = cell(md, 'important_instructions', su)
        if cu is not None: add(f'{md}|none|{su}', 'L1-population', c['n'], c['u'], 'CU', cu, 'RP T4' if 'ablation' in md else 'RP T5')
        add(f'{md}|important_instructions|{su}', 'L1-population', a['n'], a['sc'], 'ASR corrected', asr, 'RP T4' if 'ablation' in md else 'RP T5', 'corrected = stored rope-p10 recomputed judgement (sample shows 0 value changes at main)')
# Sample (OS-2): pooled arms over main-tree models; expected = sample-weighted population per-(model,suite) rate (= paper where reported)
def sample(path, tag):
    per = json.load(open(path))['per']
    pool = collections.defaultdict(list)
    for p in per:
        bm = 'agentdojo' if p['suite'] in DOJO else 'agentdyn'
        tree = 'ablation/router' if '/' in p['model_dir'] else 'main'
        pool[(tree, p['attack_dir'], bm)].append(p)
    for (tree, att, bm), ps in sorted(pool.items()):
        n = len(ps)
        def exp(metric):
            tot = 0
            for p in ps:
                c = cell(p['model_dir'], p['attack_dir'], p['suite'])
                tot += (c['u'] if metric == 'u' else c['s'] if metric == 's' else c['sc']) / c['n']
            return 100 * tot / n
        arm = f'{tag}:{tree}|{att}|{bm}'
        add(arm, 'L2-sample', n, sum(1 for p in ps if p['aer_u'] is True), 'utility (CU if none, UA if attacked)', exp('u'), 'pop-weighted (=paper where reported)')
        if att != 'none':
            add(arm, 'L2-sample', n, sum(1 for p in ps if p['aer_s'] is True), 'ASR raw (recorded)', exp('s'), 'pop-weighted (=AP where reported)')
            add(arm, 'L2-sample', n, sum(1 for p in ps if p['aer_s_corr'] is True), 'ASR corrected (recomputed)', exp('c'), 'pop-weighted (=RP where reported)')
sample(f'{S}/sample-head.json', 'head'); sample(f'{S}/sample-slice.json', 'rope-slice')
json.dump({'rows': rows, 'macro': macro_rows}, open(sys.argv[2], 'w'), indent=1)
for r in rows: print(r['level'], r['arm'], r['metric'], r['n'], r['k'], r['rate'], r['wilson95'], r['paper'], r['gap_pp'], 'FLAG' if r['flag'] else '')
for m in macro_rows: print(m)
