"""Phase 10n: trial import of the AutoGen guard-placement deposit into a scratch corpus (D-301; R-10k-1, D-320).

    uv run python tools/autogen/phase10n_trial.py ZIP --corpus DIR [--jobs N]

``ZIP`` is the pinned deposit file (Zenodo 23025259 v1.0). Its size and sha256 are checked against the profile's primary
pin before anything is read (offline; the file was downloaded with the user's yes in phase 10e). The import runs
:func:`agentprov.adapters.runner.importer.import_source` on an :class:`ArchiveTree` (D-200 archive input), in release
mode, through the validation stage. It bypasses the CLI status gate on purpose: the registry part stays ``planned`` until
a recorded full import (D.3.2), as ``tools/inspect/phase10h_trial.py`` does. It refuses to write under
``~/.agentprov/corpora``. The summary holds counts and codes only, never source text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

PROFILE = "autogen-guard-placement"


def run(zip_path: Path, corpus: Path, jobs: int) -> dict[str, Any]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.ingest.limits import IngestLimits

    if str(corpus.resolve()).startswith(str((Path.home() / ".agentprov" / "corpora").resolve())):
        raise SystemExit("trial imports never write into ~/.agentprov/corpora")
    profile = load_profile(PROFILE)
    (pin,) = [dict(p) for p in profile.data["source"]["pins"] if p.get("primary") is True]
    data = zip_path.read_bytes()
    if len(data) != pin["size"] or hashlib.sha256(data).hexdigest() != pin["sha256"] or zip_path.name != pin["file"]:
        raise SystemExit("the file is not the pinned deposit file")
    pin_record = {**pin, "bytes": pin["size"]}
    tree = ArchiveTree(zip_path, pin=pin_record, sha256=pin["sha256"], size=pin["size"])
    limits = IngestLimits()
    started = time.perf_counter()
    with CorpusWriter(corpus, limits=limits, release=True, command="import") as writer:
        report = import_source(profile.source_id, tree, corpus=writer, profile_id=profile.id, mode="release",
                               part=profile.parts[0], snapshot_id=profile.parts[0], corpus_id=profile.source_id,
                               until="validation", workers=jobs, limits=limits, pin=pin_record)
    return {"profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256}, "jobs": jobs,
            "exit_code": report.exit_code, "counters": dict(report.counters),
            "issues_by_code": dict(sorted(report.issues_by_code.items())),
            "failures": [{"stage": f["stage"], "code": f["code"]} for f in report.failures[:50]],
            "elapsed_s": round(time.perf_counter() - started, 1)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("zip", type=Path)
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args(argv)
    out = run(args.zip, args.corpus, args.jobs)
    json.dump(out, sys.stdout, indent=1, sort_keys=True)
    print()
    return int(out["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
