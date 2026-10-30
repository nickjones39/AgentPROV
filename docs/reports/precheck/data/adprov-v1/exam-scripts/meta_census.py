"""adprov-v1 release raw meta census for prereg H6-H11 (counts only; strict agentprov.ingest parse; no values written).
Usage: uv run python -I meta_census.py <repo>/src <tree root> <out.json>"""
import sys, json, collections, datetime
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from agentprov.ingest.loaders import strict_json_loads
root, out = Path(sys.argv[2]).expanduser(), Path(sys.argv[3])
C = collections.Counter(); first = {}
H9_MC = ('malformed_tool_calls', 'upstream_errors', 'discarded_usage', 'response', 'reasoning_effort', 'abnormal_finish')
for p in sorted(root.glob('*/prov/*/*.transcript.json')):
    mf = p.parts[-4]; d = strict_json_loads(p.read_bytes()); meta = d.get('meta') or {}; mc = meta.get('model_config')
    turns = d.get('turns') or []
    n_ast = sum(1 for t in turns if isinstance(t, dict) and t.get('role') == 'assistant')
    C[('h10_model_config_present', mf, isinstance(mc, dict))] += 1
    if isinstance(mc, dict):
        C[('h10_temperature', mf, repr(mc.get('temperature')))] += 1
        n = (mc.get('usage') or {}).get('n_llm_calls') if isinstance(mc.get('usage'), dict) else None
        C[('h10_n_llm_calls_present', mf, isinstance(n, int))] += 1
        if isinstance(n, int) and n > n_ast: C[('h6_calls_gt_assistant', mf)] += 1
        fr = mc.get('finish_reasons')
        if isinstance(fr, list):
            ab = [x for x in fr if x not in ('stop', 'tool_calls')]
            if ab: C[('h7_trace_with_abnormal_incl_null', mf)] += 1
            if [x for x in ab if x is not None]: C[('h7_trace_with_abnormal_nonnull', mf)] += 1
            for x in ab: C[('h7_value', repr(x)[:20])] += 1
        for k in H9_MC:
            if k in mc: C[('h9_model_config_key', k)] += 1
    for k in ('n_attempts', 'capture'):
        if k in meta: C[('h9_meta_key', k)] += 1
    if 'discarded_attempts' in d: C[('h9_top_key', 'discarded_attempts')] += 1
    s, e, w = meta.get('started_at'), meta.get('ended_at'), meta.get('wall_clock_s')
    try:
        ds, de = datetime.datetime.fromisoformat(s), datetime.datetime.fromisoformat(e)
        day = ds.date().isoformat(); first[mf] = min(first.get(mf, day), day)
        C[('h11_in_range', '2026-06-05' <= day < '2026-06-29')] += 1
        if isinstance(w, (int, float)): C[('h11_wall_within_1s', abs(w - (de - ds).total_seconds()) <= 1)] += 1
    except Exception: C[('h11_parse_fail',)] += 1
    C[('h14_folder_model_id', mf, str(meta.get('model_id'))[:60])] += 1
out.write_text(json.dumps({'counts': [[*k, v] for k, v in sorted(C.items(), key=str)], 'first_start_day': first}, indent=1) + '\n')
