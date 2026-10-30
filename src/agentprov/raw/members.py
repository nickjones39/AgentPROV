"""The versioned ``expand`` stage and ``raw/members.jsonl`` (docs/architecture AD-12, G.3.1 step 3, G.3.5, G.4.5, G.4.6,
HL H.1.4, H.8.2, K.5.7(3); MN M.1.2).

``expand`` turns a stored archive container into member objects, without extracting anything: the container's bytes are
read by digest inside a T1 worker (``job_expand``, closed-table kind ``expand``), every member passes the G.3.5 gate, and
only the members selected by the profile's patterns are streamed back in ``DATA`` frames. T0 stores each selected member
as its own raw object (a derived object of the container, origin kind ``member``) and records one row per member in
``raw/members.jsonl``:

``{"code": "ingest.…", "container": "sha256:…", "crc32": "8 hex", "disposition": "selected|not_selected|rejected",
"fn_digest": "sha256:…", "label": "<NFC name>"|null, "method": 8, "sha256": "sha256:…"|null, "size": 123}``

``code`` is present only on a rejected member; ``sha256`` is ``null`` when no object was stored. The file is sorted by
container digest and keeps each container's member order (H.1.4(1)). A member that matches the profile's *nested*
patterns is expanded in turn, up to ``max_archive_depth``, with the selection declared for its level.

Function identity (H.8.2). ``fn_digest`` is ``sha256(JCS(stage definition without fn_digest))`` of
``{"stage": "expand", "fn": "expand", "engine": "agentprov@<version>", "engine_code_sha256", "limits_sha256",
"selection_sha256"}``. ``selection_sha256`` (the digest of the sorted include and nested patterns of that level) is
added to the H.8.2 example because the rows of one container differ with the selection: without it two different
expansions of the same bytes would carry the same identity.

Labels are labels. Nothing here builds a filesystem path from a member name.

**Archives stored as byte parts (D-243, D-244).** A zip cut into byte parts is one container whose identity is a **split
descriptor**: the JCS bytes of ``{"archive": "zip", "format": "agentprov-split/0.1", "parts": [{"sha256":
"sha256:<hex>", "size": n}, ...]}`` in the declared order (:func:`split_descriptor`), stored as a raw object
(:func:`store_split_descriptor`). Its digest names the concatenation exactly (order and every part's bytes), so member
rows and ``member`` origins carry it as ``container``. :class:`ContainerSpec` with ``parts`` checks, by computation, that
its digest is the descriptor of those parts; the job receives the descriptor and the parts as inputs, re-reads the
descriptor strictly, requires the inputs to be exactly its parts in its order, and opens the parts by digest. The
descriptor's own origin record is the caller's (a new origin kind, routed; D-244).

Layering: L1. The corpus layer (``agentprov.corpus``) turns the :class:`ExpandEvent` records into register entries; this
module never imports it.
"""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import glob as _glob
import io
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Final

from agentprov.envinfo import InterpreterAdvisory, require_patched_for_archive
from agentprov.errors import INGEST_CODES, AgentProvError, IngestError
from agentprov.ingest.archives import OpenedTar, OpenedZip, ZipMember, iter_zip_members, open_archive, open_split_zip
from agentprov.ingest.limits import NESTED_RAISE_FIELDS, IngestLimits, NestedRaises, depth_limit, nested_raises
from agentprov.ingest.loaders import iter_jsonl, strict_json_loads
from agentprov.ingest.names import has_colon
from agentprov.io.atomic import atomic_write_bytes
from agentprov.io.canonical import is_sha256_hex, jcs_bytes, sha256_hex
from agentprov.io.workers import (
    Job,
    JobContext,
    MemberOutput,
    WorkerError,
    WorkerLimitError,
    WorkerPool,
)
from agentprov.raw.origins import Origin, crc32_hex
from agentprov.raw.store import (
    ObjectMismatchError,
    PutResult,
    RawObjectStore,
    RawStoreError,
    ext_for_label,
    limit_field_for,
    violation_detail,
)

__all__ = [
    "EXPAND_MODULES",
    "JOB_KIND",
    "ContainerSpec",
    "ExpandEvent",
    "ExpandOutcome",
    "ExpandedContainer",
    "MemberLog",
    "MemberRow",
    "MembersConflictError",
    "MembersError",
    "NESTED_ENTRY_KEYS",
    "Nested",
    "SPLIT_FORMAT",
    "Selection",
    "decode_members",
    "decode_split_descriptor",
    "encode_members",
    "engine_code_sha256",
    "expand_containers",
    "expand_fn_digest",
    "job_expand",
    "nested_selection",
    "split_descriptor",
    "store_split_descriptor",
]

JOB_KIND: Final = "expand"
DISPOSITIONS: Final = ("selected", "not_selected", "rejected")
_MAX_SAFE_INT: Final = 2**53 - 1  # HL H.1.4(3): corpus-layer integers stay within +-2**53
_HEX8: Final = re.compile(r"[0-9a-f]{8}")
_MAX_PATTERN: Final = 256
#: At most this many ``*`` in one path segment of a selection pattern (a whole ``**`` segment does not count; F-08).
_MAX_STARS: Final = 2
_ENGINE_NAME: Final = "agentprov"
#: The member separator of chain labels and register subjects (``corpus.rawtree.MEMBER_SEPARATOR``; D-384).
_SEPARATOR: Final = "!/"
#: Chunk size of a streamed member (D-383): one ``DATA`` frame at most.
_STREAM_CHUNK: Final = 1024 * 1024

#: The ``agentprov`` modules whose source defines the ``expand`` function (H.8.2 ``engine_code_sha256``), as paths
#: relative to the package directory: this module and its transitive import closure (lazy imports included), which
#: ``tests/unit/test_stage_scopes.py`` recomputes (D-451, bug pass BF-39). Kept here rather than in
#: :mod:`agentprov.stage_scopes` so that the pin file is in no closure.
EXPAND_MODULES: Final = (
    "envinfo.py",
    "errors.py",
    "host.py",
    "ingest/archives.py",
    "ingest/limits.py",
    "ingest/loaders.py",
    "ingest/names.py",
    "ingest/parts.py",
    "ingest/paths.py",
    "ingest/streams.py",
    "io/atomic.py",
    "io/canonical.py",
    "io/workers.py",
    "progress.py",
    "raw/members.py",
    "raw/origins.py",
    "raw/store.py",
    "versions.py",
)


class MembersError(AgentProvError):
    """A ``members.jsonl`` row or an ``expand`` request is malformed (``raw.members.invalid``)."""

    code = "raw.members.invalid"
    exit_code = 1


class MembersConflictError(MembersError):
    """One container was expanded twice with different results or different selections (``raw.members.conflict``)."""

    code = "raw.members.conflict"


# --------------------------------------------------------------------------------------------------------------
# Selection (profile include and nested-archive patterns)
# --------------------------------------------------------------------------------------------------------------


def _check_pattern(pattern: object, name: str) -> None:
    if (
        not isinstance(pattern, str)
        or not pattern
        or len(pattern) > _MAX_PATTERN
        or "\\" in pattern
        or any(ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F for c in pattern)
    ):
        raise MembersError(f"invalid selection pattern in {name!r}")
    if any(seg.count("*") > _MAX_STARS for seg in pattern.split("/") if seg != "**"):
        # F-08 / D-52: '*a*a*a*b*' backtracks super-linearly in glob.translate's regex (80 s on 200 chars)
        raise MembersError(f"a segment of a selection pattern in {name!r} has more than {_MAX_STARS} '*'")


@dataclass(frozen=True, slots=True)
class Selection:
    """The profile patterns of one archive level (G.3.1 step 3).

    ``include`` selects members to store; ``nested`` selects members that are stored **and** expanded in turn. Patterns
    are ``glob`` patterns over the NFC label with ``/`` separators (``**`` crosses directories, leading dots match);
    every other member is recorded ``not_selected`` and never decompressed (R-40). A segment may hold at most two
    ``*`` (a whole ``**`` segment aside): more backtracks super-linearly on hostile labels (F-08, D-59).

    ``children`` (D-382, a source profile's ``[import] nested``) are declared nested archives: a member that matches a
    child's pattern is stored and expanded with **that child's** selection, under its raises (:class:`Nested`); it is
    nested, never mapped. A child's pattern takes precedence over ``include``. ``nested`` (one selection per level) and
    ``children`` (a selection per declared archive) are not combined in one selection.
    """

    include: tuple[str, ...] = ()
    nested: tuple[str, ...] = ()
    children: tuple[Nested, ...] = ()

    def __post_init__(self) -> None:
        for name in ("include", "nested"):
            patterns = tuple(sorted(set(getattr(self, name))))
            for pattern in patterns:
                _check_pattern(pattern, name)
            object.__setattr__(self, name, patterns)
        children = tuple(sorted(self.children, key=lambda c: c.pattern))
        if not all(isinstance(c, Nested) for c in children):
            raise MembersError("selection children are Nested declarations")
        if len({c.pattern for c in children}) != len(children):
            raise MembersError("two nested declarations of one selection share a pattern")
        if children and self.nested:
            raise MembersError("a selection has per-level nested patterns or declared children, not both")
        object.__setattr__(self, "children", children)

    def digest(self) -> str:
        """``selection_sha256``: the JCS digest of the sorted patterns (``children`` only when there are any, so the
        digest of every selection without declared nested archives is unchanged)."""
        body: dict[str, Any] = {"include": list(self.include), "nested": list(self.nested)}
        if self.children:
            body["children"] = [c.to_json() for c in self.children]
        return sha256_hex(jcs_bytes(body))

    def child_for(self, label: str) -> Nested | None:
        """The first declared nested archive (pattern order) whose pattern matches ``label``."""
        return next((c for c in self.children if c.matches(label)), None)

    def nodes(self) -> list[Selection]:
        """This selection and every descendant's, depth first in pattern order, each once (by digest)."""
        out: dict[str, Selection] = {}
        stack = [self]
        while stack:
            node = stack.pop(0)
            out.setdefault(node.digest(), node)
            stack[0:0] = [c.selection for c in node.children]
        return list(out.values())


@dataclass(frozen=True, slots=True)
class Nested:
    """One declared nested archive (D-382): members of the parent that match ``pattern`` are archives, stored as member
    objects and expanded with ``selection`` under ``raises`` (size and ratio for the member's own gate; ``max_depth`` for
    every archive opened at or below it)."""

    pattern: str
    selection: Selection
    raises: NestedRaises = field(default_factory=NestedRaises)

    def __post_init__(self) -> None:
        _check_pattern(self.pattern, "nested")
        if not isinstance(self.selection, Selection) or not isinstance(self.raises, NestedRaises):
            raise MembersError("a nested declaration has a selection and raises")

    def to_json(self) -> dict[str, Any]:
        return {"pattern": self.pattern, "raises": self.raises.to_json(), "selection": "sha256:" + self.selection.digest()}

    def matches(self, label: str) -> bool:
        return _matcher(self.pattern).match(label) is not None


#: The keys of one ``[[import.nested]]`` entry besides its raises (D-382).
NESTED_ENTRY_KEYS: Final = frozenset({"id", "pattern", "under", "note"})


def nested_selection(include: Sequence[str], entries: Sequence[Mapping[str, Any]],
                     defaults: IngestLimits | None = None) -> Selection:  # fmt: skip
    """The expand selection of an archive input with declared nested archives (``[import] nested``, D-382).

    ``include`` is the archive selection (the profile's include, blob and context globs); every declared archive is
    expanded with the same ``include`` plus the entries declared ``under`` it. Each entry is ``{id, pattern, under?,
    note?}`` plus raises (:func:`agentprov.ingest.limits.nested_raises`). Refused (``MembersError``): an unknown key, a
    missing or duplicate ``id``, an ``under`` that names no entry, a cycle, an invalid pattern, two entries with one
    pattern under one parent, a raise below the global value or above its ceiling, and an entry whose own level
    (2 under the input, one more per ``under``) exceeds the depth allowance of its chain.
    """
    by_id: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise MembersError("an [import] nested entry is a table")
        unknown = sorted(set(entry) - NESTED_ENTRY_KEYS - NESTED_RAISE_FIELDS)
        if unknown:
            raise MembersError(f"unknown [import] nested key(s) {unknown}")
        ident, pattern, under = entry.get("id"), entry.get("pattern"), entry.get("under", "")
        if not isinstance(ident, str) or not ident or ident in by_id:
            raise MembersError("every [import] nested entry has a unique non-empty id")
        if not isinstance(pattern, str) or not isinstance(under, str):
            raise MembersError(f"[import] nested {ident!r}: pattern and under are strings")
        if not isinstance(entry.get("note", ""), str):
            raise MembersError(f"[import] nested {ident!r}: note is a string")
        _check_pattern(pattern, "nested")
        by_id[ident] = entry
    for ident, entry in by_id.items():
        seen, cursor = {ident}, str(entry.get("under", ""))
        while cursor:
            if cursor not in by_id:
                raise MembersError(f"[import] nested {ident!r}: under names no entry")
            if cursor in seen:
                raise MembersError(f"[import] nested {ident!r}: the under chain is a cycle")
            seen.add(cursor)
            cursor = str(by_id[cursor].get("under", ""))
    base = defaults or IngestLimits()

    def build(parent: str, level: int, allowance: int) -> Selection:
        children = []
        for ident in sorted(i for i, e in by_id.items() if str(e.get("under", "")) == parent):
            entry = by_id[ident]
            try:
                raises = nested_raises(entry, base)
            except ValueError as exc:
                raise MembersError(f"[import] nested {ident!r}: {exc}") from None
            own = max(allowance, raises.max_depth or 0)
            if level + 1 > own:
                raise MembersError(f"[import] nested {ident!r}: its archives open at level {level + 1}, above the depth "
                                   f"allowance {own} of its chain (declare max_depth)")  # fmt: skip
            children.append(Nested(str(entry["pattern"]), build(ident, level + 1, own), raises))
        return Selection(include=tuple(include), children=tuple(children))

    return build("", 1, base.max_archive_depth)


@functools.lru_cache(maxsize=1024)
def _matcher(pattern: str) -> re.Pattern[str]:
    compiled = _compile((pattern,))
    assert compiled is not None
    return compiled


def _compile(patterns: Iterable[str]) -> re.Pattern[str] | None:
    parts = [_glob.translate(p, recursive=True, include_hidden=True, seps="/") for p in patterns]
    if not parts:
        return None
    return re.compile("|".join(f"(?:{p})" for p in parts), re.DOTALL)


# --------------------------------------------------------------------------------------------------------------
# Split descriptors (D-243, D-244)
# --------------------------------------------------------------------------------------------------------------

SPLIT_FORMAT: Final = "agentprov-split/0.1"
#: A descriptor is at most this long (64 parts take about 6 KiB).
_MAX_DESCRIPTOR_BYTES: Final = 64 * 1024


def _check_parts(parts: Sequence[tuple[str, int]]) -> tuple[tuple[str, int], ...]:
    out = []
    for item in parts:
        if not isinstance(item, tuple | list) or len(item) != 2:
            raise MembersError("a split part is (sha256, size)")
        sha, size = item
        if not isinstance(sha, str) or not is_sha256_hex(sha):
            raise MembersError("a split part digest is 64 lower-case hex digits")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= _MAX_SAFE_INT:
            raise MembersError("a split part size is a positive integer")
        out.append((sha, size))
    if len(out) < 2:
        raise MembersError("a split archive has at least two parts")
    return tuple(out)


def split_descriptor(parts: Sequence[tuple[str, int]]) -> bytes:
    """The JCS bytes of the split descriptor of ``parts`` (``(sha256 hex, size)`` in the declared order)."""
    checked = _check_parts(parts)
    return jcs_bytes({"archive": "zip", "format": SPLIT_FORMAT,
                      "parts": [{"sha256": _ref(sha), "size": size} for sha, size in checked]})  # fmt: skip


def decode_split_descriptor(data: bytes, limits: IngestLimits | None = None) -> tuple[tuple[str, int], ...]:
    """Parse a stored split descriptor strictly; it must be exactly the canonical bytes of its parts."""
    if len(data) > _MAX_DESCRIPTOR_BYTES:
        raise MembersError("a split descriptor is too long")
    try:
        obj = strict_json_loads(data, limits, record=True)
    except IngestError as exc:
        raise MembersError(f"a split descriptor is not strict JSON ({exc.code})") from None
    if not isinstance(obj, Mapping) or set(obj) != {"archive", "format", "parts"} or obj["format"] != SPLIT_FORMAT \
            or obj["archive"] != "zip" or not isinstance(obj["parts"], list):  # fmt: skip
        raise MembersError("not a split descriptor")
    parts = []
    for part in obj["parts"]:
        if not isinstance(part, Mapping) or set(part) != {"sha256", "size"}:
            raise MembersError("a split descriptor part is {sha256, size}")
        parts.append((_unref(part["sha256"], "part sha256"), part["size"]))
    checked = _check_parts(parts)
    if split_descriptor(checked) != data:
        raise MembersError("a split descriptor is not in canonical form")
    return checked


def store_split_descriptor(store: RawObjectStore, parts: Sequence[tuple[str, int]]) -> str:
    """Store the descriptor of ``parts`` (idempotent) and return its digest; the caller records its origin (D-244)."""
    return store.put(split_descriptor(parts), ext="json").sha256


# --------------------------------------------------------------------------------------------------------------
# Function identity (H.8.2)
# --------------------------------------------------------------------------------------------------------------


@functools.cache
def engine_code_sha256() -> str:
    """The sha256 of the JCS array ``[[relpath, sha256(file)], ...]`` over :data:`EXPAND_MODULES`, sorted by relpath.

    Line endings are normalised (CRLF to LF) before hashing, so a Windows checkout with ``core.autocrlf`` gives the
    digest of the repository's LF files.
    """
    root = Path(__file__).resolve().parents[1]
    entries = []
    for relpath in sorted(EXPAND_MODULES):
        data = (root / relpath).read_bytes().replace(b"\r\n", b"\n")
        entries.append([relpath, sha256_hex(data)])
    return sha256_hex(jcs_bytes(entries))


def _engine_version() -> str:
    try:
        return metadata.version("agentprov")
    except metadata.PackageNotFoundError:  # pragma: no cover - an uninstalled source tree
        from agentprov.versions import __version__

        return __version__


def expand_fn_definition(limits: IngestLimits, selection: Selection) -> dict[str, Any]:
    """The ``expand`` stage definition of ``derivation.json`` (H.8.2), without ``fn_digest``."""
    return {
        "stage": "expand",
        "fn": "expand",
        "engine": f"{_ENGINE_NAME}@{_engine_version()}",
        "engine_code_sha256": "sha256:" + engine_code_sha256(),
        "limits_sha256": "sha256:" + sha256_hex(jcs_bytes(limits.to_json())),
        "selection_sha256": "sha256:" + selection.digest(),
    }


def expand_fn_digest(limits: IngestLimits, selection: Selection) -> str:
    """``fn_digest`` as 64 hex digits: ``sha256(JCS(definition without fn_digest))`` (H.8.2(1))."""
    return sha256_hex(jcs_bytes(expand_fn_definition(limits, selection)))


# --------------------------------------------------------------------------------------------------------------
# raw/members.jsonl
# --------------------------------------------------------------------------------------------------------------


def _ref(digest: str) -> str:
    return "sha256:" + digest


def _unref(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or not is_sha256_hex(value[7:]):
        raise MembersError(f"{what} must be 'sha256:<64 hex>'")
    return value[7:]


@dataclass(frozen=True, slots=True)
class MemberRow:
    """One member of one expanded container (AD-12). Digests are held as bare hex and written as ``sha256:<hex>``."""

    container: str
    fn_digest: str
    label: str | None
    method: int
    crc32: str
    size: int | None
    sha256: str | None
    disposition: str
    code: str | None = None

    def __post_init__(self) -> None:
        # Every closed-vocabulary test checks for a string first: a row read back is untrusted JSON, and an array or
        # object there must be MembersError, never a TypeError from a frozenset (regen item 157)
        if not is_sha256_hex(self.container) or not is_sha256_hex(self.fn_digest):
            raise MembersError("container and fn_digest are 64-hex digests")
        if not isinstance(self.disposition, str) or self.disposition not in DISPOSITIONS:
            raise MembersError("unknown member disposition")
        if self.label is not None and (not isinstance(self.label, str) or not self.label):
            raise MembersError("a member label is a non-empty string or null")
        if isinstance(self.method, bool) or not isinstance(self.method, int) or not 0 <= self.method <= 0xFFFF:
            raise MembersError("method is a 16-bit integer")
        if not isinstance(self.crc32, str) or _HEX8.fullmatch(self.crc32) is None:
            raise MembersError("crc32 is 8 lower-case hex digits")
        if self.size is not None and (
            isinstance(self.size, bool) or not isinstance(self.size, int) or not 0 <= self.size <= _MAX_SAFE_INT
        ):
            raise MembersError("size is an integer in [0, 2**53) or null")
        if self.sha256 is not None and not is_sha256_hex(self.sha256):
            raise MembersError("sha256 is a 64-hex digest or null")
        if self.disposition == "selected":
            if self.sha256 is None or self.label is None or self.code is not None or self.size is None:
                raise MembersError("a selected member has a label, a size, an object and no code")
        elif self.sha256 is not None:
            raise MembersError("only a selected member has an object")
        if self.disposition == "rejected":
            if not isinstance(self.code, str) or self.code not in INGEST_CODES:
                raise MembersError("a rejected member carries a closed ingest.* code")
        elif self.code is not None:
            raise MembersError("only a rejected member carries a code")

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "container": _ref(self.container),
            "crc32": self.crc32,
            "disposition": self.disposition,
            "fn_digest": _ref(self.fn_digest),
            "label": self.label,
            "method": self.method,
            "sha256": None if self.sha256 is None else _ref(self.sha256),
            "size": self.size,
        }
        if self.code is not None:
            out["code"] = self.code
        return out

    def line(self) -> bytes:
        return jcs_bytes(self.to_json()) + b"\n"

    @classmethod
    def from_json(cls, obj: object) -> MemberRow:
        base = {"container", "crc32", "disposition", "fn_digest", "label", "method", "sha256", "size"}
        if not isinstance(obj, Mapping) or not (set(obj) == base or set(obj) == base | {"code"}):
            raise MembersError("a members row has exactly the documented fields")
        sha = obj["sha256"]
        return cls(
            container=_unref(obj["container"], "container"),
            fn_digest=_unref(obj["fn_digest"], "fn_digest"),
            label=obj["label"],
            method=obj["method"],
            crc32=obj["crc32"],
            size=obj["size"],
            sha256=None if sha is None else _unref(sha, "sha256"),
            disposition=obj["disposition"],
            code=obj.get("code"),
        )

    def origin(self) -> Origin:
        """The ``member`` origin of this row's object (selected rows only)."""
        if self.disposition != "selected" or self.label is None or self.size is None:
            raise MembersError("only a selected member has an origin")
        return Origin.member(self.container, self.label, self.method, self.crc32, self.size)


def encode_members(rows: Iterable[MemberRow]) -> bytes:
    """The bytes of ``raw/members.jsonl``: containers sorted by digest, each container's member order kept."""
    groups: dict[str, list[MemberRow]] = {}
    for row in rows:
        groups.setdefault(row.container, []).append(row)
    return b"".join(row.line() for container in sorted(groups) for row in groups[container])


def decode_members(data: bytes, limits: IngestLimits | None = None) -> list[MemberRow]:
    """Parse ``raw/members.jsonl`` strictly; containers must be contiguous and sorted by digest."""
    rows: list[MemberRow] = []
    try:
        for _, _, value in iter_jsonl(io.BytesIO(data), limits):
            rows.append(MemberRow.from_json(value))
    except IngestError as exc:
        raise MembersError(f"raw/members.jsonl is not strict JSONL ({exc.code})") from None
    seen: list[str] = []
    for row in rows:
        if not seen or seen[-1] != row.container:
            seen.append(row.container)
    if seen != sorted(set(seen)):
        raise MembersError("raw/members.jsonl is not grouped and sorted by container", code="raw.members.unsorted")
    return rows


class MemberLog:
    """The members of every expanded container of one corpus, written as ``raw/members.jsonl`` (atomic, whole file)."""

    def __init__(self, rows: Iterable[MemberRow] = ()) -> None:
        self._groups: dict[str, list[MemberRow]] = {}
        for row in rows:
            self._groups.setdefault(row.container, []).append(row)

    def add_container(self, container: str, rows: Sequence[MemberRow]) -> bool:
        """Record one container's expansion; ``True`` if new, ``False`` if an identical expansion is already recorded.

        A different expansion of the same container (other rows or another ``fn_digest``) raises
        :class:`MembersConflictError`: a corpus holds one expansion record per container.
        """
        if any(r.container != container for r in rows):
            raise MembersError("rows of another container")
        existing = self._groups.get(container)
        if existing is not None:
            if existing != list(rows):
                raise MembersConflictError("container already expanded with a different result")
            return False
        self._groups[container] = list(rows)
        return True

    def rows(self) -> list[MemberRow]:
        return [row for container in sorted(self._groups) for row in self._groups[container]]

    def containers(self) -> list[str]:
        return sorted(self._groups)

    def __len__(self) -> int:
        return sum(len(g) for g in self._groups.values())

    def serialise(self) -> bytes:
        return encode_members(self.rows())

    def write(self, path: str | Path) -> None:
        atomic_write_bytes(path, self.serialise())

    @classmethod
    def load(cls, path: str | Path, limits: IngestLimits | None = None) -> MemberLog:
        return cls(decode_members(Path(path).read_bytes(), limits))

    def counts(self) -> dict[str, int]:
        """``{containers, selected, not_selected}`` for ``corpus.json`` (HL H.2.9 ``members``); rejected rows are neither."""
        rows = self.rows()
        return {
            "containers": len(self._groups),
            "selected": sum(1 for r in rows if r.disposition == "selected"),
            "not_selected": sum(1 for r in rows if r.disposition == "not_selected"),
        }


# --------------------------------------------------------------------------------------------------------------
# The worker side: kind ``expand``
# --------------------------------------------------------------------------------------------------------------


def _ijson(value: int) -> int | None:
    """An integer the corpus layer can carry, or ``None``: a zip64 header may declare any 64-bit size."""
    return value if 0 <= value <= _MAX_SAFE_INT else None


def _gate_limit_field(code: str, file_size: int, limits: IngestLimits) -> str | None:
    if code == "ingest.archive.size":
        return "max_member_bytes" if file_size > limits.max_member_bytes else "max_total_bytes"
    return {
        "ingest.archive.ratio": "max_ratio",
        "ingest.archive.method": "zip_methods",
        "ingest.name.invalid": "max_name_bytes",
    }.get(code)


def job_expand(ctx: JobContext) -> dict[str, Any]:
    """T1 job ``expand`` (G.3.1 step 3, G.3.5): gate every member, stream the selected ones back.

    Params: ``limits`` (an :class:`IngestLimits` record), ``include`` and ``nested`` (patterns), ``depth`` (the level of
    this container, from 1) and ``release``; ``split`` (``true``) for an archive stored as byte parts; ``children`` (the
    declared nested archives of this level, D-382: ``[{pattern, max_member_bytes?, max_ratio?}]``) and ``max_depth`` (the
    depth allowance of this container's chain), both only when declared. Input 0 is the
    container, opened by digest and re-hashed in chunks (G.4.5) and then read through the open handle, so the container is
    never held in memory as a whole (HL.R7, D-58). For a split archive (D-243), input 0 is its split descriptor, read
    strictly, and inputs 1..n must be exactly the descriptor's parts in its order; each is opened by digest and the zip is
    read through the parts (:func:`agentprov.ingest.archives.open_split_zip`).

    Frames, in central-directory order: ``{"finding": …}`` for container-level findings, then per member either
    ``{"row": …}`` (not selected or rejected) or a ``$member`` header followed by ``DATA`` frames (selected), then, if any
    accepted label contains ``:``, one info finding ``ingest.name.colon`` with their count (D-91; labels, never paths). A member
    is read completely, CRC-checked, before its header is written, so a defect found while reading rejects that member
    only (G.3.5(5)) and no partial bytes are ever sent. A structural defect raises: the job fails with its ``ingest.*``
    code and rejects the whole archive.

    **Streamed members (D-383).** A selected member that matches a declared nested archive and is larger than the global
    ``max_member_bytes`` cannot be held whole: its header carries ``"streamed": true``, its ``DATA`` frames follow as the
    member is decompressed, and one closing frame says how it ended: ``{"end": {"index"}}`` once ``zipfile`` has checked
    the CRC-32 and the byte count, or ``{"abort": {"index", "code", "reason"}}`` on a member-level defect. The parent
    publishes the bytes only after an ``end`` and its own size and CRC-32 check, and discards them otherwise.

    **Chain labels (D-384).** A member label that contains the member separator ``!/`` cannot take part in a chain of
    archive labels: in a container at level 2 or below, and for a member that matches a declared nested archive, it is
    rejected ``ingest.name.invalid``. Level-1 members of a container without declared nested archives are unchanged.
    """
    params = ctx.params
    limits = IngestLimits(**params["limits"])
    include = _compile(params["include"])
    nested = _compile(params["nested"])
    depth = int(params["depth"])
    release = bool(params["release"])
    children = [(_matcher(str(c["pattern"])), NestedRaises(**{k: v for k, v in c.items() if k != "pattern"}))
                for c in params.get("children", ())]  # fmt: skip
    max_depth = params.get("max_depth")

    def child_raises(label: str) -> NestedRaises | None:
        return next((raises for matcher, raises in children if matcher.match(label) is not None), None)

    def is_nested(label: str) -> bool:
        return (nested is not None and nested.match(label) is not None) or child_raises(label) is not None

    def selected(label: str) -> bool:
        return (include is not None and include.match(label) is not None) or is_nested(label)

    def chain_label_refused(label: str | None) -> bool:
        return label is not None and _SEPARATOR in label and (depth >= 2 or child_raises(label) is not None)

    counters = {"members": 0, "selected": 0, "not_selected": 0, "rejected": 0}
    colons = 0
    with contextlib.ExitStack() as stack:
        archive: OpenedZip | OpenedTar
        if params.get("split"):
            parts = decode_split_descriptor(ctx.read_input(0), limits)
            inputs = [item["sha256"] for item in ctx.inputs[1:]]
            if inputs != [sha for sha, _size in parts]:
                raise MembersError("the job inputs are not the split descriptor's parts in order", code="expand.protocol")
            handles = [stack.enter_context(ctx.open_input(i)) for i in range(1, len(ctx.inputs))]
            archive = open_split_zip(handles, [size for _sha, size in parts], limits, release=release, depth=depth,
                                     max_depth=max_depth)  # fmt: skip
        else:
            source = stack.enter_context(ctx.open_input(0))
            archive = open_archive(source, limits, release=release, depth=depth, max_depth=max_depth)
        stack.callback(archive.close)
        for finding in archive.findings:
            ctx.emit(
                {
                    "finding": {
                        "code": finding.code,
                        "severity": finding.severity,
                        "offset": finding.offset,
                        "detail": finding.detail,
                    }
                }
            )
        for member in iter_zip_members(archive, selected, limits, child_raises if children else None):
            counters["members"] += 1
            if member.label is not None and has_colon(member.label):
                colons += 1
            common: dict[str, Any] = {
                "index": member.index,
                "label": member.label,
                "method": member.method,
                "crc32": crc32_hex(member.crc32),
                "size": _ijson(member.file_size),
            }
            if member.disposition == "rejected":
                assert member.code is not None
                counters["rejected"] += 1
                ctx.emit(
                    {
                        "row": {
                            **common,
                            "disposition": "rejected",
                            "code": member.code,
                            "reason": member.detail,
                            "limit_field": _gate_limit_field(member.code, member.file_size, limits),
                        }
                    }
                )
                continue
            if chain_label_refused(member.label):
                counters["rejected"] += 1
                ctx.emit({"row": {**common, "disposition": "rejected", "code": "ingest.name.invalid",
                                  "reason": "label contains the member separator", "limit_field": None}})
                continue
            if member.disposition == "not_selected":
                counters["not_selected"] += 1
                ctx.emit({"row": {**common, "disposition": "not_selected"}})
                continue
            assert member.label is not None
            if is_nested(member.label) and member.file_size > limits.max_member_bytes and isinstance(archive, OpenedZip):
                counters["selected" if _stream_member(ctx, archive, member, common) else "rejected"] += 1
                continue
            try:
                content = archive.read_member(member)
            except IngestError as exc:
                counters["rejected"] += 1
                ctx.emit(
                    {
                        "row": {
                            **common,
                            "disposition": "rejected",
                            "code": exc.code,
                            "reason": exc.reason,
                            "limit_field": None,
                        }
                    }
                )
                continue
            counters["selected"] += 1
            ctx.member({**common, "nested": is_nested(member.label)})
            ctx.data(content)
    if colons:
        ctx.emit({"finding": {"code": "ingest.name.colon", "severity": "info", "offset": None,
                              "detail": f"{colons} member label(s) contain ':' (labels only, never paths; D-91)"}})
    return counters


def _stream_member(ctx: JobContext, archive: OpenedZip, member: ZipMember, common: Mapping[str, Any]) -> bool:
    """D-383: send a nested archive above the global member bound as it is decompressed, then ``end`` or ``abort``."""
    ctx.member({**common, "nested": True, "streamed": True})
    try:
        for chunk in archive.stream_member(member, _STREAM_CHUNK):
            ctx.data(chunk)
    except IngestError as exc:
        ctx.emit({"abort": {"index": member.index, "code": exc.code, "reason": exc.reason}})
        return False
    ctx.emit({"end": {"index": member.index}})
    return True


# --------------------------------------------------------------------------------------------------------------
# The parent side (T0): run the jobs, store the members, build rows, origins and events
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContainerSpec:
    """One container to expand: its stored digest, the register subject of the candidate, and the profile patterns.

    ``selections[d - depth]`` applies at archive level ``d`` (the container itself is at ``depth``, 1 for a pinned
    input or a file of a tree). A level without a selection selects nothing: every member is recorded ``not_selected``.

    ``parts`` declares an archive stored as byte parts (D-243): ``(sha256, size)`` in the declared order, and then
    ``sha256`` must be the digest of their split descriptor (:func:`split_descriptor`; checked here, by computation).

    D-380/D-384: ``depth`` is the absolute level the container opens at (a container member of an archive input opens at
    its parent's level + 1), ``max_depth`` the depth allowance its chain was granted by a declared nested archive (D-382),
    ``chain`` the member labels from the root container down to this one (``()`` for a root), and ``prefixed`` makes every
    member's register subject ``<path>!/<label>`` (the members of an archive input; one subject rule for every level).
    """

    sha256: str
    snapshot_id: str
    path: str
    selections: tuple[Selection, ...]
    parts: tuple[tuple[str, int], ...] = ()
    depth: int = 1
    max_depth: int | None = None
    chain: tuple[str, ...] = ()
    prefixed: bool = False

    def __post_init__(self) -> None:
        if not is_sha256_hex(self.sha256):
            raise MembersError("container digest must be 64 lower-case hex digits")
        if not self.snapshot_id or not self.path:
            raise MembersError("a container spec needs a snapshot id and a path")
        if isinstance(self.depth, bool) or not isinstance(self.depth, int) or self.depth < 1:
            raise MembersError("a container's depth is a positive integer")
        if self.max_depth is not None and (isinstance(self.max_depth, bool) or not isinstance(self.max_depth, int)):
            raise MembersError("a container's depth allowance is an integer")
        if self.parts:
            object.__setattr__(self, "parts", _check_parts(self.parts))
            if sha256_hex(split_descriptor(self.parts)) != self.sha256:
                raise MembersError("the container digest is not the split descriptor of its parts")

    def selection_at(self, depth: int) -> Selection:
        index = depth - self.depth
        return self.selections[index] if 0 <= index < len(self.selections) else Selection()


@dataclass(frozen=True, slots=True)
class ExpandEvent:
    """A register-worthy outcome of ``expand`` (HL H.6.3): the corpus layer writes it as a ``register.jsonl`` entry."""

    snapshot_id: str
    path: str
    code: str
    stage: str  # "ingest" or "expand"
    severity: str  # "warning" or "error"
    disposition: str  # "sealed", "not_imported" or "failed"
    detail: str


@dataclass(frozen=True, slots=True)
class ExpandedContainer:
    """Where an expanded container sits (D-380/D-384): its member labels from the root down (``()`` for a root), the
    level it opened at, the depth allowance of its chain, and its register subject path."""

    chain: tuple[str, ...]
    depth: int
    max_depth: int | None
    path: str


@dataclass(slots=True)
class ExpandOutcome:
    """Everything one :func:`expand_containers` call produced."""

    rows: list[MemberRow] = field(default_factory=list)
    origins: list[tuple[str, Origin]] = field(default_factory=list)  # (member object sha256, member origin)
    events: list[ExpandEvent] = field(default_factory=list)
    advisory: InterpreterAdvisory | None = None
    containers: list[str] = field(default_factory=list)  # digests of the containers that were expanded successfully
    #: every successfully expanded container (first reached, in job-key order) -> where it sits (D-380)
    placed: dict[str, ExpandedContainer] = field(default_factory=dict)
    #: ``(container, label)`` of every selected member that was expanded as a nested archive (never a candidate)
    nested_members: set[tuple[str, str]] = field(default_factory=set)


def _member_path(parent_path: str, depth: int, label: str | None, index: int, prefixed: bool = False) -> str:
    """The register subject path of a member: its label (HL H.6.2), ``#<index>`` when its name was rejected.

    A member of a nested container is prefixed with the nested container's own path and ``!/``, so two containers
    in one snapshot do not collide. ``prefixed`` gives every level that form (archive inputs, D-384), so the subject of a
    member at any level is ``<input>!/<chain>!/<member>``, built by this one rule.
    """
    leaf = label if label is not None else f"#{index}"
    return leaf if depth == 1 and not prefixed else f"{parent_path}{_SEPARATOR}{leaf}"


def _only(obj: Mapping[str, Any], required: set[str], optional: set[str], what: str) -> None:
    keys = set(obj)
    if not required <= keys or not keys <= required | optional:
        raise MembersError(f"malformed {what} frame from the worker", code="expand.protocol")


def _int_field(value: object, what: str, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_SAFE_INT:
        raise MembersError(f"malformed {what} from the worker", code="expand.protocol")
    return value


@dataclass(slots=True)
class _Item:
    """A validated member frame, before anything is stored."""

    index: int
    label: str | None
    method: int
    crc32: str
    size: int | None
    disposition: str
    code: str | None = None
    reason: str | None = None
    limit_field: str | None = None
    nested: bool = False
    output: MemberOutput | None = None


def _validate_common(obj: Mapping[str, Any]) -> tuple[int, str | None, int, str, int | None]:
    index = _int_field(obj["index"], "member index")
    label = obj["label"]
    if label is not None and (not isinstance(label, str) or not label):
        raise MembersError("malformed member label from the worker", code="expand.protocol")
    method = _int_field(obj["method"], "member method")
    crc = obj["crc32"]
    if not isinstance(crc, str) or _HEX8.fullmatch(crc) is None:
        raise MembersError("malformed member crc32 from the worker", code="expand.protocol")
    size = _int_field(obj["size"], "member size", nullable=True)
    assert index is not None and method is not None
    return index, label, method, crc, size


_COMMON_KEYS = {"index", "label", "method", "crc32", "size"}


def _parse_outputs(result_outputs: Sequence[Any]) -> tuple[list[dict[str, Any]], list[_Item]]:
    findings: list[dict[str, Any]] = []
    items: list[_Item] = []
    streamed: _Item | None = None  # a streamed member waiting for its closing frame (D-383)
    for out in result_outputs:
        if streamed is not None:
            _close_streamed(streamed, out)
            items.append(streamed)
            streamed = None
            continue
        if isinstance(out, MemberOutput):
            header = out.header
            _only(header, _COMMON_KEYS | {"nested"}, {"streamed"}, "member")
            index, label, method, crc, size = _validate_common(header)
            if label is None or size is None or not isinstance(header["nested"], bool):
                raise MembersError("a selected member frame is inconsistent", code="expand.protocol")
            item = _Item(index, label, method, crc, size, "selected", nested=header["nested"], output=out)
            if "streamed" in header:
                if header["streamed"] is not True or not header["nested"]:
                    raise MembersError("only a nested archive is streamed", code="expand.protocol")
                streamed = item
                continue
            if out.size != size:
                raise MembersError("a selected member frame is inconsistent", code="expand.protocol")
            items.append(item)
        elif "finding" in out and len(out) == 1:
            finding = out["finding"]
            _only(finding, {"code", "severity", "offset", "detail"}, set(), "finding")
            if finding["code"] not in INGEST_CODES or finding["severity"] not in ("info", "warning", "error"):
                raise MembersError("malformed finding from the worker", code="expand.protocol")
            findings.append(finding)
        elif "row" in out and len(out) == 1:
            row = out["row"]
            _only(row, _COMMON_KEYS | {"disposition"}, {"code", "reason", "limit_field"}, "row")
            index, label, method, crc, size = _validate_common(row)
            disposition = row["disposition"]
            if disposition not in ("not_selected", "rejected") or (label is None and disposition != "rejected"):
                raise MembersError("malformed member row from the worker", code="expand.protocol")
            code = row.get("code")
            if (disposition == "rejected") != (code is not None) or (code is not None and code not in INGEST_CODES):
                raise MembersError("malformed member code from the worker", code="expand.protocol")
            reason, limit_field = row.get("reason"), row.get("limit_field")
            if reason is not None and not isinstance(reason, str):
                raise MembersError("malformed member reason from the worker", code="expand.protocol")
            if limit_field is not None and limit_field not in IngestLimits().to_json():
                raise MembersError("malformed limit field from the worker", code="expand.protocol")
            items.append(_Item(index, label, method, crc, size, disposition, code, reason, limit_field))
        else:
            raise MembersError("unexpected frame from the expand worker", code="expand.protocol")
    if streamed is not None:
        raise MembersError("a streamed member has no closing frame", code="expand.protocol")
    return findings, items


def _close_streamed(item: _Item, frame: Any) -> None:
    """D-383: the frame after a streamed member must be its ``end`` (all its bytes arrived) or its ``abort`` (a
    member-level defect: the member is rejected with the code and its spooled bytes are discarded)."""
    if isinstance(frame, MemberOutput) or len(frame) != 1 or not ({"end", "abort"} & set(frame)):
        raise MembersError("a streamed member is not closed by its end or abort frame", code="expand.protocol")
    assert item.output is not None
    if "end" in frame:
        _only(frame["end"], {"index"}, set(), "end")
        if frame["end"]["index"] != item.index or item.output.size != item.size:
            raise MembersError("a streamed member's end frame does not match it", code="expand.protocol")
        return
    abort = frame["abort"]
    _only(abort, {"index", "code", "reason"}, set(), "abort")
    if abort["index"] != item.index or abort["code"] not in INGEST_CODES or not isinstance(abort["reason"], str):
        raise MembersError("a streamed member's abort frame is malformed", code="expand.protocol")
    item.output.close()
    item.output, item.disposition, item.code, item.reason = None, "rejected", abort["code"], abort["reason"]


def expand_containers(
    store: RawObjectStore,
    containers: Sequence[ContainerSpec],
    *,
    pool: WorkerPool,
    limits: IngestLimits | None = None,
    release: bool = False,
) -> ExpandOutcome:
    """Expand ``containers`` (and the nested archives their selections name) through T1 workers (AD-12).

    The interpreter guard (G.3.8) runs first, in this process and before any object is opened: in release mode below
    the floor it raises (exit 3); in dev mode it warns, and the advisory is on the outcome and becomes one
    ``ingest.interpreter.unpatched`` event per root container. ``pool`` must read the same store (``store_root`` is
    ``store.objects_dir``). Containers at one depth are submitted as one batch; results are processed in job-key order,
    so the outcome does not depend on the worker count.

    Each container opens at its spec's ``depth`` and is refused (``ingest.archive.depth``, never opened) above
    ``depth_limit(limits, max_depth)``; a declared nested archive (D-382) is expanded with its own selection, one level
    deeper, under the allowance of its chain. The job of a container whose selection declares nested archives may carry
    members up to the largest raised ``max_member_bytes`` (D-383).

    A structural defect rejects that container (an ``ingest.*`` event; the container object stays stored), a
    member-level defect rejects that member only, a worker limit or crash gives ``worker.limit.*`` / ``expand.failed``.
    A nested archive that archive content reaches again with another selection is not expanded twice: that reach is an
    ``expand.conflict`` event (CB-22); a caller spec that disagrees with another reach raises ``MembersConflictError``.
    Nothing is written to disk except member objects in ``store``; the caller records ``rows``, ``origins`` and
    ``events``.
    """
    limits = limits or IngestLimits()
    if pool.store_root is None or Path(pool.store_root).resolve() != store.objects_dir.resolve():
        raise ValueError("the worker pool must be built with store_root=store.objects_dir")
    advisory = require_patched_for_archive(release=release)
    outcome = ExpandOutcome(advisory=advisory)
    if advisory is not None:
        for spec in containers:
            outcome.events.append(
                ExpandEvent(
                    spec.snapshot_id,
                    spec.path,
                    "ingest.interpreter.unpatched",
                    "ingest",
                    "warning",
                    "sealed",
                    violation_detail(
                        container=spec.sha256,
                        reason=f"python {advisory.python_version} below floor {advisory.floor}",
                    ),
                )
            )

    job_limits = dataclasses.replace(
        pool.limits, max_member_bytes=limits.max_member_bytes, max_total_bytes=limits.max_total_bytes
    ).with_expand_scaling(limits.max_total_bytes)
    done: dict[str, tuple[str, bool]] = {}  # container digest -> (fn_digest, reached as a caller spec) in this call
    level: list[tuple[ContainerSpec, str, int, bool]] = [(spec, spec.path, spec.depth, True) for spec in containers]
    while level:
        batch: dict[str, tuple[ContainerSpec, str, str, Selection, int]] = {}
        for spec, path, d, root in sorted(level, key=lambda t: (t[2], t[0].sha256, t[1])):
            selection = spec.selection_at(d)
            fn = expand_fn_digest(limits, selection)
            if spec.sha256 in done:
                if done[spec.sha256][0] != fn:
                    if root or done[spec.sha256][1]:  # a caller spec takes part: API misuse
                        raise MembersConflictError("one container is reached with two different selections")
                    # archive content reaches one nested archive at two levels (CB-22): the first expansion stands
                    outcome.events.append(
                        ExpandEvent(spec.snapshot_id, path, "expand.conflict", "expand", "error", "failed",
                                    violation_detail(container=spec.sha256,
                                                     reason="nested archive already expanded with another selection"))
                    )  # fmt: skip
                continue
            done[spec.sha256] = (fn, root)
            if d > depth_limit(limits, spec.max_depth):  # never opened (G.3.2)
                outcome.events.append(
                    _ingest_event(spec, path, "ingest.archive.depth", limits, None, _container_size(store, spec.sha256))
                )
                continue
            missing = [sha for sha in (spec.sha256, *(p for p, _ in spec.parts)) if not store.has(sha)]
            if missing:
                what = "container" if missing[0] == spec.sha256 else "part"
                outcome.events.append(
                    ExpandEvent(spec.snapshot_id, path, "expand.container_missing", "expand", "error", "failed",
                                violation_detail(container=spec.sha256, reason=f"{what} not in the raw store"))
                )
                continue
            batch[f"{d}:{spec.sha256}"] = (spec, path, fn, selection, d)
        jobs = [_job(key, spec, selection, limits, d, release, job_limits) for key, (spec, _p, _f, selection, d) in
                sorted(batch.items())]  # fmt: skip
        next_level: list[tuple[ContainerSpec, str, int]] = []
        if jobs:
            for result in pool.run(jobs):
                spec, path, fn, selection, d = batch[result.key]
                try:
                    _consume(store, spec, path, d, fn, selection, limits, result, outcome, next_level)
                finally:
                    result.close()
        level = [(spec, path, d, False) for spec, path, d in next_level]
    return outcome


def _job(key: str, spec: ContainerSpec, selection: Selection, limits: IngestLimits, depth: int, release: bool,
         job_limits: Any) -> Job:  # fmt: skip
    """The ``expand`` job of one container; a split archive (D-243) adds its parts as inputs and ``split: true``; a
    selection with declared nested archives (D-382) adds ``children`` and raises the job's member cap to the largest
    raised ``max_member_bytes``; a container with a depth allowance adds ``max_depth``."""
    params: dict[str, Any] = {
        "limits": limits.to_json(),
        "include": list(selection.include),
        "nested": list(selection.nested),
        "depth": depth,
        "release": release,
    }
    if selection.children:
        params["children"] = [{"pattern": c.pattern, **{k: v for k, v in c.raises.to_json().items() if k != "max_depth"}}
                              for c in selection.children]  # fmt: skip
        member_cap = max(c.raises.member_bytes(limits) for c in selection.children)
        if member_cap > job_limits.max_member_bytes:
            job_limits = dataclasses.replace(job_limits, max_member_bytes=member_cap)
    if spec.max_depth is not None:
        params["max_depth"] = spec.max_depth
    inputs = [{"sha256": spec.sha256, "role": "container"}]
    if spec.parts:
        params["split"] = True
        inputs.extend({"sha256": sha, "role": "part"} for sha, _size in spec.parts)
    return Job(key, JOB_KIND, inputs=tuple(inputs), params=params, limits=job_limits)


def _container_size(store: RawObjectStore, sha256: str) -> int | None:
    try:
        return store.size(sha256)
    except KeyError:
        return None


def _ingest_event(
    spec: ContainerSpec,
    path: str,
    code: str,
    limits: IngestLimits,
    field_name: str | None,
    size: int | None,
    *,
    reason: str | None = None,
) -> ExpandEvent:
    """An ``ingest.*`` event for a whole container: sha256, size and effective limit, never bytes (G.3.9)."""
    limit = limit_field_for(code, limits, field=field_name)
    return ExpandEvent(
        spec.snapshot_id,
        path,
        code,
        "ingest",
        "error",
        "not_imported",
        violation_detail(sha256=spec.sha256, size=size, limit=limit, reason=reason),
    )


def _failure_event(spec: ContainerSpec, path: str, error: AgentProvError, limits: IngestLimits, size: int | None) -> ExpandEvent:
    """Map a failed job to its register event (HL H.6.3): ``ingest.*``, ``worker.limit.*`` or ``expand.failed``."""
    if isinstance(error, WorkerLimitError):
        return ExpandEvent(
            spec.snapshot_id, path, error.code, "expand", "error", "failed",
            violation_detail(sha256=spec.sha256, size=size, reason="worker limit"),
        )
    if error.code in INGEST_CODES:
        field_name = "max_split_bytes" if spec.parts and error.code == "ingest.size.file" else None
        return _ingest_event(spec, path, error.code, limits, field_name, size)
    code = "expand.failed"
    reason = f"job error {error.code}" if isinstance(error, WorkerError) else "job error"
    return ExpandEvent(spec.snapshot_id, path, code, "expand", "error", "failed",
                       violation_detail(sha256=spec.sha256, size=size, reason=reason))


def _consume(
    store: RawObjectStore,
    spec: ContainerSpec,
    path: str,
    depth: int,
    fn: str,
    selection: Selection,
    limits: IngestLimits,
    result: Any,
    outcome: ExpandOutcome,
    next_level: list[tuple[ContainerSpec, str, int]],
) -> None:
    size = _container_size(store, spec.sha256)
    if result.error is not None:
        outcome.events.append(_failure_event(spec, path, result.error, limits, size))
        return
    try:
        findings, items = _parse_outputs(result.outputs)
        indexes = [item.index for item in items]
        if len(set(indexes)) != len(indexes):
            raise MembersError("duplicate member index from the worker", code="expand.protocol")
        events: list[ExpandEvent] = []
        rows: list[MemberRow] = []
        origins: list[tuple[str, Origin]] = []
        children: list[tuple[ContainerSpec, str, int]] = []
        nested_members: set[tuple[str, str]] = set()
        for finding in findings:
            events.append(
                ExpandEvent(
                    spec.snapshot_id, path, finding["code"], "ingest",
                    finding["severity"], "sealed",
                    violation_detail(container=spec.sha256, reason=finding["detail"]),
                )
            )
        for item in items:
            crc_int = int(item.crc32, 16)
            member_path = _member_path(path, depth, item.label, item.index, spec.prefixed)
            if item.disposition == "selected":
                assert item.output is not None and item.label is not None and item.size is not None
                child = selection.child_for(item.label)
                if (child is not None and not item.nested) or (item.nested and child is None and not selection.nested):
                    raise MembersError("a member's nested flag disagrees with the selection", code="expand.protocol")
                put: PutResult = store.put_chunks(
                    item.output.iter_chunks(),
                    ext=ext_for_label(item.label),
                    max_bytes=limits.max_member_bytes if child is None else child.raises.member_bytes(limits),
                    declared_size=item.size,
                    expected_size=item.size,
                    expected_crc32=crc_int,
                )
                row = MemberRow(spec.sha256, fn, item.label, item.method, item.crc32, item.size, put.sha256, "selected")
                rows.append(row)
                origins.append((put.sha256, row.origin()))
                if child is not None:  # a declared nested archive: its own selection, one level deeper (D-382)
                    allowance = max(spec.max_depth or 0, child.raises.max_depth or 0) or None
                    children.append((ContainerSpec(put.sha256, spec.snapshot_id, member_path, (child.selection,),
                                                   depth=depth + 1, max_depth=allowance,
                                                   chain=(*spec.chain, item.label), prefixed=spec.prefixed),
                                     member_path, depth + 1))  # fmt: skip
                    nested_members.add((spec.sha256, item.label))
                elif item.nested:
                    children.append(
                        (dataclasses.replace(spec, sha256=put.sha256, parts=(), chain=(*spec.chain, item.label)),
                         member_path, depth + 1)  # a member is a plain container
                    )
                    nested_members.add((spec.sha256, item.label))
                continue
            rows.append(
                MemberRow(spec.sha256, fn, item.label, item.method, item.crc32, item.size, None, item.disposition, item.code)
            )
            if item.disposition == "rejected":
                assert item.code is not None
                limit = limit_field_for(item.code, limits, field=item.limit_field) if item.limit_field else None
                events.append(
                    ExpandEvent(
                        spec.snapshot_id,
                        member_path,
                        item.code,
                        "ingest",
                        "error",
                        "not_imported",
                        violation_detail(container=spec.sha256, size=item.size, limit=limit, reason=item.reason),
                    )
                )
    except (MembersError, ObjectMismatchError, RawStoreError, OSError) as exc:
        outcome.events.append(
            ExpandEvent(spec.snapshot_id, path, "expand.failed", "expand", "error", "failed",
                        violation_detail(sha256=spec.sha256, size=size, reason=f"expand error {getattr(exc, 'code', 'io')}"))
        )
        return
    outcome.rows.extend(rows)
    outcome.origins.extend(origins)
    outcome.events.extend(events)
    outcome.containers.append(spec.sha256)
    outcome.placed.setdefault(spec.sha256, ExpandedContainer(spec.chain, depth, spec.max_depth, path))
    outcome.nested_members |= nested_members
    next_level.extend(children)
