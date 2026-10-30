"""Mapping runner: one execution unit -> sealed AER, in a T1 worker or in process (docs/architecture D.2.4, D.2.8, D.2.9).

This is the phase-4 core of the importer runner (``import_source`` of D.2.9 builds on it):

* :class:`MapContext` is the concrete :class:`~agentprov.adapters.protocols.MappingContext`: it resolves rule references
  against the shipped catalogues (``RuleNotDeclared`` at map time) and collects seal issues.
* :func:`map_unit` runs ``Mapper.map`` and returns a :class:`MapOutcome`. A ``MalformedArtefact``,
  ``UnsupportedVariant`` or any unexpected exception yields a **degenerate** outcome (header + seal issue, D.2.8 case
  3) instead of an exception: an in-scope artefact always ends in a sealed AER.
* :func:`seal_outcome` hands the records to :class:`agentprov.aer.writer.AerWriter`, which checks every record with
  the validator, computes the accounting, seals and writes atomically (T0 write gate). A record set the writer rejects
  becomes a degenerate AER with ``adapter_defect``.
* :func:`job_map` is the T1 job ``map`` (``agentprov.io.workers.JOB_KINDS``): it reads the artefact by digest, sniffs,
  parses and maps it, and returns the records and issues as JSON frames; the parent seals them (:func:`seal_job_result`).
  :func:`map_artefact` is the same pipeline in process (tests, ``--in-process``). Two phase-6 modes serve the import
  pipeline (:mod:`agentprov.adapters.runner.importer`): ``total`` maps a whole-file artefact that fails to sniff or
  parse with a strict-loader violation to a degenerate AER (D.2.8 case 3) instead of failing the job, and ``container``
  plans the member objects of one expanded container with the reader's ``plan`` (the Inspect ``.eval`` family) and maps
  every unit, framing each unit's records after a ``{"unit": …}`` frame (:func:`split_unit_frames`). A whole-file reader
  that declares ``multi_execution = True`` (one located item per execution, e.g. a credleak cell's runs; R-10k-1, D-320)
  is mapped in ``total`` mode with ``per_item``: one unit per located item, framed as in ``container`` mode
  (:func:`map_artefact_units`).
* :func:`agentprov.adapters.runner.provjob.job_prov` is the T1 job ``prov``: ``agentprov-prov/0.1`` derivation and the
  tier-4 validators over one sealed AER read by digest from a scratch store.

Mapper and reader classes are found through the registry's lazy ``agentprov.``-namespaced factory strings (D.3.1), so
this module imports no adapter family. Nothing here reads a clock, the environment or a path other than the ones given:
the AER bytes are a pure function of the artefact, the adapter code, the profile and the catalogues (C.11.7).
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any, Final, Literal

from agentprov.adapters.profiles import SourceProfile, load_profile
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, LocatedItem, Locator, Origin
from agentprov.aer.ids import import_execution_id, mapping_id
from agentprov.aer.rules import RuleRegistry, load_catalogue, parse_rule_ref
from agentprov.aer.writer import AerWriteError, AerWriter, SealInfo
from agentprov.errors import AdapterDefect, AgentProvError, MalformedArtefact, RuleNotDeclared, UnsupportedVariant
from agentprov.io.canonical import sha256_hex

__all__ = [
    "ImportFilters",
    "ImportReport",
    "MapContext",
    "MapOutcome",
    "NotOfDialect",
    "NotSelected",
    "degenerate_unit",
    "import_source",
    "job_map",
    "map_artefact",
    "map_artefact_total",
    "map_artefact_units",
    "map_unit",
    "multi_execution",
    "rejected_rows",
    "streams",
    "resolve_factory",
    "seal_job_result",
    "seal_outcome",
    "split_unit_frames",
    "summarise_unit_frames",
    "iter_unit_frames",
    "FrameSummary",
    "variant_part",
]


def __getattr__(name: str) -> Any:
    """The import pipeline (D.2.9) lives in :mod:`agentprov.adapters.runner.importer`; imported on first use."""
    if name in ("ImportFilters", "ImportReport", "import_source"):
        from agentprov.adapters.runner import importer

        return getattr(importer, name)
    raise AttributeError(name)

Severity = Literal["info", "warning", "error"]


def resolve_factory(path: str) -> Any:
    """Resolve a registry factory ``"agentprov.<module>:<Class>"``; anything outside ``agentprov.`` is refused (D.3.1)."""
    module, sep, name = path.partition(":")
    if not sep or not module.startswith("agentprov.") or not name.isidentifier():
        raise AgentProvError("registry factories are agentprov.-namespaced 'module:Name' strings", code="adapter.factory")
    return getattr(import_module(module), name)


@dataclass(frozen=True, slots=True)
class CarvedBlob:
    """A blob carved from the unit's primary artefact (D-218): its digest, size, the value's key locator, the
    transform, the media type and the bytes. The job hands the bytes to the parent, which stores them with a ``carved``
    origin before the AER that references them is validated."""

    sha256: str
    size: int
    source: str
    loc: Mapping[str, Any]
    transform: str
    media: str | None
    data: bytes

    def header(self) -> dict[str, Any]:
        """The job member header (role ``carved``)."""
        return {"role": "carved", "sha256": self.sha256, "size": self.size, "from": self.source, "loc": dict(self.loc),
                "transform": self.transform, "media": self.media}


class MapContext:
    """The mapping context of one unit (D.2.4)."""

    def __init__(
        self, profile: SourceProfile, rules: RuleRegistry, mapping: str, ex: str,
        auxiliary: Mapping[str, bytes] | None = None, *,
        source: Callable[[], bytes] | None = None, source_sha256: str | None = None, limits: Any = None,
    ) -> None:
        self.profile = profile
        self.rules = rules
        self.mapping_id = mapping
        self.ex = ex
        self.issues: list[dict[str, Any]] = []
        self.severities: list[Severity] = []
        self.checks: list[dict[str, Any]] = []
        self._versions: dict[str, int] = {}
        # kept as given: a lazy mapping (import context artefacts) is read only when the mapper opens a role
        self._auxiliary: Mapping[str, bytes] = auxiliary if auxiliary is not None else {}
        #: D-218: the unit's primary artefact bytes (read on the first :meth:`carve`) and its digest
        self._source, self._source_sha256, self._limits = source, source_sha256, limits
        self._carver: Any = None
        self.carved: list[CarvedBlob] = []

    def _version(self, namespace: str) -> int:
        if namespace not in self._versions:
            self._versions[namespace] = load_catalogue(namespace).version
        return self._versions[namespace]

    def catalogue_versions(self, namespaces: Sequence[str]) -> dict[str, int]:
        return {ns: self._version(ns) for ns in sorted(namespaces)}

    def rule(self, rule_id: str, pointer: str | None = None) -> str:
        """``<ns>.<rule>@<n>`` or ``…#<pointer>``; :class:`RuleNotDeclared` when the shipped catalogue lacks it."""
        try:
            ref = parse_rule_ref(rule_id)
        except ValueError:
            raise RuleNotDeclared(f"not a rule id: {rule_id!r}") from None
        if ref.pointer is not None:
            raise RuleNotDeclared("pass the pointer separately")
        entry = self.rules.lookup(rule_id, {ref.namespace: self._version(ref.namespace)})
        if entry is None or not entry.citable:
            raise RuleNotDeclared(f"rule {rule_id} is not declared in the shipped {ref.namespace!r} catalogue")
        return rule_id if pointer is None else f"{rule_id}#{pointer}"

    def issue(
        self,
        code: str,
        *,
        ids: Sequence[str] = (),
        rule: str | None = None,
        severity: Severity = "warning",
        detail: str | None = None,
    ) -> None:
        if rule is None:
            raise RuleNotDeclared("every seal issue cites the rule that produced it (C.12.3)")
        namespace, _, tail = code.partition(".")
        if tail:  # "<ns>.<code>": declared in that catalogue's issue_codes (D.5.5); core codes have no dot
            catalogue = self.rules.get(namespace, self._version(namespace))
            if not catalogue.declares_issue_code(code):
                raise RuleNotDeclared(f"issue code {code} is not declared in the {namespace!r} catalogue")
        item: dict[str, Any] = {"code": code, "ids": list(ids), "rule": rule}
        if detail is not None:
            item["detail"] = detail
        self.issues.append(item)
        self.severities.append(severity)

    def check(
        self,
        check_id: str,
        *,
        scope: str,
        verdict: Literal["consistent", "inconsistent", "unverifiable"],
        observed: Mapping[str, int],
        reason: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {"id": check_id, "scope": scope, "verdict": verdict, "observed": dict(sorted(observed.items()))}
        if reason is not None:
            entry["reason"] = reason
        self.checks.append(entry)

    def carve(self, loc: Mapping[str, Any], transform: str = "utf8", *, media: str | None = None) -> dict[str, Any]:
        """A ``$blob`` reference (C.11.5) to the string at key locator ``loc`` (``p``, optionally ``line`` or ``bytes``) of
        the unit's primary artefact, carved under ``transform`` (``utf8``, or ``base64`` for a ``data:`` URI's payload;
        D-218). The bytes are re-derived from the artefact, never taken from the mapper, and travel to the parent, which
        stores them with a ``carved`` origin. ``raw.carve.invalid`` when the value cannot be carved; ``media`` defaults
        to the ``data:`` URI's own (``base64``) or ``text/plain; charset=utf-8`` (``utf8``)."""
        from agentprov.raw.carve import Carver

        if self._source is None or self._source_sha256 is None:
            raise AgentProvError("this mapping context has no primary artefact bytes to carve from",
                                 code="adapter.carve_unavailable")
        if self._carver is None:  # one parse per region of the source for all carves of this unit
            self._carver = Carver(self._source(), self._limits)
        carved = self._carver.carve(loc, transform)
        sha = sha256_hex(carved.data)
        chosen = media or carved.media or ("text/plain; charset=utf-8" if transform == "utf8" else "application/octet-stream")
        if all(c.sha256 != sha for c in self.carved):
            self.carved.append(CarvedBlob(sha, len(carved.data), self._source_sha256, dict(loc), transform, chosen,
                                          carved.data))
        return {"$blob": "sha256:" + sha, "bytes": len(carved.data), "media": chosen}

    def open_auxiliary(self, role: str) -> bytes:
        """The bytes of the unit's auxiliary artefact ``role`` (``ExecutionUnit.auxiliary``), as the caller supplied them
        from the raw store; ``adapter.auxiliary_missing`` when none was supplied."""
        try:
            return self._auxiliary[role]
        except KeyError:
            raise AgentProvError(f"auxiliary artefact {role!r} was not supplied", code="adapter.auxiliary_missing") from None


@dataclass
class MapOutcome:
    """Records, issues and checks of one mapped unit, before sealing."""

    ex: str
    records: list[dict[str, Any]]
    issues: list[dict[str, Any]] = field(default_factory=list)
    severities: Sequence[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    degenerate: bool = False
    error_code: str | None = None  # the AdapterError / IngestError code of a degenerate outcome
    carved: list[CarvedBlob] = field(default_factory=list)  # D-218: blobs carved from the primary artefact

    def emit_carved(self, ctx: Any) -> None:
        """Hand the carved blobs to the parent as job members (role ``carved``), after the unit's frames."""
        for blob in self.carved:
            ctx.member(blob.header())
            ctx.data(blob.data)

    def to_frames(self) -> list[dict[str, Any]]:
        """The JSON frames of the T1 ``map`` job: one per record, then the seal inputs."""
        frames: list[dict[str, Any]] = [{"record": r} for r in self.records]
        frames.append(
            {
                "seal": {
                    "ex": self.ex,
                    "issues": self.issues,
                    "severities": self.severities,
                    "checks": self.checks,
                    "degenerate": self.degenerate,
                    "error_code": self.error_code,
                }
            }
        )
        return frames


def _degenerate(unit: ExecutionUnit, mapper: Any, ctx: MapContext, issue_code: str, error_code: str) -> MapOutcome:
    """D.2.8 case 3: only the header (artefact, origin, adapter, unit, task as far as known) and an error seal issue.

    The family supplies the header (``mapper.degenerate_header``): what a task is, and which rule the issue cites, is
    family knowledge (invariant 1).
    """
    header = mapper.degenerate_header(unit, ctx, issue_code=issue_code, detail=error_code)
    # D.2.8 case 3 says "only the header", but the validator requires exactly one run scope per file (C.17 AER-V07):
    # the artefact itself is the observed record of the run, so the scope cites it and declares everything else unknown.
    # D-219: when no value was read (a failed map job) and the unit is the whole document, the scope cites the whole
    # artefact (C.9.1: its bytes), not its parsed root, which does not resolve for bytes that are not JSON
    key = unit.primary.locator.key()
    cited = {} if unit.primary.value is None and key == {"p": ""} else key
    run = {
        "k": "scope",
        "id": "run",
        "kind": "run",
        "ev": "O",
        "by": "source",
        "src": [{"a": unit.primary.artefact.id, **cited}],
        "unk": {"/status": "not_recorded", "/t": "not_recorded"},
    }
    return MapOutcome(ctx.ex, [dict(header), run], ctx.issues, ctx.severities, [], degenerate=True, error_code=error_code)


def map_unit(
    unit: ExecutionUnit, mapper: Any, profile: SourceProfile, *, registry: RuleRegistry | None = None,
    auxiliary: Mapping[str, bytes] | None = None, source: bytes | Callable[[], bytes] | None = None, limits: Any = None,
) -> MapOutcome:
    """Map one unit (in this process). Never raises for the unit's content; ``RuleNotDeclared`` is a programming error.

    ``auxiliary`` maps each role of ``unit.auxiliary`` to its bytes (read from the raw store by the caller). ``source``
    is the primary artefact's bytes (or a callable that reads them), offered to :meth:`MapContext.carve` (D-218)."""
    rules = registry or RuleRegistry.default()
    mapping = mapping_id(mapper.mapper_id, profile.id)
    item = unit.primary
    ex = unit.ex or import_execution_id(mapping, item.artefact.sha256, item.locator.key())
    reader = (lambda: source) if isinstance(source, bytes) else source
    ctx = MapContext(profile, rules, mapping, ex, auxiliary, source=reader, source_sha256=item.artefact.sha256,
                     limits=limits)
    try:
        records = [dict(r) for r in mapper.map(unit, ctx)]
    except RuleNotDeclared:
        raise
    except MalformedArtefact as exc:
        return _degenerate(unit, mapper, MapContext(profile, rules, mapping, ex), "unparseable_artefact", exc.code)
    except UnsupportedVariant as exc:
        return _degenerate(unit, mapper, MapContext(profile, rules, mapping, ex), "unsupported_variant", exc.code)
    except Exception:  # noqa: BLE001 - D.2.8: an unexpected exception aborts only this unit, as adapter_defect
        return _degenerate(unit, mapper, MapContext(profile, rules, mapping, ex), "adapter_defect", AdapterDefect.code)
    return MapOutcome(ex, records, ctx.issues, ctx.severities, ctx.checks, carved=list(ctx.carved))


def seal_outcome(
    outcome: MapOutcome, path: Path, *, registry: RuleRegistry | None = None, unit: ExecutionUnit | None = None,
    mapper: Any = None, profile: SourceProfile | None = None,
) -> SealInfo:
    """Write ``outcome`` through :class:`AerWriter` at ``path``. A record set the writer rejects is replaced by a
    degenerate AER (``adapter_defect``) when ``unit``, ``mapper`` and ``profile`` are given; otherwise it raises."""
    rules = registry or RuleRegistry.default()
    try:
        writer = AerWriter(path, outcome.records[0], catalogues=rules)
        for record in outcome.records[1:]:
            writer.add(record)
        return writer.seal(issues=outcome.issues, extra_checks=outcome.checks)
    except AerWriteError:
        if unit is None or mapper is None or profile is None or outcome.degenerate:
            raise
    mapping = mapping_id(mapper.mapper_id, profile.id)
    fallback = _degenerate(unit, mapper, MapContext(profile, rules, mapping, outcome.ex), "adapter_defect", "aer.write.invalid")
    return seal_outcome(fallback, path, registry=rules)


def aer_bytes(outcome: MapOutcome, *, registry: RuleRegistry | None = None, **fallback: Any) -> tuple[bytes, SealInfo]:
    """Seal ``outcome`` in a private temporary directory and return the file bytes (tests, workers' parents)."""
    with tempfile.TemporaryDirectory(prefix="agentprov-aer-") as tmp:
        path = Path(tmp) / f"{outcome.ex}.aer.jsonl"
        info = seal_outcome(outcome, path, registry=registry, **fallback)
        return path.read_bytes(), info


# ------------------------------------------------------------------------------------------------ one artefact
def _family_classes(dialect: str, mapper_id: str) -> tuple[Any, Any]:
    from agentprov.adapters.registry import MAPPERS, READERS  # L6 data: lazy strings only

    return resolve_factory(READERS[dialect])(), resolve_factory(MAPPERS[mapper_id])()


def map_artefact(
    data: bytes,
    origin: Origin,
    *,
    profile_id: str,
    media: str = "application/json",
    prov_primary: str | None = None,
    limits: Any = None,
    registry: RuleRegistry | None = None,
) -> tuple[MapOutcome, ExecutionUnit | None]:
    """Sniff, parse and map one whole-file artefact in this process (the body of :func:`job_map`).

    Returns ``(outcome, unit)``. Bytes that are not of the profile's dialect raise ``MalformedArtefact`` (the caller
    records a register entry, D.2.8 case 4); a tier-1 violation raises ``IngestError``.
    """
    from agentprov.ingest.limits import IngestLimits

    profile = load_profile(profile_id)
    imp = profile.data.get("import", {})
    dialect, mapper_id = str(imp.get("dialect")), str(imp.get("mapper"))
    reader, mapper = _family_classes(dialect, mapper_id)
    limits = limits or IngestLimits()
    sniff = reader.sniff(data, label="", limits=limits)
    if not sniff.match:
        raise MalformedArtefact(f"not of dialect {dialect} ({', '.join(sniff.reasons)})")
    primary = prov_primary or mapper.prov_primary(sniff.flags)
    artefact = ArtefactRef(id="a0", sha256=sha256_hex(data), bytes=len(data), media=media, origin=origin, role="primary",
                           prov_primary=primary)  # type: ignore[arg-type]  # the mapper returns one of the four values
    items = list(reader.parse(data, artefact, limits=limits))
    if len(items) != 1:
        raise MalformedArtefact("a whole-file dialect yields exactly one located item")
    unit = ExecutionUnit(primary=items[0])
    return map_unit(unit, mapper, profile, registry=registry, source=data, limits=limits), unit


@dataclass(frozen=True, slots=True)
class MemberRef:
    """A member object of an expanded container as a container reader's ``plan`` receives it (label, digest, size and
    ``member`` origin; the shape of the Inspect family's ``MemberObject``)."""

    label: str
    sha256: str
    size: int
    origin: Origin


def degenerate_unit(
    sha256: str, size: int, origin: Origin, *, profile: SourceProfile, mapper: Any, media: str = "application/json",
    variant: str | None = None, auxiliary: Mapping[str, ArtefactRef] | None = None, locator: Locator | None = None,
) -> ExecutionUnit:
    """A unit for an artefact that could not be parsed: its primary item has no value (D.2.8 case 3).

    The variant is the sniffed one when known, else the first variant the profile declares (``[import] variants``): the
    degenerate header names a variant of the dialect, never an invented one. ``locator`` is the document root unless
    given (the item of a ``multi_execution`` file whose mapped records the write gate rejected keeps its own locator).
    """
    imp = profile.data.get("import", {})
    declared = tuple(str(v) for v in imp.get("variants", ()))
    chosen = variant or (declared[0] if declared else "unknown")
    artefact = ArtefactRef(id="a0", sha256=sha256, bytes=size, media=media, origin=origin, role="primary",
                           prov_primary=mapper.prov_primary(frozenset()))
    item = LocatedItem(artefact, locator or Locator(a="a0", p=""), str(imp.get("dialect")), chosen, frozenset(), None)
    return ExecutionUnit(primary=item, auxiliary=dict(auxiliary or {}))


class NotOfDialect(MalformedArtefact):
    """Valid input of another kind (D.2.8 case 4): the caller registers ``select.not_execution_artefact``. ``detail`` is
    the reader's register detail (``register_detail(reasons)``, e.g. ``dtap.synthetic``), or ``None`` for the default."""

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.detail = detail


def _not_of_dialect(reader: Any, dialect: str, reasons: Sequence[str]) -> NotOfDialect:
    hook = getattr(reader, "register_detail", None)
    detail = hook(tuple(reasons)) if callable(hook) else None
    return NotOfDialect(f"not of dialect {dialect} ({', '.join(reasons)})", detail=detail if isinstance(detail, str) else None)


def _auxiliary_unit(unit: ExecutionUnit, rows: Sequence[Mapping[str, Any]]) -> ExecutionUnit:
    """``unit`` with per-unit auxiliary artefacts (runner item R1/R2 of D.16.14): one ``ArtefactRef`` per row ``{role,
    label, sha256, size, origin, media?}``, role ``supporting``. The ids are placeholders (``x<n>``): the mapper numbers
    the artefacts it cites in its header."""
    aux = dict(unit.auxiliary)
    for n, row in enumerate(rows):
        aux[str(row["role"])] = ArtefactRef(id=f"x{n}", sha256=str(row["sha256"]), bytes=int(row["size"]),
                                            media=str(row.get("media", "application/octet-stream")),
                                            origin=Origin.from_json(row["origin"]), role="supporting", prov_primary="unknown")
    return ExecutionUnit(primary=unit.primary, auxiliary=aux, mode=unit.mode, ex=unit.ex)


class NoExecution(NotOfDialect):
    """A ``multi_execution`` file of the dialect that holds no execution (no located item; e.g. a cell with no run): the
    caller registers ``select.not_execution_artefact``, and no AER is written (no execution is invented; invariant 2)."""

    def __init__(self) -> None:
        super().__init__("the file holds no execution (0 located items)", detail="no execution in the file (0 located items)")


def multi_execution(reader: Any) -> bool:
    """Whether a whole-file reader declares one execution per located item (``multi_execution = True``; R-10k-1, D-320).
    Every other reader yields exactly one item per file, as before."""
    return getattr(reader, "multi_execution", False) is True


def rejected_rows(
    data: bytes, origin: Origin, *, profile_id: str, media: str = "application/json", limits: Any = None,
) -> list[dict[str, Any]]:
    """The rows of a ``multi_execution`` file that are not executions (D-321), as ``{code, detail, loc}`` in canonical
    locator order (JCS of the key locator), from the reader's optional ``rejected``; ``[]`` for a reader without it or
    for bytes the strict loader refuses (the file is then one degenerate AER, D-320). Runs only in the T1 ``map`` job:
    the parent validates every row before any is registered (``importer._Pipeline._seal_items``)."""
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits
    from agentprov.io.canonical import jcs_bytes

    profile = load_profile(profile_id)
    imp = profile.data.get("import", {})
    reader, mapper = _family_classes(str(imp.get("dialect")), str(imp.get("mapper")))
    hook = getattr(reader, "rejected", None)
    if not multi_execution(reader) or not callable(hook):
        return []
    limits = limits or IngestLimits()
    sniff = reader.sniff(data, label="", limits=limits)
    artefact = ArtefactRef(id="a0", sha256=sha256_hex(data), bytes=len(data), media=media, origin=origin, role="primary",
                           prov_primary=mapper.prov_primary(sniff.flags if sniff.match else frozenset()))
    try:
        rows = [{"code": r.code, "detail": r.detail, "loc": r.locator.key()} for r in hook(data, artefact, limits=limits)]
    except (IngestError, MalformedArtefact):
        return []
    return sorted(rows, key=lambda row: jcs_bytes(row["loc"]))


class NotSelected(AgentProvError):
    """A recognised artefact the profile assigns to another part (``[import] variant_labels``; D.6.12 item 6): the caller
    records the register row ``code`` (``select.dialect_planned``) instead of a unit (D.2.8 case 4)."""

    code = "select.dialect_planned"


def variant_part(profile: SourceProfile, variant: str | None) -> str | None:
    """The part label ``[import] variant_labels`` gives ``variant`` (an ``.incomplete`` variant takes its base's), or
    ``None`` when the profile labels no variants or not this one."""
    labels = profile.data.get("import", {}).get("variant_labels", {})
    if not labels or variant is None:
        return None
    found = labels.get(variant, labels.get(variant.removesuffix(".incomplete")))
    return str(found) if found is not None else None


def own_pin_part(profile: SourceProfile, part: str) -> bool:
    """A part with a pin of its own that ``variant_labels`` names for no variant: it selects every file of its pin
    (``variant_labels`` splits only the files of a pin several parts share; regeneration-batch item 95, R-10j-2)."""
    labels = profile.data.get("import", {}).get("variant_labels", {})
    return part not in set(labels.values()) and any(
        p.get("part") == part for p in profile.data.get("source", {}).get("pins", ()))


def own_pin_commits(profile: SourceProfile, part: str) -> frozenset[str]:
    """The git commits of the pins of an own-pin part (:func:`own_pin_part`) of a profile that splits a shared pin by
    ``variant_labels``; empty for any other part (a profile without ``variant_labels`` selects every file it is given)."""
    if not profile.data.get("import", {}).get("variant_labels") or not own_pin_part(profile, part):
        return frozenset()
    return frozenset(str(p["commit"]) for p in profile.data.get("source", {}).get("pins", ())
                     if p.get("part") == part and p.get("kind", "git") == "git" and "commit" in p)


def _context_unit(unit: ExecutionUnit, context: Sequence[Mapping[str, Any]]) -> ExecutionUnit:
    """``unit`` with the import's context artefacts as auxiliary refs ``context:<label>`` (role ``supporting``)."""
    aux = dict(unit.auxiliary)
    for n, row in enumerate(context):
        aux[f"context:{row['label']}"] = ArtefactRef(id=f"c{n}", sha256=str(row["sha256"]), bytes=int(row["size"]),
                                                     media="application/octet-stream",
                                                     origin=Origin.from_json(row["origin"]), role="supporting",
                                                     prov_primary="unknown")
    return ExecutionUnit(primary=unit.primary, auxiliary=aux, ex=unit.ex)


def map_artefact_units(
    data: bytes,
    origin: Origin,
    *,
    profile_id: str,
    media: str = "application/json",
    limits: Any = None,
    registry: RuleRegistry | None = None,
    part: str | None = None,
    context: Sequence[Mapping[str, Any]] = (),
    context_bytes: Mapping[str, bytes] | None = None,
    auxiliary: Sequence[Mapping[str, Any]] = (),
    auxiliary_bytes: Mapping[str, bytes] | None = None,
    blob_bytes: Mapping[str, bytes] | None = None,
) -> list[tuple[MapOutcome, ExecutionUnit]]:
    """:func:`map_artefact_total` for a ``multi_execution`` reader (R-10k-1, D-320): one outcome per located item, in
    the reader's order, each with its own execution id (the item's locator enters the source key, HL H.7.1).

    Bytes that fail the strict loader still give **one** degenerate outcome for the whole file (document-root locator).
    A file of the dialect with no item raises :class:`NoExecution`. Everything else is as in :func:`map_artefact_total`;
    ``context``, ``auxiliary`` and ``blob_bytes`` are offered to every unit of the file. A reader that does not declare
    ``multi_execution`` gets the single-item rule (a list of one).
    """
    return _map_total(data, origin, profile_id=profile_id, media=media, limits=limits, registry=registry, part=part,
                      context=context, context_bytes=context_bytes, auxiliary=auxiliary, auxiliary_bytes=auxiliary_bytes,
                      blob_bytes=blob_bytes, per_item=None)


def map_artefact_total(
    data: bytes,
    origin: Origin,
    *,
    profile_id: str,
    media: str = "application/json",
    limits: Any = None,
    registry: RuleRegistry | None = None,
    part: str | None = None,
    context: Sequence[Mapping[str, Any]] = (),
    context_bytes: Mapping[str, bytes] | None = None,
    auxiliary: Sequence[Mapping[str, Any]] = (),
    auxiliary_bytes: Mapping[str, bytes] | None = None,
    blob_bytes: Mapping[str, bytes] | None = None,
) -> tuple[MapOutcome, ExecutionUnit]:
    """:func:`map_artefact` for the import pipeline: every in-scope artefact ends in a sealed outcome (D.2.8).

    Bytes that fail the strict loader (an ``ingest.*`` sniff reason, or an ``IngestError``/``MalformedArtefact`` while
    parsing) give a degenerate outcome with ``unparseable_artefact`` and the code in ``detail``. Valid JSON that is not
    of the dialect raises ``MalformedArtefact``: the caller records ``select.not_execution_artefact`` (D.2.8 case 4). A
    variant the profile's ``variant_labels`` assign to a part other than ``part`` raises :class:`NotSelected`.
    ``context`` rows (``{label, sha256, size, origin}``) are handed to a mapper that ``consumes_context`` as auxiliary
    artefacts ``context:<label>``, with their bytes from ``context_bytes`` (a lazy mapping by label is fine).
    ``auxiliary`` rows (``{role, label, sha256, size, origin}``; runner items R1/R2 of D.16.14, a reader with
    ``auxiliary_for``) become the unit's auxiliary artefacts by role, with their bytes from ``auxiliary_bytes`` (by role,
    lazy). ``blob_bytes`` (D-203) holds the blob files offered to the unit as ``blob:<hex>`` (lazy): the mapper may open
    them to check a ``$blob`` reference; they are not artefacts of the unit (no ``ArtefactRef``; the AER references them
    by digest, C.11.5). Valid input of another kind raises :class:`NotOfDialect` with the reader's register detail.
    """
    return _map_total(data, origin, profile_id=profile_id, media=media, limits=limits, registry=registry, part=part,
                      context=context, context_bytes=context_bytes, auxiliary=auxiliary, auxiliary_bytes=auxiliary_bytes,
                      blob_bytes=blob_bytes, per_item=False)[0]


def _map_total(
    data: bytes,
    origin: Origin,
    *,
    profile_id: str,
    media: str,
    limits: Any,
    registry: RuleRegistry | None,
    part: str | None,
    context: Sequence[Mapping[str, Any]],
    context_bytes: Mapping[str, bytes] | None,
    auxiliary: Sequence[Mapping[str, Any]],
    auxiliary_bytes: Mapping[str, bytes] | None,
    blob_bytes: Mapping[str, bytes] | None,
    per_item: bool | None,
) -> list[tuple[MapOutcome, ExecutionUnit]]:
    """The body of :func:`map_artefact_total` (``per_item=False``: exactly one item, else a degenerate outcome) and of
    :func:`map_artefact_units` (``per_item=None``: one outcome per item when the reader declares ``multi_execution``)."""
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits

    profile = load_profile(profile_id)
    imp = profile.data.get("import", {})
    dialect, mapper_id = str(imp.get("dialect")), str(imp.get("mapper"))
    reader, mapper = _family_classes(dialect, mapper_id)
    if per_item is None:
        per_item = multi_execution(reader)
    limits = limits or IngestLimits()
    rules = registry or RuleRegistry.default()
    sha, size = sha256_hex(data), len(data)

    def degenerate(code: str, variant: str | None) -> list[tuple[MapOutcome, ExecutionUnit]]:
        unit = degenerate_unit(sha, size, origin, profile=profile, mapper=mapper, media=media, variant=variant)
        mapping = mapping_id(mapper.mapper_id, profile.id)
        ex = import_execution_id(mapping, sha, unit.primary.locator.key())
        return [(_degenerate(unit, mapper, MapContext(profile, rules, mapping, ex), "unparseable_artefact", code), unit)]

    sniff = reader.sniff(data, label="", limits=limits)
    if not sniff.match:
        loader = [r for r in sniff.reasons if r.startswith("ingest.")]
        if loader:
            return degenerate(loader[0], None)
        raise _not_of_dialect(reader, dialect, sniff.reasons)
    owner = variant_part(profile, sniff.variant)
    pins = own_pin_commits(profile, part) if part is not None else frozenset()
    if pins:
        # an own-pin part selects the files of its pin only, never those of another commit (bug pass NF-30; fail closed)
        if (origin.data.get("commit") if origin.kind == "git" else None) not in pins:
            raise NotSelected(f"part {part} selects the files of its own pin; this file's origin is not that commit")
    elif part is not None and owner is not None and owner != part:
        raise NotSelected(f"variant {sniff.variant} belongs to part {owner}, not {part}")
    primary = mapper.prov_primary(sniff.flags)
    artefact = ArtefactRef(id="a0", sha256=sha, bytes=size, media=media, origin=origin, role="primary",
                           prov_primary=primary)
    try:
        items = list(reader.parse(data, artefact, limits=limits))
    except IngestError as exc:
        return degenerate(exc.code, sniff.variant)
    except MalformedArtefact as exc:
        return degenerate(exc.code, sniff.variant)
    if per_item and not items:
        raise NoExecution()
    if not per_item and len(items) != 1:
        return degenerate(MalformedArtefact.code, sniff.variant)
    return [_map_item(item, mapper, profile, rules, context=context, context_bytes=context_bytes, auxiliary=auxiliary,
                      auxiliary_bytes=auxiliary_bytes, blob_bytes=blob_bytes, source=data, limits=limits)
            for item in items]


def _map_item(
    item: LocatedItem, mapper: Any, profile: SourceProfile, rules: RuleRegistry, *,
    context: Sequence[Mapping[str, Any]], context_bytes: Mapping[str, bytes] | None,
    auxiliary: Sequence[Mapping[str, Any]], auxiliary_bytes: Mapping[str, bytes] | None,
    blob_bytes: Mapping[str, bytes] | None, source: bytes | Callable[[], bytes] | None, limits: Any,
) -> tuple[MapOutcome, ExecutionUnit]:
    """Map one located item of a whole file, with the unit's auxiliary, context and blob inputs (shared by the byte and
    the streamed per-item paths, D-320 and D-323)."""
    blobs: Mapping[str, bytes] = blob_bytes or {}
    unit = ExecutionUnit(primary=item)
    if auxiliary:
        unit = _auxiliary_unit(unit, auxiliary)
        return map_unit(unit, mapper, profile, registry=rules, auxiliary=_Chain(auxiliary_bytes or {}, blobs),
                        source=source, limits=limits), unit
    if context and getattr(mapper, "consumes_context", False):
        unit = _context_unit(unit, context)
        given = context_bytes or {}
        aux = _Lazy({f"context:{row['label']}": str(row["label"]) for row in context}, given)
        return map_unit(unit, mapper, profile, registry=rules, auxiliary=_Chain(aux, blobs), source=source,
                        limits=limits), unit
    return map_unit(unit, mapper, profile, registry=rules, auxiliary=blobs or None, source=source, limits=limits), unit


def streams(reader: Any) -> bool:
    """Whether a ``multi_execution`` reader streams its primary (D-323, RB-1): it defines ``sniff_stream`` and
    ``parse_stream`` over a seekable handle, so the map job never reads the whole document into memory."""
    return multi_execution(reader) and callable(getattr(reader, "sniff_stream", None)) and callable(
        getattr(reader, "parse_stream", None))


class _Inputs(Mapping[str, bytes]):
    """A T1 job's context inputs by label (input index), read on first access."""

    def __init__(self, index: Mapping[str, int], read: Any) -> None:
        self._index, self._read = dict(index), read

    def __getitem__(self, label: str) -> bytes:
        return bytes(self._read(self._index[label]))

    def __iter__(self) -> Any:
        return iter(self._index)

    def __len__(self) -> int:
        return len(self._index)


class _Chain(Mapping[str, bytes]):
    """Two read-only byte mappings as one (the unit's auxiliary or context bytes, then its blob files; D-203). Lazy
    mappings stay lazy: a key is looked up, never read, until the mapper opens it."""

    def __init__(self, first: Mapping[str, bytes], second: Mapping[str, bytes]) -> None:
        self._first, self._second = first, second

    def __getitem__(self, key: str) -> bytes:
        try:
            return self._first[key]  # one lookup: ``in`` on a lazy mapping would read the bytes once more
        except KeyError:
            return self._second[key]

    def __iter__(self) -> Any:
        return iter(dict.fromkeys([*self._first, *self._second]))

    def __len__(self) -> int:
        return len(dict.fromkeys([*self._first, *self._second]))


class _Lazy(Mapping[str, bytes]):
    """Auxiliary bytes by role, read from ``source`` (by label) only when the mapper opens one."""

    def __init__(self, roles: Mapping[str, str], source: Mapping[str, bytes]) -> None:
        self._roles, self._source = dict(roles), source

    def __getitem__(self, role: str) -> bytes:
        return self._source[self._roles[role]]

    def __iter__(self) -> Any:
        return iter(self._roles)

    def __len__(self) -> int:
        return len(self._roles)


# ------------------------------------------------------------------------------------------------ T1 job
def job_map(ctx: Any) -> dict[str, Any]:
    """T1 job ``map``. Params: ``profile`` (id), ``origin`` (C.3.12 object), optional ``media``. Input 0: the artefact.

    Frames: ``{"record": …}`` per AER record in serialisation order, then ``{"seal": {…}}``. Counters: ``records``.

    Optional params of the import pipeline: ``limits`` (an ``IngestLimits`` record; the effective tier-1 limits),
    ``mode`` = ``"total"`` (:func:`map_artefact_total`; a non-dialect artefact emits ``{"not_dialect": reasons}``, plus
    ``"detail"`` when the reader names a register detail, and no record; ``auxiliary`` rows ``[{role, label, sha256, size,
    origin}]`` are inputs after the context inputs, in the same order; ``blobs`` rows ``[{sha256, size}]`` (D-203) are
    inputs after those, opened by the mapper as ``blob:<hex>``) or ``"container"`` (``members``: the selected member objects of one container, ``[{label, sha256, size,
    origin}]``, inputs in the same order; see :func:`_job_map_container`).

    ``per_item`` (``total`` mode, set by the importer only for a ``multi_execution`` reader; R-10k-1, D-320):
    :func:`map_artefact_units`; every outcome is framed after a ``{"unit": {"sha256", "loc"}}`` frame (``loc`` is the
    item's key locator), as in ``container`` mode (:func:`split_unit_frames`). A whole-file degenerate outcome is one
    such unit with the document-root locator. Counters: ``units``, ``records``, ``degenerate``. D-321: the rows of
    :func:`rejected_rows` come first, one ``{"register": {"code", "detail", "loc"}}`` frame each (none for a whole-file
    degenerate outcome); for a file with no execution they replace the ``not_dialect`` frame when there are any.
    """
    from agentprov.ingest.limits import IngestLimits

    params = ctx.params
    limits = IngestLimits(**params["limits"]) if "limits" in params else None
    mode = params.get("mode")
    if mode == "container":
        return _job_map_container(ctx, limits)
    if mode == "total" and params.get("per_item") and params.get("stream"):
        return _job_map_stream(ctx, limits)
    data = ctx.read_input(0)
    origin = Origin.from_json(params["origin"])
    media = str(params.get("media", "application/json"))
    if mode == "total":
        context = list(params.get("context", ()))
        source = _Inputs({str(row["label"]): 1 + n for n, row in enumerate(context)}, ctx.read_input)
        auxiliary = list(params.get("auxiliary", ()))
        aux_source = _Inputs({str(row["role"]): 1 + len(context) + n for n, row in enumerate(auxiliary)}, ctx.read_input)
        blobs = list(params.get("blobs", ()))
        first_blob = 1 + len(context) + len(auxiliary)
        blob_source = _Inputs({f"blob:{row['sha256']}": first_blob + n for n, row in enumerate(blobs)}, ctx.read_input)
        pairs: list[tuple[MapOutcome, ExecutionUnit]] | None = None
        rows: list[dict[str, Any]] = []
        try:
            if params.get("per_item"):
                try:
                    pairs = map_artefact_units(data, origin, profile_id=str(params["profile"]), media=media,
                                               limits=limits, part=params.get("part"), context=context,
                                               context_bytes=source, auxiliary=auxiliary, auxiliary_bytes=aux_source,
                                               blob_bytes=blob_source)
                except NotOfDialect:
                    # D-321: valid input with no execution may still be classified row by row by the reader
                    rows = rejected_rows(data, origin, profile_id=str(params["profile"]), media=media, limits=limits)
                    if not rows:
                        raise
                    pairs = []
                else:
                    whole = len(pairs) == 1 and pairs[0][0].degenerate and pairs[0][1].primary.locator.key() == {"p": ""}
                    if not whole:
                        rows = rejected_rows(data, origin, profile_id=str(params["profile"]), media=media, limits=limits)
            else:
                outcome = map_artefact_total(data, origin, profile_id=str(params["profile"]), media=media, limits=limits,
                                             part=params.get("part"), context=context, context_bytes=source,
                                             auxiliary=auxiliary, auxiliary_bytes=aux_source, blob_bytes=blob_source)[0]
        except NotSelected as exc:
            ctx.emit({"select": {"code": exc.code, "detail": str(exc)[:200]}})
            return {"records": 0, "degenerate": 0}
        except MalformedArtefact as exc:
            frame: dict[str, Any] = {"not_dialect": str(exc)[:200]}
            if isinstance(exc, NotOfDialect) and exc.detail is not None:
                frame["detail"] = exc.detail[:200]
            ctx.emit(frame)
            return {"records": 0, "degenerate": 0}
        if pairs is not None:
            for row in rows:
                ctx.emit({"register": row})
            for item_outcome, unit in pairs:
                ctx.emit({"unit": {"sha256": unit.primary.artefact.sha256, "loc": unit.primary.locator.key()}})
                for item_frame in item_outcome.to_frames():
                    ctx.emit(item_frame)
                item_outcome.emit_carved(ctx)  # D-218: members, kept apart from the unit frames
            return {"units": len(pairs), "records": sum(len(o.records) for o, _u in pairs),
                    "degenerate": sum(int(o.degenerate) for o, _u in pairs), "rejected": len(rows)}
    else:
        outcome = map_artefact(data, origin, profile_id=str(params["profile"]), media=media, limits=limits)[0]
    for frame in outcome.to_frames():
        ctx.emit(frame)
    outcome.emit_carved(ctx)
    return {"records": len(outcome.records), "degenerate": int(outcome.degenerate)}


def _total_inputs(ctx: Any) -> dict[str, Any]:
    """The ``total`` job's per-unit inputs by kind: context, auxiliary and blob rows with their lazy byte mappings."""
    params = ctx.params
    context = list(params.get("context", ()))
    auxiliary = list(params.get("auxiliary", ()))
    blobs = list(params.get("blobs", ()))
    first_blob = 1 + len(context) + len(auxiliary)
    return {
        "context": context,
        "context_bytes": _Inputs({str(row["label"]): 1 + n for n, row in enumerate(context)}, ctx.read_input),
        "auxiliary": auxiliary,
        "auxiliary_bytes": _Inputs({str(row["role"]): 1 + len(context) + n for n, row in enumerate(auxiliary)},
                                   ctx.read_input),
        "blob_bytes": _Inputs({f"blob:{row['sha256']}": first_blob + n for n, row in enumerate(blobs)}, ctx.read_input),
    }


def _job_map_stream(ctx: Any, limits: Any) -> dict[str, Any]:
    """The ``per_item`` ``total`` job of a streaming reader (D-323, RB-1; D-320 framing).

    Store-first: the primary is opened with ``ctx.open_input(0)``, which hashes the whole stored object and fails the job
    on a mismatch before ``sniff_stream`` or ``parse_stream`` sees a byte (G.4.5; objects are 0444 and the worker cannot
    write files, so the bytes parsed are the bytes hashed). Each streamed item is mapped and framed at once (bounded
    memory in the worker; the parent still holds the job's frames); the mapper may carve from the stored primary through
    a lazy reader (D-218). Classification is :func:`map_artefact_units`'s: a loader reason seals the file whole, valid
    input of another kind is ``not_dialect`` (or its rejected rows, ``rejected_stream``), a variant of another part is
    ``select``. A failure while streaming emits ``{"abort": {"issue", "code", "variant"}}`` last: the parent then keeps
    nothing of the file but one degenerate AER (D-320 whole-file rule), so a file is never half imported."""
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits

    params = ctx.params
    profile = load_profile(str(params["profile"]))
    imp = profile.data.get("import", {})
    dialect = str(imp.get("dialect"))
    reader, mapper = _family_classes(dialect, str(imp.get("mapper")))
    if not streams(reader):
        raise AgentProvError("the stream parameter was set for a reader that does not stream", code="adapter.job_incomplete")
    limits = limits or IngestLimits()
    rules = RuleRegistry.default()
    origin = Origin.from_json(params["origin"])
    media = str(params.get("media", "application/json"))
    sha = str(ctx.inputs[0]["sha256"])
    inputs = _total_inputs(ctx)
    source = _input_reader(ctx, 0)
    mapping = mapping_id(mapper.mapper_id, profile.id)

    def emit_unit(outcome: MapOutcome, unit: ExecutionUnit) -> None:
        ctx.emit({"unit": {"sha256": unit.primary.artefact.sha256, "loc": unit.primary.locator.key()}})
        for frame in outcome.to_frames():
            ctx.emit(frame)
        outcome.emit_carved(ctx)

    def rows_of(handle: Any, artefact: ArtefactRef) -> list[dict[str, Any]]:
        hook = getattr(reader, "rejected_stream", None)
        if not callable(hook):
            return []
        handle.seek(0)
        try:
            return [{"code": r.code, "detail": r.detail, "loc": r.locator.key()}
                    for r in hook(handle, artefact, limits=limits)]
        except (IngestError, MalformedArtefact):
            return []

    with ctx.open_input(0) as handle:
        size = handle.seek(0, 2)
        handle.seek(0)
        sniff = reader.sniff_stream(handle, limits=limits)
        handle.seek(0)
        artefact = ArtefactRef(id="a0", sha256=sha, bytes=size, media=media, origin=origin, role="primary",
                               prov_primary=mapper.prov_primary(sniff.flags if sniff.match else frozenset()))
        if not sniff.match:
            loader = [r for r in sniff.reasons if r.startswith("ingest.")]
            if loader:
                unit = degenerate_unit(sha, size, origin, profile=profile, mapper=mapper, media=media)
                ex = import_execution_id(mapping, sha, unit.primary.locator.key())
                emit_unit(_degenerate(unit, mapper, MapContext(profile, rules, mapping, ex), "unparseable_artefact",
                                      loader[0]), unit)
                return {"units": 1, "degenerate": 1}
            rows = rows_of(handle, artefact)
            for row in rows:
                ctx.emit({"register": row})
            if not rows:
                error = _not_of_dialect(reader, dialect, sniff.reasons)
                frame: dict[str, Any] = {"not_dialect": str(error)[:200]}
                if error.detail is not None:
                    frame["detail"] = error.detail[:200]
                ctx.emit(frame)
            return {"units": 0, "rejected": len(rows)}
        owner = variant_part(profile, sniff.variant)
        part = params.get("part")
        if part is not None and owner is not None and owner != part:
            ctx.emit({"select": {"code": NotSelected.code,
                                 "detail": f"variant {sniff.variant} belongs to part {owner}, not {part}"[:200]}})
            return {"units": 0}
        units = degenerate = 0
        items = iter(reader.parse_stream(handle, artefact, limits=limits))
        while True:
            # only the reader's own iteration can abort the file; a failure to map an item is that item's degenerate
            # AER (map_unit), and a failure to emit (a worker frame or output limit) fails the job as on the byte path
            try:
                item = next(items)
            except StopIteration:
                break
            except (IngestError, MalformedArtefact) as exc:
                ctx.emit({"abort": {"issue": "unparseable_artefact", "code": exc.code, "variant": sniff.variant}})
                return {"units": units, "aborted": 1}
            except Exception:  # noqa: BLE001 - D.2.8: a reader defect while streaming aborts the file, never half of it
                ctx.emit({"abort": {"issue": "adapter_defect", "code": AdapterDefect.code, "variant": sniff.variant}})
                return {"units": units, "aborted": 1}
            outcome, unit = _map_item(item, mapper, profile, rules, source=source, limits=limits, **inputs)
            emit_unit(outcome, unit)
            units += 1
            degenerate += int(outcome.degenerate)
        rows = rows_of(handle, artefact)
        for row in rows:
            ctx.emit({"register": row})
        if not units and not rows:
            error = NoExecution()
            ctx.emit({"not_dialect": str(error)[:200], "detail": str(error.detail)[:200]})
        return {"units": units, "degenerate": degenerate, "rejected": len(rows)}


def _job_map_container(ctx: Any, limits: Any) -> dict[str, Any]:
    """Plan and map one expanded container (the reader's ``plan``; D.9.1). Frames, in plan order: ``{"register": {label,
    code, detail}}`` for every plan register row, then per unit ``{"unit": {"label", "sha256"}}`` followed by the unit's
    record frames and its seal frame."""
    from agentprov.ingest.limits import IngestLimits

    params = ctx.params
    profile = load_profile(str(params["profile"]))
    imp = profile.data.get("import", {})
    reader, mapper = _family_classes(str(imp.get("dialect")), str(imp.get("mapper")))
    listed = list(params["members"])
    index = {str(m["sha256"]): i for i, m in enumerate(listed)}
    members = [MemberRef(str(m["label"]), str(m["sha256"]), int(m["size"]), Origin.from_json(m["origin"])) for m in listed]
    plan = reader.plan(members, lambda sha: ctx.read_input(index[sha]), profile, limits=limits or IngestLimits())
    labels = {m.sha256: m.label for m in members}
    if params.get("plan_only"):  # D-529 pass 1: the planned units' labels only; nothing is mapped or registered
        for unit in plan.units:
            sha = unit.primary.artefact.sha256
            ctx.emit({"unit": {"label": labels.get(sha, ""), "sha256": sha}})
        return {"units": len(plan.units), "degenerate": 0}
    wanted = set(params["units"]) if "units" in params else None  # D-529 pass 2: the sampled units' labels
    for row in plan.register:
        ctx.emit({"register": {"code": str(row.get("code")), "detail": str(row.get("detail", ""))[:200],
                               "label": str(row.get("label", ""))}})
    degenerate = 0
    for unit in plan.units:
        sha = unit.primary.artefact.sha256
        if wanted is not None and labels.get(sha, "") not in wanted:
            continue
        outcome = map_unit(unit, mapper, profile, auxiliary=plan.auxiliary, source=_input_reader(ctx, index.get(sha)),
                           limits=limits)
        degenerate += int(outcome.degenerate)
        ctx.emit({"unit": {"label": labels.get(sha, ""), "sha256": sha}})
        for frame in outcome.to_frames():
            ctx.emit(frame)
        outcome.emit_carved(ctx)
    return {"units": len(plan.units), "degenerate": degenerate}


def _input_reader(ctx: Any, position: int | None) -> Callable[[], bytes] | None:
    """A lazy reader of a job input (the member a container unit is planned on; D-218 carving reads it on demand)."""
    if position is None:
        return None
    return lambda: bytes(ctx.read_input(position))


def split_unit_frames(frames: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], list[Mapping[str, Any]]]]]:
    """Split the frames of a ``container`` (or ``per_item`` ``total``) map job into its register rows and ``(unit header,
    unit frames)`` pairs."""
    register: list[dict[str, Any]] = []
    units: list[tuple[dict[str, Any], list[Mapping[str, Any]]]] = []
    for frame in frames:
        if "register" in frame:
            register.append(dict(frame["register"]))
        elif "unit" in frame:
            units.append((dict(frame["unit"]), []))
        elif units:
            units[-1][1].append(frame)
        else:
            raise AgentProvError(_FRAMING_ERROR, code="adapter.job_incomplete")
    return register, units


_FRAMING_ERROR: Final = "a container map job emitted a record before its unit frame"


@dataclass
class FrameSummary:
    """Pass 1 over the frames of one ``map`` result (D-414): what decides the file's fate, without keeping any record.

    ``rows`` and ``heads`` are what :func:`split_unit_frames` returns as register rows and unit headers, in order;
    ``framing_error`` is set exactly when it would raise (a frame that is neither a register row nor a unit header
    before the first unit header); ``abort``, ``not_dialect`` and ``select`` are the first such frame's value."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    heads: list[dict[str, Any]] = field(default_factory=list)
    framing_error: bool = False
    abort: dict[str, Any] | None = None
    not_dialect: dict[str, Any] | None = None
    select: Mapping[str, Any] | None = None
    #: memo of the importer's validated rejected-row entries (computed once per file, D-321)
    entries: Any = None
    entries_done: bool = False

    def require_framing(self) -> None:
        """Raise what :func:`split_unit_frames` raises for these frames, at the same point (before anything is sealed)."""
        if self.framing_error:
            raise AgentProvError(_FRAMING_ERROR, code="adapter.job_incomplete")


def summarise_unit_frames(frames: Iterable[Mapping[str, Any]]) -> FrameSummary:
    """Pass 1 (D-414): the :class:`FrameSummary` of ``frames``, one frame at a time."""
    summary = FrameSummary()
    for frame in frames:
        if "register" in frame:
            summary.rows.append(dict(frame["register"]))
        elif "unit" in frame:
            summary.heads.append(dict(frame["unit"]))
        elif not summary.heads:
            summary.framing_error = True
        if summary.abort is None and "abort" in frame:
            summary.abort = dict(frame["abort"])
        if summary.not_dialect is None and "not_dialect" in frame:
            summary.not_dialect = dict(frame)
        if summary.select is None and "select" in frame:
            summary.select = frame["select"]
    return summary


def iter_unit_frames(frames: Iterable[Mapping[str, Any]]) -> Iterator[tuple[dict[str, Any], list[Mapping[str, Any]]]]:
    """Pass 2 (D-414): ``(unit header, unit frames)`` pairs as :func:`split_unit_frames` makes them, one unit at a time.
    Register rows are skipped (pass 1 has them); call only after :meth:`FrameSummary.require_framing`."""
    head: dict[str, Any] | None = None
    unit: list[Mapping[str, Any]] = []
    for frame in frames:
        if "register" in frame:
            continue
        if "unit" in frame:
            if head is not None:
                yield head, unit
            head, unit = dict(frame["unit"]), []
        elif head is not None:
            unit.append(frame)
        else:
            raise AgentProvError(_FRAMING_ERROR, code="adapter.job_incomplete")
    if head is not None:
        yield head, unit


def outcome_from_frames(frames: Iterable[Mapping[str, Any]]) -> MapOutcome:
    """The :class:`MapOutcome` the frames of one unit carry (records, then the seal inputs)."""
    records: list[dict[str, Any]] = []
    seal: Mapping[str, Any] | None = None
    for frame in frames:
        if "record" in frame:
            records.append(dict(frame["record"]))
        elif "seal" in frame:
            seal = frame["seal"]
    if seal is None or not records:
        raise AgentProvError("a map job result has no records or no seal frame", code="adapter.job_incomplete")
    return MapOutcome(str(seal["ex"]), records, [dict(i) for i in seal["issues"]], list(seal["severities"]),
                      [dict(c) for c in seal["checks"]], bool(seal["degenerate"]), seal.get("error_code"))


def seal_job_result(frames: Iterable[Mapping[str, Any]], path: Path, *, registry: RuleRegistry | None = None) -> SealInfo:
    """Seal the frames of one ``map`` job result at ``path`` (the T0 write gate)."""
    return seal_outcome(outcome_from_frames(frames), path, registry=registry)
