"""The import pipeline: ``import_source`` and the source trees it reads (docs/architecture D.2.9; MN N.2.2; HL H.1, H.6).

``import_source`` is the product path of ``agentprov import`` (layer L6; it receives an opened
:class:`~agentprov.corpus.writer.CorpusWriter`, M.5.2(1)). For one source part and one snapshot it:

1. **discovers** candidates through the reader's ``iter_artefacts`` (profile include/exclude globs, strays skipped,
   sorted labels); exclude-glob matches are counted ``excluded``, input-tree rejections that match an include glob become
   ``ingest.*`` register entries;
2. **stores** every candidate in the raw store before anything parses it, with its origin (``git`` from a pinned tree, the
   pinned origin of ``--verify-against-pin``, else ``local``); identical bytes at a second location add an origin row and
   a ``dedup.collapsed`` entry, never a second execution (H.7.2); an artefact already indexed is ``skipped_resume``
   (for a ``multi_execution`` reader each execution is checked by its source key after mapping instead; R-10k-1, D-320);
3. **expands** containers (a reader with ``plan`` and ``member_patterns``: the Inspect ``.eval`` family) through the
   versioned ``expand`` stage into member objects (AD-12);
4. **maps** in T1 workers (``map`` jobs; ``total`` mode for whole-file dialects, ``container`` mode for planned
   containers), **seals** in the parent (the write gate, :class:`~agentprov.aer.writer.AerWriter`), runs the AER validator
   with locators resolved against the raw store, applies the post-mapping filters, and writes the AER and the register
   entries of its seal issues (``map.<code>``);
5. **derives and validates** in T1 workers (``prov`` jobs: ``agentprov-prov/0.1`` and the tier-4 validators) over the
   sealed bytes, overlapped with the mapping of the next batch, and writes the PROV-JSON, the validation row and the index
   entry;
6. **closes**: the writer flushes the four logs and ``validation/``; ``derivation.json`` (engine version and code digest
   per stage, DECISIONS D-13) and the working ``corpus.json`` are written.

Every candidate ends in exactly one disposition (HL R1) unless a filter or ``--limit`` makes the corpus partial; an
in-scope artefact that cannot be mapped is sealed as a degenerate AER (D.2.8 case 3), never dropped. Output bytes do not
depend on the worker count, ``--in-process`` or the batch size: results are consumed in candidate order and every log is
sorted when written.

Nothing here prints. Strings from sources reach the register only as codes, generated details and labels.
"""

from __future__ import annotations

import dataclasses

import functools
import hashlib
import io
import logging
import os
import json
import platform
import shutil
import sys
import tempfile
import threading
import time
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Concatenate, Final, Literal

from agentprov.adapters.account_paths import account_shapes, covered, redaction_patterns
from agentprov.adapters.code_verification import rule_class
from agentprov.adapters.profiles import SourceProfile, load_profile
from agentprov.adapters.runner import (
    FrameSummary,
    MapContext,
    MapOutcome,
    _degenerate,
    degenerate_unit,
    iter_unit_frames,
    multi_execution,
    streams,
    outcome_from_frames,
    resolve_factory,
    seal_outcome,
    summarise_unit_frames,
)
from agentprov.adapters.types import CandidateArtefact, ExecutionUnit, Locator
from agentprov.aer import AER_FORMAT_ID
from agentprov.aer.ids import canonical_key_loc, import_execution_id, mapping_id
from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.aer.validate import AerValidator
from agentprov.aer.writer import AerWriteError
from agentprov.corpus.dedup import source_key
from agentprov.corpus.facets import LOSS_CODES, kept_results
from agentprov.corpus.facets import proven_loss_codes as _proven_loss_codes
from agentprov.corpus.index import ExecutionEntry, IndexLog, RawRef, StageOutput
from agentprov.corpus.reader import CORPUS_FORMAT
from agentprov.corpus.register import RegisterEntry, RegisterError
from agentprov.corpus.runstate import incomplete_record, is_incomplete_record
from agentprov.corpus.selection import is_import_selection, selection_key, snapshot_selections
from agentprov.corpus.stages import in_order, stage_key, stage_map
from agentprov.corpus.writer import CorpusWriter
from agentprov.envinfo import interpreter_advisory
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import PathRejection, discover, open_evidence
from agentprov.io.canonical import jcs_bytes, sha256_hex
from agentprov.io.workers import Job, JobResult, WorkerPool
from agentprov.progress import NULL_PROGRESS, Progress, ProgressEvent
from agentprov.raw.fetch import Fetcher, Recipe, TreeEntry, is_split_pin, split_pin_record
from agentprov.raw.history import HistoryIndex
from agentprov.raw.members import ContainerSpec, Selection, expand_fn_definition, nested_selection, split_descriptor
from agentprov.raw.origins import Origin, OriginUnpinnedError
from agentprov.raw.store import RawObjectStore, ext_for_label
from agentprov.sem.reader import load_sem_bytes
from agentprov import stage_definitions as _shared
from agentprov.stage_scopes import aer_scope
from agentprov.versions import __version__

__all__ = [
    "SELECT_KEYS",
    "SPEC_ID",
    "UNTIL",
    "GitPinTree",
    "ContextTree",
    "IdentityRefusedError",
    "ImportFilters",
    "ImportReport",
    "LocalTree",
    "PinCheck",
    "PinnedObject",
    "UnpinnedInputError",
    "aux_media",
    "code_sha256",
    "git_blob_sha1",
    "import_source",
    "listing_sha256",
]

_LOG = logging.getLogger(__name__)

SPEC_ID: Final = "agentprov-prov/0.1"
UNTIL: Final = ("raw", "aer", "sem", "prov", "validation")
DEFAULT_BATCH: Final = 256
_STRAYS: Final = (".DS_Store",)
#: Seal issues whose register disposition is ``failed`` (HL H.6.3 ``map.<seal code>`` row).
_FAILED_CODES: Final = frozenset({"unparseable_artefact", "adapter_defect", "ex_conflict"})
#: Register severities that HL H.6.3 states for core seal issues (the accounting mirrors the writer adds, the D.2.8 case-3
#: errors, and the trajectory and outcome examples). They take precedence over a mapper's default ``warning``; every other
#: code keeps the severity the mapper reported (D.2.7 ``Issue.severity``).
_FIXED_SEVERITY: Final[Mapping[str, str]] = {
    "accounting_inconsistent": "warning",
    "accounting_unverifiable": "info",
    "earlier_attempts_unobservable": "info",
    "retry_passes_inferred": "warning",
    "no_execution_observed": "warning",
    "incomplete_run": "warning",
    "outcome_imposed_by_runner": "warning",
    "unparseable_artefact": "error",
    "unsupported_variant": "error",
    "adapter_defect": "error",
    "ex_conflict": "error",
}
_DEGENERATE_CODES: Final = frozenset({"unparseable_artefact", "unsupported_variant", "adapter_defect"})
#: D-321: the register codes a ``multi_execution`` reader's ``rejected`` rows may carry (H.6.3, stage ``select``).
_REJECTED_CODES: Final = frozenset({"select.not_execution_artefact", "select.out_of_scope"})
#: Seal issues an adapter rule raises only when it proves loss (H.3.2(2): ``known_incomplete``; item 11 adds
#: ``missing_tool_result``). The proof itself is :func:`agentprov.corpus.facets.proven_loss_codes`, shared with derive.
_LOSS_CODES: Final = LOSS_CODES


def proven_loss_codes(issues: Iterable[Mapping[str, Any]], kept: Collection[str] = ()) -> frozenset[str]:
    """The loss codes among ``issues`` that a class-D rule proves (H.3.2(2): "an adapter rule proves loss").

    A loss issue that cites only an I rule, such as the retry inference under an ``_unverified`` twin for a harness whose
    code is not verified (D.5.4, D-24; analysis B6), infers the loss and does not prove it, so it leaves the execution
    ``unverifiable``. An issue without a rule proves nothing; a ``missing_tool_result`` whose executions all generated
    an artefact (``kept``) is a declared removal, not a loss (D-372)."""
    return _proven_loss_codes(issues, rule_class, kept)


def index_completeness(*, degenerate: bool, accounting: str, checks_evaluated: int, unit_kind: str,
                       seal_codes: frozenset[str] | set[str]) -> str:
    """The index ``completeness`` of an import (HL H.3.2(2); D.2.9 item 8).

    ``known_incomplete`` when the seal accounting is ``inconsistent`` or an adapter rule proves loss. ``verified_complete``
    only when the source records enough to reconcile: the seal accounting is ``consistent`` **because at least one
    accounting check was evaluated** and the unit is an ``agent_execution``. ``fold_status`` of no verdicts is
    ``consistent`` (vacuously; the frozen ``aer/0.1`` seal is not changed), so an execution with no evaluated check (an
    outcome-only record, an empty log, a run error before the first assistant turn) is ``unverifiable``, as is a
    degenerate AER and every other case.
    """
    if degenerate:
        return "unverifiable"
    if accounting == "inconsistent" or seal_codes & _LOSS_CODES:
        return "known_incomplete"
    if accounting == "consistent" and checks_evaluated > 0 and unit_kind == "agent_execution":
        return "verified_complete"
    return "unverifiable"
_SEVERITY_ORDER: Final = {"info": 0, "warning": 1, "error": 2}

#: ``--select`` keys of phase 6: fields of the AER header (index facets arrive with SEM, phase 7). Applied after mapping.
SELECT_KEYS: Final[Mapping[str, Callable[[Mapping[str, Any]], object]]] = {
    "attack": lambda h: (h.get("task") or {}).get("attack_id") or "none",
    "benchmark": lambda h: (h.get("task") or {}).get("benchmark"),
    "defense": lambda h: (h.get("task") or {}).get("defense_id") or "none",
    "suite": lambda h: (h.get("task") or {}).get("suite"),
    "task": lambda h: (h.get("task") or {}).get("task_id"),
    "unit": lambda h: h.get("unit"),
    "variant": lambda h: (h.get("dialect") or {}).get("variant"),
}



def _unlink_object(path: Path) -> None:
    """Remove a scratch raw object. Objects are stored read-only, and Windows refuses to unlink a read-only file."""
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        os.chmod(path, 0o600)
        path.unlink(missing_ok=True)


def _make_writable_and_retry(function: Any, path: str, _exc: BaseException) -> None:
    """``shutil.rmtree`` error handler for the private scratch tree: clear the read-only bit and retry once."""
    os.chmod(path, 0o700 if os.path.isdir(path) else 0o600)
    function(path)

class SampleRefusedError(AgentProvError):
    """D-529: a sample this part cannot draw (``spread`` for a reader that names no stratum). Exit 5 (unsupported)."""

    code = "import.sample.unsupported"
    exit_code = 5


class IdentityRefusedError(AgentProvError):
    """G4 (MN N.1.9): the working corpus was begun with another identity or other function versions. Exit 4."""

    code = "corpus.identity_mismatch"
    exit_code = 4


class UnpinnedInputError(AgentProvError):
    """A local ``--input`` tree without a pin check (exit 4).

    Its artefacts could only carry ``local`` origins, and the AER writer seals every AER in release mode, where a local
    origin is an error (C.17 AER-V20, ``local_origin``): no AER could be written. The tree must be vouched for by a pin
    (``--verify-against-pin``) or read from the pin itself (``--fetch``)."""

    code = "raw.origin.local"
    exit_code = 4


# ================================================================================================ helpers
def git_blob_sha1(data: bytes) -> str:
    """The git blob id of ``data`` (``sha1("blob <size>\\0" + bytes)``; an object id, not a security digest)."""
    import hashlib

    digest = hashlib.sha1(b"blob %d\0" % len(data), usedforsecurity=False)
    digest.update(data)
    return digest.hexdigest()


def listing_sha256(entries: Iterable[tuple[str, str]]) -> str:
    """The J.1.4 tree-listing digest over ``(relpath, sha256)`` pairs: ``"<sha256>  <relpath>\\n"`` lines sorted by path."""
    import hashlib

    listing = "".join(f"{digest}  {rel}\n" for rel, digest in sorted(entries))
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def _match(label: str, glob: str) -> bool:
    """The families' include/exclude matcher: ``fnmatch`` over a POSIX label, ``**/`` also matching zero directories."""
    import fnmatch

    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


def _is_stray(label: str) -> bool:
    name = label.rsplit("/", 1)[-1]
    return name in _STRAYS or name.startswith("._")


#: Media types of per-unit auxiliary files by label suffix (runner items R1-R3, D.16.14; DTap sample-check fix b2): the
#: same JSON is ``application/json`` whether it is a unit's primary or another unit's supporting artefact. Labels are
#: only inspected (case-folded suffix), never opened; any other suffix stays ``application/octet-stream``.
_AUX_MEDIA: Final = ((".json", "application/json"), (".yaml", "application/yaml"), (".yml", "application/yaml"))


def aux_media(label: str) -> str:
    """The media type recorded for an auxiliary artefact with ``label`` (``"<role>:<label>"`` context refs included)."""
    lowered = label.lower()
    return next((media for suffix, media in _AUX_MEDIA if lowered.endswith(suffix)), "application/octet-stream")


# ultrareview pipeline nit: one implementation, shared with corpus.derive (agentprov.stage_definitions)
code_sha256 = _shared.code_sha256
_versions = _shared.versions
_detail = _shared.detail


# ================================================================================================ source trees
class LocalTree:
    """``--input PATH``: a directory, or one file, read in place through ``agentprov.ingest.paths`` (G.3.6).

    A directory is walked without following links; symlinks, special files and (unless ``allow_hardlinks``) files with
    several links are rejections, kept on :attr:`rejections`. Every file is opened with the no-follow opener, checked as a
    regular file and read under ``max_artefact_bytes``. A single file is the one candidate (its label is its name); the
    profile include globs do not apply to it (:attr:`explicit`). Origins are ``local`` (dev only; release mode refuses
    them) unless a :class:`PinCheck` verifies a file against the pin.
    """

    kind: Final = "local"

    def __init__(self, path: str | os.PathLike[str], *, limits: IngestLimits | None = None, allow_hardlinks: bool = False) -> None:
        self.given = os.fspath(path)
        resolved = os.path.realpath(self.given)
        self.limits = limits or IngestLimits()
        self.allow_hardlinks = allow_hardlinks
        if os.path.isdir(resolved):
            self.root, self.single = resolved, None
        else:
            self.root, self.single = os.path.dirname(resolved), os.path.basename(resolved)
        self.rejections: list[PathRejection] = []

    @property
    def explicit(self) -> bool:
        return self.single is not None

    def _origin(self, label: str) -> Origin:
        return Origin.local(os.path.join(self.root, *label.split("/")))

    def walk(self) -> Iterator[CandidateArtefact]:
        if self.single is not None:
            st = os.lstat(os.path.join(self.root, self.single))
            yield CandidateArtefact(self.single, st.st_size, self._origin(self.single))
            return
        found = discover(self.root, self.limits, allow_hardlinks=self.allow_hardlinks)
        self.rejections = list(found.rejected)
        for item in found.files:
            yield CandidateArtefact(item.label, item.size, self._origin(item.label))

    def open(self, label: str, *, max_bytes: int | None = None) -> bytes:
        limits = self.limits if max_bytes is None else self.limits.replace(max_artefact_bytes=max_bytes)
        with open_evidence(self.root, label, limits, allow_hardlinks=self.allow_hardlinks) as stream:
            return stream.read()

    def read(self, batch: Sequence[CandidateArtefact]) -> Iterator[tuple[CandidateArtefact, bytes | IngestError]]:
        for candidate in batch:
            try:
                yield candidate, self.open(candidate.label)
            except IngestError as exc:
                yield candidate, exc

    def snapshot_origin(self) -> dict[str, Any]:
        return {"kind": "local", "path": Origin.local(self.given).data["path"]}


class GitPinTree:
    """``--fetch``: the blobs under a git pin's tree in the verified fetch cache (``raw.fetch``; no checkout, no network
    when the commit is cached). Every blob is read back with its SHA-1 recomputed against the tree entry; the origin is
    ``git`` ``{repo, commit, path, blob_sha1}`` (G.7.5)."""

    kind: Final = "git"
    explicit: Final = False

    def __init__(self, fetcher: Fetcher, recipe: Recipe, *, limits: IngestLimits | None = None) -> None:
        self.fetcher, self.recipe = fetcher, recipe
        #: the import's limits: a blob over ``max_artefact_bytes`` is one candidate's ``ingest.size.file``, as in the
        #: other trees, never an error that ends the import (ultrareview pipeline #1)
        self.limits = limits or IngestLimits()
        entries, _skipped = fetcher.git_tree(recipe)
        self.entries: dict[str, TreeEntry] = {e.path: e for e in entries if e.is_blob}
        self.rejections: list[PathRejection] = []
        #: The cached introducing-commit index of the pin (D.6.16), or None: the origins then carry no ``introduced_in_commit``.
        self.history = fetcher.history_index(recipe)

    def walk(self) -> Iterator[CandidateArtefact]:
        assert self.recipe.repo is not None and self.recipe.commit is not None
        for path in sorted(self.entries, key=lambda p: p.encode("utf-8")):
            entry = self.entries[path]
            introduced = self.history.lookup(path, entry.oid) if self.history is not None else None
            yield CandidateArtefact(
                path, entry.size or 0,
                Origin.git(self.recipe.repo, self.recipe.commit, path, entry.oid, introduced_in_commit=introduced),
            )

    def open(self, label: str, *, max_bytes: int | None = None) -> bytes:
        """One blob, read under ``max_bytes`` (else the import's ``max_artefact_bytes``), as ``LocalTree.open``: an
        over-limit blob is ``ingest.size.file``, raised before it is fetched when its tree entry says so (V-7)."""
        limit = self.limits.max_artefact_bytes if max_bytes is None else max_bytes
        entry = self.entries[label]
        if (entry.size or 0) > limit:
            raise size_error(entry.size or 0, limit)
        data = next(self.fetcher.iter_git_blobs(self.recipe, [entry])).data
        if len(data) > limit:
            raise size_error(len(data), limit)
        return data

    def read(self, batch: Sequence[CandidateArtefact]) -> Iterator[tuple[CandidateArtefact, bytes | IngestError]]:
        limit = self.limits.max_artefact_bytes
        fits = [c for c in batch if (self.entries[c.label].size or 0) <= limit]  # the tree entry's size, before reading
        blobs = iter(self.fetcher.iter_git_blobs(self.recipe, [self.entries[c.label] for c in fits]))
        for candidate in batch:
            size = self.entries[candidate.label].size or 0
            data = next(blobs).data if size <= limit else None
            if data is None or len(data) > limit:
                yield candidate, size_error(size if data is None else len(data), limit)
            else:
                yield candidate, data

    def snapshot_origin(self) -> dict[str, Any]:
        return {"kind": "git", "repo": self.recipe.repo, "commit": self.recipe.commit, "subtree": ",".join(self.recipe.paths)}


def size_error(size: int, limit: int) -> IngestError:
    """``ingest.size.file`` for one candidate (no path or content in the message)."""
    return IngestError("ingest.size.file", f"artefact of {size} bytes exceeds the {limit}-byte limit")


def read_pinned(obj: PinnedObject, limits: IngestLimits) -> bytes | IngestError:
    """A D.16.14 R3 pinned object's verified local copy, read no further than the import's ``max_artefact_bytes``
    (ultrareview pipeline #1): an over-limit object is that candidate's ``ingest.size.file``."""
    limit = limits.max_artefact_bytes
    if obj.size > limit:
        return size_error(obj.size, limit)
    with open(obj.path, "rb") as handle:
        data = handle.read(limit + 1)
    return size_error(len(data), limit) if len(data) > limit else data


#: Pin kinds that deliver one downloaded file (D-200): the file is an archive input whose members are the artefacts.
#: ``url`` (D-455) also needs a recorded retrieval time: a URL is a mutable origin (H.2.3).
DOWNLOAD_PIN_KINDS: Final = ("zenodo", "hf", "url")


class ArchiveTree:
    """An archive input (D-200): one downloaded file of a download pin (a Zenodo or Hugging Face file) whose **members**
    are the source's artefacts, read in place and never extracted (AD-12; G.3.1 step 3).

    The file was checked against its pin before this tree is built (``raw.fetch.verify_download`` for ``--input``; the
    fetch cache's own check for ``--fetch``): ``sha256`` and ``size`` are the verified values. :meth:`walk` yields the
    container as the one candidate, with the pin's origin (``zenodo {doi, file}``, ``hf {repo, revision, path}`` or ``url
    {url, retrieved}``). The pipeline stores it, expands it through the versioned ``expand`` stage with the profile's selection, and imports the
    selected members (origin ``member``) as the snapshot's candidates; see ``_Pipeline.archive_members``.
    """

    kind: Final = "archive"
    explicit: Final = False
    archive_input: Final = True

    def __init__(self, path: str | os.PathLike[str], *, pin: Mapping[str, Any], sha256: str, size: int,
                 limits: IngestLimits | None = None, retrieved_at: str | None = None) -> None:
        kind = pin.get("kind")
        file = pin.get("file", pin.get("path"))
        if kind not in DOWNLOAD_PIN_KINDS or not isinstance(file, str):
            raise AgentProvError("an archive input needs a zenodo, hf or url pin naming its file", code="adapter.archive_input")
        self.path = os.path.realpath(os.fspath(path))
        self.limits = limits or IngestLimits()
        self.pin = dict(pin)
        self.sha256, self.size = sha256, size
        self.label = file.rsplit("/", 1)[-1]
        #: D-455: when a url pin's file was retrieved (RFC 3339 UTC), recorded in the working manifest's snapshot pin.
        self.retrieved_at: str | None = None
        if kind == "zenodo":
            self.origin = Origin.zenodo(str(pin.get("doi")), file)
        elif kind == "hf":
            self.origin = Origin.hf(str(pin.get("dataset", pin.get("repo"))), str(pin.get("revision")), file)
        else:
            self.retrieved_at = _recorded_retrieval(pin, retrieved_at)
            self.origin = Origin.url(str(pin.get("url")), self.retrieved_at[:10])
        self.rejections: list[PathRejection] = []
        #: D-249: the byte parts of a split archive input, in the pin's order (``None`` for one downloaded file).
        self.archive_parts: list[ArchivePart] | None = None

    def walk(self) -> Iterator[CandidateArtefact]:
        yield CandidateArtefact(self.label, self.size, self.origin)

    def stream(self, label: str) -> Any:
        """The container opened read-only, without following a link, as a regular file (G.3.6)."""
        return open_evidence(os.path.dirname(self.path), os.path.basename(self.path), self.limits)

    def read(self, batch: Sequence[CandidateArtefact]) -> Iterator[tuple[CandidateArtefact, bytes | IngestError]]:
        for candidate in batch:
            try:
                with self.stream(candidate.label) as handle:
                    yield candidate, handle.read()
            except IngestError as exc:
                yield candidate, exc

    def snapshot_origin(self) -> dict[str, Any]:
        return {**self.origin.to_json(), "sha256": "sha256:" + self.sha256, "bytes": self.size}

    @classmethod
    def split(cls, parts: Sequence[tuple[str | os.PathLike[str], str, int]], *, pin: Mapping[str, Any],
              limits: IngestLimits | None = None) -> ArchiveTree:  # fmt: skip
        """An archive input stored as byte parts (D-249): ``parts`` are ``(local path, sha256, size)`` in the pin's order,
        each already checked against its part pin (``raw.fetch.verify_parts``). The container is the split descriptor
        (D-244); each part keeps its own pinned origin (``zenodo {doi, file: <part>}`` or ``hf {repo, revision, path:
        <part>}``) and the descriptor gets a ``split`` origin."""
        from agentprov.raw.fetch import part_recipes

        if pin.get("kind") == "url":
            raise AgentProvError("a url pin names one file; an archive in byte parts is pinned on Zenodo or Hugging Face",
                                 code="adapter.archive_input")
        recipes = part_recipes(pin)
        if len(recipes) != len(parts):
            raise AgentProvError("one local part per pinned part", code="adapter.archive_input")
        declared = [(sha, size) for _path, sha, size in parts]
        sha256 = sha256_hex(split_descriptor(declared))
        tree = cls(os.fspath(parts[0][0]), pin={**pin, "file": pin.get("file", pin.get("path"))}, sha256=sha256,
                   size=sum(size for _sha, size in declared), limits=limits)  # fmt: skip
        tree.origin = Origin.split(tree.label, [sha for sha, _size in declared])
        tree.archive_parts = [
            ArchivePart(str(r.file), sha, size, Origin.zenodo(str(pin.get("doi")), str(r.file)) if r.kind == "zenodo"
                        else Origin.hf(str(r.repo), str(r.revision), str(r.file)), os.path.realpath(os.fspath(path)))
            for r, (path, sha, size) in zip(recipes, parts, strict=True)
        ]  # fmt: skip
        return tree

    def open_part(self, part: ArchivePart) -> Any:
        """A part's local copy, opened read-only without following a link (G.3.6)."""
        assert part.path is not None
        return open_evidence(os.path.dirname(part.path), os.path.basename(part.path), self.limits)


def _recorded_retrieval(pin: Mapping[str, Any], fetched: str | None) -> str:
    """The retrieval time of a url archive input (D-455; H.2.3 ``url retrieved_at``): the fetch's acquisition record, else
    the pin's own ``retrieved_at``. Never the time of the import: with neither, the import is refused (exit 3, invariant 2)."""
    from agentprov.raw.fetch import RETRIEVED_AT

    if "retrieved" in pin:  # a date-only key would leave the sealed retrieved_at's time of day to be filled in
        raise OriginUnpinnedError("a url pin records retrieved_at (RFC 3339 UTC, YYYY-MM-DDTHH:MM:SSZ), not a date-only "
                                  "retrieved")
    for value in (fetched, pin.get("retrieved_at")):
        if isinstance(value, str) and RETRIEVED_AT.fullmatch(value):
            return value
    raise OriginUnpinnedError(
        "a url pin is a mutable origin and records when its file was retrieved (H.2.3 retrieved_at); neither the fetch "
        "cache's acquisition record nor the pin's retrieved_at (RFC 3339 UTC, YYYY-MM-DDTHH:MM:SSZ) gives that time"
    )


@dataclass(frozen=True, slots=True)
class ArchivePart:
    """One byte part of a split archive input (D-249): its pinned file name, digest, size and origin; ``path`` is the
    local copy for a fresh import (``None`` when the part is read back from a corpus's raw store)."""

    file: str
    sha256: str
    size: int
    origin: Origin
    path: str | None = None


class _MemberTree:
    """The selected members of an expanded archive input, read back from the raw store by digest (re-hashed)."""

    kind: Final = "member"
    explicit: Final = False

    def __init__(self, store: RawObjectStore, objects: Mapping[str, str]) -> None:
        self.store, self.objects = store, dict(objects)  # member label -> sha256 (selected members only)
        self.rejections: list[PathRejection] = []

    def read(self, batch: Sequence[CandidateArtefact]) -> Iterator[tuple[CandidateArtefact, bytes | IngestError]]:
        for candidate in batch:
            sha = self.objects.get(candidate.label)
            if sha is None:  # the expand selection is the profile's own globs, so this is a profile or reader defect
                raise AgentProvError("the reader chose an archive member the profile's selection did not store",
                                     code="adapter.archive_input", exit_code=70)
            with self.store.open(sha) as handle:
                data = handle.read()
            if sha256_hex(data) != sha:
                raise AgentProvError("a stored member does not hash to its address", code="raw.digest.mismatch")
            yield candidate, data


class PinCheck:
    """``--verify-against-pin`` for a ``--input`` tree (MN N.2.2): the pinned origin for every file the pin vouches for.

    * ``blob``: a git pin whose tree listing is in the fetch cache. A file whose label is a path of the pin's tree and
      whose git blob id equals the tree entry's gets the pinned ``git`` origin; any other file keeps its ``local`` origin.
    * ``listing``: a pin that records a J.1.4 tree-listing digest (``listing_sha256``; the AgentDojo-PROV release tree,
      whose files are not in the commit). When the digest over the candidates equals the pin, every file gets the origin
      the family's reader assigns to a listing-verified file (``listing_origin(pin, label)``); otherwise all stay ``local``.
    """

    def __init__(
        self, kind: Literal["blob", "listing"], pin: Mapping[str, Any], *, listing: Mapping[str, str] | None = None,
        repo: str | None = None, listing_origin: Callable[[Mapping[str, Any], str], Origin] | None = None,
        history: HistoryIndex | None = None,
    ) -> None:
        self.kind, self.pin = kind, dict(pin)
        self.history = history  # the cached introducing-commit index of the pin (D.6.16), or None
        self.listing = dict(listing or {})
        self.repo = repo
        self.listing_origin = listing_origin
        self.listing_ok: bool | None = None
        self.verified = 0
        self.unverified = 0

    def prepare(self, tree: LocalTree, candidates: Sequence[CandidateArtefact]) -> None:
        """The listing kind reads every candidate once to compute the J.1.4 digest (nothing is stored)."""
        if self.kind != "listing":
            return
        pairs: list[tuple[str, str]] = []
        for candidate, data in tree.read(candidates):
            if isinstance(data, IngestError):
                self.listing_ok = False
                return
            pairs.append((candidate.label, sha256_hex(data)))
        self.listing_ok = listing_sha256(pairs) == self.pin.get("listing_sha256") and len(pairs) == self.pin.get(
            "expected_files", len(pairs)
        )

    def origin_for(self, candidate: CandidateArtefact, data: bytes) -> Origin | None:
        """The pinned origin of a verified file; ``None`` when the pin does not vouch for it."""
        if self.kind == "blob":
            oid = git_blob_sha1(data)
            commit = self.pin.get("commit")
            if self.listing.get(candidate.label) == oid and self.repo and isinstance(commit, str):
                self.verified += 1
                introduced = self.history.lookup(candidate.label, oid) if self.history is not None else None
                return Origin.git(self.repo, commit, candidate.label, oid, introduced_in_commit=introduced)
        elif self.listing_ok and self.listing_origin is not None:
            self.verified += 1
            return self.listing_origin(self.pin, candidate.label)
        self.unverified += 1
        return None


# ================================================================================================ per-unit inputs (D.16.14)
@dataclass(frozen=True)
class ContextTree:
    """Runner item R2 of D.16.14: a second pinned tree whose files are context artefacts (role ``supporting``).

    ``role`` is the pin role the profile names in ``[import] context_artefacts`` entries ``"<role>:<glob>"`` (the DTap
    ``tasks`` pin). ``tree`` is a source tree (``LocalTree`` or ``GitPinTree``) and ``pin_check`` vouches for its files
    (``None`` for a pinned tree whose candidates already carry their pinned origin). D-530: ``tree`` may be an
    :class:`ArchiveTree` (a download pin): the container is stored with the pin's origin and expanded (AD-12) with the
    role's globs, and its selected members are the context artefacts, with ``member`` origins. ``pin`` is the profile pin
    the tree stands for; it is recorded in the manifest so that a re-map can rebuild the tree from the stored corpus."""

    role: str
    tree: Any
    pin_check: PinCheck | None = None
    pin: Mapping[str, Any] | None = None


def _context_verification(source: ContextTree, stored: int) -> dict[str, Any] | None:
    """How a context tree's files were vouched for, as ``snapshot.context[].verification`` records it (D-221; pre-round
    review PR-1). A :class:`PinCheck` gives its own counts; a tree that verifies itself has every stored file vouched for:
    a download pin's archive (``ArchiveTree``: sha256 and size checked against the pin, the files its members) records
    ``download``, a git pin read from the verified fetch cache (``GitPinTree``: every blob's SHA-1 recomputed against
    the tree entry) ``blob``. Anything else (a re-map's stored tree) records none."""
    if source.pin_check is not None:
        return {"kind": source.pin_check.kind, "verified": source.pin_check.verified,
                "unverified": source.pin_check.unverified}
    if isinstance(source.tree, ArchiveTree):
        return {"kind": "download", "verified": stored, "unverified": 0}
    if isinstance(source.tree, GitPinTree):
        return {"kind": "blob", "verified": stored, "unverified": 0}
    return None


@dataclass(frozen=True)
class PinnedObject:
    """Runner item R3 of D.16.14: an object fetched by its own pin (an ``hf`` LFS object) that stands for the file at
    ``label`` in the primary tree (a Git LFS pointer). ``path`` is the verified local copy (the fetch cache); its digest
    and size are checked again before it is stored. The pointer keeps its own disposition; the object is a candidate of
    its own, with ``origin`` (``hf {repo, revision, path}``)."""

    label: str
    origin: Origin
    path: str
    sha256: str
    size: int


class _AuxListing:
    """What a reader's ``auxiliary_for`` may ask (runner items R1/R2): the labels of a directory of the primary tree, and
    whether a primary-tree label or a context label ``"<role>:<label>"`` exists."""

    def __init__(self, labels: Iterable[str], context: Mapping[str, Iterable[str]]) -> None:
        self._dirs: dict[str, list[str]] = {}
        self._all: set[str] = set()
        for label in labels:
            self._all.add(label)
            self._dirs.setdefault(label.rpartition("/")[0], []).append(label)
        for items in self._dirs.values():
            items.sort()
        self._context = {f"{role}:{label}" for role, items in context.items() for label in items}

    def siblings(self, label: str) -> tuple[str, ...]:
        return tuple(self._dirs.get(label.rpartition("/")[0], ()))

    def exists(self, ref: str) -> bool:
        return ref in self._all or ref in self._context


# ================================================================================================ report and filters
SAMPLE_MODES: Final = ("first", "spread", "random")


@dataclass(frozen=True)
class ImportSample:
    """``import --sample N --sample-mode first|spread|random [--seed S]`` (D-529): a deterministic dev sample of N
    executions, chosen once from the complete list of the import's executions, before anything is mapped, so that it
    does not depend on ``--batch-size``, ``--jobs`` or the resume order (cf. CD-7)."""

    n: int
    mode: str = "first"
    seed: str | None = None

    def __post_init__(self) -> None:
        if self.n < 1:
            raise ValueError("a sample has at least one execution")
        if self.mode not in SAMPLE_MODES:
            raise ValueError(f"unknown sample mode {self.mode!r}")
        if (self.mode == "random") != (self.seed is not None):
            raise ValueError("a seed goes with the random mode, and only with it")


def select_sample(keys: Sequence[tuple[str, str | None]], sample: ImportSample) -> frozenset[str]:
    """The keys of the sampled executions (D-529); ``keys`` are ``(sample key, stratum)`` pairs.

    * ``first``: the first N sample keys in sorted order;
    * ``random``: the N keys whose ``sha256(utf8(seed) || 0x00 || utf8(key))`` is smallest (no PRNG state: the same for
      a given seed and set of keys on every host and Python);
    * ``spread``: the strata in sorted order, taken round-robin, each one's keys in sorted order, until N are chosen.
    """
    unique = sorted(dict(keys).items())
    if sample.mode == "first":
        return frozenset(k for k, _ in unique[: sample.n])
    if sample.mode == "random":
        seed = str(sample.seed).encode("utf-8")
        ranked = sorted(unique, key=lambda kv: (hashlib.sha256(seed + b"\x00" + kv[0].encode("utf-8")).digest(), kv[0]))
        return frozenset(k for k, _ in ranked[: sample.n])
    groups: dict[str, list[str]] = {}
    for key, stratum in unique:
        groups.setdefault(stratum or "", []).append(key)
    order = [groups[g] for g in sorted(groups)]
    chosen: list[str] = []
    depth = 0
    while len(chosen) < sample.n and any(depth < len(g) for g in order):
        for group in order:
            if depth < len(group) and len(chosen) < sample.n:
                chosen.append(group[depth])
        depth += 1
    return frozenset(chosen)


@dataclass(frozen=True)
class ImportFilters:
    """Filters of N.1.7 (D.2.9): ``include_paths`` are extra globs ANDed with the profile (applied before reading);
    ``variants`` and ``select`` (key -> accepted values, keys of :data:`SELECT_KEYS`) are applied after mapping, and a
    unit they reject is counted ``filtered`` and not written."""

    include_paths: tuple[str, ...] = ()
    variants: frozenset[str] | None = None
    select: Mapping[str, frozenset[str]] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return bool(self.include_paths or self.variants is not None or self.select)

    def to_json(self) -> dict[str, Any]:
        return {
            "include_paths": list(self.include_paths),
            "select": {k: sorted(v) for k, v in sorted(self.select.items())},
            "variants": None if self.variants is None else sorted(self.variants),
        }

    def keep(self, header: Mapping[str, Any]) -> bool:
        if self.variants is not None and SELECT_KEYS["variant"](header) not in self.variants:
            return False
        for key, accepted in self.select.items():
            value = SELECT_KEYS[key](header)
            if not isinstance(value, str) or value not in accepted:
                return False
        return True


@dataclass
class ImportReport:
    """What :func:`import_source` returns (D.2.9). ``register`` holds this run's register rows (JSON)."""

    counters: dict[str, int]
    register: list[dict[str, Any]]
    issues_by_code: dict[str, int]
    limits: dict[str, Any]
    adapter: str
    adapter_version: str
    profile: str
    profile_version: int
    profile_sha256: str
    rules: dict[str, int]
    failures: list[dict[str, Any]] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    partial: bool = False
    corpus_root: str | None = None
    #: D-610: the snapshots the working manifest marks incomplete (id -> ``drained`` or ``interrupted``)
    incomplete: dict[str, str] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        """0 when every unit was sealed clean or with issues; 1 when any unit is degenerate or failed (D.2.9; N.1.3)."""
        return 1 if self.failures or self.counters.get("degenerate", 0) or self.counters.get("failed", 0) else 0


COUNTERS: Final = (
    "seen", "mapped", "sealed_clean", "sealed_with_issues", "degenerate", "failed", "registered", "excluded",
    "duplicates", "skipped_resume", "filtered", "annotated", "derived", "validated",
)  # fmt: skip


# ================================================================================================ the pipeline
@dataclass
class _Unit:
    """One sealed unit between the write gate and the index entry."""

    ex: str
    label: str
    header: dict[str, Any]
    data: bytes
    seal: Any  # SealInfo
    degenerate: bool
    codes: dict[str, str]  # register code -> severity, for this ex
    aer_row: dict[str, Any]
    aer_ok: bool


class _HeldStore:
    """The raw store as the AER validator sees it while a job's units are sealed: the corpus store plus the job's held
    carved blobs (D-218). Read-only; nothing is stored through it."""

    def __init__(self, store: RawObjectStore, held: Mapping[str, tuple[Any, Origin]]) -> None:
        self._store, self._held = store, held

    def has(self, sha256: str) -> bool:
        return sha256 in self._held or self._store.has(sha256)

    def size(self, sha256: str) -> int:
        if sha256 in self._held:
            return int(self._held[sha256][0].size)
        return self._store.size(sha256)

    def read_bytes(self, sha256: str) -> bytes:
        if sha256 in self._held:
            return bytes(self._held[sha256][0].read_bytes())
        return self._store.read_bytes(sha256)


class _ChunkStream(io.RawIOBase):
    """A read-only binary stream over an iterator of chunks (a held member's spool, stored with ``put_stream``)."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks, self._pending = chunks, b""

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        while not self._pending:
            try:
                self._pending = next(self._chunks)
            except StopIteration:
                return 0
        n = min(len(buffer), len(self._pending))
        buffer[:n] = self._pending[:n]
        self._pending = self._pending[n:]
        return n


def _removes_scratch_on_error[**P](init: Callable[Concatenate[_Pipeline, P], None]) -> Callable[Concatenate[_Pipeline, P], None]:
    """Ultrareview pipeline nit: the constructor makes its private scratch tree before checks that can raise (a profile
    refused for the input, a registry lookup); the caller never gets a pipeline to ``close``, so it is removed here."""

    @functools.wraps(init)
    def wrapper(self: _Pipeline, /, *args: P.args, **kwargs: P.kwargs) -> None:
        try:
            init(self, *args, **kwargs)
        except BaseException:
            scratch = getattr(self, "scratch", None)
            if scratch is not None:
                shutil.rmtree(scratch, onexc=_make_writable_and_retry)
            raise

    return wrapper


class _Pipeline:
    #: ``executions.jsonl`` mode of the rows this pipeline writes (H.3.1): ``import`` here; the live session pipeline
    #: (:mod:`agentprov.adapters.runner.session`) writes ``live`` rows with their capture attempt index.
    index_mode: str = "import"
    #: D-550: the tier-4 round-trip cache the ``prov`` jobs' completed round trips are stored in (``None``: none)
    validation_cache: Any = None

    def attempt_of(self, ex: str) -> int | None:
        """The live attempt index of ``ex`` (``None`` for imports)."""
        return None

    @_removes_scratch_on_error
    def __init__(
        self,
        source_id: str,
        tree: Any,
        corpus: CorpusWriter,
        *,
        profile: SourceProfile,
        part: str,
        snapshot_id: str,
        corpus_id: str,
        filters: ImportFilters,
        limit: int | None,
        mode: Literal["dev", "release"],
        until: str,
        prov_specs: Sequence[str],
        workers: int,
        in_process: bool,
        limits: IngestLimits,
        retry_failed: bool,
        progress: Progress,
        pin_check: PinCheck | None,
        resume_index: IndexLog | None,
        batch_size: int,
        dry_run: bool,
        semantics: Sequence[str] = (),
        context_trees: Sequence[ContextTree] = (),
        pinned_objects: Sequence[PinnedObject] = (),
        prov_conformance: bool = True,
        sample: ImportSample | None = None,
        context_skipped: Sequence[str] = (),
        honour_drain: bool = False,
    ) -> None:
        self.source_id, self.tree, self.corpus = source_id, tree, corpus
        #: G2c-5 (D-432): False skips tier 4 only (the W3C PROV round trip and constraint checks); recorded, never silent
        self.prov_conformance = prov_conformance
        #: D-394, PR-6: only ``import`` opts in; a re-map (``recompute``, ``derive``, ``verify --level rederive``) never
        #: drains mid-way, so a drain sent to those degrades to a stop (N.1.10(5))
        self.honour_drain = honour_drain
        self.drained = False
        self._pool_reporter = _PoolReporter(progress)
        #: D-529: the sample asked for, the sample keys it chose (``None``: no sampling) and its manifest record
        self.sample = sample
        self.sampled: frozenset[str] | None = None
        self.sample_record: dict[str, Any] | None = None
        #: NF-36: set once ``run`` returned undrained (an interrupted or D-394-drained run does not complete its snapshot)
        self.completed = False
        #: NF-36: the written manifest's ``partial`` (``None`` until one is written; a dry run writes none)
        self.manifest_partial: bool | None = None
        #: D-610: set when ``run`` raised (the manifest is still written on the way out); the snapshots the written
        #: manifest marks ``incomplete`` (id -> reason), and whether this run cleared its snapshot's earlier mark
        self.interrupted = False
        #: D-610 review: whether the last candidate this run mapped ended in a unit ``--limit`` counts (a non-degenerate
        #: one), in candidate order: a re-map under the cap stops right after its last counted unit, so a degenerate unit
        #: or a rejected candidate after it is not reproduced (nothing mapped yet: nothing follows it)
        self.clean_tail = True
        #: PR-11 #6: an outcome the AER write gate rejected since the last sealed unit (registered failed, no unit)
        self._rejected_since_unit = False
        self.manifest_incomplete: dict[str, str] = {}
        self.cleared_incomplete: str | None = None
        self._stored_files: dict[str, tuple[CandidateArtefact, str, int, Origin]] = {}
        #: NF-34 (regen item 128): multi-execution files this corpus already holds sealed whole (resumed or collapsed by
        #: their document-root key in ``_store``); a sample still lists each under its ``label#`` key
        self._known_whole: set[str] = set()
        #: PR-9: in a sample's pass 1 a whole-sealed file is only listed; its resume or D-202 collapse (PR-8 sample id ->
        #: digest and label) is applied once the draw chose its ``<id>#`` key, so a sampled-out file is never collapsed
        self._listing_sample = False
        self._deferred_whole: dict[str, tuple[str, str]] = {}
        self._expanded_containers: dict[str, tuple[list[ContainerSpec], dict[str, str], Any]] = {}
        self._planned_units: dict[str, list[str]] = {}  # container label -> its planned units' member labels
        self.profile, self.part, self.snapshot_id, self.corpus_id = profile, part, snapshot_id, corpus_id
        self.filters, self.limit, self.mode, self.until = filters, limit, mode, until
        self.specs = tuple(prov_specs)
        self.semantics = tuple(semantics)
        self.limits, self.retry_failed, self.progress, self.pin_check = limits, retry_failed, progress, pin_check
        self.batch_size, self.dry_run = max(1, batch_size), dry_run
        imp = profile.data.get("import", {})
        self.dialect, self.mapper_id = str(imp.get("dialect")), str(imp.get("mapper"))
        from agentprov.adapters.registry import MAPPERS, READERS

        self.reader = resolve_factory(READERS[self.dialect])()
        self.mapper = resolve_factory(MAPPERS[self.mapper_id])()
        self.container = callable(getattr(self.reader, "plan", None)) and callable(getattr(self.reader, "member_patterns", None))
        #: R-10k-1 (D-320): a whole-file reader with one execution per located item (a credleak cell's runs). Its files are
        #: mapped with ``per_item`` and its executions are resumed and collapsed by source key, one by one.
        self.multi = multi_execution(self.reader) and not self.container
        #: D-323 (RB-1): a multi-execution reader that streams its primary; its map jobs never read the document whole
        self.stream = self.multi and streams(self.reader)
        self.registry = RuleRegistry.default()
        self.mapping = mapping_id(self.mapper.mapper_id, profile.id)
        self.counters: Counter[str] = Counter({k: 0 for k in COUNTERS})
        if sample is not None:
            self.counters["sampled_out"] = 0  # only a sampled import reports it (the other summaries are unchanged)
        self.issues: Counter[str] = Counter()
        self.run_register: list[RegisterEntry] = []
        self.failures: list[dict[str, Any]] = []
        self.notices: list[str] = []
        self.written = 0
        #: NF-36 review: the non-degenerate units this run indexed (what ``--limit`` counts, as ``written``, but only once
        #: a unit's row is written: mapping runs a batch ahead of the index, and an interrupted run's unindexed units are
        #: mapped again by the resume); the snapshot's cumulative cap adds these
        self.indexed = 0
        self.this_run: set[str] = set()
        self.scratch = Path(tempfile.mkdtemp(prefix="agentprov-import-"))
        self.scratch_store = RawObjectStore(self.scratch / "prov-inputs")
        self.aer_tmp = self.scratch / "aer"
        self.aer_tmp.mkdir()
        release = mode == "release"
        self.map_pool = WorkerPool(store_root=corpus.store.objects_dir, spool_dir=corpus.store.tmp_dir, workers=workers,
                                   in_process=in_process, release=release)  # fmt: skip
        self.prov_pool = WorkerPool(store_root=self.scratch_store.objects_dir, workers=workers, in_process=in_process,
                                    release=release)
        #: D-931: the profile's raise-only map cap, carried by every map job of this import (timing and admission only)
        map_cap = profile.data.get("import", {}).get("map_rss_bytes")
        base = self.map_pool.limits
        self.map_limits = None if map_cap is None else dataclasses.replace(
            base, kind_rss_bytes={**base.kind_rss_bytes, "map": int(map_cap)})
        #: D-935: the profile's raise-only prov cap (generation and tier 4 of a large PROV document run in the prov job)
        prov_cap = profile.data.get("import", {}).get("prov_rss_bytes")
        pbase = self.prov_pool.limits
        self.prov_limits = None if prov_cap is None else dataclasses.replace(
            pbase, kind_rss_bytes={**pbase.kind_rss_bytes, "prov": int(prov_cap)})
        #: D-218: the carved blobs of the job being sealed, digest -> (spooled member, ``carved`` origin); stored only when a
        #: written AER cites them (``_commit_carved``)
        self._held: dict[str, tuple[Any, Origin]] = {}
        #: H.7.2(1): an execution another snapshot of this corpus already mapped gains this snapshot (D-202).
        self.known_snapshots: dict[str, tuple[str, ...]] = {}
        #: source key -> ``ex`` of every indexed execution (a ``multi_execution`` reader's executions share the digest).
        self.known_keys: dict[str, str] = {}
        self.known = self._known_artefacts(resume_index if resume_index is not None else corpus.index)
        #: D-321: ``(source_key, code)`` of the rejected rows already registered (a resume re-registers none of them).
        self.known_rejected: set[tuple[str, str]] = {
            (e.subject["source_key"], e.code) for e in corpus.register.entries()
            if set(e.subject) == {"source_key"} and e.disposition == "not_imported" and e.code in _REJECTED_CODES}
        self.catalogues = self._catalogues()
        #: D.6.12 item 6: ``[import] context_artefacts`` (role ``supporting``) are stored and handed to every ``map`` job
        #: of a mapper that declares ``consumes_context``; the rows are ``{label, sha256, size, origin}``.
        self.consumes_context = bool(getattr(self.mapper, "consumes_context", False))
        self.context_candidates: list[CandidateArtefact] = []
        self.context: list[dict[str, Any]] = []
        #: D.16.14 R1/R2: a reader with ``auxiliary_for`` names each unit's own auxiliary inputs (same-tree files such as a
        #: directory's judge, and context files ``"<role>:<label>"`` of a second pinned tree); nothing else changes for
        #: other families. R3: ``pinned_objects`` stand for files of the primary tree (LFS pointers).
        self.per_unit = callable(getattr(self.reader, "auxiliary_for", None))
        self.context_trees = {t.role: t for t in context_trees}
        #: D-221 (NF-29): the context roles the import skipped (``--no-context``), recorded in the snapshot.
        self.context_skipped = sorted(set(context_skipped))
        self.overlay = {o.label: o for o in pinned_objects}
        self.listing: _AuxListing | None = None
        self.walked: dict[str, CandidateArtefact] = {}
        self.role_candidates: dict[str, list[CandidateArtefact]] = {}
        self.unit_context: dict[str, dict[str, Any]] = {}  # "<role>:<label>" -> stored row
        #: D-530: an archive context's stored container ({label, sha256, bytes}) and the reader of its stored members
        self.context_archives: dict[str, dict[str, Any]] = {}
        self.context_readers: dict[str, Any] = {}
        self.aux_rows: dict[str, dict[str, Any] | None] = {}  # primary-tree label -> stored row (None: refused)
        self.aux_used: set[str] = set()
        self.aux_refused: dict[str, str] = {}  # auxiliary label -> register detail of a not-imported primary naming it
        self.copies_done: set[str] = set()
        self.candidate_labels: set[str] = set()
        #: D-200: an archive input (a downloaded file whose members are the artefacts). ``archive_label`` is the
        #: container's label once it is stored; register subjects of its members are ``<container>!/<member>``.
        self.archive = bool(getattr(tree, "archive_input", False))
        self.archive_label: str | None = None
        self.archive_object: dict[str, Any] | None = None
        #: D-380: the candidates of an archive input by chain label (``<nested label>!/<member label>``): the level each
        #: opens at when it is a container member, and the depth allowance of its chain (D-382)
        self.archive_meta: dict[str, tuple[int, int | None]] = {}
        #: D-560: the ``not_selected`` members of an archive input (R-40) as ``(chain label, member label)``; the ones an
        #: exclude entry names are registered as excluded walked files are
        self.unselected: list[tuple[str, str]] = []
        if imp.get("nested") and not self.archive:
            raise AgentProvError("[import] nested declares archives inside an archive input; this input is not one",
                                 code="adapter.archive_input", exit_code=5)
        if self.archive and self.container and not imp.get("include"):
            raise AgentProvError("an archive input of a container dialect needs [import] include naming its container "
                                 "members (D-380)", code="adapter.archive_input", exit_code=5)
        #: D-203: ``[import] blobs`` files (blob payloads that AER records reference by digest, ``$blob``): stored before
        #: mapping with their pinned origins and offered to the map jobs of the units in their directory or above it.
        self.blob_candidates: list[CandidateArtefact] = []
        self.blobs: dict[str, tuple[str, int]] = {}  # label -> (sha256, size)

    # -------------------------------------------------------------------------------------- resume state
    def _known_artefacts(self, index: IndexLog) -> dict[str, str]:
        """Primary artefact digest -> ``ex`` of every indexed execution (its ``source_key`` names the artefact); the full
        source keys go to ``known_keys``."""
        known: dict[str, str] = {}
        for row in index.rows():
            sha = row.source_key[len("sha256:") : len("sha256:") + 64]
            # a failed execution another snapshot shares is retried from that snapshot only (its row lists both)
            if self.retry_failed and row.status == "failed" and set(row.snapshot_ids) <= {self.snapshot_id}:
                if not self.dry_run:
                    self.corpus.discard_execution(row.ex)
                continue
            known[sha] = row.ex
            self.known_keys[row.source_key] = row.ex
            self.known_snapshots[row.ex] = tuple(row.snapshot_ids)
        return known

    def _seen_before(self, sha: str, label: str, *, key: str | None = None) -> bool:
        """Whether the primary artefact ``sha`` already has an execution in this corpus (it is then not mapped again).

        Mapped in this snapshot before: ``skipped_resume``. Mapped in another snapshot: H.7.2(1)'s collapse (D-202): the
        one execution row lists this snapshot too (its origin is already in ``raw/origins.jsonl``), a ``dedup.collapsed``
        entry records it and it counts as a duplicate.

        With ``key`` (one execution of a ``multi_execution`` file; R-10k-1, D-320) the question is asked of that source key
        rather than of the digest, and the ``dedup.collapsed`` subject is the source key (H.6.2), so every collapsed
        execution of the file has its own entry."""
        ex = self.known.get(sha) if key is None else self.known_keys.get(key)
        if ex is None:
            return False
        snapshots = self.known_snapshots.get(ex, ())
        if self.snapshot_id in snapshots:
            self.counters["skipped_resume"] += 1
            return True
        if not self.dry_run:
            self.corpus.add_snapshot(ex, self.snapshot_id)
        self.known_snapshots[ex] = (*snapshots, self.snapshot_id)
        first = snapshots[0] if snapshots else "?"
        if key is None:
            self._register(self._path_subject(label), "dedup.collapsed", severity="info", stage="select",
                           disposition="sealed", detail=f"identical bytes sha256:{sha[:16]} already mapped in snapshot {first}")
        else:
            self._register({"source_key": key}, "dedup.collapsed", severity="info", stage="select", disposition="sealed",
                           detail=f"identical execution of sha256:{sha[:16]} already mapped in snapshot {first}")
        self.counters["duplicates"] += 1
        return True

    def _catalogues(self) -> dict[str, int]:
        names = getattr(sys.modules[type(self.mapper).__module__], "CATALOGUES", ())
        return {str(ns): load_catalogue(str(ns)).version for ns in sorted(names)}

    # -------------------------------------------------------------------------------------- register
    def _register(self, subject: Mapping[str, str], code: str, *, severity: str, stage: str, disposition: str,
                  detail: str = "", rule: str | None = None, ids: Sequence[str] = (),
                  owner: Mapping[str, str] | None = None) -> None:
        entry = RegisterEntry(subject=dict(subject), code=code, severity=severity, stage=stage, disposition=disposition,
                              rule=rule, detail=_detail(detail), ids=tuple(ids), owner=owner)
        self.corpus.add_register(entry)
        self.run_register.append(entry)
        self.issues[code] += 1

    def _path_subject(self, label: str) -> dict[str, str]:
        if self.archive_label is not None and label != self.archive_label:
            return {"snapshot_id": self.snapshot_id, "path": f"{self.archive_label}!/{label}"}
        return {"snapshot_id": self.snapshot_id, "path": label}

    @staticmethod
    def _owner(entry: Mapping[str, Any]) -> dict[str, str]:
        """``{corpus_id, source_id}`` of a ``select.owned_elsewhere`` exclude (HL H.6.2): the entry's ``owner_corpus``,
        else the owner's registry corpus id, else the owner id itself (an ``ext:<name>`` owner has no corpus)."""
        from agentprov.adapters.registry import get_source

        owner = str(entry["owner"])
        corpus = entry.get("owner_corpus")
        if not isinstance(corpus, str):
            try:
                corpus = next((c.corpus_id for c in get_source(owner).capabilities if c.corpus_id), None)
            except KeyError:
                corpus = None
        return {"corpus_id": str(corpus or owner), "source_id": owner}

    def store_context(self) -> None:
        """Store the context artefacts (role ``supporting``; D.4.2 ``[import] context_artefacts``) before any mapping, with
        their pinned origins; one the pin does not vouch for is registered ``raw.origin.blob_mismatch`` and left out."""
        for candidate, data in self.tree.read(self.context_candidates):
            if isinstance(data, IngestError):
                self._register(self._path_subject(candidate.label), data.code, severity="error", stage="ingest",
                               disposition="not_imported", detail="the context artefact could not be read safely")
                self.counters["registered"] += 1
                continue
            origin = self.pin_check.origin_for(candidate, data) if self.pin_check is not None else candidate.origin
            if origin is None:
                self._register(self._path_subject(candidate.label), "raw.origin.blob_mismatch", severity="error",
                               stage="ingest", disposition="not_imported", detail="context artefact not vouched for by the pin")
                self.counters["registered"] += 1
                continue
            put = self.corpus.add_object(data, origin, ext=ext_for_label(candidate.label))
            self.context.append({"label": candidate.label, "origin": origin.to_json(), "sha256": put.sha256,
                                 "size": len(data)})

    def store_blobs(self) -> None:
        """D-203: store the ``[import] blobs`` files before any mapping, with their pinned origins (store-first, A2); one
        the pin does not vouch for, or that cannot be read safely, is registered and left out. They are never mapped:
        an AER references them by digest (``$blob``, C.11.5), and AER-V21 finds them in the raw store."""
        for candidate, data in self.tree.read(self.blob_candidates):
            if isinstance(data, IngestError):
                self._register(self._path_subject(candidate.label), data.code, severity="error", stage="ingest",
                               disposition="not_imported", detail="the blob file could not be read safely")
                self.counters["registered"] += 1
                continue
            origin = self.pin_check.origin_for(candidate, data) if self.pin_check is not None else candidate.origin
            if origin is None:
                self._register(self._path_subject(candidate.label), "raw.origin.blob_mismatch", severity="error",
                               stage="ingest", disposition="not_imported", detail="blob file not vouched for by the pin")
                self.counters["registered"] += 1
                continue
            put = self.corpus.add_object(data, origin, ext=ext_for_label(candidate.label))
            self.blobs[candidate.label] = (put.sha256, len(data))

    def _blobs_for(self, label: str) -> list[dict[str, Any]]:
        """D-203: the stored blob files offered to the unit at ``label``: those in its directory or below it, by label
        order, one per digest (``{sha256, size}``; the mapper opens them as ``blob:<hex>``)."""
        directory = label.rpartition("/")[0]
        prefix = directory + "/" if directory else ""
        rows: dict[str, dict[str, Any]] = {}
        for blob_label in sorted(self.blobs, key=lambda b: b.encode("utf-8")):
            if blob_label.startswith(prefix):
                sha, size = self.blobs[blob_label]
                rows.setdefault(sha, {"sha256": sha, "size": size})
        return list(rows.values())

    def _fail(self, subject: Mapping[str, str], stage: str, code: str, detail: str) -> None:
        self.failures.append({"subject": dict(subject), "stage": stage, "code": code, "detail": _detail(detail)})

    # -------------------------------------------------------------------------------------- archive inputs (D-200)
    def archive_selection(self) -> Selection:
        """The ``expand`` selection of an archive input: the profile's include globs, its blob globs and its (primary
        tree) context-artefact globs; every other member is recorded ``not_selected`` and never decompressed (R-40).
        ``[import] nested`` (D-382) adds the declared nested archives, each expanded with the same globs."""
        imp = self.profile.data.get("import", {})
        context = [g for g in imp.get("context_artefacts", ()) if ":" not in str(g)] if self.consumes_context else []
        include = tuple(str(g) for g in (*imp.get("include", ()), *imp.get("blobs", ()), *context))
        nested = imp.get("nested")
        return nested_selection(include, nested) if nested else Selection(include=include)

    def archive_members(self) -> list[CandidateArtefact]:
        """Store the archive input (store-first, A2), expand it (AD-12) and return its members as candidates: every member
        with a name, with its ``member`` origin; the selected ones are read back from the raw store (:class:`_MemberTree`).
        A container the ``expand`` gate rejects is registered by the writer (its ``ingest.*`` code) and fails the run."""
        containers = list(self.tree.walk())
        if len(containers) != 1:
            raise AgentProvError("an archive input is exactly one stored container", code="adapter.archive_input")
        (container,) = containers
        parts: Sequence[Any] | None = getattr(self.tree, "archive_parts", None)
        if parts:
            return self._split_members(container, parts)
        opener = getattr(self.tree, "stream", None)
        # CB-20: the verified pin digest and size (an ArchiveTree's) are checked before the container or its origin is
        # stored; a corpus's StoredTree carries none and re-hashes every object it reads
        sha, size = getattr(self.tree, "sha256", None), getattr(self.tree, "size", None)
        if opener is not None:
            with opener(container.label) as handle:
                put = self.corpus.add_object(handle, container.origin, ext=ext_for_label(container.label),
                                             expected_sha256=sha, expected_size=size)  # fmt: skip
        else:
            data = next(iter(self.tree.read([container])))[1]
            if isinstance(data, IngestError):
                raise data
            put = self.corpus.add_object(data, container.origin, ext=ext_for_label(container.label),
                                         expected_sha256=sha, expected_size=size)  # fmt: skip
        self.archive_label = container.label
        self.archive_object = {"label": container.label, "sha256": put.sha256, "bytes": put.size}
        spec = ContainerSpec(put.sha256, self.snapshot_id, container.label, (self.archive_selection(),), prefixed=True)
        return self._expand_archive(container, spec, put.sha256)

    def _split_members(self, container: CandidateArtefact, parts: Sequence[Any]) -> list[CandidateArtefact]:
        """D-249: store every part with its pinned origin (in the pin's order), then the split descriptor with its
        ``split`` origin, and expand the descriptor with its parts (D-243/D-244); the rest is the D-200 path."""
        declared: list[tuple[str, int]] = []
        for part in parts:
            with self.tree.open_part(part) as handle:
                put = self.corpus.add_object(handle, part.origin, ext=ext_for_label(part.file),
                                             expected_sha256=part.sha256, expected_size=part.size)  # fmt: skip
            declared.append((put.sha256, put.size))
        origin = Origin.split(container.label, [sha for sha, _size in declared])
        put = self.corpus.add_object(split_descriptor(declared), origin, ext="json")
        self.archive_label = container.label
        self.archive_object = {"label": container.label, "sha256": put.sha256,
                               "bytes": sum(size for _sha, size in declared),
                               "parts": [{"file": p.file, "sha256": "sha256:" + sha, "bytes": size}
                                         for p, (sha, size) in zip(parts, declared, strict=True)]}  # fmt: skip
        spec = ContainerSpec(put.sha256, self.snapshot_id, container.label, (self.archive_selection(),),
                             parts=tuple(declared), prefixed=True)  # fmt: skip
        return self._expand_archive(container, spec, put.sha256)

    def _expand_archive(self, container: CandidateArtefact, spec: ContainerSpec, put_sha: str) -> list[CandidateArtefact]:
        expanded = self.corpus.expand([spec], self.map_pool, limits=self.limits)
        if put_sha not in expanded.containers:
            event = next((e for e in expanded.events if e.path == container.label), None)
            self.counters["registered"] += 1
            self._fail({"snapshot_id": self.snapshot_id, "path": container.label}, "expand",
                       event.code if event is not None else "ingest.archive.format", "the archive input was rejected")
            self.tree = _MemberTree(self.corpus.store, {})
            return []
        self.counters["registered"] += sum(1 for e in expanded.events if e.disposition == "not_imported")
        # only the selected members are walked: a member outside the selection already has its disposition, the
        # ``not_selected`` row of raw/members.jsonl (R-40), and a rejected one its register entry (G.3.5). A declared
        # nested archive (D-382) is expanded, never a candidate; the members of every expanded level are, each under its
        # chain label (the member labels from the input down, joined with ``!/``; D-380, D-384)
        candidates: list[tuple[str, Any]] = []
        for r in expanded.rows:
            place = expanded.placed.get(r.container)
            if r.disposition == "not_selected" and place is not None and r.label is not None:
                self.unselected.append(("!/".join((*place.chain, str(r.label))), str(r.label)))
            if r.disposition != "selected" or place is None or (r.container, r.label) in expanded.nested_members:
                continue
            chain = "!/".join((*place.chain, str(r.label)))
            candidates.append((chain, r))
            self.archive_meta[chain] = (place.depth + 1, place.max_depth)
        candidates.sort(key=lambda item: item[0].encode("utf-8"))
        self.tree = _MemberTree(self.corpus.store, {chain: str(r.sha256) for chain, r in candidates})
        return [CandidateArtefact(chain, int(r.size or 0), r.origin()) for chain, r in candidates]

    # -------------------------------------------------------------------------------------- discovery
    def _hold_account_paths(self, candidates: list[CandidateArtefact]) -> list[CandidateArtefact]:
        """Regeneration-batch item 108 (the D-510 safeguard, fail closed): a selected file whose label names an account
        directory (:mod:`agentprov.adapters.account_paths`) is held as ``select.redaction_pending`` unless a redaction
        rule of the profile covers that segment or ``[import] account_path_exempt`` names it. Counts and shapes only."""
        family = str(self.profile.data.get("profile", {}).get("family", ""))
        rules = self.profile.data.get("family", {}).get(family, {}).get("redact", ())
        patterns = redaction_patterns(list(rules))
        exempt = [str(e["glob"]) for e in self.profile.data.get("import", {}).get("account_path_exempt", ())
                  if isinstance(e, Mapping) and "glob" in e]
        kept: list[CandidateArtefact] = []
        for c in candidates:
            label = self._glob_label(c)
            shapes = account_shapes(label)
            if (not shapes or any(_match(label, g) for g in exempt)
                    or all(covered(label, shape, patterns, salt=self.profile.id) for shape in shapes)):
                kept.append(c)
                continue
            self.counters["excluded"] += 1
            where = ", ".join(sorted({f"{shape.shape} in segment {shape.segment}" for shape in shapes}))
            self._register(self._path_subject(c.label), "select.redaction_pending", severity="warning", stage="select",
                           disposition="not_imported",
                           detail=f"account-path shape ({where}) with no covering redaction rule (D-510, item 108)")
        return kept

    def _glob_label(self, candidate: CandidateArtefact) -> str:
        """The label a profile glob is matched against: a member of an archive input is matched by its own member label
        (the label ``expand`` matched at its level; D-380), never by its chain label, which is a register key only."""
        if self.archive and candidate.origin.kind == "member":
            return str(candidate.origin.data["label"])
        return candidate.label

    def discover(self) -> list[CandidateArtefact]:
        everything = self.archive_members() if self.archive else list(self.tree.walk())
        if self.tree.explicit:
            candidates = [c for c in everything if not _is_stray(c.label)]
        elif self.archive:
            # the reader sees each member under its own label; it yields the objects it was given, mapped back here
            proxies = [(CandidateArtefact(self._glob_label(c), c.size, c.origin), c) for c in everything]
            back = {id(proxy): c for proxy, c in proxies}
            candidates = [back[id(p)] for p in self.reader.iter_artefacts(_Listed([p for p, _c in proxies]), self.profile)]
        else:
            candidates = list(self.reader.iter_artefacts(_Listed(everything), self.profile))
        imp = self.profile.data.get("import", {})
        include = tuple(imp.get("include", ()))
        excludes = [e for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e]
        chosen = {c.label for c in candidates}
        if not self.tree.explicit:
            context_globs = tuple(imp.get("context_artefacts", ())) if self.consumes_context else ()
            self.context_candidates = [c for c in everything if c.label not in chosen and not _is_stray(c.label)
                                       and any(_match(self._glob_label(c), g) for g in context_globs)]
            as_context = {c.label for c in self.context_candidates}
            blob_globs = tuple(str(g) for g in imp.get("blobs", ()))
            self.blob_candidates = [c for c in everything if c.label not in chosen and c.label not in as_context
                                    and not _is_stray(c.label) and any(_match(self._glob_label(c), g) for g in blob_globs)]
            as_context |= {c.label for c in self.blob_candidates}
            # D.2.8 case 4 / D.6.12 item 6: every walked file an exclude entry matches is registered with the entry's
            # select code (and owner); a context artefact or a blob file (D-203) is stored instead, never registered as
            # excluded. D-560: so is an archive member outside the expand selection, matched by its member label
            walked = [(c.label, self._glob_label(c)) for c in everything
                      if c.label not in chosen and c.label not in as_context and not _is_stray(c.label)]
            walked += [(chain, member) for chain, member in self.unselected if not _is_stray(chain)]
            for label, glob_label in walked:
                entry = next((e for e in excludes if _match(glob_label, str(e["glob"]))), None)
                if entry is None:
                    continue
                self.counters["excluded"] += 1
                code = str(entry.get("code") or "select.not_execution_artefact")
                self._register(self._path_subject(label), code, severity="info", stage="select",
                               disposition="not_imported", detail=f"excluded by the profile ({str(entry['glob'])[:120]})",
                               owner=self._owner(entry) if code == "select.owned_elsewhere" else None)
            for rejection in self.tree.rejections:
                if any(_match(rejection.label, g) for g in include):
                    self._register(self._path_subject(rejection.label), rejection.code, severity="error", stage="ingest",
                                   disposition="not_imported", detail=rejection.detail)
                    self.counters["registered"] += 1
        #: RD-3 (CD-8): the listing a listing pin is checked against (J.1.4), before overlays and --include-path
        self.pin_candidates = list(candidates)
        # item 108 holds after the snapshot: a held file is not imported, but a listing pin still covers it (pre-round
        # review #7), so the other files are not blob_mismatch
        candidates = self._hold_account_paths(candidates)
        if self.per_unit:
            candidates = self._discover_per_unit(everything, candidates)
        elif self.overlay:  # D-530 item 6: R3 pinned objects for a reader without per-unit inputs (MCPHunt's LFS documents)
            candidates = self._with_overlay(candidates)
        if self.filters.include_paths:
            kept = [c for c in candidates if all(_match(c.label, g) for g in self.filters.include_paths)]
            self.counters["filtered"] += len(candidates) - len(kept)
            candidates = kept
        self.candidate_labels = {c.label for c in candidates}
        self.counters["seen"] = len(candidates)
        return candidates

    def _discover_per_unit(self, everything: Sequence[CandidateArtefact],
                           candidates: list[CandidateArtefact]) -> list[CandidateArtefact]:
        """R1-R3: the listing the reader's ``auxiliary_for`` reads, the context trees' candidates (``[import]
        context_artefacts`` entries ``"<role>:<glob>"``) and the pinned objects, each placed right after the file it
        stands for."""
        imp = self.profile.data.get("import", {})
        globs: dict[str, list[str]] = {}
        for entry in imp.get("context_artefacts", ()):
            role, sep, glob = str(entry).partition(":")
            if sep and role in self.context_trees:
                globs.setdefault(role, []).append(glob)
        for role, source in sorted(self.context_trees.items()):
            if getattr(source.tree, "archive_input", False):  # D-530: a download pin, expanded with the role's globs
                walked = self._archive_context(role, source.tree, globs.get(role, ()))
            else:
                walked = [c for c in source.tree.walk() if not _is_stray(c.label)]
            self.role_candidates[role] = [c for c in walked if any(_match(c.label, g) for g in globs.get(role, ()))]
        self.walked = {c.label: c for c in everything if not _is_stray(c.label)}
        self.listing = _AuxListing(self.walked, {r: [c.label for c in cs] for r, cs in self.role_candidates.items()})
        return self._with_overlay(candidates)

    def _with_overlay(self, candidates: list[CandidateArtefact]) -> list[CandidateArtefact]:
        """R3: each pinned object right after the file it stands for (its pointer keeps its own disposition)."""
        if not self.overlay:
            return candidates
        out: list[CandidateArtefact] = []
        for candidate in candidates:
            out.append(candidate)
            pinned = self.overlay.get(candidate.label)
            if pinned is not None and candidate.origin.kind != pinned.origin.kind:
                out.append(CandidateArtefact(candidate.label, pinned.size, pinned.origin))
        return out

    def _is_overlay(self, candidate: CandidateArtefact) -> bool:
        pinned = self.overlay.get(candidate.label)
        return pinned is not None and candidate.origin == pinned.origin

    def _sample_id(self, label: str, origin: Origin) -> str:
        """PR-8 (D-529 x D-530 item 6): the candidate identity a sample keys by. A pinned object shares its pointer's label,
        so it is told apart by a NUL marker (labels never hold control characters); every other candidate keeps its
        label, so samples without pinned objects are unchanged."""
        pinned = self.overlay.get(label)
        return label + "\x00pinned" if pinned is not None and origin == pinned.origin else label

    def _read(self, batch: Sequence[CandidateArtefact]) -> Iterator[tuple[CandidateArtefact, bytes | IngestError]]:
        """The tree's ``read`` for ordinary candidates; a pinned object is read from its verified local copy."""
        plain = iter(self.tree.read([c for c in batch if not self._is_overlay(c)]))
        for candidate in batch:
            if self._is_overlay(candidate):
                yield candidate, read_pinned(self.overlay[candidate.label], self.limits)
            else:
                yield next(plain)

    def _role_globs(self, role: str) -> tuple[str, ...]:
        imp = self.profile.data.get("import", {})
        return tuple(glob for r, sep, glob in (str(e).partition(":") for e in imp.get("context_artefacts", ())) if sep and r == role)

    def _archive_context(self, role: str, archive: Any, globs: Sequence[str]) -> list[CandidateArtefact]:
        """D-530: store an archive context pin's container with the pin's origin (store-first, A2), expand it (AD-12) with
        the role's globs, and return its selected members as candidates (``member`` origins), read back by digest. A
        container the ``expand`` gate rejects is registered by the writer and fails the run, as an archive input does."""
        (container,) = list(archive.walk())
        with archive.stream(container.label) as handle:  # PR-4 (CB-20): checked against the pin before it is published
            put = self.corpus.add_object(handle, container.origin, ext=ext_for_label(container.label),
                                         expected_sha256=archive.sha256, expected_size=getattr(archive, "size", None))
        spec = ContainerSpec(put.sha256, f"{self.snapshot_id}:{role}", container.label, (Selection(include=tuple(globs)),),
                             prefixed=True)  # fmt: skip
        expanded = self.corpus.expand([spec], self.map_pool, limits=self.limits)
        if put.sha256 not in expanded.containers:
            event = next((e for e in expanded.events if e.path == container.label), None)
            self._fail({"snapshot_id": f"{self.snapshot_id}:{role}", "path": container.label}, "expand",
                       event.code if event is not None else "ingest.archive.format", "the context archive was rejected")
            return []
        rows = sorted((r for r in expanded.rows if r.disposition == "selected" and r.container == put.sha256
                       and r.sha256 is not None and r.label is not None), key=lambda r: str(r.label).encode("utf-8"))
        self.context_archives[role] = {"label": container.label, "sha256": put.sha256, "bytes": put.size}
        self.context_readers[role] = _MemberTree(self.corpus.store, {str(r.label): str(r.sha256) for r in rows})
        return [CandidateArtefact(str(r.label), int(r.size or 0), r.origin()) for r in rows if not _is_stray(str(r.label))]

    def store_unit_context(self) -> None:
        """R2: store every context artefact of the context trees before any mapping, with its pinned origin; one the pin
        does not vouch for is registered and left out (as :meth:`store_context` does for the primary tree)."""
        for role, candidates in sorted(self.role_candidates.items()):
            source = self.context_trees[role]
            for candidate, data in self.context_readers.get(role, source.tree).read(candidates):
                subject = {"snapshot_id": f"{self.snapshot_id}:{role}", "path": candidate.label}
                if isinstance(data, IngestError):
                    self._register(subject, data.code, severity="error", stage="ingest", disposition="not_imported",
                                   detail="the context artefact could not be read safely")
                    continue
                origin = source.pin_check.origin_for(candidate, data) if source.pin_check is not None else candidate.origin
                if origin is None:
                    self._register(subject, "raw.origin.blob_mismatch", severity="error", stage="ingest",
                                   disposition="not_imported", detail="context artefact not vouched for by the pin")
                    continue
                put = self.corpus.add_object(data, origin, ext=ext_for_label(candidate.label))
                self.unit_context[f"{role}:{candidate.label}"] = {
                    "label": candidate.label, "origin": origin.to_json(), "sha256": put.sha256, "size": len(data)}

    def _aux_row(self, ref: str) -> dict[str, Any] | None:
        """The stored row of an auxiliary reference: a context label ``"<role>:<label>"`` or a primary-tree label (read,
        vouched for by the pin and stored on first use; a pinned object stands for its label). Every row carries the
        ``media`` type of its label (:func:`aux_media`), so a judge, configuration or attempt file is not recorded as
        ``application/octet-stream``."""
        role, sep, rest = ref.partition(":")
        if sep and role in self.context_trees and ref not in self.walked:
            context = self.unit_context.get(ref)
            return None if context is None else {**context, "media": aux_media(str(context["label"]))}
        if ref in self.aux_rows:
            return self.aux_rows[ref]
        row: dict[str, Any] | None = None
        pinned = self.overlay.get(ref)
        if pinned is not None:
            data = read_pinned(pinned, self.limits)
            if isinstance(data, IngestError):
                self._register(self._path_subject(ref), data.code, severity="error", stage="ingest",
                               disposition="not_imported", detail="the pinned object exceeds the import's size limit")
            elif len(data) == pinned.size and sha256_hex(data) == pinned.sha256:
                put = self.corpus.add_object(data, pinned.origin, ext=ext_for_label(ref))
                row = {"label": ref, "media": aux_media(ref), "origin": pinned.origin.to_json(), "sha256": put.sha256,
                       "size": len(data)}
        elif ref in self.walked:
            candidate = self.walked[ref]
            candidate_data = next(iter(self.tree.read([candidate])))[1]
            if isinstance(candidate_data, IngestError):
                self._register(self._path_subject(ref), candidate_data.code, severity="error", stage="ingest",
                               disposition="not_imported", detail="the auxiliary artefact could not be read safely")
            else:
                origin = self.pin_check.origin_for(candidate, candidate_data) if self.pin_check is not None else candidate.origin
                if origin is None:
                    self._register(self._path_subject(ref), "raw.origin.blob_mismatch", severity="error", stage="ingest",
                                   disposition="not_imported", detail="auxiliary artefact not vouched for by the pin")
                else:
                    put = self.corpus.add_object(candidate_data, origin, ext=ext_for_label(ref))
                    row = {"label": ref, "media": aux_media(ref), "origin": origin.to_json(), "sha256": put.sha256,
                           "size": len(candidate_data)}
        self.aux_rows[ref] = row
        return row

    def _unit_auxiliary(self, label: str) -> list[dict[str, Any]]:
        """R1/R2: the auxiliary rows ``{role, label, sha256, size, origin}`` of one primary, by role; ``copy:<role>``
        files are stored and registered here (``dedup.collapsed`` when byte-identical to ``<role>``), never mapped."""
        assert self.listing is not None
        plan = dict(self.reader.auxiliary_for(label, self.listing))
        rows: list[dict[str, Any]] = []
        for role in sorted(plan):
            if role.startswith("copy:"):
                continue
            row = self._aux_row(str(plan[role]))
            if row is not None:
                rows.append({"role": role, **row})
        for role in sorted(plan):
            if role.startswith("copy:"):
                self._aux_copy(str(plan[role]), plan.get(role.removeprefix("copy:")))
        return rows

    def _aux_copy(self, copy: str, of: str | None) -> None:
        if copy in self.copies_done:
            return
        self.copies_done.add(copy)
        row = self._aux_row(copy)
        if row is None:
            return
        original = self._aux_row(of) if of is not None else None
        if original is not None and original["sha256"] == row["sha256"]:
            self._register(self._path_subject(copy), "dedup.collapsed", severity="info", stage="select", disposition="sealed",
                           detail=f"identical bytes sha256:{str(row['sha256'])[:16]} already stored as a unit's auxiliary artefact")
        else:
            self._register(self._path_subject(copy), "select.not_execution_artefact", severity="info", stage="select",
                           disposition="not_imported", detail="a copy whose bytes differ from the file it copies")

    def _consumed_before(self, label: str) -> None:
        """D-981: a primary skipped because it is already mapped (a resume or ``--retry-failed`` run, or a collapse into
        another snapshot's execution) used its same-tree auxiliary files when it was mapped, so they are used in this run
        too. Without this, a run that skips the unit naming an auxiliary, while a refused primary names it as well (DTap's
        LFS pointer beside its pinned object), registers that auxiliary as not an execution artefact. Only the reader's
        plan is read: nothing is stored or registered here."""
        if not self.per_unit or not isinstance(self.listing, _AuxListing):
            return
        plan = self.reader.auxiliary_for(label, self.listing)
        self.aux_used.update(str(path) for role, path in plan.items()
                             if not str(role).startswith("copy:") and str(path) in self.walked)

    def register_unconsumed_auxiliary(self) -> None:
        """R1: an auxiliary file (not itself a candidate) that every unit naming it left unmapped (a synthetic or LFS-pointer
        trajectory registered ``select.not_execution_artefact``) is registered the same way; it is already stored."""
        for label, detail in sorted(self.aux_refused.items()):
            if label in self.aux_used or label in self.candidate_labels or label in self.copies_done:
                continue
            self._register(self._path_subject(label), "select.not_execution_artefact", severity="info", stage="select",
                           disposition="not_imported", detail=f"{detail} (auxiliary artefact of a file that is not an execution)")

    # -------------------------------------------------------------------------------------- storing
    def _store(self, candidate: CandidateArtefact, data: bytes | IngestError) -> tuple[str, int, Origin] | None:
        """Store one candidate (store-first, A2); ``None`` when it was registered, collapsed or skipped."""
        if isinstance(data, IngestError):
            self._register(self._path_subject(candidate.label), data.code, severity="error", stage="ingest",
                           disposition="not_imported", detail="the input file could not be read safely")
            self.counters["registered"] += 1
            return None
        if self._is_overlay(candidate):  # R3: vouched for by its own pin (sha256 and size), not by the tree's pin check
            pinned = self.overlay[candidate.label]
            if len(data) != pinned.size or sha256_hex(data) != pinned.sha256:
                self._register(self._path_subject(candidate.label), "raw.fetch.digest", severity="error", stage="ingest",
                               disposition="not_imported", detail="the pinned object does not match its pin")
                self.counters["registered"] += 1
                self._fail(self._path_subject(candidate.label), "ingest", "raw.fetch.digest", "pinned object digest")
                return None
            origin: Origin | None = candidate.origin
        else:
            origin = self.pin_check.origin_for(candidate, data) if self.pin_check is not None else candidate.origin
        if origin is None:
            # an --input file the pin does not vouch for: its AER could carry only a local origin, which the release-mode
            # AER writer refuses (C.17 AER-V20), so it is not imported; nothing of it is kept but its digest and size
            self._register(self._path_subject(candidate.label), "raw.origin.blob_mismatch", severity="error",
                           stage="ingest", disposition="not_imported",
                           detail=f"not vouched for by the pin: sha256:{sha256_hex(data)[:16]} size {len(data)}")
            self.counters["registered"] += 1
            self._fail(self._path_subject(candidate.label), "ingest", "raw.origin.blob_mismatch", "not vouched for by the pin")
            return None
        put = self.corpus.add_object(data, origin, ext=ext_for_label(candidate.label))
        sha = put.sha256
        if sha in self.this_run:
            self._register(self._path_subject(candidate.label), "dedup.collapsed", severity="info", stage="select",
                           disposition="sealed", detail=f"identical bytes sha256:{sha[:16]} already selected in this snapshot")
            self.counters["duplicates"] += 1
            return None
        self.this_run.add(sha)
        if not self.multi and self._seen_before(sha, candidate.label):
            self._consumed_before(candidate.label)
            return None
        # multi (R-10k-1, D-320): a file sealed whole as one degenerate AER (strict loader, crashed or limited job) is
        # resumed whole by its document-root key, as a single-item file is by its digest: never re-mapped into items,
        # which would hold the same evidence twice. Otherwise each execution is checked after mapping (_seal_items).
        whole = source_key(sha, {"p": ""})
        ident = self._sample_id(candidate.label, candidate.origin) if self.multi else candidate.label  # PR-8
        if self.multi and self._listing_sample and self.known_keys.get(whole) is not None:  # PR-9: decided after the draw
            self._known_whole.add(ident)
            self._deferred_whole[ident] = (sha, candidate.label)
            return None
        if self.multi and self._seen_before(sha, candidate.label, key=whole):
            self._known_whole.add(ident)  # PR-8: a pinned object apart
            self._consumed_before(candidate.label)
            return None
        return sha, len(data), origin

    # -------------------------------------------------------------------------------------- sealing (T0 write gate)
    def _map_params(self, origin: Origin | None) -> dict[str, Any]:
        params: dict[str, Any] = {"profile": self.profile.id, "limits": self.limits.to_json(), "media": "application/json",
                                  "part": self.part}
        if origin is not None:
            params["origin"] = origin.to_json()
        if self.context:
            params["context"] = list(self.context)
        return params

    def _issue_severity(self, outcome: MapOutcome) -> dict[tuple[Any, ...], str]:
        out: dict[tuple[Any, ...], str] = {}
        for issue, severity in zip(outcome.issues, outcome.severities, strict=False):
            out[(issue.get("code"), issue.get("rule"), tuple(issue.get("ids", ())))] = str(severity)
        return out

    def _seal(self, outcome: MapOutcome, fallback: ExecutionUnit, label: str,
              extra: Sequence[tuple[str, str, str, str]] = ()) -> _Unit | None:
        """Seal one outcome, apply the filters, write the AER and its register entries, validate it (AER validator)."""
        tmp = self.aer_tmp / f"{outcome.ex}.aer.jsonl"
        try:
            info = seal_outcome(outcome, tmp, registry=self.registry, unit=fallback, mapper=self.mapper, profile=self.profile)
        except AerWriteError as exc:
            # the family's degenerate header is itself rejected by the write gate (e.g. a task it cannot name): the
            # artefact stays stored and is registered as failed, never dropped silently (D.2.8; H.6.1 R3)
            found = ",".join(sorted({f.code for f in exc.findings})) or "aer.write.invalid"
            self._register(self._path_subject(label), "map.adapter_defect", severity="error", stage="map",
                           disposition="failed", detail=f"no AER could be sealed ({found})")
            for code, severity, stage, detail in extra:  # e.g. the worker.limit.* that stopped the job (G.4.6)
                self._register(self._path_subject(label), code, severity=severity, stage=stage, disposition="failed",
                               detail=detail)
            self.counters["failed"] += 1
            self._fail(self._path_subject(label), "map", "map.adapter_defect", f"no AER could be sealed ({found})")
            self._rejected_since_unit = True
            return None
        data = tmp.read_bytes()
        tmp.unlink()
        header = strict_json_loads(data.split(b"\n", 1)[0], self.limits)
        assert isinstance(header, dict)
        seal_codes = [str(i.get("code")) for i in info.issues]
        degenerate = outcome.degenerate or bool(set(seal_codes) & _DEGENERATE_CODES)
        if not self.filters.keep(header):
            self.counters["filtered"] += 1
            return None
        ex = info.ex
        self.corpus.write_aer(ex, data)  # a dry run writes into its private temporary tree
        self._commit_carved(data)  # D-218: the carved blobs this written AER cites, and only those
        severities = self._issue_severity(outcome)
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for issue in info.issues:
            grouped.setdefault(str(issue.get("code")), []).append(issue)
        codes: dict[str, str] = {}
        for code, items in grouped.items():
            levels = [
                _FIXED_SEVERITY.get(code) or severities.get((code, i.get("rule"), tuple(i.get("ids", ()))), "warning")
                for i in items
            ]
            severity = max(levels, key=lambda s: _SEVERITY_ORDER.get(s, 1))
            ids = sorted({str(x) for i in items for x in i.get("ids", ())})
            details = [str(i["detail"]) for i in items if i.get("detail")]
            detail = details[0] if len(items) == 1 and details else (f"{len(items)} issues" if len(items) > 1 else "")
            register_code = f"map.{code}"
            self._register({"ex": ex}, register_code, severity=severity, stage="map",
                           disposition="failed" if code in _FAILED_CODES else "sealed", detail=detail,
                           rule=str(items[0].get("rule")) if items[0].get("rule") else None, ids=ids)
            codes[register_code] = severity
        for code, severity, stage, detail in extra:
            self._register({"ex": ex}, code, severity=severity, stage=stage, disposition="failed", detail=detail)
            codes[code] = severity
        report = self._validate_aer(data)
        aer_ok = report.passed if self.mode == "release" else report.ok
        aer_row = {
            "errors": sorted({f.code for f in report.errors}),
            "mode": self.mode,
            "skipped": sorted(report.skipped),
            "verdict": "pass" if aer_ok else "fail",
        }
        if not aer_ok:
            self._register({"ex": ex}, "validate.failed", severity="error", stage="validate", disposition="failed",
                           detail="aer validator: " + ",".join(aer_row["errors"] or aer_row["skipped"]))
            codes["validate.failed"] = "error"
            self._fail({"ex": ex}, "validate", "validate.failed", "the AER validator reported errors")
        if degenerate:
            self.counters["degenerate"] += 1
            first = next((c for c in seal_codes if c in _DEGENERATE_CODES), "adapter_defect")
            self._fail({"ex": ex}, "map", f"map.{first}", str(outcome.error_code or first))
        else:
            self.written += 1
        self.counters["mapped"] += 1
        self.progress.emit(ProgressEvent("step", stage="map", unit=ex))
        for ns, version in dict(header.get("rules", {})).items():
            self.catalogues.setdefault(str(ns), int(version))
        self._rejected_since_unit = False
        return _Unit(ex, label, header, data, info, degenerate, codes, aer_row, aer_ok)

    def _validate_aer(self, data: bytes) -> Any:
        validator = AerValidator(store=_HeldStore(self.corpus.store, self._held), catalogues=self.registry, mode=self.mode,
                                 profile_digests={(self.profile.id, self.profile.version): self.profile.sha256})
        for line in data.splitlines(keepends=True):
            validator.feed(line)
        return validator.finish()

    def _carved(self, result: JobResult, sources: Collection[str]) -> JobResult:
        """Check the blobs a ``map`` job carved (D-218) and **hold** them for this job's units: a held blob is visible to
        the AER validator (:class:`_HeldStore`) and is stored, with its ``carved`` origin, only when an AER written to
        the corpus lists it in ``seal.blobs`` (:meth:`_commit_carved`). So a unit that falls back to a degenerate AER, a
        file sealed whole (D-321 refused rows, a D-323 abort) or a filtered unit leaves no carved object that nothing
        cites. A carved member whose bytes do not hash to its header, or that names a source other than one of the job's
        primary inputs, fails the job (``adapter.carve_mismatch``). The members stay spooled (``io.workers``); bytes are
        read only to hash, validate or store them."""
        self._held = {}
        if not result.ok:
            return result
        for member in (m for m in result.members if m.header.get("role") == "carved"):
            header = member.header
            try:
                digest, size = hashlib.sha256(), 0
                for chunk in member.iter_chunks():
                    digest.update(chunk)
                    size += len(chunk)
                if digest.hexdigest() != header.get("sha256") or size != header.get("size") \
                        or str(header.get("from")) not in sources:
                    raise AgentProvError("a carved blob does not match its header or source")
                origin = Origin.carved(str(header["from"]), header["loc"], str(header["transform"]))
            except (AgentProvError, KeyError, TypeError):
                self._held = {}
                return replace(result, error=AgentProvError("a map job returned a carved blob that does not check",
                                                            code="adapter.carve_mismatch"))
            self._held[str(header["sha256"])] = (member, origin)
        return result

    def _commit_carved(self, data: bytes) -> None:
        """Store the held carved blobs that the written AER ``data`` lists in its ``seal.blobs`` (D-218)."""
        if not self._held or self.dry_run:
            return
        seal = strict_json_loads(data.rstrip(b"\n").rsplit(b"\n", 1)[-1], self.limits)
        for ref in seal.get("blobs", ()) if isinstance(seal, dict) else ():
            held = self._held.get(str(ref).removeprefix("sha256:"))
            if held is not None and not self.corpus.store.has(str(ref).removeprefix("sha256:")):
                member, origin = held
                self.corpus.add_object(io.BufferedReader(_ChunkStream(member.iter_chunks())), origin, ext="bin")
            elif held is not None:
                self.corpus.add_origin(str(ref).removeprefix("sha256:"), held[1])

    def _fallback(self, sha: str, size: int, origin: Origin, variant: str | None = None,
                  loc: Mapping[str, Any] | None = None) -> ExecutionUnit:
        locator = None if loc is None else Locator.from_key(loc, a="a0")
        return degenerate_unit(sha, size, origin, profile=self.profile, mapper=self.mapper, variant=variant, locator=locator)

    def _job_failure(self, result: JobResult, fallback: ExecutionUnit) -> tuple[MapOutcome, list[tuple[str, str, str, str]]]:
        """A crashed or limited ``map`` job: the unit becomes a degenerate AER (``adapter_defect``; G.4.6)."""
        code = result.error.code if result.error is not None else "worker.error"
        ex = import_execution_id(self.mapping, fallback.primary.artefact.sha256, fallback.primary.locator.key())
        outcome = _degenerate(fallback, self.mapper, MapContext(self.profile, self.registry, self.mapping, ex), "adapter_defect", code)
        extra = [(code, "error", "map", "the T1 job was stopped")] if code.startswith("worker.limit.") else []
        return outcome, extra

    # -------------------------------------------------------------------------------------- batches
    def _remaining(self) -> int | None:
        return None if self.limit is None else max(0, self.limit - self.written)

    def map_whole_files(self, batch: Sequence[CandidateArtefact]) -> list[_Unit]:
        return self._map_stored(self._store_files(batch))

    def _store_files(self, batch: Sequence[CandidateArtefact]) -> list[tuple[CandidateArtefact, str, int, Origin]]:
        """Read and store a batch of whole files (store-first, A2); a sampled import's pass 1 stored them already."""
        if self.multi and self.sampled is not None:  # pass 2 of a sampled multi-execution import: pass 1 stored every
            # file (one sealed whole before, NF-34, was resumed or collapsed there and has nothing left to map)
            ids = [self._sample_id(c.label, c.origin) for c in batch]
            return [self._stored_files.pop(i) for i in ids if i in self._stored_files]
        return self._store_batch(batch)

    def _store_batch(self, batch: Sequence[CandidateArtefact]) -> list[tuple[CandidateArtefact, str, int, Origin]]:
        stored: list[tuple[CandidateArtefact, str, int, Origin]] = []
        for candidate, data in self._read(batch) if self.overlay else self.tree.read(batch):
            item = self._store(candidate, data)
            if item is not None:
                stored.append((candidate, *item))
        return stored

    def _whole_file_jobs(self, stored: Sequence[tuple[CandidateArtefact, str, int, Origin]]) -> tuple[
            list[Job], list[list[dict[str, Any]]]]:
        context_inputs = tuple({"sha256": str(c["sha256"]), "role": "context"} for c in self.context)
        aux: list[list[dict[str, Any]]] = [self._unit_auxiliary(c.label) if self.per_unit else [] for c, *_ in stored]
        blobs: list[list[dict[str, Any]]] = [self._blobs_for(c.label) if self.blobs else [] for c, *_ in stored]
        jobs = [
            Job(key=f"{n:09d}", kind="map", limits=self.map_limits,
                inputs=({"sha256": sha, "role": "primary"}, *context_inputs,
                        *({"sha256": str(row["sha256"]), "role": "auxiliary"} for row in aux[n]),
                        *({"sha256": str(row["sha256"]), "role": "blob"} for row in blobs[n])),
                params={**self._map_params(origin), "mode": "total", **({"auxiliary": aux[n]} if aux[n] else {}),
                        **({"blobs": blobs[n]} if blobs[n] else {}), **({"per_item": True} if self.multi else {}),
                        **({"stream": True} if self.stream else {})})
            for n, (_c, sha, _s, origin) in enumerate(stored)
        ]  # fmt: skip
        return jobs, aux

    def _map_stored(self, stored: list[tuple[CandidateArtefact, str, int, Origin]]) -> list[_Unit]:
        if self.until == "raw" or not stored:
            return []
        jobs, aux = self._whole_file_jobs(stored)
        units: list[_Unit] = []
        results = self.map_pool.run(jobs, progress=self._pool_reporter)
        for n, ((candidate, sha, size, origin), result) in enumerate(zip(stored, results, strict=True)):
            same_tree = [str(row["label"]) for row in aux[n] if str(row["label"]) in self.walked]
            # D-414: pass 1 over the frames decides the file's fate; nothing is kept but the summary
            summary = summarise_unit_frames(result.iter_json()) if result.ok else None
            # D-321/D-323 with D-218: a file whose rejected rows are refused, or an aborted streamed file, is sealed
            # whole, so nothing it carved is held and nothing of it is stored
            refused = self._rows_refused(summary, sha) or self._aborted(summary) is not None
            if refused:
                self._held = {}
            else:
                result = self._carved(result, {sha})
            try:
                fallback = self._fallback(sha, size, origin)
                extra: list[tuple[str, str, str, str]] = []
                if not result.ok:
                    outcome, extra = self._job_failure(result, fallback)
                elif summary is not None and summary.not_dialect is not None:
                    frame = summary.not_dialect
                    detail = str(frame.get("detail") or f"not of dialect {self.dialect}")
                    self._register(self._path_subject(candidate.label), "select.not_execution_artefact", severity="info",
                                   stage="select", disposition="not_imported", detail=detail)
                    self.counters["registered"] += 1
                    for label in same_tree:
                        self.aux_refused.setdefault(label, detail)
                    continue
                elif summary is not None and summary.select is not None:  # D.6.12 item 6: a variant of another part
                    chosen = summary.select
                    self._register(self._path_subject(candidate.label), str(chosen["code"]), severity="info",
                                   stage="select", disposition="not_imported", detail=str(chosen.get("detail", "")))
                    self.counters["registered"] += 1
                    continue
                elif self.multi:
                    assert summary is not None
                    units.extend(self._seal_items(result, summary, candidate.label, sha, size, origin))
                    self.aux_used.update(same_tree)
                    continue
                else:
                    outcome = outcome_from_frames(result.iter_json())
                unit = self._seal(outcome, fallback, candidate.label, extra)
                if unit is not None:
                    units.append(unit)
                    self.aux_used.update(same_tree)
            finally:
                self._held = {}  # D-218: held members die with their result
                result.close()
        return units

    @staticmethod
    def _key(unit: ExecutionUnit) -> str:
        return source_key(unit.primary.artefact.sha256, unit.primary.locator.key())

    def _seal_items(self, result: JobResult, summary: FrameSummary, label: str, sha: str, size: int,
                    origin: Origin) -> list[_Unit]:
        """The executions of one ``multi_execution`` file (R-10k-1, D-320), from the ``per_item`` frames, in the reader's
        order. Each is resumed or collapsed by its own source key (H.7.2), and ``--limit`` counts each one.

        D-321: the file's rejected rows (``{"register": {code, detail, loc}}`` frames from the T1 job) are validated here,
        all before any is registered: an allowed code, a key locator naming an element (not the document root) and no
        execution's, and a detail the register accepts. Any failure seals the whole file as one degenerate AER
        (``adapter_defect``, ``adapter.rejected_invalid``), with no row and no execution of it. Valid rows are registered
        in canonical locator order with the subject ``{source_key}`` (``not_imported``; candidates, H.6.1 R1/R5)."""
        abort = summary.abort
        if abort is not None:  # D-323: a streamed file that failed part-way is kept whole, never half imported
            variant = abort.get("variant") if isinstance(abort.get("variant"), str) else None
            issue = "unparseable_artefact" if abort.get("issue") == "unparseable_artefact" else "adapter_defect"
            return self._seal_whole(sha, size, origin, label, issue, str(abort.get("code", "adapter.defect"))[:200],
                                    variant)
        summary.require_framing()  # what split_unit_frames raised, before anything is registered or sealed
        entries = self._summary_entries(summary, sha)
        if entries is None:
            return self._seal_whole(sha, size, origin, label, "adapter_defect", "adapter.rejected_invalid", None)
        for entry in entries:
            if (entry.subject["source_key"], entry.code) in self.known_rejected:
                self.counters["skipped_resume"] += 1
                continue
            self.corpus.add_register(entry)
            self.run_register.append(entry)
            self.issues[entry.code] += 1
            self.counters["registered"] += 1
        units: list[_Unit] = []
        for head, unit_frames in iter_unit_frames(result.iter_json()):  # D-414 pass 2: one unit's frames at a time
            fallback = self._fallback(sha, size, origin, loc=dict(head["loc"]))
            if str(head["sha256"]) != sha:
                raise AgentProvError("a per-item map job framed a unit of another artefact", code="adapter.job_incomplete")
            if self.sampled is not None and f"{self._sample_id(label, origin)}#{self._key(fallback)}" not in self.sampled:
                self.counters["sampled_out"] += 1  # D-529: mapped in this file's job, never sealed or written
                continue
            if self._seen_before(sha, label, key=self._key(fallback)):
                continue
            remaining = self._remaining()
            if remaining is not None and remaining <= 0:
                break
            unit = self._seal(outcome_from_frames(unit_frames), fallback, label)
            if unit is not None:
                units.append(unit)
        return units

    @staticmethod
    def _aborted(summary: FrameSummary | None) -> dict[str, Any] | None:
        """The ``abort`` frame of a streamed ``per_item`` job (D-323), if any (``None`` for a failed job)."""
        return None if summary is None else summary.abort

    def _seal_whole(self, sha: str, size: int, origin: Origin, label: str, issue: str, code: str,
                    variant: str | None) -> list[_Unit]:
        """Seal a multi-execution file whole as one degenerate AER (document-root locator; D-320 rule)."""
        fallback = self._fallback(sha, size, origin, variant)
        ex = import_execution_id(self.mapping, sha, fallback.primary.locator.key())
        outcome = _degenerate(fallback, self.mapper, MapContext(self.profile, self.registry, self.mapping, ex), issue, code)
        unit = self._seal(outcome, fallback, label)
        return [unit] if unit is not None else []

    def _rows_refused(self, summary: FrameSummary | None, sha: str) -> bool:
        """Whether a ``per_item`` job's rejected rows fail validation (D-321), checked before its carved blobs are stored
        (D-218): the file is then one degenerate AER, and a blob no AER of it cites is never stored."""
        if not self.multi or summary is None:
            return False
        if summary.framing_error:
            return False  # not per-item frames (not_dialect, select): nothing carved is kept by those paths anyway
        return bool(summary.rows) and self._summary_entries(summary, sha) is None

    def _summary_entries(self, summary: FrameSummary, sha: str) -> list[RegisterEntry] | None:
        """:meth:`_rejected_entries` of a file's pass-1 summary, computed once (D-414)."""
        if not summary.entries_done:
            summary.entries = self._rejected_entries(summary.rows, sha, [dict(head["loc"]) for head in summary.heads])
            summary.entries_done = True
        return summary.entries

    def _rejected_entries(self, rows: Sequence[Mapping[str, Any]], sha: str,
                          executions: Sequence[Mapping[str, Any]]) -> list[RegisterEntry] | None:
        """The register entries of a file's rejected rows (D-321), in canonical locator order, or ``None`` when any row is
        invalid (the T1 job saw untrusted bytes, so nothing it reports is registered unchecked)."""
        taken = {jcs_bytes(canonical_key_loc(loc)) for loc in executions}
        out: list[tuple[bytes, RegisterEntry]] = []
        for row in rows:
            try:
                code, detail, loc = row["code"], row["detail"], row["loc"]
                if code not in _REJECTED_CODES or not isinstance(detail, str) or not isinstance(loc, Mapping):
                    return None
                key_loc = canonical_key_loc(loc)
                canon = jcs_bytes(key_loc)
                if key_loc in ({}, {"p": ""}) or canon in taken:
                    return None
                taken.add(canon)
                out.append((canon, RegisterEntry(subject={"source_key": source_key(sha, key_loc)}, code=code,
                                                 severity="info", stage="select", disposition="not_imported",
                                                 detail=detail)))
            except (KeyError, TypeError, ValueError, RegisterError):
                return None
        return [entry for _canon, entry in sorted(out, key=lambda pair: pair[0])]

    def map_containers(self, batch: Sequence[CandidateArtefact]) -> list[_Unit]:
        cached = [self._expanded_containers.pop(c.label) for c in batch if c.label in self._expanded_containers]
        if cached:  # a sampled import's pass 1 stored and expanded these already (never twice: dedup.collapsed)
            units: list[_Unit] = []
            for specs, labels, expanded in cached:
                units.extend(self._map_expanded(specs, labels, expanded))
            return units
        return self._map_expanded(*self._expand_containers(batch))

    def _expand_containers(self, batch: Sequence[CandidateArtefact]) -> tuple[list[ContainerSpec], dict[str, str], Any]:
        """Store and expand a batch of containers; ``expanded`` is ``None`` when nothing was stored."""
        specs: list[ContainerSpec] = []
        labels: dict[str, str] = {}
        selection = Selection(include=self.reader.member_patterns(self.profile))
        for candidate, data in self.tree.read(batch):
            item = self._store(candidate, data)
            if item is not None:
                # D-380: a container member of an archive input opens at its absolute level, under its chain's depth
                # allowance, with the archive input's subject prefix (one subject rule, D-384)
                depth, allowance = self.archive_meta.get(candidate.label, (1, None))
                specs.append(ContainerSpec(item[0], self.snapshot_id, self._path_subject(candidate.label)["path"],
                                           (selection,), depth=depth, max_depth=allowance, prefixed=self.archive))
                labels[item[0]] = candidate.label
        if not specs:
            return specs, labels, None
        expanded = self.corpus.expand(specs, self.map_pool, limits=self.limits)
        self.counters["registered"] += sum(1 for e in expanded.events if e.disposition == "not_imported")
        return specs, labels, expanded

    def _container_jobs(self, specs: Sequence[ContainerSpec], by_container: Mapping[str, list[Any]], expanded: Any, *,
                        plan_only: bool = False, units_param: Mapping[str, list[str]] | None = None) -> tuple[
                            list[Job], list[str]]:
        jobs: list[Job] = []
        job_containers: list[str] = []
        for spec in specs:
            rows = by_container.get(spec.sha256, [])
            if spec.sha256 not in expanded.containers:
                continue  # expansion registered its own not_imported or failed event
            subject = {"snapshot_id": spec.snapshot_id, "path": spec.path}  # the candidate's subject, as _path_subject made it
            if not rows:  # RD-3 (CD-6): one disposition per candidate (H.6.1 R1), never a silent skip
                self._register(subject, "select.not_execution_artefact", severity="info",
                               stage="select", disposition="not_imported", detail="container holds no member the reader selects")
                self.counters["registered"] += 1
                continue
            if not self.dry_run:  # RD-3 (CD-9): a resumed container's earlier plan-job failure does not outlive this job
                self.corpus.discard_failure(subject)
            listed = [{"label": r.label, "origin": r.origin().to_json(), "sha256": r.sha256, "size": r.size} for r in rows]
            extra: dict[str, Any] = {"plan_only": True} if plan_only else {}
            if units_param is not None:
                extra["units"] = list(units_param.get(spec.sha256, []))
            jobs.append(Job(key=f"{len(jobs):09d}", kind="map", limits=self.map_limits,
                            inputs=tuple({"sha256": str(r.sha256), "role": "member"} for r in rows),
                            params={**self._map_params(None), "mode": "container", "members": listed, **extra}))
            job_containers.append(spec.sha256)
        return jobs, job_containers

    @staticmethod
    def _member_rows(expanded: Any) -> dict[str, list[Any]]:
        by_container: dict[str, list[Any]] = {}
        for row in expanded.rows:
            if row.disposition == "selected" and row.sha256 is not None and row.label is not None and row.size is not None:
                by_container.setdefault(row.container, []).append(row)
        return by_container

    def _map_expanded(self, specs: list[ContainerSpec], labels: dict[str, str], expanded: Any) -> list[_Unit]:
        if expanded is None or self.until == "raw":
            return []
        by_container = self._member_rows(expanded)
        units_param: dict[str, list[str]] | None = None
        if self.sampled is not None:  # D-529: every member is an input (the plan needs them); only sampled units map
            units_param = {}
            for spec in specs:
                label = labels[spec.sha256]
                planned = self._planned_units.get(label, [])
                units_param[spec.sha256] = sorted(u for u in planned if f"{label}!/{u}" in self.sampled)
                self.counters["sampled_out"] += len(planned) - len(units_param[spec.sha256])
        jobs, job_containers = self._container_jobs(specs, by_container, expanded, units_param=units_param)
        units: list[_Unit] = []
        results = self.map_pool.run(jobs, progress=self._pool_reporter) if jobs else []
        for container, result in zip(job_containers, results, strict=True):
            label = labels[container]
            member_rows = {str(r.sha256): r for r in by_container[container]}
            result = self._carved(result, set(member_rows))
            try:
                if not result.ok:
                    code = result.error.code if result.error is not None else "worker.error"
                    self._register(self._path_subject(label), "map.adapter_defect", severity="error", stage="map",
                                   disposition="failed", detail=f"container plan job failed ({code})")
                    if code.startswith("worker.limit."):
                        self._register(self._path_subject(label), code, severity="error", stage="map", disposition="failed",
                                       detail="the T1 job was stopped")
                    self.counters["failed"] += 1
                    self._fail(self._path_subject(label), "map", "map.adapter_defect", code)
                    continue
                summary = summarise_unit_frames(result.iter_json())  # D-414 pass 1
                summary.require_framing()  # what split_unit_frames raised, before any row is registered
                for plan_row in summary.rows:
                    path = f"{label}!/{plan_row['label']}" if plan_row.get("label") else label
                    self._register(self._path_subject(path), str(plan_row["code"]), severity="info", stage="select",
                                   disposition="not_imported", detail=str(plan_row.get("detail", "")))
                    self.counters["registered"] += 1
                if not summary.rows and not summary.heads:  # RD-3 (CD-6): a plan with no unit and no row (H.6.1 R1)
                    self._register(self._path_subject(label), "select.not_execution_artefact", severity="info",
                                   stage="select", disposition="not_imported", detail="container plan yields no execution")
                    self.counters["registered"] += 1
                for head, frames in iter_unit_frames(result.iter_json()):  # pass 2: one unit's frames at a time
                    sha = str(head["sha256"])
                    subject = f"{label}!/{member_rows[sha].label}" if sha in member_rows else label
                    if sha in self.this_run:  # RD-3 (CD-5): a member byte-identical to one selected earlier in this run
                        self._register(self._path_subject(subject), "dedup.collapsed", severity="info", stage="select",
                                       disposition="sealed",
                                       detail=f"identical bytes sha256:{sha[:16]} already selected in this snapshot")
                        self.counters["duplicates"] += 1
                        continue
                    if self._seen_before(sha, subject):
                        continue
                    remaining = self._remaining()
                    if remaining is not None and remaining <= 0:
                        break
                    self.this_run.add(sha)
                    member = member_rows[sha]
                    fallback = self._fallback(sha, int(member.size), member.origin())
                    unit = self._seal(outcome_from_frames(frames), fallback, f"{label}!/{member.label}")
                    if unit is not None:
                        units.append(unit)
            finally:
                self._held = {}  # D-218: held members die with their result
                result.close()
        return units

    # -------------------------------------------------------------------------------------- SEM, PROV and validation
    @property
    def _post_aer(self) -> bool:
        """The T1 ``prov`` job runs: SEM is requested (``--until sem`` and later) or PROV is."""
        return (self.until == "sem" and bool(self.semantics)) or self.until in ("prov", "validation")

    def submit_prov(self, units: Sequence[_Unit]) -> list[tuple[_Unit, str | None]]:
        """The ``prov`` jobs of ``units`` (inputs staged in the scratch store); ``None`` for a unit that is not derived."""
        staged: list[tuple[_Unit, str | None]] = []
        for unit in units:
            if self._post_aer and unit.aer_ok:
                staged.append((unit, self.scratch_store.put(unit.data, ext="jsonl").sha256))
            else:
                staged.append((unit, None))
        return staged

    def run_prov(self, staged: Sequence[tuple[_Unit, str | None]]) -> list[JobResult]:
        digests = [sha for _unit, sha in staged if sha is not None]
        jobs = [
            Job(key=f"{n:09d}", kind="prov", limits=self.prov_limits, inputs=({"sha256": sha, "role": "aer"},),
                params={"spec": SPEC_ID, "strict": self.mode == "release", "validate": self.until == "validation",
                        "semantics": list(self.semantics), "derive": self.until in ("prov", "validation"),
                        **({} if self.prov_conformance else {"conformance": False}),
                        **({"fidelity": {"collect": True, "hint": False}}
                           if self.validation_cache is not None and self.until == "validation" and self.prov_conformance
                           else {})})
            for n, sha in enumerate(digests)
        ]  # fmt: skip
        return self.prov_pool.run(jobs, progress=self._pool_reporter) if jobs else []

    def finish(self, staged: Sequence[tuple[_Unit, str | None]], results: Sequence[JobResult]) -> None:
        pending = iter(results)
        for unit, sha in staged:
            prov: dict[str, StageOutput] | None = None
            sem: dict[str, StageOutput] | None = None
            validation: StageOutput | None = None
            row: dict[str, Any] = {"aer": unit.aer_row, "checks": {"aer.validator": unit.aer_row["verdict"]}}
            if self._post_aer:
                if sha is None:
                    sem = {ref: StageOutput("skipped") for ref in self.semantics} or None
                    prov = {SPEC_ID: StageOutput("skipped")} if self.until in ("prov", "validation") else None
                else:
                    result = next(pending)
                    try:
                        sem, tier3 = self._sem_result(unit, result)
                        row["checks"].update(tier3)
                        if self.until in ("prov", "validation"):
                            prov, tier4 = self._prov_result(unit, result)
                            if tier4 is not None:
                                row.update(spec=SPEC_ID, versions=tier4["versions"])
                                row["checks"].update(tier4["checks"])
                    finally:
                        result.close()
                        _unlink_object(self.scratch_store.path_for(sha, "jsonl"))
            if self.until == "validation":
                verdicts = [unit.aer_row["verdict"]]
                if prov is not None and prov[SPEC_ID].state == "ok" and all(o.state == "ok" for o in (sem or {}).values()):
                    verdicts.append(self._tier4_verdict(row))
                else:
                    verdicts.append("fail")
                row["verdict"] = "pass" if set(verdicts) == {"pass"} else "fail"
                self.progress.emit(ProgressEvent("step", stage="validate", unit=unit.ex,
                                                 status="ok" if row["verdict"] == "pass" else "failed"))
                if row["verdict"] == "pass":
                    self.counters["validated"] += 1
                elif unit.aer_ok and prov is not None and prov[SPEC_ID].state == "ok":
                    failing = sorted(k for k, v in row["checks"].items() if v == "fail" or (v == "skipped" and self.mode == "release"))
                    self._register({"ex": unit.ex}, "validate.failed", severity="error", stage="validate", disposition="failed",
                                   detail="tiers 3-4: " + ",".join(failing))
                    unit.codes["validate.failed"] = "error"
                    self._fail({"ex": unit.ex}, "validate", "validate.failed", "tier-3 or tier-4 checks failed")
                validation = StageOutput("ok" if row["verdict"] == "pass" else "failed", self.corpus.add_validation(unit.ex, row))
            self._index(unit, prov, validation, sem)

    def _tier4_verdict(self, row: Mapping[str, Any]) -> str:
        statuses = [v for k, v in row["checks"].items() if k != "aer.validator"]
        bad = {"fail", "skipped"} if self.mode == "release" else {"fail"}
        # no check beyond the AER validator fails only when tier 4 should have run: with --skip-prov-conformance and no
        # semantics profile nothing is left to check (ultrareview pipeline #2; G2c-5 skips tier 4, it fails nothing)
        missing = not statuses and self.prov_conformance
        return "fail" if missing or any(s in bad for s in statuses) else "pass"

    def _prov_result(self, unit: _Unit, result: JobResult) -> tuple[dict[str, StageOutput], dict[str, Any] | None]:
        if not result.ok:
            code = result.error.code if result.error is not None else "worker.error"
            return self._prov_failed(unit, code), None
        errors = [frame["prov_error"] for frame in result.json if "prov_error" in frame]
        members = [m for m in result.members if m.header.get("role") == "prov"]
        if errors or not members:
            return self._prov_failed(unit, str(errors[0]) if errors else "prov.no_output"), None
        data = members[0].read_bytes()
        digest = self.corpus.write_prov(SPEC_ID, unit.ex, data)
        self.counters["derived"] += 1
        self.progress.emit(ProgressEvent("step", stage="prov", unit=unit.ex))
        tier4 = next((frame["validation"] for frame in result.json if "validation" in frame), None)
        if self.validation_cache is not None:  # D-550: the job's completed round trip, checked against these bytes
            for frame in result.json:
                if "fidelity" in frame:
                    self.validation_cache.store_frame(data, frame["fidelity"])
        return {SPEC_ID: StageOutput("ok", digest)}, tier4

    def _sem_result(self, unit: _Unit, result: JobResult) -> tuple[dict[str, StageOutput] | None, dict[str, str]]:
        """The SEM stage of one unit: each produced document is re-read and verified (strict reader, seal) before it is
        written; its index digest is the SEM digest. Returns the stage map (``None`` when no profile applies) and the
        tier-3 checks."""
        if not self.semantics:
            return None, {}
        if not result.ok:
            code = result.error.code if result.error is not None else "worker.error"
            return {ref: self._sem_failed(unit, ref, code) for ref in self.semantics}, {}
        out: dict[str, StageOutput] = {}
        for frame in result.json:
            if "sem_error" in frame:
                ref = str(frame["sem_error"]["profile"])
                out[ref] = self._sem_failed(unit, ref, str(frame["sem_error"]["code"]))
        for member in result.members:
            if member.header.get("role") != "sem":
                continue
            ref, data = str(member.header["profile"]), member.read_bytes()
            try:
                doc = load_sem_bytes(data)
            except AgentProvError as exc:
                out[ref] = self._sem_failed(unit, ref, exc.code)
                continue
            if doc.ex != unit.ex or doc.aer_digest != unit.seal.execution_digest:
                out[ref] = self._sem_failed(unit, ref, "sem.aer_digest")
                continue
            self.corpus.write_sem(ref, unit.ex, data)
            out[ref] = StageOutput("ok", doc.digest)
        for ref in self.semantics:
            if ref not in out:
                out[ref] = self._sem_failed(unit, ref, "sem.no_output")
        checks: dict[str, str] = {}
        for frame in result.json:
            if "sem_validation" in frame:
                checks.update(frame["sem_validation"]["checks"])
        self.counters["annotated"] += sum(1 for o in out.values() if o.state == "ok")
        return out, checks

    def _sem_failed(self, unit: _Unit, ref: str, code: str) -> StageOutput:
        self._register({"ex": unit.ex}, "sem.failed", severity="error", stage="sem", disposition="failed", detail=f"{ref}: {code}")
        unit.codes["sem.failed"] = "error"
        self._fail({"ex": unit.ex}, "sem", "sem.failed", f"{ref}: {code}")
        return StageOutput("failed")

    def _prov_failed(self, unit: _Unit, code: str) -> dict[str, StageOutput]:
        self._register({"ex": unit.ex}, "prov.failed", severity="error", stage="prov", disposition="failed", detail=code)
        unit.codes["prov.failed"] = "error"
        self._fail({"ex": unit.ex}, "prov", "prov.failed", code)
        return {SPEC_ID: StageOutput("failed")}

    # -------------------------------------------------------------------------------------- index entry
    def _index(self, unit: _Unit, prov: dict[str, StageOutput] | None, validation: StageOutput | None,
               sem: dict[str, StageOutput] | None = None) -> None:
        header = unit.header
        accounting_doc = unit.seal.accounting.to_json()
        accounting = str(accounting_doc.get("status"))
        checks = accounting_doc.get("checks")
        seal_codes = {c.removeprefix("map.") for c in unit.codes}
        kept: frozenset[str] = frozenset()
        if "missing_tool_result" in seal_codes:  # a declared removal keeps its result as an artefact (D-372)
            kept = kept_results(json.loads(line) for line in unit.data.splitlines() if line.strip())
        unproven = (seal_codes & _LOSS_CODES) - proven_loss_codes(unit.seal.issues, kept)  # inferred loss: D.5.4, D-24
        completeness = index_completeness(
            degenerate=unit.degenerate, accounting=accounting, checks_evaluated=len(checks) if isinstance(checks, list) else 0,
            unit_kind=str(header.get("unit")), seal_codes=seal_codes - unproven)
        key = header["source_key"]
        artefacts = list(header.get("artifacts", ()))
        entry = ExecutionEntry(
            ex=unit.ex,
            mode=self.index_mode,
            unit=str(header.get("unit")),
            source_id=self.source_id,
            snapshot_ids=(self.snapshot_id,),
            source_key=source_key(str(key["sha256"]), key["loc"]),
            raw=tuple(RawRef(str(a["sha256"]), str(a["role"]), True) for a in artefacts),
            adapter=f"{header['adapter']['id']}@{header['adapter']['version']}",
            profile=f"{self.profile.id}@{self.profile.version}",
            aer_digest=unit.seal.execution_digest,
            stages={"raw": "ok", "aer": "ok" if unit.aer_ok else "failed"},
            completeness=completeness,
            execution_observed=header.get("unit") != "outcome_only" and "no_execution_observed" not in seal_codes,
            issues=tuple(sorted(unit.codes)),
            prov=prov,
            validation=validation,
            sem=sem,
            attempt=self.attempt_of(unit.ex),
        )
        self.corpus.add_execution(entry)
        if not unit.degenerate:
            self.indexed += 1
        levels = set(unit.codes.values())
        failed = unit.degenerate or "error" in levels or (prov is not None and prov[SPEC_ID].state == "failed") or any(
            o.state == "failed" for o in (sem or {}).values()) or (
            validation is not None and validation.state == "failed") or not unit.aer_ok
        if failed and not unit.degenerate:
            self.counters["failed"] += 1
        elif not failed:
            self.counters["sealed_with_issues" if "warning" in levels else "sealed_clean"] += 1
        status = "failed" if failed else "sealed_with_issues" if "warning" in levels else "sealed"
        self.progress.emit(ProgressEvent("unit_done", unit=unit.ex, status=status, codes=tuple(sorted(unit.codes)),
                                         fields={"unit_kind": "execution"}))

    # -------------------------------------------------------------------------------------- run
    def _stage(self, name: str, phase: str, **fields: Any) -> None:
        """A corpus-level ``stage`` event (D-393, agentprov-progress/0.2); metadata only (F1)."""
        self.progress.emit(ProgressEvent("stage", stage=name, fields={"phase": phase, **fields}))

    def run(self) -> None:
        from agentprov import drain

        if self.honour_drain:
            drain.drain_supported()  # D-394: the batch loop below checks it at each batch boundary
        self._stage("discover", "begin")
        candidates = self.discover()
        self._stage("discover", "end", done=len(candidates), total=len(candidates))
        workers = self.map_pool.workers
        many = self.container or self.multi  # a candidate holds several executions: no execution total yet
        self.progress.emit(ProgressEvent("start", total=None if many else len(candidates), fields={
            "command": "import", "source": self.source_id, "plan": f"{self.part} -> {self.until}", "workers": workers,
            "unit_kind": "execution", "candidates": len(candidates),
            "candidate_kind": "container" if self.container else "file"}))
        if self.pin_check is not None and isinstance(self.tree, LocalTree):
            self.pin_check.prepare(self.tree, self.pin_candidates)
        if self.context_candidates or self.blob_candidates or self.role_candidates:
            self._stage("store", "begin")
        if self.context_candidates:
            self.store_context()
        if self.blob_candidates:
            self.store_blobs()
        if self.role_candidates:
            self.store_unit_context()
        if self.context_candidates or self.blob_candidates or self.role_candidates:
            self._stage("store", "end")
        if self.limit == 0:
            return
        if self.sample is not None:
            candidates = self._plan_sample(candidates)
        position = 0
        self._stage("map", "begin", total=len(candidates))
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="agentprov-prov") as background:
            pending: tuple[list[tuple[_Unit, str | None]], Future[list[JobResult]]] | None = None
            while position < len(candidates):
                remaining = self._remaining()
                if remaining is not None and remaining <= 0:
                    break
                if self.honour_drain and drain.draining():  # D-394: finish what is in flight, flush, stop
                    self.drained = True
                    break
                # RD-3 (CD-7): under a limit, a candidate that holds several executions (a container, a multi_execution
                # file) is taken alone, so nothing past the limit is stored or expanded, whatever the batch size
                if remaining is None:
                    size = self.batch_size
                else:
                    size = 1 if self.container or self.multi else min(self.batch_size, remaining)
                batch = candidates[position : position + size]
                position += len(batch)
                units = self.map_containers(batch) if self.container else self.map_whole_files(batch)
                self.clean_tail = self._ends_counted(batch, units)
                if pending is not None:
                    self.finish(pending[0], pending[1].result())
                    pending = None
                staged = self.submit_prov(units)
                pending = (staged, background.submit(self.run_prov, staged))
                self._stage("map", "progress", done=position, total=len(candidates))
            if pending is not None:
                self.finish(pending[0], pending[1].result())
        self._stage("map", "end", done=position, total=len(candidates))
        self._pool_reporter.close()
        if self.drained:
            self.notices.append(f"drained (--control-file): stopped after {position} of {len(candidates)} candidate(s); "
                                "re-run the same command to resume")
        if self.per_unit:
            self.register_unconsumed_auxiliary()

    def _ends_counted(self, batch: Sequence[CandidateArtefact], units: Sequence[_Unit]) -> bool:
        """D-610 review: whether ``batch`` ends, in candidate order, in a counted unit: its last unit is not degenerate and
        belongs to the batch's last candidate (a whole file, a multi-execution file, or a container's ``label!/member``,
        compared by prefix: a container inside an archive input has ``!/`` in its own label). One rule for every kind:
        the cap counts units and a re-map cuts per unit inside a file or container too, so a degenerate item after a
        candidate's last counted one is not reproduced (second review, probe 5). Job-level register rows and dedup
        members repeat in a re-map and need nothing here."""
        last = units[-1] if units else None
        label = batch[-1].label
        return last is not None and not last.degenerate and not self._rejected_since_unit and (
            last.label == label or last.label.startswith(label + "!/"))  # PR-11 #6: nor a write-gate rejection after it

    def _plan_sample(self, candidates: list[CandidateArtefact]) -> list[CandidateArtefact]:
        """D-529 pass 1: list every execution's sample key, choose the sample, and return the candidates that hold a
        sampled execution, in their original order. Whole files are listed by label and only the chosen ones are ever
        stored. Containers are stored and expanded here (their members are known only then; the user's choice,
        2026-10-15), and multi-execution files are stored and mapped once to list their items. Both are kept for pass 2,
        which maps only the sampled members or seals only the sampled items."""
        assert self.sample is not None
        stratum = getattr(self.reader, "sample_stratum", None)  # spread without one was refused before any write

        def arm(label: str) -> str | None:
            return str(stratum(label)) if callable(stratum) and stratum(label) is not None else None

        keys: list[tuple[str, str | None]] = []
        holders: dict[str, str] = {}  # sample key -> candidate label
        # PR-8: an LFS pointer whose pinned object is imported beside it yields no execution, only its register row; it
        # never competes in the sample and passes together with its object (RC-5)
        pointers = {c.label for c in candidates if c.label in self.overlay and not self._is_overlay(c)}
        listed: dict[str, tuple[CandidateArtefact, str, int, Origin]] = {}  # multi: stored in pass 1, for pass 2
        for start in range(0, len(candidates), self.batch_size):
            batch = candidates[start : start + self.batch_size]
            if self.container:
                specs, labels, expanded = self._expand_containers(batch)
                if expanded is not None:
                    by_label = {labels[spec.sha256]: spec for spec in specs}
                    for candidate in batch:
                        if candidate.label in by_label:
                            self._expanded_containers[candidate.label] = (
                                [by_label[candidate.label]], {by_label[candidate.label].sha256: candidate.label}, expanded)
                    jobs, job_containers = self._container_jobs(specs, self._member_rows(expanded), expanded, plan_only=True)
                    for container, result in zip(job_containers, self.map_pool.run(jobs) if jobs else [], strict=True):
                        label = labels[container]
                        try:
                            heads = [h for h, _frames in iter_unit_frames(result.iter_json())] if result.ok else []
                        except AgentProvError:
                            heads = []
                        finally:
                            self._held = {}
                            result.close()
                        planned = [str(h["label"]) for h in heads]
                        self._planned_units[label] = planned
                        for unit_label in planned or [""]:  # a container whose plan fails is one unit (its failure)
                            key = f"{label}!/{unit_label}"
                            keys.append((key, arm(key)))
                            holders[key] = label
            elif self.multi:
                self._listing_sample = True
                try:
                    stored = self._store_batch(batch)
                finally:
                    self._listing_sample = False
                jobs, _aux = self._whole_file_jobs(stored)
                for (candidate, sha, size, origin), result in zip(stored, self.map_pool.run(jobs) if jobs else [],
                                                                  strict=True):
                    ident = self._sample_id(candidate.label, candidate.origin)  # PR-8: never the label alone
                    listed[ident] = (candidate, sha, size, origin)
                    if ident in pointers:
                        self._held = {}
                        result.close()
                        continue
                    try:
                        summary = summarise_unit_frames(result.iter_json()) if result.ok else None
                        heads = [] if summary is None or summary.abort is not None or summary.framing_error else summary.heads
                        if heads and self._rows_refused(summary, sha):  # PR-11 #3: D-321 seals it whole, as pass 2 does
                            heads = []
                    except AgentProvError:
                        heads = []
                    finally:
                        self._held = {}
                        result.close()
                    found = [f"{ident}#{self._key(self._fallback(sha, size, origin, loc=dict(h['loc'])))}"
                             for h in heads]
                    for key in found or [f"{ident}#"]:  # a file with no item is one unit (sealed whole)
                        keys.append((key, arm(candidate.label)))
                        holders[key] = ident
                # NF-34 (regen item 128): a file the corpus holds sealed whole was skipped by _store (resume, or collapse
                # from another snapshot) before it could be listed; it stays a candidate under the key it was drawn by,
                # so a resumed sample chooses the same set (D-529) instead of a different one whose union is written
                for candidate in batch:
                    ident = self._sample_id(candidate.label, candidate.origin)
                    if ident in self._known_whole:
                        keys.append((f"{ident}#", arm(candidate.label)))
                        holders[f"{ident}#"] = ident
            else:
                for candidate in batch:
                    ident = self._sample_id(candidate.label, candidate.origin)
                    if ident in pointers:
                        continue
                    keys.append((ident, arm(candidate.label)))
                    holders[ident] = ident
        self._stored_files = listed
        chosen = select_sample(keys, self.sample)
        for ident, (sha, label) in self._deferred_whole.items():  # PR-9: resumed or collapsed only when drawn (PR-8 id)
            if f"{ident}#" in chosen:
                self._seen_before(sha, label, key=source_key(sha, {"p": ""}))
        self._deferred_whole = {}
        whole = {k for k in chosen if k.endswith("#")}  # files sealed whole keep every outcome of theirs
        self.sampled = chosen | frozenset(k for k, _ in keys if any(k.startswith(w) for w in whole))
        files = {holders[k] for k in chosen}
        # RC-5: a pointer passes exactly when its pinned object does, so a sampled import writes the full import's rows for
        # the sampled units (a pointer without its object would dispose its siblings differently, e.g. DTap's judge file)
        files |= {p for p in pointers if self._sample_id(p, self.overlay[p].origin) in files}
        self.sample_record = {"n": self.sample.n, "mode": self.sample.mode, "seed": self.sample.seed,
                              "candidates": len({k for k, _ in keys}), "selected": len(chosen),
                              "stratum": "reader" if callable(stratum) else None}
        for label in [label for label in self._stored_files if label not in files]:
            self._stored_files.pop(label)  # stored in pass 1, sampled out: no execution of it is written
        for label in [label for label in self._expanded_containers if label not in files]:
            self._expanded_containers.pop(label)
        self.counters["sampled_out"] += sum(1 for k, _ in keys if k not in self.sampled and holders[k] not in files)
        return [c for c in candidates if self._sample_id(c.label, c.origin) in files]

    def close(self) -> None:
        shutil.rmtree(self.scratch, onexc=_make_writable_and_retry)

    # -------------------------------------------------------------------------------------- documents
    def expand_selections(self) -> list[Selection]:
        """The selections of every expansion this import runs (D-380): the archive input's and those of the nested
        archives it declares (D-382), then the container dialect's members; each is one ``expand`` stage definition."""
        out = self.archive_selection().nodes() if self.archive else []
        if self.container:
            out.append(Selection(include=self.reader.member_patterns(self.profile)))
        for role, source in sorted(self.context_trees.items()):  # D-530: an archive context pin's expansion
            if getattr(source.tree, "archive_input", False):
                out.append(Selection(include=self._role_globs(role)))
        return out

    def stage_definitions(self, selections: Sequence[Selection] | None) -> list[dict[str, Any]]:
        stages: list[dict[str, Any]] = []
        for selection in selections or ():
            definition = _with_digest(expand_fn_definition(self.limits, selection))
            if all(stage["fn_digest"] != definition["fn_digest"] for stage in stages):
                stages.append(definition)
        adapter_dir = f"adapters/{self.profile.family}"
        stages.append(_with_digest({
            "stage": "aer", "fn": "map",
            "adapter": f"{self.mapper.mapper_id}@{self.mapper.version}",
            "adapter_code_sha256": "sha256:" + code_sha256([adapter_dir]),
            "profile": f"{self.profile.id}@{self.profile.version}", "profile_sha256": "sha256:" + self.profile.sha256,
            "rules": dict(sorted(self.catalogues.items())),
            "rules_sha256": {ns: "sha256:" + load_catalogue(ns, v).digest for ns, v in sorted(self.catalogues.items())},
            "format": AER_FORMAT_ID,
            "engine": f"agentprov@{__version__}",
            "engine_code_sha256": "sha256:" + code_sha256(aer_scope(self.profile.family)),  # D-451 addendum
            "limits_sha256": "sha256:" + sha256_hex(jcs_bytes(self.limits.to_json())),
            # ultrareview pipeline #5: a release-mode import says so (the AER validator is strict and the writer's
            # release guards apply), so derive, recompute and verify know it whatever --until was; a dev-mode stage is
            # unchanged
            **({"mode": "release"} if self.mode == "release" else {}),
        }))  # fmt: skip
        if self._post_aer and self.semantics:
            from agentprov.adapters.semantics_profiles import load_semantics_profile
            from agentprov.sem.profiles import parse_profile_ref

            loaded = [load_semantics_profile(*parse_profile_ref(ref)) for ref in self.semantics]
            stages.append(_shared.sem_stage_definition([
                _shared.SemanticsInfo(f"{p.id}@{p.version}", p.sha256, dict(p.rules), _family_of(p)) for p in loaded]))
        if self.until in ("prov", "validation"):
            stages.append(_shared.prov_stage_definition())
        if self.until == "validation":
            # G2c-5: a skipped tier 4 is part of the stage's identity (a corpus never mixes the two), and only then
            stages.append(_shared.validation_stage_definition(self.semantics, self.mode,
                                                              prov_conformance=self.prov_conformance))
        return stages


def _family_of(profile: Any) -> str:
    """The adapter family that ships ``profile`` (its ``build_profile`` module is ``agentprov.adapters.<family>.semantics``)."""
    return str(type(profile).__module__).split(".")[2]


_with_digest = _shared.with_digest  # H.8.2(1)


#: the keys an ``aer`` stage keeps across the runs that build one corpus (G4 refuses a run that changes one)
_AER_IDENTITY: Final = ("fn", "adapter", "adapter_code_sha256", "profile", "profile_sha256", "format", "engine",
                        "engine_code_sha256", "limits_sha256", "mode")


def merge_aer_rules(previous: Mapping[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """The ``aer`` stage a run records (ultrareview pipeline #3). Its ``rules`` are the catalogues the mapper starts
    with plus those the headers this run sealed declare, so a run that seals no unit declaring a namespace (a resume, a
    completed ``--limit`` or drained run) would drop it, and ``fn_digest`` would move with no AER changed. The corpus's
    stage keeps every namespace an earlier run of the same function recorded: the union, as a full re-map finds it."""
    if previous is None or any(previous.get(k) != current.get(k) for k in _AER_IDENTITY):
        return current
    rules = {**dict(previous.get("rules") or {}), **dict(current.get("rules") or {})}
    if rules == current.get("rules"):
        return current
    digests = {**dict(previous.get("rules_sha256") or {}), **dict(current.get("rules_sha256") or {})}
    body = {k: v for k, v in current.items() if k != "fn_digest"}
    body["rules"] = dict(sorted(rules.items()))
    body["rules_sha256"] = {ns: digests[ns] for ns in sorted(rules) if ns in digests}
    return _with_digest(body)


class _Listed:
    """A :class:`~agentprov.adapters.protocols.SourceTree` over an already walked candidate list (discovery runs once)."""

    def __init__(self, items: Sequence[CandidateArtefact]) -> None:
        self._items = list(items)

    def walk(self) -> Iterator[CandidateArtefact]:
        return iter(self._items)

    def open(self, label: str, *, max_bytes: int) -> bytes:  # pragma: no cover - readers only walk
        raise AgentProvError("discovery never opens a file", code="adapter.tree")


_lockfile_sha256 = _shared.lockfile_sha256


# ================================================================================================ entry point
class _PoolReporter:
    """The T1 pool's per-job reports (``WorkerPool.run(progress=...)``) as ``trace`` lines and ``worker`` spawn events
    (D-393). The pool reports each job as a ``unit_done``; passed on unchanged, those would be counted as units next to
    the executions. Metadata only (F1); O(1) per job; never raises."""

    def __init__(self, progress: Progress) -> None:
        self._progress = progress
        self._pids: set[int] = set()
        self._lock = threading.Lock()

    def emit(self, event: ProgressEvent) -> None:
        try:
            fields = dict(event.fields)
            pid = fields.get("worker_pid")
            if isinstance(pid, int) and not isinstance(pid, bool):
                with self._lock:
                    new = pid not in self._pids
                    self._pids.add(pid)
                if new:
                    self._progress.emit(ProgressEvent("worker", fields={"pid": pid, "tier": "t1", "phase": "spawn"}))
            self._progress.emit(ProgressEvent("trace", stage=f"t1.{fields.get('kind', 'job')}", unit=event.unit,
                                              status=event.status, duration_s=event.duration_s, codes=event.codes,
                                              fields=fields))
        except Exception:  # noqa: BLE001 - a failing display must never break the pool
            return

    def close(self) -> None:
        """Every worker seen is reported gone when the pools are done with this import."""
        with self._lock:
            pids, self._pids = sorted(self._pids), set()
        for pid in pids:
            self._progress.emit(ProgressEvent("worker", fields={"pid": pid, "tier": "t1", "phase": "exit"}))


def import_source(
    source_id: str,
    tree: Any,
    *,
    corpus: CorpusWriter | None,
    profile_id: str | None = None,
    filters: ImportFilters = ImportFilters(),  # noqa: B008 - immutable
    limit: int | None = None,
    dry_run: bool = False,
    mode: Literal["dev", "release"] = "dev",
    part: str | None = None,
    snapshot_id: str | None = None,
    corpus_id: str | None = None,
    until: str = "validation",
    prov_specs: Sequence[str] = (SPEC_ID,),
    workers: int = 0,
    in_process: bool = False,
    limits: IngestLimits | None = None,
    retry_failed: bool = False,
    progress: Progress = NULL_PROGRESS,
    pin_check: PinCheck | None = None,
    resume_index: IndexLog | None = None,
    batch_size: int = DEFAULT_BATCH,
    pin: Mapping[str, Any] | None = None,
    semantics: Sequence[str] | None = None,
    context_trees: Sequence[ContextTree] = (),
    pinned_objects: Sequence[PinnedObject] = (),
    context_skipped: Sequence[str] | None = None,
    limits_recorded_under: int | None = None,
    prov_conformance: bool = True,
    validation_cache: Any = None,
    sample: ImportSample | Mapping[str, Any] | None = None,
    drain: bool = False,
) -> ImportReport:
    """Import one snapshot of one source part into a working corpus (D.2.9; see the module docstring).

    ``corpus`` is an opened writer (its ``.partial`` tree and lock), or ``None`` with ``dry_run``: a dry run writes into a
    private temporary tree that is removed afterwards, so the working corpus is never touched (``resume_index`` then
    supplies the rows of an existing working corpus, read-only). ``until`` is a stage of N.2.2. ``semantics`` names the
    semantics profiles to annotate with (``<id>@<version>``); ``None`` takes the registry part's (C.14; HL H.2.5). Raises :class:`IdentityRefusedError` (exit 4) when the working corpus was begun
    with another identity or other function versions (G4), and lets ``KeyboardInterrupt`` through after flushing what
    was sealed (the corpus stays resumable).

    D.16.14 runner items (used only by a reader with ``auxiliary_for``, the DTap family): ``context_trees`` are second
    pinned trees whose files are context artefacts named per unit (R2), and ``pinned_objects`` are objects fetched by
    their own pin that stand for files of the primary tree (R3, the DTap LFS objects).

    ``validation_cache`` (D-550) is the tier-4 round-trip cache (:class:`agentprov.validate.cache.DiskCache`) that
    stores each completed round trip of the ``prov`` jobs, so a later validation of the same PROV is served from it.
    """
    if until not in UNTIL:
        raise ValueError(f"unknown stage {until!r}")
    if isinstance(sample, Mapping):  # a recorded selection.sample (a derive's re-map)
        sample = ImportSample(int(sample["n"]), str(sample.get("mode") or "first"),
                              None if sample.get("seed") is None else str(sample["seed"]))
    if sample is not None and limit is not None:
        raise ValueError("--sample and --limit are exclusive (D-529)")
    if any(spec != SPEC_ID for spec in prov_specs):
        raise ValueError("only agentprov-prov/0.1 is derived by the import pipeline in phase 6")
    if getattr(tree, "kind", None) == "local" and pin_check is None:
        raise UnpinnedInputError(
            "an --input tree needs --verify-against-pin: unverified files could carry only local origins, which the "
            "release-mode AER writer refuses (C.17 AER-V20); or read the pin itself with --fetch"
        )
    # D-530: a re-map's tree (``corpus.rawtree.StoredRawTree``) rebuilds the context trees and pinned objects it recorded
    if not context_trees:
        context_trees = [ContextTree(c.role, c.tree, None, pin=c.pin) for c in getattr(tree, "recorded_context", ())]
    if not pinned_objects:
        pinned_objects = [PinnedObject(o["label"], o["origin"], o["path"], o["sha256"], o["size"])
                          for o in getattr(tree, "recorded_pinned_objects", ())]
    if context_skipped is None:  # D-221: a re-map keeps the roles the recorded import skipped
        context_skipped = list(getattr(tree, "recorded_context_skipped", ()))
    profile = load_profile(profile_id) if profile_id else _primary_profile(source_id, part)
    part = part or (profile.parts[0] if profile.parts else "default")
    if semantics is None:
        semantics = _registry_semantics(source_id, part, profile.id)
    snapshot_id = snapshot_id or part
    limits = _profile_limits(limits or IngestLimits(), profile, recorded_under=limits_recorded_under)
    own: tempfile.TemporaryDirectory[str] | None = None
    writer = corpus
    if writer is None:
        if not dry_run:
            raise ValueError("a corpus writer is required unless dry_run")
        own = tempfile.TemporaryDirectory(prefix="agentprov-dry-")
        writer = CorpusWriter(Path(own.name) / "corpus", limits=limits, release=mode == "release")
        writer.open()
    pipeline: _Pipeline | None = None
    try:
        pipeline = _Pipeline(
            source_id, tree, writer, profile=profile, part=part, snapshot_id=snapshot_id,
            corpus_id=corpus_id or source_id, filters=filters, limit=limit, mode=mode, until=until, semantics=semantics,
            prov_specs=prov_specs, workers=workers, in_process=in_process, limits=limits, retry_failed=retry_failed,
            progress=progress, pin_check=pin_check, resume_index=resume_index, batch_size=batch_size, dry_run=dry_run,
            context_trees=context_trees, pinned_objects=pinned_objects, prov_conformance=prov_conformance,
            context_skipped=context_skipped,
            sample=sample, honour_drain=drain,
        )  # fmt: skip
        pipeline.validation_cache = validation_cache
        if not prov_conformance:
            pipeline.notices.append("--skip-prov-conformance: the W3C PROV conformance check (tier 4) was not run; the "
                                    "corpus is marked unvalidated until a full 'recompute --out NEW' (G2c-5)")
        if until == "sem" and not semantics:
            pipeline.notices.append("--until sem: no semantics profile applies to this part; the import stops after the AER stage")
        selections = pipeline.expand_selections()
        stages = pipeline.stage_definitions(selections)
        _check_recorded_selection(tree, pipeline)
        _check_sample(pipeline)
        if not dry_run:
            _check_identity(writer, pipeline, stages)
        started = time.monotonic()
        try:
            pipeline.run()
            pipeline.completed = not pipeline.drained  # D-394: a drained run stopped early; its snapshot is not whole
        except BaseException:
            pipeline.interrupted = True  # D-610: the finally below records the snapshot incomplete
            raise
        finally:
            if not dry_run:
                writer.flush()
                _write_documents(writer, pipeline, pipeline.stage_definitions(selections), tree, pin)
            _LOG.info("import finished in %.1f s", time.monotonic() - started)
        return _report(pipeline, profile, writer, limits, dry_run)
    finally:
        if pipeline is not None:
            pipeline.close()
        if own is not None:
            writer.close()
            own.cleanup()


def _profile_limits(limits: IngestLimits, profile: SourceProfile, *, recorded_under: int | None) -> IngestLimits:
    """The effective limits with the profile's ``[import] limits`` (D-323, RB-2). On an import the declared raise is
    applied. ``recorded_under`` is set by a ``recompute`` replaying ``corpus.json``: the profile version the limits were
    recorded under. Under the same version the recorded values must already equal the declaration (a mismatch is refused
    with a finding code, never resolved by a silent pick). Under another version the bump explains the change (D-31): the
    raisable fields start again from their defaults and the current profile's declaration applies."""
    from agentprov.ingest.profile_limits import PROFILE_RAISABLE, apply_profile_limits

    declared = profile.data.get("import", {}).get("limits") or {}
    defaults = IngestLimits()
    if recorded_under is not None and recorded_under != profile.version:
        limits = limits.replace(**{name: getattr(defaults, name) for name in PROFILE_RAISABLE})
    elif recorded_under is not None:
        for name in sorted(PROFILE_RAISABLE):
            if getattr(limits, name) != declared.get(name, getattr(defaults, name)):
                raise AgentProvError(f"{name}: corpus.json records {getattr(limits, name)}, the profile declares "
                                     f"{declared.get(name, 'the default')} (D-323)", code="corpus.derive.limits_mismatch",
                                     exit_code=4)
    if not declared:
        return limits
    try:
        return apply_profile_limits(limits, declared)
    except ValueError as exc:
        raise AgentProvError(f"the profile's [import] limits conflict with the effective limits: {exc}",
                             code="adapter.limits_conflict", exit_code=4) from None


def _primary_profile(source_id: str, part: str | None) -> SourceProfile:
    from agentprov.adapters.registry import get_source

    registration = get_source(source_id)
    for capability in registration.capabilities:
        if capability.profile and (part is None or capability.part == part):
            return load_profile(capability.profile)
    raise AgentProvError(f"no import profile for {source_id}", code="adapter.profile_missing")


def _registry_semantics(source_id: str, part: str, profile_id: str) -> tuple[str, ...]:
    """The semantics profiles the registry declares for ``source_id · part`` imported with ``profile_id`` (none if unknown)."""
    from agentprov.adapters.registry import get_source

    try:
        registration = get_source(source_id)
    except KeyError:
        return ()
    for capability in registration.capabilities:
        if capability.part == part and capability.profile == profile_id:
            return tuple(capability.semantics)
    return ()


def _same_per_unit_inputs(recorded: Mapping[str, Any], pipeline: _Pipeline) -> bool:
    """NF-25 (D-530): whether a resumed snapshot runs with the per-unit inputs it recorded: the same context roles, each
    role's pin and archive container where the snapshot recorded them (a manifest written before D-530 records neither),
    and the same pinned objects (label and sha256)."""
    entries = {str(c.get("role")): c for c in recorded.get("context") or () if isinstance(c, Mapping)}
    if set(entries) != set(pipeline.context_trees):
        return False
    for role, source in pipeline.context_trees.items():
        entry = entries[role]
        if isinstance(entry.get("pin"), Mapping) and jcs_bytes(dict(entry["pin"])) != jcs_bytes(dict(source.pin or {})):
            return False
        archive = entry.get("input")
        if isinstance(archive, Mapping) and str(archive.get("sha256", "")).removeprefix("sha256:") != str(
                getattr(source.tree, "sha256", "")):
            return False
    objects = {(str(o.get("label")), str(o.get("sha256", "")).removeprefix("sha256:"))
               for o in recorded.get("pinned_objects") or () if isinstance(o, Mapping)}
    return objects == {(o.label, o.sha256) for o in pipeline.overlay.values()}


def _check_identity(writer: CorpusWriter, pipeline: _Pipeline, stages: Sequence[Mapping[str, Any]]) -> None:
    """G4 (N.1.9): the same corpus id, source, mode and source profile, and the same function digests for every stage
    both runs define (a later ``--until`` may add stages). A snapshot the corpus does not hold yet is added (several
    snapshots per corpus, H.1.1(1) and H.7.2; D-202): it must come through the same source profile."""
    manifest = writer.read_document(writer.layout.manifest)
    if manifest is not None:
        source = (manifest.get("sources") or [{}])[0]
        if (manifest.get("corpus_id"), source.get("source_id"), manifest.get("mode")) != (
            pipeline.corpus_id, pipeline.source_id, "import"
        ):
            raise IdentityRefusedError(
                "the working corpus was begun with another corpus id, source or mode (G4); import into a new corpus "
                "directory"
            )
        # a snapshot added to a corpus comes through the profile its other snapshots came through (D-202). A snapshot
        # the manifest already lists is a resume or a re-map (recompute starts from the source's manifest, which names
        # the digest of its import): its mapping identity is checked per stage below and by H.8.4, never refused here
        listed = {s.get("snapshot_id") for s in source.get("snapshots", ()) if isinstance(s, Mapping)}
        recorded_snapshot = next((s for s in source.get("snapshots", ()) if isinstance(s, Mapping)
                                  and s.get("snapshot_id") == pipeline.snapshot_id), None)
        # NF-25 guards a resume; a re-map (a stored tree) rebuilds its inputs from the source and may leave out those
        # absent on purpose (PR-5), whose executions are reported unverified
        if (recorded_snapshot is not None and getattr(pipeline.tree, "kind", None) != "stored"
                and not _same_per_unit_inputs(recorded_snapshot, pipeline)):
            raise IdentityRefusedError(
                "the working corpus's snapshot was begun with other context trees or pinned objects (roles, pins, archive "
                "or LFS objects; G4, D-530): a resume would mix joined and unjoined units; import into a new corpus "
                "directory")
        profile = source.get("profile") or {}
        if pipeline.snapshot_id not in listed and (profile.get("id"), profile.get("sha256")) != (
            pipeline.profile.id, "sha256:" + pipeline.profile.sha256
        ):
            raise IdentityRefusedError(
                "the working corpus was begun with another source profile (G4); every snapshot of one corpus comes "
                "through the same profile"
            )
        # NF-36 (regen item 130, option (a)): a listed snapshot is resumed with the selection of eligible units it
        # recorded (filters and sample; none for a snapshot recorded whole) or with no selection and no limit, N.1.7's
        # completion path; another selection would mix two selections in one snapshot, and the corpus could then no
        # longer say which one its executions came from. --limit is not part of it: an incremental cap (N.1.7), so a
        # later run with another limit, or none, extends the snapshot (a pure --limit run on a whole snapshot too)
        current = _run_selection(pipeline)
        if pipeline.snapshot_id in listed and current is not None and selection_key(current) != selection_key(
                snapshot_selections(manifest).get(pipeline.snapshot_id)):
            raise IdentityRefusedError(
                f"snapshot {pipeline.snapshot_id} of the working corpus was imported with another selection (filters or "
                "--sample; N.1.7); resume it with the same selection (any --limit), or with none to complete it"
            )
    derivation = writer.read_document(writer.layout.derivation)
    if derivation is not None:
        recorded = stage_map(derivation)
        expansions = [d for key, d in recorded.items() if isinstance(key, tuple)]
        for stage in stages:
            if stage["stage"] == "expand":
                # D-380: one entry per expansion function; a recorded expansion of the same selection under another
                # function (engine code or limits) is a changed function (G4). A selection the corpus has not recorded
                # comes with an added snapshot (its profile was checked above) or a changed profile (the aer check)
                if stage_key(stage) not in recorded and any(
                        d.get("selection_sha256") == stage.get("selection_sha256") for d in expansions):
                    raise IdentityRefusedError("the working corpus was derived with another 'expand' function (version "
                                               "or code digest; G4)")
                continue
            before = recorded.get(stage["stage"])
            if before is not None and stage["stage"] != "aer" and before.get("fn_digest") != stage["fn_digest"]:
                raise IdentityRefusedError(
                    f"the working corpus was derived with another '{stage['stage']}' function (version or code digest; G4)"
                )
            if before is not None and stage["stage"] == "aer":
                keys = ("adapter", "adapter_code_sha256", "profile", "profile_sha256", "engine_code_sha256", "limits_sha256",
                        "mode")  # ultrareview pipeline #5: one corpus is never mapped in both modes
                if any(before.get(k) != stage.get(k) for k in keys):
                    raise IdentityRefusedError("the working corpus was mapped with another adapter, profile, engine or limits (G4)")


def _run_selection(pipeline: _Pipeline) -> dict[str, Any] | None:
    """This run's selection as its snapshot records it (NF-36), or ``None`` for an ordinary import (no filter, limit or
    sample: nothing is recorded, so its manifest is unchanged). The sample is its manifest record once drawn."""
    if not (pipeline.filters.active or pipeline.limit is not None or pipeline.sample is not None):
        return None
    sample = pipeline.sample_record if pipeline.sample_record is not None else None if pipeline.sample is None else {
        "n": pipeline.sample.n, "mode": pipeline.sample.mode, "seed": pipeline.sample.seed}
    return {"filters": pipeline.filters.to_json(), "limit": pipeline.limit, **({} if sample is None else {"sample": sample})}


def _snapshot_selection(pipeline: _Pipeline, tree: Any, prior: Mapping[str, Any] | None, *, listed: bool,
                        held: bool = True) -> dict[str, Any] | None:
    """The selection the snapshot records after this run (NF-36, N.1.7), ``None`` for a whole snapshot. ``prior`` is the
    one it recorded before (``None`` when whole or new); the identity check made this run's filters and sample equal to
    it unless the run has no selection and no limit.

    * A re-map (a stored raw tree) records the selection it replayed, verbatim.
    * A run with no selection and no limit is the completion path: once it ran to the end (at least to the AER stage)
      the snapshot is whole; an interrupted one keeps ``prior``.
    * Otherwise the snapshot keeps this run's filters and sample with a cumulative ``limit``, so a re-map (which starts
      from no executions) maps what the snapshot holds: ``--limit`` counts the units a run newly maps, so ``--limit 1``
      then ``--limit 2`` hold three units and record 3. A run that ran to the end and mapped fewer than its limit found
      nothing left (the snapshot is exhausted), and one with no limit that ran to the end mapped every selected unit:
      the limit is dropped, and a snapshot with no filter or sample left is whole. A snapshot recorded with no cap (whole,
      or a selection run to the end) is never narrowed by a later limit; an interrupted run adds what it indexed to a
      recorded cap (a unit it mapped but never indexed is mapped again by the resume), and so does an interrupted
      completion of a snapshot that records only a cap (one with a filter or sample keeps ``prior``: what it mapped
      lies outside that selection). ``--until raw`` maps nothing (the limit never trips): the recorded limit, or a new
      snapshot's given one, stays. ``held`` is false for a listed snapshot that recorded no execution yet: a cap it
      records then (an ``--until raw`` run's given limit, which a ``derive`` maps) is no unit held, so a mapping run
      counts from 0."""
    current = _run_selection(pipeline)
    if getattr(tree, "kind", None) == "stored":
        return current
    finished = pipeline.completed and pipeline.until != "raw"
    recorded = prior.get("limit") if prior is not None else None
    base: int | None = recorded if isinstance(recorded, int) and not isinstance(recorded, bool) else None
    if base is not None and not held and pipeline.until != "raw":
        base = 0
    if current is None:
        if finished or prior is None:
            return None
        bare = selection_key({k: v for k, v in prior.items() if k != "limit"}) == selection_key(None)
        return {**prior, "limit": base + pipeline.indexed} if bare and base is not None else dict(prior)
    if pipeline.until == "raw":
        limit = base if listed else pipeline.limit
    elif pipeline.limit is not None:
        exhausted = finished and pipeline.written < pipeline.limit
        limit = None if exhausted or (listed and base is None) else (base or 0) + pipeline.indexed
    else:
        limit = None if finished or base is None else base + pipeline.indexed
    if not (pipeline.filters.active or pipeline.sample is not None or limit is not None):
        return None
    return {**current, "limit": limit}


def _check_sample(pipeline: _Pipeline) -> None:
    """D-529: ``--sample-mode spread`` needs a reader that names a stratum (``sample_stratum``). NF-35 (regen item 129):
    refused here, next to the identity checks and before anything is stored or any document is (re)written, so a
    refused run leaves a fresh corpus without a manifest and an existing one byte for byte as it was (its recorded
    ``selection.sample`` included). Exit 5."""
    if pipeline.sample is not None and pipeline.sample.mode == "spread" and not callable(
            getattr(pipeline.reader, "sample_stratum", None)):
        raise SampleRefusedError(f"--sample-mode spread: the {pipeline.dialect} reader names no stratum (arm or variant) "
                                 "for its executions; use first or random")


#: D-610: what a corpus marked incomplete needs (the summary notice and the interrupted run's log line)
INCOMPLETE_HINT: Final = ("package, derive and recompute refuse the corpus until a run of this snapshot with the same "
                          "selection (or none) and no --limit short of the end runs to the end; re-run the same command")


def _stop_reason(pipeline: _Pipeline) -> str | None:
    """D-610: why this run stopped before it ran to the end (``None`` when it did)."""
    if pipeline.drained:
        return "drained"
    if pipeline.interrupted or not pipeline.completed:
        return "interrupted"
    return None


def _cap_describes(pipeline: _Pipeline, tree: Any, prior: Mapping[str, Any] | None,
                   recorded: Mapping[str, Any] | None) -> bool:
    """D-610: whether the selection a stopped run leaves recorded (``recorded``, NF-36) describes what the snapshot then
    holds, so a re-map maps the same units and no ``incomplete`` mark is needed: it carries a cumulative cap, the run was
    drained (an interrupt is always marked) with a clean tail (its last mapped candidate ended in a counted unit), it
    mapped (``--until raw`` stores part of the input, which no cap describes) from the source (a stopped re-map replays a
    cap it did not reach), and it is not a completion of a snapshot with a filter or sample (NF-36 keeps that selection
    although the run mapped units outside it)."""
    limit = (recorded or {}).get("limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or pipeline.until == "raw":
        return False
    # D-610 review (NF pass, 2026-10-21): only a drain stops at a batch boundary with every mapped unit indexed, and only
    # a clean tail is what a re-map under the cap reproduces. An interrupt can leave a mapped, stored, never-indexed batch
    if not pipeline.drained or not pipeline.clean_tail:
        return False
    if getattr(tree, "kind", None) == "stored":
        return False
    completion = _run_selection(pipeline) is None
    return not (completion and prior is not None and selection_key(
        {k: v for k, v in prior.items() if k != "limit"}) != selection_key(None))


def _ran_to_the_end(pipeline: _Pipeline) -> bool:
    """D-610: whether this run left nothing to map in its snapshot, so it clears an earlier run's ``incomplete`` mark:
    it ran to the end, mapped (``--until raw`` maps nothing) and had no ``--limit`` or found fewer units than it."""
    return pipeline.completed and pipeline.until != "raw" and (
        pipeline.limit is None or pipeline.written < pipeline.limit)


def _check_recorded_selection(tree: Any, pipeline: _Pipeline) -> None:
    """A re-map (``recompute``, ``verify --level rederive``) of an archive input re-expands it with the selection rebuilt
    from the current source profile the re-map loaded (``load_profile(profile_id)``; D-380 review). Its archive
    selection must be one the source recorded: otherwise the re-expansion would store another set of members than the
    import did. A profile change that keeps the selection is not refused here; the D-31 owner's guard (D-430) reports a
    profile that differs from the corpus's recorded version and refuses to write mixed-version output."""
    recorded = getattr(tree, "recorded_expand_selections", None)
    if not recorded or not pipeline.archive:
        return
    rebuilt = "sha256:" + pipeline.archive_selection().digest()
    if rebuilt not in recorded:
        shipped = "sha256:" + pipeline.profile.sha256
        before = getattr(tree, "recorded_profile_sha256", None)
        raise IdentityRefusedError(
            f"the archive input's expand selection rebuilt from the profile {pipeline.profile.id} ({shipped[:19]}) "
            f"is not the one the source recorded (its profile {str(before)[:19]}); re-import it instead of re-mapping")


def _write_documents(writer: CorpusWriter, pipeline: _Pipeline, stages: Sequence[Mapping[str, Any]], tree: Any,
                     pin: Mapping[str, Any] | None) -> None:
    previous = writer.read_document(writer.layout.derivation) or {}
    merged = stage_map(previous)
    recorded_aer = merged.get("aer")
    merged.update({stage_key(s): dict(s) for s in stages})
    if "aer" in merged:  # ultrareview pipeline #3: the corpus's namespaces, not only this run's
        merged["aer"] = merge_aer_rules(recorded_aer, merged["aer"])
    order = ("expand", "aer", "sem", "prov", "validation")
    derivation = {
        "format": "agentprov-derivation/0.1",
        "stages": in_order(merged, order),
        "lockfile_sha256": _lockfile_sha256(),
        "python": {"implementation": platform.python_implementation(), "version": platform.python_version()},
    }
    writer.write_document(writer.layout.derivation, derivation)
    writer.write_document(writer.layout.manifest, _manifest(writer, pipeline, tree, pin))


def _manifest(writer: CorpusWriter, pipeline: _Pipeline, tree: Any, pin: Mapping[str, Any] | None) -> dict[str, Any]:
    """The **working** manifest (unsealed; a phase-6 subset of H.2): identity, source and snapshot, adapter, formats,
    producer, effective limits, selection and the counts read back from the index and the register."""
    rows = writer.index.rows()
    register = writer.register.entries()
    advisory = writer.interpreter_advisory or (interpreter_advisory() if pipeline.container or pipeline.archive else None)
    not_imported = Counter(e.code for e in register if e.disposition == "not_imported")
    recorded = writer.read_document(writer.layout.manifest) or {}
    recorded_source = (recorded.get("sources") or [{}])[0]
    previous = [dict(s) for s in recorded_source.get("snapshots", ()) if isinstance(s, Mapping)]
    several = any(s.get("snapshot_id") != pipeline.snapshot_id for s in previous)
    mine = Counter(e.code for e in register if e.disposition == "not_imported"
                   and str(e.subject.get("snapshot_id", "")).split(":", 1)[0] == pipeline.snapshot_id)
    snapshot: dict[str, Any] = {
        "snapshot_id": pipeline.snapshot_id,
        "origin": tree.snapshot_origin() if hasattr(tree, "snapshot_origin") else None,
        "pin": _pin_record(pin, getattr(tree, "retrieved_at", None)),
        "verification": None if pipeline.pin_check is None else {
            "kind": pipeline.pin_check.kind, "verified": pipeline.pin_check.verified,
            "unverified": pipeline.pin_check.unverified},
        "counts": {"candidates": pipeline.counters["seen"], "executions": len(rows), "not_imported": sum(not_imported.values()),
                   "selection_excluded": pipeline.counters["excluded"]},
    }  # fmt: skip
    if several:  # D-202: each snapshot counts its own rows and register entries and names its part
        snapshot["counts"].update(executions=sum(1 for r in rows if pipeline.snapshot_id in r.snapshot_ids),
                                  not_imported=sum(mine.values()))
        snapshot["part"] = pipeline.part
    if pipeline.archive_object is not None:  # D-200: the stored archive input (only for archive inputs)
        snapshot["input"] = {"kind": "archive", "label": pipeline.archive_object["label"],
                             "sha256": "sha256:" + pipeline.archive_object["sha256"], "bytes": pipeline.archive_object["bytes"]}
        if "parts" in pipeline.archive_object:  # D-249: an archive input stored as byte parts (the container is its descriptor)
            snapshot["input"]["parts"] = pipeline.archive_object["parts"]
    if pipeline.context_trees:  # D.16.14 R2: the second pinned trees (only when given; other corpora are unchanged)
        snapshot["context"] = [{
            "role": role, "origin": source.tree.snapshot_origin() if hasattr(source.tree, "snapshot_origin") else None,
            "verification": _context_verification(source, sum(1 for key in pipeline.unit_context if key.startswith(role + ":"))),
            "stored": sum(1 for key in pipeline.unit_context if key.startswith(role + ":")),
            # D-530: what a re-map needs to rebuild the tree (only when known; older manifests are unchanged)
            **({"pin": dict(source.pin)} if source.pin else {}),
            **({"input": {"kind": "archive", **{k: v for k, v in pipeline.context_archives[role].items() if k != "sha256"},
                          "sha256": "sha256:" + pipeline.context_archives[role]["sha256"]}}
               if role in pipeline.context_archives else {}),
        } for role, source in sorted(pipeline.context_trees.items())]  # fmt: skip
    if pipeline.context_skipped:  # D-221 (NF-29): the context roles imported with --no-context
        snapshot["context_skipped"] = list(pipeline.context_skipped)
    if pipeline.overlay:  # D.16.14 R3: objects fetched by their own pin
        snapshot["pinned_objects"] = [{"label": o.label, "origin": o.origin.to_json(), "sha256": o.sha256, "bytes": o.size}
                                      for o in sorted(pipeline.overlay.values(), key=lambda o: o.label)]
    # NF-36 (regen item 130): each snapshot records the selection it was imported with (none when whole); see
    # _snapshot_selection for the limit it keeps
    selections = snapshot_selections(recorded)
    entry = next((s for s in previous if s.get("snapshot_id") == pipeline.snapshot_id), None)
    counted = (entry or {}).get("counts")
    held = not (isinstance(counted, Mapping) and counted.get("executions") == 0)
    current = _snapshot_selection(pipeline, tree, selections.get(pipeline.snapshot_id), listed=entry is not None,
                                  held=held)
    if current is not None:
        snapshot["selection"] = current
    # D-610: a run that stopped early marks its snapshot incomplete, unless the cap the snapshot now records describes
    # what it holds (NF-36's cumulative cap); one that ran to the end with nothing left to map clears an earlier mark (a
    # --limit run that did not exhaust the snapshot keeps it: the cap it records need not describe what the stopped
    # run held)
    stopped = _stop_reason(pipeline)
    prior_mark = (entry or {}).get("incomplete")
    if stopped is not None and (is_incomplete_record(prior_mark) or not _cap_describes(
            pipeline, tree, selections.get(pipeline.snapshot_id), current)):  # an interrupted run never is
        snapshot["incomplete"] = incomplete_record(stopped)
        if stopped == "interrupted":  # no report follows a raised run: the log names the mark
            _LOG.warning("snapshot %s is recorded incomplete (interrupted): %s", pipeline.snapshot_id, INCOMPLETE_HINT)
    elif stopped is None and isinstance(prior_mark, Mapping) and is_incomplete_record(prior_mark):
        if _ran_to_the_end(pipeline):
            pipeline.cleared_incomplete = str(prior_mark["reason"])
        else:
            snapshot["incomplete"] = dict(prior_mark)
    # D-202: the snapshots in the order they were imported (a re-map replays them in this order); a resumed snapshot
    # keeps its place
    recorded_parts = [str(p) for p in recorded_source.get("parts", ()) if isinstance(p, str)]
    snapshots: list[dict[str, Any]] = []
    for old in previous:
        if old.get("snapshot_id") == pipeline.snapshot_id:
            snapshots.append(snapshot)
        else:
            sid = old.get("snapshot_id")
            kept = {"selection": selections[sid]} if isinstance(sid, str) and sid in selections else {}
            snapshots.append({**old, "part": old.get("part") or (recorded_parts[0] if recorded_parts else pipeline.part),
                              **kept})
    if not any(s is snapshot for s in snapshots):
        snapshots.append(snapshot)
    parts = list(dict.fromkeys([*recorded_parts, pipeline.part]))
    pipeline.manifest_incomplete = {str(s["snapshot_id"]): str(s["incomplete"]["reason"]) for s in snapshots
                                    if is_incomplete_record(s.get("incomplete"))}
    pipeline.manifest_partial = any(is_import_selection(s.get("selection")) for s in snapshots) or bool(
        pipeline.manifest_incomplete)  # NF-36: while any snapshot records one (D-610: or is marked incomplete). The last run's limit is recorded only while it caps the snapshot: a run that exhausted it,
    # or a limit on a snapshot recorded uncapped, leaves no cap (package reads the top-level limit too)
    top_limit = pipeline.limit if current is not None and current.get("limit") is not None else None
    # ultrareview pipeline #4: the furthest stage the corpus holds, not the last run's --until (a later `--until raw`
    # run keeps every layer recorded before, and a re-map under a lowered `until` mapped nothing)
    order = ("raw", "aer", "sem", "prov", "validation")
    before = (recorded.get("selection") or {}).get("until") if isinstance(recorded.get("selection"), Mapping) else None
    until = max([pipeline.until, *([before] if before in order else [])], key=order.index)
    return {
        "format": CORPUS_FORMAT,
        "sealed": False,
        "state": "working",
        "corpus_id": pipeline.corpus_id,
        "mode": "import",
        "partial": pipeline.manifest_partial,
        "selection": {"filters": pipeline.filters.to_json(), "limit": top_limit, "until": until,
                      **({} if pipeline.sample_record is None else {"sample": pipeline.sample_record})},
        "sources": [{
            "source_id": pipeline.source_id, "parts": parts,
            "profile": {"id": pipeline.profile.id, "version": pipeline.profile.version, "sha256": "sha256:" + pipeline.profile.sha256},
            "snapshots": snapshots,
        }],  # fmt: skip
        "profiles": {
            "source": [{"id": pipeline.profile.id, "version": pipeline.profile.version, "sha256": "sha256:" + pipeline.profile.sha256}],
            "semantics": [{"id": i, "version": v} for i, v in (_split_ref(r) for r in pipeline.semantics)],
        },
        "adapters": [{"id": pipeline.mapper.mapper_id, "version": pipeline.mapper.version,
                      "code_sha256": "sha256:" + code_sha256([f"adapters/{pipeline.profile.family}"]),
                      "dialects": [pipeline.dialect]}],
        "formats": {"corpus": CORPUS_FORMAT, "index": "agentprov-index/0.1", "register": "agentprov-register/0.1",
                    "aer": AER_FORMAT_ID, "sem": "sem/0.1" if pipeline.semantics and pipeline._post_aer else None,
                    "capture": None},
        "producer": {
            "agentprov_version": __version__,
            "python": {"implementation": platform.python_implementation(), "version": platform.python_version()},
            "interpreter_advisory": None if advisory is None else advisory.to_json(),
            "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
            "isolation": "in-process" if pipeline.map_pool.in_process else "t1",
            "key_distributions": _versions("prov", "rdflib", "rfc8785", "pyyaml", "agentprov-capture"),
            "lockfile_sha256": _lockfile_sha256(),
        },
        "limits": {"effective": pipeline.limits.to_json(), "overrides": pipeline.limits.overrides()},
        "counts": {
            "executions": len(rows),
            "by_unit": dict(sorted(Counter(r.unit for r in rows).items())),
            "by_status": dict(sorted(Counter(r.status for r in rows).items())),
            "by_completeness": dict(sorted(Counter(r.completeness for r in rows).items())),
            "issues_by_code": dict(sorted(Counter(e.code for e in register).items())),
            "not_imported_by_code": dict(sorted(not_imported.items())),
            "members": writer.members.counts() if len(writer.members) else None,
        },
        "release": {"status": "dev", "created": None},
        # G2c-5 (D-432): only a corpus whose tier 4 was skipped carries the mark; every other one is unchanged
        **({} if pipeline.prov_conformance else {"validation": {"prov_conformance": "skipped"}}),
    }


_TREE_PIN_KEYS: Final = ("role", "kind", "repo", "commit", "tree", "tree_sha1", "listing_sha256", "doi")


def _pin_record(pin: Mapping[str, Any] | None, retrieved_at: str | None = None) -> dict[str, Any] | None:
    """The snapshot ``pin`` of the working manifest: a git or listing pin's identifying keys (unchanged since phase 6), or
    a download pin's full record (D-201: DOI, record id, version, file name, size and digests; a url pin's retrieval
    time, D-455)."""
    if pin is None:
        return None
    retrieved_at = retrieved_at or pin.get("retrieved_at")  # a re-map passes the recorded pin record (H.8.5)
    if pin.get("kind") == "url" and isinstance(retrieved_at, str):
        return dict(sorted({**Recipe.from_pin(pin).pin_record(), "retrieved_at": retrieved_at}.items()))
    if pin.get("kind") in DOWNLOAD_PIN_KINDS:
        return split_pin_record(pin) if is_split_pin(pin) else Recipe.from_pin(pin).pin_record()
    return {k: pin[k] for k in sorted(pin) if k in _TREE_PIN_KEYS}


def _split_ref(ref: str) -> tuple[str, int]:
    from agentprov.sem.profiles import parse_profile_ref

    return parse_profile_ref(ref)


def _report(pipeline: _Pipeline, profile: SourceProfile, writer: CorpusWriter, limits: IngestLimits, dry_run: bool) -> ImportReport:
    if pipeline.pin_check is not None and pipeline.pin_check.unverified:
        pipeline.notices.append(
            f"--verify-against-pin: {pipeline.pin_check.unverified} file(s) did not match the pin and were not imported "
            "(register raw.origin.blob_mismatch)"
        )
    reason = pipeline.manifest_incomplete.get(pipeline.snapshot_id)
    if reason is not None:
        pipeline.notices.append(f"snapshot {pipeline.snapshot_id} is recorded incomplete ({reason}; D-610): {INCOMPLETE_HINT}")
    elif pipeline.cleared_incomplete is not None:
        pipeline.notices.append(f"snapshot {pipeline.snapshot_id}: this run ran to the end and cleared the incomplete mark "
                                f"an earlier run left ({pipeline.cleared_incomplete}; D-610)")
    return ImportReport(
        counters={k: int(pipeline.counters[k]) for k in (*COUNTERS, *(("sampled_out",) if pipeline.sample else ()))},
        register=[e.to_json() for e in sorted(pipeline.run_register, key=lambda e: e.sort_key)],
        issues_by_code=dict(sorted(pipeline.issues.items())),
        limits=limits.to_json(),
        adapter=pipeline.mapper.mapper_id,
        adapter_version=pipeline.mapper.version,
        profile=profile.id,
        profile_version=profile.version,
        profile_sha256=profile.sha256,
        rules=dict(sorted(pipeline.catalogues.items())),
        failures=pipeline.failures,
        notices=pipeline.notices,
        partial=bool(pipeline.filters.active or pipeline.limit is not None or pipeline.sample is not None)
        if pipeline.manifest_partial is None else pipeline.manifest_partial,  # NF-36: the corpus's mark once written
        corpus_root=None if dry_run else str(writer.partial),
        incomplete=dict(sorted(pipeline.manifest_incomplete.items())),
    )

