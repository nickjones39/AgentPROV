"""``agentprov render``: on-demand PROV graph renders of selected executions (MN N.2.13; G.8.6; K.5.12).

Nothing is rendered during import; this command draws only what it is asked to. It reads a corpus (a sealed one, a
working one, or the ``<DIR>.partial`` tree of an import in progress) strictly and read-only, validates each selected
execution's ``agentprov-prov/0.1`` PROV-JSON, and writes ``<ex>.dot`` plus one image per format below the output
directory, ``<corpus>-rendered/<spec_dir>/<ss>/`` by default. It never writes inside a corpus (guard G8: exit 4).

Selection is by ``--ex`` (execution ids), ``--select KEY=VALUE[,VALUE...]`` (the AER-header keys of ``import --select``,
read from each execution's AER header; it must be bounded with ``--limit``) or ``--limit N`` alone (the first N executions
in index order). There is no ``--all``: renders are on demand, never of every graph (D-45), so a bare
``render --corpus DIR`` cannot start thousands of Graphviz runs.

The core bundle is drawn by default; ``--bundle all`` adds the inference and assessment bundles and the assessment
overlay (integrity and role colours, claim links). An image is laid out only for a graph of at most ``--max-edges``
edges (default 800): a large ``--bundle all`` graph would otherwise run into ``dot``'s 120 s timeout. Above the limit the
``.dot`` text is written, the execution fails with ``render.graph_too_large`` and the message names the remedies. Labels hold trusted-grammar tokens only; ``--show-content`` adds the
other attributes after ``escape_untrusted`` (the global ``--content-chars`` truncates). The DOT text is deterministic;
image bytes depend on the Graphviz version, which the run records as a notice.

Exit status (N.1.3): 0 all selected executions rendered, 1 a selected execution could not be (invalid or missing PROV, a
``dot`` failure; the others are still rendered), 2 usage, 3 the ``render`` extra or the ``dot`` binary is missing, 4 the
output is inside a corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Final

from agentprov.cli.common import CliUsageError, CommandResult, Context, bounded_int, redact_personal, safe_text
from agentprov.corpus.layout import dirname
from agentprov.errors import AgentProvError, IngestError
from agentprov.progress import ProgressEvent

_SELECT = re.compile(r"[A-Za-z][A-Za-z0-9_]*=[^=,][^=]*")
_EXECUTION_ID = re.compile(r"ex_[a-z2-7]{26}|ex_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_FORMAT_CHOICES: Final = ("svg", "png", "pdf", "dot")
_LISTED_PATHS: Final = 20  # per-execution output lines are printed up to this many executions


def _non_negative(text: str) -> int:
    value = bounded_int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "render",
        parents=[shared],
        help="draw selected executions' PROV graphs (needs the render extra and Graphviz dot)",
        description=(
            "Render the agentprov-prov/0.1 PROV graph of selected executions to DOT and images (N.2.13). Nothing is rendered "
            "unless asked; renders go to <corpus>-rendered/ (or --out), never into a corpus. Needs the render extra "
            "(uv sync --frozen --group docs --extra render) and the Graphviz dot binary, except with --format dot. --show-content adds attribute values "
            "(escaped, one line, --content-chars long) to the node labels; without it labels hold only ids, types and rule ids."
        ),
        epilog=(
            "Notation: entities are ovals, activities boxes, agents houses (W3C PROV colours). Border and line style show the "
            "evidence class: solid thick = Observed, dashed = Derived, dotted = Inferred, thin grey = no class. With "
            "--bundle all, purple marks the inference bundles and brown the assessment bundles; untrusted integrity is "
            "salmon, unknown integrity or role is grey, sinks are dark red and endorsers light blue. Examples: "
            "agentprov render --corpus C --ex ex_...   |   agentprov render --corpus C --select attack=important_instructions "
            "--limit 20 --format svg,png   |   agentprov render --corpus C --ex ex_... --bundle all --show-content"
        ),
        allow_abbrev=False,
    )
    p.set_defaults(command="render", handler=run_render, feedback=True)
    p.add_argument("--corpus", metavar="DIR", required=True, help="the corpus to read (sealed, working, or DIR.partial)")
    sel = p.add_argument_group("selection (--ex ID..., --select with --limit N, or --limit N; there is no render-all)")
    sel.add_argument("--ex", action="extend", nargs="+", default=[], metavar="ID", help="execution ids to render")
    sel.add_argument("--select", action="append", default=[], metavar="KEY=VALUE[,VALUE...]",
                     help="AER-header filter, as for import --select (repeatable)")  # fmt: skip
    sel.add_argument("--limit", type=_non_negative, metavar="N",
                     help="render at most the first N selected executions (required with --select)")  # fmt: skip
    out = p.add_argument_group("drawing and output")
    out.add_argument("--bundle", choices=["core", "all"], default="core",
                     help="core (default): the core bundle only; all: also the inference and assessment bundles")  # fmt: skip
    out.add_argument("--format", metavar="LIST", default="svg",
                     help="comma list from svg,png,pdf,dot (default svg); the .dot text is always written")  # fmt: skip
    out.add_argument("--direction", choices=["LR", "TB"], default="LR", help="rank direction (default LR)")
    out.add_argument("--out", metavar="DIR", help="output directory (default <corpus>-rendered); never inside a corpus")
    out.add_argument("--max-edges", type=_non_negative, metavar="N",
                     help="image layout limit: a graph with more edges gets its .dot text but no image (default 800; "
                          "0 = no limit, dot still times out at 120 s)")  # fmt: skip
    out.add_argument("--jobs", type=_non_negative, default=0, metavar="N",
                     help="parallel dot processes (0 = the host default worker count; default 0)")  # fmt: skip
    out.add_argument("--dry-run", action="store_true", help="select and build the DOT text in memory; write and run nothing")


# ------------------------------------------------------------------------------------------------ options
def _formats(text: str) -> tuple[str, ...]:
    names = [part.strip().lower() for part in text.split(",") if part.strip()]
    bad = [n for n in names if n not in _FORMAT_CHOICES]
    if not names or bad:
        shown = ", ".join(safe_text(n, 20) for n in bad)
        raise CliUsageError(
            "agentprov render: --format takes a comma list from " + ", ".join(_FORMAT_CHOICES) + (f"; unknown: {shown}" if bad else "")
        )
    return tuple(dict.fromkeys(names))


def _select_filters(expressions: list[str]) -> Any:
    from agentprov.adapters.runner.importer import SELECT_KEYS, ImportFilters

    chosen: dict[str, set[str]] = {}
    for expression in expressions:
        if not _SELECT.fullmatch(expression):
            raise CliUsageError(f"agentprov render: --select expects KEY=VALUE[,VALUE...], got {safe_text(expression, 80)!r}")
        key, _, values = expression.partition("=")
        if key not in SELECT_KEYS:
            raise CliUsageError(
                f"agentprov render: --select key {safe_text(key, 40)!r} is not supported; keys: {', '.join(sorted(SELECT_KEYS))} "
                "(AER header fields, as for import --select)"
            )
        chosen.setdefault(key, set()).update(v for v in values.split(",") if v)
    return ImportFilters(select={k: frozenset(v) for k, v in sorted(chosen.items())})


def _check_options(args: argparse.Namespace) -> tuple[tuple[str, ...], list[str], Any]:
    formats = _formats(args.format)
    ex_ids = list(dict.fromkeys(args.ex))
    for ex in ex_ids:
        if not _EXECUTION_ID.fullmatch(ex):
            raise CliUsageError(f"agentprov render: --ex expects execution ids (ex_...), got {safe_text(ex, 80)!r}")
    filters = _select_filters(args.select) if args.select else None
    if not (ex_ids or filters is not None or args.limit is not None):
        raise CliUsageError(
            "agentprov render: nothing selected; give --ex ID..., --select KEY=VALUE with --limit N, or --limit N "
            "(renders are on demand, so there is no default selection and no render-all; D-45)"
        )
    if filters is not None and args.limit is None:
        raise CliUsageError(
            "agentprov render: --select needs --limit N, so that a filter cannot start an unbounded number of renders "
            "(on demand only; D-45)"
        )
    return formats, ex_ids, filters


# ------------------------------------------------------------------------------------------------ selection
def _select_rows(source: Any, ex_ids: list[str], filters: Any, limit: int | None, result: CommandResult) -> list[Any]:
    from agentprov.render.source import read_aer_header

    rows = list(source.rows)
    if ex_ids:
        known = {r.ex: r for r in rows}
        missing = [e for e in ex_ids if e not in known]
        if missing:
            raise CliUsageError(
                "agentprov render: --ex names executions that are not in the corpus index: "
                + ", ".join(safe_text(m, 60) for m in missing[:5])
                + (f" (+{len(missing) - 5} more)" if len(missing) > 5 else "")
            )
        rows = [known[e] for e in sorted(ex_ids)]
    if filters is not None:
        kept = []
        unreadable = 0
        for row in rows:
            header = read_aer_header(source, row)
            if header is None:
                unreadable += 1
            elif filters.keep(header):
                kept.append(row)
        if unreadable:
            result.notices.append(f"--select: {unreadable} execution(s) have no readable AER header and were not selected")
        rows = kept
    if limit is not None:
        rows = rows[:limit]
    return rows


# ------------------------------------------------------------------------------------------------ one execution
class _Outcome:
    __slots__ = ("code", "detail", "dot_sha256", "ex", "paths")

    def __init__(self, ex: str) -> None:
        self.ex = ex
        self.paths: list[Path] = []
        self.dot_sha256: str | None = None
        self.code: str | None = None
        self.detail = ""


def _render_one(source: Any, row: Any, label: str, opts: dict[str, Any]) -> _Outcome:
    from agentprov.render.errors import RenderEnvironmentError
    from agentprov.render.graph import render_prov_graph
    from agentprov.render.output import output_stem
    from agentprov.render.source import SPEC_ID, read_prov_document

    outcome = _Outcome(row.ex)
    try:
        doc = read_prov_document(source, label)
        stem = output_stem(opts["out"], label, spec_dir=dirname(SPEC_ID))
        paths, text = render_prov_graph(
            doc, stem, ex=row.ex, formats=opts["formats"], direction=opts["direction"], bundles=opts["bundle"],
            show_content=opts["show_content"], content_chars=opts["content_chars"], dry_run=opts["dry_run"],
            max_edges=opts["max_edges"],
        )  # fmt: skip
        outcome.paths = paths
        outcome.dot_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    except RenderEnvironmentError:
        raise
    except IngestError as exc:
        outcome.code, outcome.detail = exc.code, exc.reason
    except AgentProvError as exc:
        outcome.code, outcome.detail = exc.code, str(exc)
    except OSError as exc:
        outcome.code, outcome.detail = "render.write_failed", exc.strerror or type(exc).__name__
    return outcome


# ------------------------------------------------------------------------------------------------ command
def run_render(ctx: Context) -> CommandResult:
    from agentprov.render import dot as dotmod
    from agentprov.render import output
    from agentprov.render.source import SPEC_ID, locate_corpus, open_corpus, prov_label

    args = ctx.args
    formats, ex_ids, filters = _check_options(args)
    result = CommandResult(dry_run=bool(args.dry_run))
    progress = ctx.progress

    # 1. where things are, and the output guard: neither needs the extra
    root, used_partial = locate_corpus(args.corpus)
    out_dir = output.assert_output_allowed(args.out if args.out else output.default_output_dir(root), root)

    # 2. the environment: pydot always (it builds the DOT text), the dot binary only for an image format
    dotmod.require_pydot()
    images = [f for f in formats if f != "dot"]
    exe = dotmod.find_dot() if images and not args.dry_run else None
    version = dotmod.graphviz_version(exe) if exe is not None else None
    if version is not None:
        result.notices.append(f"graphviz dot {version} (image bytes depend on the Graphviz version; the .dot text does not)")

    # 3. the corpus and the selection
    source = open_corpus(root)
    if used_partial or source.state != "sealed":
        result.notices.append(
            f"{'working tree' if used_partial else 'working corpus'}: not sealed or verified (run 'agentprov verify' before "
            "trusting a downloaded corpus); the render shows what the files say"
        )
    selected = _select_rows(source, ex_ids, filters, args.limit, result)
    explicit = set(ex_ids)

    plan: list[tuple[Any, str]] = []
    skipped = 0
    for row in selected:
        label = prov_label(source, row, SPEC_ID)
        if label is not None:
            plan.append((row, label))
            continue
        if row.ex in explicit:
            result.failures.append(
                {"subject": {"ex": row.ex}, "stage": "select", "code": "render.no_prov",
                 "detail": "the execution has no agentprov-prov/0.1 output in the index"}
            )  # fmt: skip
            result.issues_by_code["render.no_prov"] = result.issues_by_code.get("render.no_prov", 0) + 1
            result.error(f"{safe_text(row.ex, 80)}: has no agentprov-prov/0.1 output in this corpus; nothing to render")
        else:
            skipped += 1
    if skipped:
        result.notices.append(f"{skipped} selected execution(s) have no agentprov-prov/0.1 output and were skipped")

    from agentprov.io.workers import resolve_worker_count

    jobs = args.jobs or resolve_worker_count(0)
    opts = {
        "out": out_dir, "formats": formats, "direction": args.direction, "bundle": args.bundle,
        "show_content": bool(args.show_content), "content_chars": args.content_chars or 200, "dry_run": bool(args.dry_run),
        "max_edges": args.max_edges,
    }  # fmt: skip
    progress.emit(
        ProgressEvent(
            "start", total=len(plan),
            fields={"command": "render", "plan": f"{args.bundle} bundle, {','.join(formats)}", "workers": jobs},
        )
    )  # fmt: skip

    counters = {"selected": len(selected), "rendered": 0, "failed": len(result.failures), "skipped_no_prov": skipped, "files": 0}
    started = {row.ex: time.monotonic() for row, _ in plan}
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for (row, _label), outcome in zip(plan, pool.map(lambda item: _render_one(source, item[0], item[1], opts), plan), strict=True):
            shown = safe_text(row.ex, 80)
            progress.emit(ProgressEvent("unit_start", unit=shown))
            if outcome.code is None:
                counters["rendered"] += 1
                counters["files"] += 0 if args.dry_run else len(outcome.paths)
                if len(plan) <= _LISTED_PATHS:
                    for path in outcome.paths:
                        result.info(("would write " if args.dry_run else "wrote ") + safe_text(redact_personal(str(path)), 400))
                status = "ok"
            else:
                counters["failed"] += 1
                result.issues_by_code[outcome.code] = result.issues_by_code.get(outcome.code, 0) + 1
                result.failures.append(
                    {"subject": {"ex": row.ex}, "stage": "render", "code": outcome.code, "detail": safe_text(outcome.detail, 300)}
                )
                result.error(f"{shown}: not rendered: {outcome.code}: {safe_text(outcome.detail, 200)}")
                status = "failed"
            progress.emit(
                ProgressEvent("unit_done", unit=shown, status=status, duration_s=time.monotonic() - started[row.ex],
                              codes=() if outcome.code is None else (outcome.code,))
            )  # fmt: skip

    large = result.issues_by_code.get("render.graph_too_large", 0) + result.issues_by_code.get("render.dot_timeout", 0)
    if large:
        limit = dotmod.MAX_LAYOUT_EDGES if args.max_edges is None else args.max_edges
        result.error(
            f"agentprov render: {large} graph(s) too large to lay out as an image (limit {limit} edges, dot timeout "
            f"{dotmod.DOT_TIMEOUT_S:.0f} s); their .dot text was written. Use --bundle core, lay the .dot out offline, or "
            "raise --max-edges"
        )
    result.counters = counters
    result.exit_code = 1 if counters["failed"] else 0
    result.corpus = {
        "content_digest": None,
        "corpus_id": source.corpus_id if source.corpus_id is not None else "",
        "root": redact_personal(str(source.root)),
        "state": source.state,
    }
    verb = "would render" if args.dry_run else "rendered"
    result.info(
        f"{verb} {counters['rendered']} of {len(selected)} selected execution(s) ({args.bundle} bundle) "
        f"to {safe_text(redact_personal(str(out_dir)), 300)}; {counters['failed']} failed"
    )
    if not selected:
        result.notices.append("no execution matched the selection")
    return result
