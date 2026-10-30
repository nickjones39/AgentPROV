"""Map every gemini_cli rollout of Zenodo 20404563 in memory through the product path (phase 10o; D-154 method).

Reads ``RESULTS_raw.tar.zst`` through :mod:`agentprov.ingest` (never extracted), groups each rollout directory's members,
asks the reader for its primary and auxiliary plan (as the import pipeline's discovery does), and maps the primary with
:func:`agentprov.adapters.runner.map_artefact_total` under ``member`` origins. With ``--validate`` every sealed AER is
validated in dev and release mode, annotated with ``geminicli.tools@1`` and derived to PROV (tier-4 validation).

Prints and writes counts, issue codes, check verdicts and finding codes only: the deposit holds adversarial text and one
credential-shaped value, so no content, label text beyond the closed grammar, or value is ever printed.

Usage: ``uv run python tools/geminicli/map_census.py <RESULTS_raw.tar.zst> [--limit N] [--validate] [--out census.json]``
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import time
import zlib
from typing import Any

from agentprov.adapters.geminicli.dialect import STREAM, VERDICT, GeminiStreamReader, parse_label
from agentprov.adapters.runner import NotOfDialect, aer_bytes, map_artefact_total
from agentprov.adapters.runner.importer import _AuxListing, aux_media
from agentprov.adapters.types import Origin
from agentprov.aer.reader import load_aer_bytes
from agentprov.aer.writer import AerWriteError
from agentprov.ingest.archives import open_archive
from agentprov.ingest.limits import IngestLimits

PROFILE = "code-agent-misalignment-geminicli"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("archive")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--every", type=int, default=1, help="map every n-th primary (debugging)")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    limits = IngestLimits()
    sha = hashlib.sha256()
    with open(args.archive, "rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            sha.update(chunk)
    container = sha.hexdigest()
    members: dict[str, bytes] = {}

    def want(label: str) -> bool:
        f = parse_label(label)
        return (f is not None and f.scaffold == "gemini_cli") or label.endswith("/manifest.csv")

    with open(args.archive, "rb") as fp, open_archive(fp, limits, release=False) as tar:
        for m in tar.iter_members(want, limits):
            if m.disposition == "selected" and m.label is not None:
                members[m.label] = tar.read_member(m)
    reader = GeminiStreamReader()
    listing = _AuxListing(sorted(members), {})
    by_dir: dict[str, list[str]] = collections.defaultdict(list)
    for label in members:
        if parse_label(label) is not None:
            by_dir[label.rpartition("/")[0]].append(label)
    primaries = []
    for labels in by_dir.values():
        names = {lab.rsplit("/", 1)[-1]: lab for lab in labels}
        primaries.append(names.get(STREAM) or names[VERDICT])
    primaries.sort()
    primaries = primaries[:: max(args.every, 1)]
    if args.limit:
        primaries = primaries[: args.limit]

    def origin(label: str) -> Origin:
        data = members[label]
        return Origin.member(container, label, 0, zlib.crc32(data), len(data))

    counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    sem_profile = None
    if args.validate:
        from agentprov.adapters.semantics_profiles import load_semantics_profile
        from agentprov.aer.rules import RuleRegistry

        sem_profile = load_semantics_profile("geminicli.tools", 1)
        registry = RuleRegistry.default()
    started = time.monotonic()
    digests: dict[str, str] = {}
    for label in primaries:
        plan = reader.auxiliary_for(label, listing)
        rows = [{"role": role, "label": ref, "media": aux_media(ref), "sha256": hashlib.sha256(members[ref]).hexdigest(),
                 "size": len(members[ref]), "origin": origin(ref).to_json()} for role, ref in sorted(plan.items())]
        blobs = {role: members[ref] for role, ref in plan.items()}
        try:
            outcome, _unit = map_artefact_total(members[label], origin(label), profile_id=PROFILE, auxiliary=rows,
                                                auxiliary_bytes=blobs, media="application/x-ndjson")
        except NotOfDialect as exc:
            counts["not_of_dialect"][str(exc.detail)] += 1
            continue
        try:
            sealed, _info = aer_bytes(outcome)
        except AerWriteError as exc:
            kinds = {i: r.get("k") for i, r in enumerate(outcome.records)}
            for f in exc.findings:
                counts["write_errors"][f"{f.code} {kinds.get(f.line) if f.line is not None else '-'} {f.pointer} {f.detail[:60]}"] += 1
            continue
        doc = load_aer_bytes(sealed)
        facets = parse_label(label)
        assert facets is not None
        counts["mapped_by_cell"][facets.cell] += 1
        counts["degenerate"][str(outcome.degenerate)] += 1
        digests[label] = hashlib.sha256(sealed).hexdigest()
        for issue in doc.seal.get("issues", []):
            counts["issues"][issue["code"]] += 1
        for check in doc.seal.get("accounting", {}).get("checks", []):
            counts["checks"][f"{check['id']}:{check['verdict']}:{check.get('reason')}"] += 1
        status = next((r.get("status", "unk") for r in doc.records if r.get("k") == "scope" and r.get("id") == "run"), "?")
        counts["run_status"][str(status)] += 1
        counts["records"].update(r.get("k", "?") for r in doc.records)
        if args.validate:
            from agentprov.aer.validate import validate_records
            from agentprov.prov.engine import derive
            from agentprov.sem.engine import annotate
            from agentprov.sem.validate import validate_sem_document
            from agentprov.validate import validate_prov

            for mode in ("dev", "release"):
                report = validate_records([*doc.records, doc.seal], store=None, catalogues=registry, mode=mode)
                counts[f"aer_{mode}"]["ok" if report.ok else "failed"] += 1
                counts[f"aer_{mode}_findings"].update(f.code for f in report.findings)
            sem = annotate(doc, sem_profile)
            semv = validate_sem_document(sem, doc, catalogues=registry, mode="release", profile=sem_profile)
            counts["sem"]["ok" if semv.ok else "failed"] += 1
            counts["sem_findings"].update(f.code for f in semv.findings)
            prov = derive(doc, [sem], sem_profiles={(sem_profile.id, sem_profile.version): sem_profile})
            failed = validate_prov(prov.prov_json, doc, sems=[sem]).failed()
            counts["prov"]["ok" if not failed else "failed"] += 1
            counts["prov_failed"].update(getattr(f, "code", str(f))[:80] for f in failed)
    elapsed = time.monotonic() - started
    out: dict[str, Any] = {"container_sha256": container, "primaries": len(primaries), "elapsed_s": round(elapsed, 1),
                           "counts": {k: dict(sorted(v.items())) for k, v in sorted(counts.items())},
                           "aer_digests_sha256": hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest()}
    text = json.dumps(out, indent=1, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
