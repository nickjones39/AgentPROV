"""``agentprov verify``: corpus integrity at the levels of HL H.5.5 (MN N.2.6; D8 tier 5; DECISIONS D-38, D-39).

``verify --corpus PATH [--level checksums|chain|rederive] [--root-digest sha256:... ...] [--against-pins
[--allow-network] [--cache-dir DIR]] [--sample N --seed S] [--release] [--jobs N] [--in-process]``

``PATH`` is a corpus (sealed, working or ``.partial``; N.1.5) read in **tree mode**, a deposit directory (it holds
``DEPOSIT-MANIFEST.json``) or a lone ``<corpus_id>-v<version>.meta.zip`` read in **archive mode**, extraction-free
(:mod:`agentprov.release.verify`; archive mode offers ``checksums`` and ``chain``, ``rederive`` exits 5). The command is
read-only; ``rederive`` derives into a private temporary tree that is removed afterwards.

* ``--root-digest`` (D-39, repeatable): a root digest published outside the corpus (tag annotation, paper, deposit
  record); required under ``--release`` in tree mode and in archive mode (D-620: a deposit manifest anchors nothing).
* ``--against-pins`` compares every ``git`` origin with the in-package profile pins (blob id recomputed from the bytes;
  the pinned tree listing from the fetch cache, or fetched with ``--allow-network``; ``raw.origin.blob_mismatch``).
* ``--sample N --seed S``: a seeded uniform sample of the executions for the per-execution checks and ``rederive``
  (N.1.7); forbidden with ``--release``.
* ``--release``: ``unverified`` and ``tombstoned`` findings fail (exit 1); ``rederive`` and archive mode refuse to run
  below CPython 3.14.8 (exit 3, AD-16).

Exit codes: 0 every requested check passed (in dev mode, ``unverified`` findings are reported but do not fail); 1 a check
failed; 2 usage; 3 interpreter guard; 5 ``rederive`` in archive mode. The summary (``--json``) lists every finding as a
failure entry ``{subject, stage: "verify.<level>", code, detail}``.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentprov.cli.common import CliUsageError, CommandResult, Context, bounded_int, redact_personal, safe_text
from agentprov.progress import ProgressEvent

__all__ = ["import_hooks", "register", "run_verify"]

_SHOWN = 20


def _non_negative(text: str) -> int:
    value = bounded_int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "verify",
        parents=[shared],
        help="verify a corpus or a deposit: checksums, the raw -> AER -> SEM -> PROV digest chain, or a re-derivation",
        description="Verify corpus integrity (N.2.6; H.5.5) read-only: a corpus tree, a deposit directory or a lone meta "
        "archive (archive mode, never extracted). Levels: checksums (closed world), chain (the default: manifest, "
        "digests, index, register and counts, AER seals, raw objects and member CRC-32s, SEM/PROV inputs, facets, "
        "catalogue authority), rederive (chain plus a byte-identical re-derivation from the stored raw objects).",
        allow_abbrev=False,
    )
    p.set_defaults(command="verify", handler=run_verify, feedback=True)
    p.add_argument("--corpus", required=True, metavar="PATH", help="a corpus directory, a deposit directory or a .meta.zip")
    p.add_argument("--level", choices=("checksums", "chain", "rederive"), help="verification level (default chain)")
    p.add_argument("--root-digest", action="append", default=[], metavar="sha256:HEX",
                   help="a root digest published outside the corpus (D-39; repeatable; with --release required, and for a "
                        "deposit one per corpus; D-620, D-641)")
    p.add_argument("--against-pins", action="store_true", help="compare every git origin with the in-package profile pins")
    p.add_argument("--allow-network", action="store_true", help="--against-pins: fetch a pinned tree listing not in the cache")
    p.add_argument("--cache-dir", metavar="DIR", help="--against-pins: the fetch cache (default $AGENTPROV_HOME/cache)")
    p.add_argument("--sample", type=_non_negative, metavar="N", help="check a seeded sample of N executions (N.1.7)")
    p.add_argument("--seed", metavar="S", help="the sampling seed (with --sample)")
    p.add_argument("--release", action="store_true", help="release mode: unverified fails; no sampling; needs --root-digest")
    p.add_argument("--jobs", type=_non_negative, default=0, metavar="N", help="rederive: worker processes (0 = host default)")
    p.add_argument("--in-process", action="store_true", help="rederive: run the T1 jobs in this process (debugging only)")
    p.add_argument("--no-validation-cache", action="store_true",
                   help="rederive: always run the tier-4 PROV-O round trip; neither read nor write the round-trip cache "
                   "(D-550). With --release the cache is never read; it is audited")


# ------------------------------------------------------------------------------------------------ injection
def import_hooks() -> Any:
    """The import pipeline a ``rederive`` re-map needs (``adapters.runner``, L6), injected into ``corpus.verify``."""
    from agentprov.stats.source import import_hooks as hooks

    return hooks()


def _pin_listing(ctx: Context, args: argparse.Namespace, manifest: Mapping[str, Any] | None) -> Any:
    """``(repo, commit) -> {path: blob id} | None`` from the fetch cache (the network only with ``--allow-network``)."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    fetcher = Fetcher(resolve_cache_dir(args.cache_dir, ctx.env), allow_network=bool(args.allow_network),
                      consent="--allow-network", env=ctx.env)
    pins: list[tuple[dict[str, Any], str | None]] = []
    for source in (manifest or {}).get("sources") or ():
        profile = source.get("profile") if isinstance(source, Mapping) else None
        if not isinstance(profile, Mapping) or not isinstance(profile.get("id"), str):
            continue
        try:
            version = profile.get("version")
            loaded = load_profile(str(profile["id"]), version if isinstance(version, int) and not isinstance(version, bool) else None)
        except Exception:  # noqa: BLE001 - an unshipped profile is reported by the authority check
            continue
        canonical = loaded.data.get("source", {}).get("canonical_repo")
        for pin in loaded.data.get("source", {}).get("pins", ()):
            if isinstance(pin, Mapping) and pin.get("kind") == "git":
                pins.append((dict(pin), canonical if isinstance(canonical, str) else None))

    def listing(repo: str, commit: str) -> Mapping[str, str] | None:
        for pin, canonical in pins:
            if pin.get("commit") != commit:
                continue
            try:
                recipe = Recipe.from_pin({k: v for k, v in pin.items() if k not in ("tree", "tree_sha1")},
                                         canonical_repo=canonical)
                if recipe.repo != repo:
                    continue
                if not fetcher.plan(recipe).cached:
                    if not args.allow_network:
                        return None
                    fetcher.fetch(recipe)
                entries, _skipped = fetcher.git_tree(recipe)
            except Exception:  # noqa: BLE001 - any fetch or git failure leaves the listing unverified, never passed
                return None
            return {e.path: e.oid for e in entries if e.is_blob}
        return None

    return listing


# ------------------------------------------------------------------------------------------------ command
def _check_options(args: argparse.Namespace) -> None:
    if (args.sample is None) != (args.seed is None):
        raise CliUsageError("agentprov verify: --sample N and --seed S go together (N.1.7)")
    if args.sample is not None and args.release:
        raise CliUsageError("agentprov verify: --sample is forbidden with --release (N.1.7; H.8.5)")
    if (args.allow_network or args.cache_dir) and not args.against_pins:
        raise CliUsageError("agentprov verify: --allow-network and --cache-dir go with --against-pins")
    for digest in args.root_digest:
        if not (isinstance(digest, str) and len(digest) == 71 and digest.startswith("sha256:")
                and all(c in "0123456789abcdef" for c in digest[7:])):
            raise CliUsageError("agentprov verify: --root-digest is sha256:<64 lower-case hex>")


def run_verify(ctx: Context) -> CommandResult:
    from agentprov.release.verify import is_archive_input

    args = ctx.args
    _check_options(args)
    kind = is_archive_input(args.corpus)
    level = args.level or "chain"
    started = time.monotonic()
    # N.1.14: the level is the one unit a progress reader sees start and finish (per-file events: corpus.verify)
    ctx.progress.emit(ProgressEvent("start", total=1, fields={"command": "verify", "plan": f"level {level}",
                                                              "mode": "archive" if kind is not None else "tree"}))
    ctx.progress.emit(ProgressEvent("stage", stage="verify", fields={"phase": "begin", "level": level}))
    ctx.progress.emit(ProgressEvent("unit_start", unit=f"verify.{level}"))
    result = _archive(ctx, args, kind) if kind is not None else _tree(ctx, args)
    status = "ok" if result.exit_code == 0 else "failed"
    elapsed = time.monotonic() - started
    ctx.progress.emit(ProgressEvent("unit_done", unit=f"verify.{level}", status=status, duration_s=elapsed))
    ctx.progress.emit(ProgressEvent("stage", stage="verify", duration_s=elapsed, fields={
        "phase": "end", "level": level, "failed": result.counters.get("failed", 0) if result.counters else 0}))
    return result


def _tree(ctx: Context, args: argparse.Namespace) -> CommandResult:
    from agentprov.corpus.reader import CorpusReader
    from agentprov.corpus.verify import VerifyUsageError, verify_corpus

    level = args.level or "chain"
    if args.release and not args.root_digest:
        raise CliUsageError("agentprov verify --release: give --root-digest sha256:... (the root digest published outside "
                            "the corpus; D-39)")
    reader = CorpusReader.open(args.corpus)
    if args.in_process and args.release:
        raise CliUsageError("agentprov verify: --in-process is refused with --release (G.4.9)")
    listing = _pin_listing(ctx, args, reader.manifest()) if args.against_pins else None
    from agentprov.cli.checks import finish_validation_cache, validation_cache

    cache = validation_cache(ctx, audit=bool(args.release)) if level == "rederive" else None
    try:
        report = verify_corpus(
            level=level, reader=reader, jobs=args.jobs, sample=args.sample, seed=args.seed, release=bool(args.release),
            root_digests=tuple(args.root_digest), against_pins=bool(args.against_pins), pin_listing=listing,
            import_hooks=import_hooks() if level == "rederive" else None, in_process=bool(args.in_process),
            progress=ctx.progress, validation_cache=cache,
        )  # fmt: skip
    except VerifyUsageError as exc:
        raise CliUsageError(f"agentprov verify: {exc}") from None
    result = CommandResult()
    finish_validation_cache(result, cache)
    result.corpus = {"content_digest": report.content_digest, "corpus_id": report.corpus_id or "",
                     "root": redact_personal(str(reader.root)), "state": reader.state}
    if args.in_process and level == "rederive":
        result.notices.append("--in-process: the T1 jobs ran in the CLI process (debugging only; G.4.9)")
    _fill(result, [report], report.findings, report.counters, report.notices, level, bool(args.release))
    _check_conformance(result, reader.manifest())
    if not reader.sealed:
        result.notices.append("a working tree: checksums.sha256 is written at sealing, so the checksums level is unverified")
    if report.root_digest is not None:
        result.output(f"root digest {report.root_digest}")
    return result


def _check_conformance(result: CommandResult, manifest: Mapping[str, Any] | None) -> None:
    """G2c-5 (D-432): a corpus that skipped the W3C PROV conformance check is unvalidated, so verify fails it."""
    from agentprov.corpus.conformance import UNVALIDATED_CODE, conformance_skipped

    if not conformance_skipped(manifest):
        return
    result.failures.append({"subject": {"corpus": "corpus.json"}, "stage": "verify.validation", "code": UNVALIDATED_CODE,
                            "detail": "failed: the W3C PROV conformance check (tier 4) was skipped; run "
                                      "a full 'agentprov recompute --out NEW --stages sem,prov,validation'"})
    result.issues_by_code[UNVALIDATED_CODE] = result.issues_by_code.get(UNVALIDATED_CODE, 0) + 1
    result.error("  failed: the corpus is unvalidated: --skip-prov-conformance was used; a full "
                 "recompute writes a validated corpus")
    result.exit_code = 1


def _archive(ctx: Context, args: argparse.Namespace, kind: str) -> CommandResult:
    from agentprov.corpus.verify import VerifyUsageError
    from agentprov.release.verify import verify_deposit

    if args.against_pins or args.sample is not None or args.in_process:
        raise CliUsageError("agentprov verify: --against-pins, --sample and --in-process apply to a corpus tree, not to "
                            "archive mode")
    level = args.level or "chain"
    try:
        outcome = verify_deposit(args.corpus, level=level, release=bool(args.release), root_digests=tuple(args.root_digest))
    except VerifyUsageError as exc:
        raise CliUsageError(f"agentprov verify: {exc}") from None
    result = CommandResult()
    counters = dict(outcome.counters)
    for report in outcome.corpora:
        for key, value in report.counters.items():
            counters[key] = counters.get(key, 0) + value
    notices = list(outcome.notices) + [n for r in outcome.corpora for n in r.notices]
    findings = outcome.all_findings()
    counters["corpora"] = len(outcome.corpora)
    counters["findings"] = len(findings)
    counters["failed"] = sum(1 for f in findings if f.status == "failed")
    counters["unverified"] = sum(1 for f in findings if f.status == "unverified")
    counters["tombstoned"] = sum(1 for f in findings if f.status == "tombstoned")
    if len(outcome.corpora) == 1:
        only = outcome.corpora[0]
        result.corpus = {"content_digest": only.content_digest, "corpus_id": only.corpus_id or "",
                         "root": redact_personal(str(Path(args.corpus))), "state": "sealed"}
    _fill(result, outcome.corpora, findings, counters, notices, level, bool(args.release), passed=outcome.passed())
    result.notices.insert(0, f"archive mode ({'deposit directory' if kind == 'deposit' else 'lone meta archive'}): read "
                             "without extraction (H.5.5; D-38)")
    for report in outcome.corpora:
        if report.root_digest is not None:
            result.output(f"{safe_text(report.corpus_id or '', 120)}-v{safe_text(report.corpus_version or '', 40)}: "
                          f"root digest {report.root_digest}")
    return result


def _fill(result: CommandResult, reports: list[Any], findings: list[Any], counters: Mapping[str, int],
          notices: list[str], level: str, release: bool, *, passed: bool | None = None) -> None:
    result.counters = {k: int(v) for k, v in sorted(counters.items())}
    for finding in findings:
        result.issues_by_code[finding.code] = result.issues_by_code.get(finding.code, 0) + 1
        subject = {k: safe_text(str(v), 200) for k, v in dict(finding.subject).items()}
        result.failures.append({"subject": subject, "stage": f"verify.{finding.level}", "code": finding.code,
                                "detail": safe_text(f"{finding.status}: {finding.detail}", 300)})
    result.notices.extend(safe_text(n, 400) for n in notices)
    if passed is None:
        passed = all(r.passed() for r in reports)
    result.exit_code = 0 if passed else 1
    failed = sum(1 for f in findings if f.status == "failed")
    open_ = len(findings) - failed
    verdict = "passed" if passed and not findings else "passed with unverified checks" if passed else "FAILED"
    result.info(f"agentprov verify: level {level}{' (release mode)' if release else ''}: {verdict}; {failed} failed, "
                f"{open_} unverified or tombstoned")
    for finding in findings[:_SHOWN]:
        where = next(iter(dict(finding.subject).values()), "")
        result.error(f"  {finding.status}: {finding.code} at {safe_text(str(where), 120)}: {safe_text(finding.detail, 200)}")
    if len(findings) > _SHOWN:
        result.error(f"  ... {len(findings) - _SHOWN} more (see --json)")
