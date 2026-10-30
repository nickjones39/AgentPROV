"""Tier-1 limits (docs/architecture G.3.2).

``IngestLimits()`` carries the defaults of G.3.2. Every effective value is recorded in ``corpus.json`` (MN N.2.2) and in
the import report: :meth:`IngestLimits.to_json` gives the full record and :meth:`IngestLimits.overrides` the fields that
differ from the defaults (a value above its default MUST be passed explicitly and is recorded as an override).

Tests read limits from this object and probe ``limit - 1``, ``limit`` and ``limit + 1`` (K.5.6); they never hard-code
a value.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

KIB: Final = 1024
MIB: Final = 1024 * KIB
GIB: Final = 1024 * MIB

#: ZIP compression methods that may be decompressed: stored, deflate, zstd (G.3.5; AD-06 `.eval` uses 93).
DEFAULT_ZIP_METHODS: Final[frozenset[int]] = frozenset({0, 8, 93})

#: Fixed absolute ceilings of the per-pattern raises a source profile may declare for a nested archive (``[import]
#: nested``, D-382). They are constants, not :class:`IngestLimits` fields: the global limits never change, and a raise
#: applies only to the members that match its pattern. ``NESTED_MAX_DEPTH`` is the deepest observed shape (a split zip
#: or ``tar.zst``, a zip inside it, an ``.eval`` inside that); ``NESTED_MAX_MEMBER_BYTES`` is the default
#: ``max_artefact_bytes``, because a nested archive is stored as one raw object (D-381 (a)); ``NESTED_MAX_RATIO`` sits
#: just under deflate's own limit of about 1,032.
NESTED_MAX_DEPTH: Final = 3
NESTED_MAX_MEMBER_BYTES: Final = 2 * GIB
NESTED_MAX_RATIO: Final = 1_000
#: The keys a nested-archive declaration may raise. A raise is scoped to one pattern; the profile-wide ``[import] limits``
#: allowlist (D-323) must stay disjoint from these, so a nested raise can never become a global one.
NESTED_RAISE_FIELDS: Final = frozenset({"max_member_bytes", "max_ratio", "max_depth"})


@dataclass(frozen=True, slots=True)
class IngestLimits:
    """The tier-1 resource limits of G.3.2. Immutable; use :meth:`replace` to derive an override."""

    max_artefact_bytes: int = 2 * GIB  # ingest.size.file
    max_json_bytes: int = 64 * MIB  # one JSON document; ingest.size.file
    max_jsonl_line_bytes: int = 16 * MIB  # ingest.size.record (JSON record) / ingest.jsonl.line_too_long (line)
    max_json_depth: int = 256  # A2; ingest.json.depth. Depth counts container nesting; a scalar has depth 0
    max_int_digits: int = 1_000  # ingest.number.digits
    max_stream_bytes: int = 1 * GIB  # deferred codecs; ingest.stream.size
    max_tar_stream_bytes: int = 16 * GIB  # one decompressed tar stream, gzip or zstd (D-241); ingest.stream.size
    max_zstd_frames: int = 1_024  # frames in one zstd stream (D-240); ingest.stream.codec
    max_pax_header_bytes: int = 64 * KIB  # one pax `x` extended header in a tar (D-248); ingest.archive.format
    max_ratio: float = 200  # ingest.stream.ratio / ingest.archive.ratio
    ratio_floor_bytes: int = 1 * MIB  # the ratio is checked only above this size
    max_member_bytes: int = 256 * MIB  # ingest.archive.size
    max_total_bytes: int = 4 * GIB  # one archive; ingest.archive.size
    max_members: int = 100_000  # ingest.archive.members
    max_cd_bytes: int = 32 * MIB  # ingest.archive.cd
    max_archive_depth: int = 2  # ingest.archive.depth (top-level container is depth 1)
    zip_methods: frozenset[int] = field(default=DEFAULT_ZIP_METHODS)  # ingest.archive.method
    max_name_bytes: int = 1_024  # ingest.name.invalid; checked before NFC normalisation
    max_component_bytes: int = 255
    xz_memlimit: int = 256 * MIB  # deferred codecs; ingest.stream.memory
    zstd_window_log_max: int = 27  # 128 MiB window: zstd tar streams (D-240) and the deferred single-stream codec
    max_json_stream_bytes: int = 1 * GIB  # one JSON document read by declared-array streaming (D-242); ingest.size.file
    max_json_element_bytes: int = 16 * MIB  # one streamed element, and the envelope (D-242); ingest.size.record
    max_json_elements: int = 1_000_000  # streamed elements in one document (D-242); ingest.json.elements
    #: parts of one archive stored as byte parts (D-243); ingest.archive.parts. 32 parts of 256 MiB are max_split_bytes;
    #: the expand worker holds every part open, so this stays well under its RLIMIT_NOFILE of 64 (BF-15, D-461)
    max_split_parts: int = 32
    max_split_bytes: int = 8 * GIB  # logical size of an archive stored as byte parts (D-243); ingest.archive.parts
    max_yaml_bytes: int = 1 * MIB  # YAML tool outputs (marker normaliser); aliases rejected
    max_csv_field_bytes: int = 1 * MIB  # deferred (AD-10 row 16); ingest.csv.field
    max_literal_bytes: int = 1 * MIB  # deferred (AD-10 row 16); ingest.literal.size
    display_chars: int = 500  # quote_untrusted excerpt, characters per field (MN N.1.13 --max-chars)

    def __post_init__(self) -> None:
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if f.name == "zip_methods":
                methods = frozenset(value)
                if not methods or not all(isinstance(m, int) and not isinstance(m, bool) for m in methods):
                    raise ValueError("zip_methods must be a non-empty set of integers")
                object.__setattr__(self, "zip_methods", methods)
            elif f.name == "max_ratio":
                if isinstance(value, bool) or not isinstance(value, int | float) or not 0 < value < math.inf:
                    raise ValueError("max_ratio must be a positive finite number")  # NaN or inf would open the gate
            elif isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{f.name} must be a positive integer")

    def replace(self, **changes: Any) -> IngestLimits:
        """A copy with ``changes`` applied (validated again)."""
        return dataclasses.replace(self, **changes)

    def to_json(self) -> dict[str, Any]:
        """Every effective value, JSON-serialisable and in field order (recorded in ``corpus.json``)."""
        out: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            out[f.name] = sorted(value) if f.name == "zip_methods" else value
        return out

    def overrides(self) -> dict[str, Any]:
        """The fields whose value differs from the G.3.2 default (recorded as overrides)."""
        default = IngestLimits().to_json()
        return {k: v for k, v in self.to_json().items() if v != default[k]}


@dataclass(frozen=True, slots=True)
class NestedRaises:
    """The raises of one nested-archive pattern (D-382); ``None`` keeps the global value.

    ``max_member_bytes`` and ``max_ratio`` apply to the gate of a member that matches the pattern, as a member of its
    parent; ``max_depth`` is the deepest archive level that may be opened at or below that member. Build it with
    :func:`nested_raises`, which enforces raise-only values under the fixed ceilings.
    """

    max_member_bytes: int | None = None
    max_ratio: float | None = None
    max_depth: int | None = None

    def to_json(self) -> dict[str, Any]:
        """The declared raises only (the absent ones are not recorded), in field order."""
        return {f.name: getattr(self, f.name) for f in dataclasses.fields(self) if getattr(self, f.name) is not None}

    def member_bytes(self, limits: IngestLimits) -> int:
        return limits.max_member_bytes if self.max_member_bytes is None else max(self.max_member_bytes, limits.max_member_bytes)

    def ratio(self, limits: IngestLimits) -> float:
        return limits.max_ratio if self.max_ratio is None else max(self.max_ratio, limits.max_ratio)


def nested_raises(table: Mapping[str, Any], defaults: IngestLimits | None = None) -> NestedRaises:
    """Validate the raises of one ``[[import.nested]]`` entry (D-382); ``ValueError`` on any defect.

    Only :data:`NESTED_RAISE_FIELDS` are read from ``table`` (the caller checks the entry's other keys). Each value must
    be an integer (``max_ratio`` may be a number), at least the global default (``max_depth`` against
    ``max_archive_depth``) and at most its fixed ceiling. A value equal to the default is accepted and has no effect.
    """
    base = defaults or IngestLimits()
    values: dict[str, Any] = {}
    bounds: dict[str, tuple[float, float]] = {
        "max_member_bytes": (base.max_member_bytes, NESTED_MAX_MEMBER_BYTES),
        "max_ratio": (base.max_ratio, NESTED_MAX_RATIO),
        "max_depth": (base.max_archive_depth, NESTED_MAX_DEPTH),
    }
    for name in sorted(NESTED_RAISE_FIELDS & set(table)):
        value = table[name]
        number = int | float if name == "max_ratio" else int
        if isinstance(value, bool) or not isinstance(value, number) or not math.isfinite(value):
            raise ValueError(f"nested {name} must be {'a finite number' if name == 'max_ratio' else 'an integer'}")
        low, high = bounds[name]
        if value < low:
            raise ValueError(f"nested {name} {value} is below the global value {low}: a nested declaration only raises")
        if value > high:
            raise ValueError(f"nested {name} {value} is above its fixed ceiling {high}")
        values[name] = value
    return NestedRaises(**values)


def depth_limit(limits: IngestLimits, max_depth: int | None) -> int:
    """The archive level that may be opened: the global ``max_archive_depth``, or a declared allowance (D-382), never
    above :data:`NESTED_MAX_DEPTH` and never below the global value."""
    if max_depth is None:
        return limits.max_archive_depth
    return max(limits.max_archive_depth, min(max_depth, NESTED_MAX_DEPTH))


#: D-935: the JSON size limit for a stored PROV-JSON document (engine output, also read from a downloaded corpus). PROV grows
#: with the square of an execution's model calls (context membership and exposure pairs), so a long run's document can pass
#: the 64 MiB raw-input limit; the parse stays bounded (strict loader, depth and digit limits unchanged).
PROV_DOCUMENT_JSON_BYTES: Final = 256 * MIB


def prov_document_limits(limits: IngestLimits | None = None) -> IngestLimits:
    """``limits`` (default: the defaults) with ``max_json_bytes`` at least :data:`PROV_DOCUMENT_JSON_BYTES` (D-935): the
    limits for parsing one stored PROV-JSON document, never for raw source input."""
    base = limits or IngestLimits()
    return dataclasses.replace(base, max_json_bytes=max(base.max_json_bytes, PROV_DOCUMENT_JSON_BYTES))
