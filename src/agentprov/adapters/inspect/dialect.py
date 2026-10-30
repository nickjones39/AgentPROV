"""Reader of the Inspect AI ``.eval`` dialect (docs/architecture D.9.1; D.2.3; layer L4).

Dialect ``inspect.eval``, variant ``v2`` (log format version 2; producer band of the profile's
``[family.inspect] producer_band``). An ``.eval`` file is a ZIP container stored as one raw object. The versioned
``expand`` stage (:mod:`agentprov.raw.members`, AD-12) turns the members the profile's ``members`` patterns select into
member objects of their own (origin ``member``); this reader never opens the container itself beyond its magic bytes.
What it does:

* :meth:`InspectEvalReader.sniff` classifies the stored container by its ZIP magic and a member object by its keys
  (``EvalSample``: ``id``, ``epoch``, ``messages``, ``events``); the interim ``message_pool`` sample shape is flagged so
  that the mapper refuses it (``UnsupportedVariant``; upstream refuses to re-ground its references);
* :meth:`InspectEvalReader.plan` turns the member objects of one container into execution units: one per classic
  sample member ``samples/<id>_epoch_<n>.json`` (locator ``{"p": ""}``), with the ``header.json`` member object as the
  auxiliary artefact ``header`` (role ``supporting``). A log whose producer is outside the band, a header that is not a
  log of a supported version, and the chunked sample shape are register entries (``select.dialect_planned``), never
  units: no other reader misparses them;
* :meth:`InspectEvalReader.parse` parses one member object strictly into its located item.

Parsing goes through :mod:`agentprov.ingest` only (A-1, invariant 3). Imports: stdlib and ``agentprov.{ingest, aer,
adapters}`` (D.2.1).
"""

from __future__ import annotations

import dataclasses
import fnmatch
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, ExecutionUnit, LocatedItem, Locator, Origin, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import PROFILE_PYTHON_JSON, strict_json_loads
from agentprov.ingest.quote import escape_untrusted

__all__ = [
    "DIALECT_ID",
    "FLAG_CONTAINER",
    "FLAG_HEADER_NONFINITE",
    "FLAG_MESSAGE_POOL",
    "HEADER_LABEL",
    "VARIANT",
    "EvalPlan",
    "InspectEvalReader",
    "MemberObject",
    "classify_label",
    "load_header",
    "producer_version",
]

DIALECT_ID: Final = "inspect.eval"
VARIANT: Final = "v2"
HEADER_LABEL: Final = "header.json"
FLAG_CONTAINER: Final = "container:zip"
FLAG_MESSAGE_POOL: Final = "shape:message_pool"
#: RH-1: the unit's ``header.json`` holds a non-finite number in a member the mapper never reads (``/results``, ``/stats``;
#: Inspect writes ``NaN`` for an undefined metric, e.g. AgentHarm's ``avg_score_non_refusals`` when every sample refused).
FLAG_HEADER_NONFINITE: Final = "header:nonfinite"
_UNMAPPED_HEADER_MEMBERS: Final = frozenset({"results", "stats"})
_ZIP_MAGIC: Final = b"PK\x03\x04"
_SAMPLE_KEYS: Final = ("id", "epoch", "messages", "events")
_CLASSIC: Final = re.compile(r"samples/[^/]+_epoch_[0-9]+\.json")
_CHUNKED: Final = re.compile(r"samples/[^/]+_epoch_[0-9]+/.+")
_STRAYS: Final = (".DS_Store",)


def classify_label(label: str) -> str:
    """``header``, ``sample`` (classic shape), ``chunked`` (chunked shape, planned) or ``other``."""
    if label == HEADER_LABEL:
        return "header"
    if _CLASSIC.fullmatch(label):
        return "sample"
    if _CHUNKED.fullmatch(label):
        return "chunked"
    return "other"


def _float_pointers(value: Any, ptr: str, made: set[int]) -> Iterator[str]:
    """JSON Pointers of the ``{"$float": ...}`` objects the ``python-json`` profile made of non-finite constants
    (``made``: their ids, from the loader's ``nonfinite_objects``). A one-key ``{"$float": ...}`` object that is literally
    in the source is ordinary data, never counted (RH-1 review R2-3)."""
    if isinstance(value, dict):
        if id(value) in made:
            yield ptr
            return
        for key, item in value.items():
            yield from _float_pointers(item, f"{ptr}/{str(key).replace('~', '~0').replace('/', '~1')}", made)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _float_pointers(item, f"{ptr}/{i}", made)


def load_header(raw: bytes, limits: IngestLimits | None = None) -> tuple[Any, int]:
    """``header.json`` parsed, and the number of non-finite numbers it holds (RH-1; D.9.5).

    The ``python-json`` profile maps ``NaN``/``Infinity``/``-Infinity`` to ``{"$float": ...}`` (C.11.3); it parses every
    other document exactly as the strict profile does. A non-finite number is tolerated only under the members the
    mapper never reads (``/results``, ``/stats``): it is never mapped as a value, and the units of the log carry
    :data:`FLAG_HEADER_NONFINITE` (the mapper reports it). Anywhere else the header stays unreadable
    (``ingest.number.nonfinite``), as before.
    """
    made_objects: list[Any] = []
    header = strict_json_loads(raw, limits, profile=PROFILE_PYTHON_JSON, nonfinite_objects=made_objects)
    if not made_objects:
        return header, 0
    pointers = list(_float_pointers(header, "", {id(o) for o in made_objects}))
    # the root itself (a bare NaN document, review R2-1) or any member outside /results and /stats keeps the log planned
    if len(pointers) != len(made_objects) or not isinstance(header, dict) \
            or any(p.count("/") < 1 or p.split("/")[1] not in _UNMAPPED_HEADER_MEMBERS for p in pointers):
        raise IngestError("ingest.number.nonfinite", "NaN or Infinity literal in a mapped header member")
    return header, len(pointers)


def producer_version(header: Mapping[str, Any]) -> str | None:
    """``eval.packages.inspect_ai`` of a parsed ``header.json`` (``None`` when absent or not a string)."""
    ev = header.get("eval")
    packages = ev.get("packages") if isinstance(ev, Mapping) else None
    value = packages.get("inspect_ai") if isinstance(packages, Mapping) else None
    return value if isinstance(value, str) else None


@dataclass(frozen=True, slots=True)
class MemberObject:
    """A member object produced by the ``expand`` stage: its label, digest, size and ``member`` origin."""

    label: str
    sha256: str
    size: int
    origin: Origin


@dataclass(slots=True)
class EvalPlan:
    """What one container yields: execution units, the header bytes and register rows (D.2.8 case 4)."""

    units: list[ExecutionUnit] = field(default_factory=list)
    auxiliary: dict[str, bytes] = field(default_factory=dict)
    register: list[dict[str, str]] = field(default_factory=list)  # {"label", "code", "detail"}
    producer: str | None = None


def _sample_shape(value: object) -> str | None:
    """``None`` for an ``EvalSample`` object, else the reason code."""
    if not isinstance(value, dict):
        return "not_object"
    if not all(k in value for k in _SAMPLE_KEYS):
        return "sample_keys"
    if not isinstance(value.get("messages"), list) or not isinstance(value.get("events"), list):
        return "sample_types"
    return None


def _flags(value: Mapping[str, Any]) -> frozenset[str]:
    return frozenset({FLAG_MESSAGE_POOL}) if "message_pool" in value and "events_data" not in value else frozenset()


class InspectEvalReader:
    """``Reader`` for ``inspect.eval`` (D.2.3, D.9.1)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = frozenset({VARIANT})
    media_types: Final = frozenset({"application/zip", "application/json"})

    # ------------------------------------------------------------------------------------------ discovery
    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Candidates matching the profile's ``[import] include`` globs, minus strays and excludes, in label order."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/*.eval",)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        for candidate in sorted(tree.walk(), key=lambda c: c.label):
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._"):
                continue
            if any(_match(candidate.label, g) for g in include) and not any(_match(candidate.label, g) for g in exclude):
                yield candidate

    @staticmethod
    def sample_stratum(key: str) -> str | None:
        """D-529 ``--sample-mode spread``: one ``.eval`` log is one evaluation run (one task, model and configuration), so
        its samples form one stratum: the container's label, the part before the **last** ``!/`` (NF-37, regen item 131:
        a log inside a declared nested archive has the chain label ``<archive>!/<log>``, and splitting at the first
        ``!/`` gave every log of that archive one stratum). A head that is not an ``.eval`` names no stratum."""
        head = key.rsplit("!/", 1)[0]
        return head if head.endswith(".eval") else None

    @staticmethod
    def member_patterns(profile: SourceProfile) -> tuple[str, ...]:
        """The ``expand`` selection of the container level: ``[family.inspect] members`` (D.4.4)."""
        members = profile.family_table().get("members", ())
        return tuple(str(m) for m in members)

    # ------------------------------------------------------------------------------------------ sniff and parse
    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult:
        """Total classification: a stored container by ZIP magic only (T0); a member object by its keys."""
        if data[:4] == _ZIP_MAGIC:
            return SniffResult(True, DIALECT_ID, None, frozenset({FLAG_CONTAINER}), ("inspect.sniff.zip_magic",))
        try:
            value = strict_json_loads(data, limits)
        except IngestError as exc:
            return SniffResult(False, reasons=(exc.code,))
        reason = _sample_shape(value)
        if reason is not None:
            return SniffResult(False, reasons=(f"inspect.sniff.{reason}",))
        assert isinstance(value, dict)
        return SniffResult(True, DIALECT_ID, VARIANT, _flags(value), ("inspect.sniff.eval_sample",))

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One located item per sample member object (locator ``{"p": ""}``). ``IngestError`` or ``MalformedArtefact``."""
        value = strict_json_loads(data, limits)
        reason = _sample_shape(value)
        if reason is not None:
            raise MalformedArtefact(f"not an Inspect EvalSample object ({reason})")
        assert isinstance(value, dict)
        yield LocatedItem(artefact=artefact, locator=Locator(a=artefact.id, p=""), dialect=DIALECT_ID, variant=VARIANT,
                          flags=_flags(value), value=value)

    # ------------------------------------------------------------------------------------------ container plan
    def plan(
        self,
        members: Sequence[MemberObject],
        read: Callable[[str], bytes],
        profile: SourceProfile,
        *,
        limits: IngestLimits | None = None,
    ) -> EvalPlan:
        """Units of one expanded container. ``read(sha256)`` returns a member object's bytes (digest-checked store).

        The header decides the band (D.9.0): a producer outside ``producer_band`` or a log version outside
        ``log_versions`` makes the whole container one ``select.dialect_planned`` register row and no unit. A missing or
        unparseable header is ``select.dialect_planned`` as well: without it the log cannot be placed in the band.
        """
        limits = limits or IngestLimits()
        family = profile.family_table()
        plan = EvalPlan()
        by_kind: dict[str, list[MemberObject]] = {}
        for member in members:
            by_kind.setdefault(classify_label(member.label), []).append(member)
        headers = by_kind.get("header", [])
        if len(headers) != 1:
            plan.register.append({"label": "", "code": "select.dialect_planned", "detail": "inspect.eval: no header.json member"})
            return plan
        header_obj = headers[0]
        raw = read(header_obj.sha256)
        try:
            header, nonfinite = load_header(raw, limits)
        except IngestError as exc:
            plan.register.append({"label": header_obj.label, "code": "select.dialect_planned",
                                  "detail": f"inspect.eval: header.json unreadable ({exc.code})"})
            return plan
        if not isinstance(header, dict):
            plan.register.append({"label": header_obj.label, "code": "select.dialect_planned",
                                  "detail": "inspect.eval: header.json is not an object"})
            return plan
        producer = producer_version(header)
        plan.producer = producer
        band = family.get("producer_band", {})
        allowed = tuple(band.get("inspect_ai", ())) if isinstance(band, Mapping) else ()
        versions = tuple(family.get("log_versions", (2,)))
        if producer not in allowed or header.get("version") not in versions:
            shown = escape_untrusted(producer if producer is not None else "absent")
            plan.register.append({"label": "", "code": "select.dialect_planned",
                                  "detail": f"inspect.eval: producer inspect_ai {shown} log version "
                                            f"{escape_untrusted(str(header.get('version')))} outside the band"})
            return plan
        header_ref = ArtefactRef("a1", header_obj.sha256, header_obj.size, "application/json", header_obj.origin,
                                 "supporting", "native")
        plan.auxiliary["header"] = raw
        for member in by_kind.get("chunked", []):
            plan.register.append({"label": member.label, "code": "select.dialect_planned",
                                  "detail": "inspect.eval: chunked sample shape is planned in v0.1"})
        for member in by_kind.get("sample", []):
            artefact = ArtefactRef("a0", member.sha256, member.size, "application/json", member.origin, "primary", "native")
            data = read(member.sha256)
            sniff = self.sniff(data, label=member.label, limits=limits)
            if not sniff.match:
                # selected as a sample member but not an EvalSample: an in-scope artefact that cannot be mapped
                item = LocatedItem(artefact, Locator(a="a0", p=""), DIALECT_ID, VARIANT, frozenset(), None)
            else:
                try:
                    item = next(self.parse(data, artefact, limits=limits))
                except (IngestError, MalformedArtefact):
                    item = LocatedItem(artefact, Locator(a="a0", p=""), DIALECT_ID, VARIANT, frozenset(), None)
            if nonfinite:
                item = dataclasses.replace(item, flags=item.flags | {FLAG_HEADER_NONFINITE})
            plan.units.append(ExecutionUnit(primary=item, auxiliary={"header": header_ref}))
        return plan


def _match(label: str, glob: str) -> bool:
    """``fnmatch`` over a POSIX label, with ``**/`` also matching zero directories."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))
