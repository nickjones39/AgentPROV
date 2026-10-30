"""``agentprov derive`` and ``agentprov recompute``: re-derivation into a new corpus version (MN N.2.3, N.2.4; HL H.8;
DECISIONS D-30, D-32, D-37, D-43).

Both read ``--corpus SRC`` (sealed, working or ``.partial``) read-only and write a new working corpus ``NEW.partial``
(``--out NEW``); neither ever writes in place (PLAN rule 4). The engine is :mod:`agentprov.corpus.derive`; this module
resolves the options, applies the guards (G1-G3, G6, G9), injects the profile and catalogue lookups that live in
``adapters`` (M.5.2(1)) and, for a re-map (``--stages expand,aer``), hands a
:class:`~agentprov.corpus.rawtree.StoredRawTree` over the source's own raw store to the public
:func:`agentprov.adapters.runner.importer.import_source` (no network).

* ``recompute --corpus SRC (--out NEW | --dry-run) [--stages ...] [--show-diff N] [--strict] [--link-raw]`` re-runs the
  stages (default: every stage the source has, from raw), compares bytes per execution and exits 1 on an unexplained
  change or a failed execution (``--strict``: also on ``unverified``). ``--dry-run`` builds into a private temporary
  directory that is removed afterwards, so nothing is written next to the source or the output.
* ``derive --corpus SRC --out NEW [--stages sem,prov,validation,views] [--prov-spec adprov-v2.3-compat]
  [--views transcript-v1] [--semantics-profile ID] [--trig DIR]`` adds missing layers; present layers are carried (and
  refused, exit 4, when the package derives them at another version). ``--trig DIR`` writes PROV-O TriG outside every
  corpus (from ``NEW`` with ``--out``, else from ``SRC``, which may then be sealed).

Writing or loading ``adprov-v2.3-compat`` output prints the compat notice (R-55; Q.30).
"""

from __future__ import annotations

import argparse
import os
import shutil
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

from agentprov.cli import gitinfo
from agentprov.cli.common import CliUsageError, CommandResult, Context, bounded_int, redact_personal, safe_text
from agentprov.corpus.scratch import scratch_tree
from agentprov.errors import AgentProvError

__all__ = ["register", "run_derive", "run_recompute"]

SPEC_ID: Final = "agentprov-prov/0.1"
COMPAT_SPEC: Final = "adprov-v2.3-compat"
_SHOWN_CHANGES: Final = 20


def _non_negative(text: str) -> int:
    value = bounded_int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def _stage_list(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    d = sub.add_parser(
        "derive", parents=[shared], allow_abbrev=False,
        help="add missing derived layers (SEM, PROV, validation, views, compat, TriG) as a new corpus version",
        description="Add missing derived layers of SRC into a new working corpus NEW.partial (N.2.3); SRC is never written.",
    )  # fmt: skip
    d.set_defaults(command="derive", handler=run_derive, feedback=True)
    _common(d)
    d.add_argument("--stages", type=_stage_list, metavar="S[,S...]", help="layers to add: sem,prov,validation,views")
    d.add_argument("--views", action="append", default=[], metavar="VIEW", help="add a view (transcript-v1)")
    d.add_argument("--semantics-profile", action="append", default=None, metavar="ID@N",
                   help="semantics profile for an added sem layer (repeatable; default: the source's)")
    d.add_argument("--trig", metavar="DIR", help="write PROV-O TriG (on demand; never part of a corpus) into DIR")

    r = sub.add_parser(
        "recompute", parents=[shared], allow_abbrev=False,
        help="re-derive a corpus from its raw objects or stored AERs and compare bytes (H.8.4)",
        description="Re-run the derivation stages of SRC into NEW.partial (or in memory with --dry-run) and compare.",
    )  # fmt: skip
    r.set_defaults(command="recompute", handler=run_recompute, feedback=True)
    _common(r)
    r.add_argument("--stages", type=_stage_list, metavar="S[,S...]",
                   help="stages to re-run: expand,aer,sem,prov,validation,views (default: every stage the source has)")
    r.add_argument("--show-diff", type=_non_negative, default=0, metavar="N", help="show the first differences of N changed executions")
    r.add_argument("--strict", action="store_true", help="exit 1 when an execution is unverified")


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--corpus", metavar="SRC", help="the source corpus (sealed, working or .partial); read only")
    p.add_argument("--out", metavar="NEW", help="the new corpus directory (written as NEW.partial; must not exist)")
    p.add_argument("--prov-spec", action="append", default=[], metavar="SPEC",
                   help=f"provenance spec ({SPEC_ID}; {COMPAT_SPEC} writes the regression oracle, R-55)")
    p.add_argument("--jobs", type=_non_negative, default=0, metavar="N", help="worker processes (0 = host default)")
    p.add_argument("--in-process", action="store_true", help="debugging only: run the T1 jobs in this process")
    p.add_argument("--link-raw", action="store_true", help="hard-link raw objects into NEW instead of copying them (D-32)")
    p.add_argument("--dry-run", action="store_true", help="derive and compare in a private temporary tree; write nothing")
    p.add_argument("--no-reuse", action="store_true",
                   help="recompute every execution (--out reuses unchanged outputs by default; --dry-run never reuses)")
    p.add_argument("--skip-prov-conformance", action="store_true",
                   help="dev mode only, not advisable: a recomputed validation skips the W3C PROV conformance check "
                        "(tier 4); NEW is marked unvalidated and cannot be sealed (G2c-5)")
    p.add_argument("--no-validation-cache", action="store_true",
                   help="always run the tier-4 PROV-O round trip; neither read nor write $AGENTPROV_HOME/cache/tier4 (D-550)")


# ------------------------------------------------------------------------------------------------ injection
def catalogues() -> Any:
    """The profile and catalogue lookups of the package (``adapters``), injected into ``corpus.derive`` (M.5.2(1))."""
    from agentprov.adapters.profiles import load_profile, worker_caps
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.corpus.derive import Catalogues, SemanticsInfo
    from agentprov.sem.profiles import parse_profile_ref

    def source_profile(profile_id: str, version: int) -> str | None:
        try:
            profile = load_profile(profile_id, version)  # an archived version too (D-31)
        except AgentProvError:
            return None
        return profile.sha256 if profile.version == version else None

    def semantics(ref: str) -> SemanticsInfo | None:
        try:
            profile = load_semantics_profile(*parse_profile_ref(ref))
        except (AgentProvError, ValueError, KeyError):
            return None
        family = str(type(profile).__module__).split(".")[2]
        return SemanticsInfo(ref=f"{profile.id}@{profile.version}", sha256=profile.sha256, rules=dict(profile.rules),
                             family=family)

    def current_profile_version(profile_id: str) -> int | None:
        try:
            return load_profile(profile_id).version
        except AgentProvError:
            return None

    def profile_family(profile_id: str) -> str | None:
        try:
            return load_profile(profile_id).family
        except AgentProvError:
            return None

    def caps(profile_id: str, version: int) -> Mapping[str, int]:  # D-931, D-935
        try:
            return worker_caps(load_profile(profile_id, version))
        except AgentProvError:
            return {}

    def limits(profile_id: str, version: int) -> Mapping[str, Any]:  # D-1001
        try:
            profile = load_profile(profile_id, version)
        except AgentProvError:
            return {}
        if profile.version != version:
            return {}
        return dict(profile.data.get("import", {}).get("limits") or {})

    return Catalogues(source_profile_sha256=source_profile, semantics=semantics,
                      current_profile_version=current_profile_version, profile_family=profile_family,
                      worker_caps=caps, profile_limits=limits)


# ------------------------------------------------------------------------------------------------ guards
def _final_dir(path: str) -> Path:
    given = Path(path)
    if given.name.endswith(".partial"):
        given = given.with_name(given.name[: -len(".partial")])
    return Path(os.path.abspath(given))


def _guard_out(final: Path, reader: Any) -> None:
    from agentprov.corpus.derive import DeriveRefusedError, is_inside
    from agentprov.corpus.layout import assert_writable, partial_dir

    partial = partial_dir(final)
    if os.path.lexists(final):
        raise DeriveRefusedError("--out names a directory that exists; a new corpus version needs a new directory",
                                 code="corpus.derive.out_exists")
    source_final = reader.root.with_name(reader.root.name.removesuffix(".partial"))
    for tree in (reader.root, source_final, partial_dir(source_final)):
        for candidate in (final, partial):
            if is_inside(candidate, tree) or is_inside(tree, candidate):
                raise DeriveRefusedError("--out overlaps the source corpus (G2); choose a directory outside it",
                                         code="corpus.derive.overlap")
    assert_writable(partial)


def _guard_trig(directory: Path, roots: list[Path]) -> None:
    """Refuse a TriG directory that overlaps a corpus tree, the final directory a working tree is sealed into, or a
    directory inside a sealed corpus (G1, G2, G8)."""
    from agentprov.corpus.derive import DeriveRefusedError, is_inside
    from agentprov.corpus.layout import assert_writable, partial_dir

    trees: list[Path] = []
    for root in roots:
        final = root.with_name(root.name.removesuffix(".partial"))
        trees += [root, final, partial_dir(final)]
    for tree in trees:
        if is_inside(directory, tree) or is_inside(tree, directory):
            raise DeriveRefusedError("--trig must lie outside every corpus (G2, G8): TriG is never stored in a corpus",
                                     code="corpus.derive.trig_inside")
    assert_writable(directory)


def _trig_dir(args: argparse.Namespace) -> Path:
    return Path(os.path.abspath(str(args.trig)))


# ------------------------------------------------------------------------------------------------ commands
def run_derive(ctx: Context) -> CommandResult:
    return _run(ctx, "derive")


def run_recompute(ctx: Context) -> CommandResult:
    return _run(ctx, "recompute")


def _check_options(args: argparse.Namespace, command: str) -> None:
    if not args.corpus:
        raise CliUsageError(f"agentprov {command}: --corpus SRC is required")
    if command == "recompute" and bool(args.out) == bool(args.dry_run):
        raise CliUsageError("agentprov recompute: exactly one of --out NEW or --dry-run is required (never in place)")
    if command == "derive":
        if args.out and args.dry_run:
            raise CliUsageError("agentprov derive: --out and --dry-run are mutually exclusive")
        if not args.out and not args.dry_run and not getattr(args, "trig", None):
            raise CliUsageError("agentprov derive: --out NEW is required (derive never writes into the source corpus)")
    for spec in args.prov_spec:
        if spec not in (SPEC_ID, COMPAT_SPEC):
            raise CliUsageError(f"agentprov {command}: unknown --prov-spec {safe_text(spec, 60)!r}; specs: {SPEC_ID}, {COMPAT_SPEC}")


def _filters(recorded: Mapping[str, Any]) -> Any:
    from agentprov.adapters.runner.importer import ImportFilters

    variants = recorded.get("variants")
    chosen = recorded.get("select")
    select: Mapping[str, Any] = chosen if isinstance(chosen, Mapping) else {}
    return ImportFilters(
        include_paths=tuple(str(g) for g in recorded.get("include_paths") or ()),
        variants=None if variants is None else frozenset(str(v) for v in variants),
        select={str(k): frozenset(str(v) for v in values) for k, values in sorted(select.items())},
    )


def _recorded_profile_version(manifest: Mapping[str, Any]) -> int:
    """The source profile version the corpus was imported under (D-323: the version its recorded limits belong to)."""
    profile = ((manifest.get("sources") or [{}])[0] or {}).get("profile") or {}
    version = profile.get("version") if isinstance(profile, Mapping) else None
    return version if isinstance(version, int) and not isinstance(version, bool) else 0


def _limits(overrides: Mapping[str, Any]) -> Any:
    from agentprov.ingest.limits import IngestLimits

    changes = {k: tuple(v) if isinstance(v, list) else v for k, v in overrides.items()}
    return IngestLimits().replace(**changes) if changes else IngestLimits()


def _remap(ctx: Context, derivation: Any, reader: Any, writer: Any) -> None:
    from agentprov.adapters.runner.importer import import_source
    from agentprov.adapters.types import CandidateArtefact
    from agentprov.corpus.derive import batch_for
    from agentprov.io.workers import resolve_worker_count
    from agentprov.corpus.rawtree import StoredRawTree

    # D-202: one tree per recorded snapshot, replayed in import order (a single-snapshot corpus has one)
    trees = [StoredRawTree(reader, snapshot_id=sid, candidate_type=CandidateArtefact)
             for sid in derivation.snapshot_ids()] or [StoredRawTree(reader, candidate_type=CandidateArtefact)]
    derivation.exclude_absent(trees)  # BF-20, CB-6: inputs absent on purpose are not re-mapped
    register = reader.register()
    unreproducible = [e for tree in trees for e in tree.unreproducible(register)]  # the register collapses repeats
    derivation.prepare(writer, unreproducible=unreproducible)
    plan = derivation.plan
    try:
        for tree in trees:
            arguments = derivation.import_arguments(tree.snapshot_id)
            import_source(
                derivation.source_id(), tree, corpus=writer, filters=_filters(derivation.recorded_selection(tree.snapshot_id)),
                limits=_limits(derivation.recorded_limit_overrides()), workers=plan.jobs,
                limits_recorded_under=_recorded_profile_version(derivation.manifest),
                in_process=plan.in_process, batch_size=plan.batch_size or batch_for(resolve_worker_count(plan.jobs)),
                progress=ctx.progress, **arguments,
            )
    finally:
        derivation.restamp(writer)
    derivation.complete_remap(writer)


def _run(ctx: Context, command: str) -> CommandResult:
    args = ctx.args
    _check_options(args, command)
    from agentprov.corpus.derive import DRIFT_REFUSAL, Derivation, DeriveRefusedError, resolve_plan
    from agentprov.corpus.reader import CorpusReader
    from agentprov.corpus.writer import CorpusWriter

    result = CommandResult(dry_run=bool(args.dry_run))
    reader = CorpusReader.open(args.corpus)
    injected = catalogues()
    trig_only = command == "derive" and not args.out and not args.dry_run
    try:
        plan = resolve_plan(
            reader, command,
            stages=args.stages, prov_specs=args.prov_spec, views=getattr(args, "views", []),
            semantics=getattr(args, "semantics_profile", None), jobs=args.jobs, in_process=bool(args.in_process),
            link_raw=bool(args.link_raw), show_diff=getattr(args, "show_diff", 0), strict=bool(getattr(args, "strict", False)),
            reuse=not (args.no_reuse or args.dry_run),
            catalogues=injected, prov_conformance=not args.skip_prov_conformance,
        )  # fmt: skip
    except ValueError as exc:
        raise CliUsageError(f"agentprov {command}: {exc}") from None
    if args.in_process:
        result.notices.append("--in-process: the T1 jobs ran in the CLI process (debugging only; G.4.9)")
    if args.skip_prov_conformance:
        result.notices.append("--skip-prov-conformance: a recomputed validation did not run the W3C PROV conformance "
                              "check (tier 4); NEW is marked unvalidated (G2c-5)")
    corpus_id = str((reader.manifest() or {}).get("corpus_id") or "")
    if trig_only:
        return _trig(args, reader, None, result, corpus_id)

    tmp: str | None = None
    if args.dry_run:
        tmp = str(scratch_tree(f"agentprov-{command}-", reader.root))  # on the source's filesystem: raw objects link
        final = Path(tmp) / "corpus"
        plan = replace(plan, link_raw=True)  # a private tree removed afterwards: linking changes no source byte
    else:
        final = _final_dir(args.out)
        _guard_out(final, reader)
        if getattr(args, "trig", None):  # before any unit is processed (N.1.3 precedence)
            from agentprov.corpus.layout import partial_dir

            _guard_trig(_trig_dir(args), [reader.root, partial_dir(final)])
    from agentprov.cli.checks import finish_validation_cache, validation_cache

    derivation = Derivation(reader, plan, catalogues=injected, progress=ctx.progress)
    derivation.validation_cache = validation_cache(ctx)
    try:
        derivation.check_inputs()
        if derivation.drift and not args.dry_run:
            built = derivation.built_at()  # D-780: where to recompute it; said only when the source records it
            known = [] if built == "building commit not recorded" else [f"source {built}"]
            raise DeriveRefusedError(DRIFT_REFUSAL + ":\n" + "\n".join([*derivation.drift, *known]),  # one drift per line (RC-8)
                                     code="corpus.derive.version_drift")
        with CorpusWriter(final, limits=reader.limits, release=plan.mode == "release", command=command,
                          break_stale_lock=bool(args.break_stale_lock), build_step=gitinfo.build_step(command)) as writer:
            if plan.remap:
                _remap(ctx, derivation, reader, writer)
            else:
                derivation.prepare(writer)
                derivation.rederive(writer)
            report = derivation.finish(writer)
        partial = writer.partial
        if getattr(args, "trig", None) and not args.dry_run:
            out_reader = CorpusReader(partial, state="working")
            _trig(args, out_reader, reader, result, corpus_id)
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
        finish_validation_cache(result, derivation.validation_cache)
    return _result(result, report, args, command, corpus_id, None if args.dry_run else partial)


def _trig(args: argparse.Namespace, reader: Any, source: Any, result: CommandResult, corpus_id: str) -> CommandResult:
    from agentprov.corpus.derive import export_trig

    directory = _trig_dir(args)
    roots = [reader.root] + ([source.root] if source is not None else [])
    _guard_trig(directory, roots)
    trig = export_trig(reader, directory)
    result.counters.setdefault("trig_written", trig.files)
    result.counters["trig_failed"] = len(trig.failed)
    versions = ", ".join(f"{k} {v}" for k, v in sorted(trig.versions.items()))
    result.notices.append(f"TriG listing {trig.listing_sha256} ({versions}); TriG is not part of the corpus (AD-10 row 3)")
    result.info(f"agentprov derive: {trig.files} TriG file(s) written to {redact_personal(str(directory))}")
    if trig.failed:
        result.exit_code = 1
        for ex in trig.failed[:20]:
            result.error(f"  TriG failed: {ex}")
    if result.corpus is None:
        result.corpus = {"content_digest": None, "corpus_id": corpus_id, "root": redact_personal(str(reader.root)),
                         "state": reader.state}
    return result


def _result(result: CommandResult, report: Any, args: argparse.Namespace, command: str, corpus_id: str,
            partial: Path | None) -> CommandResult:
    from agentprov.ingest.quote import escape_untrusted_line  # one line each: data never starts a line (N.1.13)
    from agentprov.prov.specs import compat_notice

    result.counters = {**result.counters, **report.counters}
    result.issues_by_code = dict(report.issues_by_code)
    result.failures = list(report.failures)
    result.exit_code = max(result.exit_code, report.exit_code)
    if report.compat_written or report.compat_loaded:
        result.notices.append(compat_notice())
    result.notices.extend(report.notices)
    for change in report.corpus_changes:
        how = "explained by a declared version change" if change["explained"] else "UNEXPLAINED"
        result.notices.append(f"{change['file']} differs ({change['removed']} line(s) removed, {change['added']} added): {how}")
    result.corpus = {
        "content_digest": None,
        "corpus_id": corpus_id,
        "root": redact_personal(str(partial)) if partial is not None else "(dry run: private temporary tree, removed)",
        "state": "working",
    }
    c = report.counters
    verb = "would derive" if args.dry_run else "derived"
    result.info(
        f"agentprov {command}: {verb} {c.get('selected', 0)} execution(s); recomputed stages: "
        f"{','.join(report.recomputed) or 'none'}; {c.get('identical', 0)} identical, {c.get('changed_explained', 0)} "
        f"changed (explained), {c.get('unexplained_change', 0)} unexplained, {c.get('failed', 0)} failed, "
        f"{c.get('unverified', 0)} unverified; {c.get('index_refreshed', 0)} index row(s) refreshed"
    )
    if partial is not None:
        result.info(f"agentprov {command}: new working corpus {redact_personal(str(partial))}")
    for change in report.changes[:_SHOWN_CHANGES]:
        if change["class"] != "identical":
            result.error(f"  {change['class']}: {change['ex']} [{', '.join(escape_untrusted_line(o, max_chars=80) for o in change['outputs'])}]")
    for detail in report.details:
        result.output(f"  diff {detail['ex']} {escape_untrusted_line(detail['output'], max_chars=80)} line {detail['line']}:")
        result.output(f"    - {escape_untrusted_line(str(detail['old']), max_chars=300)}")
        result.output(f"    + {escape_untrusted_line(str(detail['new']), max_chars=300)}")
        for line in detail["semantic"]:
            result.output(f"    {escape_untrusted_line(line, max_chars=300)}")
    for notice in result.notices:
        result.info(f"notice: {safe_text(notice, 400)}")
    return result

