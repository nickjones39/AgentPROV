"""Source locators and their resolution against the raw store (C.9).

A locator names a raw artefact listed in the header (``a``) or a content-addressed blob (``blob``) plus one
addressing form (C.9.1):

======================  ==========================================================================
form                    members
======================  ==========================================================================
whole artefact          ``a`` only: the artefact as a whole (resolves to its bytes)
JSON pointer            ``a``, ``p``
byte range              ``a``, ``bytes: [start, end_exclusive]``, ``p``?  (pointer relative to the slice)
line (0-based)          ``a``, ``line``, ``p``?  (JSONL artefacts)
origin pointer          ``a``, ``o``  (pointer into the artefact's ``origin`` record)
blob                    ``blob: "sha256:<hex>"``, ``p``?
======================  ==========================================================================

Resolution (C.9.2) is always against the **digest-checked stored object**: the bytes are fetched by SHA-256,
their digest and (for artefacts) byte length are verified, and only then parsed with the strict loader of
``agentprov.ingest.loaders``, profile ``python-json`` (RH-1, D-710): it parses every document exactly as the strict
profile does, except that a ``NaN``/``Infinity``/``-Infinity`` constant becomes ``{"$float": ...}`` (C.11.3) instead of
failing the whole document. So a locator into a source document that holds a non-finite number elsewhere (an Inspect
header with a ``NaN`` metric) resolves, and a locator pointing *at* a non-finite value resolves to that object, never
to a number. Archives are never opened here: an archive member is a raw object of its own. Failures are errors, never
warnings.

What the raw store must provide: the :class:`RawStore` protocol below.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final, Protocol, runtime_checkable

from agentprov.aer.canon import pointer_unescape
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.loaders import PROFILE_PYTHON_JSON, strict_json_loads
from agentprov.io.canonical import is_sha256_hex, sha256_hex, sha256_of_ref
from agentprov.aer.types import Json, Locator

__all__ = [
    "BlobDigestError",
    "BlobMissingError",
    "LocatorError",
    "LocatorResolver",
    "RawStore",
    "pointer_exists",
    "pointer_get",
    "resolve",
]


@runtime_checkable
class RawStore(Protocol):
    """The part of the content-addressed raw store (``agentprov.raw.store``) that AER needs.

    ``sha256`` arguments are 64 lower-case hex digits. The store addresses *all* raw bytes (artefacts, archive
    member objects, capture logs, blobs) by that digest; extensions and sharding are its business.
    """

    def has(self, sha256: str) -> bool:
        """Whether an object with this digest is stored."""
        ...

    def size(self, sha256: str) -> int:
        """Byte length of the stored object; ``KeyError`` when absent."""
        ...

    def read_bytes(self, sha256: str) -> bytes:
        """The stored bytes; ``KeyError`` when absent. The caller re-verifies the digest."""
        ...


class LocatorError(AgentProvError):
    """A locator does not resolve (``aer.locator.dangling``)."""

    code = "aer.locator.dangling"
    exit_code = 1


class BlobMissingError(LocatorError):
    """An artefact or blob is absent from the raw store (``aer.blob.missing``)."""

    code = "aer.blob.missing"


class BlobDigestError(LocatorError):
    """Stored bytes do not match the recorded digest or size (``aer.blob.digest``)."""

    code = "aer.blob.digest"


_MISSING: Final = object()
type Loads = Callable[[bytes], Any]


def _default_loads(data: bytes) -> Any:
    return strict_json_loads(data, profile=PROFILE_PYTHON_JSON)


def pointer_get(document: Any, pointer: str) -> Any:
    """RFC 6901 evaluation; ``KeyError`` when the pointer does not resolve (also for list index problems)."""
    if not isinstance(pointer, str):  # AER read back from a corpus is untrusted: a non-string never resolves
        raise KeyError("not a JSON Pointer")
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise KeyError("not a JSON Pointer")
    current = document
    for raw in pointer[1:].split("/"):
        token = pointer_unescape(raw)
        if isinstance(current, list):
            if not (token.isascii() and token.isdigit()) or (len(token) > 1 and token[0] == "0"):
                raise KeyError("bad array index")
            if len(token) > len(str(len(current))):  # longer than any valid index: no int() of 4,301+ digits
                raise KeyError("array index out of range")
            index = int(token)
            if index >= len(current):
                raise KeyError("array index out of range")
            current = current[index]
        elif isinstance(current, dict):
            if token not in current:
                raise KeyError("missing member")
            current = current[token]
        else:
            raise KeyError("cannot descend into a scalar")
    return current


def pointer_exists(document: Any, pointer: str) -> bool:
    try:
        pointer_get(document, pointer)
    except KeyError:
        return False
    return True


class LocatorResolver:
    """Resolves locators of one execution against a raw store, caching verified bytes and parsed documents.

    ``header`` is the ``execution`` record (its ``artifacts`` give digest, size and ``origin`` per ``a``).
    ``loads`` is the strict JSON parser (default: ``agentprov.ingest.loaders.strict_json_loads``, profile
    ``python-json``: non-finite constants as ``{"$float": ...}``; RH-1, D-710).
    """

    def __init__(
        self,
        header: Mapping[str, Any],
        store: RawStore,
        *,
        loads: Loads | None = None,
        max_cached_documents: int = 4,
    ) -> None:
        self._store = store
        self._loads = loads or _default_loads
        self._artefacts: dict[str, Mapping[str, Any]] = {}
        artefacts = header.get("artifacts")
        for entry in artefacts if isinstance(artefacts, list) else []:
            if isinstance(entry, Mapping) and isinstance(entry.get("id"), str):
                self._artefacts[entry["id"]] = entry
        self._bytes: dict[str, bytes] = {}
        self._docs: dict[str, Any] = {}
        self._max_docs = max_cached_documents

    # ---------------------------------------------------------------------------------------- bytes
    def _fetch(self, sha256: str, expected_size: int | None) -> bytes:
        if not is_sha256_hex(sha256):
            raise LocatorError("malformed digest")
        cached = self._bytes.get(sha256)
        if cached is None:
            try:
                data = self._store.read_bytes(sha256)
            except KeyError:
                raise BlobMissingError("object is not in the raw store") from None
            if sha256_hex(data) != sha256:
                raise BlobDigestError("stored bytes do not match their digest")
            if len(self._bytes) >= self._max_docs:
                self._bytes.pop(next(iter(self._bytes)))
            self._bytes[sha256] = cached = data
        if expected_size is not None and len(cached) != expected_size:
            raise BlobDigestError("stored byte length differs from the recorded size")
        return cached

    def artefact_bytes(self, artefact_id: str) -> bytes:
        """The digest- and size-checked bytes of header artefact ``artefact_id``."""
        entry = self._artefacts.get(artefact_id)
        if entry is None:
            raise LocatorError("locator names an artefact that the header does not list")
        digest, size = entry.get("sha256"), entry.get("bytes")
        if not isinstance(digest, str):
            raise LocatorError("artefact has no digest")
        return self._fetch(digest, size if isinstance(size, int) and not isinstance(size, bool) else None)

    def blob_bytes(self, blob_ref: str, expected_size: int | None = None) -> bytes:
        """The digest-checked bytes of ``blob_ref`` (``"sha256:<hex>"``)."""
        try:
            digest = sha256_of_ref(blob_ref)
        except ValueError:
            raise LocatorError("malformed blob reference") from None
        return self._fetch(digest, expected_size)

    # ---------------------------------------------------------------------------------------- parse
    def _parse(self, data: bytes) -> Any:
        try:
            return self._loads(data)
        except IngestError:
            raise LocatorError("object does not parse as strict JSON") from None

    def _document(self, key: str, data: bytes) -> Any:
        cached = self._docs.get(key, _MISSING)
        if cached is _MISSING:
            if len(self._docs) >= self._max_docs:
                self._docs.pop(next(iter(self._docs)))
            cached = self._docs[key] = self._parse(data)
        return cached

    # ---------------------------------------------------------------------------------------- resolve
    def resolve(self, loc: Mapping[str, Any]) -> Json | bytes:
        """Resolve ``loc``; ``LocatorError`` (or a subclass) on any failure."""
        keys = frozenset(loc)
        pointer = loc.get("p", "")
        if not isinstance(pointer, str):
            raise LocatorError("malformed pointer")
        try:
            if "blob" in loc:
                data = self.blob_bytes(str(loc["blob"]))
                if "p" not in loc:
                    return data
                return pointer_get(self._document("blob:" + str(loc["blob"]), data), pointer)
            artefact = loc.get("a")
            if not isinstance(artefact, str):
                raise LocatorError("locator names no artefact")
            if keys == {"a"}:
                return self.artefact_bytes(artefact)
            if "o" in loc:
                entry = self._artefacts.get(artefact)
                if entry is None:
                    raise LocatorError("locator names an artefact that the header does not list")
                return pointer_get(entry.get("origin"), str(loc["o"]))
            data = self.artefact_bytes(artefact)
            if "bytes" in loc:
                start, end = self._range(loc["bytes"], len(data))
                return pointer_get(self._parse(data[start:end]), pointer)
            if "line" in loc:
                return pointer_get(self._parse(self._line(data, loc["line"])), pointer)
            return pointer_get(self._document("a:" + artefact, data), pointer)
        except KeyError:
            raise LocatorError("pointer does not resolve") from None

    @staticmethod
    def _range(value: object, length: int) -> tuple[int, int]:
        ok = (
            isinstance(value, list)
            and len(value) == 2
            and all(isinstance(n, int) and not isinstance(n, bool) for n in value)
        )
        if not ok:
            raise LocatorError("malformed byte range")
        assert isinstance(value, list)
        start, end = int(value[0]), int(value[1])
        if not 0 <= start < end <= length:
            raise LocatorError("byte range outside the artefact")
        return start, end

    @staticmethod
    def _line(data: bytes, line: object) -> bytes:
        if not isinstance(line, int) or isinstance(line, bool) or line < 0:
            raise LocatorError("malformed line number")
        lines = data.split(b"\n")  # LF only: never splitlines()
        if line >= len(lines) or (line == len(lines) - 1 and lines[line] == b""):
            raise LocatorError("line is outside the artefact")
        return lines[line]


def resolve(
    loc: Locator | Mapping[str, Any],
    *,
    header: Mapping[str, Any],
    store: RawStore,
    loads: Loads | None = None,
) -> Json | bytes:
    """Resolve one locator (C.9.2); see :class:`LocatorResolver` for repeated use over one execution."""
    return LocatorResolver(header, store, loads=loads).resolve(loc)
