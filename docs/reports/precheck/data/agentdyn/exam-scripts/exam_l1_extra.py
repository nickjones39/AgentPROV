"""agentdyn pre-check follow-up (examiner, 2026-10-15): whole-population raw counts that l1_scan.py does not emit.

Read-only; raw bytes only through agentprov.ingest.loaders.strict_json_loads; prints and writes counts only (no string
values). Covers prereg sections 2/6/7 items the L1 summary cannot test: message, tool-call, tool-message and tool-error
totals; runs without a tool call; last-message shapes (null content with/without calls, empty text blocks: H-13,
L1-08); [user, assistant]-only runs (c); runs not ending in an assistant message; evaluation day histogram (H-16);
v0.k11 system-prompt digest prefix and key presence (H-15).

Usage: uv run python -I exam_l1_extra.py --root ~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn \
           --units-dir ~/.agentprov/migration-work/precheck/agentdyn --out <json> [--limit N]
"""
import argparse, collections, hashlib, json, os

from agentprov.ingest.loaders import strict_json_loads

SECALIGN = ("meta_secalign-70B", "meta_secalign-8B")
GOOGLE_API = ("google_gemini-2.5-flash-piguard_detector", "google_gemini-2.5-flash-prompt_guard_2_detector",
              "google_gemini-2.5-flash-transformers_pi_detector")


def content_shape(m):
    ct = m.get("content")
    if ct is None:
        return "null"
    if isinstance(ct, str):
        return "empty" if ct.strip() == "" else "text"
    if isinstance(ct, list):
        texts = [b.get("content") if isinstance(b, dict) and "content" in b else (b.get("text") if isinstance(b, dict) else b) for b in ct]
        return "empty" if all(not (isinstance(t, str) and t.strip()) for t in texts) else "text"
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--units-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    root, ud = os.path.expanduser(a.root), os.path.expanduser(a.units_dir)
    out = {}
    for part in "abc":
        tot = collections.Counter(); last = collections.Counter(); days = collections.Counter(); sysd = collections.Counter()
        grp_final = collections.Counter(); keys = collections.Counter()
        n = 0
        for line in open(f"{ud}/l1-units-{part}.jsonl"):
            row = json.loads(line)
            if a.limit and n >= a.limit:
                break
            n += 1
            d = row["facets"]["pipeline_dir"]
            with open(f"{root}/{row['label']}", "rb") as fh:
                v = strict_json_loads(fh.read())
            msgs = [m for m in (v.get("messages") or []) if isinstance(m, dict)]
            roles = [m.get("role") for m in msgs]
            calls = sum(len(m.get("tool_calls") or []) for m in msgs if m.get("role") == "assistant")
            tool_msgs = sum(r == "tool" for r in roles)
            tool_err = sum(1 for m in msgs if m.get("role") == "tool" and m.get("error"))
            tot["files"] += 1; tot["messages"] += len(msgs); tot["tool_calls"] += calls; tot["tool_messages"] += tool_msgs
            tot["tool_errors"] += tool_err; tot["runs_without_tool_call"] += calls == 0
            tot["not_ending_in_assistant"] += bool(msgs) and roles[-1] != "assistant"
            tot["user_assistant_only"] += roles == ["user", "assistant"]
            tot["system_user_only"] += roles == ["system", "user"]
            la = next((m for m in reversed(msgs) if m.get("role") == "assistant"), None)
            if la is not None:
                shape = f"{content_shape(la)}|calls={'y' if la.get('tool_calls') else 'n'}"
                last[shape] += 1
                g = "secalign" if d in SECALIGN else "google_api" if d in GOOGLE_API else "camel" if d.endswith("-camel") else "openai_compatible"
                grp_final[f"{g}|n"] += 1
                grp_final[f"{g}|empty_final_without_call"] += shape in ("empty|calls=n", "null|calls=n")
            ts = v.get("evaluation_timestamp")
            if isinstance(ts, str):
                days[ts[:10]] += 1
            for k in ("evaluation_timestamp", "agentdojo_package_version"):
                keys[f"{k}:{'present' if k in v else 'absent'}"] += 1
            if part == "b" and msgs and msgs[0].get("role") == "system":
                ct = msgs[0].get("content")
                txt = ct if isinstance(ct, str) else json.dumps(ct)
                sysd[hashlib.sha256(txt.encode()).hexdigest()[:8]] += 1
        out[part] = {"totals": dict(tot), "last_assistant_shape": dict(last), "empty_final_by_client_group": dict(grp_final),
                     "evaluation_days": dict(sorted(days.items())), "keys": dict(keys), "b_system_sha256_prefix": dict(sysd)}
        print(part, json.dumps(out[part])[:600])
    with open(os.path.expanduser(a.out), "w") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
