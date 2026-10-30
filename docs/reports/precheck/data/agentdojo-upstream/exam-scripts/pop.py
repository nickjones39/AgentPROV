"""agentdojo-upstream OS-1/L1-05: population recount from L1 unit rows (counts only). Usage: pop.py OUT.json"""
import json, sys, re
from collections import Counter, defaultdict
sys.path.insert(0, "tools/analysis2")
from exam2_lib import wilson

from pathlib import Path
W = str(Path.home() / ".agentprov/migration-work/precheck/agentdojo-upstream")
INJ11 = {"workspace": 6, "slack": 5, "travel": 7, "banking": 9}
OUT = {}


def rows(part):
    with open(f"{W}/l1-units-{part}.jsonl") as f:
        for line in f:
            yield json.loads(line)


def injn(fid):
    m = re.match(r"injection_task_(\d+)$", fid)
    return int(m.group(1)) if m else None


for part in ("head", "2024-06"):
    dirs = Counter(); flags = Counter(); pathdis = Counter()
    benign = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    att = defaultdict(Counter)
    sec_benign = Counter(); sec_prepass = Counter(); runerr = Counter(); inj_ids = defaultdict(set)
    suites_by_dir_none = defaultdict(Counter); prepass = Counter()
    for r in rows(part):
        fa = r["facets"]
        d, a, s = fa["pipeline_dir"], fa["attack_dir"], fa["suite"]
        dirs[d] += 1
        for fl in r["flags"]:
            flags[fl] += 1
            if fl.startswith("path_disagrees"):
                pathdis[fl] += 1
        o = r["outcomes"]
        u, sec, err = o.get("utility"), o.get("security"), o.get("error_present")
        if err:
            runerr["_all"] += 1
            if not (u is False and sec is True):
                runerr["_exception:" + a] += 1
        if a == "none":
            suites_by_dir_none[d][s] += 1
            if fa["task_kind"] == "prepass":
                prepass[d] += 1
                sec_prepass[str(sec)] += 1
                continue
            sec_benign[str(sec)] += 1
            b = benign[d][s]; b[1] += 1; b[0] += u is True
        else:
            fid = fa["file"]
            if s == "workspace":
                inj_ids[d].add(fid)
            c = att[(d, a)]
            c["n"] += 1; c["u"] += u is True; c["s"] += sec is True; c["err"] += bool(err); c["unull"] += u is None
            k = injn(fid)
            if s != "workspace" or (k is not None and k <= 5):
                c["n629"] += 1; c["u629"] += u is True; c["s629"] += sec is True; c["err629"] += bool(err)
                c["s629_err"] += bool(err) and sec is True
    res = {"dirs": dict(sorted(dirs.items())), "n_dirs": len(dirs), "flags": dict(flags), "path_disagrees": dict(pathdis),
           "benign_user_task_security": dict(sec_benign), "prepass_security": dict(sec_prepass),
           "run_errors_total": runerr["_all"], "run_error_exceptions": {k: v for k, v in runerr.items() if k != "_all"},
           "arms": {}}
    for d in sorted(dirs):
        bs = benign[d]
        k97 = sum(v[0] for v in bs.values()); n97 = sum(v[1] for v in bs.values())
        weighted = sum(v[0] * INJ11.get(s, 0) for s, v in bs.items())
        arm = {"files": dirs[d], "benign_n": n97, "benign_k": k97,
               "benign_u_pct": round(100 * k97 / n97, 2) if n97 else None,
               "benign_wilson": [round(100 * x, 2) for x in wilson(k97, n97)] if n97 else None,
               "benign_paper_weighted_pct": round(100 * weighted / 629, 2) if n97 == 97 else None,
               "benign_suites": {s: v[1] for s, v in bs.items()}, "prepass": prepass[d],
               "workspace_injection_ids": len(inj_ids[d]), "attacks": {}}
        for (dd, a), c in sorted(att.items()):
            if dd != d:
                continue
            arm["attacks"][a] = {
                "n": c["n"], "ua_k": c["u"], "asr_k": c["s"], "run_errors": c["err"], "utility_null": c["unull"],
                "ua_pct": round(100 * c["u"] / c["n"], 2), "asr_pct": round(100 * c["s"] / c["n"], 2),
                "asr_wilson": [round(100 * x, 2) for x in wilson(c["s"], c["n"])],
                "ua_wilson": [round(100 * x, 2) for x in wilson(c["u"], c["n"])],
                "n629": c["n629"], "ua629_pct": round(100 * c["u629"] / c["n629"], 2) if c["n629"] else None,
                "asr629_pct": round(100 * c["s629"] / c["n629"], 2) if c["n629"] else None,
                "asr629_k": c["s629"], "ua629_k": c["u629"], "err629": c["err629"], "asr629_k_run_error": c["s629_err"],
                "asr629_k_excl_run_errors": c["s629"] - c["s629_err"]}
        res["arms"][d] = arm
    res["none_suites_partial_dirs"] = {d: dict(v) for d, v in suites_by_dir_none.items() if d in (
        "claude-3-sonnet-20240229-repeat_user_prompt", "mistralai_Mixtral-8x7B-Instruct-v0.1")}
    OUT[part] = res
json.dump(OUT, open(sys.argv[1], "w"), indent=1, sort_keys=True)
for p, r in OUT.items():
    print(p, r["n_dirs"], sum(r["dirs"].values()), r["benign_user_task_security"], r["prepass_security"], r["run_errors_total"], r["run_error_exceptions"])
