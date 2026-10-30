"""Golden-fixture loader and byte-comparison helpers (docs/architecture K.3.2, K.7, J.2.2, G.8.1 item 5; R-42).

**Layout.** The golden fixtures live in ``tests/fixtures/agentdojo_prov_v1/golden/`` (K.3.1). The directory is found by
:func:`golden_dir`: the environment variable ``AGENTPROV_GOLDEN_DIR`` when set, else the repository default. The index
``golden_index.json`` sits in that directory; its file paths are relative to the *fixtures root*, which is
``golden_dir().parent.parent`` (J.2.2), so the native logs under ``tests/fixtures/agentdojo/`` resolve as well.

**Index (J.2.2).** A JSON list; each entry is a :class:`GoldenEntry`: ``id`` (``R01``-``R10``, ``C01``-``C09``,
``N-C01``-``N-C09``), ``kind`` (``v1_pair`` or ``native_log``), ``files`` (``path``, ``sha256``, ``bytes``, an optional
``git_blob_sha1`` and, as an additive field, ``role``), ``origin``, ``aliases``, ``licence`` and ``licence_class``,
``why``, ``hazards``, ``expect`` and, for converted pairs, ``native`` (the id of the native log behind the pair).

**Output hygiene (G.8.1 item 5).** Fixtures hold third-party model outputs and prompt-injection payloads. Nothing in this
module prints a fixture substring longer than :data:`EXCERPT_CHARS` characters, and every excerpt goes through
:func:`agentprov.ingest.quote.escape_untrusted`. A byte difference is reported as the line, the JSON Pointer, both
sha256 values and one escaped excerpt each. :func:`assertrepr_compare` applies the same rule to every ``str`` and
``bytes`` operand of a failed assertion; ``tests/conftest.py`` installs it as ``pytest_assertrepr_compare``.

``agentprov.testing`` may import L0-L6 only and may be imported only by ``tests/`` and ``tools/`` (M.5.1).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.quote import escape_untrusted

#: Environment variable that overrides :func:`golden_dir`.
ENV_GOLDEN_DIR: Final = "AGENTPROV_GOLDEN_DIR"

#: ``<repo>/src/agentprov/testing/golden.py`` -> ``<repo>``.
REPO_ROOT: Final = Path(__file__).resolve().parents[3]
DEFAULT_GOLDEN_DIR: Final = REPO_ROOT / "tests" / "fixtures" / "agentdojo_prov_v1" / "golden"
INDEX_NAME: Final = "golden_index.json"

#: Largest fixture substring any helper prints (R-42; G.8.1 item 5).
EXCERPT_CHARS: Final = 40

KIND_V1_PAIR: Final = "v1_pair"
KIND_NATIVE_LOG: Final = "native_log"
KINDS: Final = (KIND_V1_PAIR, KIND_NATIVE_LOG)

ROLE_V1_TRANSCRIPT: Final = "v1_transcript"
ROLE_COMPAT_GRAPH: Final = "compat_graph"
ROLE_NATIVE_LOG: Final = "native_log"
ROLES: Final = (ROLE_V1_TRANSCRIPT, ROLE_COMPAT_GRAPH, ROLE_NATIVE_LOG)

#: Licence classes of K.4.2 (RESOLUTIONS §3.8): the closed set.
LICENCE_CLASSES: Final = frozenset({"permissive", "noncommercial", "restricted", "restricted_use"})

#: Hazard tags of the index. The four MIG-10 pairs (R-59) carry ``mig10`` plus their J.2.1 hazard.
HAZARD_TAGS: Final = frozenset(
    {
        "mig10",
        "nested_order",  # a non-lexicographic object nested inside ``args`` (needs ``ext.lex.ord`` at depth)
        "wall_clock_integral",  # an integral ``wall_clock_s`` (needs ``ext.lex.flt`` on ``/t/dur_s``)
        "args_order_top",  # a top-level ``args`` object whose keys are not in lexicographic order
        "args_float_integral",  # an integral float inside ``args`` (``1.0``)
    }
)

_ID_PREFIXES: Final = ("R", "C", "N-C")


class GoldenIndexError(Exception):
    """The golden index is missing, malformed or inconsistent (``problems`` lists each defect; no fixture text)."""

    def __init__(self, message: str, problems: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.problems = tuple(problems)


# ---------------------------------------------------------------------------------------------------- locations


def golden_dir() -> Path:
    """The golden fixture directory: ``$AGENTPROV_GOLDEN_DIR`` when set and non-empty, else the repository default."""
    override = os.environ.get(ENV_GOLDEN_DIR, "").strip()
    return Path(override).expanduser() if override else DEFAULT_GOLDEN_DIR


def fixtures_root() -> Path:
    """The ``tests/fixtures`` directory that index paths are relative to (``golden_dir().parent.parent``, J.2.2)."""
    return golden_dir().parent.parent


def index_path() -> Path:
    return golden_dir() / INDEX_NAME


def golden_skip_reason() -> str | None:
    """Why golden tests cannot run here (``None`` when they can). Use as ``pytest.skip(reason)``."""
    path = index_path()
    if path.is_file():
        return None
    return (
        f"golden fixtures not found: no {INDEX_NAME} in {golden_dir()} "
        f"(copy tests/fixtures from the staging tree, or set {ENV_GOLDEN_DIR})"
    )


def golden_available() -> bool:
    return golden_skip_reason() is None


# ---------------------------------------------------------------------------------------------------- digests


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    """The git blob id of ``data``: ``sha1("blob <len>\\0" + data)`` (what ``git hash-object`` prints)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


# ---------------------------------------------------------------------------------------------------- the index


@dataclass(frozen=True, slots=True)
class GoldenFile:
    role: str
    path: str  # relative to fixtures_root(), POSIX separators
    sha256: str
    size: int  # the index key is ``bytes``
    git_blob_sha1: str | None = None

    @property
    def abspath(self) -> Path:
        return fixtures_root() / self.path

    def read_bytes(self) -> bytes:
        return self.abspath.read_bytes()


@dataclass(frozen=True, slots=True)
class GoldenEntry:
    id: str
    kind: str
    files: tuple[GoldenFile, ...]
    origin: Mapping[str, Any]
    aliases: tuple[str, ...]
    licence: str
    licence_class: str
    why: str = field(repr=False)
    hazards: tuple[str, ...]
    expect: Mapping[str, Any] = field(repr=False)
    native: str | None = None  # converted pairs: the id (``N-Cnn``) of the native log behind the pair

    @property
    def tree(self) -> str | None:
        """``"release"`` or ``"converted"`` for a v1 pair, else ``None``."""
        tree = self.origin.get("tree")
        return tree if isinstance(tree, str) else None

    @property
    def is_converted(self) -> bool:
        return self.tree == "converted"

    def file(self, role: str) -> GoldenFile:
        for item in self.files:
            if item.role == role:
                return item
        raise KeyError(f"{self.id} has no file with role {role!r}")

    def path_of(self, role: str) -> Path:
        return self.file(role).abspath

    def read_bytes(self, role: str) -> bytes:
        return self.file(role).read_bytes()

    def transcript_bytes(self) -> bytes:
        """The stored ``transcript/v1`` bytes of a v1 pair."""
        return self.read_bytes(ROLE_V1_TRANSCRIPT)

    def graph_bytes(self) -> bytes:
        """The stored baseline (``adprov-v2.3-compat``) graph bytes of a v1 pair."""
        return self.read_bytes(ROLE_COMPAT_GRAPH)

    def native_bytes(self) -> bytes:
        """The native log bytes of a ``native_log`` entry."""
        return self.read_bytes(ROLE_NATIVE_LOG)


def _problems_of_entry(raw: object, position: int) -> list[str]:
    where = f"entry {position}"
    if not isinstance(raw, dict):
        return [f"{where}: not an object"]
    out: list[str] = []
    ident = raw.get("id")
    if not isinstance(ident, str) or not ident.startswith(_ID_PREFIXES):
        out.append(f"{where}: bad id")
        ident = f"#{position}"
    where = f"entry {ident}"
    kind = raw.get("kind")
    if kind not in KINDS:
        out.append(f"{where}: kind must be one of {KINDS}")
    for key, typ in (("origin", dict), ("aliases", list), ("hazards", list), ("expect", dict), ("files", list)):
        if not isinstance(raw.get(key), typ):
            out.append(f"{where}: {key} must be a {typ.__name__}")
    for key in ("licence", "licence_class", "why"):
        if not isinstance(raw.get(key), str):
            out.append(f"{where}: {key} must be a string")
    if raw.get("licence_class") not in LICENCE_CLASSES:
        out.append(f"{where}: licence_class outside the allow-list")
    if isinstance(raw.get("hazards"), list):
        out.extend(f"{where}: unknown hazard tag" for tag in raw["hazards"] if tag not in HAZARD_TAGS)
    files = raw.get("files")
    roles: list[Any] = []
    if isinstance(files, list):
        for j, item in enumerate(files):
            fwhere = f"{where} file {j}"
            if not isinstance(item, dict):
                out.append(f"{fwhere}: not an object")
                continue
            roles.append(item.get("role"))
            if item.get("role") not in ROLES:
                out.append(f"{fwhere}: bad role")
            path = item.get("path")
            if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/") or "\\" in path:
                out.append(f"{fwhere}: path must be a relative POSIX path without '..'")
            digest = item.get("sha256")
            if not (isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)):
                out.append(f"{fwhere}: sha256 must be 64 lower-case hex digits")
            size = item.get("bytes")
            if not (isinstance(size, int) and not isinstance(size, bool) and size >= 0):
                out.append(f"{fwhere}: bytes must be a non-negative integer")
            blob = item.get("git_blob_sha1")
            if blob is not None and not (isinstance(blob, str) and len(blob) == 40):
                out.append(f"{fwhere}: git_blob_sha1 must be 40 hex digits")
    expected_roles = {
        KIND_V1_PAIR: [ROLE_V1_TRANSCRIPT, ROLE_COMPAT_GRAPH],
        KIND_NATIVE_LOG: [ROLE_NATIVE_LOG],
    }.get(kind if isinstance(kind, str) else "")
    if expected_roles is not None and roles != expected_roles:
        out.append(f"{where}: files must have the roles {expected_roles} in this order")
    if kind == KIND_V1_PAIR and not (isinstance(raw.get("origin"), dict) and raw["origin"].get("tree") in ("release", "converted")):
        out.append(f"{where}: origin.tree must be 'release' or 'converted'")
    return out


def validate_index(raw: object) -> list[str]:
    """Schema problems of a decoded index (an empty list when it is well formed). Never includes fixture text."""
    if not isinstance(raw, list):
        return ["the index must be a JSON list"]
    problems: list[str] = []
    seen: set[str] = set()
    paths: set[str] = set()
    for position, item in enumerate(raw):
        problems.extend(_problems_of_entry(item, position))
        if isinstance(item, dict):
            ident = item.get("id")
            if isinstance(ident, str):
                if ident in seen:
                    problems.append(f"duplicate id {ident}")
                seen.add(ident)
            for f in item.get("files", []) if isinstance(item.get("files"), list) else []:
                if isinstance(f, dict) and isinstance(f.get("path"), str):
                    if f["path"] in paths:
                        problems.append(f"entry {ident}: path listed twice")
                    paths.add(f["path"])
    by_id = {item.get("id"): item for item in raw if isinstance(item, dict)}
    for item in raw:
        if isinstance(item, dict) and item.get("native") is not None:
            target = by_id.get(item["native"])
            if target is None or target.get("kind") != KIND_NATIVE_LOG:
                problems.append(f"entry {item.get('id')}: native does not name a native_log entry")
    return problems


def _entry_from_raw(raw: dict[str, Any]) -> GoldenEntry:
    files = tuple(
        GoldenFile(
            role=f["role"],
            path=f["path"],
            sha256=f["sha256"],
            size=f["bytes"],
            git_blob_sha1=f.get("git_blob_sha1"),
        )
        for f in raw["files"]
    )
    return GoldenEntry(
        id=raw["id"],
        kind=raw["kind"],
        files=files,
        origin=raw["origin"],
        aliases=tuple(raw["aliases"]),
        licence=raw["licence"],
        licence_class=raw["licence_class"],
        why=raw["why"],
        hazards=tuple(raw["hazards"]),
        expect=raw["expect"],
        native=raw.get("native"),
    )


def load_index(path: Path | None = None) -> tuple[GoldenEntry, ...]:
    """Load and schema-check ``golden_index.json`` (default: ``golden_dir()/golden_index.json``).

    Raises :class:`GoldenIndexError` when the file is missing, is not strict JSON, or fails :func:`validate_index`.
    Entries are in file order. The index is parsed with the strict tier-1 loader (duplicate keys are rejected).
    """
    target = path if path is not None else index_path()
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise GoldenIndexError(f"cannot read the golden index: {exc.__class__.__name__}") from None
    try:
        raw = strict_json_loads(data, IngestLimits())
    except Exception as exc:
        raise GoldenIndexError(f"the golden index is not strict JSON: {getattr(exc, 'code', exc.__class__.__name__)}") from None
    problems = validate_index(raw)
    if problems:
        raise GoldenIndexError(f"the golden index has {len(problems)} problem(s)", problems)
    return tuple(_entry_from_raw(item) for item in raw)


def _natural_key(ident: str) -> tuple[str, int]:
    head = ident.rstrip("0123456789")
    tail = ident[len(head) :]
    return head, int(tail) if tail else 0


def entries(kind: str | None = None, *, path: Path | None = None) -> tuple[GoldenEntry, ...]:
    """All entries (optionally of one ``kind``), sorted ``R01..R10, C01..C09, N-C01..N-C09``."""
    order = {"R": 0, "C": 1, "N-C": 2}
    selected = [e for e in load_index(path) if kind is None or e.kind == kind]
    return tuple(sorted(selected, key=lambda e: (order[_natural_key(e.id)[0]], _natural_key(e.id)[1])))


def v1_pairs(*, path: Path | None = None) -> tuple[GoldenEntry, ...]:
    """The 19 golden pairs (R01-R10, C01-C09), the four MIG-10 pairs included."""
    return entries(KIND_V1_PAIR, path=path)


def native_logs(*, path: Path | None = None) -> tuple[GoldenEntry, ...]:
    return entries(KIND_NATIVE_LOG, path=path)


def get_entry(ident: str, *, path: Path | None = None) -> GoldenEntry:
    for entry in load_index(path):
        if entry.id == ident:
            return entry
    raise KeyError(f"no golden entry {ident!r}")


def native_of(entry: GoldenEntry, *, path: Path | None = None) -> GoldenEntry | None:
    """The native-log entry behind a converted pair (``None`` for a release pair)."""
    return get_entry(entry.native, path=path) if entry.native else None


def verify_entry_files(entry: GoldenEntry) -> list[str]:
    """Problems with ``entry``'s files on disk: missing, size or sha256 mismatch, git blob id mismatch (no fixture text)."""
    out: list[str] = []
    for item in entry.files:
        where = f"{entry.id}:{item.role}"
        try:
            data = item.read_bytes()
        except OSError as exc:
            out.append(f"{where}: unreadable ({exc.__class__.__name__})")
            continue
        if len(data) != item.size:
            out.append(f"{where}: size {len(data)} != indexed {item.size}")
        if sha256_hex(data) != item.sha256:
            out.append(f"{where}: sha256 {sha256_hex(data)} != indexed {item.sha256}")
        if item.git_blob_sha1 is not None and git_blob_sha1(data) != item.git_blob_sha1:
            out.append(f"{where}: git blob sha1 {git_blob_sha1(data)} != indexed {item.git_blob_sha1}")
    return out


# ---------------------------------------------------------------------------------------------------- byte diffs


@dataclass(frozen=True, slots=True)
class ByteDiff:
    """The first difference between two byte strings (``None`` is returned by :func:`diff_bytes` when equal).

    ``line`` and ``column`` are 1-based (``column`` counts bytes); ``offset`` is the 0-based byte offset of the first
    differing byte (or the shorter length when one value is a prefix of the other). ``pointer`` is the JSON Pointer of
    the innermost value or object member that holds the offset in the *expected* document, or ``None`` when the bytes
    are not parseable as JSON or the offset lies past the end. The text fields are in-memory only (``repr=False``);
    :func:`describe_diff` prints them escaped and truncated.
    """

    offset: int
    line: int
    column: int
    expected_sha256: str
    actual_sha256: str
    expected_length: int
    actual_length: int
    pointer: str | None = field(repr=False)
    expected_excerpt: str = field(repr=False)  # raw, untruncated window; never printed unescaped
    actual_excerpt: str = field(repr=False)


def first_difference_offset(expected: bytes, actual: bytes) -> int | None:
    """The offset of the first differing byte, ``min(len)`` for a pure prefix, ``None`` when equal."""
    if expected == actual:
        return None
    limit = min(len(expected), len(actual))
    lo, hi = 0, limit  # binary search on the common-prefix length: O(n) compares of slices, fast for large inputs
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if expected[:mid] == actual[:mid]:
            lo = mid
        else:
            hi = mid - 1
    return lo


class _PointerScanner:
    """Finds the JSON Pointer of the innermost value (or member) that covers one byte offset. Bytes, no decoding."""

    _MAX_DEPTH: Final = 200
    _WS: Final = b" \t\r\n"
    _LITERAL: Final = re.compile(rb"true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")

    def __init__(self, data: bytes, target: int) -> None:
        self.data = data
        self.target = target
        self.best: str | None = None

    def run(self) -> str | None:
        try:
            i = self._skip(0)
            end = self._skip(self._value(i, "", 0))
            if end != len(self.data):
                return None
        except (ValueError, IndexError):
            return None
        return self.best

    def _skip(self, i: int) -> int:
        data = self.data
        while i < len(data) and data[i] in self._WS:
            i += 1
        return i

    @staticmethod
    def _token(raw: str) -> str:
        return raw.replace("~", "~0").replace("/", "~1")

    def _string_end(self, i: int) -> int:
        data = self.data
        if data[i] != 0x22:
            raise ValueError
        i += 1
        while data[i] != 0x22:
            i += 2 if data[i] == 0x5C else 1
        return i + 1

    def _value(self, i: int, path: str, depth: int) -> int:
        if depth > self._MAX_DEPTH:
            raise ValueError
        data = self.data
        start = i
        first = data[i]
        if first == 0x7B:  # {
            i = self._skip(i + 1)
            if data[i] == 0x7D:
                i += 1
            else:
                while True:
                    key_start = i
                    key_end = self._string_end(i)
                    key = json.loads(data[key_start:key_end].decode("utf-8", "replace"))
                    member = f"{path}/{self._token(key)}"
                    i = self._skip(key_end)
                    if data[i] != 0x3A:
                        raise ValueError
                    i = self._skip(i + 1)
                    value_end = self._value(i, member, depth + 1)
                    if self.best is None and key_start <= self.target < value_end:
                        self.best = member
                    i = self._skip(value_end)
                    if data[i] == 0x2C:
                        i = self._skip(i + 1)
                        continue
                    if data[i] == 0x7D:
                        i += 1
                        break
                    raise ValueError
        elif first == 0x5B:  # [
            i = self._skip(i + 1)
            if data[i] == 0x5D:
                i += 1
            else:
                index = 0
                while True:
                    element = f"{path}/{index}"
                    i = self._value(i, element, depth + 1)
                    i = self._skip(i)
                    if data[i] == 0x2C:
                        i = self._skip(i + 1)
                        index += 1
                        continue
                    if data[i] == 0x5D:
                        i += 1
                        break
                    raise ValueError
        elif first == 0x22:
            i = self._string_end(i)
        else:
            while i < len(data) and data[i] not in b",]} \t\r\n":
                i += 1
            if self._LITERAL.fullmatch(data[start:i]) is None:
                raise ValueError
        if self.best is None and start <= self.target < i:
            self.best = path
        return i


def json_pointer_at(data: bytes, offset: int) -> str | None:
    """The JSON Pointer (RFC 6901) of the innermost value or member of ``data`` whose bytes cover ``offset``.

    Whitespace and punctuation resolve to the enclosing container. Returns ``None`` when ``data`` is not well-formed
    JSON by this scanner's reading, nests deeper than 200, or ``offset`` is outside the document.
    """
    if not 0 <= offset < len(data):
        return None
    return _PointerScanner(data, offset).run()


def _window(data: bytes, offset: int) -> str:
    """Up to :data:`EXCERPT_CHARS` characters of ``data`` starting a few bytes before ``offset`` (raw, not escaped)."""
    start = max(offset - 8, data.rfind(b"\n", 0, offset) + 1)
    return data[start : start + 4 * EXCERPT_CHARS].decode("utf-8", "surrogateescape")[:EXCERPT_CHARS]


def diff_bytes(expected: bytes, actual: bytes) -> ByteDiff | None:
    """Compare two byte strings; ``None`` when they are identical, else the first difference (G.8.1 item 5)."""
    offset = first_difference_offset(expected, actual)
    if offset is None:
        return None
    line = expected.count(b"\n", 0, offset) + 1
    column = offset - (expected.rfind(b"\n", 0, offset) + 1) + 1
    return ByteDiff(
        offset=offset,
        line=line,
        column=column,
        expected_sha256=sha256_hex(expected),
        actual_sha256=sha256_hex(actual),
        expected_length=len(expected),
        actual_length=len(actual),
        pointer=json_pointer_at(expected, offset),
        expected_excerpt=_window(expected, offset),
        actual_excerpt=_window(actual, offset),
    )


def _show(text: str) -> str:
    """A fixture substring as it may appear in output: truncated to :data:`EXCERPT_CHARS` and escaped."""
    return escape_untrusted(text[:EXCERPT_CHARS])


def describe_diff(diff: ByteDiff, *, expected: str = "expected", actual: str = "actual") -> list[str]:
    """The lines that report ``diff``: line, column, JSON Pointer, both sha256, escaped excerpts <= 40 characters."""
    pointer = "(none: not parseable as JSON, or past the end)" if diff.pointer is None else _show(diff.pointer)
    return [
        f"bytes differ at offset {diff.offset} (line {diff.line}, column {diff.column})",
        f"JSON Pointer: {pointer}",
        f"{expected}: sha256 {diff.expected_sha256}, {diff.expected_length} bytes",
        f"{actual}: sha256 {diff.actual_sha256}, {diff.actual_length} bytes",
        f"{expected} excerpt: {_show(diff.expected_excerpt)}",
        f"{actual} excerpt: {_show(diff.actual_excerpt)}",
    ]


def assert_bytes_equal(expected: bytes, actual: bytes, *, what: str = "bytes") -> None:
    """Assert byte identity. On failure raise ``AssertionError`` whose message is :func:`describe_diff` (no long excerpts)."""
    diff = diff_bytes(expected, actual)
    if diff is not None:
        raise AssertionError("\n".join([f"{what}: not byte-identical", *describe_diff(diff)]))


def assert_matches_sha256(data: bytes, expected_sha256: str, *, what: str = "bytes") -> None:
    """Assert ``sha256(data)`` equals ``expected_sha256`` (hex); the message carries both digests and no content."""
    got = sha256_hex(data)
    if got != expected_sha256:
        raise AssertionError(f"{what}: sha256 {got} != expected {expected_sha256} ({len(data)} bytes)")


# ---------------------------------------------------------------------------------------------------- pytest hook


def _as_bytes(value: object) -> bytes | None:
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8", "surrogatepass")
    return None


def assertrepr_compare(op: str, left: object, right: object) -> list[str] | None:
    """Body of ``pytest_assertrepr_compare``: no ``str`` or ``bytes`` operand reaches test output unescaped (K.3.4(8)).

    ``None`` (pytest's default report) when neither operand is a ``str`` or ``bytes``. Otherwise the report carries
    types, lengths and sha256 values; for ``==`` on two ``str``/``bytes`` operands it adds the first-difference report
    of :func:`describe_diff`. Strings nested in containers are not intercepted (pytest's default report applies).
    """
    left_bytes, right_bytes = _as_bytes(left), _as_bytes(right)
    if left_bytes is None and right_bytes is None:
        return None

    def summary(value: object, data: bytes | None) -> str:
        if data is None:
            return f"<{type(value).__name__}>"
        return f"<{type(value).__name__} {len(data)} bytes sha256 {sha256_hex(data)[:16]}>"

    lines = [f"{summary(left, left_bytes)} {op} {summary(right, right_bytes)}"]
    if left_bytes is not None and right_bytes is not None and op == "==":
        diff = diff_bytes(left_bytes, right_bytes)
        if diff is not None:
            lines.extend(describe_diff(diff, expected="left", actual="right"))
        return lines
    for name, data in (("left", left_bytes), ("right", right_bytes)):
        if data is not None and op in ("in", "not in", "!=", "is", "is not"):
            lines.append(f"{name}: {_show(data.decode('utf-8', 'surrogateescape'))}")
    return lines
