"""Sealing a working corpus: ``agentprov package --corpus DIR`` seal mode (HL H.1.5, H.2, H.4.4, H.5, H.9; MN N.2.11).

:func:`seal` turns the working tree ``DIR.partial/`` into the sealed corpus ``DIR/``:

**Preconditions** (each refuses with :class:`PackageRefusedError`, exit 4, before anything is written; N.2.11):
the working corpus exists and is not partial (no ``--limit``, no filter); the version asked for is the spec's and
``CHANGES.toml`` has an entry for it; the corpus spec matches the working corpus (source, profile and its digest, parts,
snapshots, mode, shard depth); every spec'd stage is complete for every execution (SEM, PROV, validation); the
validation stage ran strict (release mode); ``corpus.json`` records no ``interpreter_advisory`` (AD-16); the pin vouched
for every object (``verification.unverified == 0``), a pin was recorded and no object origin is ``local`` (D-33); the
snapshot origin built from the pin equals the spec's; the licence policy permits packaging (D.3.4; R-14); every upstream
licence file the spec names is supplied; the producer commit is known and its tree clean (H.2.7); the tree is
closed-world apart from an empty ``raw/tmp/`` (removed at sealing; H.1.5(4)); the card passes the lint and its mode is
the corpus's (H.9(5)). A live corpus (``corpus.json`` ``mode: live``, whatever its rows say; D-666) is refused with exit
5 (``package.unsupported.live``). A corpus-level check that fails afterwards (a claim that does not hold, a manifest that does not
validate, a digest that does not recompute) is :class:`agentprov.corpus.manifest.ManifestError` (exit 1).

**Steps** (N.2.11): complete the index rows (the five H.3.1 full-row members, computed from AER and SEM by
:mod:`agentprov.corpus.facets`; a row that is already full must recompute equal) while one pass over AER, SEM and PROV
collects what the manifest computes (:class:`agentprov.corpus.manifest.AerStats`); write ``rules/`` (byte copies of the
spec, card, changes, source and semantics profiles, rule catalogues and the PROV spec catalogue: a record, never an
authority, AD-14), ``schemas/`` (the published schemas), ``LICENSES/`` (``DERIVED.txt``, the verbatim upstream licence
files, a generated ``NOTICE.md``), ``CHANGELOG.md``, ``DATASHEET.md`` and the full ``corpus.json`` (``sealed: true``);
remove the empty ``raw/tmp/``; write ``checksums.sha256``; check the checksums (closed world) and the manifest, then run
``verify --level chain`` over the sealed tree (:mod:`agentprov.corpus.verify`; N.2.11 step 3); swap
``DIR.partial`` to ``DIR`` (:func:`agentprov.io.atomic.atomic_swap_dir`). If a step fails, every file the seal wrote is
removed and the two rewritten files (``executions.jsonl``, ``corpus.json``) get their working bytes back, so the working
tree stays a working tree.

**An interrupted seal** (CB-9): a seal that dies with no Python exception (SIGKILL, the OOM killer, a power loss) after
``corpus.json`` says ``sealed: true`` and before the swap cannot roll back, and its working bytes are gone. The next
seal of that ``DIR`` resumes it instead of refusing the sealed manifest: the manifest must validate, name the corpus and
version asked for, recompute its content digest and record the supplied spec, card, changes and release arguments; then
``raw/tmp/`` is removed and ``checksums.sha256`` written if the run died before those steps, the checksums (closed
world) and ``verify --level chain`` must pass, and the tree is swapped. A check that fails refuses with
:class:`SealInterruptedError` (``corpus.seal.interrupted``, exit 4) and changes nothing it has not already checked.

**Inputs from the caller** (:class:`SealInputs`): this module runs no subprocess and imports nothing above L5
(M.5.2(1), M.5.3): the CLI supplies the build inputs from the repository (``corpora/<id>/``), the source profile bytes,
the semantics profile files, the upstream licence texts, the producer's git commit and cleanliness, the claims checker of
``adapters.registry.claims`` and, when available, the field-group table of ``agentprov stats``. The result is
deterministic: two seals of two copies of one working corpus with the same inputs give byte-identical trees and the same
root digest (HL-T4; Q.20); nothing depends on the wall clock unless a release date is passed.

Extension point for the deposit builder (U5): :func:`seal` returns a :class:`SealReport` (corpus id and version,
content and root digests); ``agentprov.release.builder`` reads the sealed tree it names.
"""

from __future__ import annotations

import json
import os
import re
import time
import tomllib
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Final

from agentprov.aer.rules import CATALOGUE_HOMES, load_catalogue
from agentprov.corpus.authority import prov_catalogue_version
from agentprov.corpus.buildstep import BuildStepError, parse_steps
from agentprov.corpus.datasheet import CardChecker, StatementTable, render
from agentprov.corpus.facets import facet_members, facet_schema
from agentprov.corpus.index import ORACLE_SPECS, ORACLE_STATUS, IndexRow, encode_index
from agentprov.corpus.integrity import content_digest, root_digest, verify_checksums, write_checksums
from agentprov.corpus.layout import (
    CHANGELOG,
    CHECKSUMS,
    DATASHEET,
    MANIFEST,
    PARTIAL_SUFFIX,
    CorpusLayout,
    SealedCorpusError,
    assert_writable,
    iter_tree,
)
from agentprov.corpus.licences import is_non_commercial
from agentprov.corpus.manifest import (
    CORPUS_FORMATS,
    AerStats,
    ManifestError,
    aer_schema_resource,
    corpus_counts,
    digests_of,
    duplicate_summary,
    file_ref,
    format_for_aer,
    load_published_schema,
    ONTOLOGY_VERSIONS,
    origin_matches_pin,
    raw_dispositions,
    rule_catalogue_refs,
    schema_resource,
    snapshot_counts,
    snapshot_origin_from_pin,
    validate_manifest,
    validation_summary,
)
from agentprov.corpus.reader import WORKING, CorpusReader
from agentprov.corpus.register import encode_register
from agentprov.corpus.selection import snapshot_selections
from agentprov.corpus.spec import CorpusSpec, parse_spec, selection_of
from agentprov.corpus.withheld import decode_withheld, encode_withheld, withheld_summary
from agentprov.corpus.withheld import load_published_schema as load_withheld_schema
from agentprov.corpus.withhold import WithholdError, WithholdPlan, derived_labels, plan_withholding
from agentprov.corpus.writer import document_bytes, validation_summary as working_validation_summary
from agentprov.envinfo import refuse_advisory_manifest
from agentprov.errors import AgentProvError
from agentprov.ingest.names import collision_key
from agentprov.io.atomic import _fsync_dir, atomic_swap_dir, atomic_write_bytes
from agentprov.io.canonical import jcs_bytes, sha256_hex
from agentprov.progress import NULL_PROGRESS, Progress, ProgressEvent
from agentprov.sem.profiles import profile_digest

__all__ = [
    "LicenceFile",
    "PackageRefusedError",
    "ProducerFacts",
    "ReleaseArgs",
    "ReleaseDateError",
    "SealInputs",
    "SealInterruptedError",
    "SealReport",
    "parse_changes",
    "seal",
    "sidecar_path",
]

#: The private sidecar of a sealed corpus ``DIR``: ``DIR.withheld/`` holds the files withholding took out (D-231).
SIDECAR_SUFFIX: Final = ".withheld"

_SEMVER_ENTRY: Final = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.+-]+)?")
_BUMPS: Final = ("initial", "major", "minor", "patch")
_LICENCE_REDISTRIBUTION: Final = {"include": "permitted", "reference": "permitted", "nc_partition": "permitted-non-commercial",
                                  "forbidden": "not-permitted"}  # fmt: skip
#: 9999-12-31T23:59:59Z, the last second a ``datetime`` (and an RFC 3339 ``release.created``) can name.
MAX_SOURCE_DATE_EPOCH: Final = 253402300799
_POLICY_TO_RAW: Final = {"include": "include", "reference": "reference", "nc_partition": "include", "forbidden": "withhold"}


class PackageRefusedError(AgentProvError):
    """A ``package`` precondition refused the corpus (N.2.11; exit 4). Nothing was written."""

    code = "package.refused"
    exit_code = 4


class ReleaseDateError(PackageRefusedError):
    """The release arguments name no real instant: ``--release-date`` is not a calendar date or ``SOURCE_DATE_EPOCH`` lies
    outside 0..9999-12-31T23:59:59Z (H.2.13; exit 2, a usage error). Nothing was written."""

    code = "package.release_date"
    exit_code = 2


class SealInterruptedError(PackageRefusedError):
    """``DIR.partial`` holds the sealed ``corpus.json`` of a seal that stopped before the swap, and the tree does not
    check out, so the seal is not resumed (N.2.11; exit 4). The working bytes were rewritten by the interrupted run."""

    code = "corpus.seal.interrupted"
    exit_code = 4


@dataclass(frozen=True)
class ReleaseArgs:
    """Release arguments (H.2.13): ``created`` comes only from ``--release-date`` or ``SOURCE_DATE_EPOCH``; DOIs only when
    the user passes them; ``previous`` names the predecessor version."""

    release_date: str | None = None  # YYYY-MM-DD
    source_date_epoch: int | None = None
    version_doi: str | None = None
    concept_doi: str | None = None
    previous: Mapping[str, str] | None = None

    def to_json(self) -> dict[str, Any]:
        """The manifest's ``release`` object. ``created`` is never an impossible instant: ``release_date`` is a real
        calendar date and ``source_date_epoch`` lies in 0..:data:`MAX_SOURCE_DATE_EPOCH`, else :class:`ReleaseDateError`
        (exit 2)."""
        import datetime

        created = None
        if self.release_date is not None:
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", self.release_date) is None:
                raise ReleaseDateError("--release-date is YYYY-MM-DD")
            try:
                datetime.date.fromisoformat(self.release_date)
            except ValueError:
                raise ReleaseDateError("--release-date is YYYY-MM-DD, a real calendar date") from None
            created = f"{self.release_date}T00:00:00Z"
        elif self.source_date_epoch is not None:
            if not 0 <= self.source_date_epoch <= MAX_SOURCE_DATE_EPOCH:
                raise ReleaseDateError("SOURCE_DATE_EPOCH lies outside 1970-01-01T00:00:00Z..9999-12-31T23:59:59Z")
            created = datetime.datetime.fromtimestamp(self.source_date_epoch, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"concept_doi": self.concept_doi, "created": created,
                "previous": None if self.previous is None else dict(self.previous),
                "source_date_epoch": self.source_date_epoch, "status": "sealed", "version_doi": self.version_doi}  # fmt: skip


@dataclass(frozen=True)
class ProducerFacts:
    """What the sealing process knows about itself (H.2.7); supplied by the CLI (``corpus/`` runs no subprocess)."""

    git_commit: str | None
    git_tree_clean: bool
    distributions_sha256: str  # "sha256:<hex>" of the sorted "name==version\n" lines of the installed distributions
    zlib_version: str


@dataclass(frozen=True)
class LicenceFile:
    """One verbatim upstream licence file for ``LICENSES/<source_id>/<name>`` and where its bytes came from (NOTICE.md)."""

    data: bytes
    provenance: str  # generated text, e.g. "raw object sha256:… at git <repo>@<commit>:LICENSE" or "supplied at sealing"


@dataclass(frozen=True)
class SealInputs:
    """Everything :func:`seal` needs besides the working tree (see the module docstring)."""

    spec: bytes  # corpora/<id>/corpus-spec.toml
    card: bytes  # corpora/<id>/CARD.md
    changes: bytes  # corpora/<id>/CHANGES.toml
    statements: StatementTable
    source_profile: bytes  # the in-package source profile file (byte copy)
    semantics_profiles: Mapping[str, Mapping[str, bytes]]  # "<id>@<v>" -> data files of the profile directory
    licence_files: Mapping[str, LicenceFile]  # name -> file (names listed in the spec's [licence] files)
    producer: ProducerFacts
    checker: CardChecker
    registry_date: str
    field_groups: Callable[[Mapping[str, Any]], str] | None = None
    gate_reports: Mapping[str, str | None] = field(default_factory=dict)  # oracle spec -> gate report digest
    #: D-810: the persona files the spec's ``[scan]`` table references, by file name (written to ``rules/personas/``)
    persona_files: Mapping[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True)
class SealReport:
    """The outcome of :func:`seal` (counters of N.2.11: ``executions``, ``failed_rows``, ``files``, ``bytes``)."""

    corpus_id: str
    corpus_version: str
    root: Path
    content_digest: str
    root_digest: str | None  # None for a dry run (nothing is written)
    counters: Mapping[str, int]
    notices: tuple[str, ...] = ()
    dry_run: bool = False
    sidecar: Path | None = None  # DIR.withheld/ when anything was withheld (D-231)


def _refuse(message: str, code: str) -> PackageRefusedError:
    return PackageRefusedError(message, code=f"package.refused.{code}")


def _persona_files(spec: CorpusSpec, supplied: Mapping[str, bytes]) -> dict[str, bytes]:
    """``rules/personas/<name>`` -> bytes for the persona files the spec's ``[scan]`` table references (D-810). Each must
    be supplied, equal the spec's sha256 and parse; one the spec does not reference is refused. The spec (digest in
    ``files.spec``) names the digest of each, so the list that clears a release scan is bound to the sealed corpus. An
    observed group (``benchmark-input``, ``model-generated``, ``withhold``, ``withhold-object``) is evidence from one
    corpus's records and clears or withholds only there: its ``corpus_id`` must be the spec's."""
    from agentprov.corpus.personas import CORPUS_CLASSES, PersonaError, parse_persona_file, sha256_label

    wanted = {path.rsplit("/", 1)[-1]: digest for path, digest in spec.persona_files}
    if extra := sorted(set(supplied) - set(wanted)):
        raise _refuse(f"a persona file the spec does not reference was supplied ({len(extra)})", "persona")
    out: dict[str, bytes] = {}
    for name, digest in sorted(wanted.items()):
        data = supplied.get(name)
        if data is None:
            raise _refuse(f"the spec's persona file {name} was not supplied", "persona")
        if sha256_label(data) != digest:
            raise _refuse(f"the persona file {name} differs from the sha256 the spec records", "persona")
        try:
            parsed = parse_persona_file(data)
        except PersonaError as exc:
            raise _refuse(f"the persona file {name} is not valid: {exc}", "persona") from None
        if any(g.get("class") in CORPUS_CLASSES and g["corpus_id"] != spec.corpus_id for g in parsed.groups):
            raise _refuse(f"the persona file {name} has an observed group of another corpus (owning corpus only)", "persona")
        out[f"rules/personas/{name}"] = data
    return out


def _refuse_label_collisions(labels: Iterable[str]) -> None:
    """Refuse two labels with one G.3.6 collision key: on a case-insensitive volume the later write would replace the
    earlier file under the earlier name (``license`` over ``LICENSE``, an upstream ``notice.md`` over the generated
    ``NOTICE.md``). :func:`parse_spec` refuses such licence names first; this is the check before anything is written."""
    seen: dict[str, str] = {}
    for label in sorted(labels):
        other = seen.setdefault(collision_key(label), label)
        if other != label:
            raise _refuse(f"the labels {other} and {label} differ only in case or Unicode normalisation (G.3.6)",
                          "label_collision")


# ================================================================================================ build inputs
def parse_changes(data: bytes) -> list[dict[str, str]]:
    """``CHANGES.toml``: ``[[change]]`` entries ``{version, bump, summary}`` (L.1.3: bumps applied by hand and recorded
    here). ``bump`` is ``initial``, ``major``, ``minor`` or ``patch``; versions are unique."""
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise _refuse("CHANGES.toml is not valid UTF-8 TOML", "changes") from None
    if set(doc) - {"change"} or not isinstance(doc.get("change", []), list):
        raise _refuse("CHANGES.toml holds [[change]] entries only", "changes")
    out: list[dict[str, str]] = []
    for entry in doc.get("change", []):
        if not isinstance(entry, dict) or set(entry) != {"version", "bump", "summary"}:
            raise _refuse("a [[change]] entry is {version, bump, summary}", "changes")
        if not isinstance(entry["version"], str) or _SEMVER_ENTRY.fullmatch(entry["version"]) is None:
            raise _refuse("a [[change]] version is SemVer", "changes")
        if entry["bump"] not in _BUMPS or not isinstance(entry["summary"], str) or not entry["summary"].strip():
            raise _refuse("a [[change]] bump is initial|major|minor|patch and its summary is text", "changes")
        out.append({k: str(entry[k]) for k in ("version", "bump", "summary")})
    if len({e["version"] for e in out}) != len(out):
        raise _refuse("CHANGES.toml has two entries for one version", "changes")
    return out


def _changelog(corpus_id: str, entries: Sequence[Mapping[str, str]]) -> bytes:
    lines = [f"# Changelog: {corpus_id}", "",
             "Generated from rules/CHANGES.toml at sealing. Corpus versions are bumped by hand (L.1.3; the SemVer checker "
             "is deferred, AD-10 row 10)."]  # fmt: skip
    for entry in entries:
        lines += ["", f"## {entry['version']} ({entry['bump']})", "", entry["summary"].strip()]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _catalogue_bytes(namespace: str, version: int) -> bytes:
    """The package bytes of catalogue ``namespace`` at ``version`` (current file or ``rules/archive/``), checked against
    :func:`agentprov.aer.rules.load_catalogue` (AD-14: the package is the authority, the corpus copy is a record)."""
    catalogue = load_catalogue(namespace, version)
    home = CATALOGUE_HOMES.get(namespace) or f"agentprov.adapters.{namespace}"
    top, *rest = home.split(".")
    for relative in (f"rules/{namespace}.rules.toml", f"rules/archive/{namespace}.rules.v{version}.toml"):
        node = resources.files(top).joinpath(*rest, *relative.split("/"))
        if node.is_file():
            data = node.read_bytes()
            if sha256_hex(data) == catalogue.digest:
                return data
    raise ManifestError(f"the bytes of catalogue {namespace} v{version} cannot be read back", code="corpus.manifest.catalogue")


def _prov_catalogue_bytes(version: int | None = None) -> bytes:
    """The package bytes of the ``aprov`` catalogue at ``version``: the current file, or for an older version its
    byte-exact archive (``prov/catalogue/archive/``; D-960: a corpus is sealed with the version it was built under)."""
    from agentprov.prov.specs import CATALOGUE_RESOURCE, archived_catalogue_sha256, load_spec

    current = load_spec()
    if version is None or version == current.catalogue_version:
        data = resources.files("agentprov.prov").joinpath(*CATALOGUE_RESOURCE.split("/")).read_bytes()
        expected: str | None = current.catalogue_sha256
    else:
        node = resources.files("agentprov.prov").joinpath("catalogue", "archive", f"agentprov-prov-0.1.v{int(version)}.toml")
        data = node.read_bytes() if node.is_file() else b""
        expected = archived_catalogue_sha256(version)
    if expected is None or sha256_hex(data) != expected:
        raise ManifestError("the PROV spec catalogue cannot be read back", code="corpus.manifest.catalogue")
    return data


# ================================================================================================ checks
def _stage(derivation: Mapping[str, Any] | None, name: str) -> Mapping[str, Any] | None:
    for stage in (derivation or {}).get("stages", ()):
        if isinstance(stage, Mapping) and stage.get("stage") == name:
            return stage
    return None


def _check_working(manifest: Mapping[str, Any] | None, spec: CorpusSpec, corpus_version: str) -> Mapping[str, Any]:
    if manifest is None or manifest.get("format") not in CORPUS_FORMATS:  # a 0.1 working corpus seals as 0.1 (D-212)
        raise _refuse("the working corpus has no working corpus.json", "manifest")
    if manifest.get("sealed") is not False or manifest.get("state") != "working":
        raise _refuse("corpus.json is not a working manifest", "manifest")
    if manifest.get("mode") == "live":  # D-666: a native-log live corpus holds only `mode: import` rows, so the row
        # check in _complete_rows alone would let it through; the manifest says what the corpus is
        raise PackageRefusedError("sealing a live corpus is not supported in this build", code="package.unsupported.live",
                                  exit_code=5)
    from agentprov.corpus.runstate import incomplete_snapshots

    incomplete = incomplete_snapshots(manifest)
    if incomplete:  # D-610: before the partial check it implies, so the refusal names the cause
        sid = sorted(incomplete)[0]
        raise _refuse(f"snapshot {sid} of the working corpus is incomplete: an import run stopped before it ran to the "
                      f"end ({incomplete[sid]}); re-run the same import to the end, then package", "incomplete")
    selection = manifest.get("selection") or {}
    filters = selection.get("filters") or {}
    if manifest.get("partial") or selection.get("limit") is not None or filters.get("include_paths") or filters.get(
            "select") or filters.get("variants") is not None:
        raise _refuse("the working corpus is partial (--limit or a filter); package seals complete imports only", "partial")
    # NF-36 (regen item 130), class-0 backstop: a snapshot that records the selection it was imported with is a partial
    # import whatever the top-level mark says (a later snapshot's run must never clear it)
    partial = sorted(snapshot_selections(manifest))
    if partial:
        raise _refuse(f"snapshot {partial[0]} of the working corpus was imported with a selection (--limit, a filter or "
                      "--sample); package seals complete imports only", "partial")
    refuse_advisory_manifest(manifest)  # AD-16 as ruled: exit 4
    from agentprov.corpus.conformance import conformance_skipped

    if conformance_skipped(manifest):  # G2c-5 (D-432): unvalidated until a full recompute
        raise _refuse("the working corpus skipped the W3C PROV conformance check (--skip-prov-conformance); run "
                      "a full 'recompute --out NEW --stages sem,prov,validation' and seal NEW", "prov_conformance")
    try:
        steps = parse_steps((manifest.get("producer") or {}).get("build_steps"))
    except BuildStepError as exc:
        raise _refuse(f"the working corpus's build_steps is malformed: {exc}", "manifest") from None
    if any(step.get("git_tree_clean") is False for step in steps):  # D-780: a dirty tree names no code that can be rebuilt
        raise _refuse("a build step of the working corpus ran from a checkout with uncommitted changes, so its recorded "
                      "commit does not describe the code that ran; rebuild the corpus from a clean checkout (D-780)",
                      "build_dirty")
    if corpus_version != spec.corpus_version:
        raise _refuse("--corpus-version differs from the corpus spec's corpus_version", "version")
    if manifest.get("mode") != spec.mode:
        raise _refuse("the spec's mode differs from the working corpus's", "spec")
    sources = manifest.get("sources") or []
    if len(sources) != 1:
        raise _refuse("the working corpus has not exactly one source", "spec")
    source = sources[0]
    profile = source.get("profile") or {}
    if (source.get("source_id"), profile.get("id"), profile.get("version")) != (
            spec.source.source_id, spec.source.profile_id, spec.source.profile_version):
        raise _refuse("the spec's source or profile differs from the working corpus's", "spec")
    if not set(source.get("parts", ())) <= set(spec.source.parts):
        raise _refuse("the working corpus covers a part the spec does not name", "spec")
    working_ids = sorted(s.get("snapshot_id") for s in source.get("snapshots", ()))
    if working_ids != sorted(s.snapshot_id for s in spec.source.snapshots):
        raise _refuse("the spec's snapshots differ from the working corpus's", "spec")
    for snapshot in source.get("snapshots", ()):
        verification = snapshot.get("verification")
        if snapshot.get("pin") is None:
            raise _refuse(f"snapshot {snapshot.get('snapshot_id')}: no pin was recorded at import (D-33)", "unpinned")
        if isinstance(verification, Mapping) and verification.get("unverified", 0) > 0:
            raise _refuse(f"snapshot {snapshot.get('snapshot_id')}: the pin did not vouch for every input file", "unverified")
    return source


def _check_context(source: Mapping[str, Any], corpus_format: str) -> None:
    """NF-24: the sealed ``agentprov-corpus/0.1`` snapshot is a closed schema without ``context`` (D.16.14 R2) or
    ``pinned_objects`` (R3). Sealed, those joins would be dropped and every re-map of the corpus would run without them,
    so such a corpus is sealed only as ``agentprov-corpus/0.2``, which carries both (D-221; user decision 2026-10-21)."""
    for snapshot in source.get("snapshots", ()):
        held = [key for key in ("context", "pinned_objects") if snapshot.get(key)]
        if held and corpus_format == "agentprov-corpus/0.1":
            raise _refuse(f"snapshot {snapshot.get('snapshot_id')}: imported with {' and '.join(held)}, which the sealed "
                          f"{corpus_format} form cannot hold (a re-map of the sealed corpus would lose the joins); such a "
                          "corpus is sealed only from corpus/0.2", "context")
        if isinstance(snapshot.get("input"), Mapping) and corpus_format == "agentprov-corpus/0.1":  # D-223
            raise _refuse(f"snapshot {snapshot.get('snapshot_id')}: imported from an archive input, which the sealed "
                          f"{corpus_format} form cannot record (a re-map of the sealed corpus would not re-expand it); such "
                          "a corpus is sealed only from corpus/0.2", "archive_input")
        for entry in snapshot.get("context") or ():  # D-221: a context tree is sealed as its pin vouched for it
            role = entry.get("role") if isinstance(entry, Mapping) else None
            verification = entry.get("verification") if isinstance(entry, Mapping) else None
            if not isinstance(entry, Mapping) or not isinstance(entry.get("pin"), Mapping):
                raise _refuse(f"snapshot {snapshot.get('snapshot_id')}: context tree {role!r} has no pin recorded at "
                              "import (D-33, D-221)", "unpinned")
            if not isinstance(verification, Mapping) or verification.get("unverified") != 0:
                raise _refuse(f"snapshot {snapshot.get('snapshot_id')}: the pin of context tree {role!r} did not vouch "
                              "for every file (D-221)", "unverified")
            if verification.get("kind") not in ("download", "blob"):  # re-check RC-15: the sealed schema's kinds
                raise _refuse(f"snapshot {snapshot.get('snapshot_id')}: context tree {role!r} records no known "
                              "verification kind (download or blob; D-221)", "unverified")


def _sealed_input(recorded: Mapping[str, Any]) -> dict[str, Any]:
    """A recorded archive input (D-200, D-249, D-530) in its sealed form (``manifest.SNAPSHOT_INPUT``)."""
    def digest(value: Any) -> str:
        return "sha256:" + str(value or "").removeprefix("sha256:")

    out: dict[str, Any] = {"kind": "archive", "label": str(recorded.get("label")), "sha256": digest(recorded.get("sha256")),
                           "bytes": int(recorded.get("bytes") or 0)}
    if isinstance(recorded.get("parts"), list):
        out["parts"] = [{"file": str(p.get("file")), "sha256": digest(p.get("sha256")), "bytes": int(p.get("bytes") or 0)}
                        for p in recorded["parts"] if isinstance(p, Mapping)]
    return out


def _sealed_per_unit(snapshot: Mapping[str, Any], by_sha: Mapping[str, Sequence[Mapping[str, Any]]],
                     corpus_format: str) -> dict[str, Any]:
    """D-221/D-223: the ``input``, ``context``, ``pinned_objects`` and ``context_skipped`` members of a sealed
    ``agentprov-corpus/0.2`` snapshot, from the working snapshot (empty under ``agentprov-corpus/0.1``, which
    :func:`_check_context` refuses for any of them).

    A context tree's sealed origin is built from the role's recorded pin and the object origins it vouched for, as the
    snapshot's own (D-33); a pinned object must be stored with the origin the working snapshot records for it."""
    if corpus_format == "agentprov-corpus/0.1":
        return {}
    sid = snapshot.get("snapshot_id")
    out: dict[str, Any] = {}
    if isinstance(snapshot.get("input"), Mapping):  # D-223: the stored archive input, so a re-map re-expands it
        out["input"] = _sealed_input(snapshot["input"])
    context = []
    for entry in sorted(snapshot.get("context") or (), key=lambda c: str(c["role"])):
        pin = entry["pin"]
        objects = [o for group in by_sha.values() for o in group
                   if o.get("kind") not in ("member", "carved") and origin_matches_pin(o, pin)]
        try:
            origin = snapshot_origin_from_pin(pin, objects, corpus_format=corpus_format)
        except ManifestError as exc:
            raise _refuse(f"snapshot {sid}: context tree {entry['role']!r}: {exc}", "pin") from None
        verification = entry["verification"]
        sealed = {"role": str(entry["role"]), "origin": origin, "stored": int(entry.get("stored") or 0),
                  "verification": {"kind": str(verification.get("kind")), "verified": int(verification.get("verified", 0)),
                                   "unverified": 0}}
        if isinstance(entry.get("input"), Mapping):
            sealed["input"] = _sealed_input(entry["input"])
        context.append(sealed)
    if context:
        out["context"] = context
    pinned = []
    for row in sorted(snapshot.get("pinned_objects") or (), key=lambda o: str(o["label"]).encode("utf-8")):
        digest = str(row.get("sha256", "")).removeprefix("sha256:")
        recorded = dict(row.get("origin") or {})
        if recorded not in [dict(o) for o in by_sha.get(digest, ())]:
            raise _refuse(f"snapshot {sid}: pinned object {str(row.get('label'))[:120]!r} is not stored with the origin "
                          "the import recorded for it (D-221)", "pinned_object")
        pinned.append({"label": str(row["label"]), "origin": recorded, "sha256": "sha256:" + digest,
                       "bytes": int(row.get("bytes") or 0)})
    if pinned:
        out["pinned_objects"] = pinned
    skipped = sorted({str(r) for r in snapshot.get("context_skipped") or ()})
    if skipped:
        out["context_skipped"] = skipped
    return out


def _check_stages(spec: CorpusSpec, derivation: Mapping[str, Any] | None, rows: Sequence[IndexRow]) -> Mapping[str, Any]:
    validation = _stage(derivation, "validation")
    if _stage(derivation, "aer") is None or _stage(derivation, "prov") is None or validation is None:
        raise _refuse("a spec'd stage (aer, prov, validation) is not recorded in derivation.json", "stages")
    if spec.sem_profiles and _stage(derivation, "sem") is None:
        raise _refuse("the spec names semantics profiles but no SEM stage ran", "stages")
    if validation.get("mode") != "release":
        raise _refuse("the validation stage did not run strict (release mode); package needs strict validation", "dev_validation")
    for row in rows:
        if row.validation is None or row.prov is None or set(row.prov) != set(spec.prov_specs):
            raise _refuse("an execution lacks a spec'd PROV or validation stage", "stages")
        if set(row.sem or {}) != set(spec.sem_profiles):
            raise _refuse("an execution lacks a spec'd SEM stage", "stages")
    return validation


def _licence_table(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    licence = profile.get("licence")
    if not isinstance(licence, Mapping) or not isinstance(licence.get("basis"), str) or licence.get("policy") not in _POLICY_TO_RAW:
        raise _refuse("the source profile has no complete [licence] table", "licence")
    return licence


def _licences(spec: CorpusSpec, profile: Mapping[str, Any], raw_policy: str, registry_date: str) -> dict[str, Any]:
    lic = _licence_table(profile)
    policy = str(lic["policy"])
    if policy == "forbidden":
        raise _refuse("the licence policy is forbidden: the corpus may not be packaged (D.3.4)", "licence_policy")
    if policy == "nc_partition" and not spec.corpus_id.endswith("-nc"):
        raise _refuse("an nc_partition source is packaged only as a separately licensed -nc corpus (H.4.1)", "licence_policy")
    if raw_policy != "withhold" and _POLICY_TO_RAW[policy] != raw_policy:  # withholding only narrows a release (D-233)
        raise _refuse(f"the snapshot raw policy {raw_policy} does not follow licence policy {policy} (H.4.1(2))", "licence_policy")
    spdx = lic.get("spdx")
    derived = spdx if spec.licence_derived == "inherit" else spec.licence_derived
    if not isinstance(derived, str) or not derived:
        raise _refuse("the derived licence is inherit but the source has no SPDX id", "licence")
    restrictions = sorted({str(r) for r in lic.get("restrictions", ())})
    data_licence = lic.get("data_licence")
    profile_meta = profile.get("profile", {})
    # The per-term SPDX family test of the release licence class (H.10.6), not a "-NC" substring.
    redistribution = "permitted-non-commercial" if is_non_commercial(derived) else _LICENCE_REDISTRIBUTION[policy]
    return {
        "assessment": (f"Licence facts as recorded in the [licence] table of source profile {profile_meta.get('id')}@"
                       f"{profile_meta.get('version')} and in the source registry (registry date {registry_date}); "
                       "not legal advice."),
        "attribution": [str(a) for a in lic.get("attribution", ())],
        "class": {"restrictions": restrictions, "spdx": derived},
        "derived": {"basis": "inherit" if spec.licence_derived == "inherit" else "user-decision",
                    "decided_by": spec.licence_decided_by, "spdx": derived, "text_path": "LICENSES/DERIVED.txt"},
        "embedded": [{"status": "not assessed", "what": str(u)} for u in lic.get("unassessed", ())],
        "policy": {"licence_policy": policy, "raw_policy": raw_policy},
        "raw": [{
            "basis": str(lic["basis"]),
            "copyright": [str(h) for h in lic.get("holders", ())],
            "data_licence_explicit": isinstance(data_licence, str) and data_licence not in ("", "none"),
            "licence_files": [f"LICENSES/{spec.source.source_id}/{name}" for name in spec.licence_files],
            "source_id": spec.source.source_id,
            "spdx": spdx if isinstance(spdx, str) else None,
        }],
        "redistribution": redistribution,
        "restrictions": restrictions,
    }  # fmt: skip


def _derived_txt(licences: Mapping[str, Any], spec: CorpusSpec) -> bytes:
    derived = licences["derived"]
    lines = [
        f"Licence of the AgentPROV-derived artefacts of corpus {spec.corpus_id}",
        "",
        "The derived artefacts of this corpus (the AER, SEM and PROV files, the index, the register, the validation results, "
        "the views and the generated documents) are licensed under:",
        "",
        f"    SPDX-License-Identifier: {derived['spdx']}",
        "",
        f"Basis: {derived['basis']} (decided by {derived['decided_by']}).",
    ]
    if derived["basis"] == "inherit":
        lines.append(f"The licence is inherited from the source data; its upstream licence text is in LICENSES/{spec.source.source_id}/.")
    if licences["restrictions"]:
        lines += ["", "The following restrictions apply to the data and to everything derived from it:"]
        lines += [f"  - {r}" for r in licences["restrictions"]]
    lines += ["", "This statement records a licence decision; it is not legal advice."]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _notice(spec: CorpusSpec, profile: Mapping[str, Any], licences: Mapping[str, Any], origin: Mapping[str, Any],
            files: Mapping[str, LicenceFile]) -> bytes:
    source = profile.get("source", {})
    lines = [f"# Notice: {spec.source.source_id}", "",
             f"Generated at sealing from the source profile and the corpus spec of `{spec.corpus_id}` (H.4.4)."]
    lines += ["", "## Origin", ""]
    if origin.get("kind") == "git":
        lines.append(f"- Repository: {origin['repo']}")
        lines.append(f"- Commit: `{origin['commit']}`" + (f", tree `{origin['subtree']}`" if origin.get("subtree") else ""))
    elif origin.get("kind") == "corpus":
        lines.append(f"- Corpus: {origin['corpus']} {origin['version']}, producer commit `{origin['producer_commit']}`")
    if isinstance(source.get("canonical_repo"), str):
        lines.append(f"- Canonical repository: {source['canonical_repo']}")
    if isinstance(source.get("concept_doi"), str):
        lines.append(f"- Concept DOI: {source['concept_doi']}")
    if isinstance(source.get("paper"), str):
        lines.append(f"- Paper: {source['paper']}")
    raw = licences["raw"][0]
    lines += ["", "## Licence", "", f"- SPDX: {raw['spdx'] or 'none'}", f"- Basis (verbatim): {raw['basis']}"]
    if raw["copyright"]:
        lines += ["- Copyright holders:"] + [f"  - {h}" for h in raw["copyright"]]
    lines += ["", "## Licence files", ""]
    for name in spec.licence_files:
        file = files[name]
        lines.append(f"- `{name}`: sha256 `{sha256_hex(file.data)}`; {file.provenance}")
    if not spec.licence_files:
        lines.append("- none")
    lines += ["", "## Required citations", ""] + ([f"- {a}" for a in licences["attribution"]] or ["- none"])
    lines += ["", "## Restrictions (verbatim)", ""] + ([f"- {r}" for r in licences["restrictions"]] or ["- none"])
    lines += ["", "Licence readings are not legal advice."]
    return ("\n".join(lines) + "\n").encode("utf-8")


# ================================================================================================ the pass over executions
def _complete_rows(reader: CorpusReader, rows: Sequence[IndexRow], gate_reports: Mapping[str, str | None]) -> tuple[
        list[IndexRow], AerStats]:
    stats = AerStats()
    out: list[IndexRow] = []
    for row in rows:
        aer = reader.read_aer(row)
        sem = reader.read_sem_all(row)
        prov = [reader.read_prov(row, spec) for spec in sorted(row.prov_paths or {})]
        stats.add(aer, sem, prov)
        if row.mode != "import":
            raise PackageRefusedError("sealing a live corpus is not supported in this build", code="package.unsupported.live",
                                      exit_code=5)
        members = facet_members(aer, sem, prov_specs=sorted(row.prov_paths or {}), gate_reports=gate_reports)
        if row.facet_members is not None and row.facet_members.to_json() != members.to_json():
            raise ManifestError("a full index row's facets do not recompute from its AER and SEM (H.3.3(3))",
                                code="corpus.manifest.facets")
        out.append(row.with_facets(members))
    return out, stats


# ================================================================================================ seal
#: Origin kinds of a derived object and the member naming the object it was derived from (a member: its container; a
#: carved blob, D-218: its source object).
_DERIVED: Final = {"member": "container", "carved": "from"}


def snapshot_object_origins(primaries: Iterable[str], by_sha: Mapping[str, Sequence[Mapping[str, Any]]],
                            pin: Mapping[str, Any] | None, *, several: bool) -> list[dict[str, Any]]:
    """The object-level origins a snapshot's sealed origin is built from (H.2.3; D-33): the non-derived origins of the
    snapshot's primary objects and of every object they derive from, followed to the root of each chain. A log inside an
    ``.eval`` inside a tar.zst, a split zip or a nested zip (D-380, D-381) reaches the archive input's ``hf``, ``zenodo``
    or ``split`` origin however deep it is nested; ``seen`` ends a cycle. Each root origin is listed once.

    With ``several`` snapshots (D-202) an object two snapshots share has a chain to each pin, so only the roots this pin
    vouched for are kept (:func:`origin_matches_pin`, and for a single-file Hugging Face pin, the pinned file)."""
    out: dict[tuple[str, bytes], dict[str, Any]] = {}
    seen: set[str] = set()
    todo = sorted(primaries)
    while todo:
        sha = todo.pop()
        if sha in seen:
            continue
        seen.add(sha)
        for origin in by_sha.get(sha, ()):
            via = _DERIVED.get(str(origin.get("kind")))
            if via is None:
                out.setdefault((sha, jcs_bytes(origin)), dict(origin))
            elif isinstance(origin.get(via), str):
                todo.append(str(origin[via]).removeprefix("sha256:"))
    origins = [out[key] for key in sorted(out)]
    if several:
        origins = [o for o in origins if _vouched(o, pin)]
    return origins


def snapshot_pin_object_origins(working_snapshot: Mapping[str, Any], primaries: Iterable[str],
                                by_sha: Mapping[str, Sequence[Mapping[str, Any]]], *, several: bool) -> list[dict[str, Any]]:
    """:func:`snapshot_object_origins` for one working-manifest snapshot, as ``seal`` builds its origin (D-33). PR-2: an R3
    pinned object (an LFS object) is a primary candidate with its own pin's origin; like the re-map (rawtree's
    ``pinned_keys``), the snapshot origin is built without the exact (object, origin) pairs the snapshot's
    ``pinned_objects`` record. Shared with the pre-check's sealed-copy spec (``tools/precheck/l2_check.py``)."""
    pinned = {(str(o.get("sha256", "")).removeprefix("sha256:"), json.dumps(o.get("origin"), sort_keys=True))
              for o in working_snapshot.get("pinned_objects") or () if isinstance(o, Mapping)}
    by_sha_snapshot = {sha: [o for o in group if (sha, json.dumps(dict(o), sort_keys=True)) not in pinned]
                       for sha, group in by_sha.items()} if pinned else by_sha
    return snapshot_object_origins(primaries, by_sha_snapshot, working_snapshot.get("pin"), several=several)


def _vouched(origin: Mapping[str, Any], pin: Mapping[str, Any] | None) -> bool:
    if not origin_matches_pin(origin, pin):
        return False
    if origin.get("kind") == "hf" and pin is not None and pin.get("archive") != "split-zip":
        file = pin.get("file", pin.get("path"))  # an hf pin is a revision, and each snapshot pins one file of it
        return not isinstance(file, str) or origin.get("path") == file
    return True


def _final_and_partial(root: Path) -> tuple[Path, Path]:
    final = root.with_name(root.name[: -len(PARTIAL_SUFFIX)]) if root.name.endswith(PARTIAL_SUFFIX) else root
    return final, final.with_name(final.name + PARTIAL_SUFFIX)


class _Writer:
    """Writes files into the working tree and remembers what to undo when sealing fails."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.created: list[Path] = []
        self.restore: dict[Path, bytes] = {}

    def write(self, label: str, data: bytes) -> None:
        path = self.root.joinpath(*label.split("/"))
        if os.path.lexists(path):
            if path not in self.restore and path not in self.created:
                self.restore[path] = path.read_bytes()
        else:
            self.created.append(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, data)

    def rollback(self) -> None:
        for path, data in self.restore.items():
            atomic_write_bytes(path, data)
        for path in reversed(self.created):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        checksums = self.root / "checksums.sha256"
        if checksums.exists() and checksums not in self.restore:
            checksums.unlink()
        for directory in ("rules/prov", "rules", "schemas", "LICENSES"):
            _prune(self.root / directory)


def _prune(directory: Path) -> None:
    if not directory.is_dir():
        return
    for child in sorted(directory.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if child.is_dir():
            try:
                child.rmdir()
            except OSError:
                pass
    try:
        directory.rmdir()
    except OSError:
        pass


def seal(root: str | os.PathLike[str], *, corpus_version: str, inputs: SealInputs, release: ReleaseArgs | None = None,
         dry_run: bool = False, progress: Progress = NULL_PROGRESS) -> SealReport:
    """Seal ``DIR.partial`` into ``DIR`` (see the module docstring); ``root`` is ``DIR`` or ``DIR.partial``.

    ``progress`` receives a ``start`` line and one unit per seal stage (:data:`SEAL_STAGES`; N.1.14). It never changes
    what is written (F1).

    Raises :class:`PackageRefusedError` (exit 4) for a refused precondition, :class:`ManifestError` /
    :class:`agentprov.corpus.datasheet.DatasheetError` (exit 1, or 4 for the card) for a failed corpus-level check.
    ``dry_run`` computes everything and writes nothing (N.1.6); its report has no root digest. A ``DIR.partial`` whose
    own ``corpus.json`` is sealed is an interrupted seal and is resumed (:func:`_resume`; CB-9).
    """
    (release or ReleaseArgs()).to_json()  # an impossible release date refuses before anything is read or written
    final, partial = _final_and_partial(Path(root))
    stage = _Stages(progress, dry_run=dry_run)
    if os.path.lexists(final):
        raise _refuse("the sealed directory already exists; a sealed corpus is never rewritten (H.1.5(3))", "exists")
    if not partial.is_dir():
        raise PackageRefusedError("no working corpus DIR.partial to seal", code="corpus.missing", exit_code=2)
    try:
        assert_writable(partial)
    except SealedCorpusError as exc:
        if exc.code != SealedCorpusError.code:
            raise  # corpus.sealed.unverifiable: fail closed
        assert_writable(partial.parent)  # a sealed corpus above DIR.partial still refuses; otherwise the flag is its own
        return _resume(final, partial, corpus_version=corpus_version, inputs=inputs, release=release, dry_run=dry_run)
    spec = parse_spec(inputs.spec)
    # the directory name is informative only (H.1.2): the corpus id comes from the spec (D-35)
    reader = CorpusReader(partial, state=WORKING, used_partial=True)
    working = reader.manifest()
    source = _check_working(working, spec, corpus_version)
    assert working is not None
    if reader.shard_depth != spec.shard_depth:
        raise _refuse("the spec's shard depth differs from the working tree's", "spec")
    changes = parse_changes(inputs.changes)
    if not any(e["version"] == corpus_version for e in changes):
        raise _refuse(f"CHANGES.toml has no entry for {corpus_version} (manual bump, AD-10 row 10)", "changelog")
    producer = inputs.producer
    if producer.git_commit is None or re.fullmatch(r"[0-9a-f]{40}", producer.git_commit) is None or not producer.git_tree_clean:
        raise _refuse("package runs in release mode: the producer commit must be known and its tree clean (H.2.7)", "git")
    profile_doc = _parse_profile(inputs.source_profile)
    working_profile = source["profile"]
    if "sha256:" + sha256_hex(inputs.source_profile) != working_profile.get("sha256"):
        raise _refuse("the supplied source profile differs from the one the import used (rules.mismatch, AD-14)", "profile")
    persona_labels = _persona_files(spec, inputs.persona_files)
    missing = [name for name in spec.licence_files if name not in inputs.licence_files]
    if missing:
        raise _refuse("an upstream licence file the spec names was not supplied: " + ", ".join(missing), "licence_file")
    scan = iter_tree(partial)
    lock = [f for f in scan.findings if f.code == "corpus.tree.lock"]
    if lock:
        raise _refuse("the working tree is locked: a writer may be running", "locked")
    stray = [f for f in scan.findings if not (f.code == "corpus.tree.raw_tmp" and f.label == "raw/tmp")]
    if stray:
        raise _refuse(f"the tree is not closed-world ({', '.join(sorted({f.code for f in stray}))}); refusing to seal "
                      "(H.1.5(4))", "closed_world")

    derivation = reader.derivation()
    rows_all = reader.index()
    register_working = reader.register()
    corpus_format = format_for_aer(str((_stage(derivation, "aer") or {}).get("format") or ""))
    _check_context(source, corpus_format)
    members = reader.members()
    origins = reader.origins()
    snapshot_spec = {s.snapshot_id: s for s in spec.source.snapshots}

    # withholding (H.4.5; D-230..D-236): what leaves this corpus version, decided before anything else is computed
    plan = _plan(reader, partial, scan, rows_all, register_working, members, origins, source, snapshot_spec,
                 inputs.source_profile, spec, release, _catalogue_versions(derivation), inputs.spec, inputs.persona_files)
    stage("withhold")
    sidecar = sidecar_path(final)
    if not plan.empty and os.path.lexists(sidecar):
        raise _refuse("the private sidecar DIR.withheld already exists; it is never overwritten (D-231)", "sidecar")
    rows_in = [row for row in rows_all if row.ex not in plan.executions]
    register = sorted([*register_working, *plan.register], key=lambda e: e.sort_key)
    validation_stage = _check_stages(spec, derivation, rows_in)
    imp = profile_doc.get("import") if isinstance(profile_doc.get("import"), Mapping) else {}

    # snapshots: origin from the pin (D-33), selection, recomputed counts
    by_sha: dict[str, list[Mapping[str, Any]]] = {}
    for origin_row in origins:
        by_sha.setdefault(origin_row.sha256, []).append({"kind": origin_row.origin.kind, **origin_row.origin.data})
    if any(o["kind"] == "local" for group in by_sha.values() for o in group):
        raise _refuse("an object origin is local: the pin did not vouch for it (D-33)", "local_origin")
    snapshots = []
    all_ids = [s.snapshot_id for s in spec.source.snapshots]
    for working_snapshot in sorted(source["snapshots"], key=lambda s: s["snapshot_id"]):
        sid = working_snapshot["snapshot_id"]
        sspec = snapshot_spec[sid]
        primaries = {ref.sha256 for r in rows_all if sid in r.snapshot_ids for ref in r.raw if ref.role == "primary"}
        object_origins = snapshot_pin_object_origins(working_snapshot, primaries, by_sha,
                                                     several=len(source["snapshots"]) > 1)
        try:
            origin = snapshot_origin_from_pin(working_snapshot.get("pin"), object_origins, corpus_format=corpus_format)
        except ManifestError as exc:
            raise _refuse(str(exc), "pin") from None
        if dict(sspec.origin) != origin:
            raise _refuse(f"snapshot {sid}: the spec's origin differs from the origin the recorded pin gives (D-33)", "origin")
        selection = selection_of(sspec, imp)
        counts = snapshot_counts(rows_in, register, sid, selection["exclude"], all_snapshots=all_ids)
        snapshots.append({"alt_origins": [dict(o) for o in sspec.alt_origins], "counts": counts, "origin": origin,
                          "raw_policy": sspec.raw_policy, "selection": selection, "snapshot_id": sid,
                          **_sealed_per_unit(working_snapshot, by_sha, corpus_format)})  # fmt: skip
    # a withhold snapshot releases nothing (D-233); the released snapshots share one raw policy
    raw_policies = {s["raw_policy"] for s in snapshots if s["raw_policy"] != "withhold"}
    if len(raw_policies) > 1:
        raise _refuse("snapshots with different raw policies are not supported in this build", "raw_policy")
    licences = _licences(spec, profile_doc, next(iter(raw_policies), "withhold"), inputs.registry_date)

    # one pass over every released execution: full rows and the AER statistics
    rows, stats = _complete_rows(reader, rows_in, inputs.gate_reports)
    stage("executions")
    index_bytes = encode_index(rows)
    register_bytes = encode_register(register) if plan.register else reader.read_bytes("register.jsonl")
    members_bytes = reader.read_bytes("raw/members.jsonl")
    results_bytes, summary_bytes = reader.read_bytes("validation/results.jsonl"), reader.read_bytes("validation/summary.json")
    withheld_results: list[dict[str, Any]] = []
    if plan.executions:
        kept = [r for r in reader.validation_results() if r.get("ex") not in plan.executions]
        withheld_results = [r for r in reader.validation_results() if r.get("ex") in plan.executions]
        results_bytes = b"".join(jcs_bytes(r) + b"\n" for r in kept)
        summary_bytes = document_bytes(working_validation_summary(kept))

    # rules/: byte copies (a record, AD-14)
    files: dict[str, bytes] = {
        "rules/corpus-spec.toml": inputs.spec,
        "rules/CARD.md": inputs.card,
        "rules/CHANGES.toml": inputs.changes,
        f"rules/{spec.source.profile_id}.profile.toml": inputs.source_profile,
    }
    files.update(persona_labels)
    aer_stage = _stage(derivation, "aer") or {}
    sem_stage = _stage(derivation, "sem") or {}
    catalogues: dict[str, int] = {str(ns): int(v) for ns, v in dict(aer_stage.get("rules", {})).items()}
    for ns, v in dict(sem_stage.get("rules", {})).items():
        if catalogues.setdefault(str(ns), int(v)) != int(v):
            raise _refuse(f"two versions of catalogue {ns} contributed to one corpus version (H.2.5)", "catalogue")
    catalogues.setdefault("corpus", load_catalogue("corpus").version)
    catalogue_refs: dict[str, tuple[int, str, int, str]] = {}
    for ns, version in sorted(catalogues.items()):
        data = _catalogue_bytes(ns, version)
        recorded = dict(aer_stage.get("rules_sha256", {})).get(ns)
        if recorded is not None and recorded != "sha256:" + sha256_hex(data):
            raise _refuse(f"catalogue {ns} v{version} in the package differs from the one the import used (rules.mismatch)",
                          "catalogue")
        files[f"rules/{ns}.rules.toml"] = data
        catalogue_refs[ns] = (version, sha256_hex(data), len(load_catalogue(ns, version).rules), f"rules/{ns}.rules.toml")
    prov_stage = _stage(derivation, "prov") or {}
    # D-960: the version the prov stage was built under (current or archived; D-930 keeps stored corpora at it). Unknown
    # recorded bytes fall back to the current version, which the comparison below then refuses.
    prov_catalogue = _prov_catalogue_bytes(prov_catalogue_version(prov_stage))
    if prov_stage.get("rules_sha256") not in (None, "sha256:" + sha256_hex(prov_catalogue)):
        raise _refuse("the PROV spec catalogue differs from the one the import used (rules.mismatch)", "catalogue")
    files["rules/prov/agentprov-prov-0.1.toml"] = prov_catalogue
    from agentprov.prov.specs import parse_spec_catalogue

    prov_spec = parse_spec_catalogue(prov_catalogue, source="rules/prov/agentprov-prov-0.1.toml")
    catalogue_refs["aprov"] = (prov_spec.catalogue_version, sha256_hex(prov_catalogue), len(prov_spec.rules),
                               "rules/prov/agentprov-prov-0.1.toml")
    stats.rules_used.update(str(d["from"]) for d in facet_schema() if "@" in str(d["from"]))
    semantics_refs = []
    recorded_sem = dict(sem_stage.get("profiles", {}))
    for ref in spec.sem_profiles:
        profile_files = inputs.semantics_profiles.get(ref)
        if profile_files is None:
            raise _refuse(f"semantics profile {ref} was not supplied", "profile")
        digest = profile_digest(profile_files)
        if recorded_sem.get(ref) != "sha256:" + digest:
            raise _refuse(f"semantics profile {ref} differs from the one the import used (rules.mismatch)", "profile")
        pid, _, pversion = ref.rpartition("@")
        paths = []
        for name, data in sorted(profile_files.items()):
            if not name.endswith(".toml"):
                raise ManifestError(f"semantics profile {ref} holds a non-TOML file; it cannot be recorded under rules/",
                                    code="corpus.manifest.profile")
            label = f"rules/{pid}-{pversion}.{name[: -len('.toml')].replace('/', '.')}.profile.toml"
            files[label] = data
            paths.append(label)
        semantics_refs.append({"id": pid, "paths": paths, "sha256": "sha256:" + digest, "version": int(pversion)})

    # schemas/ and LICENSES/
    # D-212: the corpus format follows the AER format of its records (one AER version per corpus version)
    files[f"schemas/{aer_schema_resource(corpus_format)}"] = (
        resources.files("agentprov").joinpath("schemas", aer_schema_resource(corpus_format)).read_bytes())
    files[f"schemas/{schema_resource(corpus_format)}"] = load_published_schema(corpus_format)
    withheld_bytes = None if plan.document is None else encode_withheld(plan.document)
    if plan.document is not None and withheld_bytes is not None:
        files["WITHHELD.json"] = withheld_bytes
        files[f"schemas/{plan.document.schema_resource}"] = load_withheld_schema(plan.document.schema_resource)
    origin0 = snapshots[0]["origin"]
    for name in spec.licence_files:
        files[f"LICENSES/{spec.source.source_id}/{name}"] = inputs.licence_files[name].data
    files[f"LICENSES/{spec.source.source_id}/NOTICE.md"] = _notice(spec, profile_doc, licences, origin0, inputs.licence_files)
    files["LICENSES/DERIVED.txt"] = _derived_txt(licences, spec)
    files[CHANGELOG] = _changelog(spec.corpus_id, changes)

    # the manifest
    adapters = [dict(a) for a in working.get("adapters", ())]
    for adapter in adapters:
        if adapter.get("code_sha256") != aer_stage.get("adapter_code_sha256"):
            raise ManifestError("the adapter code digest differs between corpus.json and derivation.json",
                                code="corpus.manifest.adapter")
    working_producer = dict(working.get("producer") or {})
    producer_json: dict[str, Any] = {
        "agentprov_version": working_producer.get("agentprov_version"),
        "distributions_sha256": producer.distributions_sha256,
        "git_commit": producer.git_commit,
        "git_tree_clean": producer.git_tree_clean,
        "interpreter_advisory": working_producer.get("interpreter_advisory"),
        "isolation": working_producer.get("isolation"),
        "key_distributions": dict(working_producer.get("key_distributions") or {}),
        "lockfile_sha256": working_producer.get("lockfile_sha256"),
        "platform": dict(working_producer.get("platform") or {}),
        "python": dict(working_producer.get("python") or {}),
        "sandbox": None,
        "zlib_version": producer.zlib_version,
    }
    build_steps = parse_steps(working_producer.get("build_steps"))
    if build_steps and corpus_format != "agentprov-corpus/0.1":  # 0.1 is frozen (D-163); D-780 adds the key to 0.2
        producer_json["build_steps"] = build_steps
    if producer_json["lockfile_sha256"] is None:
        producer_json["lockfile_absent_reason"] = "the import ran without the core uv.lock of a source checkout"
    references = _references(reader)
    raw_objects = raw_dispositions(_stored(scan), plan.objects, references)
    counts = corpus_counts(rows, register, members, snapshots, stats)
    rows_by_status = counts["by_status"]
    results = _jsonl(results_bytes)
    manifest: dict[str, Any] = {
        "adapters": adapters,
        "corpus_id": spec.corpus_id,
        "corpus_version": corpus_version,
        "counts": counts,
        "digests": digests_of(rows, raw_objects, index_bytes=index_bytes, register_bytes=register_bytes,
                              members_bytes=members_bytes),
        "duplicates": duplicate_summary(rows, register),
        "facet_schema": facet_schema(),
        "format": corpus_format,
        "formats": {"aer": CORPUS_FORMATS[corpus_format], "capture": None, "corpus": corpus_format, "index": "agentprov-index/0.1",
                    "register": "agentprov-register/0.1", "sem": "sem/0.1" if spec.sem_profiles else None},
        "framework_identities": stats.framework_identities(),
        "layout": {"shard_depth": spec.shard_depth},
        "licences": licences,
        "live": None,
        "mode": spec.mode,
        "models": stats.model_summaries(),
        "ontology": {"iri": "https://w3id.org/agentprov/ns#", "prefix": "apv", "version": ONTOLOGY_VERSIONS[corpus_format]},
        "oracle_specs": [{"gate_report": inputs.gate_reports.get(s), "spec": s, "status": ORACLE_STATUS}
                         for s in sorted(spec.prov_specs) if s in ORACLE_SPECS],
        "producer": producer_json,
        "profiles": {"semantics": semantics_refs,
                     "source": [{"id": spec.source.profile_id, "path": f"rules/{spec.source.profile_id}.profile.toml",
                                 "sha256": working_profile["sha256"], "version": spec.source.profile_version}]},
        "prov_specs": list(spec.prov_specs),
        "rule_catalogues": rule_catalogue_refs(catalogue_refs, stats.rules_used),
        "sources": [{
            "lineage": dict(profile_doc.get("lineage") or {}),
            "mirrors": [],
            "parts": list(spec.source.parts),
            "profile": {"id": spec.source.profile_id, "path": f"rules/{spec.source.profile_id}.profile.toml",
                        "sha256": working_profile["sha256"], "version": spec.source.profile_version},
            "snapshots": snapshots,
            "source_id": spec.source.source_id,
        }],
        "title": spec.title,
        "validation": validation_summary(_json(summary_bytes), validation_stage, results,
                                         aer_format=CORPUS_FORMATS[corpus_format]),
    }  # fmt: skip
    _check_gating(manifest, rows, register, results)
    file_roles = {
        "card": file_ref("rules/CARD.md", inputs.card, jsonl=False),
        "changes": file_ref("rules/CHANGES.toml", inputs.changes, jsonl=False),
        "derivation": file_ref("derivation.json", reader.read_bytes("derivation.json"), jsonl=False),
        "index": file_ref("executions.jsonl", index_bytes, jsonl=True),
        "members": file_ref("raw/members.jsonl", members_bytes, jsonl=True),
        "origins": file_ref("raw/origins.jsonl", reader.read_bytes("raw/origins.jsonl"), jsonl=True),
        "register": file_ref("register.jsonl", register_bytes, jsonl=True),
        "spec": file_ref("rules/corpus-spec.toml", inputs.spec, jsonl=False),
        "validation_results": file_ref("validation/results.jsonl", results_bytes, jsonl=True),
        "validation_summary": file_ref("validation/summary.json", summary_bytes, jsonl=False),
    }
    if withheld_bytes is not None:
        file_roles["withheld"] = file_ref("WITHHELD.json", withheld_bytes, jsonl=False)
    if reader.exists("raw/REFERENCES.json"):  # item 5: a referenced object's ledger is declared like WITHHELD.json
        file_roles["references"] = file_ref("raw/REFERENCES.json", reader.read_bytes("raw/REFERENCES.json"), jsonl=False)
    manifest["files"] = file_roles
    rules_by_code: dict[str, set[str]] = {}
    for entry in register:
        if entry.rule:
            rules_by_code.setdefault(entry.code, set()).add(entry.rule.split("#", 1)[0])
    register_stats: dict[str, Any] = {"rules_by_code": {k: sorted(v) for k, v in rules_by_code.items()}, "withheld": 0}
    if plan.document is not None:
        register_stats["withheld"] = len(plan.document.entries) + len(plan.document.executions)
        register_stats["withheld_summary"] = withheld_summary(plan.document)
    try:
        card_text = inputs.card.decode("utf-8")
    except UnicodeDecodeError:
        raise _refuse("CARD.md is not UTF-8", "card") from None
    # pass 1 evaluates the claims (they enter the content digest); pass 2 renders the text with the content digest
    first = render(manifest, card_text, register_stats, {}, checker=inputs.checker, statements=inputs.statements,
                   field_groups=inputs.field_groups)
    manifest["datasheet"] = {"card_sha256": first.card_sha256, "claims": first.claims,
                             "statements": first.statements, "statements_sha256": first.statements_sha256}
    manifest["content_digest"] = content_digest(manifest)
    rendered = render(manifest, card_text, register_stats, {}, checker=inputs.checker, statements=inputs.statements,
                      field_groups=inputs.field_groups)
    if rendered.claims != first.claims:
        raise ManifestError("the datasheet claims differ between the two rendering passes", code="corpus.manifest.claims")
    files[DATASHEET] = rendered.text.encode("utf-8")
    manifest["release"] = (release or ReleaseArgs()).to_json()
    manifest["sealed"] = True
    issues = validate_manifest(manifest)
    if issues:
        shown = "; ".join(f"{i.pointer or '/'} {i.code}: {i.detail}" for i in issues[:5])
        raise ManifestError(f"the sealed manifest does not validate ({len(issues)} issue(s)): {shown}")
    manifest_bytes = _document_bytes(manifest)
    _refuse_label_collisions([*files, "executions.jsonl", "register.jsonl", "validation/results.jsonl",
                              "validation/summary.json", MANIFEST])
    stage("manifest")
    counters = {"bytes": 0, "executions": len(rows), "failed_rows": rows_by_status["failed"], "files": 0}
    if plan.document is not None:
        counters["withheld_executions"] = len(plan.document.executions)
        counters["withheld_objects"] = len(plan.document.entries)
    if plan.unscanned:
        counters["withheld_unscanned"] = len(plan.unscanned)
    if plan.partial:
        counters["scanned_partial"] = plan.partial
    notices = []
    if plan.unscanned:  # D-454: loud, with each archive's container chain
        shown = "; ".join(plan.unscanned[:20]) + (f"; and {len(plan.unscanned) - 20} more" if len(plan.unscanned) > 20 else "")
        notices.append(f"WITHHELD UNREAD: {len(plan.unscanned)} stored archive(s) the withholding scan could not read in "
                       f"decoded form are withheld (basis unscanned, D-454): {shown}")
    if plan.partial:
        notices.append(f"{plan.partial} stored archive(s) without a usable central directory were scanned by their local "
                       "headers (scanned_partial, D-453)")
    if inputs.field_groups is None:
        notices.append("the field-group coverage table was not computed (agentprov stats is not available to package)")
    if dry_run:
        return SealReport(spec.corpus_id, corpus_version, final, manifest["content_digest"], None, counters, tuple(notices),
                          True)

    writer = _Writer(partial)
    side = _Sidecar(partial, sidecar)
    try:
        if not plan.empty:
            _withhold_files(side, reader, plan, rows_all, withheld_results, withheld_bytes)
        for label in sorted(files):
            writer.write(label, files[label])
        writer.write("executions.jsonl", index_bytes)
        writer.write("register.jsonl", register_bytes)
        writer.write("validation/results.jsonl", results_bytes)
        writer.write("validation/summary.json", summary_bytes)
        writer.write(MANIFEST, manifest_bytes)
        tmp = CorpusLayout(partial).raw_tmp
        if tmp.is_dir():
            tmp.rmdir()  # empty (checked above): an import leaves it behind
        stage("write")
        write_checksums(partial)
        report = verify_checksums(partial)
        if not report.ok:
            raise ManifestError(f"the sealed tree fails its own checksums ({report.codes()})", code="corpus.manifest.checksums")
        reread = CorpusReader(partial, state=WORKING).read_document(MANIFEST)
        if reread != manifest or validate_manifest(reread):
            raise ManifestError("corpus.json does not read back equal", code="corpus.manifest.readback")
        stage("checksums")
        _verify_chain(partial)
        stage("chain")
        digest = root_digest(partial)
        listed = [label for label, _, _ in iter_tree(partial).files]
        counters["files"] = len(listed)
        counters["bytes"] = sum(size for _, _, size in iter_tree(partial).files)
        atomic_swap_dir(partial, final)
        stage("swap")
    except BaseException:
        if partial.is_dir():
            writer.rollback()
            side.rollback()
            CorpusLayout(partial).raw_tmp.mkdir(parents=True, exist_ok=True)
        raise
    return SealReport(spec.corpus_id, corpus_version, final, manifest["content_digest"], digest, counters, tuple(notices),
                      sidecar=None if plan.empty else sidecar)


def _resume(final: Path, partial: Path, *, corpus_version: str, inputs: SealInputs, release: ReleaseArgs | None,
            dry_run: bool) -> SealReport:
    """Finish a seal that died after writing the sealed ``corpus.json`` and before the swap (see the module docstring;
    CB-9). Everything before that write had completed, so only the remaining steps run: remove ``raw/tmp/``, write
    ``checksums.sha256`` if absent, check the checksums and ``verify --level chain``, swap. Each failed check raises
    :class:`SealInterruptedError`; a dry run checks the manifest and the inputs and writes nothing."""

    def refuse(reason: str) -> SealInterruptedError:
        return SealInterruptedError(
            "DIR.partial holds the sealed corpus.json of an interrupted seal (it stopped after writing the sealed manifest "
            f"and before the swap to DIR) and cannot be resumed: {reason}. Rerun package with the inputs of the "
            "interrupted run; if the tree itself is damaged, rebuild the working corpus (import and derive) and seal it "
            "again, since the interrupted run rewrote its working files")

    spec = parse_spec(inputs.spec)
    reader = CorpusReader(partial, state=WORKING)
    try:
        manifest = reader.read_document(MANIFEST)
    except AgentProvError as exc:
        raise refuse(f"corpus.json cannot be read ({exc.code})") from None
    if not isinstance(manifest, Mapping) or validate_manifest(manifest):
        raise refuse("corpus.json does not validate")
    if manifest.get("corpus_id") != spec.corpus_id or manifest.get("corpus_version") != corpus_version:
        raise refuse("it seals another corpus id or version than the one asked for")
    try:
        recomputed = content_digest(manifest)
    except ValueError:
        recomputed = None
    if recomputed != manifest.get("content_digest"):
        raise refuse("its content digest does not recompute")
    if manifest.get("release") != (release or ReleaseArgs()).to_json():
        raise refuse("the release arguments differ from the ones the interrupted run sealed")
    roles = manifest.get("files")
    for role, label, data in (("spec", "rules/corpus-spec.toml", inputs.spec), ("card", "rules/CARD.md", inputs.card),
                              ("changes", "rules/CHANGES.toml", inputs.changes)):
        if not isinstance(roles, Mapping) or roles.get(role) != file_ref(label, data, jsonl=False):
            raise refuse(f"the supplied {label.rsplit('/', 1)[-1]} differs from the one the interrupted run sealed")
    counts = manifest["counts"]
    counters = {"bytes": 0, "executions": counts["executions"], "failed_rows": counts["by_status"]["failed"], "files": 0}
    sidecar = None
    if reader.exists("WITHHELD.json"):
        try:
            document = decode_withheld(reader.read_bytes("WITHHELD.json"), reader.limits)
        except AgentProvError as exc:
            raise refuse(f"WITHHELD.json is not valid ({exc.code})") from None
        counters["withheld_executions"] = len(document.executions)
        counters["withheld_objects"] = len(document.entries)
        sidecar = sidecar_path(final) if os.path.isdir(sidecar_path(final)) else None
    notices = ("resumed an interrupted seal: corpus.json was already sealed and the swap to DIR had not happened",)
    if dry_run:
        return SealReport(spec.corpus_id, corpus_version, final, manifest["content_digest"], None, counters, notices, True)

    try:
        tmp = CorpusLayout(partial).raw_tmp
        if tmp.is_dir():
            tmp.rmdir()  # the interrupted run died before removing it; a non-empty one refuses
        if not os.path.lexists(partial / CHECKSUMS):
            write_checksums(partial)
    except (OSError, AgentProvError) as exc:
        raise refuse(f"the tree cannot be checksummed ({getattr(exc, 'code', type(exc).__name__)})") from None
    report = verify_checksums(partial)
    if not report.ok:
        raise refuse(f"it fails its own checksums ({report.codes()})")
    try:
        _verify_chain(partial)
    except ManifestError as exc:
        raise refuse(str(exc)) from None
    digest = root_digest(partial)
    files = iter_tree(partial).files
    counters["files"] = len(files)
    counters["bytes"] = sum(size for _, _, size in files)
    atomic_swap_dir(partial, final)
    return SealReport(spec.corpus_id, corpus_version, final, manifest["content_digest"], digest, counters, notices,
                      sidecar=sidecar)


#: The seal stages in order, reported as the units of a ``package`` run; a dry run stops after ``manifest``.
SEAL_STAGES: Final = ("withhold", "executions", "manifest", "write", "checksums", "chain", "swap")


class _Stages:
    """``start`` with the number of stages, then ``unit_start``/``unit_done`` per seal stage (N.1.14; metadata only).

    Corpus-level stages are reported as units, so a ``--progress-file`` reader at the ``status`` level sees them."""

    def __init__(self, progress: Progress, *, dry_run: bool) -> None:
        self._progress = progress
        self._stages = SEAL_STAGES[: SEAL_STAGES.index("manifest") + 1] if dry_run else SEAL_STAGES
        self._next = 0
        self._last = time.monotonic()
        progress.emit(ProgressEvent("start", total=len(self._stages), fields={"command": "package", "plan": "seal"}))
        self._open(self._stages[0])

    def _open(self, name: str) -> None:
        self._progress.emit(ProgressEvent("stage", stage=name, fields={"phase": "begin"}))  # 0.2 (D-393)
        self._progress.emit(ProgressEvent("unit_start", unit=name))

    def __call__(self, name: str) -> None:
        now = time.monotonic()
        self._progress.emit(ProgressEvent("unit_done", unit=name, status="ok", duration_s=now - self._last))
        self._progress.emit(ProgressEvent("stage", stage=name, duration_s=now - self._last, fields={"phase": "end"}))
        self._last = now
        self._next = self._stages.index(name) + 1
        if self._next < len(self._stages):
            self._open(self._stages[self._next])


# ================================================================================================ withholding
def sidecar_path(final: Path) -> Path:
    """``DIR.withheld/``: the private sidecar beside the sealed corpus ``DIR`` (D-231). Never part of a corpus or a
    deposit; deleting it is the user's decision."""
    return final.with_name(final.name + SIDECAR_SUFFIX)


def _release_date(release: ReleaseArgs | None) -> str | None:
    created = (release or ReleaseArgs()).to_json()["created"]
    return created[:10] if isinstance(created, str) else None


def _plan(reader: CorpusReader, partial: Path, scan: Any, rows: Sequence[IndexRow], register: Sequence[Any],
          members: Sequence[Any], origins: Sequence[Any], source: Mapping[str, Any], snapshot_spec: Mapping[str, Any],
          profile: bytes, spec: CorpusSpec, release: ReleaseArgs | None, catalogues: Mapping[str, int],
          spec_bytes: bytes = b"", persona_files: Mapping[str, bytes] | None = None) -> WithholdPlan:
    """The withholding plan of this seal (:mod:`agentprov.corpus.withhold`); a refused policy or plan is exit 4. The
    policy is read with :func:`agentprov.corpus.withhold.load_policy` (an issue rule's code checked against the
    catalogues the import used, D-311), as ``chain`` and the deposit builder read it from the profile copy under
    ``rules/``."""
    from agentprov.corpus.withhold import load_policy, withhold_address_classes

    persona_files = persona_files or {}
    listed = (frozenset(o.removeprefix("sha256:") for o in spec.withhold_objects), frozenset(spec.withhold_executions))
    try:
        held, objects = withhold_address_classes(spec_bytes, lambda name: persona_files.get(name))
        policy = load_policy(profile, profile_id=spec.source.profile_id, profile_version=spec.source.profile_version,
                             catalogues=catalogues, addresses=held, object_addresses=objects, listed=listed)
    except WithholdError as exc:
        raise _refuse(str(exc), "withhold_policy") from None
    tombstones: list[Any] = []
    if reader.exists("raw/tombstones.jsonl"):
        from agentprov.corpus.purge import decode_tombstones

        try:
            tombstones = decode_tombstones(reader.read_bytes("raw/tombstones.jsonl"), reader.limits)
        except AgentProvError as exc:
            raise _refuse(f"raw/tombstones.jsonl is not valid ({exc.code})", "tombstones") from None
    layout = CorpusLayout(partial)

    def stream(label: str) -> Iterator[bytes]:
        with reader.open_file(label, stored=True) as handle:
            while chunk := handle.read(1 << 20):
                yield chunk

    def artefacts(row: IndexRow) -> Sequence[Mapping[str, Any]]:
        try:
            listed = reader.read_aer(row).header.get("artifacts")
        except AgentProvError:
            return ()
        return [a for a in listed if isinstance(a, Mapping)] if isinstance(listed, list) else ()

    snapshots = {str(s["snapshot_id"]): (snapshot_spec[s["snapshot_id"]].raw_policy, s.get("pin"))
                 for s in source["snapshots"]}  # fmt: skip
    try:
        return plan_withholding(
            rows=rows, register=register, members=members, origins=origins,
            present={_object_hex(label): (label, size) for label, role, size in scan.files if role == "raw_object"},
            tombstones=tombstones, snapshots=snapshots, stream=stream,
            derived=lambda row: derived_labels(layout, row, reader.exists), artefacts=artefacts, policy=policy,
            decided_on=_release_date(release),
        )  # fmt: skip
    except WithholdError as exc:
        raise _refuse(str(exc), exc.code.rsplit(".", 1)[-1]) from None


def _catalogue_versions(derivation: Mapping[str, Any] | None) -> dict[str, int]:
    """Namespace -> version of the rule catalogues the AER and SEM stages used (``derivation.json``)."""
    out: dict[str, int] = {}
    for name in ("aer", "sem"):
        for ns, version in dict((_stage(derivation, name) or {}).get("rules", {})).items():
            if isinstance(version, int) and not isinstance(version, bool):
                out.setdefault(str(ns), version)
    return out


def _object_hex(label: str) -> str:
    return label.rsplit("/", 1)[-1].split(".", 1)[0]


def _stored(scan: Any) -> list[str]:
    return sorted(_object_hex(label) for label, role, _ in scan.files if role == "raw_object")


def _references(reader: CorpusReader) -> list[str]:
    """The digests ``raw/REFERENCES.json`` lists (bare hex), or none."""
    if not reader.exists("raw/REFERENCES.json"):
        return []
    from agentprov.raw.references import parse_references

    try:
        return sorted({r.sha256 for r in parse_references(reader.read_bytes("raw/REFERENCES.json"), reader.limits)})
    except AgentProvError as exc:
        raise _refuse(f"raw/REFERENCES.json is not valid ({exc.code})", "references") from None


def _json(data: bytes) -> dict[str, Any]:
    from agentprov.ingest.loaders import strict_json_loads

    value = strict_json_loads(data)
    return value if isinstance(value, dict) else {}


def _jsonl(data: bytes) -> list[dict[str, Any]]:
    import io

    from agentprov.ingest.loaders import iter_jsonl

    return [value for _, _, value in iter_jsonl(io.BytesIO(data)) if isinstance(value, dict)]


class _Sidecar:
    """The private sidecar ``DIR.withheld/`` (D-231): files of the working tree are **renamed** into it (never copied
    and deleted, never deleted), and :meth:`rollback` renames them back when sealing fails."""

    def __init__(self, partial: Path, root: Path) -> None:
        self.partial = partial
        self.root = root
        self.moved: list[str] = []
        self.written: list[Path] = []
        self.created = False

    def _ensure(self) -> None:
        if not self.created:
            os.mkdir(self.root, 0o700)  # fails when it exists: a sidecar is never overwritten
            self.created = True

    def move(self, label: str) -> None:
        self._ensure()
        source = self.partial.joinpath(*label.split("/"))
        target = self.root.joinpath(*label.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(target):
            raise ManifestError("a sidecar file exists already", code="corpus.manifest.sidecar")
        os.rename(source, target)
        self.moved.append(label)
        _fsync_dir(target.parent)
        _fsync_dir(source.parent)
        _prune_up(self.partial, label)

    def write(self, label: str, data: bytes) -> None:
        self._ensure()
        path = self.root.joinpath(*label.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, data)
        self.written.append(path)

    def rollback(self) -> None:
        for label in reversed(self.moved):
            source = self.partial.joinpath(*label.split("/"))
            source.parent.mkdir(parents=True, exist_ok=True)
            os.rename(self.root.joinpath(*label.split("/")), source)
        self.moved.clear()
        for path in reversed(self.written):
            try:
                path.unlink()  # a copy this seal wrote (the withheld rows, WITHHELD.json); the originals are untouched
            except FileNotFoundError:
                pass
        self.written.clear()
        if self.created:
            _prune(self.root)
            self.created = False


def _prune_up(root: Path, label: str) -> None:
    """Remove the directories ``label`` leaves empty below ``root`` (a sealed tree has no empty directory, H.1.5(4))."""
    parts = label.split("/")[:-1]
    while parts:
        try:
            os.rmdir(root.joinpath(*parts))
        except OSError:
            return
        parts.pop()


def _withhold_files(side: _Sidecar, reader: CorpusReader, plan: WithholdPlan, rows: Sequence[IndexRow],
                    results: Sequence[Mapping[str, Any]], withheld_bytes: bytes | None) -> None:
    """Rename every file of a withheld execution and every stored withheld object into the sidecar, and record there the
    withheld index rows, their validation rows and a copy of ``WITHHELD.json``."""
    layout = CorpusLayout(side.partial)
    held = [row for row in rows if row.ex in plan.executions]
    for row in held:
        for label in derived_labels(layout, row, reader.exists):
            side.move(label)
    for _sha, label in sorted(plan.present.items()):
        side.move(label)
    side.write("executions.jsonl", encode_index(held))
    if results:
        side.write("validation/results.jsonl", b"".join(jcs_bytes(r) + b"\n" for r in results))
    if withheld_bytes is not None:
        side.write("WITHHELD.json", withheld_bytes)


def _verify_chain(partial: Path) -> None:
    """N.2.11 step 3: ``verify --level chain`` over the tree just sealed (still named ``DIR.partial``), in release mode
    (an unverified or tombstoned finding blocks sealing too). A failure is a corpus-level check failure (exit 1)."""
    from agentprov.corpus.reader import SEALED
    from agentprov.corpus.verify import verify_corpus

    report = verify_corpus(reader=CorpusReader(partial, state=SEALED), level="chain")
    if not report.passed(release=True):
        shown = ", ".join(f"{code} x{n}" for code, n in list(report.codes().items())[:8])
        raise ManifestError(f"the sealed tree fails verify --level chain ({shown})", code="corpus.manifest.verify")


def _document_bytes(document: Mapping[str, Any]) -> bytes:
    """A single JSON document of the corpus layer (H.1.4(2)): sorted keys, two-space indentation, UTF-8, final LF."""
    import json

    return (json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _parse_profile(data: bytes) -> dict[str, Any]:
    try:
        return tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise _refuse("the supplied source profile is not valid UTF-8 TOML", "profile") from None


# the register codes that say an execution failed with gating checks failed (H.2.12): ``validate.failed``, or the stage
# failure derive and import register instead when PROV or SEM failed while the tier-3 checks still ran
_GATING_FAILURE_CODES = frozenset({"validate.failed", "prov.failed", "sem.failed"})


def _check_gating(manifest: Mapping[str, Any], rows: Sequence[IndexRow], register: Iterable[Any],
                  results: Iterable[Mapping[str, Any]]) -> None:
    """H.2.12: in strict mode no gating check is skipped, and a failed gating check is allowed only for an execution
    whose index row is ``failed`` and whose register entries say so (:data:`_GATING_FAILURE_CODES`). This is judged per
    execution over ``results`` (the rows of ``validation/results.jsonl``), and the manifest's summed ``fail`` must not
    exceed the failed checks of the executions that pass that test."""
    validation = manifest["validation"]
    if any(c["skipped"] for c in validation["checks"]):
        raise ManifestError("strict validation: a gating check was skipped (H.2.12)", code="corpus.manifest.validation")
    failed_checks = sum(c["fail"] for c in validation["checks"])
    if failed_checks:
        gating = {str(c["id"]) for c in validation["checks"]}
        flagged = {e.subject.get("ex") for e in register if e.code in _GATING_FAILURE_CODES}
        failed_rows = {r.ex for r in rows if r.status == "failed"}
        covered = 0
        for result in results:
            # an outcome outside the four R-64 values counts as fail, as validation/summary.json counts it
            fails = sum(1 for cid, outcome in dict(result.get("checks", {})).items()
                        if cid in gating and outcome not in ("pass", "skipped", "not_applicable"))
            if not fails:
                continue
            if result.get("ex") not in failed_rows or result.get("ex") not in flagged:
                raise ManifestError("a gating check failed for an execution that is not a failed, registered row "
                                    "(H.2.12)", code="corpus.manifest.validation")
            covered += fails
        if failed_checks > covered:
            raise ManifestError("the validation summary counts more gating failures than the failed, registered rows "
                                "have (H.2.12)", code="corpus.manifest.validation")

