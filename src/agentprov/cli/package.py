"""``agentprov package``: seal a working corpus (MN N.2.11 seal mode; HL H.1.5, H.9, H.4.4).

Seal mode: ``package --corpus DIR --corpus-version X.Y.Z [--spec corpora/<id>/corpus-spec.toml] [--licence-file
NAME=PATH]… [--release-date YYYY-MM-DD] [--dry-run]``. The command gathers the build inputs and hands them to
:func:`agentprov.corpus.package.seal`, which writes and swaps the tree (``corpus/`` runs no subprocess and imports nothing
above L5):

* the corpus spec, ``CARD.md`` and ``CHANGES.toml`` from ``corpora/<id>/`` (``--spec``; by default the repository's
  ``corpora/<DIR name>/corpus-spec.toml``) and the decided statements ``corpora/datasheet-statements.toml`` beside it;
* the in-package source profile and semantics profiles (package data, AD-14);
* the upstream licence files the spec names: the corpus's own raw object when the import stored that file at the pinned
  commit (path equal to the name), otherwise ``--licence-file NAME=PATH`` (recorded in ``NOTICE.md`` as supplied at
  sealing);
* the producer's git commit and cleanliness (``git rev-parse`` / ``git status --porcelain`` on the checkout, through the
  absolute ``git`` path; M.5.3), the installed-distributions digest and the zlib version (H.2.7);
* the claims checker of :mod:`agentprov.adapters.registry.claims` (M.5.2(1));
* the H.1.5(5) guard: the sealed directory is outside every git work tree unless git-ignored.

``package`` is release mode for the interpreter guard (G.3.8): a corpus whose manifest records an advisory is refused
(exit 4). The deposit mode (``--deposit OUT --corpus DIR [--corpus DIR ...] --metadata release.toml --release-date
YYYY-MM-DD``) is the offline deposit builder's (H.10, D-42): :data:`DEPOSIT_HANDLER` dispatches it to
:func:`agentprov.cli.deposit.run_deposit`. The index mode (``--index OUT --part RECEIPT [--part RECEIPT ...] --corpus DIR
[--corpus DIR ...] --metadata release.toml --release-date YYYY-MM-DD``; H.10.7, D-947) builds the index-only umbrella
deposit (:func:`agentprov.cli.deposit.run_index`). Exit codes: 0 sealed; 1 a corpus-level check failed; 2 usage; 4 a precondition
refused (the deposit mode adds 3 and 5, see :mod:`agentprov.cli.deposit`).

Withholding (H.4.5; D-230..D-236): a working corpus with purge tombstones, a ``withhold`` snapshot or a source-profile
``[withhold]`` policy seals as a corpus version that withholds the affected raw objects and executions. The command
reports their counts (never a value) and the private sidecar ``DIR.withheld/`` their files were renamed into.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import zlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

from agentprov.cli.gitinfo import REPO_ROOT, _git, distributions_sha256, git_facts
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

__all__ = ["DEPOSIT_HANDLER", "REPO_ROOT", "git_facts", "register", "run_package"]

STATEMENTS_FILE: Final = "datasheet-statements.toml"
#: 9999-12-31T23:59:59Z, the last second a ``datetime`` (and an RFC 3339 ``release.created``) can name.
MAX_SOURCE_DATE_EPOCH: Final = 253402300799


def _deposit(ctx: Context) -> CommandResult:
    from agentprov.cli.deposit import run_deposit

    return run_deposit(ctx)


#: The deposit mode's entry point (H.10; U5). ``None``: ``--deposit`` exits 5.
DEPOSIT_HANDLER: Callable[[Context], CommandResult] | None = _deposit


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser(
        "package",
        parents=[shared],
        help="seal a working corpus (DIR.partial -> DIR), or build an offline deposit draft from sealed corpora",
        description="Seal a working corpus (N.2.11): write rules/, schemas/, LICENSES/, DATASHEET.md, CHANGELOG.md, the full "
        "corpus.json and checksums.sha256, then swap DIR.partial to DIR and print the root digest. With --deposit OUT, "
        "build a deposit draft (deterministic archives, DEPOSIT-MANIFEST.json, deposit-metadata.json) from one or more "
        "sealed corpora. With --index OUT, build the index-only umbrella deposit of a collection (COLLECTION-INDEX.json, "
        "datasheet copies, no archives) from the part records' draft receipts and their sealed corpora. Nothing is "
        "uploaded or published.",
        allow_abbrev=False,
    )
    p.set_defaults(command="package", handler=run_package, feedback=True)
    p.add_argument("--corpus", required=True, action="append", metavar="DIR",
                   help="the corpus directory (seal mode: once, its working tree is DIR.partial; deposit and index "
                        "modes: a sealed corpus, repeatable)")
    p.add_argument("--corpus-version", metavar="X.Y.Z", help="seal mode (required there): the version to seal (the spec's)")
    p.add_argument("--spec", metavar="PATH", help="corpora/<id>/corpus-spec.toml (CARD.md and CHANGES.toml beside it)")
    p.add_argument("--licence-file", action="append", default=[], metavar="NAME=PATH",
                   help="an upstream licence file the spec names that the corpus does not store (repeatable)")
    p.add_argument("--release-date", metavar="YYYY-MM-DD", help="release.created (else SOURCE_DATE_EPOCH, else null)")
    p.add_argument("--deposit", metavar="OUT", help="build a deposit draft directory OUT from sealed corpora (H.10)")
    p.add_argument("--index", metavar="OUT", help="build the index-only umbrella deposit OUT of a collection (H.10.7; "
                                                  "D-947): no archives, nothing uploaded")
    p.add_argument("--part", action="append", default=[], metavar="RECEIPT",
                   help="index mode: a part record's draft receipt (DIR.zenodo-TARGET-draft-receipt.json, status "
                        "complete), its deposit directory DIR beside it; repeatable")
    p.add_argument("--metadata", metavar="release.toml",
                   help="deposit and index modes: title, creators, keywords, preamble, DOIs (H.10.2)")
    p.add_argument("--max-archive-bytes", type=bounded_int, metavar="N",
                   help="deposit mode: split archives on shard boundaries at N bytes (default and maximum 2^31-1, no ZIP64)")
    p.add_argument("--allow-mixed-licence-classes", action="store_true",
                   help="deposit mode: admit corpora of different licence classes in one deposit (recorded; never -nc)")
    p.add_argument("--dry-run", action="store_true", help="compute and check everything, write nothing")


def _is_ignored(tree: Path, path: Path) -> bool:
    return _git(tree, "check-ignore", "-q", "--no-index", str(path)) is not None


def _spec_path(args: argparse.Namespace, final: Path) -> Path:
    if args.spec is not None:
        path = Path(args.spec)
    else:
        path = REPO_ROOT / "corpora" / final.name / "corpus-spec.toml"
    if not path.is_file():
        raise CliUsageError(f"agentprov package: no corpus spec at {safe_text(str(path), 200)!r}; name it with --spec")
    for sibling in ("CARD.md", "CHANGES.toml"):
        if not (path.parent / sibling).is_file():
            raise CliUsageError(f"agentprov package: {sibling} is missing beside the corpus spec")
    if not (path.parent.parent / STATEMENTS_FILE).is_file():
        raise CliUsageError(f"agentprov package: corpora/{STATEMENTS_FILE} is missing beside the corpora directory")
    return path


def _licence_files(args: argparse.Namespace, partial: Path, spec: Any) -> dict[str, Any]:
    """The upstream licence files the spec names: from the corpus's raw store (a git object whose path is the name, at the
    pinned commit of a snapshot), else from ``--licence-file NAME=PATH``."""
    from agentprov.corpus.package import LicenceFile
    from agentprov.corpus.reader import WORKING, CorpusReader

    supplied: dict[str, Path] = {}
    for item in args.licence_file:
        name, sep, path = item.partition("=")
        if not sep or not name or not path:
            raise CliUsageError("agentprov package: --licence-file takes NAME=PATH")
        supplied[name] = Path(path)
    reader = CorpusReader(partial, state=WORKING, used_partial=True)
    commits = {str(s.origin.get("commit")) for s in spec.source.snapshots if s.origin.get("kind") == "git"}
    by_path: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for row in reader.origins():
        data = row.origin.data
        if row.origin.kind == "git" and str(data.get("commit")) in commits and isinstance(data.get("path"), str):
            by_path.setdefault(str(data["path"]), (row.sha256, data))
    out: dict[str, Any] = {}
    store = reader.raw_store()
    for name in spec.licence_files:
        if name in supplied:
            try:
                blob = supplied[name].read_bytes()
            except OSError:
                raise CliUsageError(f"agentprov package: --licence-file {safe_text(name, 60)}: cannot be read") from None
            out[name] = LicenceFile(blob, "supplied at sealing with --licence-file (not verified against a pin)")
        elif name in by_path:
            sha, data = by_path[name]
            blob = store.read_bytes(sha)
            out[name] = LicenceFile(blob, f"raw object sha256:{sha} of this corpus; git {data.get('repo')}@{data.get('commit')}:"
                                          f"{name} (blob {data.get('blob_sha1')})")
    return out


def _persona_files(spec_path: Path, spec: Any) -> dict[str, bytes]:
    """The persona files (digests of benchmark e-mail addresses, D-810) the spec's ``[scan]`` table names, read from beside
    the spec; the seal checks each against the sha256 the spec records."""
    out: dict[str, bytes] = {}
    for relative, _digest in spec.persona_files:
        path = spec_path.parent / relative
        try:
            out[relative.rsplit("/", 1)[-1]] = path.read_bytes()
        except OSError:
            raise CliUsageError(f"agentprov package: the persona file {safe_text(relative, 80)} the spec names cannot be read") from None
    return out


def _field_groups(partial: Path) -> Callable[[Mapping[str, Any]], str] | None:
    """The ``agentprov stats`` field-group table of the tree being sealed (M.5.2(1); R-57), or None without the layer."""
    import importlib

    try:
        module = importlib.import_module("agentprov.stats.datasheet")
    except ImportError:
        return None
    renderer = getattr(module, "renderer", None)
    return renderer(partial) if callable(renderer) else None


def _release_args(release_date: str | None, epoch: str | None) -> Any:
    """The seal's :class:`ReleaseArgs` (H.2.13). ``release.created`` is never an impossible date: ``--release-date`` must
    be a real calendar date (the deposit mode's check) and ``SOURCE_DATE_EPOCH`` at most 9999-12-31T23:59:59Z (exit 2)."""
    from agentprov.cli.deposit import _release_date
    from agentprov.corpus.package import ReleaseArgs

    if release_date is not None:
        _release_date(release_date)
        return ReleaseArgs(release_date=release_date)
    if epoch and re.fullmatch(r"[0-9]+", epoch):  # ASCII only: str.isdigit takes Arabic-Indic and superscript digits (CC-19)
        if int(epoch) > MAX_SOURCE_DATE_EPOCH:
            raise CliUsageError("agentprov package: SOURCE_DATE_EPOCH is after 9999-12-31T23:59:59Z")
        return ReleaseArgs(source_date_epoch=int(epoch))
    return ReleaseArgs()


def run_package(ctx: Context) -> CommandResult:
    args = ctx.args
    if args.index is not None or args.part:
        from agentprov.cli.deposit import run_index

        return run_index(ctx)
    if args.deposit is not None or args.metadata is not None or args.max_archive_bytes is not None or args.allow_mixed_licence_classes:
        if DEPOSIT_HANDLER is not None:
            return DEPOSIT_HANDLER(ctx)
        raise UnsupportedCapability(
            "package --deposit is not implemented in this build",
            refusal=Refusal(id="--deposit", mode="package", status="the deposit builder is not implemented in this build",
                            lines=("Seal the corpus with package --corpus DIR --corpus-version X.Y.Z first.",)),
            code="cli.unsupported.package",
        )
    from agentprov.adapters.profiles import ProfileError, load_profile
    from agentprov.adapters.registry import REGISTRY_DATE
    from agentprov.adapters.registry.claims import CHECKER
    from agentprov.adapters.semantics_profiles import semantics_families
    from agentprov.corpus.datasheet import load_statements
    from agentprov.corpus.layout import assert_outside_git_work_tree
    from agentprov.corpus.package import ProducerFacts, SealInputs, seal
    from agentprov.corpus.spec import parse_spec

    if len(args.corpus) != 1:
        raise CliUsageError("agentprov package: the seal mode takes one --corpus (several only with --deposit)")
    if args.corpus_version is None:
        raise CliUsageError("agentprov package: the seal mode needs --corpus-version X.Y.Z")
    release = _release_args(args.release_date, ctx.env.get("SOURCE_DATE_EPOCH"))
    given = Path(args.corpus[0])
    final = given.with_name(given.name.removesuffix(".partial"))
    partial = final.with_name(final.name + ".partial")
    if os.path.isdir(final):
        from agentprov.corpus.layout import assert_writable

        assert_writable(final)  # a sealed corpus is never rewritten: exit 4 (N.1.5; K.12.5)
    spec_path = _spec_path(args, final)
    spec_bytes = spec_path.read_bytes()
    spec = parse_spec(spec_bytes, source=spec_path.name)
    if not partial.is_dir():
        raise CliUsageError("agentprov package: no working corpus DIR.partial at that path (N.1.5)")
    assert_outside_git_work_tree(final, is_ignored=_is_ignored)  # read-only, so a dry run is refused too (CC-20)
    try:  # the version the spec names, current or archived (D-31, D-933; D-960): the corpus is sealed with what it recorded
        profile = load_profile(spec.source.profile_id, spec.source.profile_version)
    except ProfileError:
        raise CliUsageError("agentprov package: the package ships no such version of the spec's source profile") from None
    from importlib import resources

    root = resources.files("agentprov").joinpath("adapters")
    semantics: dict[str, dict[str, bytes]] = {}
    for ref in spec.sem_profiles:
        pid, _, version = ref.rpartition("@")
        files: dict[str, bytes] = {}
        for family in semantics_families():
            node = root.joinpath(family, "semantics", f"{pid}-{version}")
            if node.is_dir():
                _collect(node, "", files)
        semantics[ref] = files
    commit, clean = git_facts()
    inputs = SealInputs(
        spec=spec_bytes,
        card=(spec_path.parent / "CARD.md").read_bytes(),
        changes=(spec_path.parent / "CHANGES.toml").read_bytes(),
        statements=load_statements((spec_path.parent.parent / STATEMENTS_FILE).read_bytes()),
        source_profile=_profile_bytes(profile),
        semantics_profiles=semantics,
        licence_files=_licence_files(args, partial, spec),
        persona_files=_persona_files(spec_path, spec),
        producer=ProducerFacts(git_commit=commit, git_tree_clean=clean, distributions_sha256=distributions_sha256(),
                               zlib_version=zlib.ZLIB_RUNTIME_VERSION),
        checker=CHECKER,
        registry_date=REGISTRY_DATE,
        field_groups=_field_groups(partial),
    )
    report = seal(final, corpus_version=args.corpus_version, inputs=inputs, release=release, dry_run=bool(args.dry_run),
                  progress=ctx.progress)
    result = CommandResult(dry_run=bool(args.dry_run), counters=dict(report.counters))
    result.corpus = {"content_digest": report.content_digest, "corpus_id": report.corpus_id,
                     "root": redact_personal(str(report.root)),  # "<home>/...", like options.corpus (CC-21)
                     "state": "working" if args.dry_run else "sealed"}  # fmt: skip
    result.notices.extend(report.notices)
    if report.root_digest is None:
        result.info(f"dry run: {report.corpus_id} {report.corpus_version} would seal with content digest {report.content_digest}")
    else:
        result.output(f"sealed {report.corpus_id} {report.corpus_version}: {report.counters['executions']} executions, "
                      f"{report.counters['files']} files")
        result.output(f"content digest {report.content_digest}")
        result.output(f"root digest {report.root_digest}")
    if "withheld_objects" in report.counters:  # counts only: a withheld value is never shown (G.9.5)
        verb = "would withhold" if report.root_digest is None else "withheld"
        result.output(f"{verb} {report.counters['withheld_objects']} raw object(s) and "
                      f"{report.counters['withheld_executions']} execution(s), listed in WITHHELD.json (H.4.5)")
        if report.sidecar is not None:
            result.output(f"their private files are in {redact_personal(str(report.sidecar))} (never released; D-231)")
    return result


def _collect(node: Any, prefix: str, out: dict[str, bytes]) -> None:
    for child in sorted(node.iterdir(), key=lambda c: c.name):
        if child.name.startswith((".", "_")):
            continue
        if child.is_dir():
            _collect(child, f"{prefix}{child.name}/", out)
        elif child.is_file():
            out[f"{prefix}{child.name}"] = child.read_bytes()


def _profile_bytes(profile: Any) -> bytes:
    """The bytes of the in-package profile file, current or archived (its digest is the profile's ``sha256``)."""
    from importlib import resources

    from agentprov.adapters.profiles import profile_families

    for family in profile_families():
        root = resources.files("agentprov").joinpath("adapters", family, "profiles")
        for node in (root.joinpath(f"{profile.id}.profile.toml"),
                     root.joinpath("archive", f"{profile.id}.profile.v{profile.version}.toml")):
            if node.is_file():
                data = node.read_bytes()
                if hashlib.sha256(data).hexdigest() == profile.sha256:
                    return data
    raise CliUsageError("agentprov package: the source profile file cannot be read back from the package")
