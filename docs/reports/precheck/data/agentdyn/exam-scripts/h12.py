"""H-12: identical-trajectory cells between pairs of arms of the same model (L1 fp), part a (+ b, c)."""
import json, collections, itertools, sys, os
W = os.path.expanduser("~/.agentprov/migration-work/precheck/agentdyn")
cells = collections.defaultdict(dict)  # dir -> cell -> (fp, null_final)
part_of = {}
for p in "abc":
    for line in open(f"{W}/l1-units-{p}.jsonl"):
        r = json.loads(line); f = r["facets"]
        cell = "/".join(r["label"].split("/")[2:])
        d = f["pipeline_dir"] if p != "b" or f["pipeline_dir"] != "gpt-5-mini-2025-08-07-progent" else f["pipeline_dir"]
        key = d + ("#" + p if d == "gpt-5-mini-2025-08-07-progent" else "")
        cells[key][cell] = (r["fp"], "null_final" in r["flags"])
        part_of[key] = p
MODELS = ["google_gemini-2.5-flash", "google_gemini-2.5-pro", "gpt-4o-2024-08-06", "gpt-4o-mini-2024-07-18", "gpt-5-mini-2025-08-07",
          "gpt-5.1-2025-11-13", "meta-llama_llama-3.3-70b-instruct", "qwen_qwen3-235b-a22b-2507"]
GOOGLE = {"google_gemini-2.5-flash-piguard_detector", "google_gemini-2.5-flash-prompt_guard_2_detector", "google_gemini-2.5-flash-transformers_pi_detector"}
def model_of(d):
    base = d.split("#")[0]
    for m in sorted(MODELS, key=len, reverse=True):
        if base == m or base.startswith(m + "-"):
            return m
    return None
out = []
for m in MODELS:
    ds = sorted(d for d in cells if model_of(d) == m)
    for a, b in itertools.combinations(ds, 2):
        common = set(cells[a]) & set(cells[b])
        same = sum(cells[a][c][0] == cells[b][c][0] for c in common)
        both_empty = sum(cells[a][c][0] == cells[b][c][0] and cells[a][c][1] and cells[b][c][1] for c in common)
        bysuite = collections.Counter(c.split("/")[0] for c in common if cells[a][c][0] == cells[b][c][0])
        cls = "google_pair" if a in GOOGLE and b in GOOGLE else ("mixed" if (a in GOOGLE) != (b in GOOGLE) else "openai_compatible")
        out.append({"a": a, "b": b, "class": cls, "common": len(common), "identical": same, "identical_both_empty": both_empty,
                    "share_excl_empty": round((same - both_empty) / len(common), 4) if common else None, "by_suite": dict(bysuite)})
json.dump(out, open(sys.argv[1], "w"), indent=1)
for o in out:
    if o["class"] == "google_pair" or (o["share_excl_empty"] or 0) > 0.02:
        print(o["class"], o["a"][-40:], "|", o["b"][-40:], o["common"], o["identical"], o["identical_both_empty"], o["share_excl_empty"], o["by_suite"])
print("pairs", len(out), "openai_compatible >2%:", sum(1 for o in out if o["class"] == "openai_compatible" and (o["share_excl_empty"] or 0) > 0.02))
