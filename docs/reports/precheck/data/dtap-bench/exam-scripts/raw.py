"""dtap-bench targeted raw reads through agentprov.ingest (open_evidence + strict_json_loads); counts, pointer classes and
16-hex account digests only, never a value. Inputs: staged runs tree, tasks tree, LFS dir, L1 rows, xpair-labels.json.
Sections: judges (H9 originals, H10 LLM-judge keys, H12a #14 marker), named accounts (H11), sonnet-4 mentions (H15),
timestamps of non-stem files (H17), step counts of cross-pair identical trajectories (H18).
Usage: python -I raw.py <runs_root> <tasks_root> <lfs_dir> <l1-units> <l1-aux> <xpair-labels.json> <out.json>"""
import collections, hashlib, json, os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../../../tools/precheck"))
from agentprov.ingest.limits import MIB, IngestLimits  # noqa: E402
from agentprov.ingest.loaders import strict_json_loads  # noqa: E402
from agentprov.ingest.paths import open_evidence  # noqa: E402
from l1_scan import ACCOUNT_PATTERNS, GENERIC_ACCOUNTS  # noqa: E402

runs, tasks, lfs, units, aux, xpair, out = sys.argv[1:8]
LIM = IngestLimits().replace(max_json_bytes=512 * MIB)
LFS = b"version https://git-lfs.github.com/spec/v1\n"


def load(label):
    with open_evidence(runs, label, LIM) as h:
        data = h.read()
    if data.startswith(LFS):
        oid = re.search(rb"\noid sha256:([0-9a-f]{64})\n", data).group(1).decode()
        with open_evidence(lfs, oid, LIM) as h:
            data = h.read()
        assert hashlib.sha256(data).hexdigest() == oid
    return strict_json_loads(data)


def walk(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{p}/{k}")
            yield ("key", f"{p}/{k}", k)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v, re.sub(r"$", "/*", p))
    elif isinstance(o, str):
        yield ("str", p, o)


def norm(p):
    return re.sub(r"/trajectory/\*", "/trajectory/*", p)


def pclass(p):
    if p.startswith("/traj_info/agent_final_response") or re.match(r"/trajectory/\*/(action|metadata/message)", p):
        return "agent_content"
    if re.match(r"/trajectory/\*/(state|metadata/tool_params|metadata/error)", p):
        if re.search(r"/state/(plugins|agents|storePath)", p):
            return "tool_state_harness_config"
        return "tool_content"
    if p.startswith("/task_info"):
        return "task_info"
    if p.startswith("/traj_info/metadata/mcp_tools"):
        return "traj_info_mcp_tool_description"
    return "other:" + p.split("/")[1]


rows = [json.loads(l) for l in open(units)]
facet = {os.path.dirname(r["label"]): r["facets"] for r in rows}
R = {}

# 1. judges
LLMK = re.compile(r"llm_judge|llm_model|gpt_model")
j = collections.Counter(); orig = collections.defaultdict(lambda: collections.Counter())
for line in open(aux):
    a = json.loads(line); lab = a["label"]; f = facet.get(os.path.dirname(lab), {})
    d = load(lab); keys = set(); cs_marker = False; o_val = None
    for kind, p, v in walk(d):
        if kind == "key":
            if LLMK.search(v):
                keys.add(v)
            if v == "original_attack_success":
                pass
        elif "No judge_tool set" in v:
            cs_marker = True
    for k in keys:
        j[f"files_with_key:{k}"] += 1
    if keys:
        j["files_with_llm_key"] += 1
        j[f"files_with_llm_key|split={f.get('split_label')}|domain={f.get('domain')}"] += 1
    if cs_marker:
        j[f"no_judge_tool_set|domain={f.get('domain')}"] += 1
    def find(o, name):
        if isinstance(o, dict):
            if name in o:
                return o[name], True
            for v in o.values():
                r, ok = find(v, name)
                if ok:
                    return r, ok
        return None, False
    ov, has = find(d, "original_attack_success")
    if has:
        stored = a["outcomes"].get("attack_success")
        key = f"{f.get('framework')}|{f.get('model')}|{f.get('split_label')}|{f.get('domain')}"
        orig[key][f"{ov}->{stored}"] += 1; j["with_original_attack_success"] += 1
R["judges"] = dict(j); R["rejudged_by_cell"] = {k: dict(v) for k, v in sorted(orig.items())}

# 2-5 trajectories
named = [r for r in rows if "account_path_named" in r["flags"]]
acc = collections.defaultdict(lambda: {"files": set(), "classes": collections.Counter(), "frameworks": set()})
for r in named:
    d = load(r["label"])
    for kind, p, v in walk(d):
        if kind != "str":
            continue
        for name, rx in ACCOUNT_PATTERNS.items():
            for m in rx.finditer(v):
                a_ = m.group(1)
                if (name == "users-dir" and a_.lower() == "shared") or a_.lower() in GENERIC_ACCOUNTS:
                    continue
                dg = name + ":" + hashlib.sha256(a_.encode("utf-8", "surrogatepass")).hexdigest()[:16]
                e = acc[dg]; e["files"].add(r["label"]); e["classes"][pclass(norm(p))] += 1; e["frameworks"].add(r["facets"]["framework"])
# benchmark-config presence of each account digest (task tree text, regex only)
cfg_dg = set()
for dp, _, fs in os.walk(tasks):
    for fn in fs:
        if fn.endswith((".yaml", ".yml", ".json", ".py", ".md", ".txt", ".sh")):
            rel = os.path.relpath(os.path.join(dp, fn), tasks)
            if rel.startswith(".git"):
                continue
            try:
                with open_evidence(tasks, rel, LIM) as h:
                    t = h.read().decode("utf-8", "replace")
            except Exception:
                continue
            for name, rx in ACCOUNT_PATTERNS.items():
                for m in rx.finditer(t):
                    cfg_dg.add(name + ":" + hashlib.sha256(m.group(1).encode("utf-8", "surrogatepass")).hexdigest()[:16])
R["named_accounts"] = {dg: {"files": len(e["files"]), "classes": dict(e["classes"]), "frameworks": sorted(e["frameworks"]),
                            "in_task_tree": dg in cfg_dg} for dg, e in sorted(acc.items(), key=lambda x: -len(x[1]["files"]))}
cls_tot = collections.Counter()
for e in R["named_accounts"].values():
    for c, n in e["classes"].items():
        cls_tot[c] += n
R["named_summary"] = {"distinct": len(acc), "in_task_tree": sum(e["in_task_tree"] for e in R["named_accounts"].values()),
                      "strings_by_class": dict(cls_tot),
                      "accounts_only_outside_task_tree_with_harness_config_or_mcp": sum(
                          1 for e in R["named_accounts"].values() if not e["in_task_tree"] and
                          set(e["classes"]) & {"tool_state_harness_config", "traj_info_mcp_tool_description", "task_info"})}

SON = "claude-sonnet-4-20250514"
s = collections.Counter()
for r in rows:
    f = r["facets"]
    if f["framework"] == "claudesdk" and f["model"] == "claude-sonnet-4-5" and "judge_only_unit" not in r["flags"]:
        d = load(r["label"]); hit = set()
        for kind, p, v in walk(d):
            if kind == "str" and SON in v:
                hit.add(pclass(norm(p)))
        for c in hit:
            s[c] += 1
        if hit:
            s["files"] += 1
R["sonnet4_mentions_claudesdk_sonnet45"] = dict(s)

t = collections.Counter(); CUT = "2026-05-05T03:53:41"
for r in rows:
    stem = os.path.basename(r["label"])[:8]
    if stem.isdigit() or "judge_only_unit" in r["flags"]:
        continue
    d = load(r["label"]); ts = (d.get("traj_info") or {}).get("timestamp") if isinstance(d, dict) else None
    t["read"] += 1
    if isinstance(ts, str):
        late = ts[:19] > CUT
        t[("late_" if late else "ok_") + ("synthetic" if "synthetic" in r["flags"] else "other")] += 1
        if ts[:10] > "2026-07-01":
            t["after_pin"] += 1
R["timestamps_nonstem_files"] = dict(t)

xp = json.load(open(xpair))["xpair_labels"]; lab2 = {r["label"]: r for r in rows}
g = collections.Counter()
for grp in xp:
    steps = []
    for lab in grp:
        d = load(lab); steps.append(len(d.get("trajectory") or []) if isinstance(d, dict) else 0)
    mx = max(steps)
    g["groups"] += 1; g["degenerate_le3" if mx <= 3 else "non_degenerate"] += 1
    if mx > 3:
        g[f"nd_max_steps_{min(mx, 10)}{'+' if mx >= 10 else ''}"] += 1
        g["nd_units"] += len(grp)
        g["nd_cross_framework" if len({lab2[l]["facets"]["framework"] for l in grp}) > 1 else "nd_same_framework"] += 1
R["xpair_identical"] = dict(g)
json.dump(R, open(out, "w"), indent=1, sort_keys=True)
print(json.dumps({k: v for k, v in R.items() if k not in ("named_accounts", "rejudged_by_cell")}, indent=0))
