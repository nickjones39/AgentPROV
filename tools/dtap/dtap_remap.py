"""D02 for DTap: re-map every ``agent_execution`` of a DTap corpus from its raw objects and compare the AER bytes.

    uv run python -I tools/dtap/dtap_remap.py --corpus DIR --out ROWS.jsonl [--jobs 4] [--limit N]

The generic re-map (``tools/analysis2/exam2_determinism.py`` ``_remap``) passes context artefacts by the profile's
``context_artefacts`` globs and no per-unit auxiliary artefacts, so it cannot rebuild a DTap unit (runner items R1/R2:
the directory's judge file, the other attempts of a re-run group and the joined configuration of the ``tasks`` pin).
This helper rebuilds them **from ``raw/origins.jsonl`` and the raw store only**: the listing of each pinned tree is the
set of stored origin paths, the reader's ``auxiliary_for`` plan is computed on it, and every auxiliary row (label,
sha256, size, origin) and its bytes come from the stored objects, never from the AER header. The primary's origin is the
header's ``a0`` origin (as in the generic tool). Each line of ``--out``: ``{ex, aer_equal, ...}`` (counts, ids and record
keys only; no corpus text).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

PROFILE = "dtap-bench"
RUNS_ROLE = "runs"
_ROOT: Path | None = None
_STATE: dict[str, Any] = {}


def _init(root: str) -> None:
    from agentprov.adapters.profiles import load_profile

    global _ROOT
    _ROOT = Path(root)
    profile = load_profile(PROFILE)
    pins = {p["role"]: p for p in profile.data["source"]["pins"]}
    runs_repo = str(profile.data["source"].get("canonical_repo") or pins[RUNS_ROLE].get("repo"))
    tasks_repo = str(pins["tasks"]["repo"])
    by_label: dict[tuple[str, str], dict[str, Any]] = {}
    for line in (_ROOT / "raw" / "origins.jsonl").read_bytes().splitlines():
        if not line:
            continue
        row = json.loads(line)
        origin = row["origin"]
        if origin.get("kind") != "git":
            continue
        tree = "runs" if origin.get("repo") == runs_repo else ("tasks" if origin.get("repo") == tasks_repo else None)
        if tree is not None:
            by_label.setdefault((tree, str(origin["path"])), row)
    _STATE.update(by_label=by_label, runs=[p for t, p in by_label if t == "runs"], tasks=[p for t, p in by_label if t == "tasks"])


def _bytes(sha: str) -> bytes:
    assert _ROOT is not None
    h = sha.removeprefix("sha256:")
    return next(p for p in (_ROOT / "raw" / "objects" / h[:2]).glob(h + "*") if p.is_file()).read_bytes()


def remap(row: dict[str, Any]) -> dict[str, Any]:
    from agentprov.adapters.dtap.dialect import DtapTrajectoryReader
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner import _family_classes, aer_bytes, degenerate_unit, map_artefact_total  # noqa: PLC2701
    from agentprov.adapters.runner.importer import _AuxListing  # noqa: PLC2701 - the importer's own listing type
    from agentprov.aer.rules import RuleRegistry
    from agentprov.raw.origins import Origin

    assert _ROOT is not None
    aer = (_ROOT / row["paths"]["aer"]).read_bytes()
    header = json.loads(aer.split(b"\n", 1)[0])
    prim = next(a for a in header["artifacts"] if a.get("role") == "primary")
    data = _bytes(prim["sha256"])
    origin = Origin.from_json(prim["origin"])
    label = str(prim["origin"].get("path") or prim["origin"].get("file"))  # an hf origin names its file
    listing = _AuxListing(_STATE["runs"], {"tasks": _STATE["tasks"]})
    plan = DtapTrajectoryReader().auxiliary_for(label, listing)
    rows: list[dict[str, Any]] = []
    blobs: dict[str, bytes] = {}
    for role, ref in sorted(plan.items()):
        if role.startswith("copy:"):
            continue
        tree, _, path = ref.partition(":") if ref.startswith("tasks:") else ("runs", "", ref)
        stored = _STATE["by_label"].get((tree, path))
        if stored is None:
            return {"ex": row["ex"], "error": f"auxiliary_not_stored:{role}"}
        sha = str(stored["sha256"]).removeprefix("sha256:")
        raw = _bytes(sha)
        rows.append({"role": role, "label": ref, "sha256": sha, "size": len(raw), "origin": stored["origin"]})
        blobs[role] = raw
    profile = load_profile(PROFILE)
    registry = RuleRegistry.default()
    outcome, _unit = map_artefact_total(data, origin, profile_id=PROFILE, part="head", registry=registry, auxiliary=rows,
                                        auxiliary_bytes=blobs)
    imp = profile.data.get("import", {})
    _reader, mapper = _family_classes(str(imp.get("dialect")), str(imp.get("mapper")))
    fallback = degenerate_unit(prim["sha256"], len(data), origin, profile=profile, mapper=mapper)
    got, _info = aer_bytes(outcome, registry=registry, unit=fallback, mapper=mapper, profile=profile)
    res: dict[str, Any] = {"ex": row["ex"], "aer_equal": got == aer, "auxiliary_roles": sorted(r["role"].split(":")[0] for r in rows)}
    if got != aer:
        a, b = got.split(b"\n"), aer.split(b"\n")
        res["lines"] = [len(a), len(b)]
        first = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), None)
        res["first_diff_line"] = first
        if first is not None:
            x, y = json.loads(a[first]), json.loads(b[first])
            res["diff_keys"] = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))[:10]
            res["diff_record"] = f"{y.get('k')}:{y.get('id')}"
    return res


def job(line: bytes) -> dict[str, Any]:
    row = json.loads(line)
    try:
        return remap(row)
    except Exception as exc:  # noqa: BLE001 - recorded, never hidden
        return {"ex": row["ex"], "error": type(exc).__name__}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)
    root = a.corpus if (a.corpus / "executions.jsonl").exists() else a.corpus.with_name(a.corpus.name + ".partial")
    lines = [x for x in (root / "executions.jsonl").read_bytes().split(b"\n")
             if x and json.loads(x).get("unit") == "agent_execution" and (json.loads(x).get("stages") or {}).get("aer") == "ok"]
    if a.limit:
        lines = lines[: a.limit]
    c: Counter[str] = Counter()
    with open(a.out, "w", encoding="utf-8") as fh, Pool(a.jobs, initializer=_init, initargs=(str(root),)) as pool:
        for res in pool.imap(job, lines, chunksize=4):
            c["equal" if res.get("aer_equal") else ("error:" + res["error"] if "error" in res else "differs")] += 1
            fh.write(json.dumps(res, sort_keys=True) + "\n")
    print(json.dumps({"remapped": len(lines), **dict(sorted(c.items()))}, sort_keys=True))
    return 0 if c.get("equal", 0) == len(lines) else 1


if __name__ == "__main__":
    raise SystemExit(main())
