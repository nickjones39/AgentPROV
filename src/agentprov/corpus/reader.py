"""``CorpusReader``: strict, read-only access to a sealed corpus, a working corpus or a ``DIR.partial`` tree (MN N.1.5).

Every phase-11 consumer of a corpus (``derive``/``recompute`` sources, ``verify``, ``stats``, ``inspect``, sealing) reads
through this class. It never writes, never takes a lock and never sweeps a temporary file.

**Resolution** (:func:`resolve_corpus`, the reader column of N.1.5). A path ending in ``.partial`` is first normalised to
``DIR``. Then ``DIR`` is read when its ``corpus.json`` says ``"sealed": true``; otherwise ``DIR.partial`` is read when it
exists (state ``working``); otherwise the corpus does not exist (exit 2). A ``DIR`` that exists but is not sealed and
has no ``DIR.partial`` is refused too: a working tree is always named ``<DIR>.partial`` (H.1.5(1)). A ``corpus.json``
that cannot be parsed is refused (fail closed), because whether the tree is sealed cannot be established.

**Strict reads.** A corpus may have been downloaded, so it is untrusted (G.5.7). Every file is opened by its
corpus-relative label through :func:`agentprov.ingest.paths.open_evidence` (no link followed, regular files only,
size-limited) after the label passed the H.1.2 grammar (:func:`agentprov.corpus.layout.classify_relpath`); JSON goes
through the strict loaders of :mod:`agentprov.ingest.loaders`; JSONL corpus files go through their own strict decoders
(index, register, origins, members). A path recorded in an index row is recomputed from the layout and compared before
it is opened (H.1.3(6)), and what is read is checked against the row: the AER execution digest, the SEM digest and the
PROV file sha256 (the D9 chain, H.5.1).

The index is streamed (:meth:`CorpusReader.iter_index`): one line at a time, each strictly parsed, canonical (its bytes
equal the row's JCS line), sorted and unique, with its recorded paths checked against the layout. Both working rows and
full rows decode (:class:`agentprov.corpus.index.IndexRow`).
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Final

from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.corpus.index import IndexError_, IndexRow
from agentprov.corpus.layout import (
    CHECKSUMS,
    DERIVATION,
    EXECUTIONS,
    MANIFEST,
    PARTIAL_SUFFIX,
    REGISTER,
    CorpusLayout,
    classify_relpath,
)
from agentprov.corpus.register import RegisterEntry, decode_register
from agentprov.errors import AgentProvError, IngestError
from agentprov.formats import require_supported
from agentprov.ingest.limits import prov_document_limits
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl, strict_json_loads
from agentprov.ingest.paths import STORED_OBJECT_LIMITS, open_evidence
from agentprov.raw.origins import OriginRow, decode_origins
from agentprov.raw.store import RawObjectStore
from agentprov.sem.reader import load_sem_bytes
from agentprov.sem.types import SemDocument

if TYPE_CHECKING:
    from agentprov.raw.members import MemberRow

__all__ = [
    "SEALED",
    "WORKING",
    "CorpusLocation",
    "CorpusNotFoundError",
    "CorpusReadError",
    "CorpusReader",
    "resolve_corpus",
]

SEALED: Final = "sealed"
WORKING: Final = "working"
CORPUS_FORMAT: Final = "agentprov-corpus/0.2"
#: Every corpus format this build reads (D-212): 0.1 corpora hold aer/0.1 records, 0.2 corpora aer/0.2.
CORPUS_FORMATS: Final = frozenset({"agentprov-corpus/0.1", "agentprov-corpus/0.2"})
DERIVATION_FORMAT: Final = "agentprov-derivation/0.1"
VALIDATION_SUMMARY_FORMAT: Final = "agentprov-validation-summary/0.1"


class CorpusNotFoundError(AgentProvError):
    """No sealed ``DIR`` and no ``DIR.partial`` (N.1.5: a reader exits 2, a usage error)."""

    code = "corpus.missing"
    exit_code = 2


class CorpusReadError(AgentProvError):
    """A corpus file is missing, unreadable, malformed or does not match what the index records (exit 1)."""

    code = "corpus.read.invalid"
    exit_code = 1


@dataclass(frozen=True, slots=True)
class CorpusLocation:
    """Where a ``--corpus DIR`` resolved to: the normalised ``DIR`` (``final``), the tree read (``root``) and its state."""

    final: Path
    root: Path
    state: str  # sealed | working
    used_partial: bool  # the tree read is ``DIR.partial``


def _is_real_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def json_document_limits(limits: IngestLimits) -> IngestLimits:
    """``limits`` with the file-size cap lowered to ``max_json_bytes`` (GR-35): a single JSON document is refused at open,
    before it is read, rather than read under the 2 GiB artefact cap and refused by the parser."""
    if limits.max_artefact_bytes <= limits.max_json_bytes:
        return limits
    return limits.replace(max_artefact_bytes=limits.max_json_bytes)


def _sealed_flag(directory: Path, limits: IngestLimits) -> bool | None:
    """``True``/``False`` from ``directory/corpus.json``; ``None`` when there is none. Unparseable: refused."""
    try:
        with open_evidence(directory, MANIFEST, json_document_limits(limits)) as stream:
            data = stream.read()
    except FileNotFoundError:
        return None
    except (IngestError, OSError) as exc:
        code = exc.code if isinstance(exc, IngestError) else type(exc).__name__
        raise CorpusReadError(f"corpus.json cannot be opened ({code})", code="corpus.read.manifest") from None
    try:
        document = strict_json_loads(data, limits)
    except IngestError as exc:
        raise CorpusReadError(f"corpus.json is not strict JSON ({exc.code})", code="corpus.read.manifest") from None
    return isinstance(document, dict) and document.get("sealed") is True


def resolve_corpus(path: str | os.PathLike[str], *, limits: IngestLimits | None = None) -> CorpusLocation:
    """Resolve ``--corpus DIR`` for a reader (N.1.5). See the module docstring."""
    limits = limits or IngestLimits()
    given = Path(os.fspath(path))
    final = given.with_name(given.name[: -len(PARTIAL_SUFFIX)]) if given.name.endswith(PARTIAL_SUFFIX) else given
    if not final.name:
        raise CorpusNotFoundError("a corpus path names a directory")
    partial = final.with_name(final.name + PARTIAL_SUFFIX)
    if _is_real_dir(final) and _sealed_flag(final, limits) is True:
        return CorpusLocation(final, final, SEALED, False)
    if _is_real_dir(partial):
        return CorpusLocation(final, partial, WORKING, True)
    if _is_real_dir(final):
        raise CorpusNotFoundError(
            "the directory is not a sealed corpus and has no .partial working tree beside it (N.1.5)",
            code="corpus.not_sealed")
    raise CorpusNotFoundError("neither a sealed corpus nor a .partial working tree exists at this path (N.1.5)")


class CorpusReader:
    """Read-only access to one corpus tree (see the module docstring). Construct it with :meth:`open`."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        state: str,
        used_partial: bool = False,
        limits: IngestLimits | None = None,
        shard_depth: int | None = None,
    ) -> None:
        if state not in (SEALED, WORKING):
            raise ValueError("state is sealed or working")
        if shard_depth not in (None, 1, 2):
            raise ValueError("shard depth is 1 or 2")
        self.root = Path(os.path.realpath(root))
        self.state = state
        self.used_partial = used_partial
        self.limits = limits or IngestLimits()
        self._depth = shard_depth
        self._manifest: dict[str, Any] | None = None
        self._manifest_read = False
        self._rows: dict[str, IndexRow] | None = None

    @classmethod
    def open(cls, path: str | os.PathLike[str], *, limits: IngestLimits | None = None) -> CorpusReader:
        """Resolve ``path`` by N.1.5 and open the tree it names. A sealed tree must have a supported manifest."""
        location = resolve_corpus(path, limits=limits)
        reader = cls(location.root, state=location.state, used_partial=location.used_partial, limits=limits)
        if reader.sealed and reader.manifest() is None:
            raise CorpusReadError("a sealed corpus has a corpus.json", code="corpus.read.manifest")
        return reader

    # ------------------------------------------------------------------------------------------ state
    @property
    def sealed(self) -> bool:
        return self.state == SEALED

    @property
    def shard_depth(self) -> int:
        """The execution shard depth (H.1.3(2)): the manifest's ``layout.shard_depth`` when it records one, else read from
        the first index row's AER path, else 1."""
        if self._depth is None:
            self._depth = self._detect_depth()
        return self._depth

    @property
    def layout(self) -> CorpusLayout:
        return CorpusLayout(self.root, shard_depth=self.shard_depth)

    def _detect_depth(self) -> int:
        manifest = self.manifest()
        layout = manifest.get("layout") if manifest else None
        if isinstance(layout, dict) and layout.get("shard_depth") in (1, 2):
            return int(layout["shard_depth"])
        with self._open_optional(EXECUTIONS) as stream:
            if stream is None:
                return 1
            line = stream.readline(self.limits.max_jsonl_line_bytes + 2)
        if not line:
            return 1
        try:
            row = IndexRow.from_json(strict_json_loads(line.rstrip(b"\n"), self.limits, record=True))
        except (IngestError, IndexError_) as exc:
            raise CorpusReadError(f"executions.jsonl line 1 is not an index row ({exc.code})", code="corpus.read.index") from None
        return 2 if row.aer_path.count("/") == 3 else 1

    # ------------------------------------------------------------------------------------------ raw file access
    def _check_label(self, label: str) -> None:
        if classify_relpath(label) is None:
            raise CorpusReadError("not a file of the H.1.2 corpus tree", code="corpus.read.path")

    def open_file(self, label: str, *, stored: bool = False, json_document: bool = False) -> IO[bytes]:
        """Open the corpus file ``label`` (grammar-checked; no link followed). ``stored`` lifts the artefact size cap
        for bytes that were admitted under their own limits when stored (raw objects); ``json_document`` lowers it to
        ``max_json_bytes`` (GR-35)."""
        self._check_label(label)
        limits = STORED_OBJECT_LIMITS if stored else json_document_limits(self.limits) if json_document else self.limits
        try:
            return open_evidence(self.root, label, limits, allow_hardlinks=True)
        except FileNotFoundError:
            raise CorpusReadError(f"{label}: missing", code="corpus.read.missing") from None
        except IngestError as exc:
            raise CorpusReadError(f"{label}: cannot be opened ({exc.code})", code="corpus.read.unreadable") from None
        except OSError as exc:
            raise CorpusReadError(f"{label}: cannot be opened ({type(exc).__name__})", code="corpus.read.unreadable") from None

    def _open_optional(self, label: str) -> _Optional:
        return _Optional(self, label)

    def read_bytes(self, label: str, *, stored: bool = False) -> bytes:
        with self.open_file(label, stored=stored) as stream:
            return stream.read()

    def exists(self, label: str) -> bool:
        """Whether the grammar-admitted file ``label`` exists as a regular file (``lstat``; no link followed)."""
        self._check_label(label)
        current = self.root
        for part in label.split("/"):
            current = current / part
            try:
                mode = os.lstat(current).st_mode
            except FileNotFoundError:
                return False
            except OSError:
                return True  # present but not examinable: the open that follows reports it
            if stat.S_ISLNK(mode):
                return True  # present; open_file refuses it (no link is followed)
        return stat.S_ISREG(mode)

    def read_document(self, label: str, *, required: bool = True) -> dict[str, Any] | None:
        """A single JSON document (``corpus.json``, ``derivation.json``, ``validation/summary.json``, ``WITHHELD.json``,
        ``raw/REFERENCES.json``) parsed strictly; ``None`` when absent and not ``required``."""
        if not required and not self.exists(label):
            return None
        with self.open_file(label, json_document=True) as stream:
            data = stream.read()
        try:
            value = strict_json_loads(data, self.limits)
        except IngestError as exc:
            raise CorpusReadError(f"{label}: not strict JSON ({exc.code})", code="corpus.read.json") from None
        if not isinstance(value, dict):
            raise CorpusReadError(f"{label}: not a JSON object", code="corpus.read.json")
        return value

    # ------------------------------------------------------------------------------------------ corpus documents
    def manifest(self) -> dict[str, Any] | None:
        """``corpus.json`` (format checked, fail closed), or ``None`` for a working tree without one."""
        if not self._manifest_read:
            document = self.read_document(MANIFEST, required=False)
            if document is not None:
                require_supported(document.get("format"), expected=CORPUS_FORMATS)
            self._manifest, self._manifest_read = document, True
        return self._manifest

    def derivation(self) -> dict[str, Any] | None:
        """``derivation.json`` (format checked), or ``None`` when absent."""
        document = self.read_document(DERIVATION, required=False)
        if document is not None:
            require_supported(document.get("format"), expected=DERIVATION_FORMAT)
        return document

    def checksums_bytes(self) -> bytes | None:
        """The bytes of ``checksums.sha256``, or ``None`` (a working tree has none)."""
        return self.read_bytes(CHECKSUMS) if self.exists(CHECKSUMS) else None

    # ------------------------------------------------------------------------------------------ index
    def iter_index(self) -> Iterator[IndexRow]:
        """Stream ``executions.jsonl``: strict, canonical, sorted, unique; recorded paths checked against the layout."""
        layout = self.layout
        previous: bytes | None = None
        with self.open_file(EXECUTIONS) as stream:
            number = 0
            while True:
                raw = stream.readline(self.limits.max_jsonl_line_bytes + 2)
                if not raw:
                    return
                number += 1
                if not raw.endswith(b"\n"):
                    raise CorpusReadError(f"executions.jsonl line {number}: no final LF or over the line limit",
                                          code="corpus.read.index")
                try:
                    value = strict_json_loads(raw[:-1], self.limits, record=True)
                    row = IndexRow.from_json(value, layout)
                except (IngestError, IndexError_) as exc:
                    raise CorpusReadError(f"executions.jsonl line {number}: not an index row ({exc.code})",
                                          code="corpus.read.index") from None
                if row.line() != raw:
                    raise CorpusReadError(f"executions.jsonl line {number}: not in canonical (JCS) form",
                                          code="corpus.read.index")
                key = row.ex.encode("ascii")
                if previous is not None and key <= previous:
                    raise CorpusReadError(f"executions.jsonl line {number}: not sorted by ex, or a duplicate",
                                          code="corpus.read.index")
                previous = key
                yield row

    def index(self) -> list[IndexRow]:
        """Every index row (read once and kept)."""
        if self._rows is None:
            self._rows = {row.ex: row for row in self.iter_index()}
        return list(self._rows.values())

    def row(self, ex: str) -> IndexRow | None:
        self.index()
        assert self._rows is not None
        return self._rows.get(ex)

    # ------------------------------------------------------------------------------------------ JSONL corpus files
    def register(self) -> list[RegisterEntry]:
        try:
            return decode_register(self.read_bytes(REGISTER), self.limits)
        except AgentProvError as exc:
            if isinstance(exc, CorpusReadError):
                raise
            raise CorpusReadError(f"register.jsonl is not valid ({exc.code})", code="corpus.read.register") from None

    def origins(self) -> list[OriginRow]:
        try:
            return decode_origins(self.read_bytes("raw/origins.jsonl"), self.limits)
        except AgentProvError as exc:
            if isinstance(exc, CorpusReadError):
                raise
            raise CorpusReadError(f"raw/origins.jsonl is not valid ({exc.code})", code="corpus.read.origins") from None

    def members(self) -> list[MemberRow]:
        try:
            from agentprov.raw.members import decode_members  # GR-34: lazily (it loads io.workers and host)

            return decode_members(self.read_bytes("raw/members.jsonl"), self.limits)
        except AgentProvError as exc:
            if isinstance(exc, CorpusReadError):
                raise
            raise CorpusReadError(f"raw/members.jsonl is not valid ({exc.code})", code="corpus.read.members") from None
        except TypeError:  # ultra raw-withhold #10: an array or object where a member row holds a string (fail closed)
            raise CorpusReadError("raw/members.jsonl is not valid (a field has the wrong type)",
                                  code="corpus.read.members") from None

    def validation_results(self) -> list[dict[str, Any]]:
        """``validation/results.jsonl`` rows (strict JSONL, sorted by ``ex``); ``[]`` when the stage never ran."""
        label = "validation/results.jsonl"
        if not self.exists(label):
            return []
        rows: list[dict[str, Any]] = []
        with self.open_file(label) as stream:
            try:
                for _, _, value in iter_jsonl(stream, self.limits):
                    if not isinstance(value, dict) or not isinstance(value.get("ex"), str):
                        raise CorpusReadError("a validation row is an object with an ex", code="corpus.read.validation")
                    rows.append(value)
            except IngestError as exc:
                raise CorpusReadError(f"{label} is not strict JSONL ({exc.code})", code="corpus.read.validation") from None
        keys = [r["ex"].encode("utf-8") for r in rows]
        if keys != sorted(set(keys)):
            raise CorpusReadError(f"{label} is not sorted by ex, or has a duplicate", code="corpus.read.validation")
        return rows

    def validation_summary(self) -> dict[str, Any] | None:
        document = self.read_document("validation/summary.json", required=False)
        if document is not None:
            require_supported(document.get("format"), expected=VALIDATION_SUMMARY_FORMAT)
        return document

    def raw_store(self) -> RawObjectStore:
        """The raw object store, opened read-only (nothing is created or swept)."""
        return RawObjectStore(self.root / "raw", limits=self.limits, create=False)

    # ------------------------------------------------------------------------------------------ per-execution files
    def aer_bytes(self, row: IndexRow) -> bytes:
        return self.read_bytes(self._recomputed(row.aer_path, self.layout.aer_relpath(row.ex)))

    def read_aer(self, row: IndexRow) -> AerDocument:
        """The execution's AER, fully verified (strict, canonical, seal), whose execution digest is ``digests.aer``."""
        try:
            document = load_aer_bytes(self.aer_bytes(row), verify=True)
        except AgentProvError as exc:
            if isinstance(exc, CorpusReadError):
                raise
            raise CorpusReadError(f"the AER of a row is not valid ({exc.code})", code="corpus.read.aer") from None
        if document.execution_digest != row.aer_digest or document.ex != row.ex:
            raise CorpusReadError("the AER's execution digest differs from the index (D9 chain)", code="corpus.read.digest")
        return document

    def read_sem(self, row: IndexRow, profile: str) -> SemDocument:
        """The execution's SEM document for ``profile`` (``<id>@<version>``), verified, whose digest is ``digests.sem``."""
        return self.read_sem_bytes(row, profile)[1]

    def read_sem_bytes(self, row: IndexRow, profile: str) -> tuple[bytes, SemDocument]:
        """:meth:`read_sem` with the exact bytes the document was verified from (handed on unchanged to a T1 job)."""
        stage = (row.sem or {}).get(profile)
        recorded = (row.sem_paths or {}).get(profile)
        if stage is None or stage.digest is None or recorded is None:
            raise CorpusReadError("the row has no SEM output for this profile", code="corpus.read.missing")
        data = self.read_bytes(self._recomputed(recorded, self.layout.sem_relpath(profile, row.ex)))
        try:
            document = load_sem_bytes(data, verify=True)
        except AgentProvError as exc:
            raise CorpusReadError(f"the SEM document of a row is not valid ({exc.code})", code="corpus.read.sem") from None
        if document.digest != stage.digest or document.ex != row.ex or document.aer_digest != row.aer_digest:
            raise CorpusReadError("the SEM digest or its AER digest differs from the index (D9 chain)", code="corpus.read.digest")
        return data, document

    def read_sem_all(self, row: IndexRow) -> dict[str, SemDocument]:
        """Every SEM document of the row with output, by profile reference."""
        return {profile: self.read_sem(row, profile) for profile in sorted(row.sem_paths or {})}

    def prov_bytes(self, row: IndexRow, spec: str) -> bytes:
        """The PROV-JSON bytes of ``spec``, whose sha256 is ``digests.prov.<spec>.json``."""
        stage = (row.prov or {}).get(spec)
        recorded = (row.prov_paths or {}).get(spec)
        if stage is None or stage.digest is None or recorded is None:
            raise CorpusReadError("the row has no PROV output for this spec", code="corpus.read.missing")
        data = self.read_bytes(self._recomputed(recorded, self.layout.prov_relpath(spec, row.ex)))
        if hashlib.sha256(data).hexdigest() != stage.digest:
            raise CorpusReadError("the PROV file's sha256 differs from the index (D9 chain)", code="corpus.read.digest")
        return data

    def read_prov(self, row: IndexRow, spec: str) -> Any:
        """The PROV-JSON document of ``spec``, parsed strictly."""
        try:
            return strict_json_loads(self.prov_bytes(row, spec), prov_document_limits(self.limits))  # D-935
        except IngestError as exc:
            raise CorpusReadError(f"a PROV document is not strict JSON ({exc.code})", code="corpus.read.prov") from None

    @staticmethod
    def _recomputed(recorded: str, expected: str) -> str:
        if recorded != expected:
            raise CorpusReadError("a recorded path differs from the layout's (H.1.3(6))", code="corpus.read.path")
        return expected


class _Optional:
    """``with reader._open_optional(label) as stream`` gives ``None`` for an absent file instead of raising."""

    def __init__(self, reader: CorpusReader, label: str) -> None:
        self.reader, self.label = reader, label
        self.stream: IO[bytes] | None = None

    def __enter__(self) -> IO[bytes] | None:
        if self.reader.exists(self.label):
            self.stream = self.reader.open_file(self.label)
        return self.stream

    def __exit__(self, *exc: object) -> None:
        if self.stream is not None:
            self.stream.close()
