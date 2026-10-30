"""Phase-10j trial imports into scratch corpora only, offline (part C; D-100's method, D-200 archive inputs, D-202).

    uv run python tools/agentdojo/phase10j_trial.py seed    --profile ID --cache DIR
    uv run python tools/agentdojo/phase10j_trial.py import  --profile ID --cache DIR --corpus DIR [--jobs N]
    uv run python tools/agentdojo/phase10j_trial.py compare CORPUS_A CORPUS_B
    uv run python tools/agentdojo/phase10j_trial.py summary CORPUS

* ``seed`` packs each git pin of the profile (its commit, trees and the blobs the phase-10c staging clone holds) into a
  **scratch** bare fetch cache, as ``phase10d_trial.py seed`` does (``GIT_NO_LAZY_FETCH=1``, file protocol only: an absent
  blob is never fetched).
* ``import`` runs :func:`agentprov.adapters.runner.importer.import_source` in release mode through validation, one call per
  part in the profile's part order, all into the same scratch corpus (several snapshots per corpus, D-202). A git part
  reads its pinned tree from the scratch cache (``GitPinTree``); a zenodo part is an archive input (``ArchiveTree``) built
  from the staged file after :func:`agentprov.raw.fetch.verify_download` checked it against the pin, exactly as
  ``agentprov import --input FILE --verify-against-pin`` does. The CLI status gate is bypassed on purpose: the registry
  parts stay ``planned`` until a recorded full import (D.3.2). Nothing is written under ``~/.agentprov/corpora``.
* ``compare`` and ``summary`` are ``phase10d_trial.py``'s (byte comparison of two trial corpora; index, validation and
  register counts).

Reports hold counts, codes and paths only, never source text.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase10d_trial as d10  # noqa: E402
from phase10j_profiles import ARCHIVES, BARES, STAGING  # noqa: E402


def _pins(profile: Any) -> list[tuple[str, dict[str, Any]]]:
    """``(part, pin)`` in the profile's part order; a part without a pin of its own reads the primary pin."""
    pins = [dict(p) for p in profile.data["source"]["pins"]]
    primary = next(p for p in pins if p.get("primary") is True)
    return [(part, next((p for p in pins if p.get("part") == part), primary)) for part in profile.parts]


def seed(profile_id: str, cache: Path) -> list[dict[str, Any]]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.raw.fetch import Recipe

    profile = load_profile(profile_id)
    repo = profile.data["source"].get("canonical_repo")
    out = []
    for part, pin in _pins(profile):
        if pin["kind"] != "git":
            continue
        recipe = Recipe.from_pin(pin, canonical_repo=repo)
        clone = STAGING / BARES[str(repo)]
        d10._recipe = lambda _pid, r=recipe, p=pin: (profile, r, p)  # one pin at a time
        out.append({"part": part, **d10.seed(profile_id, clone, cache)})
    return out


def _tree(profile: Any, part: str, pin: dict[str, Any], cache: Path) -> tuple[Any, dict[str, Any]]:
    from agentprov.adapters.runner.importer import ArchiveTree, GitPinTree
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.paths import open_evidence
    from agentprov.raw.fetch import Fetcher, Recipe, verify_download

    repo = profile.data["source"].get("canonical_repo")
    recipe = Recipe.from_pin(pin, canonical_repo=repo)
    if pin["kind"] == "git":
        d10._recipe = lambda _pid, r=recipe, p=pin: (profile, r, p)
        paths, absent = d10.covering_paths(cache, recipe)
        if paths:
            recipe = Recipe.from_pin(pin, canonical_repo=repo, paths=paths)
        return GitPinTree(Fetcher(cache), recipe), {"commit": recipe.commit, "absent_blobs": len(absent)}
    path = STAGING / ARCHIVES[pin["sha256"]]
    limits = IngestLimits()
    with open_evidence(str(path.parent), path.name, limits) as handle:
        sha256, _md5, size = verify_download(handle, path.name, recipe)
    return ArchiveTree(path, pin=pin, sha256=sha256, size=size, limits=limits), {"file": pin.get("file"), "sha256": sha256}


def run_import(profile_id: str, cache: Path, corpus: Path, jobs: int, limit: int | None = None) -> dict[str, Any]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import import_source
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.ingest.limits import IngestLimits

    if str(corpus.resolve()).startswith(str((Path.home() / ".agentprov" / "corpora").resolve())):
        raise SystemExit("trial imports never write into ~/.agentprov/corpora")
    profile = load_profile(profile_id)
    limits = IngestLimits()
    out: dict[str, Any] = {"profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256},
                           "jobs": jobs, "snapshots": []}
    for part, pin in _pins(profile):  # several parts over one pin (variant_labels): one import of it per part
        tree, pin_info = _tree(profile, part, pin, cache)
        started = time.perf_counter()
        with CorpusWriter(corpus, limits=limits, release=True, command="import") as writer:
            report = import_source(profile.source_id, tree, corpus=writer, profile_id=profile.id, mode="release",
                                   part=part, snapshot_id=part, corpus_id=profile.source_id, until="validation",
                                   workers=jobs, limits=limits, pin=pin, limit=limit)
        out["snapshots"].append({
            "part": part, "pin": pin_info, "exit_code": report.exit_code, "counters": dict(report.counters),
            "issues_by_code": dict(sorted(report.issues_by_code.items())),
            "failures": [{"stage": f["stage"], "code": f["code"], "path": f["subject"].get("path")}
                         for f in report.failures[:50]],
            "notices": list(report.notices)[:20], "elapsed_s": round(time.perf_counter() - started, 1)})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--profile", required=True)
    s.add_argument("--cache", required=True, type=Path)
    i = sub.add_parser("import")
    i.add_argument("--profile", required=True)
    i.add_argument("--cache", required=True, type=Path)
    i.add_argument("--corpus", required=True, type=Path)
    i.add_argument("--jobs", type=int, default=4)
    i.add_argument("--out", type=Path)
    i.add_argument("--limit", type=int, help="a smoke test: import only the first N candidates of each snapshot")
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    m = sub.add_parser("summary")
    m.add_argument("corpus", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "seed":
        result: Any = seed(args.profile, args.cache)
    elif args.cmd == "import":
        result = run_import(args.profile, args.cache, args.corpus, args.jobs, args.limit)
        if args.out:
            args.out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    elif args.cmd == "compare":
        result = d10.compare_corpora(args.a, args.b)
    else:
        result = d10.summarise(args.corpus)
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
