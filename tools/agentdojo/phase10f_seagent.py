"""Phase-10f census of the SEAgent deposit zip (Zenodo 23218779), offline, extraction-free (D-150, D-156).

    uv run python tools/agentdojo/phase10f_seagent.py census --zip SEAGENT.zip [--workers N] [--out REPORT.json]

The runner does not yet import a deposit archive whose members are whole run logs ("archive inputs", D_adapters §D.6.15),
so there is no trial import for this source. The census does the mapping half of one: it verifies the zip against the
profile's pin (size, md5, sha256), opens it with :func:`agentprov.ingest.archives.open_archive` (the G.3.5 gate: names,
links, methods, sizes, ratios), selects the members that match the profile's ``[import] include``, and maps each selected
member with the profile through
:func:`agentprov.adapters.runner.map_artefact_total` with a development-only ``local`` origin whose path is the member
label (the agentdojo mapper reads the layout from the origin's ``/path``, which a ``member`` origin lacks; routing D-156).
The core writer validates in release mode and refuses that origin, so nothing is sealed: the mapped records are validated
in development mode (every error other than the local origin and the absent seal line is reported as a finding), and the
per-file census counts of
:mod:`agentprov.adapters.agentdojo.census`, as ``profile_census.py`` does for git pins. It then compares them with the
profile's ``observed`` table. The report holds counts, codes, variants and labels only; never source text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from collections.abc import Iterator
from multiprocessing import Pool
from pathlib import Path
from typing import Any

PROFILE = "seagent-agentdojo"
PART = "head"


def _work(job: tuple[str, str, int, int, int, bytes]) -> dict[str, Any]:
    container, label, method, crc32, size, raw = job
    from agentprov.adapters.agentdojo.census import census_file
    from agentprov.adapters.agentdojo.quirks import CensusFile
    from agentprov.adapters.runner import NotSelected, map_artefact_total
    from agentprov.errors import MalformedArtefact
    from agentprov.raw.origins import Origin

    row: dict[str, Any] = {"path": label}
    try:
        # A development-only `local` origin whose path is the member label: the agentdojo mapper reads the layout from
        # the origin's `/path`, which a `member` origin does not have (routing D-156). Scratch census only, never a corpus.
        del container, method, crc32, size
        outcome, unit = map_artefact_total(raw, Origin.local(label), profile_id=PROFILE, part=PART)
    except NotSelected:
        row["status"] = "not_selected"
        return row
    except MalformedArtefact:
        row["status"] = "not_dialect"
        return row
    except Exception as exc:  # a crash is a finding; the label is the pinned member name, never content
        row.update(status="crash", code=getattr(exc, "code", type(exc).__name__))
        return row
    # The core writer validates in release mode, which refuses a `local` origin, so the records are not sealed: they are
    # validated in development mode, and every finding other than the local origin itself (pointer
    # /artifacts/*/origin/kind) and the missing seal line is reported.
    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import validate_records

    report = validate_records(outcome.records, store=None, catalogues=RuleRegistry.default(), mode="dev")
    findings = sorted({f"{f.code}:{f.detail}" for f in report.findings if f.severity == "error"
                       and not f.pointer.endswith("/origin/kind") and f.code != "aer.order.envelope"})
    records = [json.loads(json.dumps(r)) for r in outcome.records]
    row.update(status="degenerate" if outcome.degenerate else "mapped", variant=unit.primary.variant,
               unit=records[0].get("unit"), issues=sorted({str(i["code"]) for i in outcome.issues}),
               findings=findings,
               records_sha256=hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest(),
               census=census_file(CensusFile(records, outcome.issues)))
    return row


def _pin() -> tuple[Any, dict[str, Any]]:
    from agentprov.adapters.profiles import load_profile

    profile = load_profile(PROFILE)
    pin = next(dict(p) for p in profile.data["source"]["pins"] if p.get("part") == PART and p.get("primary") is True)
    return profile, pin


def verify_zip(path: Path, pin: dict[str, Any]) -> str:
    """The zip's sha256 after checking size, md5 and sha256 against the pin (exit on any mismatch)."""
    sha, md5, size = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    if size != pin["size"] or md5.hexdigest() != pin["md5"] or sha.hexdigest() != pin["sha256"]:
        raise SystemExit("the zip does not match the profile pin (size, md5 or sha256)")
    return sha.hexdigest()


def _members(path: Path, container: str, include: tuple[str, ...], exclude: tuple[str, ...],
             tally: Counter[str]) -> Iterator[tuple[str, str, int, int, int, bytes]]:
    from agentprov.adapters.runner.importer import _match
    from agentprov.ingest.archives import iter_zip_members, open_archive

    def selected(label: str) -> bool:
        return any(_match(label, g) for g in include) and not any(_match(label, g) for g in exclude)

    with path.open("rb") as fh, open_archive(fh, release=True) as archive:
        for member in iter_zip_members(archive, selected):
            tally[member.disposition if member.code is None else f"{member.disposition}:{member.code}"] += 1
            if member.disposition == "selected" and member.label is not None:
                yield container, member.label, member.method, member.crc32, member.file_size, archive.read_member(member)


def census(path: Path, workers: int) -> dict[str, Any]:
    from agentprov.adapters.agentdojo.census import add, compare, declared
    from agentprov.adapters.agentdojo.profile import family_table

    profile, pin = _pin()
    container = verify_zip(path, pin)
    include = tuple(profile.data["import"]["include"])
    exclude = tuple(e["glob"] for e in profile.data["import"].get("exclude", ()))
    started = time.perf_counter()
    gate: Counter[str] = Counter()
    totals: dict[str, dict[str, int]] = {}
    status: Counter[str] = Counter()
    variants: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    found: Counter[str] = Counter()
    units: Counter[str] = Counter()
    crashes: list[dict[str, Any]] = []
    samples: dict[str, list[str]] = {}
    aer: dict[str, str] = {}
    with Pool(workers) as pool:
        for row in pool.imap(_work, _members(path, container, include, exclude, gate), chunksize=16):
            status[row["status"]] += 1
            if row["status"] == "crash":
                crashes.append({"path": row["path"], "code": row.get("code")})
                continue
            if row["status"] in ("not_dialect", "not_selected"):
                continue
            aer[row["path"]] = row["records_sha256"]
            variants[str(row["variant"])] += 1
            units[str(row["unit"])] += 1
            found.update(row["findings"])
            issues.update(row["issues"])
            for code in row["issues"]:
                if len(samples.setdefault(code, [])) < 5:
                    samples[code].append(row["path"])
            add(totals, row["census"])
    table = family_table(profile)
    return {
        "profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256}, "part": PART,
        "pin": {"doi": pin["doi"], "file": pin["file"], "sha256": container},
        "gate": dict(sorted(gate.items())), "files": sum(status.values()), "status": dict(sorted(status.items())),
        "variants": dict(sorted(variants.items())), "units": dict(sorted(units.items())),
        "validation_findings": dict(sorted(found.items())), "files_by_issue_code": dict(sorted(issues.items())),
        "crashes": crashes[:50], "issue_samples": {c: samples[c] for c in sorted(samples) if issues[c] < sum(status.values())},
        "measured": {q: dict(sorted(k.items())) for q, k in sorted(totals.items())},
        "declared": declared(table, PART), "differences": compare(table, PART, totals),
        "records_digest_of_digests": hashlib.sha256("".join(f"{k}\t{v}\n" for k, v in sorted(aer.items())).encode()).hexdigest(),
        "elapsed_s": round(time.perf_counter() - started, 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("census")
    c.add_argument("--zip", type=Path, required=True)
    c.add_argument("--workers", type=int, default=8)
    c.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    report = census(args.zip, args.workers)
    text = json.dumps(report, indent=1, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
