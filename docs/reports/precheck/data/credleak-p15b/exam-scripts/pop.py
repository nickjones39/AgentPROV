"""credleak-p15b whole-population raw census (prereg H1-H3, H5-H12, H15) over the 643 cells of the pinned v3 zip,
read through agentprov.ingest (rawlib). Counts, labels, field classes and truncated digests only; no value, no name.
Usage: python -I pop.py <exam-scripts dir> <worktree root> <out.json>
"""
import sys, re, json, csv, io, os, hashlib, collections, tomllib
from datetime import datetime
sys.path.insert(0, sys.argv[1]); from rawlib import cells, members
ROOT, OUT = sys.argv[2], sys.argv[3]
C = collections.Counter
tables = tomllib.load(open(f"{ROOT}/src/agentprov/adapters/credleak/semantics/credleak.tools-1/tables.toml", "rb"))
LISTED = {t["name"] for t in tables.get("tool", [])}
WH = {"canary-tag": re.compile("CANARY[^_]"), "canary-tag-left": re.compile("[^_/]CANARY"),
      "aws-key-shape": re.compile("AKIA[0-9A-Z]{16}"), "sk-key-shape": re.compile(r"sk-[A-Za-z0-9_\-]{20,256}")}
TAG = re.compile("CANARY"); AWS = WH["aws-key-shape"]; ANT = re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"); SK = WH["sk-key-shape"]
ACC = {"users-dir": re.compile(r"/Users/([^/\s\"'<>\\]{1,64})/"), "home-dir": re.compile(r"/home/([^/\s\"'<>\\]{1,64})/")}
sys.path.insert(0, f"{ROOT}/tools/precheck"); from l1_scan import GENERIC_ACCOUNTS
TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$"); RID = re.compile(r"^\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-\d{3}Z$")
OPER = hashlib.sha256(os.path.basename(os.path.expanduser("~")).encode()).hexdigest()[:12]
sample = set(json.load(open(f"{ROOT}/docs/reports/precheck/data/credleak-p15b/l2-sample-head.json"))["labels"])

def layout(label):
    p = label.split("/"); f = p[-1]
    if any(x.startswith("_") for x in p[2:-1]): return "underscore:" + [x for x in p[2:-1] if x.startswith("_")][0][:22]
    pre = "excluded:" if "excluded-models" in p else "roster:"
    for k in ("run__", "archive-", "addendum-", "extcanary__"):
        if f.startswith(k): return pre + k.rstrip("_-")
    return pre + "other"
def model_dir(label):
    p = label.split("/")
    return p[-2] if not p[-2].startswith("_") else "<none>"
def strings(o, ptr):
    if isinstance(o, str): yield ptr, o
    elif isinstance(o, dict):
        for k, v in o.items(): yield from strings(v, ptr)
    elif isinstance(o, list):
        for v in o: yield from strings(v, ptr)
def field_strings(run):
    for t in run.get("turns", []):
        yield "assistant", t.get("assistantResponse") or ""
        yield "user", t.get("userMessage") or ""
        for x in t.get("canariesFound") or []:
            if isinstance(x, str): yield "detector", x
        for c in t.get("toolCalls") or []:
            yield "tool_name", c.get("tool") or ""
            for _, s in strings(c.get("input"), ""): yield "tool_input", s
            yield "tool_output", c.get("output") or ""
    for k, v in run.items():
        if k != "turns":
            for _, s in strings(v, ""): yield "run_fields", s
def ts(s): return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ")

R = dict(layout_cells=C(), layout_runs=C(), turns_per_run=C(), runs=0, turns=0, calls=0, cells=0, run_model_mismatch=0,
         run_scenario_mismatch=0, repetition_mismatch=0, model_strings=C(), model_vs_dir=C(), tallies=collections.defaultdict(C),
         invocation_error=0, no_call_runs=0, zero_turn_runs=0, empty_response_runs=0, empty_response_by_model=C(),
         intent_verdicts_nonempty=0, extcanary_runs=0, extcanary_exfil=0, ts_shape_bad=C(), ts_missing=0, ts_decrease_runs=0,
         ts_pairs_within_run=0, ts_range=[None, None], ts_out_of_range=0, run_pairs=0, overlap_pairs=0,
         malformed_calls=0, malformed_names=set(), placeholder_names=C(), tag_by_field=C(), shapes=C(), untagged_shape_strings=0,
         untagged_shape_runs=0, value_runs=0, value_cells=0, value_runs_sampled=0, value_cells_sampled=0, runs_sampled=0,
         released_runs_in_value_cells=0, defence=C(), technique_cells=C())
acc = collections.defaultdict(lambda: dict(strings=0, cells=set(), runs=0, fields=C(), techniques=set(), models=set(),
                                           layouts=set(), in_user_msg=0, kind=None, length=0, operator=False))
pc = collections.defaultdict(lambda: C())  # csv key -> counts
run_calls = {}
for label, d in cells():
    R["cells"] += 1; lay = layout(label); R["layout_cells"][lay] += 1; R["defence"][d.get("defence")] += 1
    R["technique_cells"][d.get("technique")] += 1
    R["model_vs_dir"][("eq" if d["model"] == model_dir(label) else f"{lay}|{model_dir(label)}->{d['model']}")] += 1
    if not RID.match(d.get("runId", "")): R["ts_shape_bad"]["runId"] += 1
    if not TS.match(d.get("timestamp", "")): R["ts_shape_bad"]["cell"] += 1
    vb_cell = 0; prev_end = None; runs = d.get("runs", [])
    sec = label.split("/")[1]
    mcsv = d["model"].replace("eu.anthropic.claude-", "anthropic.").replace("claude-", "")
    for i, r in enumerate(runs):
        R["runs"] += 1; R["layout_runs"][lay] += 1; R["model_strings"][r.get("model")] += 1
        R["runs_sampled"] += label in sample
        if r.get("model") != d.get("model"): R["run_model_mismatch"] += 1
        if r.get("scenarioId") != d.get("scenario"): R["run_scenario_mismatch"] += 1
        if r.get("repetition") != i + 1: R["repetition_mismatch"] += 1
        turns = r.get("turns", []); R["turns"] += len(turns); R["turns_per_run"][len(turns)] += 1
        if not turns: R["zero_turn_runs"] += 1
        nc = sum(len(t.get("toolCalls") or []) for t in turns); R["calls"] += nc; run_calls[f"{label}#/runs/{i}"] = nc
        if nc == 0: R["no_call_runs"] += 1
        if r.get("invocationError") is True: R["invocation_error"] += 1
        if turns and all(not (t.get("assistantResponse") or "").strip() for t in turns) and nc == 0:
            R["empty_response_runs"] += 1; R["empty_response_by_model"][r.get("model")] += 1
        if any(v is not None for v in (r.get("intentVerdicts") or [])): R["intent_verdicts_nonempty"] += 1
        for k in ("hijackSucceeded", "exfiltrationDetected", "agentDetected", "displayedToUser", "maliciousArtifactEmitted",
                  "scriptAudited", "payloadDelivered"):
            R["tallies"][k][str(r.get(k))] += 1
        if lay.endswith("extcanary"):
            R["extcanary_runs"] += 1; R["extcanary_exfil"] += r.get("exfiltrationDetected") is True
        # csv key (errored runs counted apart)
        k = (sec, mcsv, d.get("technique"), d.get("scenario")); p = pc[(k, lay)]
        p["N"] += 1; p["errored"] += r.get("invocationError") is True
        if r.get("invocationError") is not True:
            p["exfil"] += r.get("exfiltrationDetected") is True; p["mae"] += r.get("maliciousArtifactEmitted") is True
            p["saf"] += r.get("scriptAudited") is False; p["pd"] += r.get("payloadDelivered") is True
        p["exfil_all"] += r.get("exfiltrationDetected") is True
        # timestamps
        tl = []
        for t in turns:
            s = t.get("timestamp")
            if not isinstance(s, str): R["ts_missing"] += 1; continue
            if not TS.match(s): R["ts_shape_bad"]["turn"] += 1; continue
            x = ts(s); tl.append(x)
            lo, hi = R["ts_range"]; R["ts_range"] = [min(lo or s, s), max(hi or s, s)]
            if not ("2026-05-01" <= s[:10] <= "2026-09-14"): R["ts_out_of_range"] += 1
        R["ts_pairs_within_run"] += max(0, len(tl) - 1)
        if any(b < a for a, b in zip(tl, tl[1:])): R["ts_decrease_runs"] += 1
        if tl:
            if prev_end is not None:
                R["run_pairs"] += 1; R["overlap_pairs"] += tl[0] < prev_end
            prev_end = tl[-1]
        # tool names
        for t in turns:
            for c in t.get("toolCalls") or []:
                n = c.get("tool")
                if n not in LISTED: R["malformed_calls"] += 1; R["malformed_names"].add(n)
                if n in ("-", "0", "nan", "", None): R["placeholder_names"][repr(n)] += 1
        # tags, shapes, value-bearing, accounts
        vb = False; untag = 0
        for fld, s in field_strings(r):
            if not s: continue
            n = len(TAG.findall(s))
            if n: R["tag_by_field"][fld] += n
            for nm, rx in (("aws", AWS), ("anthropic", ANT)): R["shapes"][nm] += len(rx.findall(s))
            R["shapes"]["sk_other"] += sum(1 for m in SK.findall(s) if not m.startswith("sk-ant-"))
            for rx in (AWS, SK):
                for m in rx.finditer(s):
                    if "CANARY" not in s[max(0, m.start() - 40): m.end() + 40]: untag += 1
            if not vb and any(rx.search(s) for rx in WH.values()): vb = True
            for kind, rx in ACC.items():
                for m in rx.finditer(s):
                    name = m.group(1)
                    if name.lower() in GENERIC_ACCOUNTS or (kind == "users-dir" and name.lower() == "shared"): continue
                    dg = hashlib.sha256(name.encode("utf-8", "surrogatepass")).hexdigest()[:12]
                    a = acc[f"{kind}:{dg}"]; a["strings"] += 1; a["cells"].add(label); a["fields"][fld] += 1
                    a["techniques"].add(d.get("technique")); a["models"].add(d.get("model")); a["layouts"].add(lay)
                    a["length"] = len(name); a["operator"] = dg == OPER
                    a["shape"] = "lower" if name.islower() else ("capitalised" if name[:1].isupper() else "mixed")
                    a["has_digit"] = any(ch.isdigit() for ch in name)
        if untag: R["untagged_shape_strings"] += untag; R["untagged_shape_runs"] += 1
        if vb: R["value_runs"] += 1; vb_cell += 1; R["value_runs_sampled"] += label in sample
    if vb_cell:
        R["value_cells"] += 1; R["value_cells_sampled"] += label in sample
        R["released_runs_in_value_cells"] += len(runs) - vb_cell
# per-account run counts (cells x runs is approximate: count cells)
accounts = {k: dict(strings=v["strings"], cells=len(v["cells"]), fields=dict(v["fields"]), techniques=sorted(v["techniques"]),
                    models=len(v["models"]), layouts=sorted(v["layouts"]), name_length=v["length"], shape=v.get("shape"),
                    has_digit=v.get("has_digit"), operator=v["operator"], sampled_cells=len(v["cells"] & sample))
            for k, v in sorted(acc.items())}
# csv reconciliation
csvres = {}
for lbl, data in members(lambda l: l in ("p15b-run-data/per-cell-counts.csv", "p15b-run-data/per-cell-counts-v2.csv")):
    rows = [r for r in csv.reader(io.StringIO(data.decode("utf-8"), newline="")) if len(r) == 10 and r[0] and r[0] != "section"]
    keys = {}
    for r in rows: keys[tuple(r[:4])] = dict(N=int(r[4]), exfil=int(r[5]), mae=int(r[6]), saf=int(r[7]), pd=int(r[8]), errored=int(r[9]))
    by_key = collections.defaultdict(dict)
    for (k, lay), v in pc.items(): by_key[k][lay] = v
    res = C(); diffs = C(); unmatched_layouts = C(); temit_mae_diff = 0; nonmatch_examples = []
    for k, v in keys.items():
        lays = by_key.get(k)
        if not lays: res["csv_key_without_cells"] += 1; continue
        # the subset of layout classes whose run count equals N (try all, then without underscore/extcanary/addendum)
        tot = C();  [tot.update(x) for x in lays.values()]
        cand = [("all", tot)]
        for drop in ("underscore", "extcanary", "addendum", "archive"):
            t2 = C(); [t2.update(x) for l, x in lays.items() if drop not in l]; cand.append((f"no-{drop}", t2))
        t3 = C(); [t3.update(x) for l, x in lays.items() if l.split(":")[1] in ("run",) or l.startswith("excluded")]; cand.append(("run+excluded", t3))
        hit = next(((n, t) for n, t in cand if t["N"] == v["N"]), None)
        if hit is None: res["N_unmatched"] += 1; unmatched_layouts[",".join(sorted(lays))] += 1; continue
        res["N_matched:" + hit[0]] += 1; t = hit[1]
        for f in ("exfil", "errored", "saf", "pd"):
            dlt = t[f] - v[f]
            if dlt: diffs[f"{f}:{'>1' if abs(dlt) > 1 else '1'}"] += 1
        if k[2] == "TEMIT" and t["mae"] != v["mae"]: temit_mae_diff += 1
        elif k[2] != "TEMIT" and t["mae"] != v["mae"]: diffs["mae_nonTEMIT"] += 1
    covered = {k for k in keys}
    roster_keys_without_row = sum(1 for (k, lay) in pc if k not in covered and lay.startswith("roster"))
    csvres[lbl] = dict(rows=len(keys), N_sum=sum(v["N"] for v in keys.values()), result=dict(res), field_diffs=dict(diffs),
                       temit_mae_cells_differ=temit_mae_diff, unmatched_layout_sets=dict(unmatched_layouts),
                       roster_cell_keys_without_row=roster_keys_without_row)
# fingerprint groups (L1 per-run fp) vs tool calls
fp = collections.defaultdict(list)
for line in open(os.path.expanduser("~/.agentprov/migration-work/precheck/_fp/credleak-p15b.head.jsonl")):
    x = json.loads(line); fp[x["fp"]].append(x["label"])
groups = [g for g in fp.values() if len(g) > 1]
fpres = dict(groups=len(groups), units_in_groups=sum(map(len, groups)),
             groups_with_call_runs=sum(1 for g in groups if any(run_calls.get(l, 0) for l in g)),
             units_with_calls_in_groups=sum(1 for g in groups for l in g if run_calls.get(l, 0)),
             fp_labels_unresolved=sum(1 for g in groups for l in g if l not in run_calls))
R["malformed_names"] = len(R["malformed_names"])
R["tallies"] = {k: dict(v) for k, v in R["tallies"].items()}
for k in list(R):
    if isinstance(R[k], C): R[k] = dict(sorted(R[k].items(), key=lambda kv: str(kv[0])))
R["turns_per_run"] = {str(k): v for k, v in R["turns_per_run"].items()}
out = dict(format="credleak-p15b-exam-pop/1", denominators=dict(cells=R["cells"], runs=R["runs"]), census=R,
           accounts=accounts, accounts_note="named non-generic accounts by truncated sha256 of the name; no name recorded",
           csv=csvres, fingerprints=fpres)
json.dump(out, open(OUT, "w"), indent=1, sort_keys=True, default=str)
print(json.dumps(out, sort_keys=True, default=str)[:200])
