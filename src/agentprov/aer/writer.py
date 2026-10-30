"""The AER writer: backward references, id uniqueness, canonical lines, accounting and the seal (C.2.1, C.11.6).

::

    writer = AerWriter(path, header, catalogues=registry)
    writer.add(record)           # raises AerWriteError at the first invalid record
    info = writer.seal(issues=[...], extra_checks=[...])

Every record is checked as it is added by the same validator that checks files (:class:`~agentprov.aer.validate.
AerValidator`, ``dev``-independent: findings that are errors in release mode are errors here), so a producer cannot
write what the validator would reject. Records are held as canonical lines in memory; nothing touches the disk
until :meth:`AerWriter.seal` succeeds, and then the file appears atomically (temporary sibling, ``fsync``,
rename), so a failed or abandoned writer leaves no partial file.

The writer does not resolve locators against the raw store (it has none); the write gate of D8 runs the store-aware
validator over the sealed file. It never writes a time, a host name, a path or a package version into a record
(C.11.7): the output bytes are a pure function of the records, issues and extra checks passed in.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentprov.aer import AER_VERSION
from agentprov.aer.accounting import Accounting, mirror_issues
from agentprov.aer.canon import CanonError, dumps_line
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.types import Json
from agentprov.aer.validate import AerValidator, Finding
from agentprov.errors import AgentProvError
from agentprov.io.atomic import atomic_write_bytes

__all__ = ["AerWriteError", "AerWriter", "SealInfo"]

class AerWriteError(AgentProvError):
    """A record, issue or sealing step is invalid; ``findings`` names the validator findings (never source text)."""

    code = "aer.write.invalid"

    def __init__(self, message: str, findings: Sequence[Finding] = ()) -> None:
        super().__init__(message)
        self.findings = tuple(findings)


@dataclass(frozen=True, slots=True)
class SealInfo:
    """What :meth:`AerWriter.seal` returns."""

    path: Path
    ex: str
    n_records: int
    execution_digest: str  # hex SHA-256 over every line before the seal (``aer_digest`` is ``"sha256:" + this``)
    file_sha256: str  # hex SHA-256 of the whole file: what ``checksums.sha256`` lists
    accounting: Accounting
    issues: tuple[dict[str, Json], ...]
    size: int


class AerWriter:
    """Builds one ``.aer.jsonl`` file. ``header`` is the ``execution`` record (line 0)."""

    def __init__(self, path: Path | str, header: Mapping[str, Any], *, catalogues: RuleRegistry) -> None:
        self._path = Path(path)
        self._validator = AerValidator(store=None, catalogues=catalogues, mode="release")
        self._lines: list[bytes] = []
        self._sealed = False
        self._failed = False
        if header.get("k") != "execution":
            raise AerWriteError("the first record must be the execution header")
        self._ex = str(header.get("ex"))
        # the format version is the core's, never an adapter's: every record this build seals is aer/0.2 (D-212)
        self._append({**dict(header), "aer": AER_VERSION})

    # ------------------------------------------------------------------------------------------ add
    def _append(self, record: dict[str, Any]) -> None:
        try:
            line = dumps_line(record)
        except CanonError as exc:
            self._failed = True
            raise AerWriteError("record cannot be canonicalised (encode source values with canon.encode_value)") from exc
        unresolved = self._validator.n_unresolved
        errors = [f for f in self._validator.feed_checked(line) if f.severity == "error"]
        if self._validator.n_unresolved != unresolved:
            self._failed = True
            raise AerWriteError("record names a later or unknown record: references must be backward-only (C.5.2)")
        if errors:
            self._failed = True
            raise AerWriteError(f"record {len(self._lines)} is invalid: {', '.join(sorted({f.code for f in errors}))}", errors)
        self._lines.append(line)

    def add(self, record: Mapping[str, Any]) -> None:
        """Append one record after the header. Raises :class:`AerWriteError` when it is invalid in context.

        After a failure the writer is unusable (its validator has consumed the bad record): build a new one.
        """
        if self._sealed or self._failed:
            raise AerWriteError("the writer is sealed or failed")
        if record.get("k") in ("execution", "seal"):
            raise AerWriteError("the header is given to the constructor and the seal is written by seal()")
        self._append(dict(record))

    # ------------------------------------------------------------------------------------------ seal
    def seal(self, *, issues: Sequence[Mapping[str, Any]], extra_checks: Sequence[Mapping[str, Json]] = ()) -> SealInfo:
        """Compute accounting, mirror non-consistent verdicts as issues, write the seal and the file atomically.

        ``issues`` are the mapper's seal issues (order kept). One mirrored issue per ``inconsistent`` or
        ``unverifiable`` check (``accounting_<verdict>`` citing the check, C.12.3) is appended unless an equal
        issue is already present. ``extra_checks`` are profile or live checks computed by the mapper; they are
        recorded after the core checks, in the order given, and take part in the status fold.
        """
        if self._sealed or self._failed:
            raise AerWriteError("the writer is sealed or failed")
        given = [dict(i) for i in issues]
        accounting = self._validator.accounting_so_far(given, extra_checks)
        have = {_issue_key(i) for i in given}
        for mirror in mirror_issues(accounting):
            if _issue_key(mirror) not in have:
                given.append(dict(mirror))
                have.add(_issue_key(mirror))
        body = b"".join(self._lines)
        seal: dict[str, Any] = {
            "k": "seal",
            "id": "seal",
            "n_records": len(self._lines) + 1,
            "records_sha256": hashlib.sha256(body).hexdigest(),
            "accounting": accounting.to_json(),
            "issues": given,
        }
        blobs = list(self._validator.blob_digests)
        if blobs:
            seal["blobs"] = blobs
        try:
            line = dumps_line(seal)
        except CanonError as exc:
            raise AerWriteError("the seal cannot be canonicalised") from exc
        self._validator.feed(line)
        errors = list(self._validator.finish().errors)
        if errors:
            raise AerWriteError(f"the sealed record set is invalid: {', '.join(sorted({f.code for f in errors}))}", errors)
        data = body + line
        atomic_write_bytes(self._path, data)
        self._sealed = True
        return SealInfo(
            path=self._path,
            ex=self._ex,
            n_records=len(self._lines) + 1,
            execution_digest=str(seal["records_sha256"]),
            file_sha256=hashlib.sha256(data).hexdigest(),
            accounting=accounting,
            issues=tuple(given),
            size=len(data),
        )


def _issue_key(issue: Mapping[str, Any]) -> tuple[object, object, tuple[object, ...]]:
    ids = issue.get("ids")
    return issue.get("code"), issue.get("rule"), tuple(ids) if isinstance(ids, list) else ()

