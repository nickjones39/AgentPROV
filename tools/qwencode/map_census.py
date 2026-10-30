"""TRIAL AND CENSUS ONLY (never product code): map every Qwen Code run of Zenodo 23168099 in memory (phase 10o part C).

Reads ``trajectories_Qwen-qwen3coder.zip`` and the supplementary zip through :mod:`agentprov.ingest` (never extracted).
The supplementary zip's score records, requests and execution rules are listed under ``supp:<label>`` references, the
shape a context tree will give once D-530 wires context pins (routed; the product import waits for it). Each run is
mapped with :func:`agentprov.adapters.runner.map_artefact_total` under ``member`` origins, as the import pipeline's ``map``
job would; with ``--validate`` every sealed AER is validated (dev and release), annotated and derived to PROV (tier 4).

Prints counts, issue codes, check verdicts and finding codes only: the deposit holds RedCode payloads.

Usage: ``uv run python tools/qwencode/map_census.py RUNS.zip SUPP.zip [--every N] [--validate] [--out census.json]``
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

from agentprov.adapters.qwencode.dialect import API_SAMPLE, SUPP_ROLE, QwenJsonReader, parse_label
from agentprov.adapters.runner import NotOfDialect, aer_bytes, map_artefact_total
from agentprov.adapters.runner.importer import _AuxListing, aux_media
from agentprov.adapters.types import Origin
from agentprov.aer.reader import load_aer_bytes
from agentprov.aer.writer import AerWriteError
from agentprov.ingest.archives import iter_zip_members, open_archive
from agentprov.ingest.limits import IngestLimits

PROFILE = "redcode-exec-qwencode"
SUPP_PREFIXES = ("results/Qwen/", "dataset/RedCode-Exec/", "prompt_generator/output/", "OH_evaluation/execution_rules.md")


def read_zip(path: str, want: Any) -> tuple[str, dict[str, tuple[bytes, int]]]:
    """The container's sha256 and its selected members: label -> (bytes, method)."""
    limits = IngestLimits()
    with open(path, "rb") as fp:
        sha = hashlib.sha256(fp.read()).hexdigest()
    out: dict[str, tuple[bytes, int]] = {}
    with open(path, "rb") as fp, open_archive(fp, limits, release=False) as z:
        for m in iter_zip_members(z, want, limits):
            if m.disposition == "selected" and m.label is not None:
                out[m.label] = (z.read_member(m), int(m.method))
    return sha, out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("supp")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    runs_sha, runs = read_zip(args.runs, lambda label: "/trajectory/" in label)
    supp_sha, supp = read_zip(args.supp, lambda label: label.startswith(SUPP_PREFIXES) and "/OH/" not in label)
    reader = QwenJsonReader()
    listing = _AuxListing(sorted(runs), {SUPP_ROLE: sorted(supp)})
    primaries = sorted(label for label in runs if parse_label(label) is not None)[:: max(args.every, 1)]

    def ref_bytes(ref: str) -> tuple[bytes, Origin]:
        if ref.startswith(SUPP_ROLE + ":"):
            label = ref.split(":", 1)[1]
            data, method = supp[label]
            return data, Origin.member(supp_sha, label, method, zlib.crc32(data), len(data))
        data, method = runs[ref]
        return data, Origin.member(runs_sha, ref, method, zlib.crc32(data), len(data))

    counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    if args.validate:
        from agentprov.adapters.semantics_profiles import load_semantics_profile
        from agentprov.aer.rules import RuleRegistry

        sem_profile = load_semantics_profile("qwencode.tools", 2)
        registry = RuleRegistry.default()
    started = time.monotonic()
    digests: dict[str, str] = {}
    for label in primaries:
        plan = reader.auxiliary_for(label, listing)
        rows, blobs = [], {}
        for role, ref in sorted(plan.items()):
            data, origin = ref_bytes(ref)
            rows.append({"role": role, "label": ref, "media": aux_media(ref), "sha256": hashlib.sha256(data).hexdigest(),
                         "size": len(data), "origin": origin.to_json()})
            blobs[role] = data
        counts["plan_roles"][",".join(sorted(plan))] += 1
        data, origin = ref_bytes(label)
        try:
            outcome, _unit = map_artefact_total(data, origin, profile_id=PROFILE, auxiliary=rows, auxiliary_bytes=blobs)
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
        counts["mapped_by_group"][f"{facets.target}/{facets.language}"] += 1
        counts["degenerate"][str(outcome.degenerate)] += 1
        digests[label] = hashlib.sha256(sealed).hexdigest()
        for issue in doc.seal.get("issues", []):
            counts["issues"][issue["code"]] += 1
        for check in doc.seal.get("accounting", {}).get("checks", []):
            counts["checks"][f"{check['id']}:{check['verdict']}:{check.get('reason')}"] += 1
        run = next((r for r in doc.records if r.get("k") == "scope" and r.get("id") == "run"), {})
        counts["run_status"][str(run.get("status", "unk"))] += 1
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
    out: dict[str, Any] = {"runs_sha256": runs_sha, "supp_sha256": supp_sha, "primaries": len(primaries),
                           "api_samples": sum(1 for label in runs if label.endswith(API_SAMPLE)),
                           "elapsed_s": round(time.monotonic() - started, 1),
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
