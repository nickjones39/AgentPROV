"""Phase-10o trial import of the gemini_cli part of Zenodo 20404563, offline, into a scratch corpus only (D-330).

    uv run python tools/geminicli/trial_import.py import  --archive RESULTS_raw.tar.zst --corpus DIR [--jobs N] [--out REPORT.json]
    uv run python tools/geminicli/trial_import.py summary CORPUS_DIR

``import`` checks the local copy of the pinned file against the profile's pin (size and sha256), builds the archive input
(:class:`agentprov.adapters.runner.importer.ArchiveTree`, D-200) and runs
:func:`agentprov.adapters.runner.importer.import_source` in release mode through the validation stage. It bypasses the CLI
status gate on purpose: the registry part stays ``planned`` until a recorded full import (D.3.2). A corpus under
``~/.agentprov/corpora`` is refused. ``summary`` counts a trial corpus: index statuses and stages, failed validation checks
and register codes. Reports hold counts and codes only, never source text or a label beyond the closed grammar.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

PROFILE = "code-agent-misalignment-geminicli"


def run_import(archive: Path, corpus: Path, jobs: int) -> dict[str, Any]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import ArchiveTree, import_source
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.ingest.limits import IngestLimits

    if str(corpus.resolve()).startswith(str((Path.home() / ".agentprov" / "corpora").resolve())):
        raise SystemExit("trial imports never write into ~/.agentprov/corpora")
    profile = load_profile(PROFILE)
    (pin,) = profile.data["source"]["pins"]
    digest = hashlib.sha256()
    with archive.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    size = archive.stat().st_size
    if (digest.hexdigest(), size) != (pin["sha256"], pin["size"]):
        raise SystemExit("the local file does not match the profile's pin")
    limits = IngestLimits()
    tree = ArchiveTree(archive, pin=dict(pin), sha256=pin["sha256"], size=size, limits=limits)
    part = profile.parts[0]
    started = time.perf_counter()
    with CorpusWriter(corpus, limits=limits, release=True, command="import") as writer:
        report = import_source(profile.source_id, tree, corpus=writer, profile_id=profile.id, mode="release", part=part,
                               snapshot_id=part, corpus_id="code-agent-misalignment", until="validation", workers=jobs,
                               limits=limits, pin=dict(pin))
    return {"profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256}, "jobs": jobs,
            "exit_code": report.exit_code, "counters": dict(report.counters),
            "issues_by_code": dict(sorted(report.issues_by_code.items())),
            "failures": [{"stage": f["stage"], "code": f["code"]} for f in report.failures[:50]],
            "notices": list(report.notices)[:20], "elapsed_s": round(time.perf_counter() - started, 1)}


def summarise(root: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in (root / "executions.jsonl").read_text(encoding="utf-8").splitlines() if line]
    stages: Counter[str] = Counter()
    for row in rows:
        for stage, value in row.get("stages", {}).items():
            values = value.values() if isinstance(value, dict) else [value]
            stages.update(f"{stage}:{v}" for v in values)
    summary = json.loads((root / "validation" / "summary.json").read_text(encoding="utf-8"))
    failed = {c["id"]: c["fail"] for c in summary.get("checks", ()) if c.get("fail")}
    register = Counter((r.get("code"), (r.get("detail") or "")[:40]) for r in
                       (json.loads(line) for line in (root / "register.jsonl").read_text(encoding="utf-8").splitlines() if line))
    return {"executions": len(rows), "status": dict(Counter(r.get("status") for r in rows)),
            "units": dict(Counter(r.get("unit") for r in rows)), "completeness": dict(Counter(r.get("completeness") for r in rows)),
            "stages": dict(sorted(stages.items())), "validation_checks": len(summary.get("checks", ())),
            "validation_failed": failed, "register": {f"{c} | {d}": n for (c, d), n in sorted(register.items(), key=str)}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("import")
    i.add_argument("--archive", required=True, type=Path)
    i.add_argument("--corpus", required=True, type=Path)
    i.add_argument("--jobs", type=int, default=8)
    i.add_argument("--out", type=Path)
    s = sub.add_parser("summary")
    s.add_argument("corpus", type=Path)
    args = parser.parse_args(argv)
    out = run_import(args.archive, args.corpus, args.jobs) if args.cmd == "import" else summarise(args.corpus)
    text = json.dumps(out, indent=1, sort_keys=True)
    if getattr(args, "out", None):
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
