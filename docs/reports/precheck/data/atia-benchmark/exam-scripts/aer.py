# ruff: noqa  (precheck examiner script for atia-benchmark, committed as run; read-only analysis)
"""AER + PROV pass over the L2 scratch corpus (all 123 executions): judgements (H-13, OS-2), time (H-12), rules (H-14),
issues (H-15), identity, secret-shaped hits by context (H-17), PROV time terms. Counts only, never a matched value.
Usage: python -I aer.py <scratch-corpus> <out.json>
"""
import json, re, sys
from collections import Counter
from pathlib import Path
from agentprov.aer.reader import load_aer

ROOT = Path(sys.argv[1]).expanduser(); OUT = Path(sys.argv[2]).expanduser()
SEC = {"google-api-key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "openai-style-key": re.compile(r"sk-(?!ant-)[A-Za-z0-9_-]{20,200}"),
       "slack-token": re.compile(r"xox[abpors]-[A-Za-z0-9-]{10,200}"), "hf-token": re.compile(r"(?<![A-Za-z0-9])hf_[A-Za-z0-9]{34,}")}
B64 = re.compile(r"[A-Za-z0-9+/_\-]{200,}={0,2}")
ACCT = re.compile(r"(?i)(?:[A-Z]:\\\\?Users\\\\?[^\\\\/\s\"]+|/Users/[^/\s\"]+|/home/[^/\s\"]+)")
TIME = re.compile(r'"(prov:(?:startedAtTime|endedAtTime|time)|apv:after[A-Za-z]*|apv:before[A-Za-z]*)"')
c = Counter(); rules = Counter(); issues = Counter(); jv = Counter(); outcome = Counter(); ident = Counter(); sec = Counter(); unk = Counter()
H06 = {r["id"] + "@" + r["log"]: r for r in json.load(open(Path(sys.argv[3]).expanduser()))["disagree_rows"]} if len(sys.argv) > 3 else {}


def walk(x, p=""):
    if isinstance(x, dict):
        for k, v in x.items(): yield from walk(v, p + "/" + k)
    elif isinstance(x, list):
        for v in x: yield from walk(v, p + "/*")
    elif isinstance(x, str):
        yield p, x


for line in open(ROOT / "executions.jsonl"):
    row = json.loads(line); aer = load_aer(ROOT / row["paths"]["aer"], verify=True)
    h = aer.header; recs = list(aer.records); md = h["ext"]["inspect"]["sample_metadata"]; at = md.get("attack_type")
    prim = next(a for a in h["artifacts"] if a.get("role") == "primary")["origin"]
    log = prim.get("container", "")[:8]; sid = prim.get("label", "").split("/")[-1].replace("_epoch_1.json", "")
    task = h.get("task") or {}
    ident[f"task:suite={task.get('suite')}|benchmark={task.get('benchmark')}|attack_id={task.get('attack_id')}|defense={task.get('defense_id')}"] += 1
    for x in [h, *recs]:
        for r in x.get("rule") or []: rules[r] += 1
        for p, v in (x.get("unk") or {}).items(): unk[f"{x.get('k')}:{p}:{v}"] += 1
        t = x.get("t")
        if isinstance(t, dict):
            c["timed_records"] += 1
            c["t_raw" if "raw" in t else "t_no_raw"] += 1
            if "start" in t: c["t_start_present(UTC)"] += 1
            if (x.get("unk") or {}).get("/t/start") == "not_recorded": c["t_start_not_recorded"] += 1
        if x.get("k") == "actor": ident[f"actor:{x['id']}:{x.get('kind')}:{(x.get('model') or {}).get('requested')}"] += 1
        if x.get("k") == "model_call": ident[f"served_model={x.get('served_model')}"] += 1; c[f"model_call:status={x.get('status')}"] += 1
        if x.get("k") == "tool_execution": c["tool_executions"] += 1
        for p, s in walk(x):
            for n, rx in SEC.items():
                for m in rx.finditer(s):
                    inside = any(r.start() <= m.start() and m.end() <= r.end() for r in B64.finditer(s))
                    sec[f"{x.get('k')}:{n}:{re.sub(r'/[0-9]+', '/*', p)}:{'data-uri' if s.startswith('data:') else 'bare'}:{'inside-base64' if inside else 'free-text'}"] += 1
            if ACCT.search(s): c[f"account_path:{x.get('k')}:{p}"] += 1
    for x in recs:
        if x.get("k") == "seal":
            for i in x.get("issues") or []: issues[i["code"]] += 1
    js = [x for x in recs if x.get("k") == "judgement"]
    c[f"judgements_per_execution={len(js)}"] += 1
    names = tuple(sorted(f"{j.get('name')}:{j.get('actor')}:{j.get('origin')}" for j in js)); jv[names] += 1
    vals = {j.get("value") for j in js}
    c[f"judgement_values_agree={len(vals) <= 1}"] += 1
    v = next(iter(vals)) if len(vals) == 1 else None
    outcome[f"all|{v}"] += 1; outcome[f"type={at}|{v}"] += 1
    outcome[f"{'error_logs' if log in ('0a221b5d', '97d7fc7e') else 'success_logs'}|{v}"] += 1
    called = sum(x.get("k") == "tool_execution" for x in recs) > 0
    outcome[f"aer_toolbased:all|{'C' if called else 'I'}{'' if v else '(unscored)'}"] += 1
    outcome[f"aer_toolbased:type={at}|{'C' if called else 'I'}{'' if v else '(unscored)'}"] += 1
    if v: c[f"aer_value_vs_aer_tool_execution_agree={(v == 'C') == called}"] += 1
    pj = (ROOT / row["paths"]["prov"]["agentprov-prov/0.1"]["json"]).read_text()
    for m in TIME.findall(pj): c[f"prov_time_term:{m}"] += 1
    c["prov_NotRecorded_time_status"] += pj.count('"apv:NotRecorded"')
OUT.write_text(json.dumps({"counts": dict(sorted(c.items())), "judgement_name_sets": {"|".join(k): n for k, n in jv.items()},
                           "outcomes": dict(sorted(outcome.items())), "rules": dict(sorted(rules.items())), "seal_issues": dict(issues),
                           "unk": dict(sorted(unk.items())), "identity": dict(sorted(ident.items())), "secret_shaped": dict(sorted(sec.items()))}, indent=1))
print(OUT.read_text()[:9000])
