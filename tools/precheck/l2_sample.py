"""Level 2 of the corpus pre-check: the deterministic stratified sample of a part (docs/reports/precheck/README.md §4).

    uv run python tools/precheck/l2_sample.py select --units L1-UNITS.jsonl --source S --part P --corpus-id C --out SAMPLE.json
        [--where FACET=VALUE ...] [--exclude-flag FLAG ...] [--exclude-facet FACET=VALUE ...] [--exclude-profile-code CODE ...]
    uv run python tools/precheck/l2_sample.py select --units-from-tree --source S --part P --corpus-id C --out SAMPLE.json
        [--cache DIR] [--input PATH]

**Rule (pre-registered, README §4).** Unit = the raw artefact the importer selects (file or archive member; one L1 row).
Stratum = the part's arm key (the L1 row's ``stratum``). Units whose ``parse`` is not ``ok`` are eligible and stay in their
stratum. With N units in all:

* N < 30: every unit (every stratum whole).
* Otherwise each stratum's quota is ``min(k, size)`` with k = 5, raised to the smallest k >= 5 for which the quotas sum to
  at least 30 (so the total is "about 5 per stratum, at least 30").
* When the quotas sum to more than 300, they are reduced proportionally: ``max(1, floor(q * 300 / total))``; the units
  still free under 300 go one at a time to the strata in sorted stratum order (only to a stratum still below its quota),
  cycling until 300 or every quota is met. At least 1 per stratum always holds, so a part with more than 300 strata gets
  one unit per stratum (more than 300 units; recorded).
* Draw per stratum: its labels sorted (code-point order), then
  ``random.Random(f"20261011:precheck:{source}:{part}:{stratum}").sample(labels, quota)``.

The output lists the strata (sorted) with their sampled labels (sorted) and the union of labels (sorted); the post-check
reuses the file unchanged. ``--where`` keeps only L1 rows whose facet has the value (e.g. ``attack_dir=autodojo`` for the
AutoDojo slice of the ROPE tree); ``--exclude-flag`` drops rows carrying a flag and ``--exclude-facet FACET=VALUE`` rows whose
facet has the value before the draw (e.g. ``model=<local-path-model>`` (the Inspect header model facet): the AgentHarm local-path-model logs may not
reach a scratch import); all three are recorded in the rule. ``--exclude-profile-code CODE`` drops the rows that the part
profile's own ``[import] exclude`` entries of that register code match (the importer's matcher on the member's own label):
the frame then excludes exactly what the profile excludes, e.g. ``select.redaction_pending`` for EnvironmentOptim's
6,016 local-Qwen logs (D-255). The L1 rows never hold such a unit (the scanner classifies it ``excluded``), so the count
is expected to be 0; the rule records the code and its globs (only when given, so earlier sample files keep their shape).

``--units-from-tree`` is the fallback before L1 rows exist: it lists the importer's candidates of a git or local tree
(``l2_import.build``; archive inputs need L1 rows) and takes the stratum from path facets only (agentdojo layout:
``<prefix>/<pipeline_dir>|<attack_dir>|<suite>``; DTap: ``framework|model|split``; OpenHands: the model directory; others:
the directory). It is a fallback, recorded as such; parts whose arm is not in the path (AgentDyn's variant split) refuse it.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import (  # noqa: E402
    ACCOUNT_PATH,
    SAMPLE_FORMAT,
    SECRET_PATTERNS,
    SEED,
    read_jsonl,
    sha256_file,
    tilde,
    write_json,
)

PER_STRATUM: Final = 5
MINIMUM: Final = 30
MAXIMUM: Final = 300

RULE_TEXT: Final = (
    "README section 4: unit = importer-selected raw artefact (one L1 row), stratum = the L1 row's arm key; about 5 per "
    "stratum (k raised from 5 until the quotas reach 30), all units when fewer than 30; above 300 the quotas are reduced "
    "proportionally (max(1, floor(q*300/total))) and the rest is given one at a time in sorted stratum order; per stratum "
    "the sorted labels are drawn with random.Random('20261011:precheck:<source>:<part>:<stratum>').sample"
)


# ================================================================================================ the allocation
def allocate(sizes: Mapping[str, int], *, per: int = PER_STRATUM, minimum: int = MINIMUM,
             maximum: int = MAXIMUM) -> dict[str, int]:
    """The quota of every stratum (see the module docstring). ``sizes`` maps stratum -> number of units (> 0)."""
    strata = sorted(s for s, n in sizes.items() if n > 0)
    total_units = sum(sizes[s] for s in strata)
    if not strata:
        return {}
    if total_units < minimum:
        return {s: sizes[s] for s in strata}
    k = per
    while sum(min(k, sizes[s]) for s in strata) < minimum:
        k += 1
    quotas = {s: min(k, sizes[s]) for s in strata}
    total = sum(quotas.values())
    if total <= maximum:
        return quotas
    reduced = {s: max(1, math.floor(quotas[s] * maximum / total)) for s in strata}
    free = maximum - sum(reduced.values())
    while free > 0 and any(reduced[s] < quotas[s] for s in strata):
        for s in strata:
            if free <= 0:
                break
            if reduced[s] < quotas[s]:
                reduced[s] += 1
                free -= 1
    return reduced


def stratum_seed(source: str, part: str, stratum: str) -> str:
    return f"{SEED}:precheck:{source}:{part}:{stratum}"


def draw(source: str, part: str, strata: Mapping[str, Sequence[str]], quotas: Mapping[str, int]) -> dict[str, list[str]]:
    """Per stratum, ``quota`` labels drawn from its sorted labels with the stratum's seeded generator (sorted output)."""
    out: dict[str, list[str]] = {}
    for stratum in sorted(quotas):
        labels = sorted(strata[stratum])
        quota = quotas[stratum]
        chosen = labels if quota >= len(labels) else random.Random(stratum_seed(source, part, stratum)).sample(labels, quota)
        out[stratum] = sorted(chosen)
    return out


def group(units: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Stratum -> labels; a label in two rows (or two strata) is refused."""
    strata: dict[str, list[str]] = {}
    seen: dict[str, str] = {}
    for row in units:
        label, stratum = row.get("label"), row.get("stratum")
        if not isinstance(label, str) or not label:
            raise SystemExit("an L1 unit row has no label")
        stratum = stratum if isinstance(stratum, str) and stratum else "<none>"
        if label in seen:
            raise SystemExit(f"label listed twice in the L1 rows (strata {seen[label]!r} and {stratum!r})")
        seen[label] = stratum
        strata.setdefault(stratum, []).append(label)
    return strata


def select(units: Sequence[Mapping[str, Any]], *, source: str, part: str, corpus_id: str,
           where: Mapping[str, str] | None = None, exclude_flags: Sequence[str] = (),
           exclude_facets: Mapping[str, str] | None = None, basis: Mapping[str, Any] | None = None,
           exclude_globs: Mapping[str, Sequence[str]] | None = None) -> dict[str, Any]:
    """The sample document of a part from its unit rows (``label``, ``stratum``, optional ``sha256``, ``facets``,
    ``flags``, ``parse``). ``exclude_globs`` (``--exclude-profile-code``) maps a register code to the profile's
    ``[import] exclude`` globs of that code; a row whose own label (an archive member's last chain segment) matches one
    is dropped, with the importer's matcher."""
    where = dict(where or {})
    unwanted = dict(exclude_facets or {})
    by_code = {str(k): [str(g) for g in v] for k, v in sorted((exclude_globs or {}).items())}
    dropped_facets = 0
    dropped_code: dict[str, int] = {}
    kept: list[Mapping[str, Any]] = []
    dropped_where = 0
    dropped_flags: dict[str, int] = {}
    for row in units:
        facets = row.get("facets") if isinstance(row.get("facets"), dict) else {}
        if any(str((facets or {}).get(k, "<none>")) != v for k, v in where.items()):
            dropped_where += 1
            continue
        if any(str((facets or {}).get(k, "<none>")) == v for k, v in unwanted.items()):
            dropped_facets += 1
            continue
        code = profile_code_hit(str(row.get("label", "")), by_code) if by_code else None
        if code is not None:
            dropped_code[code] = dropped_code.get(code, 0) + 1
            continue
        flags = [str(f) for f in row.get("flags") or ()]
        hit = [f for f in exclude_flags if f in flags]
        if hit:
            for f in hit:
                dropped_flags[f] = dropped_flags.get(f, 0) + 1
            continue
        kept.append(row)
    strata = group(kept)
    quotas = allocate({s: len(v) for s, v in strata.items()})
    chosen = draw(source, part, strata, quotas)
    labels = sorted(label for group_ in chosen.values() for label in group_)
    unsafe = [label for label in labels if not committable(label)]
    if unsafe:  # the sample file is committed: a label with an account path or a secret shape may not be written
        raise SystemExit(f"{len(unsafe)} sampled label(s) carry an account path or a secret-like shape; the sample file "
                         "is committed, so the orchestrator decides (exclude them with --exclude-flag/--where)")
    by_label = {str(r["label"]): r for r in kept}
    sha = {label: str(by_label[label]["sha256"]) for label in labels if isinstance(by_label[label].get("sha256"), str)}
    not_ok = sum(1 for label in labels if by_label[label].get("parse", "ok") != "ok")
    rule: dict[str, Any] = {"text": RULE_TEXT, "per_stratum": PER_STRATUM, "minimum": MINIMUM, "maximum": MAXIMUM,
                            "where": where, "exclude_flags": list(exclude_flags), "exclude_facets": unwanted}
    population: dict[str, Any] = {"units": len(kept), "strata": len(strata), "dropped_where": dropped_where,
                                  "dropped_facets": dropped_facets, "dropped_flags": dict(sorted(dropped_flags.items())),
                                  "strata_sizes": {s: len(strata[s]) for s in sorted(strata)}}
    if by_code:  # recorded only when used, so every earlier sample file keeps its exact shape
        rule["exclude_profile_codes"] = by_code
        population["dropped_profile_code"] = {c: dropped_code.get(c, 0) for c in by_code}
    return {
        "format": SAMPLE_FORMAT, "source": source, "part": part, "corpus_id": corpus_id, "seed": SEED,
        "rule": rule, "population": population,
        "quotas": {s: quotas[s] for s in sorted(quotas)},
        "strata": chosen, "labels": labels, "n": len(labels), "sha256": sha, "parse_not_ok_sampled": not_ok,
        "over_maximum": len(labels) > MAXIMUM, "basis": dict(basis or {}),
    }


def profile_code_hit(label: str, by_code: Mapping[str, Sequence[str]]) -> str | None:
    """The first code (sorted) one of whose globs matches ``label``'s own label (the importer's ``_match``), else None."""
    from agentprov.adapters.runner.importer import _match

    own = label.rsplit("!/", 1)[-1]
    return next((code for code, globs in sorted(by_code.items()) if any(_match(own, g) for g in globs)), None)


def profile_exclude_globs(source: str, part: str, codes: Sequence[str]) -> dict[str, list[str]]:
    """``code -> [glob ...]`` of the part's profile ``[import] exclude`` entries with those codes (a code with no entry
    is refused: the plan would record an exclusion the profile does not make)."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.registry import get_source

    cap = next((c for c in get_source(source).capabilities if c.part == part), None)
    if cap is None or cap.profile is None:
        raise SystemExit(f"{source} · {part}: no registry profile")
    entries = [e for e in load_profile(str(cap.profile)).data.get("import", {}).get("exclude", ())
               if isinstance(e, Mapping) and "glob" in e]
    out: dict[str, list[str]] = {}
    for code in codes:
        globs = [str(e["glob"]) for e in entries if str(e.get("code")) == code]
        if not globs:
            raise SystemExit(f"{source} · {part}: the profile has no [import] exclude entry with code {code!r}")
        out[code] = globs
    return out


def committable(label: str) -> bool:
    """A label may go into a committed file: printable, no account path, no secret-like shape."""
    data = label.encode("utf-8", "surrogatepass")
    return label.isprintable() and not ACCOUNT_PATH.search(data) and not any(p.search(data) for p in SECRET_PATTERNS.values())


# ================================================================================================ fallback: path facets
def fallback_unit(label: str, dialect: str) -> dict[str, Any]:
    """A minimal unit row from a label alone (``--units-from-tree``)."""
    facets: dict[str, str] = {}
    if dialect == "agentdojo.tracelogger":
        segs = label.split("/")
        if len(segs) >= 5:
            facets = {"pipeline_dir": "/".join(segs[:-4]), "suite": segs[-4], "task_dir": segs[-3], "attack_dir": segs[-2]}
            stratum = f"{facets['pipeline_dir']}|{facets['attack_dir']}|{facets['suite']}"
        else:
            stratum = label.rpartition("/")[0] or "<root>"
    elif dialect == "dtap.trajectory":
        from agentprov.adapters.dtap.dialect import parse_path

        parsed = parse_path(label)
        if parsed is None:
            stratum = "<unparsed>"
        else:
            facets = {"framework": parsed.framework, "model": parsed.model, "split": parsed.split_label,
                      "domain": parsed.domain}
            stratum = f"{parsed.framework}|{parsed.model}|{parsed.split_label}"
    elif dialect == "openhands.events":
        from agentprov.adapters.openhands.dialect import parse_path as oh_parse

        parsed_oh: Any = oh_parse(label)
        model = getattr(parsed_oh, "model", None) if parsed_oh is not None else None
        facets = {"model": str(model)} if model else {}
        stratum = str(model) if model else (label.rpartition("/")[0] or "<root>")
    else:
        stratum = label.rpartition("/")[0] or "<root>"
    return {"label": label, "stratum": stratum, "facets": facets, "flags": [], "parse": "ok", "basis": "path-facets"}


_NO_FALLBACK: Final = {("agentdyn", "a"), ("agentdyn", "b"), ("agentdyn", "c")}


def units_from_tree(source: str, part: str, *, cache: Path | None, input_path: Path | None) -> list[dict[str, Any]]:
    if (source, part) in _NO_FALLBACK:
        raise SystemExit(f"{source} · {part}: part membership is the sniffed variant, not the path; use L1 rows")
    import l2_import

    built = l2_import.build(source, part, cache=cache, input_path=input_path, scratch=None, seed_cache=True)
    if getattr(built.tree, "archive_input", False):
        raise SystemExit(f"{source} · {part}: an archive input lists its members only after expand; use L1 rows")
    labels = l2_import.candidate_labels(built)
    dialect = str(built.profile.data.get("import", {}).get("dialect"))
    return [fallback_unit(label, dialect) for label in labels]


# ================================================================================================ CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    src = s.add_mutually_exclusive_group(required=True)
    src.add_argument("--units", type=Path, help="the part's L1 per-unit rows (l1-units-<part>.jsonl)")
    src.add_argument("--units-from-tree", action="store_true", help="fallback: units from the tree's path facets")
    s.add_argument("--source", required=True)
    s.add_argument("--part", required=True)
    s.add_argument("--corpus-id", required=True)
    s.add_argument("--out", required=True, type=Path)
    s.add_argument("--where", action="append", default=[], metavar="FACET=VALUE")
    s.add_argument("--exclude-flag", action="append", default=[], metavar="FLAG")
    s.add_argument("--exclude-facet", action="append", default=[], metavar="FACET=VALUE",
                   help="drop rows whose facet has the value (e.g. model=<local-path-model> for the AgentHarm logs)")
    s.add_argument("--exclude-profile-code", action="append", default=[], metavar="CODE",
                   help="drop rows the profile's [import] exclude entries of this code match (e.g. "
                        "select.redaction_pending: EnvironmentOptim's local-Qwen logs, D-255); recorded in the rule")
    s.add_argument("--cache", type=Path, help="--units-from-tree: fetch cache (default: the recipe's)")
    s.add_argument("--input", type=Path, help="--units-from-tree: the local tree (a git clone) instead of the cache")
    args = parser.parse_args(argv)
    where: dict[str, str] = {}
    unwanted: dict[str, str] = {}
    for items, target, flag in ((args.where, where, "--where"), (args.exclude_facet, unwanted, "--exclude-facet")):
        for item in items:
            key, sep, value = item.partition("=")
            if not sep or not key:
                parser.error(f"{flag} expects FACET=VALUE, got {item!r}")
            target[key] = value
    if args.units is not None:
        units = list(read_jsonl(args.units))
        basis = {"units_file": tilde(args.units), "units_sha256": sha256_file(args.units), "kind": "l1-rows"}
    else:
        units = units_from_tree(args.source, args.part, cache=args.cache, input_path=args.input)
        basis = {"kind": "path-facets-fallback"}
    globs = profile_exclude_globs(args.source, args.part, args.exclude_profile_code) if args.exclude_profile_code else None
    doc = select(units, source=args.source, part=args.part, corpus_id=args.corpus_id, where=where,
                 exclude_flags=args.exclude_flag, exclude_facets=unwanted, basis=basis, exclude_globs=globs)
    write_json(args.out, doc)
    print(f"{args.source} · {args.part}: {doc['n']} of {doc['population']['units']} units in "
          f"{len(doc['strata'])} strata -> {tilde(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
