"""Typed errors with stable codes and CLI exit codes (docs/architecture: MN M.1.2, N.1.3; D.2.7; G.3.9).

* :class:`AgentProvError` is the base of every AgentPROV error: a stable dotted ``code`` and the CLI ``exit_code``.
* :class:`IngestError` (and its adapter-layer subclass :class:`IngestSafetyError`) carries one code of the closed
  ``ingest.<area>.<kind>`` registry of G.3.9 (:data:`INGEST_CODES`). Tier-1 loaders raise nothing else on hostile
  input (K.11.1 F-1).
* :class:`AdapterError` and its subclasses follow D.2.7.
* :class:`Issue` is the adapter-layer issue record of D.2.7. It is defined here, next to the error hierarchy, as
  MN M.1.2 lists it; ``agentprov.adapters.types`` re-exports it so that ``agentprov.adapters.types.Issue`` (D.2.7)
  names the same class.

Exception messages never carry raw source text (D.2.7): tier-1 code reports lengths, offsets, limits and codes only.
Callers that need to show a source string quote it through ``agentprov.ingest.quote``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Final, Literal


class AgentProvError(Exception):
    """Base of every AgentPROV error: a stable dotted ``code`` and the CLI ``exit_code`` (N.1.3)."""

    code: str = "internal"
    exit_code: int = 70

    def __init__(self, message: str, *, code: str | None = None, exit_code: int | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if exit_code is not None:
            self.exit_code = exit_code


# --------------------------------------------------------------------------------------------------------------
# Tier-1 ingest errors (G.3.9)
# --------------------------------------------------------------------------------------------------------------

#: The closed ``ingest.<area>.<kind>`` registry of G.3.9. ``ingest.stream.*`` other than ``codec`` and the two
#: dialect codes ``ingest.csv.field`` / ``ingest.literal.size`` are reserved for deferred codecs and dialects.
INGEST_CODES: Final[frozenset[str]] = frozenset(
    {
        "ingest.size.file",
        "ingest.size.record",
        "ingest.stream.codec",
        "ingest.stream.size",
        "ingest.stream.ratio",
        "ingest.stream.memory",
        "ingest.stream.truncated",
        "ingest.json.syntax",
        "ingest.json.encoding",
        "ingest.json.bom",
        "ingest.json.duplicate_key",
        "ingest.json.depth",
        "ingest.json.lone_surrogate",
        "ingest.json.elements",
        "ingest.number.digits",
        "ingest.number.nonfinite",
        "ingest.jsonl.crlf",
        "ingest.jsonl.blank",
        "ingest.jsonl.nul",
        "ingest.jsonl.no_final_newline",
        "ingest.jsonl.line_too_long",
        "ingest.archive.format",
        "ingest.archive.cd",
        "ingest.archive.prefix",
        "ingest.archive.trailing",
        "ingest.archive.overlap",
        "ingest.archive.members",
        "ingest.archive.size",
        "ingest.archive.ratio",
        "ingest.archive.depth",
        "ingest.archive.traversal",
        "ingest.archive.link",
        "ingest.archive.duplicate",
        "ingest.archive.encrypted",
        "ingest.archive.method",
        "ingest.archive.crc",
        "ingest.archive.parts",
        "ingest.name.invalid",
        "ingest.name.colon",
        "ingest.path.symlink",
        "ingest.path.hardlink",
        "ingest.path.special",
        "ingest.path.duplicate",
        "ingest.path.unsupported_platform",
        "ingest.yaml.alias",
        "ingest.csv.field",
        "ingest.literal.size",
        "ingest.interpreter.unpatched",
    }
)

#: CLI exit code per ingest code where it differs from the default 1 (``failures``): tar and other refused archive
#: formats are ``unsupported`` (5; G.3.5), release-mode interpreter refusal and a host without the no-follow primitives are ``environment`` (3; G.3.8, C-1).
_INGEST_EXIT_CODES: Final[Mapping[str, int]] = {
    "ingest.archive.format": 5,
    "ingest.interpreter.unpatched": 3,
    "ingest.path.unsupported_platform": 3,
}

Severity = Literal["info", "warning", "error"]


class IngestError(AgentProvError):
    """A tier-1 violation: carries one code of :data:`INGEST_CODES` (G.3.9; K.11.1 F-1).

    ``line`` (0-based) and ``offset`` (byte offset) are the locator of the defect when one exists; ``limit`` is the
    effective limit that was exceeded. The message never contains source text.
    """

    exit_code = 1

    def __init__(
        self,
        code: str,
        message: str,
        *,
        line: int | None = None,
        offset: int | None = None,
        limit: int | float | None = None,
        exit_code: int | None = None,
    ) -> None:
        if code not in INGEST_CODES:
            raise ValueError(f"unknown ingest code: {code!r}")  # a programming error, never source-derived
        super().__init__(
            f"{code}: {message}",
            code=code,
            exit_code=_INGEST_EXIT_CODES.get(code, 1) if exit_code is None else exit_code,
        )
        self.reason = message
        self.line = line
        self.offset = offset
        self.limit = limit

    def to_json(self) -> dict[str, Any]:
        """The register-row shape: code, locator and effective limit (no source text)."""
        out: dict[str, Any] = {"code": self.code}
        if self.line is not None:
            out["line"] = self.line
        if self.offset is not None:
            out["offset"] = self.offset
        if self.limit is not None:
            out["limit"] = self.limit
        return out


class IngestSafetyError(IngestError):
    """Adapter-layer subclass of :class:`IngestError`, raised inside readers (D.2.7; G.11 item 5)."""


@dataclass(frozen=True, slots=True)
class IngestFinding:
    """A recorded, non-raising tier-1 observation (G.3.3: findings, per-line JSONL issues, G.3.5: trailing data).

    ``detail`` is machine-oriented static text and never contains source text.
    """

    code: str
    severity: Severity = "warning"
    line: int | None = None
    offset: int | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.code not in INGEST_CODES:
            raise ValueError(f"unknown ingest code: {self.code!r}")

    def to_error(self) -> IngestError:
        return IngestError(self.code, self.detail or "recorded finding", line=self.line, offset=self.offset)


# --------------------------------------------------------------------------------------------------------------
# Adapter layer (D.2.7)
# --------------------------------------------------------------------------------------------------------------


class AdapterError(AgentProvError):
    """Base of the adapter-layer errors (D.2.7). ``code`` is a stable machine code; the exit code is per class."""

    code = "adapter.error"
    exit_code = 1
    #: the seal-issue code (C.12.3) a per-unit subclass maps to, where one exists
    seal_issue: ClassVar[str | None] = None


class ProfileError(AdapterError):
    """Invalid profile, catalogue or registry (package data). Exit 70."""

    code = "adapter.profile"
    exit_code = 70


class RuleNotDeclared(ProfileError):
    """A mapper cited a rule absent from the catalogue: a programming error. Exit 70."""

    code = "adapter.rule_not_declared"


class MalformedArtefact(AdapterError):
    """Sniffed as this dialect but unparseable (invalid JSON, wrong types). Seal issue ``unparseable_artefact``."""

    code = "adapter.malformed_artefact"
    seal_issue = "unparseable_artefact"


class UnsupportedVariant(AdapterError):
    """Recognised family, unsupported variant (for example AgentDojo ``pre_v0`` dev logs)."""

    code = "adapter.unsupported_variant"
    seal_issue = "unsupported_variant"


class AdapterDefect(AdapterError):
    """Wrapper for any unexpected exception raised inside ``Mapper.map``."""

    code = "adapter.defect"
    seal_issue = "adapter_defect"


class BackendUnavailable(AdapterError):
    """Backend environment not built or unverifiable. Exit 3."""

    code = "adapter.backend_unavailable"
    exit_code = 3


class IdentityMismatch(AdapterError):
    """Built environment differs from the pinned identity (D.10.6). Exit 3."""

    code = "adapter.identity_mismatch"
    exit_code = 3


class UnsupportedConfiguration(AdapterError):
    """Live configuration the backend cannot capture faithfully (for example a defence). Exit 5."""

    code = "adapter.unsupported_configuration"
    exit_code = 5


@dataclass(frozen=True, slots=True)
class Issue:
    """An adapter-layer issue (D.2.7).

    ``code`` is a seal-issue code of C.12.3 or ``"<ns>.<code>"`` declared in the catalogue. ``detail`` is short,
    machine-oriented text and MUST NOT copy source text: source strings are referenced by id and locator only.
    """

    code: str
    ids: tuple[str, ...] = ()
    rule: str | None = None
    severity: Severity = "warning"
    detail: str | None = None
