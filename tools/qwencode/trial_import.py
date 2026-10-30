"""TRIAL ONLY (never product code): scratch import of the Qwen Code runs of Zenodo 23168099 (phase 10o part C; D-570).

    uv run python tools/suite_queue.py --class import --cpu 4 -- python tools/qwencode/trial_import.py import \
        --runs RUNS.zip --supp SUPP.zip --corpus DIR [--jobs 4] [--out REPORT.json]
    uv run python tools/qwencode/trial_import.py summary CORPUS_DIR

``import`` checks both local files against the profile's pins (size and sha256), builds the primary archive input
(:class:`agentprov.adapters.runner.importer.ArchiveTree`, D-200) and, for the supplementary zip, a **trial-only member
tree** (:class:`SuppMemberTree`) handed to the importer as the ``supp`` context tree. The CLI does not wire a profile's
context pins and a context tree cannot be an archive yet (D-530, routed to phase-10i-context): this driver stands in for
that path for trial and census purposes only (orchestrator's ruling, 2026-10-15). It runs
:func:`agentprov.adapters.runner.importer.import_source` in release mode through validation, bypassing the CLI status gate
on purpose (the registry part stays ``planned``). A corpus under ``~/.agentprov/corpora`` is refused. ``summary`` counts a
trial corpus. Reports hold counts and codes only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zlib
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, Final

PROFILE = "redcode-exec-qwencode"
SUPP_PREFIXES = ("results/Qwen/", "dataset/RedCode-Exec/", "prompt_generator/output/", "OH_evaluation/execution_rules.md")


class SuppMemberTree:
    """TRIAL ONLY: the supplementary zip's selected members as a source tree, read through :mod:`agentprov.ingest`
    (extraction-free) and held in memory; each candidate carries its pinned ``member`` origin."""

    kind: Final = "member"
    explicit: Final = False

    def __init__(self, path: Path, sha256: str) -> None:
        from agentprov.adapters.types import CandidateArtefact, Origin
        from agentprov.ingest.archives import iter_zip_members, open_archive
        from agentprov.ingest.limits import IngestLimits

        limits = IngestLimits()
        self.rejections: list[Any] = []
        self._data: dict[str, bytes] = {}
        self._cands: list[Any] = []
        with path.open("rb") as fp, open_archive(fp, limits, release=False) as z:
            for m in iter_zip_members(z, lambda label: label.startswith(SUPP_PREFIXES) and "/OH/" not in label, limits):
                if m.disposition != "selected" or m.label is None:
                    continue
                data = z.read_member(m)
                self._data[m.label] = data
                self._cands.append(CandidateArtefact(m.label, len(data),
                                                     Origin.member(sha256, m.label, int(m.method), zlib.crc32(data), len(data))))

    def walk(self) -> Iterator[Any]:
        yield from sorted(self._cands, key=lambda c: c.label)

    def read(self, batch: Sequence[Any]) -> Iterator[tuple[Any, bytes]]:
        for candidate in batch:
            yield candidate, self._data[candidate.label]


def _verify(path: Path, pin: dict[str, Any]) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    if (digest.hexdigest(), path.stat().st_size) != (pin["sha256"], pin["size"]):
        raise SystemExit(f"{path.name} does not match the profile's {pin['role']} pin")


def run_import(runs: Path, supp: Path, corpus: Path, jobs: int) -> dict[str, Any]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import ArchiveTree, ContextTree, import_source
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.ingest.limits import IngestLimits

    if str(corpus.resolve()).startswith(str((Path.home() / ".agentprov" / "corpora").resolve())):
        raise SystemExit("trial imports never write into ~/.agentprov/corpora")
    profile = load_profile(PROFILE)
    pins = {p["role"]: dict(p) for p in profile.data["source"]["pins"]}
    _verify(runs, pins["runs"])
    _verify(supp, pins["supp"])
    limits = IngestLimits()
    tree = ArchiveTree(runs, pin=pins["runs"], sha256=pins["runs"]["sha256"], size=pins["runs"]["size"], limits=limits)
    context = [ContextTree("supp", SuppMemberTree(supp, pins["supp"]["sha256"]))]
    part = profile.parts[0]
    started = time.perf_counter()
    with CorpusWriter(corpus, limits=limits, release=True, command="import") as writer:
        report = import_source(profile.source_id, tree, corpus=writer, profile_id=profile.id, mode="release", part=part,
                               snapshot_id=part, corpus_id="redcode-exec-qwencode", until="validation", workers=jobs,
                               limits=limits, pin=pins["runs"], context_trees=context)
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
            "completeness": dict(Counter(r.get("completeness") for r in rows)), "stages": dict(sorted(stages.items())),
            "validation_checks": len(summary.get("checks", ())), "validation_failed": failed,
            "register": {f"{c} | {d}": n for (c, d), n in sorted(register.items(), key=str)}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("import")
    i.add_argument("--runs", required=True, type=Path)
    i.add_argument("--supp", required=True, type=Path)
    i.add_argument("--corpus", required=True, type=Path)
    i.add_argument("--jobs", type=int, default=4)
    i.add_argument("--out", type=Path)
    s = sub.add_parser("summary")
    s.add_argument("corpus", type=Path)
    args = parser.parse_args(argv)
    out = run_import(args.runs, args.supp, args.corpus, args.jobs) if args.cmd == "import" else summarise(args.corpus)
    text = json.dumps(out, indent=1, sort_keys=True)
    if getattr(args, "out", None):
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
