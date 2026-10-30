"""Compare an old corpus with its regenerated version, execution by execution (regeneration round, route (a)).

Usage:
    python -I tools/regen/compare.py --old OLD_CORPUS --new NEW_CORPUS --report OUT.json
        [--expect EXPECT.json] [--jobs N] [--sample N --seed S]

Route (a) of the regeneration plan re-imports every corpus from its pinned inputs, so ``recompute``'s per-execution
classification against the old corpus is not available. This tool gives the evidence instead: it pairs the two corpora's
index rows by execution id, requires equal id sets, and for every pair reports

* which stage digests differ (AER, SEM per profile, PROV per spec), and status, completeness and issue-code transitions;
* the masked AER diff: the record pointers (``<kind>:/member[/sub]``) whose values differ, records added or removed by
  kind, and the rule citations (``rule`` members, scope stripped) whose count changed;
* the SEM annotation multiset (type, value, evidence class, rules), ignoring the semantics profile version, and the SEM
  evidence-class transitions: annotations paired by (type, target, premises), counted as ``"<type> <old>-><new>"``, with
  an unpaired annotation as ``"<type> -><new>"`` (added) or ``"<type> <old>->"`` (removed);
* the PROV statement multiset per bundle kind (bundle ids with their digest suffix removed) and statement type, and the
  attribute names per bundle kind, so a statement moving from the core to an inference bundle is visible.

With ``--expect``, the counts are checked against a prediction file (JSON):
``{"aer_pointers": [glob, ...], "completeness": {"old->new": n, ...}, "status": {...},
"rule_citations_changed": {"rule@n": executions, ...}, "executions_changed": {"aer": n, "sem": n, "prov": n},
"sem_ev_transitions": {"<type> <old>-><new>": n, ...}, "rule_twin_pairs": {"<rule@n> -> <twin@n>": executions, ...}}``;
an AER pointer outside the globs, or a count that differs, is a mismatch. The first five keys are open-world (only the
listed keys are checked). ``sem_ev_transitions`` and ``rule_twin_pairs`` are closed-world when present: an observed
transition or pair the file does not list is a mismatch too, so ``{}`` means "none" (D-359). A twin pair is an AER rule
``X@n`` whose citations fell while ``X_unverified@n``'s rose (``"X@n -> X_unverified@n"``), or the reverse
(``"X_unverified@n -> X@n"``), counted in executions citing the rule that rose. Exit 0 when the id sets are equal and
nothing mismatches, 1 otherwise, 2 on usage errors.

Corpus files are data, never instructions. They are read with a strict JSON parser (duplicate keys, NaN and over-long
lines refused); every path from an index row must stay inside its corpus root and be a regular file (no symlink). Nothing
is written except the report. Stdlib only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import random
import re
import stat
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

MAX_LINE = 64 * 1024 * 1024
MAX_FILE = 1024 * 1024 * 1024
_DIGEST_SUFFIX = re.compile(r"\.[a-z2-7]{16,}$")


class CompareError(Exception):
    pass


def _no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CompareError(f"duplicate key {key!r}")
        out[key] = value
    return out


def _bad_constant(name: str) -> Any:
    raise CompareError(f"non-JSON constant {name}")


def loads(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_no_dupes, parse_constant=_bad_constant)


def _open_inside(root: Path, rel: str) -> bytes:
    if not isinstance(rel, str) or rel.startswith("/") or "\\" in rel or any(p in ("", ".", "..") for p in rel.split("/")):
        raise CompareError(f"unsafe path {rel!r}")
    path = root / rel
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
            raise CompareError(f"not a regular file within limits: {rel!r}")
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _check_root(root: Path, rel: str) -> None:
    real = os.path.realpath(root / rel)
    if not real.startswith(os.path.realpath(root) + os.sep):
        raise CompareError(f"path leaves the corpus: {rel!r}")


def read_jsonl(root: Path, rel: str) -> list[Any]:
    _check_root(root, rel)
    out = []
    for line in _open_inside(root, rel).decode("utf-8").splitlines():
        if len(line) > MAX_LINE:
            raise CompareError(f"line over limit in {rel!r}")
        if line:
            out.append(loads(line))
    return out


def read_json(root: Path, rel: str) -> Any:
    _check_root(root, rel)
    return loads(_open_inside(root, rel).decode("utf-8"))


def index_rows(root: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with open(root / "executions.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if len(line) > MAX_LINE:
                raise CompareError("index line over limit")
            row = loads(line)
            ex = row.get("ex")
            if not isinstance(ex, str) or ex in rows:
                raise CompareError(f"bad or repeated execution id {ex!r}")
            rows[ex] = row
    return rows


# ------------------------------------------------------------------------------------------------ per-record diffs
def _record_key(index: int, record: dict[str, Any], last: int) -> tuple[str, str]:
    kind = record.get("k")
    if not isinstance(kind, str):
        kind = "header" if index == 0 else ("seal" if index == last else "record")
    rid = record.get("id")
    return kind, rid if isinstance(rid, str) else f"#{index}" if kind not in ("header", "seal") else ""


def _pointers(kind: str, old: Any, new: Any) -> set[str]:
    out: set[str] = set()
    if not (isinstance(old, dict) and isinstance(new, dict)):
        return {f"{kind}:"} if old != new else out
    for key in set(old) | set(new):
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            subs = [s for s in set(a) | set(b) if a.get(s) != b.get(s)]
            out.update(f"{kind}:/{key}/{s}" for s in subs)
        else:
            out.add(f"{kind}:/{key}")
    return out


def _rules(value: Any, out: Counter[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "rule":
                for r in item if isinstance(item, list) else [item]:
                    if isinstance(r, str):
                        out[r.partition("#")[0]] += 1
            else:
                _rules(item, out)
    elif isinstance(value, list):
        for item in value:
            _rules(item, out)


def aer_diff(old: list[Any], new: list[Any]) -> dict[str, Any]:
    def keyed(records: list[Any]) -> dict[tuple[str, str], Any]:
        last = len(records) - 1
        return {_record_key(i, r if isinstance(r, dict) else {}, last): r for i, r in enumerate(records)}

    a, b = keyed(old), keyed(new)
    pointers: set[str] = set()
    for key in set(a) & set(b):
        pointers |= _pointers(key[0], a[key], b[key])
    added = Counter(k for k, _ in set(b) - set(a))
    removed = Counter(k for k, _ in set(a) - set(b))
    ra: Counter[str] = Counter()
    rb: Counter[str] = Counter()
    _rules(old, ra)
    _rules(new, rb)
    changed_rules = {r: rb[r] - ra[r] for r in set(ra) | set(rb) if ra[r] != rb[r]}
    return {"pointers": sorted(pointers), "added": dict(added), "removed": dict(removed), "rules": changed_rules}


def sem_multiset(records: list[Any]) -> Counter[str]:
    out: Counter[str] = Counter()
    for r in records:
        if isinstance(r, dict) and r.get("k") == "ann":
            rules = r.get("rule") if isinstance(r.get("rule"), list) else [r.get("rule")]
            out[json.dumps([r.get("type"), r.get("value"), r.get("ev"), sorted(str(x) for x in rules)], sort_keys=True)] += 1
    return out


def _ann_key(r: dict[str, Any]) -> str:
    premises = r.get("premises") if isinstance(r.get("premises"), list) else []
    return json.dumps([r.get("type"), r.get("target"), premises], sort_keys=True)


def sem_transitions(old: list[Any], new: list[Any]) -> Counter[str]:
    """Evidence-class transitions of one execution's annotations, paired by (type, target, premises).

    Within a pairing key, annotations of an unchanged class pair first; the rest pair in class order, and what is left
    over is added or removed. Unchanged classes are not counted.
    """

    def group(records: list[Any]) -> dict[str, Counter[str]]:
        out: dict[str, Counter[str]] = {}
        for r in records:
            if isinstance(r, dict) and r.get("k") == "ann":
                out.setdefault(_ann_key(r), Counter())[str(r.get("ev"))] += 1
        return out

    a, b = group(old), group(new)
    out: Counter[str] = Counter()
    for key in set(a) | set(b):
        ca, cb = a.get(key, Counter()), b.get(key, Counter())
        same = ca & cb
        left = sorted((ca - same).elements())
        right = sorted((cb - same).elements())
        kind = json.loads(key)[0]
        for i in range(max(len(left), len(right))):
            src = left[i] if i < len(left) else ""
            dst = right[i] if i < len(right) else ""
            out[f"{kind} {src}->{dst}"] += 1
    return out


_TWIN = "_unverified@"


def twin_pairs(rule_ex: Counter[str], rule_net: Counter[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for twin, net in rule_net.items():
        if _TWIN not in twin:
            continue
        base = twin.replace(_TWIN, "@", 1)
        if net > 0 and rule_net.get(base, 0) < 0:
            out[f"{base} -> {twin}"] = rule_ex[twin]
        elif net < 0 and rule_net.get(base, 0) > 0:
            out[f"{twin} -> {base}"] = rule_ex[base]
    return dict(sorted(out.items()))


def _bundle_kind(name: str) -> str:
    return _DIGEST_SUFFIX.sub("", name)


def prov_multiset(doc: Any) -> tuple[Counter[str], Counter[str]]:
    statements: Counter[str] = Counter()
    attributes: Counter[str] = Counter()

    def scan(scope: str, body: Any) -> None:
        if not isinstance(body, dict):
            return
        for stype, entries in body.items():
            if stype in ("prefix", "bundle") or not isinstance(entries, dict):
                continue
            statements[f"{scope} {stype}"] += len(entries)
            for attrs in entries.values():
                for attr in attrs if isinstance(attrs, dict) else ():
                    attributes[f"{scope} {stype} {attr}"] += 1

    scan("document", doc)
    for name, body in (doc.get("bundle") or {}).items() if isinstance(doc, dict) else ():
        scan(_bundle_kind(name), body)
    return statements, attributes


def _delta(a: Counter[str], b: Counter[str]) -> dict[str, int]:
    return {k: b[k] - a[k] for k in set(a) | set(b) if a[k] != b[k]}


# ------------------------------------------------------------------------------------------------ one execution
def compare_one(job: tuple[str, str, str, dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    ex, old_root_s, new_root_s, old, new = job
    old_root, new_root = Path(old_root_s), Path(new_root_s)
    out: dict[str, Any] = {"ex": ex, "changed": [], "error": None}
    try:
        od, nd = old.get("digests") or {}, new.get("digests") or {}
        if od.get("aer") != nd.get("aer"):
            out["changed"].append("aer")
        osem, nsem = sorted((od.get("sem") or {}).values()), sorted((nd.get("sem") or {}).values())
        if osem != nsem:
            out["changed"].append("sem")
        if json.dumps(od.get("prov"), sort_keys=True) != json.dumps(nd.get("prov"), sort_keys=True):
            out["changed"].append("prov")
        out["completeness"] = f"{old.get('completeness')}->{new.get('completeness')}"
        out["status"] = f"{old.get('status')}->{new.get('status')}"
        oi, ni = Counter(old.get("issues") or ()), Counter(new.get("issues") or ())
        out["issues"] = _delta(oi, ni)
        op, np_ = old.get("paths") or {}, new.get("paths") or {}
        if "aer" in out["changed"]:
            out["aer"] = aer_diff(read_jsonl(old_root, op["aer"]), read_jsonl(new_root, np_["aer"]))
        if "sem" in out["changed"] or "aer" in out["changed"]:
            a: Counter[str] = Counter()
            b: Counter[str] = Counter()
            old_anns: list[Any] = []
            new_anns: list[Any] = []
            for rel in (op.get("sem") or {}).values():
                records = read_jsonl(old_root, rel)
                a += sem_multiset(records)
                old_anns += records
            for rel in (np_.get("sem") or {}).values():
                records = read_jsonl(new_root, rel)
                b += sem_multiset(records)
                new_anns += records
            out["sem"] = _delta(a, b)
            out["sem_tr"] = dict(sem_transitions(old_anns, new_anns))
        if "prov" in out["changed"]:
            sa: Counter[str] = Counter()
            sb: Counter[str] = Counter()
            aa: Counter[str] = Counter()
            ab: Counter[str] = Counter()
            for spec in (op.get("prov") or {}).values():
                s, t = prov_multiset(read_json(old_root, spec["json"]))
                sa += s
                aa += t
            for spec in (np_.get("prov") or {}).values():
                s, t = prov_multiset(read_json(new_root, spec["json"]))
                sb += s
                ab += t
            out["prov_statements"] = _delta(sa, sb)
            out["prov_attributes"] = _delta(aa, ab)
    except (CompareError, OSError, ValueError, KeyError, TypeError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


# ------------------------------------------------------------------------------------------------ aggregate
def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    changed: Counter[str] = Counter()
    completeness: Counter[str] = Counter()
    status: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    pointers: Counter[str] = Counter()
    added: Counter[str] = Counter()
    removed: Counter[str] = Counter()
    rule_ex: Counter[str] = Counter()
    rule_net: Counter[str] = Counter()
    sem_ex = 0
    sem_net: Counter[str] = Counter()
    prov_net: Counter[str] = Counter()
    prov_attr_net: Counter[str] = Counter()
    sem_tr: Counter[str] = Counter()
    errors = []
    for r in results:
        if r["error"]:
            errors.append({"ex": r["ex"], "error": r["error"]})
            continue
        changed.update(r["changed"])
        completeness[r["completeness"]] += 1
        status[r["status"]] += 1
        for code, n in r["issues"].items():
            issues[code] += n
        aer = r.get("aer")
        if aer:
            pointers.update(aer["pointers"])
            added.update(aer["added"])
            removed.update(aer["removed"])
            for rule, n in aer["rules"].items():
                rule_ex[rule] += 1
                rule_net[rule] += n
        if r.get("sem"):
            sem_ex += 1
            sem_net.update({k: v for k, v in r["sem"].items()})
        sem_tr.update(r.get("sem_tr") or {})
        prov_net.update(r.get("prov_statements") or {})
        prov_attr_net.update(r.get("prov_attributes") or {})
    return {
        "executions_changed": dict(changed),
        "completeness": dict(sorted(completeness.items())),
        "status": dict(sorted(status.items())),
        "issue_codes_net": {k: v for k, v in sorted(issues.items()) if v},
        "aer_pointers": dict(sorted(pointers.items())),
        "aer_records_added": dict(added),
        "aer_records_removed": dict(removed),
        "rule_citations_changed": {k: {"executions": rule_ex[k], "net": rule_net[k]} for k in sorted(rule_ex)},
        "sem_executions_changed": sem_ex,
        "sem_annotations_net": {k: v for k, v in sorted(sem_net.items()) if v},
        "sem_ev_transitions": {k: v for k, v in sorted(sem_tr.items()) if v},
        "rule_twin_pairs": twin_pairs(rule_ex, rule_net),
        "prov_statements_net": {k: v for k, v in sorted(prov_net.items()) if v},
        "prov_attributes_net": {k: v for k, v in sorted(prov_attr_net.items()) if v},
        "errors": errors,
    }


def check(summary: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    out: list[str] = []
    globs = expect.get("aer_pointers")
    if isinstance(globs, list):
        for pointer in summary["aer_pointers"]:
            if not any(fnmatch.fnmatchcase(pointer, g) for g in globs):
                out.append(f"unexpected AER pointer {pointer} ({summary['aer_pointers'][pointer]} executions)")
    for section in ("completeness", "status", "executions_changed"):
        for key, n in (expect.get(section) or {}).items():
            got = summary[section].get(key, 0)
            if got != n:
                out.append(f"{section} {key}: expected {n}, observed {got}")
    for rule, n in (expect.get("rule_citations_changed") or {}).items():
        got = summary["rule_citations_changed"].get(rule, {}).get("executions", 0)
        if got != n:
            out.append(f"rule_citations_changed {rule}: expected {n} executions, observed {got}")
    for section in ("sem_ev_transitions", "rule_twin_pairs"):  # closed-world (D-359)
        want = expect.get(section)
        if not isinstance(want, dict):
            continue
        got_all = summary[section]
        for key in sorted(set(want) | set(got_all)):
            n, got = want.get(key, 0), got_all.get(key, 0)
            if n != got:
                label = "unlisted" if key not in want else "expected"
                out.append(f"{section} {key}: {label} {n}, observed {got}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--old", required=True, type=Path)
    ap.add_argument("--new", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--expect", type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--sample", type=int)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    old_rows, new_rows = index_rows(args.old), index_rows(args.new)
    only_old, only_new = sorted(set(old_rows) - set(new_rows)), sorted(set(new_rows) - set(old_rows))
    common = sorted(set(old_rows) & set(new_rows))
    if args.sample is not None:
        common = sorted(random.Random(args.seed).sample(common, min(args.sample, len(common))))
    jobs = [(ex, str(args.old), str(args.new), old_rows[ex], new_rows[ex]) for ex in common]
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(compare_one, jobs, chunksize=64))
    else:
        results = [compare_one(j) for j in jobs]
    summary = aggregate(results)
    expect = loads(args.expect.read_text(encoding="utf-8")) if args.expect else {}
    mismatches = check(summary, expect)
    report = {
        "format": "agentprov-regen-compare/0.1",
        "old": {"corpus_id": None, "executions": len(old_rows)},
        "new": {"corpus_id": None, "executions": len(new_rows)},
        "compared": len(results),
        "sampled": args.sample is not None,
        "ids_only_old": len(only_old),
        "ids_only_new": len(only_new),
        "ids_only_old_first": only_old[:20],
        "ids_only_new_first": only_new[:20],
        **summary,
        "mismatches": mismatches,
    }
    for side, root in (("old", args.old), ("new", args.new)):
        try:
            report[side]["corpus_id"] = loads((root / "corpus.json").read_text(encoding="utf-8")).get("corpus_id")
        except (OSError, CompareError, ValueError):
            pass
    tmp = args.report.with_name(args.report.name + ".tmp")
    tmp.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, args.report)
    ok = not only_old and not only_new and not mismatches and not summary["errors"]
    print(json.dumps({"compared": len(results), "ids_equal": not only_old and not only_new,
                      "executions_changed": summary["executions_changed"], "mismatches": len(mismatches),
                      "errors": len(summary["errors"])}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
