"""Profile census over a full pinned snapshot: every ``observed`` count recomputed from the AERs (D.6.10 item 3; D.6.12).

    uv run python tools/agentdojo/profile_census.py --profile agentdojo-upstream --part head [--workers 10] \
        [--cache DIR] [--out REPORT.json] [--limit N]

Reads every blob of the part's primary git pin from the bare, extraction-free fetch cache (``git ls-tree`` /
``git cat-file --batch``, each blob checked against its SHA-1; no checkout, no network), keeps the profile's ``[import]
include`` selection, maps each blob with the profile (origin ``git``: the pinned commit, path and blob id), seals it with
the core writer and sums the per-file census counts of :mod:`agentprov.adapters.agentdojo.census` (generic quirks and
quirk hooks). It then compares them with the profile's ``observed`` table for the part and prints the differences.
The report holds counts, codes and variants only; never source text.

The ``full_corpus`` test ``tests/full_corpus/test_profile_census.py`` calls :func:`census` for every AgentDojo-family
profile part whose snapshot is in the cache. Wave-2 profiles need nothing here: their hooks carry their census functions.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Iterator
from multiprocessing import Pool
from pathlib import Path
from typing import Any

_PROFILE: dict[str, str] = {}


def _init(profile_id: str, part: str) -> None:
    _PROFILE["id"], _PROFILE["part"] = profile_id, part


def _work(job: tuple[str, str, str, str, bytes]) -> dict[str, Any]:
    repo, commit, path, blob, raw = job
    from agentprov.adapters.agentdojo.census import census_file
    from agentprov.adapters.agentdojo.quirks import CensusFile
    from agentprov.adapters.runner import NotSelected, aer_bytes, map_artefact_total
    from agentprov.adapters.types import Origin
    from agentprov.errors import MalformedArtefact

    row: dict[str, Any] = {"path": path}
    try:
        outcome, unit = map_artefact_total(raw, Origin.git(repo, commit, path, blob), profile_id=_PROFILE["id"],
                                           part=_PROFILE["part"])
    except NotSelected:  # a variant of another part (variant_labels): not this part's census
        row["status"] = "not_selected"
        return row
    except MalformedArtefact:
        row["status"] = "not_dialect"
        return row
    except Exception as exc:  # a crash is a finding; the label is the pinned path, never content
        row.update(status="crash", code=getattr(exc, "code", type(exc).__name__))
        return row
    try:
        data, info = aer_bytes(outcome)
    except Exception as exc:  # noqa: BLE001
        row.update(status="crash", code=getattr(exc, "code", type(exc).__name__))
        return row
    records = [json.loads(line) for line in data.splitlines()][:-1]
    row.update(status="degenerate" if outcome.degenerate else "sealed", variant=unit.primary.variant,
               unit=records[0].get("unit"), issues=sorted({str(i["code"]) for i in info.issues}),
               accounting=info.accounting.to_json()["status"],
               census=census_file(CensusFile(records, info.issues)))
    return row


def _blobs(fetcher: Any, recipe: Any, include: tuple[str, ...], limit: int | None) -> Iterator[tuple[str, str, str, str, bytes]]:
    from agentprov.adapters.runner.importer import _match

    entries, _skipped = fetcher.git_tree(recipe)
    chosen = [e for e in entries if e.is_blob and any(_match(e.path, g) for g in include)]
    if limit is not None:
        chosen = chosen[:limit]
    for blob in fetcher.iter_git_blobs(recipe, chosen):
        yield recipe.repo, recipe.commit, blob.entry.path, blob.entry.oid, blob.data


def census_pin(profile: Any, part: str) -> dict[str, Any]:
    """The pin a part's census reads (D.6.12 item 15): the part's own pin (the primary one first), else the primary pin
    that serves the part through ``[import] variant_labels`` (agentdyn's ``b`` and ``c`` are files of the ``head`` pin,
    whose ``part`` is ``a``). ``ProfileError`` when no pin serves the part; the census reads git pins only."""
    from agentprov.errors import ProfileError

    pins = [dict(p) for p in profile.data["source"]["pins"]]
    own = sorted((p for p in pins if p.get("part") == part), key=lambda p: p.get("primary") is not True)
    if own:
        return own[0]
    served = set(profile.data.get("import", {}).get("variant_labels", {}).values())
    if part in served:
        primary = [p for p in pins if p.get("primary") is True and p.get("part") in served]
        if len(primary) == 1:
            return primary[0]
    raise ProfileError(f"{profile.id} · {part}: no git pin serves this part (its own, or a primary pin by variant_labels)")


def census(profile_id: str, part: str, *, cache: str | None = None, workers: int = 10,
           limit: int | None = None) -> dict[str, Any]:
    """Map the part's pinned snapshot and return the census report (``ProfileError``/``NotCachedError`` when absent)."""
    from agentprov.adapters.agentdojo.census import add, compare, declared
    from agentprov.adapters.agentdojo.profile import family_table
    from agentprov.adapters.profiles import load_profile
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    profile = load_profile(profile_id)
    source = profile.data["source"]
    pin = census_pin(profile, part)
    if pin.get("kind") != "git":
        from agentprov.errors import ProfileError

        raise ProfileError(f"{profile.id} · {part}: the census reads a git pin, not a {pin.get('kind')} pin")
    recipe = Recipe.from_pin(pin, canonical_repo=source.get("canonical_repo"))
    fetcher = Fetcher(resolve_cache_dir(cache))
    include = tuple(profile.data.get("import", {}).get("include", ()))
    started = time.perf_counter()
    totals: dict[str, dict[str, int]] = {}
    status: Counter[str] = Counter()
    variants: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    accounting: Counter[str] = Counter()
    units: Counter[str] = Counter()
    crashes: list[dict[str, Any]] = []
    with Pool(workers, initializer=_init, initargs=(profile_id, part)) as pool:
        for row in pool.imap(_work, _blobs(fetcher, recipe, include, limit), chunksize=16):
            status[row["status"]] += 1
            if row["status"] == "crash":
                crashes.append({"path": row["path"], "code": row.get("code")})
                continue
            if row["status"] in ("not_dialect", "not_selected"):
                continue
            variants[str(row["variant"])] += 1
            units[str(row["unit"])] += 1
            accounting[str(row["accounting"])] += 1
            issues.update(row["issues"])
            add(totals, row["census"])
    table = family_table(profile)
    return {
        "profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256},
        "part": part,
        "pin": {"commit": recipe.commit, "paths": list(recipe.paths)},
        "files": sum(status.values()),
        "status": dict(sorted(status.items())),
        "variants": dict(sorted(variants.items())),
        "units": dict(sorted(units.items())),
        "accounting": dict(sorted(accounting.items())),
        "files_by_issue_code": dict(sorted(issues.items())),
        "crashes": crashes[:50],
        "measured": {q: dict(sorted(k.items())) for q, k in sorted(totals.items())},
        "declared": declared(table, part),
        "differences": compare(table, part, totals),
        "elapsed_s": round(time.perf_counter() - started, 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", required=True)
    parser.add_argument("--part", required=True)
    parser.add_argument("--cache", default=None)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    report = census(args.profile, args.part, cache=args.cache, workers=args.workers, limit=args.limit)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("files", "status", "variants", "differences", "elapsed_s")}, indent=2))
    return 0 if not report["differences"] and not report["crashes"] else 1


if __name__ == "__main__":
    sys.exit(main())
