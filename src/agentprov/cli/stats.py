"""``agentprov stats``: minimal, generic statistics over one or more corpora (MN N.2.12; K.5.11; G.8.6; D.15.4).

    agentprov stats --corpus DIR [--corpus DIR …] [--tables counts,statements,unknowns,field_groups]
          [--prov-spec SPEC] [--select K=V…] [--format {text,csv,json,markdown}] [--out PATH] [--artefacts]
          [--per-execution]

Each corpus is opened read-only (sealed, working or ``DIR.partial``; N.1.5) with ``verify="checksums"``: a sealed corpus
whose checksums fail gets no tables and the command exits 1; a working corpus cannot be verified and gets a notice
recommending ``agentprov verify``. Tables are computed per corpus, never pooled (:mod:`agentprov.stats.tables`).
``--artefacts`` adds the D.15.4 artefact table of the shared artefact layer; ``--per-execution`` adds the statements
table at execution grain (O.3.5).

The payload goes to stdout, or to ``--out PATH`` (atomic), which must lie outside every corpus (guard G8: exit 4). With the
global ``--json`` the CLI summary takes stdout, so the payload goes to ``--out`` or, without it, to stderr. Output is
deterministic (no wall-clock value; ``json`` is JCS). Exit 0; 1 when a corpus fails the checksums check or a file of a
corpus cannot be read; 2 for usage; 4 for an output path inside a corpus.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any, Final

from agentprov.cli.common import CliUsageError, CommandResult, Context, redact_personal, safe_text
from agentprov.errors import AgentProvError
from agentprov.progress import ProgressEvent

__all__ = ["StatsOutputRefused", "register", "run_stats"]

_SELECT: Final = re.compile(r"[A-Za-z][A-Za-z0-9_.]*=[^=]+")
_FORMATS: Final = ("text", "csv", "json", "markdown")


class StatsOutputRefused(AgentProvError):
    """``--out`` lies inside a corpus (guard G8; exit 4)."""

    code = "stats.output_in_corpus"
    exit_code = 4


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    from agentprov.stats.tables import PROV_SPECS, TABLES

    p = sub.add_parser(
        "stats",
        parents=[shared],
        help="generic statistics over corpora: counts, PROV statements, unknowns, field-group coverage",
        description=(
            "Compute the generic tables of N.2.12 over each corpus separately (never pooled): counts per source, status "
            "and unit; PROV statements by evidence class, bundle and rule; unknown-reason proportions per field-group "
            "pointer; and the per-source information-loss table (field-group coverage, R-57). Reads the corpus "
            "read-only; writes only to stdout or --out (outside every corpus). Only aggregates are printed."
        ),
        epilog=(
            "Examples: agentprov stats --corpus C   |   agentprov stats --corpus C1 --corpus C2 --tables field_groups "
            "--format csv --out fg.csv   |   agentprov stats --corpus C --select unit=agent_execution --format json   |   "
            "agentprov stats --corpus C --artefacts --tables counts"
        ),
        allow_abbrev=False,
    )
    p.set_defaults(command="stats", handler=run_stats, feedback=True)
    p.add_argument("--corpus", metavar="DIR", action="append", required=True,
                   help="a corpus to read (sealed, working, or DIR.partial); repeatable, one table set per corpus")  # fmt: skip
    p.add_argument("--tables", metavar="LIST", default=",".join(TABLES),
                   help=f"comma list from {','.join(TABLES)} (default: all four)")  # fmt: skip
    p.add_argument("--artefacts", action="store_true",
                   help="also scan every selected execution with the shared artefact layer (D.15.4 table)")  # fmt: skip
    p.add_argument("--per-execution", action="store_true",
                   help="with the statements table, also give it at execution grain (statements_by_execution; O.3.5)")  # fmt: skip
    p.add_argument("--prov-spec", choices=PROV_SPECS, default=PROV_SPECS[0],
                   help="the provenance spec whose PROV files the statements table counts (default agentprov-prov/0.1)")  # fmt: skip
    p.add_argument("--select", action="append", default=[], metavar="KEY=VALUE[,VALUE...]",
                   help="index-row filter (repeatable; keys: source_id, profile, unit, status, mode, completeness, "
                        "execution_observed, adapter, snapshot, issue, facet.<name>, cell.<member> (suite, task_id, "
                        "attack_id, attack_target_id, defense_id, ...), outcome.<claim>=true|false|none)")  # fmt: skip
    p.add_argument("--format", choices=_FORMATS, default="text", help="payload format (default text)")
    p.add_argument("--out", metavar="PATH", help="write the payload to PATH (atomic; never inside a corpus)")


# ------------------------------------------------------------------------------------------------ options
def _tables(text: str, artefacts: bool) -> tuple[str, ...]:
    from agentprov.stats.tables import TABLES

    names = [t.strip() for t in text.split(",") if t.strip()]
    bad = [n for n in names if n not in TABLES]
    if not names or bad:
        shown = ", ".join(safe_text(n, 30) for n in bad)
        raise CliUsageError(f"agentprov stats: --tables takes a comma list from {', '.join(TABLES)}" + (f"; unknown: {shown}" if bad else ""))
    chosen = tuple(dict.fromkeys(names))
    return (*chosen, "artefacts") if artefacts else chosen


def _select(expressions: list[str]) -> dict[str, list[str]]:
    from agentprov.stats.source import SelectionError, normalise_select

    chosen: dict[str, list[str]] = {}
    for expression in expressions:
        if not _SELECT.fullmatch(expression):
            raise CliUsageError(f"agentprov stats: --select expects KEY=VALUE[,VALUE...], got {safe_text(expression, 80)!r}")
        key, _, values = expression.partition("=")
        chosen.setdefault(key, []).extend(v for v in values.split(",") if v)
    try:
        normalise_select(chosen)
    except SelectionError as exc:
        raise CliUsageError(
            f"agentprov stats: --select: {exc}") from None  # fmt: skip
    return chosen


def _check_output(out: str, roots: list[Path]) -> Path:
    """Refuse an output inside any corpus (G8): a corpus root, an ancestor holding a corpus file, or a sealed corpus."""
    from agentprov.corpus.layout import SealedCorpusError, assert_writable

    resolved = Path(os.path.realpath(out))
    if resolved.is_dir():
        raise CliUsageError("agentprov stats: --out names a directory; give a file path")
    if not resolved.parent.is_dir():
        raise CliUsageError(f"agentprov stats: --out: the directory {safe_text(redact_personal(str(resolved.parent)), 200)!r} does not exist")
    try:
        assert_writable(resolved)
    except SealedCorpusError:
        raise StatsOutputRefused("refusing to write statistics inside a sealed corpus (guard G8)") from None
    for directory in resolved.parents:
        if directory in roots or (directory / "corpus.json").exists() or (directory / "executions.jsonl").exists():
            raise StatsOutputRefused("refusing to write statistics inside a corpus; use --out PATH outside every corpus (guard G8)")
    return resolved


# ------------------------------------------------------------------------------------------------ command
def run_stats(ctx: Context) -> CommandResult:
    from agentprov.io.atomic import atomic_write_bytes
    from agentprov.stats import compute, open_corpus
    from agentprov.stats.output import render

    args = ctx.args
    tables = _tables(args.tables, args.artefacts)
    select = _select(args.select)
    result = CommandResult()

    corpora = [open_corpus(path, verify="checksums", raise_on_failure=False) for path in args.corpus]
    roots = [Path(os.path.realpath(c.root)) for c in corpora]
    if len(set(roots)) != len(roots):
        raise CliUsageError("agentprov stats: the same corpus is given twice")
    out_path = _check_output(args.out, roots) if args.out else None

    progress = ctx.progress
    progress.emit(ProgressEvent("start", fields={"command": "stats", "plan": ",".join(tables), "corpora": len(corpora)}))

    def on_row(row: Any) -> None:
        progress.emit(ProgressEvent("unit_done", unit=row.ex, status="ok"))

    if args.per_execution and "statements" not in tables:
        raise CliUsageError("agentprov stats: --per-execution applies to the statements table; add it to --tables")
    report = compute(corpora, tables, prov_spec=args.prov_spec, select=select, on_row=on_row, per_execution=args.per_execution)
    document = report.to_json()
    payload = render(document, args.format)

    for corpus, tables_of in zip(corpora, report.corpora, strict=True):
        label = safe_text(corpus.corpus_id or "(no corpus_id)", 80)
        if corpus.verification == "not_sealed":
            result.notices.append(f"{label}: working corpus, not sealed or verified (run 'agentprov verify' before trusting a "
                                  "downloaded corpus)")  # fmt: skip
        elif corpus.verification == "failed":
            result.error(f"agentprov stats: {label}: the corpus fails the checksums check; no table computed")
        result.notices.extend(f"{label}: {safe_text(n, 300)}" for n in tables_of.notices)
        for code, n in tables_of.failures.items():
            result.issues_by_code[code] = result.issues_by_code.get(code, 0) + n
        result.failures.extend(tables_of.failure_list)
    for notice in result.notices:
        result.info(f"agentprov stats: notice: {notice}")
    failed_corpora = sum(1 for c in corpora if c.verification == "failed")
    result.counters = {
        "corpora": len(corpora),
        "corpora_failed_checksums": failed_corpora,
        "rows": sum(t.population["rows"] for t in report.corpora),
        "selected": sum(t.population["selected"] for t in report.corpora),
        "read_failures": sum(len(t.failure_list) for t in report.corpora),
    }
    first = corpora[0]
    result.corpus = {
        "content_digest": first.content_digest,
        "corpus_id": first.corpus_id or "",
        "root": redact_personal(str(first.root)),
        "state": first.state,
    }
    result.exit_code = 1 if failed_corpora or report.failed else 0

    if out_path is not None:
        atomic_write_bytes(out_path, payload)
        result.info(f"wrote {args.format} statistics for {len(corpora)} corpus/corpora to {safe_text(redact_personal(str(out_path)), 300)}")
    elif args.json:
        # --json puts the summary document on stdout, so the payload goes to stderr (N.1.4)
        for line in payload.decode("utf-8").splitlines():
            result.output(line)
    else:
        result.payload = payload
    return result
