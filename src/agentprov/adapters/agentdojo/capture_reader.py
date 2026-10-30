"""Reader of the live-capture dialect ``agentprov.capture`` variant ``0.1`` (docs/architecture C.13, D.10.0, D.10.4; layer L4).

A capture session is staged as a hash-chained JSONL event log, content-addressed blobs and the native TraceLogger JSON
the stock harness wrote beside it (C.13.1). After ingestion each of them is a raw object of its own (origin ``capture``);
this reader turns the objects of one session into one execution unit, exactly as the Inspect reader turns the member
objects of one container into units (D.9.1), so the runner's ``container`` map job dispatches it unchanged:

* :meth:`CaptureLogReader.sniff` recognises a capture log by its first line (``session.start`` with ``capture: "0.1"``);
* :func:`read_capture_log` splits the log on LF, parses every complete line with the strict loader of
  :mod:`agentprov.ingest` (one JSON object per line, ``max_jsonl_line_bytes``), and hands the raw lines and the parsed
  events to the hash-chain verifier of ``agentprov_capture`` (:func:`agentprov_capture.verify.verify_chain`, the one
  implementation of C.13.2). Only the **verifiable prefix** is mapped (C.13.2: an unsealed log is kept and its verifiable
  prefix mapped);
* :meth:`CaptureLogReader.plan` finds the capture log among the session's objects, reads the blobs the verified events
  reference and the native TraceLogger JSON named by the ``native.log`` event (both by digest), and yields the unit with
  the auxiliary bytes ``blob:<hex>`` and ``native_log``. A log without a verifiable ``session.start`` names no session and
  no execution: it is a register row (``select.not_execution_artefact``), never a unit.

Untrusted bytes are parsed only through :mod:`agentprov.ingest` (invariant 3); nothing here interprets event content
beyond the envelope and the blob references. Imports: stdlib, ``agentprov.{ingest, aer, adapters, errors}`` and the
``agentprov_capture`` verifier (D.2.1).
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov_capture.verify import verify_chain

from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, ExecutionUnit, LocatedItem, Locator, Origin, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = [
    "DIALECT_ID",
    "LOG_MEDIA",
    "VARIANT",
    "CaptureLogReader",
    "CaptureLogView",
    "CapturePlan",
    "ChainFinding",
    "SessionObject",
    "blob_refs",
    "read_capture_log",
]

DIALECT_ID: Final = "agentprov.capture"
VARIANT: Final = "0.1"
LOG_MEDIA: Final = "application/x-ndjson"
_LOG_SUFFIX: Final = ".capture.jsonl"
_UUID7: Final = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_DIGEST: Final = re.compile(r"sha256:([0-9a-f]{64})")
_STRAYS: Final = frozenset({".DS_Store"})


def _verify_chain(lines: Sequence[bytes], events: Sequence[Mapping[str, Any] | None]) -> Any:
    """:func:`agentprov_capture.verify.verify_chain` (C.13.2): the one implementation of the chain rules, shared with the
    backends (D.10.0). ``events`` holds ``None`` for a complete line the strict loader rejected (``cap.chain.bad_json``)."""
    return verify_chain(lines, events)


@dataclass(frozen=True, slots=True)
class ChainFinding:
    """One finding of the chain verifier, reduced to the verifier's code and the sequence number (never source text)."""

    code: str
    seq: int | None


@dataclass(frozen=True, slots=True)
class CaptureLogView:
    """A capture log as the mapper sees it: the verifiable prefix and what the verifier said about the whole log.

    ``events`` are the parsed events of the verifiable prefix (``events[i]`` is line ``i``). ``n_lines`` counts every
    line of the log, a torn final line included; ``sealed`` is the verifier's verdict, and is false whenever a line could
    not be parsed or the log ends in a torn line (C.13.2: a sealed log's ``session.end`` counts every line).
    """

    events: tuple[Mapping[str, Any], ...]
    n_lines: int
    n_parsed: int
    sealed: bool
    status: str | None
    appended_by: str | None
    head: str | None
    findings: tuple[ChainFinding, ...] = ()
    torn: bool = False
    unparsed_line: int | None = None

    @property
    def session(self) -> str | None:
        """The session UUIDv7 of a verified ``session.start``, else ``None``."""
        if not self.events or self.events[0].get("type") != "session.start":
            return None
        data = self.events[0].get("data")
        session = data.get("session") if isinstance(data, dict) else None
        return session if isinstance(session, str) and _UUID7.fullmatch(session) else None


def _split_lines(data: bytes) -> tuple[list[bytes], bytes | None]:
    """Complete lines (each with its LF) and the torn tail (bytes after the last LF), never ``splitlines``."""
    lines: list[bytes] = []
    pos = 0
    while True:
        nl = data.find(b"\n", pos)
        if nl < 0:
            break
        lines.append(data[pos : nl + 1])
        pos = nl + 1
    return lines, (data[pos:] if pos < len(data) else None)


def read_capture_log(
    data: bytes,
    limits: IngestLimits | None = None,
    *,
    verifier: Callable[[Sequence[bytes], Sequence[Mapping[str, Any] | None]], Any] | None = None,
) -> CaptureLogView:
    """Parse a capture log strictly and verify its chain (C.13.2); the view holds the verifiable prefix.

    Every complete line is parsed with :func:`agentprov.ingest.loaders.strict_json_loads` (``record=True``: the
    ``max_jsonl_line_bytes`` bound); a line the loader rejects, or that is not one JSON object, is passed to the verifier
    as ``None`` (its ``cap.chain.bad_json``). A torn final line (no LF) is passed as is, as the contract requires. The
    view keeps the events of the verifiable prefix only (``n_verified``, which ends before a ``prev`` mismatch's
    predecessor, C.13.10).
    """
    limits = limits or IngestLimits()
    if len(data) > limits.max_artefact_bytes:
        raise IngestError("ingest.size.file", f"capture log of {len(data)} bytes exceeds the limit",
                          limit=limits.max_artefact_bytes)
    lines, torn = _split_lines(data)
    events: list[Mapping[str, Any] | None] = []
    for line in lines:
        try:
            value = strict_json_loads(line[:-1], limits, record=True)
        except IngestError:
            value = None
        events.append(value if isinstance(value, dict) else None)
    parsed = sum(1 for e in events if e is not None)
    unparsed = next((i for i, e in enumerate(events) if e is None), None)
    report = (verifier or _verify_chain)(lines + ([torn] if torn is not None else []), events)
    n_verified = max(0, min(int(report.n_verified), unparsed if unparsed is not None else len(events)))
    sealed = bool(report.sealed) and unparsed is None and torn is None and n_verified == len(lines)
    findings = tuple(
        ChainFinding(str(getattr(issue, "code", "chain")), getattr(issue, "seq", None)
                     if isinstance(getattr(issue, "seq", None), int) else None)
        for issue in report.issues
    )
    verified: tuple[Mapping[str, Any], ...] = tuple(e for e in events[:n_verified] if e is not None)
    return CaptureLogView(
        events=verified,
        n_lines=len(lines) + (1 if torn is not None else 0),
        n_parsed=parsed,
        sealed=sealed,
        status=report.status if sealed and isinstance(report.status, str) else None,
        appended_by=report.appended_by if sealed and isinstance(report.appended_by, str) else None,
        head=report.head if isinstance(report.head, str) else None,
        findings=findings,
        torn=torn is not None,
        unparsed_line=unparsed,
    )


def blob_refs(value: object) -> list[str]:
    """The ``sha256`` hex digests of every well-formed ``{"$blob": "sha256:<hex>", …}`` inside ``value``, in first-seen
    order (an iterative walk: events are bounded by the loader's depth limit, but no recursion is needed)."""
    seen: dict[str, None] = {}
    stack: list[object] = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            ref = node.get("$blob")
            if isinstance(ref, str):
                match = _DIGEST.fullmatch(ref)
                if match is not None:
                    seen.setdefault(match.group(1), None)
                continue
            stack.extend(reversed(list(node.values())))
        elif isinstance(node, list):
            stack.extend(reversed(node))
    return list(seen)


@dataclass(frozen=True, slots=True)
class SessionObject:
    """One staged object of a session as the plan receives it: label (relative to the session directory; a label, never a
    path), digest, size and origin (the shape of the runner's ``MemberRef``)."""

    label: str
    sha256: str
    size: int
    origin: Origin


@dataclass(slots=True)
class CapturePlan:
    """What one session yields: the unit (at most one), the auxiliary bytes, and register rows (D.2.8 case 4)."""

    units: list[ExecutionUnit] = field(default_factory=list)
    auxiliary: dict[str, bytes] = field(default_factory=dict)
    register: list[dict[str, str]] = field(default_factory=list)  # {"label", "code", "detail"}


def _first_line(data: bytes) -> bytes:
    nl = data.find(b"\n")
    return data if nl < 0 else data[:nl]


def _match(label: str, glob: str) -> bool:
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


class CaptureLogReader:
    """``Reader`` for ``agentprov.capture`` (D.2.3; C.13)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = frozenset({VARIANT})
    media_types: Final = frozenset({LOG_MEDIA})

    def __init__(
        self, *, verifier: Callable[[Sequence[bytes], Sequence[Mapping[str, Any] | None]], Any] | None = None
    ) -> None:
        self._verifier = verifier

    # ------------------------------------------------------------------------------------------ discovery
    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Capture logs matching the profile's ``[import] include`` globs (default ``raw/capture/*.capture.jsonl``)."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("raw/capture/*" + _LOG_SUFFIX,)
        for candidate in sorted(tree.walk(), key=lambda c: c.label):
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._"):
                continue
            if any(_match(candidate.label, g) for g in include):
                yield candidate

    # ------------------------------------------------------------------------------------------ sniff and parse
    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult:
        """Total: a capture log iff its first line is a ``session.start`` event of ``capture: "0.1"``."""
        try:
            first = strict_json_loads(_first_line(data), limits, record=True)
        except IngestError as exc:
            return SniffResult(False, reasons=(exc.code,))
        if not isinstance(first, dict) or first.get("type") != "session.start":
            return SniffResult(False, reasons=("capture.sniff.no_session_start",))
        payload = first.get("data")
        if not isinstance(payload, dict) or payload.get("capture") != VARIANT:
            return SniffResult(False, reasons=("capture.sniff.not_capture_0_1",))
        return SniffResult(True, DIALECT_ID, VARIANT, frozenset(), ("capture.sniff.session_start",))

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One located item per capture log (locator ``{}``: the whole artefact, C.4.1 live ``source_key``).

        ``MalformedArtefact`` when no ``session.start`` verifies (no session, no execution)."""
        view = read_capture_log(data, limits, verifier=self._verifier)
        if view.session is None:
            raise MalformedArtefact("capture log without a verifiable session.start")
        yield LocatedItem(artefact=artefact, locator=Locator(a=artefact.id), dialect=DIALECT_ID, variant=VARIANT,
                          flags=frozenset(), value=view)

    # ------------------------------------------------------------------------------------------ session plan
    def plan(
        self,
        members: Sequence[Any],
        read: Callable[[str], bytes],
        profile: SourceProfile,
        *,
        limits: IngestLimits | None = None,
    ) -> CapturePlan:
        """The unit of one staged session. ``members`` are its objects (``label``, ``sha256``, ``size``, ``origin``);
        ``read(sha256)`` returns an object's bytes from the digest-checked store.

        Exactly one object labelled ``*.capture.jsonl`` is the log; any other count is one register row. Blobs and the
        native log are found **by digest** (the events name them by digest; labels are data). A blob or native log the
        events name but the session lacks is left out: the mapper declares what it cannot read.
        """
        limits = limits or IngestLimits()
        plan = CapturePlan()
        logs = [m for m in members if str(m.label).endswith(_LOG_SUFFIX)]
        if len(logs) != 1:
            plan.register.append({"label": "", "code": "select.not_execution_artefact",
                                  "detail": f"agentprov.capture: {len(logs)} capture logs in the session (one expected)"})
            return plan
        log = logs[0]
        data = read(log.sha256)
        sniff = self.sniff(data, label=log.label, limits=limits)
        if not sniff.match:
            plan.register.append({"label": str(log.label), "code": "select.not_execution_artefact",
                                  "detail": "agentprov.capture: " + ",".join(sniff.reasons)})
            return plan
        artefact = ArtefactRef("a0", log.sha256, log.size, LOG_MEDIA, log.origin, "capture_log", "native")
        try:
            item = next(self.parse(data, artefact, limits=limits))
        except (IngestError, MalformedArtefact) as exc:
            plan.register.append({"label": str(log.label), "code": "select.not_execution_artefact",
                                  "detail": f"agentprov.capture: {getattr(exc, 'code', 'malformed')}"})
            return plan
        view: CaptureLogView = item.value
        by_digest = {str(m.sha256): m for m in members}
        for digest in blob_refs([e.get("data") for e in view.events]):
            member = by_digest.get(digest)
            if member is None:
                continue
            raw = read(digest)
            if hashlib.sha256(raw).hexdigest() == digest:
                plan.auxiliary[f"blob:{digest}"] = raw
        auxiliary: dict[str, ArtefactRef] = {}
        native = _native_event(view)
        if native is not None:
            member = by_digest.get(native)
            if member is not None:
                raw = read(native)
                if hashlib.sha256(raw).hexdigest() == native:
                    plan.auxiliary["native_log"] = raw
                    auxiliary["native_log"] = ArtefactRef("a1", native, len(raw), "application/json", member.origin,
                                                          "native_log", "native")
        cache = _attack_cache(view, profile)
        if cache is not None:
            digest, media = cache
            member = by_digest.get(digest)
            if member is not None:
                raw = read(digest)
                if hashlib.sha256(raw).hexdigest() == digest:
                    # D.11.9: the replayed attack cache, a context artefact (fail-closed prov_primary, C.3.12)
                    plan.auxiliary["attack_cache"] = raw
                    auxiliary["attack_cache"] = ArtefactRef(f"a{1 + len(auxiliary)}", digest, len(raw), media,
                                                            member.origin, "supporting", "unknown")
        plan.units.append(ExecutionUnit(primary=item, auxiliary=auxiliary, mode="live", ex=f"ex_{view.session}"))
        return plan


def _attack_cache(view: CaptureLogView, profile: SourceProfile) -> tuple[str, str] | None:
    """``(sha256, media)`` of the attack cache the session's cell names, when the profile declares a cache-replaying
    attack (``[family.agentdojo.live] attack_cache``, D.11.9) and the cell runs it; ``None`` otherwise."""
    family = profile.data.get("family")
    agentdojo = family.get("agentdojo") if isinstance(family, Mapping) else None
    live = agentdojo.get("live") if isinstance(agentdojo, Mapping) else None
    spec = live.get("attack_cache") if isinstance(live, Mapping) else None
    if not isinstance(spec, Mapping) or not view.events:
        return None
    data = view.events[0].get("data")
    cell = data.get("cell") if isinstance(data, Mapping) else None
    if not isinstance(cell, Mapping) or cell.get("attack_id") != spec.get("attack"):
        return None
    params = cell.get("attack_params")
    digest = params.get(str(spec.get("sha256_param"))) if isinstance(params, Mapping) else None
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        return None
    return digest, str(spec.get("media") or "application/octet-stream")


def _native_event(view: CaptureLogView) -> str | None:
    """The digest named by the last verified ``native.log`` event, if well formed."""
    found: str | None = None
    for event in view.events:
        if event.get("type") != "native.log":
            continue
        data = event.get("data")
        digest = data.get("sha256") if isinstance(data, dict) else None
        if isinstance(digest, str):
            digest = digest.removeprefix("sha256:")
            if re.fullmatch(r"[0-9a-f]{64}", digest):
                found = digest
    return found
