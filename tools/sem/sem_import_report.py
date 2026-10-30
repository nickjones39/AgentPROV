"""Phase-7 import report: the SEM stage and the assessment bundles of a working corpus (numbers, codes and digests only).

Reads ``executions.jsonl``, ``derivation.json``, ``validation/results.jsonl`` and every PROV-JSON file of a working corpus
written by ``agentprov import`` (``--until validation``) and writes a JSON report:

- executions; SEM stage states per profile; the SEM set digest ``sha256`` over the sorted ``"<ex> <sem digest>\\n"``
  lines (HL ``sem_set``);
- the ``sem`` stage definition recorded in ``derivation.json`` (profile digests, catalogue versions, engine code digest);
- tier-3 check states (``<profile>:SEM-Vnn``) and tier-4 verdicts from the validation rows;
- assessment-bundle content summed over all PROV files: ``apv:Assessment`` entities by claim, mention entities, and
  ambiguous payload claims;
- with ``--compare <reference working corpus>``: how many AER digests equal the reference's (SEM must change no AER).

No source text is read or written. Usage::

    uv run python tools/sem/sem_import_report.py --corpus ~/.agentprov/corpora/<id>.partial \\
        [--compare ~/.agentprov/corpora/<phase-6 id>.partial] --out docs/reports/sem/<name>.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _rows(corpus: Path) -> dict[str, dict[str, Any]]:
    with (corpus / "executions.jsonl").open("rb") as fh:
        return {r["ex"]: r for r in (json.loads(line) for line in fh)}


def _assessment(corpus: Path, rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    claims: Counter[str] = Counter()
    mentions = ambiguous = bundles = 0
    for row in rows.values():
        for spec, entry in (row.get("paths", {}).get("prov") or {}).items():
            doc = json.loads((corpus / entry["json"]).read_bytes())
            for iri, bundle in (doc.get("bundle") or {}).items():
                if ".assess." not in iri:
                    continue
                bundles += 1
                for body in (bundle.get("entity") or {}).values():
                    claim = body.get("apv:claim")
                    if isinstance(claim, dict):
                        claims[str(claim.get("$"))] += 1
                        status = body.get("apv:markerStatus")
                        ambiguous += isinstance(status, dict) and status.get("$") == "apv:Ambiguous"
                mentions += len(bundle.get("mentionOf") or {})
            del spec
    return {"bundles": bundles, "assessments_by_claim": dict(sorted(claims.items())), "mentions": mentions,
            "payload_ambiguous": ambiguous}


def report(corpus: Path, compare: Path | None) -> dict[str, Any]:
    rows = _rows(corpus)
    sem_states: dict[str, Counter[str]] = {}
    lines: dict[str, list[str]] = {}
    for ex, row in sorted(rows.items()):
        for profile, state in (row["stages"].get("sem") or {}).items():
            sem_states.setdefault(profile, Counter())[state] += 1
            digest = row["digests"]["sem"][profile]
            if digest is not None:
                lines.setdefault(profile, []).append(f"{ex} {digest}\n")
    derivation = json.loads((corpus / "derivation.json").read_bytes())
    sem_stage = next((s for s in derivation["stages"] if s.get("stage") == "sem"), None)
    tier3: dict[str, Counter[str]] = {}
    verdicts: Counter[str] = Counter()
    with (corpus / "validation" / "results.jsonl").open("rb") as fh:
        for line in fh:
            row = json.loads(line)
            verdicts[row.get("verdict", "?")] += 1
            for check, status in row.get("checks", {}).items():
                if ":SEM-V" in check:
                    tier3.setdefault(check.split(":", 1)[1], Counter())[status] += 1
    out: dict[str, Any] = {
        "format": "agentprov-sem-import-report/0.1",
        "executions": len(rows),
        "status": dict(sorted(Counter(r["status"] for r in rows.values()).items())),
        "sem": {p: dict(sorted(c.items())) for p, c in sorted(sem_states.items())},
        "sem_set_sha256": {p: "sha256:" + hashlib.sha256("".join(ls).encode("ascii")).hexdigest()
                           for p, ls in sorted(lines.items())},
        "sem_stage": None if sem_stage is None else {k: sem_stage[k] for k in sorted(sem_stage)
                                                     if k in ("profiles", "rules", "engine_code_sha256", "format", "fn_digest")},
        "tier3_checks": {c: dict(sorted(s.items())) for c, s in sorted(tier3.items())},
        "validation_verdicts": dict(sorted(verdicts.items())),
        "assessment": _assessment(corpus, rows),
    }
    if compare is not None:
        reference = _rows(compare)
        out["aer_digests_equal_to_reference"] = sum(1 for ex, r in rows.items()
                                                    if ex in reference and reference[ex]["digests"]["aer"] == r["digests"]["aer"])
        out["reference_executions"] = len(reference)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report(args.corpus, args.compare), indent=1, sort_keys=True) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
