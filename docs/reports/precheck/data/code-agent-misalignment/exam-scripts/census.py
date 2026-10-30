"""Exam pass over the pinned archive (read-only, streamed through tools/precheck/l1_scan.py's ArchiveSource, i.e.
agentprov.ingest). Counts only: no value, no account name, no member content is written.

    uv run python -I S/census.py OUT.json
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan  # noqa: E402

ARCHIVE = str(Path.home() / ".agentprov/staging/10e/zenodo_20404563/RESULTS_raw.tar.zst")
ROLL = re.compile(r"^RESULTS_build/cells/gemini_cli__([^/]+)/(SK-[A-Z]+)__(m\d\d)/(.+)$")
HOME = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/([^/\s\"'<>\\]{0,64})")
STREAM_KEYS = {"init": set(), "message": set(), "tool_use": set(), "tool_result": set(), "error": set(), "result": set()}


def d12(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:12]


def main(out: str) -> int:
    args = l1_scan.parser().parse_args(["--source", "code-agent-misalignment-geminicli", "--part", "results-raw",
                                        "--input", ARCHIVE])
    profile, _cap = l1_scan.resolve(args.source, args.part, None)
    limits = l1_scan.IngestLimits()
    source, _info = l1_scan.build_source(args, profile, args.part, limits)
    entries = source.entries()
    r: dict = {"members_walked": len(entries)}
    roles: dict = defaultdict(Counter)
    diff = Counter()
    diff_max = 0
    rollouts: dict = defaultdict(dict)
    want = set()
    for e in entries:
        m = ROLL.match(e.own)
        if e.own in ("RESULTS_build/manifest.csv", "RESULTS_build/cell_summary.csv", "RESULTS_build/README.md"):
            want.add(e.label)
        if not m:
            continue
        model, sk, mut, role = m.groups()
        roles[model][role] += 1
        key = f"{model}|{sk}|{mut}"
        rollouts[key][role] = e.size
        if role == "final_diff.patch":
            diff["n"] += 1
            diff["zero"] += e.size == 0
            diff["gt_1mib"] += e.size > 1048576
            diff["total"] += e.size
            diff_max = max(diff_max, e.size)
        if not role.endswith(".patch"):
            want.add(e.label)
    r["roles_by_model"] = {k: dict(sorted(v.items())) for k, v in sorted(roles.items())}
    r["rollouts"] = len(rollouts)
    r["final_diff"] = {**diff, "max": diff_max}
    top = {}
    per = defaultdict(lambda: defaultdict(Counter))  # model -> metric -> counter
    named = {"files_by_role": Counter(), "matches_by_role": Counter(), "digest_by_role": defaultdict(Counter),
             "second_seg_digests": Counter(), "files_by_model": Counter(), "jss_agent_work_files": Counter(),
             "name_shape": Counter()}
    secrets = {"stripe_distinct": Counter(), "stripe_prefix": Counter(), "stripe_by_skeleton": Counter(),
               "stripe_files_by_role": Counter(), "pem_by_role": Counter(), "jwt_by_role": Counter(),
               "aiza_labels": [], "aiza_by_role": Counter()}
    verdicts, metas, logs = {}, {}, Counter()
    for label, _size, data in source.stream(want):
        own = label.split("::")[-1]
        if not isinstance(data, bytes):
            continue
        if own.startswith("RESULTS_build/") and not ROLL.match(own):
            top[own] = hashlib.sha256(data).hexdigest()
            continue
        model, sk, mut, role = ROLL.match(own).groups()
        key = f"{model}|{sk}|{mut}"
        text = data.decode("utf-8", "replace")
        # account paths and secrets in every role
        hits = [mm for mm in HOME.finditer(text) if mm.group(1).lower() not in l1_scan.GENERIC_ACCOUNTS]
        if hits:
            named["files_by_role"][role] += 1
            named["files_by_model"][model] += 1
            named["matches_by_role"][role] += len(hits)
            for mm in hits:
                acc = mm.group(1)
                named["digest_by_role"][role][d12(acc)] += 1
                named["second_seg_digests"][d12(acc) + "/" + d12(mm.group(2))] += 1
                named["name_shape"][("lower_alnum" if re.fullmatch(r"[a-z0-9_]+", acc) else "other") + f":len{len(acc)}"] += 1
        if "jss_agent_work" in text:
            named["jss_agent_work_files"][role] += 1
        for mm in l1_scan.SECRET_PATTERNS["stripe-key"].finditer(text):
            v = mm.group(0)
            secrets["stripe_distinct"][d12(v)] += 1
            secrets["stripe_prefix"][v[:8]] += 1  # 'sk_live_' / 'sk_test_' / 'rk_...' class only
            secrets["stripe_by_skeleton"][sk] += 1
            secrets["stripe_files_by_role"][role] += 1
        if l1_scan.SECRET_PATTERNS["private-key-block"].search(text):
            secrets["pem_by_role"][role] += 1
        if l1_scan.SECRET_PATTERNS["jwt"].search(text):
            secrets["jwt_by_role"][role] += 1
        if l1_scan.SECRET_PATTERNS["google-api-key"].search(text):
            secrets["aiza_by_role"][role] += 1
            if role == "gemini_stream.jsonl":
                secrets["aiza_labels"].append(own)
        if role in ("runner_stdout.log", "runner_stderr.log"):
            n = len(text)
            logs[f"{role}:n"] += 1
            logs[f"{role}:eq50000"] += n == 50000
            logs[f"{role}:gt50000"] += n > 50000
            if role == "runner_stderr.log":
                per[model]["retry_lines"]["n"] += len(re.findall(r"(?i)retry", text))
        elif role == "verdict.json":
            p = l1_scan.parse_json(data, limits)
            v = p.value if isinstance(p.value, dict) else {}
            verdicts[key] = {k: v.get(k) for k in ("elicited", "exit_code", "timed_out", "elapsed_sec", "n_misaligned")}
        elif role == "gemini_meta.json":
            p = l1_scan.parse_json(data, limits)
            v = p.value if isinstance(p.value, dict) else {}
            metas[key] = {k: x for k, x in v.items() if isinstance(x, (int, float, bool)) or x is None}
        elif role == "gemini_stream.jsonl" and data:
            ev = Counter()
            tu_empty = tools = 0
            last = None
            inv = 0
            stats_calls = None
            res_status = None
            init_model = None
            dates = set()
            for line in data.split(b"\n"):
                if not line.strip():
                    continue
                p = l1_scan.parse_json(line, limits)
                o = p.value if isinstance(p.value, dict) else {}
                t = o.get("type")
                ev[t] += 1
                last = t
                if t in STREAM_KEYS:
                    STREAM_KEYS[t].update(o.keys())
                if isinstance(o.get("timestamp"), str):
                    dates.add(o["timestamp"][:10])
                if t == "init":
                    init_model = o.get("model")
                elif t == "tool_use":
                    tools += 1
                    tu_empty += o.get("parameters") == {}
                    inv += o.get("tool_name") == "codebase_investigator"
                elif t == "result":
                    res_status = o.get("status")
                    st = o.get("stats") if isinstance(o.get("stats"), dict) else {}
                    per[model]["stats_keys"][",".join(sorted(st))] += 1
                    stats_calls = st.get("tool_calls")
            pm = per[model]
            pm["streams"]["n"] += 1
            pm["events"].update(ev)
            pm["tool_use"]["n"] += tools
            pm["tool_use"]["params_empty"] += tu_empty
            pm["init_model"][str(init_model)] += 1
            pm["last_event"][str(last)] += 1
            pm["result_status"][str(res_status)] += 1
            pm["zero_tool_use"]["n"] += tools == 0
            pm["error_or_zero_tool"]["n"] += (res_status == "error") or tools == 0
            pm["dates"].update(dates)
            if inv:
                pm["investigator"]["calls"] += inv
                pm["investigator"]["streams"] += 1
                if stats_calls is not None and stats_calls != tools:
                    pm["investigator"]["stats_differs"] += 1
            if stats_calls is not None and stats_calls != tools:
                pm["stats_tool_calls_differs"]["n"] += 1
    r["top_files_sha256"] = top
    r["stream_keys"] = {k: sorted(v) for k, v in STREAM_KEYS.items()}
    r["per_model"] = {m: {k: dict(sorted(c.items())) for k, c in v.items()} for m, v in sorted(per.items())}
    r["named_home"] = {k: (dict(v) if not isinstance(v, defaultdict) else {a: dict(b) for a, b in v.items()})
                       for k, v in named.items()}
    r["secrets"] = {k: (dict(v) if isinstance(v, Counter) else v) for k, v in secrets.items()}
    r["secrets"]["stripe_distinct_n"] = len(secrets["stripe_distinct"])
    r["secrets"].pop("stripe_distinct")
    r["logs"] = dict(logs)
    # rollout-level joins
    agg = defaultdict(Counter)
    for key, rr in rollouts.items():
        model = key.split("|")[0]
        has_stream = "gemini_stream.jsonl" in rr
        cls = "no_stream" if not has_stream else ("empty" if rr["gemini_stream.jsonl"] == 0 else "stream")
        a = agg[model]
        a[cls] += 1
        v = verdicts.get(key, {})
        a[f"{cls}:elicited"] += bool(v.get("elicited"))
        a["exit_code_0"] += v.get("exit_code") == 0
        a["timed_out_false"] += v.get("timed_out") is False
        es = v.get("elapsed_sec")
        a["verdict_elapsed_ge240"] += isinstance(es, (int, float)) and es >= 240
        if cls == "no_stream":
            a["no_stream:has_meta"] += "gemini_meta.json" in rr
            a["no_stream:has_events_nonempty"] += rr.get("events.jsonl", 0) > 0
            if isinstance(es, (int, float)):
                a.setdefault("no_stream:elapsed_list", 0)
        a["file_after.json"] += "file_after.json" in rr
        a["transcript_tail.txt"] += "transcript_tail.txt" in rr
        mt = metas.get(key)
        if mt is not None:
            for k2, x in mt.items():
                if "exit" in k2 and isinstance(x, int):
                    a[f"meta:{k2}={x}"] += 1
            if any("exit" in k2 and x == 143 for k2, x in mt.items()):
                a["meta_exit143"] += 1
                el = mt.get("elapsed_sec")
                a["meta_exit143_elapsed_240_246"] += isinstance(el, (int, float)) and 240 <= el <= 246
    r["rollout_join"] = {m: dict(sorted(c.items())) for m, c in sorted(agg.items())}
    ns_el = sorted(v["elapsed_sec"] for k, v in verdicts.items()
                   if "gemini_stream.jsonl" not in rollouts[k] and isinstance(v.get("elapsed_sec"), (int, float)))
    r["no_stream_verdict_elapsed"] = {"n": len(ns_el), "median": ns_el[len(ns_el) // 2] if ns_el else None,
                                      "min": ns_el[0] if ns_el else None, "max": ns_el[-1] if ns_el else None}
    r["meta_keys"] = sorted({k for m in metas.values() for k in m})
    Path(out).write_text(json.dumps(r, indent=1, sort_keys=True, default=sorted) + "\n", encoding="utf-8")
    print("ok", len(entries), len(rollouts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
