"""H3: per cap/no-egress/base directory, tool results by function: error-free vs error class (the leading
`<Name>Error` / `<Name>Exception` token only, else 'other'). A function is 'blocked' in a directory when every one of its
results carries the blocking class seen for functions never error-free there. Counts and function names only.
Usage (repo root): uv run python -I .../exam-scripts/h3.py OUT.json (imports raw.py's walker setup)"""
import io, json, re, sys, collections as C
from pathlib import Path
from agentprov.adapters.profiles import load_profile
from agentprov.ingest.archives import iter_zip_members, open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import open_evidence
from agentprov.raw.members import nested_selection
ZIP = Path.home() / ".agentprov/staging/10c/zenodo-23138310/agent-authority-caps-v2.0.0.zip"
L = IngestLimits().replace(max_json_element_bytes=64 << 20)
imp = load_profile("authority-caps-agentdojo").data["import"]
sel = nested_selection(tuple(imp["include"]), imp["nested"])
DIRS = re.compile(r"runs_exp[47]\.tar\.gz!/runs/(gpt-[^/]+?(-capA3|-capA4|-noegress)?)/")
CLS = re.compile(r"^\s*([A-Z][A-Za-z]+(Error|Exception))")
T = C.defaultdict(lambda: C.defaultdict(C.Counter))
def walk(a, s, chain, depth):
    for m in iter_zip_members(a, lambda l: s.child_for(l) is not None or any(__import__("fnmatch").fnmatch(l, g) for g in s.include), L,
                              lambda l: s.child_for(l).raises if s.child_for(l) else None):
        if m.disposition == "not_selected": continue
        lab = "!/".join((*chain, m.label)); ch = s.child_for(m.label)
        if ch is not None:
            if "exp5" in m.label: continue
            walk(open_archive(io.BytesIO(a.read_member(m)), L, release=False, depth=depth + 1, max_depth=ch.raises.max_depth), ch.selection, (*chain, m.label), depth + 1); continue
        g = DIRS.search(lab)
        if not g: continue
        d = strict_json_loads(a.read_member(m), L)
        for x in d.get("messages") or []:
            if x.get("role") != "tool": continue
            fn = (x.get("tool_call") or {}).get("function"); e = x.get("error")
            k = "ok" if e is None else ((CLS.match(str(e)) or [None, "other"])[1])
            T[g.group(1)][fn][k] += 1
with open_evidence(str(ZIP.parent), ZIP.name, L.replace(max_artefact_bytes=1 << 40)) as h:
    walk(open_archive(h, L, release=False), sel, (), 1)
out = {}
for dr, fns in sorted(T.items()):
    cls = C.Counter(k for fn, c in fns.items() if "ok" not in c for k in c)
    out[dr] = {"functions": len(fns), "ok_functions": sorted(fn for fn, c in fns.items() if "ok" in c), "never_ok_functions": sorted(fn for fn, c in fns.items() if "ok" not in c),
               "error_classes_of_never_ok": dict(cls),
               "classes_all": dict(C.Counter({k: n for c in fns.values() for k, n in c.items() if k != "ok"})),
               "ok_functions_with_blocking_class": {fn: dict(c) for fn, c in fns.items() if "ok" in c and any(k in c for k in cls if k != "other")}}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True); print("ok", len(out))
