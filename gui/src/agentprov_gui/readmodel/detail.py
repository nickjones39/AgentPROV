"""One execution's documents (design §2.3 ``ExecutionDetail``, §3 "Read"). No Qt here.

Everything goes through the core's strict, digest-checking reader: the row is the fully checked
:class:`~agentprov.corpus.index.IndexRow` (:func:`agentprov_gui.readmodel.executions.read_row`); the AER is read with its
seal and execution digest checked against the row; each SEM document with its digest; each PROV file with its sha256
(the D9 chain). A document that fails is reported by its closed error code and the others still load.

**Validation and register rows** are looked up for this ``ex`` only. ``validation/results.jsonl`` is sorted by ``ex``
and ``register.jsonl`` by ``(subject_key, code)``, where an execution's ``subject_key`` is its ``ex``, so both are
binary-searched (a few strict line parses) instead of decoded whole (2.5 s and 25 s on agentdyn-a-p10, measured
2026-10-14). The validation row's bytes must hash to the index's ``digests.validation``; the register rows are decoded
by the core's :func:`~agentprov.corpus.register.decode_register` (strict, canonical, sorted).
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import IO, Any, Final

from agentprov.aer.reader import AerDocument
from agentprov.corpus.index import IndexRow
from agentprov.corpus.layout import REGISTER
from agentprov.corpus.reader import CorpusReader
from agentprov.corpus.register import RegisterEntry, decode_register
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.sem.types import SemDocument

__all__ = ["DetailCache", "ExecutionDetail", "load_detail", "lookup_sorted_lines"]

VALIDATION: Final = "validation/results.jsonl"


@dataclass(slots=True)
class ExecutionDetail:
    """The documents of one execution. ``errors`` maps a part (``aer``, ``sem:<profile>``, ``prov:<spec>``,
    ``validation``, ``register``) to a closed error code; a part with an error is absent."""

    ex: str
    row: IndexRow
    aer: AerDocument | None = None
    sem: dict[str, SemDocument] = field(default_factory=dict)
    prov: dict[str, Any] = field(default_factory=dict)  # spec -> parsed PROV-JSON
    prov_text: dict[str, str] = field(default_factory=dict)  # spec -> the file's text (UTF-8, as stored)
    prov_size: dict[str, int] = field(default_factory=dict)
    validation: dict[str, Any] | None = None
    register: list[RegisterEntry] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    size_bytes: int = 0  # approximate memory weight, for the LRU


def _read_line_at(stream: IO[bytes], pos: int, cap: int) -> tuple[int, bytes]:
    """The first complete line starting at or after ``pos`` and its offset (``b""`` at EOF)."""
    if pos == 0:
        stream.seek(0)
        return 0, stream.readline(cap)
    stream.seek(pos - 1)
    if stream.read(1) != b"\n":
        stream.readline(cap)  # skip the rest of the line we landed in
    start = stream.tell()
    return start, stream.readline(cap)


def lookup_sorted_lines(
    stream: IO[bytes],
    size: int,
    target: str,
    key_of: Callable[[Any], str | None],
    limits: IngestLimits,
    *,
    max_lines: int = 10_000,
) -> list[bytes]:
    """Every line (with its LF) whose key equals ``target`` in a JSONL file sorted bytewise by that key.

    Each probed line is parsed strictly; ``key_of`` maps the parsed value to its key. Raises
    :class:`~agentprov.errors.IngestError` for a line that is not strict JSON or not LF-terminated.
    """
    cap = limits.max_jsonl_line_bytes + 2
    want = target.encode("utf-8")

    def key_at(line: bytes) -> bytes:
        if not line.endswith(b"\n"):
            raise IngestError("ingest.jsonl.line_too_long", "a line has no final LF or exceeds the limit")
        key = key_of(strict_json_loads(line[:-1], limits, record=True))
        return (key or "").encode("utf-8")

    lo, hi = 0, size  # invariant: the first line with key >= target starts in [lo, hi]
    while lo < hi:
        mid = (lo + hi) // 2
        start, line = _read_line_at(stream, mid, cap)
        if not line or key_at(line) >= want:
            hi = mid
        else:
            lo = start + len(line)
    start, line = _read_line_at(stream, lo, cap)
    out: list[bytes] = []
    while line and key_at(line) == want:
        out.append(line)
        if len(out) >= max_lines:
            break
        line = stream.readline(cap)
    return out


def _size(reader: CorpusReader, label: str) -> int:
    import os

    return os.lstat(reader.root / label).st_size


def _validation_row(reader: CorpusReader, row: IndexRow) -> dict[str, Any] | None:
    if row.validation is None or row.validation.digest is None or not reader.exists(VALIDATION):
        return None
    with reader.open_file(VALIDATION) as stream:
        lines = lookup_sorted_lines(stream, _size(reader, VALIDATION), row.ex,
                                    lambda v: v.get("ex") if isinstance(v, dict) else None, reader.limits)
    if len(lines) != 1:
        raise AgentProvError("validation row missing or duplicated", code="gui.validation.lookup")
    body = lines[0][:-1]
    if hashlib.sha256(body).hexdigest() != row.validation.digest.removeprefix("sha256:"):
        raise AgentProvError("validation row differs from digests.validation", code="corpus.read.digest")
    value = strict_json_loads(body, reader.limits, record=True)
    if not isinstance(value, dict):
        raise AgentProvError("validation row is not an object", code="corpus.read.validation")
    return value


def _register_rows(reader: CorpusReader, ex: str) -> list[RegisterEntry]:
    if not reader.exists(REGISTER):
        return []
    with reader.open_file(REGISTER) as stream:
        lines = lookup_sorted_lines(stream, _size(reader, REGISTER), ex,
                                    lambda v: v.get("subject_key") if isinstance(v, dict) else None, reader.limits)
    return decode_register(b"".join(lines), reader.limits) if lines else []


def load_detail(reader: CorpusReader, row: IndexRow) -> ExecutionDetail:
    """Read every document of ``row`` (see the module docstring). Never raises for a bad document."""
    detail = ExecutionDetail(row.ex, row)
    weight = 0
    try:
        detail.aer = reader.read_aer(row)
        weight += len(reader.aer_bytes(row)) * 4
    except AgentProvError as exc:
        detail.errors["aer"] = exc.code
    for profile in sorted(row.sem_paths or {}):
        try:
            data, document = reader.read_sem_bytes(row, profile)
            detail.sem[profile] = document
            weight += len(data) * 4
        except AgentProvError as exc:
            detail.errors[f"sem:{profile}"] = exc.code
    for spec in sorted(row.prov_paths or {}):
        try:
            data = reader.prov_bytes(row, spec)
            detail.prov[spec] = strict_json_loads(data, reader.limits)
            detail.prov_text[spec] = data.decode("utf-8", "surrogateescape")
            detail.prov_size[spec] = len(data)
            weight += len(data) * 6
        except AgentProvError as exc:
            detail.errors[f"prov:{spec}"] = exc.code
    try:
        detail.validation = _validation_row(reader, row)
    except AgentProvError as exc:
        detail.errors["validation"] = exc.code
    try:
        detail.register = _register_rows(reader, row.ex)
    except AgentProvError as exc:
        detail.errors["register"] = exc.code
    detail.size_bytes = weight
    return detail


class DetailCache:
    """An LRU of parsed details: 64 entries or 256 MiB, whichever is reached first (design §2.4)."""

    def __init__(self, max_entries: int = 64, max_bytes: int = 256 * 1024 * 1024) -> None:
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self._items: OrderedDict[tuple[str, str], ExecutionDetail] = OrderedDict()
        self._bytes = 0

    def get(self, root: str, ex: str) -> ExecutionDetail | None:
        item = self._items.get((root, ex))
        if item is not None:
            self._items.move_to_end((root, ex))
        return item

    def put(self, root: str, detail: ExecutionDetail) -> None:
        key = (root, detail.ex)
        old = self._items.pop(key, None)
        if old is not None:
            self._bytes -= old.size_bytes
        self._items[key] = detail
        self._bytes += detail.size_bytes
        while self._items and (len(self._items) > self.max_entries or self._bytes > self.max_bytes):
            _, dropped = self._items.popitem(last=False)
            self._bytes -= dropped.size_bytes

    def clear(self) -> None:
        self._items.clear()
        self._bytes = 0
