"""Phase 10n: map every run row of the AutoGen guard-placement deposit in memory (D-301; the D-154 method).

    uv run python tools/autogen/phase10n_map.py ZIP [--out CENSUS.json] [--prov] [--limit N]

``ZIP`` is the pinned deposit file (Zenodo 23025259 v1.0; its sha256 is checked against the profile pin). The zip is
read through :mod:`agentprov.ingest` (never extracted). Every ``runs.jsonl`` member the profile includes is parsed by the
reader; each run row becomes one ``ExecutionUnit`` (locator ``{"line": n}``) whose per-unit inputs are the members the
reader's ``auxiliary_for`` names, each under its ``member`` origin; the unit is mapped by :func:`map_unit`, sealed, and
validated in release mode (``store=None``: locators are not resolved here). With ``--prov`` the SEM and PROV stages
run too (tier-4 validation is not run here). The output holds counts, codes and labels only, never source text.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

from agentprov.adapters.autogen.dialect import AutoGenRunsReader, parse_label
from agentprov.adapters.autogen.mapper import AutoGenMapper
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import aer_bytes, map_unit
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, LocatedItem
from agentprov.aer.reader import load_aer_bytes
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import validate_records
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.raw.origins import Origin

PROFILE = "autogen-guard-placement"
MEDIA = {".jsonl": "application/jsonl", ".json": "application/json"}


class _Listing:
    def __init__(self, labels: set[str]) -> None:
        self.labels = labels

    def siblings(self, label: str) -> tuple[str, ...]:
        head = label.rsplit("/", 1)[0] + "/"
        return tuple(sorted(x for x in self.labels if x.startswith(head) and "/" not in x[len(head):]))

    def exists(self, ref: str) -> bool:
        return ref in self.labels


def _media(label: str) -> str:
    return next((m for ext, m in MEDIA.items() if label.endswith(ext)), "application/octet-stream")


def load_members(zip_path: Path) -> tuple[str, dict[str, tuple[bytes, int]]]:
    """``(container sha256, {label: (bytes, method)})`` of every selected member."""
    raw = zip_path.read_bytes()
    container = hashlib.sha256(raw).hexdigest()
    out: dict[str, tuple[bytes, int]] = {}
    with open_zip(io.BytesIO(raw), IngestLimits(), release=False) as z:
        for m in iter_zip_members(z):
            if m.disposition == "selected" and m.label is not None:
                out[m.label] = (z.read_member(m), m.method)
    return container, out


def units_of(label: str, members: dict[str, tuple[bytes, int]], container: str) -> list[tuple[ExecutionUnit, dict[str, bytes]]]:
    """One unit per run row of the run file ``label``, with its auxiliary refs and bytes."""
    reader = AutoGenRunsReader()
    data, method = members[label]
    origin = Origin.member(container, label, method, zlib.crc32(data), len(data))
    artefact = ArtefactRef(id="a0", sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), media=_media(label),
                           origin=origin, role="primary", prov_primary="native")
    plan = reader.auxiliary_for(label, _Listing(set(members)))
    aux: dict[str, ArtefactRef] = {}
    aux_bytes: dict[str, bytes] = {}
    for n, (role, ref) in enumerate(sorted(plan.items())):
        body, meth = members[ref]
        aux[role] = ArtefactRef(id=f"x{n}", sha256=hashlib.sha256(body).hexdigest(), bytes=len(body), media=_media(ref),
                                origin=Origin.member(container, ref, meth, zlib.crc32(body), len(body)),
                                role="supporting", prov_primary="unknown")
        aux_bytes[role] = body
    items: list[LocatedItem] = list(reader.parse(data, artefact, limits=IngestLimits()))
    return [(ExecutionUnit(primary=item, auxiliary=aux), aux_bytes) for item in items]


def map_one(unit: ExecutionUnit, aux_bytes: dict[str, bytes], *, prov: bool = False) -> dict[str, Any]:
    profile = load_profile(PROFILE)
    mapper = AutoGenMapper()
    outcome = map_unit(unit, mapper, profile, auxiliary=aux_bytes)
    sealed, _info = aer_bytes(outcome)
    doc = load_aer_bytes(sealed)
    report = validate_records([*doc.records, doc.seal], store=None, catalogues=RuleRegistry.default(), mode="release")
    result: dict[str, Any] = {"outcome": outcome, "sealed": sealed, "doc": doc, "report": report}
    if prov:
        from agentprov.adapters.semantics_profiles import load_semantics_profile
        from agentprov.prov.engine import derive
        from agentprov.sem.engine import annotate

        sem_profile = load_semantics_profile("autogen.tools", 1)
        sem = annotate(doc, sem_profile)
        result["sem"] = sem
        result["prov"] = derive(doc, [sem], sem_profiles={(sem_profile.id, sem_profile.version): sem_profile})
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("zip", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--prov", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    profile = load_profile(PROFILE)
    (pin,) = [p for p in profile.data["source"]["pins"] if p.get("primary")]
    container, members = load_members(args.zip)
    if container != pin["sha256"]:
        print("the zip is not the pinned deposit file", file=sys.stderr)
        return 2
    imp = profile.data["import"]
    reader = AutoGenRunsReader()

    class _Tree:
        def walk(self):  # minimal SourceTree for iter_artefacts
            from agentprov.adapters.types import CandidateArtefact

            for lab, (body, meth) in sorted(members.items()):
                yield CandidateArtefact(lab, len(body), Origin.member(container, lab, meth, zlib.crc32(body), len(body)))

    chosen = [c.label for c in reader.iter_artefacts(_Tree(), profile)]  # type: ignore[arg-type]
    excluded = {e["glob"]: e["code"] for e in imp["exclude"]}
    census: dict[str, Any] = {"container": container, "files": len(chosen), "units": 0, "degenerate": 0,
                              "valid_release": 0, "invalid": Counter(), "issues": Counter(), "unit_kind": Counter(),
                              "records": Counter(), "checks": Counter(), "variants": Counter(), "by_file": {},
                              "excluded_files": {}, "sem_annotations": Counter(), "prov_ok": 0}
    for glob, code in sorted(excluded.items()):
        body = members.get(glob)
        if body is not None:
            sniff = reader.sniff(body[0], label=glob, limits=IngestLimits())
            rows = body[0].count(b"\n")
            census["excluded_files"][glob] = {"code": code, "rows": rows, "reasons": list(sniff.reasons)}
    done = 0
    for label in chosen:
        if parse_label(label) is None:
            continue
        units = units_of(label, members, container)
        census["by_file"][label] = len(units)
        for unit, aux in units:
            if args.limit is not None and done >= args.limit:
                break
            done += 1
            r = map_one(unit, aux, prov=args.prov)
            census["units"] += 1
            census["variants"][unit.primary.variant] += 1
            if r["outcome"].degenerate:
                census["degenerate"] += 1
            census["unit_kind"][r["doc"].header["unit"]] += 1
            for rec in r["doc"].records:
                census["records"][rec["k"]] += 1
            for issue in r["doc"].seal.get("issues", []):
                census["issues"][issue["code"]] += 1
            for check in r["doc"].seal.get("accounting", {}).get("checks", []):
                census["checks"][f"{check['id']}:{check['verdict']}"] += 1
            if r["report"].ok:
                census["valid_release"] += 1
            else:
                for f in r["report"].findings:
                    census["invalid"][f"{f.code} {f.pointer or ''}"[:120]] += 1
            if args.prov:
                for a in r["sem"].annotations:
                    census["sem_annotations"][a["type"]] += 1
                census["prov_ok"] += 1
    out = {k: (dict(sorted(v.items())) if isinstance(v, Counter) else v) for k, v in census.items()}
    text = json.dumps(out, indent=1, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
