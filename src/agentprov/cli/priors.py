"""``agentprov priors``: the estimate's local priors, built from your own sealed corpora (D-1062).

    agentprov priors build [--corpus DIR]... [--jobs N] [--min-executions N] [--format text|json]
    agentprov priors show [--format text|json]

``build`` counts the model calls, tokens and durations of the executions of your sealed corpora (every one under
``$AGENTPROV_HOME/corpora``, or the ``--corpus`` directories) into ``$AGENTPROV_HOME/estimate/priors-local.json``, in
the format of the shipped priors (:mod:`agentprov.estimate.localpriors`). Working corpora and withheld executions are
left out; nothing is written into a corpus. ``agentprov estimate`` then uses those rows before the shipped ones (this
model family's rows first). ``show`` says which priors the estimate would use.

Counts only: no corpus text is kept. The table is an input to an estimate, never evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Final

from agentprov.cli.common import CommandResult, Context, bounded_int, safe_text

BUILD_FORMAT: Final = "agentprov-priors-build/0.1"
SHOW_FORMAT: Final = "agentprov-priors-show/0.1"
MAX_CORPORA: Final = 64


def _count(text: str) -> int:
    value = bounded_int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def _positive(text: str) -> int:
    value = bounded_int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser("priors", parents=[shared], help="build or show the estimate's local priors (your sealed corpora)",
                       description=__doc__.splitlines()[0], allow_abbrev=False)
    p.set_defaults(command="priors", handler=run_priors, feedback=False)
    actions = p.add_subparsers(dest="priors_action", metavar="ACTION", required=True)
    b = actions.add_parser("build", parents=[shared],
                           help="count your sealed corpora into $AGENTPROV_HOME/estimate/priors-local.json",
                           allow_abbrev=False)
    b.add_argument("--corpus", action="append", metavar="DIR",
                   help="a sealed corpus to read (repeatable; default: every sealed corpus under "
                        "$AGENTPROV_HOME/corpora, the highest version of each)")
    b.add_argument("--jobs", type=_count, default=0, metavar="N", help="worker processes (0 = host default)")
    b.add_argument("--min-executions", type=_positive, default=5, metavar="N",
                   help="leave out a row with fewer executions (default 5, as the shipped priors)")
    b.add_argument("--format", choices=["text", "json"], default="text")
    s = actions.add_parser("show", parents=[shared], help="the priors the estimate uses: local, shipped or both",
                           allow_abbrev=False)
    s.add_argument("--format", choices=["text", "json"], default="text")


def _payload(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def _summary(path: Path) -> dict[str, Any]:
    """A priors table: whether it exists, its sha256, its rows by benchmark, its model families and its corpora."""
    from agentprov.estimate.localpriors import LABEL, corpora_of
    from agentprov.estimate.priors import load_priors

    header, rows = load_priors(path)
    try:
        sha = hashlib.sha256(path.read_bytes()).hexdigest() if rows else None
    except OSError:
        sha = None
    benchmarks: dict[str, int] = {}
    for key in rows:
        if LABEL.fullmatch(key[0]):
            benchmarks[key[0]] = benchmarks.get(key[0], 0) + 1
    corpora = corpora_of(header)
    return {"exists": bool(rows), "sha256": sha, "rows": len(rows), "benchmarks": dict(sorted(benchmarks.items())),
            "families": sorted({k[3] for k in rows if k[3] and LABEL.fullmatch(k[3])}), "corpora": corpora,
            "executions": sum(c["executions_read"] or 0 for c in corpora)}


def show_document(home: Path) -> dict[str, Any]:
    from agentprov.estimate.localpriors import local_priors_path
    from agentprov.estimate.priors import PRIORS

    path = local_priors_path(home)
    return {"format": SHOW_FORMAT, "local": {"path": str(path), **_summary(path)}, "shipped": _summary(PRIORS),
            "order": ["corpus (--stats-corpus)", "local, this model family", "shipped, this model family",
                      "local, any model", "shipped, any model", "your defaults (estimate.default.*)"]}


def run_priors(ctx: Context) -> CommandResult:
    from agentprov.cli.common import CliUsageError
    from agentprov.cli.live.envs import agentprov_home
    from agentprov.cli import priors_read as R
    from agentprov.estimate import localpriors as L

    args = ctx.args
    home = agentprov_home(ctx.env)
    result = CommandResult()
    if args.priors_action == "show":
        doc = show_document(home)
        if args.format == "json":
            result.payload = _payload(doc)
            return result
        for name in ("local", "shipped"):
            t = doc[name]
            if not t["exists"]:
                result.output(f"{name} priors: none" + (" (build them with 'agentprov priors build')"
                                                         if name == "local" else ""))
                continue
            ids = ", ".join(safe_text(c["corpus_id"] or "?", 80) for c in t["corpora"])
            result.output(f"{name} priors: {t['rows']} rows from {t['executions']:,} executions of "
                          f"{len(t['corpora'])} corpora ({ids})")
            result.output("  benchmarks: " + ", ".join(f"{safe_text(b, 60)} {n}" for b, n in t["benchmarks"].items()))
        result.output("order: " + "; ".join(doc["order"]))
        return result

    if args.corpus and len(args.corpus) > MAX_CORPORA:
        raise CliUsageError(f"agentprov priors build: at most {MAX_CORPORA} --corpus")
    skipped: list[dict[str, Any]] = []
    if args.corpus:
        paths = R.check_given([Path(c) for c in args.corpus])
    else:
        paths, skipped = R.discover(home / "corpora")
    if not paths:
        result.output("priors: no sealed corpus to read: nothing built" + ("" if not skipped else
                      f" ({len(skipped)} director{'y' if len(skipped) == 1 else 'ies'} skipped)"))
        result.counters = {"corpora": 0, "rows": 0}
        if args.format == "json":
            result.payload = _payload({"format": BUILD_FORMAT, "written": False, "path": None, "sha256": None,
                                       "rows": 0, "executions": 0, "corpora": [], "skipped": skipped})
        return result
    from agentprov.io.workers import resolve_worker_count

    jobs = resolve_worker_count(args.jobs)
    data, built = R.build_local(paths, jobs=jobs, min_executions=args.min_executions, skipped=skipped,
                                given=bool(args.corpus), progress=ctx.progress)
    path = L.write_local(home, data)
    result.counters = {"corpora": len(built["corpora"]), "rows": built["rows"], "executions": built["executions"],
                       "skipped": len(built["skipped"])}
    if args.format == "json":
        result.payload = _payload({"format": BUILD_FORMAT, "written": True, "path": str(path),
                                   "sha256": hashlib.sha256(data).hexdigest(), "rows": built["rows"],
                                   "executions": built["executions"], "corpora": built["corpora"],
                                   "skipped": built["skipped"]})
    else:
        for c in built["corpora"]:
            result.output(f"  {safe_text(c['corpus_id'] or '?', 80)} {safe_text(c['corpus_version'] or '', 40)}: "
                          f"{c['executions_read']:,} of {c['executions_indexed']:,} executions"
                          + (f", {c['withheld']} withheld" if c["withheld"] else "")
                          + (f", {c['duplicates']} already counted" if c["duplicates"] else "")
                          + (f", {c['unreadable']} unreadable" if c["unreadable"] else ""))
        for s in built["skipped"]:
            result.output(f"  skipped {safe_text(s['name'] or '(name not shown)', 80)}: {s['reason']}")
        result.output(f"priors: {built['rows']} rows from {built['executions']:,} executions of "
                      f"{len(built['corpora'])} sealed corpora into {path}")
    return result
