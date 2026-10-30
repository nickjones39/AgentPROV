"""Streaming reader of ``.aer.jsonl`` files with seal verification and a record index (C.2.1, C.11.6).

The reader trusts nothing it is given: every line is parsed strictly (via ``agentprov.ingest.loaders``), must be
the canonical JCS serialisation of itself, and the seal's ``n_records`` and ``records_sha256`` are recomputed.
A file that fails any of these raises :class:`AerFormatError` (framing, parsing, canonical form) or
:class:`AerIntegrityError` (count or digest). It reads in binary mode and splits on LF only, so the bytes it
verifies are exactly the bytes on disk on every host.

Use :func:`iter_records` to stream, :func:`load_aer` for the header, records, seal and an id/part index, and
:func:`read_header` / :func:`read_seal` to look at the ends of a file without verifying the middle (the corpus
index uses them; ``verify`` and the validator are the places that check everything).
"""

from __future__ import annotations

import hashlib
import io
import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from agentprov.aer.canon import CanonError, dumps_line, loads_strict
from agentprov.aer.validate import MAX_LINE_BYTES, iter_lines
from agentprov.errors import AgentProvError

__all__ = [
    "AerDocument",
    "AerFormatError",
    "AerIntegrityError",
    "iter_records",
    "load_aer",
    "load_aer_bytes",
    "read_header",
    "read_seal",
]


class AerFormatError(AgentProvError):
    """The file is not a well-formed AER file (framing, strict parse, canonical form, record order)."""

    code = "aer.format"
    exit_code = 1


class AerIntegrityError(AgentProvError):
    """The seal does not match the file (``aer.seal.count`` or ``aer.seal.digest``)."""

    code = "aer.seal.digest"
    exit_code = 1


@dataclass(slots=True)
class AerDocument:
    """A fully read and verified AER file."""

    header: dict[str, Any]
    records: list[dict[str, Any]]  # header .. last record before the seal, in file order
    seal: dict[str, Any]
    execution_digest: str  # hex SHA-256 over every line before the seal
    file_sha256: str  # hex SHA-256 of the whole file
    _index: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)

    def get(self, record_id: str) -> dict[str, Any] | None:
        """The record with local id ``record_id`` (header ``exec`` included), or ``None``."""
        return self._index.get(record_id)

    def part(self, part_id: str) -> dict[str, Any] | None:
        """The message part addressed by ``<message id>#<k>``, or ``None``."""
        base, _, ordinal = part_id.partition("#")
        message = self._index.get(base)
        if (message is None or message.get("k") != "message" or not (ordinal.isascii() and ordinal.isdigit())
                or len(ordinal) > 18):  # more than 18 digits: out of range (split_part_id)
            return None
        parts = message.get("parts")
        k = int(ordinal)
        return parts[k] if isinstance(parts, list) and k < len(parts) and isinstance(parts[k], dict) else None

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r.get("k") == kind]

    @property
    def ex(self) -> str:
        return str(self.header["ex"])


def _parse_line(line: bytes, index: int) -> dict[str, Any]:
    if not line.endswith(b"\n"):
        raise AerFormatError(f"line {index}: missing final LF")
    body = line[:-1]
    if body.endswith(b"\r") or body == b"":
        raise AerFormatError(f"line {index}: CR or blank line")
    try:
        record = loads_strict(body)
    except CanonError as exc:
        raise AerFormatError(f"line {index}: strict parse failed ({exc.code})") from None
    if not isinstance(record, dict):
        raise AerFormatError(f"line {index}: not a JSON object")
    try:
        canonical = dumps_line(record)
    except CanonError:
        raise AerFormatError(f"line {index}: not representable in JCS") from None
    if canonical != line:
        raise AerFormatError(f"line {index}: not in canonical (JCS) form")
    return record


def _open_lines(stream: IO[bytes]) -> Iterator[tuple[int, bytes]]:
    for index, (line, oversize) in enumerate(iter_lines(stream)):
        if oversize or len(line) > MAX_LINE_BYTES:
            raise AerFormatError(f"line {index}: longer than {MAX_LINE_BYTES} bytes")
        yield index, line


def iter_records(path: Path | str, *, verify: bool = True) -> Iterator[dict[str, Any]]:
    """Yield every record of the file in order, header first and seal last.

    With ``verify=True`` (default) the seal's count and digest are checked before the seal record is yielded; a
    mismatch raises :class:`AerIntegrityError` there. Records before the seal are yielded as they are read, so a
    consumer that needs verified data only must consume the generator to its end (``load_aer`` does).
    """
    with open(path, "rb") as stream:
        yield from _iter_stream(stream, verify=verify)


def _iter_stream(stream: IO[bytes], *, verify: bool) -> Iterator[dict[str, Any]]:
    """The body of :func:`iter_records` over an open binary stream (a file, or the bytes of :func:`load_aer_bytes`)."""
    hasher = hashlib.sha256()
    pending: tuple[int, bytes, dict[str, Any]] | None = None
    count = 0
    first = True
    for index, line in _open_lines(stream):
        record = _parse_line(line, index)
        count += 1
        if first:
            if record.get("k") != "execution":
                raise AerFormatError("line 0 is not the execution record")
            first = False
        if pending is not None:
            if pending[2].get("k") == "seal":
                raise AerFormatError(f"line {pending[0]}: seal is not the last line")
            hasher.update(pending[1])
            yield pending[2]
        pending = (index, line, record)
    if pending is None or count < 2:
        raise AerFormatError("an AER file has at least two lines")
    seal = pending[2]
    if seal.get("k") != "seal":
        raise AerFormatError("the last line is not the seal")
    if verify:
        _verify_seal(seal, count, hasher.hexdigest())
    yield seal


def _verify_seal(seal: Mapping[str, Any], count: int, digest: str) -> None:
    if seal.get("n_records") != count:
        raise AerIntegrityError("seal.n_records differs from the line count", code="aer.seal.count")
    if seal.get("records_sha256") != digest:
        raise AerIntegrityError("seal.records_sha256 differs from the execution digest", code="aer.seal.digest")


def load_aer(path: Path | str, *, verify: bool = True) -> AerDocument:
    """Read and (by default) verify a whole file; see the module docstring for the failures."""
    return load_aer_bytes(Path(path).read_bytes(), verify=verify)


def load_aer_bytes(data: bytes, *, verify: bool = True) -> AerDocument:
    """:func:`load_aer` over the bytes of a file (a T1 job reads its input by digest and may not write a file)."""
    records = list(_iter_stream(io.BytesIO(data), verify=verify))
    seal = records.pop()
    body_end = len(data) - len(dumps_line(seal))
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        rid = record.get("id")
        if isinstance(rid, str):
            if rid in index:
                raise AerFormatError("duplicate record id")
            index[rid] = record
    return AerDocument(
        header=records[0],
        records=records,
        seal=seal,
        execution_digest=hashlib.sha256(data[:body_end]).hexdigest(),
        file_sha256=hashlib.sha256(data).hexdigest(),
        _index=index,
    )


def read_header(path: Path | str) -> dict[str, Any]:
    """Line 0 (the ``execution`` record), parsed strictly; the rest of the file is not read or verified."""
    with open(path, "rb") as stream:
        line = stream.readline(MAX_LINE_BYTES + 2)
    record = _parse_line(line, 0)
    if record.get("k") != "execution":
        raise AerFormatError("line 0 is not the execution record")
    return record


def read_seal(path: Path | str) -> dict[str, Any]:
    """The last line (the ``seal`` record), found by reading back from the end; the middle is not verified."""
    with open(path, "rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        chunk = 4096
        while True:
            start = max(0, size - chunk)
            stream.seek(start)
            tail = stream.read(size - start)
            lines = tail.split(b"\n")
            if len(lines) >= 3 or start == 0:
                break
            chunk *= 4
    if not tail.endswith(b"\n"):
        raise AerFormatError("file does not end with LF")
    last = lines[-2] + b"\n"
    if len(lines) < 3 and start != 0:
        raise AerFormatError("seal line not found")
    record = _parse_line(last, -1)
    if record.get("k") != "seal":
        raise AerFormatError("the last line is not the seal")
    return record
