"""Phase-10h trial imports of the two AgentHarm Inspect log sets, offline, into scratch corpora only (D-180, D-185).

    uv run python tools/inspect/phase10h_trial.py import  --profile ID --corpus DIR [--cache DIR] [--jobs N] [--every N]
                                                           [--skip-local-path-models]
    uv run python tools/inspect/phase10h_trial.py compare CORPUS_A CORPUS_B [--subset]
    uv run python tools/inspect/phase10h_trial.py summary CORPUS

``import`` runs :func:`agentprov.adapters.runner.importer.import_source` on the profile's git pin read from the verified
fetch cache (``GitPinTree``: every blob's SHA-1 recomputed against its tree entry; origin ``git``), in release mode,
through the validation stage. It bypasses the CLI status gate on purpose: the registry parts stay ``planned`` until a
recorded full import (D.3.2), as ``tools/agentdojo/phase10d_trial.py`` does. It refuses to write under
``~/.agentprov/corpora``.

``--skip-local-path-models`` drops every selected log whose header ``eval.model`` names a local filesystem path (an
absolute path, possibly after a ``provider/`` or ``provider/model:`` prefix): those ids carry workstation account names
and wait for the redaction proposal D-182. The decision reads each header through :mod:`agentprov.ingest` and is reported
as a count; the ids are never printed. ``--every N`` keeps every N-th selected log in label order (a second, smaller
import for the determinism comparison). ``compare`` checks byte identity of the object trees of two imports (``--subset``:
B's objects must all be in A). Reports hold counts, codes and labels only, never source text.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

#: A model id that names a local path: ``/...``, ``provider//...`` or ``provider/org/model:/...``.
_LOCAL_PATH_MODEL = re.compile(r"(^|/|:)/(workspace|Users|home|mnt|scratch|data|root|tmp)/")


def _local_path_model(blob: bytes) -> bool | None:
    """True when the log's header names a local-path model; None when the log has no readable header."""
    from agentprov.ingest.archives import iter_zip_members, open_zip
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    limits = IngestLimits()
    with open_zip(io.BytesIO(blob), limits, release=True) as archive:
        for member in iter_zip_members(archive, lambda label: label == "header.json"):
            if member.disposition == "selected":
                header = strict_json_loads(archive.read_member(member), limits)
                model = header.get("eval", {}).get("model") if isinstance(header, dict) else None
                return isinstance(model, str) and _LOCAL_PATH_MODEL.search(model) is not None
    return None


def _tree(profile: Any, cache: Path | None) -> tuple[Any, Any, dict[str, Any]]:
    from agentprov.adapters.runner.importer import GitPinTree
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    pin = next(dict(p) for p in profile.data["source"]["pins"] if p.get("primary") is True)
    recipe = Recipe.from_pin(pin, canonical_repo=profile.data["source"].get("canonical_repo"))
    fetcher = Fetcher(resolve_cache_dir(str(cache) if cache else None))
    if not fetcher.plan(recipe).cached:
        raise SystemExit("the pinned commit is not in the fetch cache; run 'agentprov fetch' first (with the user's consent)")
    return GitPinTree(fetcher, recipe), fetcher, pin


def _selected(tree: Any, profile: Any) -> list[str]:
    from agentprov.adapters.runner.importer import _match

    imp = profile.data.get("import", {})
    include = tuple(imp.get("include", ()))
    exclude = tuple(e["glob"] for e in imp.get("exclude", ()))
    return sorted(p for p in tree.entries if any(_match(p, g) for g in include) and not any(_match(p, g) for g in exclude))


def run_import(profile_id: str, corpus: Path, cache: Path | None, jobs: int, every: int | None, skip_local: bool) -> dict[str, Any]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import import_source
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.ingest.limits import IngestLimits

    if str(corpus.resolve()).startswith(str((Path.home() / ".agentprov" / "corpora").resolve())):
        raise SystemExit("trial imports never write into ~/.agentprov/corpora")
    profile = load_profile(profile_id)
    tree, fetcher, pin = _tree(profile, cache)
    logs = _selected(tree, profile)
    dropped: set[str] = set()
    headerless = 0
    if skip_local:
        entries = {p: tree.entries[p] for p in logs}
        for path, blob in zip(logs, fetcher.iter_git_blobs(tree.recipe, [entries[p] for p in logs]), strict=True):
            flag = _local_path_model(blob.data)
            headerless += flag is None
            if flag:
                dropped.add(path)
    if every:
        kept = [p for p in logs if p not in dropped]
        dropped |= set(kept) - set(kept[::every])
    tree.entries = {p: e for p, e in tree.entries.items() if p not in dropped}
    limits = IngestLimits()
    part = profile.parts[0]
    started = time.perf_counter()
    with CorpusWriter(corpus, limits=limits, release=True, command="import") as writer:
        report = import_source(profile.source_id, tree, corpus=writer, profile_id=profile.id, mode="release", part=part,
                               snapshot_id=part, corpus_id=profile.source_id, until="validation", workers=jobs,
                               limits=limits, pin=pin)
    return {"profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256},
            "pin": {"commit": pin["commit"]}, "selected_logs": len(logs), "dropped_local_path_model_logs":
            len(dropped) if skip_local and not every else None, "headerless_logs_seen": headerless if skip_local else None,
            "every": every, "imported_logs": len(logs) - len(dropped), "jobs": jobs, "exit_code": report.exit_code,
            "counters": dict(report.counters), "issues_by_code": dict(sorted(report.issues_by_code.items())),
            "failures": [{"stage": f["stage"], "code": f["code"], "path": f["subject"].get("path")} for f in report.failures[:50]],
            "notices": list(report.notices)[:20], "elapsed_s": round(time.perf_counter() - started, 1)}


#: The per-execution object trees of a corpus: content-addressed, so a sample's objects must be in the full corpus.
_OBJECT_TREES = ("aer/", "sem/", "prov/", "raw/objects/")


def _digests(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and not rel.startswith(("logs/", "lock")) and not rel.endswith((".lock", "derivation.json")):
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def compare_corpora(a: Path, b: Path, *, subset: bool) -> dict[str, Any]:
    da, db = _digests(a), _digests(b)
    if subset:
        objects = {k: v for k, v in db.items() if k.startswith(_OBJECT_TREES)}
        missing = sorted(k for k in objects if k not in da)
        differ = sorted(k for k in objects if k in da and da[k] != objects[k])
        return {"mode": "subset", "objects_b": len(objects), "n_missing": len(missing), "missing": missing[:20],
                "n_differ": len(differ), "differ": differ[:20]}
    differ = sorted(k for k in set(da) & set(db) if da[k] != db[k])
    return {"files_a": len(da), "files_b": len(db), "only_a": sorted(set(da) - set(db))[:20],
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
    register = Counter(json.loads(line).get("code") for line in (root / "register.jsonl").read_text(encoding="utf-8").splitlines() if line)
    return {"executions": len(rows), "status": dict(Counter(r.get("status") for r in rows)),
            "completeness": dict(Counter(r.get("completeness") for r in rows)), "stages": dict(sorted(stages.items())),
            "validation_checks": len(summary.get("checks", ())), "validation_failed": failed,
            "register_codes": dict(sorted(register.items()))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("import")
    i.add_argument("--profile", required=True)
    i.add_argument("--corpus", required=True, type=Path)
    i.add_argument("--cache", type=Path)
    i.add_argument("--jobs", type=int, default=8)
    i.add_argument("--every", type=int)
    i.add_argument("--skip-local-path-models", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    c.add_argument("--subset", action="store_true")
    s = sub.add_parser("summary")
    s.add_argument("corpus", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "import":
        out = run_import(args.profile, args.corpus, args.cache, args.jobs, args.every, args.skip_local_path_models)
    elif args.cmd == "compare":
        out = compare_corpora(args.a, args.b, subset=args.subset)
    else:
        out = summarise(args.corpus)
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
