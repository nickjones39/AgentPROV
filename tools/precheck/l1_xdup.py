"""L1-04 across parts and corpora: byte-identical artefacts and identical trajectories (docs/reports/precheck/README.md).

    uv run python tools/precheck/l1_xdup.py [--fp-dir DIR] [--out FILE] [--with-limit]

Reads every ``<precheck root>/_fp/<source>.<part>.jsonl`` written by ``l1_scan.py --emit-fp`` (rows ``{fp, sha256,
label, unit?, source, part, corpus_id, stratum}``; smoke files with a ``.limitN`` suffix are skipped unless
``--with-limit``) and the scratch unit rows ``<precheck root>/<corpus_id>/l1-units-<part>.jsonl`` for the facets, and
reports, for byte identity (artefact ``sha256``) and for trajectory identity (the family fingerprint of a unit):

* groups by scope: ``within_part`` (one source part), ``cross_part`` (several parts of one corpus), ``cross_corpus``;
* the pairs of parts / corpora that share groups, the group size distribution, the facets that differ inside groups of
  one part (an identical trajectory under two arm labels is a finding to examine);
* the largest groups with up to five labels each (labels only, never content).

Output: ``docs/reports/precheck/data/_cross/l1-xdup.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from itertools import combinations
from pathlib import Path
from typing import Any, Final

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from l1_scan import DATA_DIR, guard_output, precheck_root, safe_label, shown_path  # noqa: E402

_LARGEST: Final = 25

Member = tuple[str, str, str, str, str]  # (corpus_id, source, part, label, unit)


def load_fp(fp_dir: Path, with_limit: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    for path in sorted(fp_dir.glob("*.jsonl")):
        if ".limit" in path.name and not with_limit:
            continue
        count = Counter[str]()
        first: dict[str, Any] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if "source" not in row or "part" not in row:  # an older file: the name is <source>.<part>.jsonl
                source, _, part = path.name.removesuffix(".jsonl").partition(".")
                row.setdefault("source", source)
                row.setdefault("part", part)
            rows.append(row)
            first = first or row
            count["units"] += 1
            count["artefacts"] += 0 if row.get("unit") else 1
        inputs.append({"file": path.name, "source": first.get("source"), "part": first.get("part"),
                       "corpus_id": first.get("corpus_id"), **count})  # fmt: skip
    return rows, inputs


def load_facets(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str, str], dict[str, str]]:
    """``(source, part, label) -> facets`` from the scratch unit rows of every part that has fingerprints."""
    wanted = {(str(r.get("corpus_id")), str(r["source"]), str(r["part"])) for r in rows}
    out: dict[tuple[str, str, str], dict[str, str]] = {}
    for corpus_id, source, part in sorted(wanted):
        path = precheck_root() / corpus_id / f"l1-units-{part}.jsonl"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                out[(source, part, row["label"])] = row.get("facets", {})
    return out


def scope(members: Sequence[Member]) -> str:
    corpora = {m[0] for m in members}
    parts = {(m[1], m[2]) for m in members}
    if len(corpora) > 1:
        return "cross_corpus"
    if len(parts) > 1:
        return "cross_part"
    return "within_part"


def report(groups: Mapping[str, list[Member]], facets: Mapping[tuple[str, str, str], Mapping[str, str]]) -> dict[str, Any]:
    by_scope: dict[str, dict[str, Any]] = {}
    for name in ("within_part", "cross_part", "cross_corpus"):
        by_scope[name] = {"groups": 0, "members": 0, "sizes": Counter[str](), "pairs": Counter[str](),
                          "by_part": Counter[str](), "facets_differing": Counter[str]()}  # fmt: skip
    largest: list[tuple[int, str, list[Member]]] = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        where = scope(members)
        entry = by_scope[where]
        entry["groups"] += 1
        entry["members"] += len(members)
        entry["sizes"][str(len(members)) if len(members) < 10 else "10+"] += 1
        parts = sorted({f"{m[1]}.{m[2]}" for m in members})
        for p in parts:
            entry["by_part"][p] += 1
        if where == "cross_corpus":
            for a, b in combinations(sorted({m[0] for m in members}), 2):
                entry["pairs"][f"{a}|{b}"] += 1
        elif where == "cross_part":
            for a, b in combinations(parts, 2):
                entry["pairs"][f"{a}|{b}"] += 1
        per_part: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
        for m in members:
            per_part[(m[1], m[2])].append(facets.get((m[1], m[2], m[3]), {}))
        for items in per_part.values():
            if len(items) < 2:
                continue
            for k in sorted({k for f in items for k in f}):
                if len({f.get(k) for f in items}) > 1:
                    entry["facets_differing"][k] += 1
        largest.append((len(members), key, members))
    largest.sort(key=lambda t: (-t[0], t[1]))
    out: dict[str, Any] = {}
    for name, entry in by_scope.items():
        out[name] = {"groups": entry["groups"], "members": entry["members"],
                     "sizes": dict(sorted(entry["sizes"].items())),
                     "pairs": dict(entry["pairs"].most_common(50)), "by_part": dict(sorted(entry["by_part"].items())),
                     "facets_differing_in_groups": dict(sorted(entry["facets_differing"].items()))}  # fmt: skip
    out["largest"] = [{"size": n, "scope": scope(members),
                       "members": [{"corpus_id": m[0], "part": f"{m[1]}.{m[2]}", "label": safe_label(m[3]) + (f"#{m[4]}" if m[4] else "")}
                                   for m in members[:5]]} for n, _key, members in largest[:_LARGEST]]  # fmt: skip
    return out


def run(fp_dir: Path, out_path: Path, with_limit: bool) -> dict[str, Any]:
    rows, inputs = load_fp(fp_dir, with_limit)
    facets = load_facets(rows)
    by_sha: dict[str, list[Member]] = defaultdict(list)
    seen_artefact: set[tuple[str, str, str]] = set()
    by_fp: dict[str, list[Member]] = defaultdict(list)
    null_fp = 0
    for r in rows:
        member: Member = (str(r.get("corpus_id")), str(r["source"]), str(r["part"]), str(r["label"]), str(r.get("unit") or ""))
        artefact = (member[1], member[2], member[3])
        if r.get("sha256") and artefact not in seen_artefact:
            seen_artefact.add(artefact)
            by_sha[str(r["sha256"])].append(member)
        if r.get("fp"):
            by_fp[str(r["fp"])].append(member)
        else:
            null_fp += 1
    result = {
        "tool": "tools/precheck/l1_xdup.py", "fp_dir": shown_path(fp_dir), "inputs": inputs,
        "totals": {"rows": len(rows), "artefacts": len(seen_artefact), "units_without_fp": null_fp,
                   "distinct_sha256": len(by_sha), "distinct_fp": len(by_fp)},
        "byte_identical": report(by_sha, facets),
        "trajectory_identical": report(by_fp, facets),
    }  # fmt: skip
    out_path.parent.mkdir(parents=True, exist_ok=True)
    guard_output(out_path).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--fp-dir", default=None, help="default: <precheck root>/_fp")
    p.add_argument("--out", default=str(DATA_DIR / "_cross" / "l1-xdup.json"))
    p.add_argument("--with-limit", action="store_true", help="include the smoke (.limitN) fingerprint files")
    args = p.parse_args(argv)
    fp_dir = Path(args.fp_dir) if args.fp_dir else precheck_root() / "_fp"
    result = run(fp_dir, Path(args.out), args.with_limit)
    print(json.dumps(result["totals"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
