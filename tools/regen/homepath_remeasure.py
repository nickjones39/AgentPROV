"""Item-22 re-measure (plan §7b): D-457 account-path names in the derived records of a stored corpus and of its
regenerated copy, compared per name. Counts and opaque ordinals only; no name or path is printed or written.

Usage: python -I tools/regen/homepath_remeasure.py OLD.partial NEW.partial [--suite github] --release-scan tools/release_scan.py

Per corpus and per distinct name (D-457 shapes of tools/release_scan.py, allowlist and D-604 labels excluded):
executions holding it (AER), PROV files holding it, the kind of the first AER record holding it in each execution,
how many executions hold the bare token in an earlier record, and hits under harness-derived pointers (traceback,
error, location, env, cwd, path keys outside message parts). The two corpora are compared name by name in memory; the
report gives ordinals (sorted by a per-run salted hash), never the names.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("old", type=Path)
ap.add_argument("new", type=Path)
ap.add_argument("--suite")
ap.add_argument("--release-scan", type=Path, required=True)
a = ap.parse_args()
spec = importlib.util.spec_from_file_location("release_scan", a.release_scan)
rs = importlib.util.module_from_spec(spec)
sys.modules["release_scan"] = rs  # its dataclasses look the module up
spec.loader.exec_module(rs)
ALLOW = rs.ACCOUNT_ALLOWLIST
LABEL = rs.REDACTION_LABEL
PATTERN = rs._ACCOUNT_PATH
HARNESS = re.compile(r"(?i)(traceback|error|location|env|cwd|workdir|log_?file|logdir)")


def names_in(data: bytes) -> set[str]:
    out = set()
    for m in PATTERN.finditer(data):
        name = [g for g in m.groups() if g is not None][-1]  # the POSIX form also captures (Users|home)
        if name.lower().rstrip(b".").decode("ascii", "replace") in ALLOW or LABEL.fullmatch(name) or set(name) <= {46}:
            continue
        out.add(name.decode("ascii", "replace"))
    return out


def walk(obj, ptr=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{ptr}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{ptr}/{i}")
    elif isinstance(obj, str):
        yield ptr, obj


def measure(root: Path):
    rows = [json.loads(line) for line in (root / "executions.jsonl").read_text().splitlines() if line.strip()]
    per = defaultdict(lambda: {"ex": 0, "prov": 0, "first": Counter(), "earlier": 0, "harness": 0})
    selected = 0
    for row in rows:
        recs = [json.loads(line) for line in (root / row["paths"]["aer"]).read_bytes().splitlines() if line.strip()]
        if a.suite:
            ex = next((r for r in recs if r.get("k") == "execution"), {})
            if (ex.get("task") or {}).get("suite") != a.suite:
                continue
        selected += 1
        seen: dict[str, int] = {}
        texts = [json.dumps(r, ensure_ascii=False) for r in recs]
        for i, r in enumerate(recs):
            raw = texts[i].encode("utf-8")
            for name in names_in(raw):
                if name not in seen:
                    seen[name] = i
                    per[name]["ex"] += 1
                    per[name]["first"][r.get("k")] += 1
                    if any(name in t for t in texts[:i]):
                        per[name]["earlier"] += 1
            for ptr, s in walk(r):
                if HARNESS.search(ptr) and "/parts/" not in ptr:
                    for name in names_in(s.encode("utf-8")):
                        per[name]["harness"] += 1
        for spec_paths in (row.get("paths", {}).get("prov") or {}).values():
            for rel in spec_paths.values():
                for name in names_in((root / rel).read_bytes()):
                    if name in seen or a.suite is None:
                        per[name]["prov"] += 1
    return selected, per


salt = os.urandom(16)
s_old, old = measure(a.old)
s_new, new = measure(a.new)
names = sorted(set(old) | set(new), key=lambda n: hashlib.sha256(salt + n.encode()).hexdigest())
diffs = []
for i, n in enumerate(names, 1):
    o, w = old.get(n), new.get(n)
    if o is None or w is None:
        diffs.append({"ordinal": i, "only_in": "old" if w is None else "new"})
        continue
    fo = {k: (dict(v) if isinstance(v, Counter) else v) for k, v in o.items()}
    fw = {k: (dict(v) if isinstance(v, Counter) else v) for k, v in w.items()}
    if fo != fw:
        diffs.append({"ordinal": i, "fields": sorted(k for k in fo if fo[k] != fw[k])})


def summary(per):
    return {"names": len(per), "model_generated_shape": sum(1 for v in per.values() if v["earlier"] == 0),
            "with_earlier_token": sum(1 for v in per.values() if v["earlier"] > 0),
            "harness_hits": sum(v["harness"] for v in per.values()),
            "first_kinds": dict(sum((v["first"] for v in per.values()), Counter()))}


print(json.dumps({"selected_executions": {"old": s_old, "new": s_new}, "old": summary(old), "new": summary(new),
                  "names_equal": set(old) == set(new), "per_name_feature_diffs": diffs}, sort_keys=True))
