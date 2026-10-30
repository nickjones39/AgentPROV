"""Generate the shipped estimate priors ``src/agentprov/estimate/data/estimate_priors.json`` (D-653, D-701).

Run through the machine-wide job queue (it reads every AER file of the stored corpora):

    python tools/suite_queue.py --class import --cpu 2 -- \\
        .venv/bin/python tools/estimate/gen_estimate_priors.py --workers 2 \\
        --corpus NAME --corpus-commit NAME=COMMIT ...

**Which corpora.** ``--corpus NAME`` (repeatable) names each directory of ``$AGENTPROV_HOME/corpora`` exactly; a name
that is not there, or two copies of one corpus (``x-rg1.partial`` and ``x-p10.partial``: one execution would count
twice), is refused. Without ``--corpus``, one copy per corpus is chosen and printed: the newest regenerated one
(``<name>-rg<N>.partial``, highest ``N``), else the newest ``<name>-p<N>.partial``, else ``<name>.partial``; never a
``.pre-`` copy. A regenerated copy is preferred because it is the one that is sealed (orchestrator 2026-10-23).

**Building commits.** Every chosen corpus needs ``--corpus-commit NAME=COMMIT``: the commit of the checkout that built
it, recorded in the table as its ``building_commit``. The corpora do not record it (their manifests hold code digests),
so it comes from the round's records and is never inferred here.

For every execution of the chosen corpora, ``agentprov.estimate.usage.execution_usage`` counts the model calls, the tokens per call (recorded
usage, else message characters / 4) and the run's duration; ``aggregate`` turns them into quantiles per benchmark,
suite, attack (or benign) and model family, plus the same keys over any model.

**The table holds counts and quantiles only** (no text, no ids of executions); it names each corpus (its id, its
manifest's sha256 and how many executions were read) and the commit of the checkout that built it. Corpus text is
untrusted data and never leaves the reading process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from agentprov.errors import IngestError
from agentprov.estimate.priors import PRIORS as OUT
from agentprov.estimate.priors import PRIORS_FORMAT as FORMAT
from agentprov.estimate.usage import CHARS_PER_TOKEN, ExecutionUsage, aggregate, execution_usage
from agentprov.ingest.loaders import strict_json_loads

HERE = Path(__file__).resolve().parent


def _corpus_identity(root: Path) -> dict[str, Any]:
    manifest = root / "corpus.json"
    try:
        data = manifest.read_bytes()
    except OSError:
        return {"name": root.name, "corpus_id": None, "manifest_sha256": None}
    try:
        doc = strict_json_loads(data)
    except IngestError:
        doc = {}
    corpus_id = doc.get("corpus_id") if isinstance(doc, dict) and isinstance(doc.get("corpus_id"), str) else None
    return {"name": root.name, "corpus_id": corpus_id, "manifest_sha256": hashlib.sha256(data).hexdigest()}


def _commit(checkout: Path) -> str:
    try:
        head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True,  # noqa: S603, S607 - fixed argv
                              check=True, timeout=30).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"],  # noqa: S603, S607 - fixed argv
                               capture_output=True, text=True, check=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return head + (" (modified)" if dirty else "")


_VERSION = re.compile(r"(?P<base>.+?)(?:-(?P<kind>rg|p)(?P<n>\d+))?(?:\.partial)?")
_COMMIT = re.compile(r"[0-9a-f]{7,40}")


class Refused(Exception):
    """A selection or argument the tool will not build from (exit 2)."""


def corpus_base(name: str) -> tuple[str, tuple[int, int]]:
    """A corpus directory's base name and its rank: a regenerated copy (``-rg<N>``) above every ``-p<N>`` copy, which
    is above an unversioned name; the higher ``N`` first within each."""
    m = _VERSION.fullmatch(name)
    if m is None:
        return name, (0, 0)
    return m.group("base"), ({"rg": 2, "p": 1}.get(m.group("kind") or "", 0), int(m.group("n") or 0))


def newest_versions(roots: Iterable[Path]) -> list[Path]:
    """One directory per corpus: the newest regenerated copy, else the newest ``-p<N>``, else the unversioned one."""
    best: dict[str, tuple[tuple[int, int], Path]] = {}
    for root in roots:
        base, rank = corpus_base(root.name)
        if base not in best or rank > best[base][0]:
            best[base] = (rank, root)
    return sorted(path for _, path in best.values())


def choose(corpora_root: Path, names: list[str]) -> list[Path]:
    """The corpora to read: the named ones exactly (refused: a missing name, two copies of one corpus), else the
    newest copy of each corpus under ``corpora_root``."""
    present = {p.name: p for p in corpora_root.iterdir() if p.is_dir() and ".pre-" not in p.name}
    if not names:
        return newest_versions(present.values())
    missing = sorted(n for n in names if n not in present)
    if missing:
        raise Refused("not a corpus directory here (or a .pre- copy): " + ", ".join(missing))
    by_base: dict[str, list[str]] = {}
    for n in dict.fromkeys(names):
        by_base.setdefault(corpus_base(n)[0], []).append(n)
    doubled = sorted(" and ".join(v) for v in by_base.values() if len(v) > 1)
    if doubled:
        raise Refused("two copies of one corpus would count its executions twice: " + "; ".join(doubled))
    return sorted(present[n] for n in dict.fromkeys(names))


def building_commits(pairs: list[str], chosen: list[Path]) -> dict[str, str]:
    """``NAME=COMMIT`` for every chosen corpus (refused: a malformed pair or commit, a name not chosen, a chosen corpus
    without one)."""
    out: dict[str, str] = {}
    for pair in pairs:
        name, sep, commit = pair.partition("=")
        if not sep or not _COMMIT.fullmatch(commit):
            raise Refused(f"--corpus-commit takes NAME=COMMIT (a hex commit): {pair[:120]!r}")
        out[name] = commit
    names = {p.name for p in chosen}
    unknown = sorted(set(out) - names)
    if unknown:
        raise Refused("--corpus-commit for a corpus not chosen: " + ", ".join(unknown))
    without = sorted(names - set(out))
    if without:
        raise Refused("no --corpus-commit for: " + ", ".join(without))
    return out


def _one(path: str) -> ExecutionUsage | None:
    return execution_usage(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the GUI estimate priors from the stored corpora (counts only).")
    home = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov")).expanduser()
    ap.add_argument("--corpora-root", type=Path, default=home / "corpora")
    ap.add_argument("--corpus", action="append", default=[],
                    help="a corpus directory name, used exactly (repeatable; default: the newest copy of each)")
    ap.add_argument("--corpus-commit", action="append", default=[], metavar="NAME=COMMIT",
                    help="the commit that built corpus NAME (required for every chosen corpus)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--min-executions", type=int, default=5, help="drop keys with fewer executions")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    try:
        roots = choose(args.corpora_root, args.corpus)
        commits = building_commits(args.corpus_commit, roots)
    except Refused as exc:
        print(f"gen_estimate_priors: refused: {exc}", file=sys.stderr)
        return 2
    for root in roots:
        print(f"gen_estimate_priors: reading {root.name} (built at {commits[root.name]})", file=sys.stderr)
    corpora: list[dict[str, Any]] = []
    usages: list[ExecutionUsage] = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for root in roots:
            files = sorted(str(p) for p in (root / "aer").rglob("*.aer.jsonl")) if (root / "aer").is_dir() else []
            read = [u for u in pool.map(_one, files, chunksize=64) if u is not None]
            usages += read
            corpora.append({**_corpus_identity(root), "executions_read": len(read), "aer_files": len(files),
                            "building_commit": commits[root.name]})
            print(f"gen_estimate_priors: {root.name}: {len(read)} of {len(files)} AER files", file=sys.stderr)
    rows: dict[tuple[str, ...], dict[str, Any]] = {}
    for with_model in (True, False):
        for with_backend in (True, False):
            for (bench, suite, attack, family, backend), stats in sorted(aggregate(
                    usages, with_model=with_model, with_backend=with_backend,
                    min_executions=args.min_executions).items()):
                rows.setdefault((bench, suite, attack, family, backend), {
                    "benchmark": bench, "suite": suite, "attack": attack or None, "family": family or None,
                    "backend": backend or None, **stats.to_json()})
    doc = {"format": FORMAT, "built_from": {"commit": _commit(HERE.parent.parent), "tool": "tools/estimate/gen_estimate_priors.py",
                                            "chars_per_token": CHARS_PER_TOKEN, "min_executions": args.min_executions,
                                            "corpora": corpora}}
    head = json.dumps(doc, sort_keys=True, separators=(",", ":"))[:-1]
    lines = [json.dumps(rows[k], sort_keys=True, separators=(",", ":")) for k in sorted(rows)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(head + ',"rows":[\n' + ",\n".join(lines) + "\n]}\n", encoding="utf-8")
    print(f"gen_estimate_priors: {len(rows)} rows from {len(usages)} executions -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
