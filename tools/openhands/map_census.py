"""Map every run of an OpenHands source end to end, offline (phase 10g; D-170-D-179).

    uv run python -I tools/openhands/map_census.py oas --tree OAS_WORKTREE [--out REPORT.json] [--digests D.jsonl] [--jobs N]
    uv run python -I tools/openhands/map_census.py redcode --zips ZIP_DIR [--out REPORT.json] [--digests D.jsonl] [--jobs N]

For each trajectory: the reader's auxiliary plan, :func:`agentprov.adapters.runner.map_artefact_total`, sealing through
the AER writer (release-mode validation), SEM with the semantics profile the source profile selects, PROV with ``agentprov-prov/0.1`` and the tier-4
checks (:func:`agentprov.validate.prov.validate_prov`, round trip included). OpenAgentSafety files get their git origin
at the pin (``blob_sha1`` computed from the bytes); RedCode members get their ``member`` origin (container sha256, label,
method, crc32, size) and are read in memory through ``agentprov.ingest`` (never extracted). The runner does not import
deposit archives yet (D-156), so for RedCode this census is the mapping half of an import: nothing is stored or sealed
into a corpus.

The report holds counts, codes and labels only, never source text. ``--digests`` writes one line per run (label and the
sha256 of the sealed AER, the SEM and the PROV bytes) so that two runs with different worker counts can be compared.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

OAS_REPO = "https://github.com/sani903/OpenAgentSafety"
OAS_COMMIT = "857798ff26c4ce6e1d7911ee4d8b3f84a71184e0"

_STATE: dict[str, Any] = {}


def _init(mode: str, root: str) -> None:
    from agentprov.ingest.archives import iter_zip_members, open_zip

    _STATE["mode"], _STATE["root"] = mode, Path(root)
    if mode == "oas":
        base = Path(root)
        labels = [p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file() and ".git" not in p.parts]
        _STATE["labels"] = labels
        return
    members: dict[str, Any] = {}
    meta: dict[str, tuple[str, int, int, int]] = {}
    handles = []
    for z in sorted(Path(root).glob("*.zip")):
        if not (z.name.startswith("trajectories_OH-") or z.name == "agent-execution-decisions-supp.zip"):
            continue
        csha = hashlib.sha256(z.read_bytes()).hexdigest()
        fp = open(z, "rb")  # noqa: SIM115 - kept open for the worker's lifetime
        oz = open_zip(fp, release=True)
        handles.append((fp, oz))
        for m in iter_zip_members(oz):
            if m.label is None or m.disposition != "selected" or m.label.startswith("environment/"):
                continue
            members[m.label] = (oz, m)
            meta[m.label] = (csha, m.method, m.crc32, m.file_size)
    _STATE.update(members=members, meta=meta, handles=handles, labels=list(members))


def _read(label: str) -> bytes:
    if _STATE["mode"] == "oas":
        return (_STATE["root"] / label).read_bytes()
    oz, m = _STATE["members"][label]
    return bytes(oz.read_member(m))


def _origin(label: str, data: bytes) -> Any:
    from agentprov.adapters.runner.importer import git_blob_sha1
    from agentprov.adapters.types import Origin

    if _STATE["mode"] == "oas":
        return Origin.git(OAS_REPO, OAS_COMMIT, label, git_blob_sha1(data))
    csha, method, crc, size = _STATE["meta"][label]
    return Origin.member(csha, label, method, crc, size)


def _one(label: str) -> dict[str, Any]:
    from agentprov.adapters.openhands.dialect import OpenHandsEventsReader
    from agentprov.adapters.runner import aer_bytes, map_artefact_total
    from agentprov.adapters.runner.importer import _AuxListing, aux_media
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.prov.engine import derive
    from agentprov.sem.engine import annotate, dumps_sem
    from agentprov.validate.prov import validate_prov

    row: dict[str, Any] = {"label": label}
    profile_id = "openagentsafety" if _STATE["mode"] == "oas" else "redcode-exec-openhands"
    try:
        listing = _STATE.setdefault("listing", _AuxListing(_STATE["labels"], {}))
        plan = OpenHandsEventsReader().auxiliary_for(label, listing)
        rows, blobs = [], {}
        for role, ref in sorted(plan.items()):
            raw = _read(ref)
            rows.append({"role": role, "label": ref, "media": aux_media(ref), "sha256": hashlib.sha256(raw).hexdigest(),
                         "size": len(raw), "origin": _origin(ref, raw).to_json()})
            blobs[role] = raw
        data = _read(label)
        outcome, unit = map_artefact_total(data, _origin(label, data), profile_id=profile_id, auxiliary=rows,
                                           auxiliary_bytes=blobs)
        sealed, _info = aer_bytes(outcome)
        doc = load_aer_bytes(sealed)
        from agentprov.adapters.profiles import load_profile

        selected = load_profile(profile_id).family_table()["semantics_profile"]
        profile = load_semantics_profile(str(selected["id"]), int(selected["version"]))
        sem = annotate(doc, profile)
        prov = derive(doc, [sem], sem_profiles={(profile.id, profile.version): profile})
        report = validate_prov(prov.prov_json, doc, sems=[sem])
        sem_bytes = dumps_sem(sem)
        row.update(
            status="degenerate" if outcome.degenerate else "mapped",
            variant=unit.primary.variant,
            plan=sorted(plan),
            kinds=dict(Counter(r["k"] for r in doc.records)),
            issues=dict(Counter(i["code"] for i in doc.seal["issues"])),
            accounting=doc.seal["accounting"]["status"],
            annotations=dict(Counter(a["type"] for a in sem.annotations)),
            outcomes=dict(Counter(f"{a['value'].get('claim')}={a['value'].get('holds')}" for a in sem.annotations
                                  if a["type"] == "outcome")),
            tier4=dict(Counter(f"{o.id}:{o.status}" for o in report.outcomes if o.status != "pass")),
            classes=dict(Counter(f"{r['k']}:{r['ev']}" for r in doc.records[1:-1] if "ev" in r)),
            aer_sha256=hashlib.sha256(sealed).hexdigest(),
            sem_sha256=hashlib.sha256(sem_bytes).hexdigest(),
            prov_sha256=hashlib.sha256(prov.prov_json).hexdigest(),
        )
    except Exception as exc:  # a crash is a finding; the label is the pinned name, never content
        row.update(status="crash", code=getattr(exc, "code", type(exc).__name__), error=type(exc).__name__)
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("oas")
    a.add_argument("--tree", type=Path, required=True)
    b = sub.add_parser("redcode")
    b.add_argument("--zips", type=Path, required=True)
    for p in (a, b):
        p.add_argument("--out", type=Path)
        p.add_argument("--digests", type=Path)
        p.add_argument("--jobs", type=int, default=8)
        p.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)
    root = str(args.tree if args.cmd == "oas" else args.zips)
    _init(args.cmd, root)
    from agentprov.adapters.openhands.dialect import parse_path

    labels = sorted(lab for lab in _STATE["labels"] if parse_path(lab) is not None and (
        lab.rsplit("/", 1)[-1].startswith("traj_") if args.cmd == "oas" else "/trajectory/" in lab))
    if args.limit:
        labels = labels[: args.limit]
    started = time.time()
    with mp.Pool(args.jobs, initializer=_init, initargs=(args.cmd, root)) as pool:
        rows = list(pool.imap(_one, labels, chunksize=8))
    totals: dict[str, Counter[str]] = {k: Counter() for k in ("status", "variant", "plan", "kinds", "issues", "issue_runs",
                                                                 "accounting", "annotations", "outcomes", "tier4", "classes",
                                                                 "crash")}
    for row in rows:
        totals["status"][row["status"]] += 1
        if row["status"] == "crash":
            totals["crash"][str(row.get("code"))] += 1
            continue
        totals["variant"][row["variant"]] += 1
        totals["accounting"][row["accounting"]] += 1
        totals["plan"][",".join(row["plan"])] += 1
        for key in ("kinds", "issues", "annotations", "outcomes", "tier4", "classes"):
            totals[key].update(row[key])
        totals["issue_runs"].update(row["issues"].keys())
    report = {
        "source": args.cmd,
        "runs": len(rows),
        "seconds": round(time.time() - started, 1),
        "jobs": args.jobs,
        **{k: dict(sorted(v.items(), key=lambda kv: (-kv[1], kv[0]))) for k, v in totals.items()},
    }
    text = json.dumps(report, indent=1, ensure_ascii=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.digests:
        with args.digests.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps({k: row.get(k) for k in ("label", "status", "aer_sha256", "sem_sha256", "prov_sha256")},
                                    sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("runs", "seconds", "status", "accounting", "crash", "tier4")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
