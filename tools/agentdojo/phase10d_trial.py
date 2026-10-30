"""Phase-10d trial imports of the AgentDojo-format sources, offline, into scratch corpora only (D-100).

    uv run python tools/agentdojo/phase10d_trial.py seed    --profile ID --clone BARE --cache DIR
    uv run python tools/agentdojo/phase10d_trial.py census  --profile ID --cache DIR [--out REPORT.json]
    uv run python tools/agentdojo/phase10d_trial.py import  --profile ID --cache DIR --corpus DIR [--jobs N] [--sample N]
    uv run python tools/agentdojo/phase10d_trial.py compare CORPUS_A CORPUS_B

``seed`` builds a **scratch** bare fetch cache ``<cache>/git/<host>/<owner>/<repo>.git`` holding the pinned commit, its
trees and every blob of it the local clone has (the phase-10c staging clones are partial clones whose promisor remote is
GitHub). The objects are packed from the clone with ``git pack-objects`` under ``GIT_NO_LAZY_FETCH=1`` and
``GIT_ALLOW_PROTOCOL=file``, so a missing blob can never be fetched: it is simply absent. ``tools/seed_git_cache.py`` is
not used for these clones because its ``git fetch`` would let the clone's ``upload-pack`` fetch a missing blob lazily
from the network. Nothing is logged in the shared ``~/.agentprov/cache``.

The pin check reads the tree listing with the product code (``raw.fetch.Fetcher.git_tree`` on the scratch cache). Because
``git ls-tree -l`` prints ``BAD`` as the size of an absent blob, the listing is restricted to **covering pathspecs**: the
largest path prefixes of the pinned tree that hold no absent blob (the whole tree when nothing is absent). Every run log
of the phase-10c sources is present; the absent blobs are figures and documents, listed in the report.

``import`` runs :func:`agentprov.adapters.runner.importer.import_source` with the pinned tree read from that cache
(``GitPinTree``: each blob's SHA-1 recomputed against the tree entry; origin ``git``), in release mode, through the
validation stage. It bypasses the CLI status gate on purpose: the registry parts stay ``planned`` until a recorded full
import (D.3.2). ``--sample N`` keeps a stratified sample (every N-th selected log in label order, per pipeline directory).
``compare`` checks that two imports of the same tree (e.g. ``--jobs 1`` and ``--jobs 8``) hold byte-identical AER, SEM
and PROV objects and index rows; with ``--subset`` the second import is a stratified sample of the first's tree, and every
object it holds (AER, SEM, PROV, raw) must be in the first with the same bytes. ``census`` maps every selected blob as ``tools/agentdojo/profile_census.py`` does and
compares the profile's ``observed`` table. Reports hold counts, codes and paths only, never source text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

_GIT_ENV = {"GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1", "LC_ALL": "C"}
_HARDEN = ["-c", f"core.hooksPath={os.devnull}", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always",
           "-c", "core.symlinks=false"]


def _git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | _GIT_ENV
    done = subprocess.run(["git", *_HARDEN, "-C", str(repo), *args], input=data, capture_output=True, env=env, check=False)
    if done.returncode != 0:
        raise SystemExit(f"git {args[0]} failed in {repo.name}: {done.stderr.decode('utf-8', 'replace')[:300]}")
    return done.stdout


def _recipe(profile_id: str) -> tuple[Any, Any, dict[str, Any]]:
    from agentprov.adapters.profiles import load_profile
    from agentprov.raw.fetch import Recipe

    profile = load_profile(profile_id)
    source = profile.data["source"]
    pin = next(dict(p) for p in source["pins"] if p.get("primary") is True)
    return profile, Recipe.from_pin(pin, canonical_repo=source.get("canonical_repo")), pin


# ---------------------------------------------------------------------------------------------------------- seed
def seed(profile_id: str, clone: Path, cache: Path) -> dict[str, Any]:
    _profile, recipe, _pin = _recipe(profile_id)
    bare = recipe.cache_path(cache)
    commit = recipe.commit
    if _git(clone, "cat-file", "-t", commit).strip() != b"commit":
        raise SystemExit("the clone does not hold the pinned commit")
    listing = _git(clone, "ls-tree", "-r", "-t", "-z", "--full-tree", commit)
    objects = [commit]
    blobs: list[str] = []
    for entry in listing.split(b"\0"):
        if entry:
            mode, kind, oid = entry.split(b"\t", 1)[0].split()
            if kind == b"tree":
                objects.append(oid.decode())
            elif kind == b"blob":
                blobs.append(oid.decode())
    objects.append(_git(clone, "rev-parse", f"{commit}^{{tree}}").decode().strip())
    checked = _git(clone, "cat-file", "--batch-check", data="".join(b + "\n" for b in blobs).encode()).decode().splitlines()
    present = [b for b, line in zip(blobs, checked, strict=True) if not line.endswith(" missing")]
    absent = sorted(set(blobs) - set(present))
    wanted = list(dict.fromkeys([*objects, *present]))
    pack = _git(clone, "pack-objects", "--stdout", "--missing=allow-any", data="".join(o + "\n" for o in wanted).encode())
    bare.mkdir(parents=True, exist_ok=True)
    if not (bare / "objects").is_dir():
        _git(bare, "init", "-q", "--bare", "--template=", str(bare))
    _git(bare, "index-pack", "--stdin", data=pack)
    (bare / "shallow").write_text(commit + "\n", encoding="ascii")
    return {"commit": commit, "store": str(bare), "objects": len(wanted), "blobs": len(blobs), "absent_blobs": len(absent)}


def covering_paths(cache: Path, recipe: Any) -> tuple[list[str], list[str]]:
    """The largest pathspecs of the pinned tree without an absent blob, and the absent blob paths."""
    bare = recipe.cache_path(cache)
    listing = _git(bare, "ls-tree", "-r", "-z", "--full-tree", recipe.commit)
    paths: list[tuple[str, str]] = []
    for entry in listing.split(b"\0"):
        if entry:
            head, path = entry.split(b"\t", 1)
            if head.split()[1] == b"blob":
                paths.append((path.decode("utf-8"), head.split()[2].decode()))
    checked = _git(bare, "cat-file", "--batch-check", data="".join(o + "\n" for _p, o in paths).encode()).decode().splitlines()
    absent = sorted(p for (p, _o), line in zip(paths, checked, strict=True) if line.endswith(" missing"))
    if not absent:
        return [], []
    bad_dirs = {"/".join(p.split("/")[:i]) for p in absent for i in range(1, p.count("/") + 1)}
    out: set[str] = set()
    for path, _oid in paths:
        if path in absent:
            continue
        parts = path.split("/")
        for i in range(1, len(parts) + 1):
            prefix = "/".join(parts[:i])
            if i == len(parts) or prefix not in bad_dirs:
                out.add(prefix)
                break
    return sorted(out), absent


def _fetcher_recipe(profile_id: str, cache: Path) -> tuple[Any, Any, Any, dict[str, Any], list[str]]:
    from agentprov.raw.fetch import Fetcher, Recipe

    profile, recipe, pin = _recipe(profile_id)
    paths, absent = covering_paths(cache, recipe)
    if paths:
        recipe = Recipe.from_pin(pin, canonical_repo=profile.data["source"].get("canonical_repo"), paths=paths)
    return profile, Fetcher(cache), recipe, pin, absent


# ---------------------------------------------------------------------------------------------------------- census
def census(profile_id: str, cache: Path, workers: int) -> dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import profile_census as pc
    from multiprocessing import Pool

    from agentprov.adapters.agentdojo.census import add, compare, declared
    from agentprov.adapters.agentdojo.profile import family_table

    profile, fetcher, recipe, _pin, absent = _fetcher_recipe(profile_id, cache)
    part = profile.parts[0]
    include = tuple(profile.data.get("import", {}).get("include", ()))
    exclude = tuple(e["glob"] for e in profile.data.get("import", {}).get("exclude", ()))
    from agentprov.adapters.runner.importer import _match

    entries, _ = fetcher.git_tree(recipe)
    chosen = [e for e in entries if e.is_blob and any(_match(e.path, g) for g in include)
              and not any(_match(e.path, g) for g in exclude)]

    def blobs() -> Any:
        for blob in fetcher.iter_git_blobs(recipe, chosen):
            yield recipe.repo, recipe.commit, blob.entry.path, blob.entry.oid, blob.data

    started = time.perf_counter()
    totals: dict[str, dict[str, int]] = {}
    status: Counter[str] = Counter()
    variants: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    accounting: Counter[str] = Counter()
    units: Counter[str] = Counter()
    crashes: list[dict[str, Any]] = []
    samples: dict[str, list[str]] = {}
    with Pool(workers, initializer=pc._init, initargs=(profile_id, part)) as pool:
        for row in pool.imap(pc._work, blobs(), chunksize=16):
            status[row["status"]] += 1
            if row["status"] == "crash":
                crashes.append({"path": row["path"], "code": row.get("code")})
                continue
            if row["status"] in ("not_dialect", "not_selected"):
                continue
            variants[str(row["variant"])] += 1
            units[str(row["unit"])] += 1
            accounting[str(row["accounting"])] += 1
            issues.update(row["issues"])
            for code in row["issues"]:
                if len(samples.setdefault(code, [])) < 5:
                    samples[code].append(row["path"])
            add(totals, row["census"])
    table = family_table(profile)
    return {
        "profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256}, "part": part,
        "pin": {"commit": recipe.commit, "covering_paths": len(recipe.paths), "absent_blobs": absent},
        "files": sum(status.values()), "status": dict(sorted(status.items())), "variants": dict(sorted(variants.items())),
        "units": dict(sorted(units.items())), "accounting": dict(sorted(accounting.items())),
        "files_by_issue_code": dict(sorted(issues.items())), "crashes": crashes[:50],
        "issue_samples": {c: samples[c] for c in sorted(samples) if issues[c] < sum(status.values())},
        "measured": {q: dict(sorted(k.items())) for q, k in sorted(totals.items())},
        "declared": declared(table, part), "differences": compare(table, part, totals),
        "elapsed_s": round(time.perf_counter() - started, 1),
    }


# ---------------------------------------------------------------------------------------------------------- import
def _sample(tree: Any, profile: Any, every: int) -> Any:
    """Keep every ``every``-th selected log per pipeline directory (label order) in a ``GitPinTree``; context artefacts and
    every other entry stay, so selection, exclusion and the pin check run as for the whole tree."""
    from agentprov.adapters.runner.importer import _match

    include = tuple(profile.data.get("import", {}).get("include", ()))
    logs = sorted(p for p in tree.entries if any(_match(p, g) for g in include))
    by_dir: dict[str, list[str]] = {}
    for path in logs:
        by_dir.setdefault(path.rsplit("/", 4)[0], []).append(path)
    keep = {p for group in by_dir.values() for p in group[::every]}
    dropped = set(logs) - keep
    tree.entries = {p: e for p, e in tree.entries.items() if p not in dropped}
    return tree


def run_import(profile_id: str, cache: Path, corpus: Path, jobs: int, sample: int | None) -> dict[str, Any]:
    from agentprov.adapters.runner.importer import GitPinTree, import_source
    from agentprov.corpus.writer import CorpusWriter
    from agentprov.ingest.limits import IngestLimits

    profile, fetcher, recipe, pin, absent = _fetcher_recipe(profile_id, cache)
    if str(corpus).startswith(str(Path.home() / ".agentprov" / "corpora")):
        raise SystemExit("trial imports never write into ~/.agentprov/corpora")
    tree: Any = GitPinTree(fetcher, recipe)
    if sample:
        tree = _sample(tree, profile, sample)
    limits = IngestLimits()
    part = profile.parts[0]
    started = time.perf_counter()
    with CorpusWriter(corpus, limits=limits, release=True, command="import") as writer:
        report = import_source(profile.source_id, tree, corpus=writer, profile_id=profile.id, mode="release", part=part,
                               snapshot_id=part, corpus_id=profile.source_id, until="validation", workers=jobs,
                               limits=limits, pin=pin)
    return {"profile": {"id": profile.id, "version": profile.version, "sha256": profile.sha256},
            "pin": {"commit": recipe.commit, "covering_paths": len(recipe.paths), "absent_blobs": absent},
            "jobs": jobs, "sample_every": sample, "exit_code": report.exit_code, "counters": dict(report.counters),
            "issues_by_code": dict(sorted(report.issues_by_code.items())),
            "failures": [{"stage": f["stage"], "code": f["code"], "path": f["subject"].get("path")} for f in report.failures[:50]],
            "notices": list(report.notices)[:20], "elapsed_s": round(time.perf_counter() - started, 1)}


# ---------------------------------------------------------------------------------------------------------- compare
def _digests(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and not rel.startswith(("logs/", "lock")) and not rel.endswith((".lock", "derivation.json")):
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


#: The per-execution object trees of a corpus: content-addressed, so a sample's objects must be in the full corpus.
_OBJECT_TREES = ("aer/", "sem/", "prov/", "raw/objects/")


def compare_corpora(a: Path, b: Path, *, subset: bool = False) -> dict[str, Any]:
    """Byte comparison of two trial corpora. ``subset``: B is a stratified sample of A's tree; every object file of B
    (AER, SEM, PROV, raw objects) must exist in A with the same bytes (the index files necessarily differ)."""
    da, db = _digests(a), _digests(b)
    if subset:
        objects = {k: v for k, v in db.items() if k.startswith(_OBJECT_TREES)}
        missing = sorted(k for k in objects if k not in da)
        differ = sorted(k for k in objects if k in da and da[k] != objects[k])
        return {"mode": "subset", "objects_b": len(objects), "missing_in_a": missing[:20], "n_missing": len(missing),
                "differ": differ[:50], "n_differ": len(differ), "only_a": [], "only_b": missing[:20]}
    differ = sorted(k for k in set(da) & set(db) if da[k] != db[k])
    return {"files_a": len(da), "files_b": len(db), "only_a": sorted(set(da) - set(db))[:20],
            "only_b": sorted(set(db) - set(da))[:20], "differ": differ[:50], "n_differ": len(differ)}


def summarise(root: Path) -> dict[str, Any]:
    """Counts of a trial corpus: index statuses and stages, validation checks that failed, register codes."""
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
            "units": dict(Counter(r.get("unit") for r in rows)), "completeness": dict(Counter(r.get("completeness") for r in rows)),
            "stages": dict(sorted(stages.items())), "validation_checks": len(summary.get("checks", ())),
            "validation_failed": failed, "register_codes": dict(sorted(register.items()))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--profile", required=True)
    s.add_argument("--clone", required=True, type=Path)
    s.add_argument("--cache", required=True, type=Path)
    c = sub.add_parser("census")
    c.add_argument("--profile", required=True)
    c.add_argument("--cache", required=True, type=Path)
    c.add_argument("--workers", type=int, default=8)
    c.add_argument("--out", type=Path)
    i = sub.add_parser("import")
    i.add_argument("--profile", required=True)
    i.add_argument("--cache", required=True, type=Path)
    i.add_argument("--corpus", required=True, type=Path)
    i.add_argument("--jobs", type=int, default=8)
    i.add_argument("--sample", type=int)
    i.add_argument("--out", type=Path)
    m = sub.add_parser("summary")
    m.add_argument("corpus", type=Path)
    k = sub.add_parser("compare")
    k.add_argument("a", type=Path)
    k.add_argument("b", type=Path)
    k.add_argument("--subset", action="store_true", help="B is a stratified sample of A: compare B's objects against A")
    args = parser.parse_args(argv)
    if args.cmd == "seed":
        result = seed(args.profile, args.clone, args.cache)
    elif args.cmd == "census":
        result = census(args.profile, args.cache, args.workers)
    elif args.cmd == "import":
        result = run_import(args.profile, args.cache, args.corpus, args.jobs, args.sample)
    elif args.cmd == "summary":
        result = summarise(args.corpus)
    else:
        result = compare_corpora(args.a, args.b, subset=args.subset)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if getattr(args, "out", None):
        args.out.write_text(text, encoding="utf-8")
    print(text if args.cmd != "census" else json.dumps({k: result[k] for k in ("files", "status", "variants",
                                                                               "files_by_issue_code", "crashes", "differences")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
