"""``agentprov migrate``: the baseline migration gates (MN N.2.14; J.3.0).

Implemented in this build: ``verify-baseline`` (gate G0), ``gate-a``, ``gate-b``, ``gate-d`` and ``gate-e``; ``gate G0|A|B|D|E``
is the same command with the gate as an argument. The sub-command spellings of J.3.0 bind (erratum E7); the others of N.2.14
(``reconcile``, ``gate-c``, ``all``) arrive with their gates and are not registered as stubs.

Gate D (J.3.5; D-49) validates **stored AERs**: ``--scope golden`` is ``tests/golden/test_gate_d.py`` through the CLI; ``--scope full``
takes ``--corpus DIR`` once per tree (the v1 import of the release tree, of the converted tree, and the native June-2024 import),
reads them read-only and writes its report (``--report``, with a markdown and a per-execution JSONL beside it) nowhere else; a report
target inside a corpus (``--report`` or the default under ``--reports-dir``) is refused (exit 4). ``--limit N``
checks an evenly spaced subset (scope ``sample``; a diagnostic report, no predecessor chain). ``--accept-gap TREE`` records that a tree
has no stored AERs; the report says so.

Exit status (N.1.3): 0 the gate passed, 1 it failed, 2 usage, 3 an environment problem (no baseline, no lock, ...), 4 a
refusal (a gate started before its predecessors passed, or ``--release`` with ``--in-process``).

The report (``agentprov-migration-gate/0.1``) is written atomically to ``--report PATH``, or to
``<reports-dir>/<gate>/<UTC date>-<short commit>.json`` (default ``$AGENTPROV_HOME/migration/reports``; never the
repository unless ``--reports-dir`` names it). Gate E also writes the semantic diff of
each tree (``agentprov-semdiff/0.1``, J.3.6) to ``<semdiff-dir>/semdiff-<tree>.{json,md}`` (default ``$AGENTPROV_HOME/migration/semdiff``;
the golden scope writes ``semdiff-<tree>.golden.{json,md}``). Compat output is a regression oracle (R-55): gates B and E
print the notice.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from agentprov.cli.common import CliUsageError, CommandResult, Context, bounded_int, safe_text
from agentprov.errors import AgentProvError

if TYPE_CHECKING:
    from agentprov.migration import gates

GATES = ("G0", "A", "B", "D", "E")


def _default_config() -> Path:
    from agentprov.migration.lock import REPO_ROOT

    return REPO_ROOT / "migration" / "local.toml"


def _positive(text: str) -> int:
    value = bounded_int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def _common(shared: argparse.ArgumentParser) -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--scope", choices=["golden", "full"], help="golden: the golden set (CI); full: the baseline trees (local). Default: golden (G0: full)")
    common.add_argument("--workers", type=_positive, metavar="N", help="worker processes for mapping (0 = host default; default 8 or [run] workers of the config)")
    common.add_argument("--release", action="store_true", help="release mode: params.strict true, skipped checks fail, T1 isolation grade must be watchdog or better")
    common.add_argument("--report", metavar="PATH", help="write the gate report to PATH (atomic); default <reports-dir>/<gate>/<date>-<commit>.json")
    common.add_argument("--reports-dir", metavar="DIR", help="reports directory (default $AGENTPROV_HOME/migration/reports); predecessor reports are looked up here and in the repository's migration/reports")
    common.add_argument("--config", metavar="FILE", help="migration config (default migration/local.toml when it exists)")
    common.add_argument("--in-process", action="store_true", help="debugging only: map in this process (refused with --release)")
    return common


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "migrate",
        parents=[shared],
        help="baseline migration gates G0, A, B, D and E (J.3)",
        description="Run the baseline migration gates (N.2.14; J.3.0). Implemented: verify-baseline (G0), gate-a, gate-b, gate-d, gate-e.",
        allow_abbrev=False,
    )
    p.set_defaults(command="migrate", handler=_no_subcommand, feedback=False)
    inner = p.add_subparsers(dest="migrate_command", metavar="GATE-COMMAND", parser_class=type(p))
    common = _common(shared)

    def add(name: str, help_text: str, gate: str | None) -> argparse.ArgumentParser:
        q = inner.add_parser(name, parents=[shared, common], help=help_text, description=help_text, allow_abbrev=False)
        q.set_defaults(command="migrate", handler=run_migrate, feedback=True, gate_default=gate)
        return q

    add("verify-baseline", "gate G0: verify the old repository, its corpora and the baseline environment against the lock", "G0")
    add("gate-a", "gate A: v1 -> AER -> v1 view, A1 (JCS) and A2 (bytes), from the AER alone", "A")
    add("gate-b", "gate B: adprov-v2.3-compat graph bytes (B1 from the view, B2 from the source)", "B")
    d = add("gate-d", "gate D: SEM and agentprov-prov/0.1 re-derived from stored AERs and validated in every D8 tier (release mode)", "D")
    e = add("gate-e", "gate E: the semantic diff of the compat graphs against agentprov-prov/0.1, from semdiff-map.toml", "E")
    g = add("gate", "run one gate by name: G0, A, B, D or E", None)
    g.add_argument("gate_name", metavar="GATE", type=str.upper, choices=GATES, help="G0, A, B, D or E")
    for q in (d, g):
        q.add_argument("--corpus", action="append", metavar="DIR", help="gate D, full scope: a corpus of stored AERs (read-only); once per tree")
        q.add_argument("--limit", type=_positive, metavar="N", help="gate D: check N evenly spaced executions per corpus (scope sample)")
        q.add_argument("--accept-gap", action="append", choices=["release", "converted", "native"], metavar="TREE",
                       help="gate D, full scope: record that this tree has no stored AERs (the report says so)")
    for q in (e, g):
        q.add_argument("--semdiff-dir", metavar="DIR", help="gate E: where semdiff-<tree>.{json,md} go (default $AGENTPROV_HOME/migration/semdiff)")


def _no_subcommand(ctx: Context) -> CommandResult:
    raise CliUsageError("agentprov migrate: a gate command is required (verify-baseline, gate-a, gate-b, gate-d, gate-e, or gate G0|A|B|D|E)")


def _config(args: argparse.Namespace, scope: str) -> gates.MigrationConfig:
    from agentprov.migration import gates
    from agentprov.migration.pipeline import default_work_dir

    config_file = Path(args.config) if args.config else _default_config()
    if args.config and not config_file.is_file():
        raise CliUsageError("agentprov migrate: --config is not a file")
    overrides: dict[str, Any] = {"strict": bool(args.release), "in_process": bool(args.in_process)}
    if args.workers is not None:
        overrides["workers"] = args.workers
    if args.reports_dir:
        overrides["reports_dir"] = Path(args.reports_dir)
    cfg = gates.MigrationConfig.from_env(config_file=config_file, **overrides)
    if scope == "full" and cfg.work is None:
        cfg = _replace(cfg, work=default_work_dir())
    return cfg


def _replace(cfg: gates.MigrationConfig, **changes: Any) -> gates.MigrationConfig:
    from agentprov.migration import gates

    return gates.MigrationConfig(**{f: getattr(cfg, f) for f in cfg.__dataclass_fields__} | changes)


def run_migrate(ctx: Context) -> CommandResult:
    from agentprov.migration import gates  # imported on use: CLI start-up loads no migration engine

    args = ctx.args
    gate: str = getattr(args, "gate_name", None) or args.gate_default
    scope = cast(Literal["golden", "full"], args.scope or ("full" if gate == "G0" else "golden"))
    if gate == "G0" and scope != "full":
        raise CliUsageError("agentprov migrate: gate G0 verifies the old repository and has the full scope only")
    if args.release and args.in_process:
        raise AgentProvError("--in-process is refused together with --release (G.4.9)", code="cli.refused.in_process", exit_code=4)
    cfg = _config(args, scope)
    report_path = Path(args.report) if args.report else None
    extra = [report_path.parent] if report_path is not None else []
    result = CommandResult()
    if gate == "D":
        return _run_gate_d(ctx, cfg, scope, report_path, extra)
    if getattr(args, "corpus", None) or getattr(args, "limit", None) is not None or getattr(args, "accept_gap", None):
        raise CliUsageError("agentprov migrate: --corpus, --limit and --accept-gap belong to gate D")
    if scope == "full" and gate != "G0":
        gates.require_predecessors(cfg, gate, "full", extra_dirs=extra)
    if report_path is None:  # CB-27: never replace a report of another scope or mode, checked before the work runs
        gates.refuse_default_target(cfg.reports_dir, gate, scope=scope, strict=cfg.strict)

    semdiff_written: list[Path] = []
    semdiffs: dict[str, Any] = {}
    if gate == "G0":
        report = gates.verify_baseline(cfg)
    elif gate == "A":
        report = gates.gate_a_v1_identity(cfg, scope=scope, progress=ctx.progress)
    elif gate == "B":
        report = gates.gate_b_compat_bytes(cfg, scope=scope, progress=ctx.progress)
    else:
        report, semdiffs = gates.gate_e_semdiff(cfg, scope=scope, progress=ctx.progress)
        directory = Path(args.semdiff_dir) if getattr(args, "semdiff_dir", None) else None
        semdiff_written = gates.write_semdiff(semdiffs, directory, scope=scope)

    if gate in ("B", "E"):
        result.output(gates.COMPAT_NOTICE)  # R-55: compat output was produced; never suppressed by -q
        result.notices.append("adprov-v2.3-compat output is a regression oracle (apv:RegressionOracle), not the recommended semantics")
    written = gates.write_report(report, cfg.reports_dir, path=report_path)

    counts = report.counts
    result.counters = {k: int(v) for k, v in counts.items()}
    for failure in report.failures:
        code = failure["check"]
        result.issues_by_code[code] = result.issues_by_code.get(code, 0) + 1
        result.failures.append(
            {"subject": {"path": safe_text(failure["item"], 300)}, "stage": f"gate-{gate}", "code": code, "detail": safe_text(failure["detail"], 300)}
        )
    result.exit_code = 0 if report.verdict == gates.PASS else 1
    unit = "checks" if gate == "G0" else "traces"
    result.output(
        f"gate {gate} ({scope}, {'release' if cfg.strict else 'dev'} mode): {report.verdict}; {counts['passed']}/{counts['expected']} {unit} "
        f"passed, {counts['failed']} failed, {counts['skipped']} skipped; {report.wall_s:.1f}s"
    )
    for tree, semdiff in semdiffs.items():
        doc = semdiff.document
        reasons = ", ".join(f"{rel} {label} {n}" for rel, labels in doc["edges"]["by_relation"].items() for label, n in labels.items())
        result.output(
            f"semdiff {tree}: {doc['executions']} graphs, {doc['edges']['total']} edges ({reasons}); overlaps R4+R6 "
            f"{doc['overlaps']['R4+R6']}; unmapped {doc['unmapped']}"
        )
    result.output(f"report: {safe_text(str(written), 300)}")
    for path in semdiff_written:
        result.output(f"semdiff: {safe_text(str(path), 300)}")
    return result


def _run_gate_d(ctx: Context, cfg: gates.MigrationConfig, scope: str, report_path: Path | None, extra: list[Path]) -> CommandResult:
    from agentprov.migration import gate_d, gates  # noqa: PLC0415 - the engines load only when gate D runs

    args = ctx.args
    corpora = [Path(c) for c in (args.corpus or [])]
    if scope == "golden" and (corpora or args.limit is not None or args.accept_gap):
        raise CliUsageError("agentprov migrate: gate D at golden scope takes no --corpus, --limit or --accept-gap")
    if scope == "full" and not corpora:
        raise CliUsageError("agentprov migrate: gate D at full scope needs --corpus DIR for each tree (stored AERs; see --help)")
    # N.1.5: the default target <reports-dir>/D/<id>.json is refused inside a corpus like --report, before any work runs.
    gate_d._refuse_inside(report_path if report_path is not None else cfg.reports_dir / "D", corpora)
    if scope == "full" and args.limit is None:
        gates.require_predecessors(cfg, "D", "full", extra_dirs=extra)
    if report_path is None:  # CB-27: a --limit run is scope sample (J.3.5)
        gates.refuse_default_target(cfg.reports_dir, "D", scope="sample" if scope == "full" and args.limit is not None else scope, strict=cfg.strict)
    run = gate_d.gate_d_validate(
        cfg, scope=scope, corpora=corpora, limit=args.limit, accept_gaps=args.accept_gap or (), report_path=report_path,
        progress=ctx.progress,
    )  # fmt: skip
    report = run.report
    target = report_path or gates.default_report_path(report, cfg.reports_dir)
    written = gate_d.write_outputs(run, target)
    result = CommandResult()
    counts = report.counts
    result.counters = {k: int(v) for k, v in counts.items()}
    for failure in report.failures:
        code = failure["check"]
        result.issues_by_code[code] = result.issues_by_code.get(code, 0) + 1
        result.failures.append(
            {"subject": {"path": safe_text(failure["item"], 300)}, "stage": "gate-D", "code": code, "detail": safe_text(failure["detail"], 300)}
        )
    result.exit_code = 0 if report.verdict == gates.PASS else 1
    result.output(
        f"gate D ({report.scope}, {'release' if cfg.strict else 'dev'} mode): {report.verdict}; {counts['passed']}/{counts['expected']} "
        f"executions passed, {counts['failed']} failed, {counts['skipped']} skipped; {report.wall_s:.1f}s"
    )
    for check in report.checks:
        if check.status != gates.PASS:
            result.output(f"check {safe_text(check.check, 120)}: {check.status}: {safe_text(check.detail, 200)}")
    for path in written:
        result.output(f"{'report' if path.suffix == '.json' else path.suffix.lstrip('.') or 'file'}: {safe_text(str(path), 300)}")
    return result
