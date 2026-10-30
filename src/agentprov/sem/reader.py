"""Reader of ``.sem.jsonl`` files with seal verification (C.14.1; same line rules as AER, C.2.1 and C.11).

The reader is as strict as :mod:`agentprov.aer.reader`, whose line helpers it reuses: binary mode, LF framing, every
line parsed by the bounded strict loader (``agentprov.ingest.loaders`` via :func:`agentprov.aer.canon.loads_strict`)
and required to equal its own canonical JCS serialisation, at most 16 MiB per line. Line 0 is the ``k: "sem"`` header,
the last line the ``seal``, every other line a ``k: "ann"`` record with an ``id`` and a ``target``. With
``verify=True`` the seal's ``n_records`` (lines including the seal, C.11.6) and ``records_sha256`` (SHA-256 over every
line before the seal: the SEM digest of the D9 chain) are recomputed.

Framing, parsing and canonical-form failures, and a header without the members the :class:`SemDocument` accessors
read (``ex`` and ``aer_digest`` strings, a ``profile`` object with a string ``id`` and an integer ``version``), raise
:class:`SemFormatError` (``sem.format``); a seal mismatch raises :class:`SemIntegrityError` (``sem.seal.count`` or
``sem.seal.digest``). Everything else C.14.4 requires (closed header, member patterns, targets, values, rules, the
AER binding) is the validator's (:mod:`agentprov.sem.validate`). Messages carry line
numbers and fixed labels only, never file text (G.8.1).
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

from agentprov.aer.reader import AerFormatError, _parse_line
from agentprov.aer.validate import MAX_LINE_BYTES, iter_lines
from agentprov.errors import AgentProvError
from agentprov.sem.types import SemDocument

__all__ = ["SemFormatError", "SemIntegrityError", "load_sem", "load_sem_bytes"]


class SemFormatError(AgentProvError):
    """The file is not a well-formed SEM file (framing, strict parse, canonical form, record kinds and order)."""

    code = "sem.format"
    exit_code = 1


class SemIntegrityError(AgentProvError):
    """The seal does not match the file (``sem.seal.count`` or ``sem.seal.digest``)."""

    code = "sem.seal.digest"
    exit_code = 1


def _line_record(line: bytes, index: int) -> dict[str, Any]:
    try:
        return _parse_line(line, index)
    except AerFormatError as exc:  # same rules as AER (C.14.1); re-typed so callers see one SEM error family
        raise SemFormatError(str(exc)) from None


def _check_header_members(header: dict[str, Any]) -> None:
    """The members the SemDocument accessors read; closedness and patterns stay the validator's (C.14.4)."""
    profile = header.get("profile")
    if not (
        isinstance(header.get("ex"), str)
        and isinstance(header.get("aer_digest"), str)
        and isinstance(profile, dict)
        and isinstance(profile.get("id"), str)
        and isinstance(profile.get("version"), int)
        and not isinstance(profile.get("version"), bool)
    ):
        raise SemFormatError("line 0: the sem header lacks a well-formed ex, aer_digest or profile")


def load_sem(path: Path | str, *, verify: bool = True) -> SemDocument:
    """Read and (by default) verify a whole ``.sem.jsonl`` file; see the module docstring for the failures."""
    return load_sem_bytes(Path(path).read_bytes(), verify=verify)


def load_sem_bytes(data: bytes, *, verify: bool = True) -> SemDocument:
    """:func:`load_sem` over the bytes of a file (a worker job reads its input by digest)."""
    records: list[dict[str, Any]] = []
    hasher = hashlib.sha256()
    seal: dict[str, Any] | None = None
    for index, (line, oversize) in enumerate(iter_lines(io.BytesIO(data))):
        if oversize or len(line) > MAX_LINE_BYTES:
            raise SemFormatError(f"line {index}: longer than {MAX_LINE_BYTES} bytes")
        record = _line_record(line, index)
        if seal is not None:
            raise SemFormatError(f"line {index - 1}: seal is not the last line")
        kind = record.get("k")
        if index == 0:
            if kind != "sem":
                raise SemFormatError("line 0 is not the sem header")
            _check_header_members(record)
        elif kind == "seal":
            seal = record
            continue
        elif kind != "ann":
            raise SemFormatError(f"line {index}: not an annotation record")
        elif "id" not in record or "target" not in record:
            raise SemFormatError(f"line {index}: annotation without id or target")
        hasher.update(line)
        records.append(record)
    if seal is None or not records:
        raise SemFormatError("a SEM file has a header and a seal")
    count = len(records) + 1
    digest = hasher.hexdigest()
    if verify:
        if seal.get("n_records") != count:
            raise SemIntegrityError("seal.n_records differs from the line count", code="sem.seal.count")
        if seal.get("records_sha256") != digest:
            raise SemIntegrityError("seal.records_sha256 differs from the SEM digest", code="sem.seal.digest")
    return SemDocument(
        header=records[0],
        records=records,
        seal=seal,
        digest=digest,
        file_sha256=hashlib.sha256(data).hexdigest(),
    )
