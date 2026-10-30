"""Pre-check examiner, redcode-exec-openhands head: whole-population L1 recount (read-only, counts only).

Reads the 7 pinned Zenodo 23168099 zips through agentprov.ingest (extraction-free). Never prints a value of an
account name, host name or secret-like string: only counts, normalised pointers and 8-hex sha256 prefixes.
Usage: uv run python -I pop.py OUT.json
"""
import csv, hashlib, io, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.loaders import strict_json_loads

Z = Path.home() / ".agentprov/staging/10g/zenodo_23168099"
PIN = {  # profile redcode-exec-openhands@1 [[source.pins]]
    "trajectories_OH-sonnet_S1.zip": ("ef8ecfc0c1c5e6b7e132f27aa3a34aa33cf61b59cbd009e207991c4160103ab5", "33d432a994110790a4af5bc4b208e39e", 10207154),
    "trajectories_OH-sonnet_S2.zip": ("795bfc669a19394d05544144e3928d88ec66d30beac4196ef73998161fa8c256", "8e81b7ed4a76d010758f2f3b36169fb1", 10756810),
    "trajectories_OH-sonnet_S3.zip": ("2c54e642fb1b6a7997dca9afe7ebd14c888a8bf9ecf7685d0ef6cadc777913a8", "e6c02e14a34609d343105d6fdf9de897", 10825922),
    "trajectories_OH-qwen3coder_S1.zip": ("6073f14da94d772cac5fe743e2cb0ab7bcadd86c891e494b21d9c1960c68f202", "c3e9aa7302a02cc5da15f5ecb087b744", 17624490),
    "trajectories_OH-qwen3coder_S2.zip": ("1deabb16106498704d90646dc7637db5b4bbef3d5f5b32a66c68414c65185313", "31e3e3c494201ea1f27d355a85518c52", 17966428),
    "trajectories_OH-qwen3coder_S3.zip": ("22fc7c5747c92cf7d57a662f8f0f3e6a2816d4a7952d8f97787c114d42a018e0", "f7d9bb452ae31c22f96d3fb5e617bccd", 10043836),
    "agent-execution-decisions-supp.zip": ("96e328facb240c14da16c394290372ddbb7221d97498cea16a64bd720192ae69", "8dfc720e8d328bffa50336ccf02b8b8f", 10130955),
}
FIXED = "a40faf5a4fd15d250e87d87670cfbcff49635380f8754cdd45b0bcbae64a5b6a"
TRAJ = re.compile(r"^results/OH/(?P<model>[^/]+)/(?P<target>S[123])/(?P<lang>python|bash)/trajectory/"
                  r"oh_(?P<sc>\d+)_(?P<pl>\d+)(?:_(?P<ltag>py|sh))?_(?P<t2>S[123])-(?P<hash>[0-9a-f]+)\.json$")
HOME = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/")
USERS = re.compile(r"/Users/([^/\s\"'<>\\]{1,64})/")
GENERIC = {"ubuntu", "user", "root", "runner", "app", "node", "admin", "agent", "dev", "test", "guest", "vscode", "jovyan",
           "circleci", "ec2-user", "sandbox", "username", "you", "yourname", "name", "me", "shared", "default", "docker",
           "work", "coder", "jenkins", "alice", "bob", "john", "jane", "example", "demo", "<user>", "user1", "myuser"}
CRED = re.compile(r"(?i)(?:api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s{0,3}[:=]\s{0,3}[\"']?[A-Za-z0-9_\-/+=.]{16,}")
STRICT_SECRETS = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}|(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_\-]{20,}|(?:AKIA|ASIA)[0-9A-Z]{16}"
                            r"|gh[pousr]_[A-Za-z0-9]{30,}|AIza[0-9A-Za-z_\-]{35}|hf_[A-Za-z0-9]{34,}|-----BEGIN[A-Z ]{0,20} PRIVATE KEY-----")
OPERATOR = Path.home().name
d8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]


def walk(v, ptr=""):
    if isinstance(v, dict):
        for k, x in v.items():
            yield from walk(x, ptr + "/" + (k if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,40}", str(k)) else "<key>"))
    elif isinstance(v, list):
        for x in v:
            yield from walk(x, ptr + "/*")
    elif isinstance(v, str):
        yield ptr, v


def main(out):
    R = {"pins": {}}
    for f, (sha, md5, size) in PIN.items():
        b = (Z / f).read_bytes()
        R["pins"][f] = {"size_ok": len(b) == size, "sha256_ok": hashlib.sha256(b).hexdigest() == sha,
                        "md5_ok": hashlib.md5(b).hexdigest() == md5}
    arms, cells, hashes, ltag = Counter(), Counter(), defaultdict(set), Counter()
    mr_model, ohv, agent, fixed, finish, lastev, nev = Counter(), Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    ids = Counter(); missing_ids = 0; uncaused_err = 0; cause = Counter()
    acct = defaultdict(lambda: {"artefacts": set(), "strings": 0, "ptrs": Counter(), "arms": Counter()})
    meta = {"username": Counter(), "hostname": Counter()}
    cred_art, cred_ptr, strict_art = set(), Counter(), set()
    keys = {}
    for f in sorted(PIN):
        if not f.startswith("trajectories_"):
            continue
        with open(Z / f, "rb") as fp, open_zip(fp, release=False) as oz:
            for m in iter_zip_members(oz):
                lab = m.label or ""
                mm = TRAJ.match(lab)
                if m.disposition != "selected" or not mm:
                    R.setdefault("unmatched", Counter())[f"{m.disposition}:{bool(mm)}"] += 1
                    continue
                model = "claude-sonnet-4-6" if mm["model"].startswith("claude") else "qwen3-coder-30b-a3b"
                arm = f"{model}/{mm['target']}/{mm['lang']}"
                arms[arm] += 1
                cells[(arm, int(mm["sc"]), int(mm["pl"]))] += 1
                hashes[mm["hash"]].add((model, mm["target"], mm["lang"]))
                ltag[f"{mm['target']}:{mm['ltag']}:{'agree' if mm['target'] == mm['t2'] else 'disagree'}"] += 1
                keys[(mm["model"], mm["target"], mm["lang"], int(mm["sc"]), f"{mm['sc']}_{mm['pl']}")] = arm
                ev = strict_json_loads(oz.read_member(m))
                nev[len(ev)] += 1
                eids = [e.get("id") for e in ev]
                ids["first0" if eids and eids[0] == 0 else "first_other"] += 1
                ids["strict_inc" if all(b > a for a, b in zip(eids, eids[1:])) else "not_inc"] += 1
                gaps = sum(b - a - 1 for a, b in zip(eids, eids[1:]))
                missing_ids += gaps
                ids["with_gap" if gaps else "no_gap"] += 1
                pos = {e.get("id"): i for i, e in enumerate(ev)}
                users = 0
                for i, e in enumerate(ev):
                    if "cause" in e:
                        c = e["cause"]
                        cause["resolved_earlier" if c in pos and pos[c] < i else "other"] += 1
                    elif e.get("observation") == "error":
                        uncaused_err += 1
                    a = e.get("args") if isinstance(e.get("args"), dict) else {}
                    if "openhands_version" in a: ohv[str(a["openhands_version"])[:20]] += 1
                    if "agent_class" in a: agent[str(a["agent_class"])[:30]] += 1
                    if e.get("source") == "user" and e.get("action") == "message":
                        users += 1
                        if users > 1:
                            fixed[hashlib.sha256(str(a.get("content", "")).encode()).hexdigest() == FIXED] += 1
                    tcm = e.get("tool_call_metadata")
                    if isinstance(tcm, dict) and isinstance(tcm.get("model_response"), dict):
                        mr_model[f"{model}:{str(tcm['model_response'].get('model'))[:40]}"] += 1
                    md = (e.get("extras") or {}).get("metadata") if isinstance(e.get("extras"), dict) else None
                    if isinstance(md, dict):
                        for k in meta:
                            if k in md: meta[k][d8(str(md[k]))] += 1
                finish["yes" if any(e.get("action") == "finish" for e in ev) else "no"] += 1
                le = ev[-1]
                lastev[f"{'act' if 'action' in le else 'obs'}:{le.get('action') or le.get('observation')}"] += 1
                for ptr, s in walk(ev):
                    for rx, kind in ((HOME, "home"), (USERS, "users")):
                        for n in rx.findall(s):
                            if n.lower() in GENERIC: continue
                            a = acct[(kind, n)]; a["artefacts"].add(lab); a["strings"] += 1; a["ptrs"][ptr] += 1; a["arms"][arm] += 1
                    if CRED.search(s): cred_art.add(lab); cred_ptr[ptr] += 1
                    if STRICT_SECRETS.search(s): strict_art.add(lab)
    # supplementary archive: scores, aggregates, dataset text, account scan of every member
    scores = defaultdict(list); agg = []; dataset_text = []; supp_acct = defaultdict(lambda: Counter()); supp_strict = Counter()
    per_rec = defaultdict(Counter)  # (model_dir, S, lang, sc) -> score counter
    with open(Z / "agent-execution-decisions-supp.zip", "rb") as fp, open_zip(fp, release=False) as oz:
        for m in iter_zip_members(oz):
            lab = m.label or ""
            b = oz.read_member(m)
            top = lab.split("/")[0] if "/" in lab else "<root>"
            try:
                text = b.decode("utf-8")
            except UnicodeDecodeError:
                text = None
                supp_acct["<binary>"]["files"] += 1
            if text is not None:
                for rx, kind in ((HOME, "home"), (USERS, "users")):
                    for n in rx.findall(text):
                        if n.lower() in GENERIC: continue
                        supp_acct[f"{top}:{kind}"][d8(n)] += 1
                        if n == OPERATOR: supp_acct["operator"]["hits"] += 1
                if STRICT_SECRETS.search(text): supp_strict[top] += 1
            cl = re.match(r"^results/OH/([^/]+)/(S[123])/(python|bash)/conversation_log/index(\d+)\.json$", lab)
            if cl:
                for e in strict_json_loads(b):
                    scores[(cl[1], cl[2], cl[3], int(cl[4]), str(e.get("index")))].append(e.get("score"))
                    per_rec[(cl[1], cl[2], cl[3], int(cl[4]))][e.get("score")] += 1
            elif lab.startswith("dataset/RedCode-Exec/") and text:
                dataset_text.append(text)
            elif re.match(r"^results/OH/.*(per_scenario\.csv|_summary\.json)$", lab):
                agg.append((lab, b))
    # join
    sk, tk = set(scores), set(keys)
    joined = Counter()
    for k in sk & tk:
        for v in scores[k]: joined[f"{keys[k]}:score={v}"] += 1
    R["join"] = {"traj": len(tk), "score_keys": len(sk), "both": len(sk & tk), "traj_only": len(tk - sk),
                 "score_only": len(sk - tk), "entries_per_key": dict(Counter(len(v) for v in scores.values()))}
    R["outcomes_joined"] = dict(sorted(joined.items()))
    # aggregates vs per-record
    amap = {"Success": 3, "Reject": 0, "Fail": 1}
    chk = Counter(); diffs = []
    for lab, b in agg:
        p = lab.split("/"); md, S, lang = p[2], p[3], p[4]
        if lab.endswith(".csv"):
            for row in csv.DictReader(io.StringIO(b.decode())):
                if not (row.get("scenario") or "").strip().isdigit():
                    rec = Counter()
                    for (a, b2, c, _), cc in per_rec.items():
                        if (a, b2, c) == (md, S, lang): rec.update(cc)
                    sc = "total_row"
                    if not all((row.get(k) or "").strip().isdigit() for k in ("success", "reject", "fail")):
                        chk["csv_row:non_numeric"] += 1; continue
                else:
                    sc = int(row["scenario"]); rec = per_rec.get((md, S, lang, sc))
                got = {"success": rec[3], "reject": rec[0], "fail": rec[1]} if rec else None
                exp = {k: int(row[k]) for k in ("success", "reject", "fail")}
                ok = got == exp; chk[f"csv_row:{ok}"] += 1
                if not ok: diffs.append({"file": "/".join(p[2:5]) + "/csv", "scenario": sc})
        else:
            d = strict_json_loads(b)
            blocks = [(d.get("scenario"), d["results"])] if "scenario" in d else [(None, d["results"])] + [(int(k), v) for k, v in d.get("by_scenario", {}).items()]
            for sc, res in blocks:
                if sc is None:
                    tot = Counter()
                    for (a, b2, c, _), cc in per_rec.items():
                        if (a, b2, c) == (md, S, lang): tot.update(cc)
                    rec = tot
                else:
                    rec = per_rec.get((md, S, lang, sc), Counter())
                ok = all(res.get(k) == rec[v] for k, v in amap.items())
                kind = "scenario_summary" if "scenario" in d else ("arm_total" if sc is None else "arm_by_scenario")
                chk[f"{kind}:{ok}"] += 1
                if not ok: diffs.append({"file": "/".join(p[2:5]), "kind": kind, "scenario": sc})
    R["aggregates"] = {"files": len(agg), "checks": dict(chk), "diffs": diffs[:40], "n_diffs": len(diffs)}
    ds = "\n".join(dataset_text)
    R["trajectories"] = {
        "arms": dict(sorted(arms.items())), "cells": len(cells), "cell_dups": sum(1 for v in cells.values() if v > 1),
        "cells_per_arm": dict(Counter(a for (a, _, _) in cells)), "scenarios_per_arm": {a: len({s for (x, s, _) in cells if x == a}) for a in arms},
        "name_ltag": dict(ltag), "hash_groups": dict(Counter(f"n={len(v)}:{'+'.join(sorted(m for m, _, _ in v))}" for v in hashes.values())),
        "hash_values": len(hashes),
        "events_per_run": {"min": min(nev), "max": max(nev), "total": sum(k * v for k, v in nev.items())},
        "ids": dict(ids), "missing_ids": missing_ids, "cause": dict(cause), "uncaused_error_obs": uncaused_err,
        "openhands_version": dict(ohv), "agent_class": dict(agent), "later_user_msgs_fixed_digest": {str(k): v for k, v in fixed.items()},
        "model_response_model": dict(mr_model), "finish": dict(finish), "last_event_no_finish_or_all": dict(lastev.most_common(10)),
        "run_metadata_distinct": {k: {"distinct": len(v), "events": sum(v.values())} for k, v in meta.items()},
    }
    R["accounts_traj"] = [{"kind": k, "name_d8": d8(n), "artefacts": len(a["artefacts"]), "strings": a["strings"],
                           "in_redcode_dataset": n in ds, "pointers": dict(a["ptrs"]), "arms": dict(a["arms"]),
                           "is_operator": n == OPERATOR, "equals_run_metadata_username": d8(n) in meta["username"]}
                          for (k, n), a in sorted(acct.items(), key=lambda x: -len(x[1]["artefacts"]))]
    R["secret_like_traj"] = {"generic_credential_assignment_artefacts": len(cred_art), "pointers": dict(cred_ptr.most_common(12)),
                             "strict_token_shape_artefacts": len(strict_art)}
    R["supp_scan"] = {k: ({"distinct": len(v), "hits": sum(v.values())} if k not in ("operator", "<binary>") else dict(v)) for k, v in supp_acct.items()}
    R["supp_scan_name_d8"] = {k: sorted(v) for k, v in supp_acct.items() if k not in ("operator", "<binary>")}
    R["supp_strict_secret_files_by_top"] = dict(supp_strict)
    Path(out).write_text(json.dumps(R, indent=1, sort_keys=True, default=str))
    print(json.dumps({"pins_ok": all(all(v.values()) for v in R["pins"].values()), "join": R["join"], "agg": R["aggregates"]["checks"]}))


if __name__ == "__main__":
    main(sys.argv[1])
