"""Population exam of environmentoptim-agentdojo head: read the 104 selected logs from the pinned bare clone
through agentprov.ingest (strict bounded parse, blob SHA-1 checked). Counts, labels and truncated digests only.
Usage: uv run python -I pop.py OUT.json"""
import collections as C, hashlib, json, math, os, re, subprocess, sys
from agentprov.ingest.loaders import strict_json_loads
from agentprov.adapters.runner.importer import git_blob_sha1

BARE = os.path.expanduser("~/.agentprov/staging/10c/environmentoptim/EnvironmentOptim.git")
COMMIT = "febf82d8d1d8344d6c19e9fd172b51e52d68416a"
PREFIX = "runs/gpt-5.4-2026-03-05/"
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {
    "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file", "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
H = ["-c", f"core.hooksPath={os.devnull}", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always"]
SPOTIFY = "se3550000000054910000003"  # benchmark fixture IBAN (AgentDojo banking), compared lower-case
CRED = re.compile(r"(?i)((?:api[_-]?key|secret|token|passw(?:or)?d))[\"']?\s{0,3}[:=]\s{0,3}[\"']?([A-Za-z0-9_\-/+=.]{16,})")
ACCT = re.compile(r"/Users/|/home/|[A-Za-z]:\\\\Users|_ceph_ssd_students_")


def wilson(k, n, z=1.959964):
    if n == 0:
        return None
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(100 * (c - h) / d, 2), round(100 * (c + h) / d, 2)]


def tree():
    out = subprocess.run(["git", *H, "-C", BARE, "ls-tree", "-r", "-z", COMMIT, "--", PREFIX],
                         capture_output=True, env=ENV, check=True).stdout
    res = {}
    for rec in out.split(b"\0"):
        if rec:
            meta, path = rec.split(b"\t", 1); m = meta.split()
            if m[1] == b"blob":
                res[path.decode()] = m[2].decode()
    return res


def main(out_path):
    t = tree()
    p = subprocess.Popen(["git", *H, "-C", BARE, "cat-file", "--batch"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=ENV)
    o = C.defaultdict(C.Counter); per_suite = C.defaultdict(C.Counter); ts = []
    gh = {}; ut5 = {}; cred_vals = set(); cred_by = C.Counter(); cred_role = C.Counter(); cred_kw = C.Counter()
    sysp = C.Counter(); topkeys = C.Counter(); bench = C.Counter(); pkg = C.Counter()
    for path, oid in sorted(t.items()):
        p.stdin.write(oid.encode() + b"\n"); p.stdin.flush()
        h = p.stdout.readline().split(); data = p.stdout.read(int(h[2])); p.stdout.read(1)
        assert git_blob_sha1(data) == oid
        d = strict_json_loads(data)
        _, _, suite, task, a1, a2 = path.split("/")
        o["files"]["n"] += 1
        topkeys[tuple(sorted(d))] += 1
        bench[str(d.get("benchmark_version"))] += 1; pkg[str(d.get("agentdojo_package_version"))] += 1
        c = o["H5"]
        c["pipeline_ok"] += d.get("pipeline_name") == "gpt-5.4-2026-03-05"
        c["attack_null"] += d.get("attack_type") is None
        c["inj_null"] += d.get("injection_task_id") is None
        c["suite_eq_path"] += d.get("suite_name") == suite
        c["task_eq_path"] += d.get("user_task_id") == task
        c["error_null"] += d.get("error") is None
        c["security_true"] += d.get("security") is True
        ts.append(str(d.get("evaluation_timestamp")))
        msgs = d.get("messages") or []
        c["zero_messages"] += len(msgs) == 0
        sm = [m for m in msgs if m.get("role") == "system"]
        if sm:
            txt = "".join(x.get("content") or "" for x in sm[0]["content"]) if isinstance(sm[0]["content"], list) else str(sm[0]["content"])
            sysp[hashlib.sha256(txt.encode()).hexdigest()[:12] + f"/{len(txt)}"] += 1
        # tool calls, placeholder args, call ids, trailing calls, null final
        ids = []; calls = 0; ph_present = ph_null = 0
        for i, m in enumerate(msgs):
            for tc in m.get("tool_calls") or []:
                calls += 1; ids.append(tc.get("id"))
                if "placeholder_args" in tc:
                    ph_present += 1; ph_null += tc["placeholder_args"] is None
        c["tool_calls"] += calls; c["placeholder_present"] += ph_present; c["placeholder_null"] += ph_null
        c["call_id_null"] += sum(x is None for x in ids); c["call_id_repeat"] += len(ids) - len(set(ids))
        last = msgs[-1] if msgs else {}
        c["last_is_assistant"] += last.get("role") == "assistant"
        c["trailing_call_logs"] += bool(last.get("role") == "assistant" and last.get("tool_calls"))
        if last.get("role") == "assistant":
            cont = last.get("content")
            empty = cont is None or (isinstance(cont, list) and not any((x.get("content") or "").strip() for x in cont))
            c["null_final"] += bool(empty and not last.get("tool_calls"))
        u = d.get("utility") is True
        per_suite[suite]["n"] += 1; per_suite[suite]["utility_true"] += u
        if suite == "github" and task in ("user_task_5", "user_task_7", "user_task_8", "user_task_11"):
            gh[task] = u
        if suite == "banking" and task == "user_task_5":
            ex = []
            for i, m in enumerate(msgs):
                for tc in m.get("tool_calls") or []:
                    if tc.get("function") == "send_money" and str((tc.get("args") or {}).get("recipient", "")).lower() == SPOTIFY:
                        res = next((r for r in msgs[i + 1:] if r.get("role") == "tool" and r.get("tool_call_id") == tc.get("id")), None)
                        ex.append({"amount": (tc.get("args") or {}).get("amount"), "tool_error": None if res is None else res.get("error") is not None})
            ut5 = {"utility": u, "send_money_to_spotify_calls": ex}
        # credential-shaped strings: role, keyword, distinct values by digest only
        for m in msgs:
            for x in m.get("content") or [] if isinstance(m.get("content"), list) else []:
                for mm in CRED.finditer(x.get("content") or ""):
                    cred_vals.add(hashlib.sha256(mm.group(2).encode()).hexdigest()[:12])
                    cred_by[suite] += 1; cred_role[m.get("role")] += 1; cred_kw[mm.group(1).lower()] += 1
        c["account_path_logs"] += bool(ACCT.search(data.decode("utf-8")))
    p.stdin.close(); p.wait()
    pooled_k = sum(v["utility_true"] for v in per_suite.values()); pooled_n = sum(v["n"] for v in per_suite.values())
    res = {
        "pin": COMMIT, "files": o["files"]["n"], "H5_H8_H9_H10": dict(o["H5"]),
        "benchmark_version": dict(bench), "agentdojo_package_version": dict(pkg),
        "top_level_key_sets": len(topkeys), "top_level_keys_n": sorted(len(k) for k in topkeys),
        "system_prompt_digest12_len": dict(sysp),
        "evaluation_timestamp": {"min": min(ts), "max": max(ts)},
        "utility_by_suite": {s: {**v, "rate": round(100 * v["utility_true"] / v["n"], 2), "wilson95": wilson(v["utility_true"], v["n"])}
                             for s, v in sorted(per_suite.items())},
        "utility_pooled": {"k": pooled_k, "n": pooled_n, "rate": round(100 * pooled_k / pooled_n, 2), "wilson95": wilson(pooled_k, pooled_n)},
        "agentdyn_8_github_utility": gh,
        "cc07_161_banking_ut5": ut5,
        "cc07_181": {"attacked_logs": 0, "note": "benign-only part; #181 concerns banking injection-task security checks"},
        "credential_shaped": {"strings": sum(cred_by.values()), "by_suite": dict(cred_by), "by_role": dict(cred_role),
                              "by_keyword": dict(cred_kw), "distinct_values": len(cred_vals)},
    }
    json.dump(res, open(out_path, "w"), indent=1, sort_keys=True)
    print(json.dumps(res, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1])
