"""Origin records and ``raw/origins.jsonl`` (docs/architecture C.3.12, HL H.1.2/H.1.4/H.2.3, G.9.6, K.5.7; MN N.1.12(7)).

An :class:`Origin` says where one stored object came from. The kinds are ``git``, ``hf``, ``zenodo``, ``url``,
``corpus``, ``capture``, ``member``, ``split``, ``carved`` and ``local``. ``split`` (D-244, D-249) is the origin of a split descriptor:
the stored JCS list of the byte parts of one archive in their declared order (``raw.members.split_descriptor``). It
appears only in ``raw/origins.jsonl``: a descriptor is never a mapped artefact, so no AER cites it and the ``aer/0.1``
artefact ``Origin`` (which has no such kind) is unchanged. ``carved`` (D-218) is the origin of a carved blob: the exact
bytes of one string value of a stored object (``from``, its 64-hex digest), at a key locator (``loc``) under a transform
(``utf8`` or ``base64``; :mod:`agentprov.raw.carve`). Like ``split`` it appears only in ``raw/origins.jsonl``: an AER cites
a carved blob by ``$blob`` digest (``seal.blobs``), never as an artefact. At object level, which is what ``raw/origins.jsonl`` holds, the field
set is the AER artefact ``Origin`` of C.3.12 (the shape the ``aer/0.1`` schema and validator already enforce), because
one vocabulary serves AER ``artifacts[].origin`` and the mirror rows of ``raw/origins.jsonl`` (H.2.3). Snapshot-level
origins of ``corpus.json`` (HL H.2.3: ``subtree``, ``session_ids``, ``retrieved_at``) belong to the manifest and are not
produced here.

Pinning (D3, G.7.5, K.5.7(2)): a ``git`` commit and an ``hf`` revision must be 40 lower-case hex digits. A branch, a
tag, ``latest`` or an empty value raises ``raw.origin.unpinned`` (exit 3, "the command refuses"). A ``url`` origin carries
its retrieval date because the origin is mutable. A ``local`` origin is development only (the release validator rejects
it) and its path is written with the user's home path as ``<home>`` and the host name as ``<host>`` (G.9.6, N.1.12(7)).

``raw/origins.jsonl`` holds one JCS line per (object, origin): ``{"origin": {...}, "sha256": "sha256:<hex>"}``, UTF-8,
LF-terminated, sorted bytewise by ``(sha256, JCS(origin))`` and duplicate-free (HL H.1.4(1)); an empty set is a 0-byte
file. :class:`OriginLog` accumulates rows and writes the whole file atomically, so the file on disk is always sorted.
"""

from __future__ import annotations

import io
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, ClassVar, Final

from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl
from agentprov.io.atomic import atomic_write_bytes
from agentprov.io.canonical import is_sha256_hex, jcs_bytes

__all__ = [
    "CARVE_TRANSFORMS",
    "ORIGIN_KINDS",
    "Origin",
    "OriginError",
    "OriginLog",
    "OriginRow",
    "OriginUnpinnedError",
    "crc32_hex",
    "decode_origins",
    "encode_origins",
    "redact_personal",
]

ORIGIN_KINDS: Final = ("git", "hf", "zenodo", "url", "corpus", "capture", "member", "split", "carved", "local")
#: The closed set of carving transforms of a ``carved`` origin (D-218; :mod:`agentprov.raw.carve` applies them). Defined
#: here so that reading an origin never imports the carving code (D-222: it stays out of the expand stage's closure).
CARVE_TRANSFORMS: Final = ("utf8", "base64")
SPLIT_ARCHIVES: Final = ("zip",)
ZIP_METHODS: Final = (0, 8, 93)

_HEX40: Final = re.compile(r"[0-9a-f]{40}")
_HEX8: Final = re.compile(r"[0-9a-f]{8}")
_UUID7: Final = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_DATE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_MAX_STRING: Final = 4096


class OriginError(AgentProvError):
    """An origin record is malformed (``raw.origin.invalid``)."""

    code = "raw.origin.invalid"
    exit_code = 1


class OriginUnpinnedError(OriginError):
    """A ``git`` or ``hf`` origin names a branch, a tag or nothing instead of a 40-hex commit (``raw.origin.unpinned``).

    Exit 3: the command refuses (G.7.5).
    """

    code = "raw.origin.unpinned"
    exit_code = 3


def crc32_hex(value: int) -> str:
    """The 8 lower-case hex digits of a CRC-32 (C.3.12 ``member`` origin)."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("crc32 must be an integer in [0, 2**32)")
    return f"{value:08x}"


# --------------------------------------------------------------------------------------------------------------
# Personal-path redaction (G.9.6, N.1.12(7))
# --------------------------------------------------------------------------------------------------------------


def _default_host() -> str:
    """The machine's name without importing a network module: ``os.uname`` where it exists, else ``COMPUTERNAME``."""
    uname = getattr(os, "uname", None)
    if uname is not None:
        return str(uname().nodename)
    return os.environ.get("COMPUTERNAME", "")


def redact_personal(text: str, *, home: str | os.PathLike[str] | None = None, host: str | None = None) -> str:
    """Replace the user's home path with ``<home>`` and the host name with ``<host>`` (non-content surfaces only).

    ``home`` and ``host`` default to the running user's and machine's; they are parameters so that tests and
    ``recompute`` can pass fixed values. A home of ``/`` (or empty) and a host name shorter than three characters are
    never substituted, since that would damage ordinary text. Both the native and the POSIX spelling of the home path
    are replaced; the host name only where it is a whole token.
    """
    if home is None:
        try:
            home = Path.home()
        except (RuntimeError, KeyError):  # pragma: no cover - no resolvable home
            home = ""
    homes = {os.fspath(home), Path(os.fspath(home)).as_posix()} if os.fspath(home) else set()
    for candidate in sorted(homes, key=len, reverse=True):
        if len(candidate.rstrip("/\\")) > 1:
            text = text.replace(candidate.rstrip("/\\"), "<home>")
    if host is None:
        host = _default_host()
    if host and len(host) >= 3:
        text = re.sub(rf"(?<![\w.-]){re.escape(host)}(?![\w.-])", "<host>", text)
    return text


# --------------------------------------------------------------------------------------------------------------
# Origin
# --------------------------------------------------------------------------------------------------------------


def _text(value: object, field: str, *, https: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_STRING:
        raise OriginError(f"origin field {field!r} must be a non-empty string of at most {_MAX_STRING} characters")
    if any(ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F for c in value):
        raise OriginError(f"origin field {field!r} contains a control character")
    if https and not value.startswith("https://"):
        raise OriginError(f"origin field {field!r} must be an https URL")
    return value


def _pinned(value: object, field: str) -> str:
    if not isinstance(value, str) or _HEX40.fullmatch(value) is None:
        raise OriginUnpinnedError(f"origin field {field!r} must be a full 40-hex commit or revision, never a branch or tag")
    return value


def _hex40(value: object, field: str) -> str:
    if not isinstance(value, str) or _HEX40.fullmatch(value) is None:
        raise OriginError(f"origin field {field!r} must be 40 lower-case hex digits")
    return value


def _validate_date(value: object, field: str) -> str:
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        raise OriginError(f"origin field {field!r} must be an RFC 3339 date (YYYY-MM-DD)")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise OriginError(f"origin field {field!r} is not a calendar date") from None
    return value


def _int(value: object, field: str, *, low: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low or value > 2**53 - 1:
        raise OriginError(f"origin field {field!r} must be an integer in [{low}, 2**53)")
    return value


@dataclass(frozen=True, slots=True)
class Origin:
    """One origin record (object level, C.3.12). Build with the class methods or :meth:`from_json`; validated on creation."""

    kind: str
    data: Mapping[str, Any]

    _FIELDS: ClassVar[Mapping[str, tuple[frozenset[str], frozenset[str]]]] = {
        "git": (frozenset({"repo", "commit", "path", "blob_sha1"}), frozenset({"introduced_in_commit"})),
        "hf": (frozenset({"repo", "revision", "path"}), frozenset()),
        "zenodo": (frozenset({"doi", "file"}), frozenset()),
        "url": (frozenset({"url", "retrieved"}), frozenset()),
        "corpus": (frozenset({"corpus", "version", "path"}), frozenset({"producer_commit"})),
        "capture": (frozenset({"session"}), frozenset()),
        "member": (frozenset({"container", "label", "method", "crc32", "size"}), frozenset()),
        "split": (frozenset({"archive", "label", "parts"}), frozenset()),
        "carved": (frozenset({"from", "loc", "transform"}), frozenset()),
        "local": (frozenset({"path"}), frozenset()),
    }

    def __post_init__(self) -> None:
        if self.kind not in ORIGIN_KINDS:
            raise OriginError("unknown origin kind")
        required, optional = self._FIELDS[self.kind]
        keys = set(self.data)
        if not required <= keys or not keys <= required | optional:
            raise OriginError(f"{self.kind} origin has missing or unknown fields")
        clean = dict(self.data)
        check = getattr(self, f"_check_{self.kind}")
        check(clean)
        object.__setattr__(self, "data", clean)

    # -- per-kind validation (in place; raises OriginError) --
    @staticmethod
    def _check_git(d: dict[str, Any]) -> None:
        _text(d["repo"], "repo", https=True)
        _pinned(d["commit"], "commit")
        _text(d["path"], "path")
        _hex40(d["blob_sha1"], "blob_sha1")
        if "introduced_in_commit" in d:
            _hex40(d["introduced_in_commit"], "introduced_in_commit")

    @staticmethod
    def _check_hf(d: dict[str, Any]) -> None:
        _text(d["repo"], "repo")
        _pinned(d["revision"], "revision")
        _text(d["path"], "path")

    @staticmethod
    def _check_zenodo(d: dict[str, Any]) -> None:
        _text(d["doi"], "doi")
        _text(d["file"], "file")

    @staticmethod
    def _check_url(d: dict[str, Any]) -> None:
        _text(d["url"], "url", https=True)
        _validate_date(d["retrieved"], "retrieved")

    @staticmethod
    def _check_corpus(d: dict[str, Any]) -> None:
        _text(d["corpus"], "corpus")
        _text(d["version"], "version")
        _text(d["path"], "path")
        if "producer_commit" in d:
            _hex40(d["producer_commit"], "producer_commit")

    @staticmethod
    def _check_capture(d: dict[str, Any]) -> None:
        if not isinstance(d["session"], str) or _UUID7.fullmatch(d["session"]) is None:
            raise OriginError("origin field 'session' must be a lower-case UUIDv7")

    @staticmethod
    def _check_member(d: dict[str, Any]) -> None:
        if not isinstance(d["container"], str) or not is_sha256_hex(d["container"]):
            raise OriginError("origin field 'container' must be the 64-hex sha256 of the container object")
        _text(d["label"], "label")
        if isinstance(d["method"], bool) or d["method"] not in ZIP_METHODS:
            raise OriginError("origin field 'method' must be one of 0, 8, 93")
        if not isinstance(d["crc32"], str) or _HEX8.fullmatch(d["crc32"]) is None:
            raise OriginError("origin field 'crc32' must be 8 lower-case hex digits")
        _int(d["size"], "size")

    @staticmethod
    def _check_split(d: dict[str, Any]) -> None:
        if d["archive"] not in SPLIT_ARCHIVES:
            raise OriginError("origin field 'archive' must be one of: zip")
        _text(d["label"], "label")
        parts = d["parts"]
        if not isinstance(parts, list | tuple) or len(parts) < 2 or not all(isinstance(p, str) and is_sha256_hex(p) for p in parts):
            raise OriginError("origin field 'parts' must list at least two 64-hex part digests in order")
        d["parts"] = list(parts)

    @staticmethod
    def _check_carved(d: dict[str, Any]) -> None:
        if not isinstance(d["from"], str) or not is_sha256_hex(d["from"]):
            raise OriginError("origin field 'from' must be the 64-hex sha256 of the source object")
        loc = d["loc"]
        if not isinstance(loc, Mapping) or not set(loc) <= {"p", "line", "bytes"} or not isinstance(loc.get("p", ""), str) \
                or ("line" in loc and "bytes" in loc):
            raise OriginError("origin field 'loc' must be a key locator: p, with at most one of line and bytes")
        if "line" in loc:
            _int(loc["line"], "loc.line")
        if "bytes" in loc:
            span = loc["bytes"]
            if not isinstance(span, list | tuple) or len(span) != 2:
                raise OriginError("origin field 'loc.bytes' must be [start, end]")
            _int(span[0], "loc.bytes")
            _int(span[1], "loc.bytes")
        if d["transform"] not in CARVE_TRANSFORMS:
            raise OriginError(f"origin field 'transform' must be one of: {', '.join(CARVE_TRANSFORMS)}")
        d["loc"] = {k: (list(v) if k == "bytes" else v) for k, v in sorted(loc.items())}

    @staticmethod
    def _check_local(d: dict[str, Any]) -> None:
        _text(d["path"], "path")

    # -- constructors --
    @classmethod
    def git(
        cls, repo: str, commit: str, path: str, blob_sha1: str, *, introduced_in_commit: str | None = None
    ) -> Origin:
        data: dict[str, Any] = {"repo": repo, "commit": commit, "path": path, "blob_sha1": blob_sha1}
        if introduced_in_commit is not None:
            data["introduced_in_commit"] = introduced_in_commit
        return cls("git", data)

    @classmethod
    def hf(cls, repo: str, revision: str, path: str) -> Origin:
        return cls("hf", {"repo": repo, "revision": revision, "path": path})

    @classmethod
    def zenodo(cls, doi: str, file: str) -> Origin:
        return cls("zenodo", {"doi": doi, "file": file})

    @classmethod
    def url(cls, url: str, retrieved: str) -> Origin:
        return cls("url", {"url": url, "retrieved": retrieved})

    @classmethod
    def corpus(cls, corpus: str, version: str, path: str, *, producer_commit: str | None = None) -> Origin:
        data: dict[str, Any] = {"corpus": corpus, "version": version, "path": path}
        if producer_commit is not None:
            data["producer_commit"] = producer_commit
        return cls("corpus", data)

    @classmethod
    def capture(cls, session: str) -> Origin:
        return cls("capture", {"session": session})

    @classmethod
    def member(cls, container: str, label: str, method: int, crc32: int | str, size: int) -> Origin:
        """The origin of an archive member stored by ``expand``; ``crc32`` is an int or its 8 hex digits."""
        crc = crc32_hex(crc32) if isinstance(crc32, int) else crc32
        return cls("member", {"container": container, "label": label, "method": method, "crc32": crc, "size": size})

    @classmethod
    def split(cls, label: str, parts: Sequence[str], *, archive: str = "zip") -> Origin:
        """The origin of a split descriptor (D-249): the logical archive's label and its parts' digests, in order."""
        return cls("split", {"archive": archive, "label": label, "parts": list(parts)})

    @classmethod
    def carved(cls, source: str, loc: Mapping[str, Any], transform: str) -> Origin:
        """The origin of a carved blob (D-218): the source object's digest, the value's key locator and the transform."""
        return cls("carved", {"from": source, "loc": dict(loc), "transform": transform})

    @classmethod
    def local(
        cls, path: str | os.PathLike[str], *, home: str | os.PathLike[str] | None = None, host: str | None = None
    ) -> Origin:
        """A development-only origin; the home path is written ``<home>`` and the host name ``<host>`` (G.9.6)."""
        return cls("local", {"path": redact_personal(os.fspath(path), home=home, host=host)})

    @classmethod
    def from_json(cls, obj: object) -> Origin:
        """Validate a parsed origin object (``{"kind": ..., ...}``)."""
        if not isinstance(obj, Mapping) or not isinstance(obj.get("kind"), str):
            raise OriginError("an origin is an object with a 'kind'")
        return cls(obj["kind"], {k: v for k, v in obj.items() if k != "kind"})

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.data}

    def canonical(self) -> bytes:
        """The JCS bytes of the origin: the second half of the row sort key."""
        return jcs_bytes(self.to_json())


# --------------------------------------------------------------------------------------------------------------
# raw/origins.jsonl
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OriginRow:
    """One line of ``raw/origins.jsonl``: an object digest (64 hex) and one origin."""

    sha256: str
    origin: Origin

    def __post_init__(self) -> None:
        if not isinstance(self.sha256, str) or not is_sha256_hex(self.sha256):
            raise OriginError("an origin row needs a 64-hex sha256")

    @property
    def sort_key(self) -> tuple[str, bytes]:
        return (self.sha256, self.origin.canonical())

    def to_json(self) -> dict[str, Any]:
        return {"origin": self.origin.to_json(), "sha256": "sha256:" + self.sha256}

    def line(self) -> bytes:
        return jcs_bytes(self.to_json()) + b"\n"

    @classmethod
    def from_json(cls, obj: object) -> OriginRow:
        if not isinstance(obj, Mapping) or set(obj) != {"origin", "sha256"}:
            raise OriginError("an origin row has exactly 'origin' and 'sha256'")
        ref = obj["sha256"]
        if not isinstance(ref, str) or not ref.startswith("sha256:") or not is_sha256_hex(ref[7:]):
            raise OriginError("an origin row's sha256 is 'sha256:<64 hex>'")
        return cls(ref[7:], Origin.from_json(obj["origin"]))


def encode_origins(rows: Iterable[OriginRow]) -> bytes:
    """The bytes of ``raw/origins.jsonl``: de-duplicated, sorted by ``(sha256, JCS(origin))``, LF-terminated."""
    unique = {row.sort_key: row for row in rows}
    return b"".join(unique[key].line() for key in sorted(unique))


def decode_origins(data: bytes, limits: IngestLimits | None = None) -> list[OriginRow]:
    """Parse ``raw/origins.jsonl`` strictly (fails closed on any framing finding, and on unsorted or repeated rows)."""
    rows: list[OriginRow] = []
    try:
        for _, _, value in iter_jsonl(io.BytesIO(data), limits):
            rows.append(OriginRow.from_json(value))
    except IngestError as exc:
        raise OriginError(f"raw/origins.jsonl is not strict JSONL ({exc.code})") from None
    keys = [r.sort_key for r in rows]
    if keys != sorted(set(keys)):
        raise OriginError("raw/origins.jsonl is not sorted and duplicate-free", code="raw.origin.unsorted")
    return rows


class OriginLog:
    """Accumulates origin rows for one raw store and writes ``raw/origins.jsonl`` atomically (whole file, sorted).

    :meth:`add` is idempotent. An origin is mandatory for every stored object (K.5.7(1)): the corpus writer refuses an
    object without one.
    """

    def __init__(self, rows: list[OriginRow] | None = None) -> None:
        self._rows: dict[tuple[str, bytes], OriginRow] = {}
        self._counts: dict[str, int] = {}  # sha256 -> lines; keeps count() O(1) for corpora of tens of thousands
        for row in rows or []:
            if row.sort_key not in self._rows:
                self._counts[row.sha256] = self._counts.get(row.sha256, 0) + 1
            self._rows[row.sort_key] = row

    def add(self, sha256: str, origin: Origin) -> bool:
        """Record one (object, origin); ``True`` when the row is new."""
        row = OriginRow(sha256, origin)
        if row.sort_key in self._rows:
            return False
        self._rows[row.sort_key] = row
        self._counts[row.sha256] = self._counts.get(row.sha256, 0) + 1
        return True

    def rows(self) -> list[OriginRow]:
        return [self._rows[k] for k in sorted(self._rows)]

    def origins_of(self, sha256: str) -> list[Origin]:
        return [r.origin for r in self.rows() if r.sha256 == sha256]

    def count(self, sha256: str) -> int:
        """The number of lines for ``sha256`` (index column ``n_origins``, HL H.3.1)."""
        return self._counts.get(sha256, 0)

    def __len__(self) -> int:
        return len(self._rows)

    def serialise(self) -> bytes:
        return encode_origins(list(self._rows.values()))

    def write(self, path: str | os.PathLike[str]) -> None:
        atomic_write_bytes(Path(path), self.serialise())

    @classmethod
    def load(cls, path: str | os.PathLike[str], limits: IngestLimits | None = None) -> OriginLog:
        return cls(decode_origins(Path(path).read_bytes(), limits))
