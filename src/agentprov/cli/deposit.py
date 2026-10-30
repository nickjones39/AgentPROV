"""``agentprov package --deposit``: build a deposit draft from sealed corpora (MN N.2.11 deposit mode; HL H.10; D-42).

``package --deposit OUT --corpus DIR [--corpus DIR ...] --metadata release.toml --release-date YYYY-MM-DD
[--max-archive-bytes N] [--allow-mixed-licence-classes] [--dry-run]``. The command gathers what the offline builder
cannot (``release/`` runs no subprocess): the producer's git commit and cleanliness, the claims text lint of
:mod:`agentprov.adapters.registry.claims` (M.5.2(1)), the ``verify --level chain`` pre-archive check (H.10.1(3); U4,
:func:`verify_chain`) and the H.1.5(5) guard (the draft holds corpora, so it is outside
every git work tree unless git-ignored). Each corpus's release scan is read from ``<corpus>.release-scan.json`` beside it
(``tools/release_scan.py``, G.9.4). ``package`` is release mode for the interpreter guard (G.3.8).

Exit codes (N.1.3): 0 the draft was written; 1 a corpus failed verification or a generated text failed the lint; 2 usage
(including a malformed ``release.toml``); 3 below CPython 3.14.8; 4 a refusal (unsealed, advisory, ``test_only``,
``withhold``, missing or untriaged scan, mixed licence classes without the flag); 5 a corpus with ``views/``. The
command ends with "nothing has been uploaded or published" (D9).

The index mode (H.10.7; D-941 L-5, D-947): ``package --index OUT --part RECEIPT [--part RECEIPT ...] --corpus DIR
[--corpus DIR ...] --metadata release.toml --release-date YYYY-MM-DD [--dry-run]`` builds the index-only umbrella deposit
of a collection with :func:`agentprov.release.index.build_index`: each ``--part`` is a part record's draft receipt
(``complete``, with a reserved DOI), whose deposit directory lies beside it, and the ``--corpus`` directories are exactly
the sealed corpora those parts hold. Exit codes: 0 written; 1 a corpus check or the lint failed; 2 usage; 3 below CPython
3.14.8; 4 a refusal (a receipt not complete or without a DOI, a part changed since its upload, a corpus in no part or in
two, a digest or licence class that differs from the part's).
"""

from __future__ import annotations

import platform
import re
from datetime import date
from pathlib import Path
from typing import Any

from agentprov.cli.common import CliUsageError, CommandResult, Context, safe_text

__all__ = ["run_deposit", "run_index", "verify_chain"]

NOT_PUBLISHED = "Nothing has been uploaded or published."


def _release_date(text: str | None) -> date:
    if text is None:
        raise CliUsageError("agentprov package --deposit: --release-date YYYY-MM-DD is required (archive timestamps, H.10.4)")
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text) is None:
            raise ValueError(text)
        release_date = date.fromisoformat(text)
    except ValueError:
        raise CliUsageError("agentprov package: --release-date is YYYY-MM-DD") from None
    # ZIP member timestamps end at 2107 (the low end is clamped to 1980 by the builder); refuse before any verification
    if release_date.year > 2107:
        raise CliUsageError("agentprov package --deposit: --release-date is at most 2107-12-31 (ZIP timestamps, H.10.4)")
    return release_date


def _lint(location: str, text: str) -> list[tuple[str, str, str]]:
    from agentprov.adapters.registry.claims import lint_text

    return [(v.nc_id, v.location, v.detail) for v in lint_text(location, text)]


def verify_chain(root: Path) -> Any:
    """The pre-archive verifier injected into the builder (``build_deposit(verify=...)``; H.10.1(3)): ``verify --level
    chain`` in release mode (an unverified or tombstoned finding fails too)."""
    from agentprov.corpus.verify import verify_corpus
    from agentprov.release.builder import CorpusVerification

    report = verify_corpus(root, level="chain")
    detail = ", ".join(f"{code}: {n}" for code, n in report.codes().items())
    return CorpusVerification("chain", report.passed(release=True), detail)


def run_deposit(ctx: Context) -> CommandResult:
    from agentprov.cli.package import _is_ignored, git_facts
    from agentprov.corpus.layout import assert_outside_git_work_tree
    from agentprov.release.builder import DEFAULT_MAX_ARCHIVE_BYTES, DepositProducer, build_deposit
    from agentprov.release.metadata import parse_release_toml
    from agentprov.versions import __version__

    args = ctx.args
    if args.deposit is None:
        raise CliUsageError("agentprov package: --metadata, --max-archive-bytes and --allow-mixed-licence-classes belong to "
                            "the deposit mode (--deposit OUT)")
    if args.metadata is None:
        raise CliUsageError("agentprov package --deposit: --metadata release.toml is required (H.10.2)")
    if args.licence_file or args.spec is not None or args.corpus_version is not None:
        raise CliUsageError("agentprov package --deposit: --corpus-version, --spec and --licence-file belong to the seal "
                            "mode; the deposit mode takes sealed corpora")
    release_date = _release_date(args.release_date)
    try:
        metadata = parse_release_toml(Path(args.metadata).read_bytes())
    except OSError:
        raise CliUsageError("agentprov package --deposit: the --metadata file cannot be read") from None
    corpora = [Path(p) for p in args.corpus]
    out = Path(args.deposit)
    assert_outside_git_work_tree(out, is_ignored=_is_ignored)  # read-only, so a dry run is refused too (CC-20)
    commit, clean = git_facts()
    producer = DepositProducer(agentprov_version=__version__, git_commit=commit, git_tree_clean=clean,
                               python=platform.python_version())
    report = build_deposit(
        corpora, metadata, out, release_date=release_date, producer=producer,
        max_archive_bytes=DEFAULT_MAX_ARCHIVE_BYTES if args.max_archive_bytes is None else int(args.max_archive_bytes),
        allow_mixed_licence_classes=bool(args.allow_mixed_licence_classes), lint=_lint, verify=verify_chain,
        dry_run=bool(args.dry_run),
    )  # fmt: skip
    result = CommandResult(dry_run=bool(args.dry_run), counters=report.counters)
    result.notices.extend(report.notices)
    if not clean or commit is None:
        result.notices.append("the AgentPROV checkout is not a clean known commit; the deposit records that (producer)")
    verb = "would write" if report.dry_run else "wrote"
    result.output(f"deposit draft: {verb} {report.counters['archives']} archive(s) for {len(report.corpora)} corpus "
                  f"version(s) to {safe_text(str(out), 200)}")
    for entry in report.corpora:
        cls: dict[str, Any] = entry["licence_class"]
        result.output(f"{entry['corpus_id']} {entry['corpus_version']}: root digest {entry['root_digest']}; licence class "
                      f"{cls['spdx']}" + (f" + {len(cls['restrictions'])} restriction(s)" if cls["restrictions"] else ""))
    if report.mixed_licence_classes:
        result.output("licence classes are mixed (--allow-mixed-licence-classes); recorded in deposit-metadata.json and the "
                      "datasheet copies")
    result.output(NOT_PUBLISHED)
    return result


def _index_release_date(text: str | None) -> date:
    if text is None:
        raise CliUsageError("agentprov package --index: --release-date YYYY-MM-DD is required (the publication date)")
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text) is None:
            raise ValueError(text)
        return date.fromisoformat(text)
    except ValueError:
        raise CliUsageError("agentprov package: --release-date is YYYY-MM-DD") from None


def run_index(ctx: Context) -> CommandResult:
    from agentprov.cli.package import _is_ignored, git_facts
    from agentprov.corpus.layout import assert_outside_git_work_tree
    from agentprov.release.builder import DepositProducer
    from agentprov.release.index import build_index
    from agentprov.release.metadata import LicenceClass, parse_release_toml
    from agentprov.versions import __version__

    args = ctx.args
    if args.index is None:
        raise CliUsageError("agentprov package: --part belongs to the index mode (--index OUT)")
    if args.deposit is not None:
        raise CliUsageError("agentprov package: --deposit and --index are different modes; give one")
    if args.max_archive_bytes is not None or args.allow_mixed_licence_classes:
        raise CliUsageError("agentprov package --index: an index has no archives and one licence class; "
                            "--max-archive-bytes and --allow-mixed-licence-classes belong to the deposit mode")
    if args.licence_file or args.spec is not None or args.corpus_version is not None:
        raise CliUsageError("agentprov package --index: --corpus-version, --spec and --licence-file belong to the seal "
                            "mode; the index mode takes sealed corpora")
    if not args.part:
        raise CliUsageError("agentprov package --index: at least one --part RECEIPT is required")
    if args.metadata is None:
        raise CliUsageError("agentprov package --index: --metadata release.toml is required (H.10.2)")
    release_date = _index_release_date(args.release_date)
    try:
        metadata = parse_release_toml(Path(args.metadata).read_bytes())
    except OSError:
        raise CliUsageError("agentprov package --index: the --metadata file cannot be read") from None
    out = Path(args.index)
    assert_outside_git_work_tree(out, is_ignored=_is_ignored)  # it holds datasheet copies; as the deposit mode (CC-20)
    commit, clean = git_facts()
    producer = DepositProducer(agentprov_version=__version__, git_commit=commit, git_tree_clean=clean,
                               python=platform.python_version())
    report = build_index([Path(p) for p in args.part], [Path(p) for p in args.corpus], metadata, out,
                         release_date=release_date, producer=producer, lint=_lint, dry_run=bool(args.dry_run))
    result = CommandResult(dry_run=bool(args.dry_run), counters=report.counters)
    result.notices.extend(report.notices)
    if not clean or commit is None:
        result.notices.append("the AgentPROV checkout is not a clean known commit; the index records that (producer)")
    verb = "would write" if report.dry_run else "wrote"
    result.output(f"index deposit: {verb} {report.counters['documents']} file(s) for {len(report.parts)} part record(s) "
                  f"and {report.counters['corpora']} corpus version(s) on {report.target} to {safe_text(str(out), 200)}")
    for part in report.parts:
        cls = LicenceClass(part["licence_class"]["spdx"], tuple(part["licence_class"]["restrictions"]))
        result.output(f"{safe_text(part['record'], 120)}: reserved DOI {part['reserved_doi']}; licence class "
                      f"{cls.label()}; corpora " + ", ".join(c["corpus_id"] for c in part["corpora"]))
    result.output(NOT_PUBLISHED)
    return result
