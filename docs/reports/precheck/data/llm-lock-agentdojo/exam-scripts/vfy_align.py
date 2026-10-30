"""Verifier (PC-03/PC-04): per-check alignment of hybrid detector values to tool outputs, and detector identity by value sets.

For every tool output in the hybrid, embedding and transformer arms the check sequence is rebuilt from the logged lists:
preliminary p (hybrid arms; the embedding rows reuse the hybrid thresholds and are not a test of that arm) (embedding RF malicious probability; benign if 1-p >= 0.6, malicious if p >= 0.6, else a secondary value is
consumed). Decisions are compared with the logged effect (sentinel redaction, or abort at the last output) under two check
orders (per tool turn: reversed as in the pinned defense_utils.query, or forward) and two secondary polarities (s >= 0.5
is malicious, or s < 0.5). Identity: each hybrid secondary value (rounded 1e-6) is looked up in the transformer arms'
value sets (as logged, and as 1 - v). Counts only; raw logs by blob id, sha256-checked, strict agentprov.ingest parse.
Usage: uv run python -I vfy_align.py <l1-units-head.jsonl> <bare repo> <commit> <out.json>
"""
from __future__ import annotations
import hashlib, json, os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pop_io import tree, Reader, text  # noqa: E402
from agentprov.ingest.loaders import strict_json_loads

UNITS, BARE, COMMIT, OUT = sys.argv[1:5]
SENT = "<Data omitted because a prompt injection was detected>"
HQ, HP = "hybrid/qualifire-prompt-injection-jailbreak-sentinel-v2", "hybrid/protectai-deberta-v3-base-prompt-injection-v2"
TQ, TP = "transformer/qualifire-prompt-injection-jailbreak-sentinel-v2", "transformer/protectai-deberta-v3-base-prompt-injection-v2"
ARMS = {HQ, HP, TQ, TP, "embedding"}
t = tree(BARE, COMMIT); r = Reader(BARE)
TV = defaultdict(lambda: defaultdict(set)); HV = defaultdict(list)
th = lambda m: hashlib.sha256(text(m.get("content")).encode()).hexdigest()
A = defaultdict(Counter); vals = defaultdict(set); hsec = defaultdict(list); prel = defaultdict(set)


def turns(ms):
    out, cur = [], []
    for m in ms:
        if m.get("role") == "tool": cur.append(m)
        elif cur: out.append(cur); cur = []
    if cur: out.append(cur)
    return out


def simulate(ms, P, S, order, pol, aborting):
    """Return (consistent, n_checks, prelim_left, sec_left)."""
    P, S = list(P), list(S); ts = turns(ms); aborted = ms[-1].get("role") == "tool"; n = 0
    for ti, tu in enumerate(ts):
        seq = list(reversed(tu)) if order == "rev" else list(tu)
        for j, m in enumerate(seq):
            if not P: return False, n, 0, len(S)
            p = P.pop(0); n += 1
            if 1 - p >= 0.6: mal = False
            elif p >= 0.6: mal = True
            else:
                if not S: return False, n, len(P), 0
                s = S.pop(0); mal = (s >= 0.5) if pol == "ge" else (s < 0.5)
            if aborting:
                last_turn = ti == len(ts) - 1
                if mal:
                    if not (aborted and last_turn): return False, n, len(P), len(S)
                    return (not P and not S), n, len(P), len(S)
            else:
                if mal != (SENT in text(m.get("content"))): return False, n, len(P), len(S)
    if aborting and aborted: return False, n, len(P), len(S)
    return (not P and not S), n, len(P), len(S)


for ln in open(UNITS, encoding="utf-8"):
    row = json.loads(ln); f = row["facets"]; arm = f["model_dir"]
    if arm not in ARMS: continue
    raw = r.read(t[row["label"]]); assert hashlib.sha256(raw).hexdigest() == row["sha256"]
    x = strict_json_loads(raw); ms = x["messages"]; a = A[arm]; a["logs"] += 1
    if arm.startswith("transformer/"):
        V = [v for v in (x.get("classification_malicious_probability") or []) if isinstance(v, (int, float))]
        for v in V: vals[arm].add(round(v, 6))
        seq = [m for tu in turns(ms) for m in reversed(tu)]
        if len(V) == len(seq):
            a["aligned_logs"] += 1
            for m, v in zip(seq, V):
                if SENT not in text(m.get("content")): TV[arm][th(m)].add(round(v, 6))
        continue
    P = [v for v in (x.get("preliminary_classification_malicious_probability") or []) if isinstance(v, (int, float))]
    S = [v for v in (x.get("secondary_classification_malicious_probability") or []) if isinstance(v, (int, float))]
    for v in P: prel[arm].add(round(v, 6))
    if arm != "embedding": hsec[arm] += [round(v, 6) for v in S]
    if arm != "embedding":
        PP, SS = list(P), list(S)
        for m in [m for tu in turns(ms) for m in reversed(tu)]:
            if not PP: break
            p = PP.pop(0)
            if 1 - p < 0.6 and p < 0.6 and SS:
                v = SS.pop(0)
                if SENT not in text(m.get("content")): HV[arm].append((th(m), round(v, 6)))
    n_uncertain = sum(1 - p < 0.6 and p < 0.6 for p in P)
    a["sec_eq_uncertain_prelims"] += n_uncertain == len(S); a["prelim_logs"] += bool(P)
    aborting = arm != HQ
    for order in ("rev", "fwd"):
        for pol in (("ge", "lt") if arm != "embedding" else ("ge",)):
            ok, *_ = simulate(ms, P, S, order, pol, aborting)
            a[f"consistent|{order}|{pol}"] += ok
    if arm == HQ:
        nred = sum(SENT in text(m.get("content")) for m in ms if m.get("role") == "tool")
        nprel_mal = sum(p >= 0.6 for p in P)
        a["red_eq_prelmal+sec_ge05"] += nred == nprel_mal + sum(s >= 0.5 for s in S)
        a["red_eq_prelmal+sec_lt05"] += nred == nprel_mal + sum(s < 0.5 for s in S)
r.close()
ident = {}
for h in (HP, HQ):
    c = Counter(); hv = hsec[h]
    for v in hv:
        for band, keep in (("all", True), ("mid_0.02-0.98", 0.02 < v < 0.98)):
            if not keep: continue
            c[f"{band}|values"] += 1
            for tr, nm in ((TP, "tp"), (TQ, "tq")):
                c[f"{band}|in_{nm}"] += v in vals[tr]; c[f"{band}|in_1-{nm}"] += round(1 - v, 6) in vals[tr]
    ident[h] = dict(c)
paired = {}
for h in (HP, HQ):
    c = Counter()
    for k, v in HV[h]:
        c["hybrid_checks_unredacted"] += 1
        for tr, nm in ((TP, "tp"), (TQ, "tq")):
            if k in TV[tr]:
                c[f"text_in_{nm}"] += 1; c[f"eq_{nm}"] += v in TV[tr][k]
                c[f"eq_1-{nm}"] += round(1 - v, 6) in TV[tr][k]
                c[f"within_0.01_{nm}"] += any(abs(v - w) <= 0.01 for w in TV[tr][k])
                c[f"within_0.01_1-{nm}"] += any(abs(1 - v - w) <= 0.01 for w in TV[tr][k])
    paired[h] = dict(sorted(c.items()))
emb_overlap = {h: len(prel[h] & prel["embedding"]) for h in (HP, HQ)} | {f"distinct_{k}": len(v) for k, v in prel.items()}
out = {"corpus_id": "llm-lock-agentdojo", "pin": COMMIT[:8], "arms": {k: dict(sorted(v.items())) for k, v in sorted(A.items())},
       "secondary_identity": ident, "paired_by_output_text": paired, "prelim_value_overlap_with_embedding": emb_overlap,
       "distinct_transformer_values": {k: len(v) for k, v in vals.items()}}
json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1); print(json.dumps(out, indent=1))
