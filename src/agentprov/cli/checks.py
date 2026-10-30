"""``agentprov validate``: the validation tiers (MN N.2.5; DECISIONS D8, D-40).

**File mode** (``FILE...``, ``--aer PATH``) implements tier 2, the AER tier (``agentprov.aer.validate``), for
``.aer.jsonl`` files; ``.sem.jsonl``, ``.prov.json`` and ``.prov.trig`` files exit 5 (their file-mode tiers are not built).
Locator and artefact-digest checks need the raw store: ``--store DIR`` names one (the ``raw/`` directory of a corpus);
without it those checks are reported skipped.

**Corpus mode** (``--corpus DIR``; phase 11, U4) re-runs the tiers ``aer``, ``sem``, ``prov`` and ``linkage`` over the
corpus's stored outputs (:mod:`agentprov.corpus.validation`), read-only for sealed and working corpora alike: the report
goes to ``--report PATH`` (outside the corpus; ``-`` for stdout) and the summary to ``--json``. It gives per-execution
rows of the ``validation/results.jsonl`` shape, the tier results and ``linkage_resolved_pct`` in the D-40 shape, and
compares the rows with the corpus's stored ``validation/`` (``results_reproduced`` / ``results_differ``) when every
default tier runs in the corpus's own validation mode. ``--strict`` and ``--release`` run the validators in release
mode (a skipped check fails); ``--release`` also asks for ``shacl`` and ``regression``. ``shacl`` is not built and
``regression`` applies to ``adprov-v1`` corpora only (not built either): a requested tier that does not run is reported
**skipped**, never passed, and fails under ``--strict`` and ``--release`` (N.2.5(1)). ``--sample N --seed S`` validates a
seeded sample (forbidden with ``--release``).

A file or corpus under validation is untrusted input: it is opened through ``agentprov.ingest.paths`` and parsed by the
validators' bounded, strict loaders. Findings never contain text taken from the data (G.3.9), and anything shown still
passes ``safe_text``.
"""

from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from agentprov.raw.store import RawObjectStore
from agentprov.cli.common import (
    CliUsageError,
    CommandResult,
    Context,
    Refusal,
    UnsupportedCapability,
    bounded_int,
    redact_personal,
    safe_text,
)
from agentprov.errors import AgentProvError, IngestError
from agentprov.progress import ProgressEvent

if TYPE_CHECKING:
    from agentprov.aer.rules import RuleRegistry
    from agentprov.aer.validate import ValidationReport

TIERS: Final = ("aer", "sem", "prov", "linkage", "shacl", "regression")
DEFAULT_TIERS: Final = ("aer", "sem", "prov", "linkage")
#: The tiers corpus mode runs (U4); ``shacl`` and ``regression`` are not built.
IMPLEMENTED_TIERS: Final = frozenset({"aer", "sem", "prov", "linkage"})
#: The tiers file mode runs (by file type).
FILE_TIERS: Final = frozenset({"aer"})
_SUFFIX_TIERS: Final = {".aer.jsonl": "aer", ".sem.jsonl": "sem", ".prov.json": "prov", ".prov.trig": "prov"}
_HEX64: Final = re.compile(r"[0-9a-f]{64}")



def _validate_limits(manifest: Any) -> Any:
    """D-935: the validate jobs' limits with the memory cap the corpus's source profile raises (``[import]
    prov_rss_bytes``, read at the recorded profile version), else ``None`` (the defaults). Timing only."""
    import dataclasses

    from agentprov.adapters.profiles import load_profile, worker_caps
    from agentprov.corpus.validation import VALIDATE_LIMITS

    cap = 0
    for source in manifest.get("sources") or () if isinstance(manifest, dict) else ():
        profile = source.get("profile") if isinstance(source, dict) else None
        if not (isinstance(profile, dict) and isinstance(profile.get("id"), str) and isinstance(profile.get("version"), int)):
            continue
        try:
            cap = max(cap, worker_caps(load_profile(profile["id"], profile["version"])).get("validate", 0))
        except AgentProvError:
            continue
    if not cap:
        return None
    return dataclasses.replace(VALIDATE_LIMITS, kind_rss_bytes={**VALIDATE_LIMITS.kind_rss_bytes, "validate": cap})

def _non_negative(text: str) -> int:
    value = bounded_int(text)  # CC-15: within the JSON summary's integer domain
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "validate",
        parents=[shared],
        help="validate AER files (tier 2) or a corpus's stored outputs (tiers aer, sem, prov, linkage)",
        description="Validate AgentPROV Execution Record files (tier 2), or re-run the tiers aer, sem, prov and linkage "
        "over a corpus's stored outputs, read-only (--corpus; N.2.5). Checks that cannot run are reported as skipped, never "
        "as passed.",
        allow_abbrev=False,
    )
    p.set_defaults(command="validate", handler=run_validate, feedback=True)
    p.add_argument("files", nargs="*", metavar="FILE", help="files to validate (type detected by suffix: .aer.jsonl)")
    p.add_argument("--aer", action="append", default=[], metavar="PATH", help="an AER file, whatever its suffix (repeatable)")
    p.add_argument("--store", metavar="DIR", help="raw store directory (objects/<h0h1>/<sha256>); without it locator checks are skipped")
    p.add_argument("--corpus", metavar="DIR", help="validate a corpus's stored outputs, read-only (sealed, working or .partial)")
    p.add_argument("--tiers", metavar="LIST", help=f"comma list from {','.join(TIERS)} (default {','.join(DEFAULT_TIERS)})")
    p.add_argument("--prov-spec", metavar="SPEC", help="corpus mode: the PROV spec (agentprov-prov/0.1)")
    strict = p.add_mutually_exclusive_group()
    strict.add_argument("--strict", action="store_true", help="a skipped check fails")
    strict.add_argument("--release", action="store_true", help="implies --strict, release-mode validator, every applicable tier")
    p.add_argument("--report", metavar="PATH", help="corpus mode: write the report to PATH (outside the corpus; - = stdout)")
    p.add_argument("--sample", type=_non_negative, metavar="N", help="corpus mode: validate a seeded sample of N executions")
    p.add_argument("--seed", metavar="S", help="sampling seed")
    p.add_argument("--card", metavar="CARD.md", help="lint a corpus card with the claims library (N.2.5(7))")
    p.add_argument("--jobs", type=_non_negative, default=0, metavar="N",
                   help="corpus mode: worker processes for tiers sem, prov and linkage (0 = host default)")
    p.add_argument("--in-process", action="store_true",
                   help="corpus mode: run every tier in this process (no workers; allowed with --release, AD-10 row 17)")
    p.add_argument("--no-validation-cache", action="store_true",
                   help="corpus mode: always run the tier-4 PROV-O round trip; neither read nor write the round-trip "
                   "cache under $AGENTPROV_HOME/cache/tier4 (D-550). --release never reads it either: it recomputes "
                   "every round trip and audits the entries it finds")
    p.add_argument("--dry-run", action="store_true", help="accepted (file validation never writes)")


def open_store(root: str | os.PathLike[str]) -> RawObjectStore:
    """Open an existing raw store read-only, re-hashing every object it returns (``agentprov.raw.store``)."""
    return RawObjectStore(root, create=False, verify_on_read=True)


def _catalogues() -> RuleRegistry:
    """The rule catalogues the validator may autoload (package data only; the adapter families add theirs later)."""
    from agentprov.aer.rules import RuleRegistry

    return RuleRegistry()


# --------------------------------------------------------------------------------------------------------------
# Validation of one file
# --------------------------------------------------------------------------------------------------------------


def _validate_file(path: str, *, store: RawObjectStore | None, mode: str) -> ValidationReport:
    from agentprov.aer.validate import AerValidator, iter_lines
    from agentprov.ingest.paths import open_evidence, open_root

    target = Path(path)
    validator = AerValidator(store=store, catalogues=_catalogues(), mode=mode)  # type: ignore[arg-type]
    with open_root(target.parent) as root, open_evidence(root, target.name) as stream:
        for line, oversize in iter_lines(stream):
            validator.feed(line, oversize=oversize)
    return validator.finish()


def _classify(args: argparse.Namespace) -> list[str]:
    """The file arguments in order (explicit ``--aer`` paths, then positional files), type-checked."""
    paths: list[str] = list(args.aer)
    for name in args.files:
        lower = name.lower()
        tier = next((t for suffix, t in _SUFFIX_TIERS.items() if lower.endswith(suffix)), None)
        if tier is None:
            raise CliUsageError(
                f"agentprov validate: cannot tell the type of {safe_text(name, 120)!r} (expected .aer.jsonl, .sem.jsonl, "
                ".prov.json or .prov.trig); name an AER file with --aer PATH"
            )
        if tier not in FILE_TIERS:
            raise UnsupportedCapability(
                f"cannot validate {safe_text(name, 120)!r}: the {tier} tier is not implemented in this build",
                refusal=Refusal(
                    id=name,
                    mode="validate",
                    status=f"the {tier} tier is not implemented in this build",
                    lines=("Only the AER tier (.aer.jsonl) can be validated yet.",),
                ),
                code="cli.unsupported.validate",
            )
        paths.append(name)
    unique = list(dict.fromkeys(paths))
    for name in unique:
        if not os.path.isfile(name):
            raise CliUsageError(f"agentprov validate: {safe_text(name, 120)!r} is not a file")
    return unique


def _check_options(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    """Usage rules and refusals; returns the file list and the requested tiers."""
    for dest, flag in (("report", "--report"), ("prov_spec", "--prov-spec"), ("sample", "--sample"), ("seed", "--seed")):
        if getattr(args, dest) is not None:
            raise UnsupportedCapability(
                f"{flag} applies to corpus mode (--corpus DIR); file mode does not implement it",
                refusal=Refusal(
                    id=flag,
                    mode="validate",
                    status=f"{flag} applies to corpus mode only",
                    lines=("Reports, PROV specs and sampling apply to --corpus DIR; file mode validates AER files.",),
                ),
                code="cli.unsupported.validate",
            )
    if not args.files and not args.aer:
        raise CliUsageError("agentprov validate: give FILE..., --aer PATH or --corpus DIR")
    tiers = list(TIERS if args.release else DEFAULT_TIERS)
    if args.tiers is not None:
        tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]
        unknown = [t for t in tiers if t not in TIERS]
        if unknown or not tiers:
            raise CliUsageError(
                f"agentprov validate: --tiers takes a comma list from {', '.join(TIERS)}"
                + (f"; unknown: {', '.join(safe_text(t, 20) for t in unknown)}" if unknown else "")
            )
    if args.store is not None and not os.path.isdir(args.store):
        raise CliUsageError("agentprov validate: --store is not a directory")
    return _classify(args), tiers


def run_card(args: argparse.Namespace) -> CommandResult:
    """``validate --card CARD.md`` (N.2.5(7); H.9(3)-(5)): the card lint of the one claims library
    (``adapters/registry/claims.py``): front matter mode, no digit outside a placeholder, registered claims, the text rules
    (agnosticism term, unqualified "reproducible", scope words, coverage phrase). Read-only; exit 0 or 1."""
    from agentprov.adapters.registry.claims import lint_card

    if args.files or args.aer or args.corpus is not None:
        raise CliUsageError("agentprov validate: --card lints one card; give no FILE, --aer or --corpus with it")
    path = Path(args.card)
    try:
        text = path.read_bytes().decode("utf-8")
    except OSError:
        raise CliUsageError(f"agentprov validate: --card {safe_text(args.card, 120)!r} cannot be read") from None
    except UnicodeDecodeError:
        raise CliUsageError("agentprov validate: --card is not UTF-8") from None
    result = CommandResult(dry_run=bool(args.dry_run))
    violations = lint_card(text, location=path.name)
    for violation in violations:
        result.issues_by_code[violation.nc_id] = result.issues_by_code.get(violation.nc_id, 0) + 1
        result.failures.append({"subject": {"path": safe_text(violation.location, 200)}, "stage": "card",
                                "code": f"card.{violation.nc_id}", "detail": safe_text(violation.detail, 300)})
        result.error(f"{safe_text(violation.location, 200)}: {violation.nc_id}: {safe_text(violation.detail, 300)}")
    result.counters = {"cards": 1, "violations": len(violations)}
    result.exit_code = 1 if violations else 0
    result.info(f"card {safe_text(path.name, 120)}: " + ("passed" if not violations else f"{len(violations)} violation(s)"))
    return result


def run_validate(ctx: Context) -> CommandResult:
    args = ctx.args
    if args.card is not None:
        return run_card(args)
    if args.corpus is not None:
        return run_corpus(ctx)
    files, tiers = _check_options(args)
    strict = bool(args.strict or args.release)
    mode = "release" if args.release else "dev"
    store = open_store(args.store) if args.store else None
    progress = ctx.progress
    result = CommandResult(dry_run=bool(args.dry_run))
    not_run = [t for t in tiers if t not in FILE_TIERS]
    counters = dict.fromkeys(
        ("files", "passed", "passed_with_skips", "failed", "records", "errors", "warnings", "checks_skipped"), 0
    )
    progress.emit(
        ProgressEvent(
            "start",
            total=len(files),
            fields={"command": "validate", "plan": f"tier aer, {mode} mode", "workers": 1},
        )
    )
    for tier in not_run:
        result.notices.append(f"tier {tier} is not implemented in this build and was not run (skipped, not passed)")
    if "aer" not in tiers:
        result.notices.append("the aer tier was not requested: nothing was validated")
    skipped_everywhere: set[str] = set()
    for path in files if "aer" in tiers else []:
        shown = safe_text(path, 200)
        progress.emit(ProgressEvent("unit_start", unit=shown))
        started = time.monotonic()
        counters["files"] += 1
        try:
            report = _validate_file(path, store=store, mode=mode)
        except IngestError as exc:
            code, detail = exc.code, exc.reason
        except OSError as exc:
            code, detail = "validate.read.error", exc.strerror or type(exc).__name__
        else:
            _tally(result, counters, shown, report, strict)
            skipped_everywhere.update(report.skipped)
            status = "failed" if not report.ok else "passed_with_skips" if report.skipped else "passed"
            progress.emit(
                ProgressEvent("step", unit=shown, stage="aer", duration_s=time.monotonic() - started,
                              fields={"records": report.n_records, "mode": report.mode})
            )
            progress.emit(
                ProgressEvent("unit_done", unit=shown, status=status, duration_s=time.monotonic() - started,
                              codes=tuple(dict.fromkeys(f.code for f in report.errors)))
            )
            continue
        counters["failed"] += 1
        counters["errors"] += 1
        result.issues_by_code[code] = result.issues_by_code.get(code, 0) + 1
        result.failures.append(
            {"subject": {"path": safe_text(path, 300)}, "stage": "read", "code": code, "detail": safe_text(detail, 300)}
        )
        result.error(f"{shown}: cannot be read: {code}: {safe_text(detail, 200)}")
        progress.emit(
            ProgressEvent("unit_done", unit=shown, status="failed", duration_s=time.monotonic() - started, codes=(code,))
        )
    counters["checks_skipped"] = len(skipped_everywhere) + len(not_run)
    for label in sorted(skipped_everywhere):
        result.notices.append(f"skipped: {safe_text(label, 200)}")
    if strict and (not_run or skipped_everywhere):
        for label in [*(f"tier {t} not implemented" for t in not_run), *sorted(skipped_everywhere)]:
            result.failures.append(
                {"subject": {"path": "(run)"}, "stage": "strict", "code": "validate.check.skipped", "detail": safe_text(label, 200)}
            )
            result.issues_by_code["validate.check.skipped"] = result.issues_by_code.get("validate.check.skipped", 0) + 1
    result.counters = counters
    failed = counters["failed"] > 0 or (strict and bool(not_run or skipped_everywhere))
    result.exit_code = 1 if failed else 0
    summary = (
        f"validated {counters['files']} file(s) in {mode} mode: {counters['passed']} passed, "
        f"{counters['passed_with_skips']} passed with skipped checks, {counters['failed']} failed"
    )
    result.info(summary)
    return result


def _tally(result: CommandResult, counters: dict[str, int], shown: str, report: ValidationReport, strict: bool) -> None:
    counters["records"] += report.n_records
    counters["errors"] += len(report.errors)
    counters["warnings"] += len(report.warnings)
    for finding in report.findings:
        result.issues_by_code[finding.code] = result.issues_by_code.get(finding.code, 0) + 1
    for finding in report.errors:
        where = "" if finding.line is None else f"line {finding.line + 1} "
        result.failures.append(
            {
                "subject": {"path": shown},
                "stage": "aer",
                "code": finding.code,
                "detail": safe_text(f"{where}{finding.pointer or '/'} {finding.invariant} {finding.detail}".strip(), 300),
            }
        )
    if not report.ok:
        counters["failed"] += 1
        result.error(f"{shown}: FAILED, {len(report.errors)} error(s): " + ", ".join(sorted({f.code for f in report.errors})[:6]))
    elif report.skipped:
        counters["passed_with_skips"] += 1
        result.info(f"{shown}: passed; {len(report.skipped)} check(s) skipped")
    else:
        counters["passed"] += 1
        result.info(f"{shown}: passed")


# --------------------------------------------------------------------------------------------------------------
# Corpus mode (phase 11, U4)
# --------------------------------------------------------------------------------------------------------------


class ReportInsideCorpusError(AgentProvError):
    """``--report`` names a path inside the corpus (N.1.9 G2: validation never writes into a corpus; exit 4)."""

    code = "validate.report.inside_corpus"
    exit_code = 4


def _corpus_tiers(args: argparse.Namespace) -> list[str]:
    tiers = list(TIERS if args.release else DEFAULT_TIERS)
    if args.tiers is not None:
        tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]
        unknown = [t for t in tiers if t not in TIERS]
        if unknown or not tiers:
            raise CliUsageError(f"agentprov validate: --tiers takes a comma list from {', '.join(TIERS)}"
                                + (f"; unknown: {', '.join(safe_text(t, 20) for t in unknown)}" if unknown else ""))
    return list(dict.fromkeys(tiers))


def _report_path(args: argparse.Namespace, root: Path) -> Path | None:
    if args.report is None or args.report == "-":
        return None
    target = Path(os.path.abspath(args.report))
    real_root = Path(os.path.realpath(root))
    final_root = real_root.with_name(real_root.name.removesuffix(".partial"))
    real_target = Path(os.path.realpath(target.parent)) / target.name
    for tree in (real_root, final_root, final_root.with_name(final_root.name + ".partial")):
        if real_target == tree or real_target.is_relative_to(tree):
            raise ReportInsideCorpusError("--report must lie outside the corpus: validation never writes into a corpus "
                                          "(N.1.9 G2)")
    if not target.parent.is_dir():
        raise CliUsageError(f"agentprov validate: the directory of --report {safe_text(args.report, 120)!r} does not exist")
    return target


#: The setting that caps the tier-4 round-trip cache (D-894): GiB, read by every command that uses the cache. Unset: the
#: cache's own default (2 GiB). The cap bounds the eviction after a run; it never changes an outcome (a hint is re-checked).
CACHE_CAP_SETTING: Final = "compute.validation_cache_gib"


def validation_cache(ctx: Context, *, audit: bool = False) -> Any:
    """The tier-4 round-trip cache of a corpus command (D-550): ``None`` with ``--no-validation-cache``; in ``audit``
    mode (``--release``) it never serves an entry, only compares the ones it finds with fresh round trips. Its size cap
    is the ``compute.validation_cache_gib`` setting when set (D-894)."""
    if getattr(ctx.args, "no_validation_cache", False):
        return None
    from agentprov import settings
    from agentprov.validate.cache import DiskCache, default_root

    root = default_root(ctx.env)
    cap = settings.get(CACHE_CAP_SETTING, home=root.parents[1])  # D-894: $AGENTPROV_HOME/settings.json
    if isinstance(cap, int | float) and not isinstance(cap, bool):
        return DiskCache(root, audit=audit, max_bytes=int(cap * 1024**3))
    return DiskCache(root, audit=audit)


def finish_validation_cache(result: CommandResult, cache: Any) -> None:
    """Bound the cache's size after a run that wrote to it, and report its counters as a message (diagnostics only:
    never in a report, a row or a digest). An audit mismatch is an error message: an entry disagreed with a fresh round
    trip (it was replaced; the run's outcomes are the fresh ones)."""
    if cache is None:
        return
    stats = cache.stats
    if stats.stored:
        cache.evict()
    counts = ", ".join(f"{k} {v}" for k, v in stats.as_json().items() if v)
    result.info(f"tier-4 round-trip cache{' (audit)' if cache.audit else ''}: {counts or 'unused'}")
    if stats.audit_mismatch:
        result.error(f"tier-4 round-trip cache: {stats.audit_mismatch} entr(y/ies) disagreed with a fresh round trip "
                     "and were replaced (the run used the fresh outcomes)")


def run_corpus(ctx: Context) -> CommandResult:
    """``validate --corpus DIR`` (see the module docstring)."""
    import json

    from agentprov.corpus.integrity import root_digest
    from agentprov.corpus.reader import CorpusReader
    from agentprov.corpus.validation import validate_corpus
    from agentprov.io.atomic import atomic_write_bytes

    args = ctx.args
    if args.files or args.aer:
        raise CliUsageError("agentprov validate: --corpus validates a corpus; give no FILE or --aer with it")
    if args.store is not None:
        raise CliUsageError("agentprov validate: --store applies to file mode; corpus mode reads the corpus's raw store")
    if args.prov_spec is not None and args.prov_spec != "agentprov-prov/0.1":
        raise UnsupportedCapability(
            f"--prov-spec {safe_text(args.prov_spec, 60)}: corpus mode validates agentprov-prov/0.1 only",
            refusal=Refusal(id="--prov-spec", mode="validate", status="only agentprov-prov/0.1 is validated in corpus mode",
                            lines=("The adprov-v2.3-compat graphs are a regression oracle; migration gate B compares them.",)),
            code="cli.unsupported.validate")
    if (args.sample is None) != (args.seed is None):
        raise CliUsageError("agentprov validate: --sample N and --seed S go together (N.1.7)")
    if args.report == "-" and args.json:  # CC-23: stdout carries exactly one JSON document
        raise CliUsageError("agentprov validate: --report - and --json both write to stdout; write the summary with "
                            "--summary-json PATH, or the report with --report PATH")
    if args.sample is not None and args.release:
        raise CliUsageError("agentprov validate: --sample is forbidden with --release (N.2.5(1))")
    tiers = _corpus_tiers(args)
    strict = bool(args.strict or args.release)
    mode = "release" if strict else "dev"
    reader = CorpusReader.open(args.corpus)
    report_path = _report_path(args, reader.root)
    manifest = reader.manifest() or {}
    run = [t for t in tiers if t in IMPLEMENTED_TIERS]
    not_run = [t for t in tiers if t not in IMPLEMENTED_TIERS]
    result = CommandResult(dry_run=bool(args.dry_run))
    sources = [str(s.get("source_id")) for s in manifest.get("sources") or () if isinstance(s, dict)]
    skipped: list[str] = []
    for tier in not_run:
        if tier == "regression" and "adprov-v1" not in sources:
            result.notices.append("tier regression: not applicable (it is the v1 -> AER -> v1 round trip of adprov-v1 "
                                  "corpora)")
            continue
        skipped.append(tier)
        result.notices.append(f"tier {tier} is not implemented in this build and was not run (skipped, not passed)")
    outcome = None
    cache = validation_cache(ctx, audit=bool(args.release)) if run else None
    if run:
        outcome = validate_corpus(reader, tiers=run, mode=mode, sample=args.sample, seed=args.seed,
                                  progress=ctx.progress, jobs=None if args.in_process else args.jobs, cache=cache,
                                  limits=_validate_limits(manifest))
        finish_validation_cache(result, cache)
    counters = dict(outcome.counters) if outcome is not None else {"executions": 0}
    counters["tiers_run"] = len(run)
    counters["checks_skipped"] = len(skipped)
    result.counters = counters
    content = manifest.get("content_digest") if reader.sealed else None
    identity = {"content_digest": content if isinstance(content, str) else None,
                "corpus_id": str(manifest.get("corpus_id") or ""), "state": reader.state,
                "root_digest": root_digest(reader.root) if reader.sealed else None}
    result.corpus = {"content_digest": identity["content_digest"], "corpus_id": identity["corpus_id"],
                     "root": redact_personal(str(reader.root)), "state": reader.state}
    if outcome is not None:
        result.notices.extend(outcome.notices)
        if outcome.counters.get("rules_drift"):  # D-460: one per drifted catalogue, besides the rows it gates
            result.issues_by_code["aer.rules.drift"] = int(outcome.counters["rules_drift"])
        for failure in outcome.failures:
            code = str(failure["code"])
            result.issues_by_code[code] = result.issues_by_code.get(code, 0) + 1
            checks = ", ".join(str(c) for c in failure["checks"][:12])
            result.failures.append({"subject": {"ex": str(failure["ex"])}, "stage": "validate", "code": code,
                                    "detail": safe_text(f"checks: {checks}" if checks else "the stored row differs", 300)})
    if strict and skipped:
        for tier in skipped:
            result.failures.append({"subject": {"path": "(run)"}, "stage": "strict", "code": "validate.check.skipped",
                                    "detail": f"tier {tier} not implemented"})
            result.issues_by_code["validate.check.skipped"] = result.issues_by_code.get("validate.check.skipped", 0) + 1
    result.exit_code = 1 if (outcome is not None and not outcome.ok) or (strict and skipped) else 0
    if outcome is not None:
        document = outcome.report(identity)
        document["skipped_tiers"] = skipped
        data = (json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        if args.report == "-":
            result.payload = data
        elif report_path is not None:
            if args.dry_run:
                result.notices.append("--dry-run: the report was not written")
            else:
                atomic_write_bytes(report_path, data)
        pct = outcome.validation.get("linkage_resolved_pct")
        shown = "n/a" if not isinstance(pct, dict) else f"{pct.get('$dec')}%"
        result.info(f"validated {counters.get('executions', 0)} execution(s) of {safe_text(identity['corpus_id'], 80)} "
                    f"({reader.state}) in {mode} mode, tiers {','.join(run)}: {counters.get('passed', 0)} passed, "
                    f"{counters.get('failed', 0)} failed; linkage resolved {counters.get('linkage_resolved', 0)}/"
                    f"{counters.get('linkage_applicable', 0)} ({shown}); stored results reproduced "
                    f"{counters.get('results_reproduced', 0)}, differ {counters.get('results_differ', 0)}"
                    + (f"; {_skipped_text(skipped, strict)}" if skipped else ""))
        result.notices.append(f"linkage_resolved_pct {shown} (claim c1-linkage)")
    elif skipped:
        result.info(f"validated nothing of {safe_text(identity['corpus_id'], 80)} ({reader.state}): "
                    f"{_skipped_text(skipped, strict)}")
    return result


def _skipped_text(skipped: list[str], strict: bool) -> str:
    """The summary's account of the requested tiers that did not run (F-3): named, with the reason, as skipped and not
    passed; under ``--strict`` and ``--release`` a skipped tier fails the run (N.2.5(1))."""
    text = f"skipped, not passed: {', '.join(f'tier {t} (not implemented in this build)' for t in skipped)}"
    return text + ("; a skipped tier fails --strict and --release (exit 1)" if strict else "")
