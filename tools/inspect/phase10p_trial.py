"""Phase-10p trial imports of the control-arena archive, offline, into scratch corpora only (D-341, D-347).

    uv run python tools/inspect/phase10p_trial.py import  --corpus DIR --input DIR [--part P ...] [--jobs N]
    uv run python tools/inspect/phase10p_trial.py compare CORPUS_A CORPUS_B
    uv run python tools/inspect/phase10p_trial.py summary CORPUS

``import`` imports the profile's parts (default: all five, in profile order) as snapshots of one corpus (D-202), each
through the product's archive-input path: the staged copy under ``--input`` (the pinned tree's layout) is checked against
its pin offline (``verify_parts`` for a split zip, D-249; ``verify_download`` for a tar.zst, D-201), then
:func:`agentprov.adapters.runner.importer.import_source` runs in release mode through the validation stage. It bypasses
the CLI status gate on purpose: the registry parts stay ``planned`` until a recorded full import (D.3.2), as
``tools/inspect/phase10h_trial.py`` does. It refuses to write under ``~/.agentprov/corpora``.

D-345's 36 account-path logs are held back by the profile itself (exact-path excludes, ``select.redaction_pending``,
D-324; profile version 2). Reports hold counts, codes and labels only, never source text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

PROFILE_ID = "controlarena-persistent"


def _thaw(value: Any) -> Any:
    """A frozen profile table back to plain dicts and lists."""
    from collections.abc import Mapping

    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(v) for v in value]
    return value


def _tree(pin: dict[str, Any], root: Path, limits: Any) -> Any:
    from agentprov.adapters.runner.importer import ArchiveTree
    from agentprov.ingest.paths import open_evidence
    from agentprov.raw.fetch import Recipe, is_split_pin, part_recipes, verify_download, verify_parts

    if is_split_pin(pin):
        recipes = part_recipes(pin)
        directory = root / Path(str(pin["file"])).parent
        checked = verify_parts(lambda name: open_evidence(str(directory), name, limits), recipes)
        parts = [(directory / str(r.file).rsplit("/", 1)[-1], sha, size) for r, (sha, size) in zip(recipes, checked, strict=True)]
        return ArchiveTree.split(parts, pin=pin, limits=limits)
    path = root / str(pin["file"])
    recipe = Recipe.from_pin(pin)
    with open_evidence(str(path.parent), path.name, limits) as handle:
        sha256, _md5, size = verify_download(handle, path.name, recipe)
    return ArchiveTree(path, pin=pin, sha256=sha256, size=size, limits=limits)


def run_import(corpus: Path, root: Path, parts: list[str], jobs: int) -> dict[str, Any]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner import importer
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.ingest.limits import IngestLimits

    if str(corpus.resolve()).startswith(str((Path.home() / ".agentprov" / "corpora").resolve())):
        raise SystemExit("trial imports never write into ~/.agentprov/corpora")
    profile = load_profile(PROFILE_ID)
    pins = {str(p["part"]): p for p in profile.data["source"]["pins"]}
    limits = IngestLimits()
    out: dict[str, Any] = {"profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256}, "parts": {}}
    for part in parts or list(profile.parts):
        pin = _thaw(pins[part])
        started = time.perf_counter()
        tree = _tree(pin, root, limits)
        with CorpusWriter(corpus, limits=limits, release=True, command="import") as writer:
            report = importer.import_source(profile.source_id, tree, corpus=writer, profile_id=profile.id, mode="release",
                                            part=part, snapshot_id=part, corpus_id=profile.source_id,
                                            until="validation", workers=jobs, limits=limits, pin=pin)
        out["parts"][part] = {
            "exit_code": report.exit_code, "counters": dict(report.counters),
            "issues_by_code": dict(sorted(report.issues_by_code.items())),
            "failures": [{"stage": f["stage"], "code": f["code"], "path": f["subject"].get("path")} for f in report.failures[:400]],
            "n_failures": len(report.failures), "notices": list(report.notices)[:20],
            "elapsed_s": round(time.perf_counter() - started, 1)}
    return out


#: The per-execution object trees of a corpus: content-addressed, so identical imports have identical trees.
_OBJECT_TREES = ("aer/", "sem/", "prov/", "raw/objects/")


def _digests(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and rel.startswith(_OBJECT_TREES):
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def compare_corpora(a: Path, b: Path) -> dict[str, Any]:
    da, db = _digests(a), _digests(b)
    differ = sorted(k for k in set(da) & set(db) if da[k] != db[k])
    return {"objects_a": len(da), "objects_b": len(db), "only_a": sorted(set(da) - set(db))[:20],
            "only_b": sorted(set(db) - set(da))[:20], "n_differ": len(differ), "differ": differ[:50]}


def summarise(root: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in (root / "executions.jsonl").read_text(encoding="utf-8").splitlines() if line]
    stages: Counter[str] = Counter()
    for row in rows:
        for stage, value in row.get("stages", {}).items():
            values = value.values() if isinstance(value, dict) else [value]
            stages.update(f"{stage}:{v}" for v in values)
    summary = json.loads((root / "validation" / "summary.json").read_text(encoding="utf-8"))
    failed = {c["id"]: c["fail"] for c in summary.get("checks", ()) if c.get("fail")}
    register = [json.loads(line) for line in (root / "register.jsonl").read_text(encoding="utf-8").splitlines() if line]
    members = [json.loads(line) for line in (root / "raw" / "members.jsonl").read_text(encoding="utf-8").splitlines() if line] \
        if (root / "raw" / "members.jsonl").exists() else []
    return {"executions": len(rows), "status": dict(Counter(r.get("status") for r in rows)),
            "completeness": dict(Counter(r.get("completeness") for r in rows)),
            "snapshots": dict(Counter(s for r in rows for s in r.get("snapshot_ids", ()))),
            "stages": dict(sorted(stages.items())), "validation_checks": len(summary.get("checks", ())),
            "validation_failed": failed, "register_codes": dict(Counter(e.get("code") for e in register)),
            "member_dispositions": dict(Counter(m.get("disposition") for m in members))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("import")
    i.add_argument("--corpus", required=True, type=Path)
    i.add_argument("--input", required=True, type=Path, help="the staged copy of the pinned tree")
    i.add_argument("--part", action="append", default=[])
    i.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    s = sub.add_parser("summary")
    s.add_argument("corpus", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "import":
        out = run_import(args.corpus, args.input, args.part, args.jobs)
    elif args.cmd == "compare":
        out = compare_corpora(args.a, args.b)
    else:
        out = summarise(args.corpus)
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
