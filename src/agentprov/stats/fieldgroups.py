"""The field groups of the information-loss table and their per-execution evaluation (C.3.16; O.3.5; R-57).

The groups are package data, ``field_groups.toml`` beside this module: O.3.5 owns the list of group names, C.3.16 the
record selectors and AER JSON Pointers. :func:`field_groups` loads and validates the file once (unknown keys, kinds or
pointers are refused, so a typo cannot silently drop a group); :func:`evaluate` applies it to the records of one AER.

**Statuses.** An occurrence's status is ``"O"``, ``"D"``, ``"I"`` or ``"unk:<reason>"`` (C.7.1). ``O:<party>`` counts as
``O``. :data:`STATUSES` lists them strongest first. The *weakest* of several occurrences is the one with the highest
:func:`weakness`: ``I`` is weaker than ``D``, which is weaker than ``O``, and every ``unk`` is weaker than ``I``; among
reasons, C.3.16 makes the *first* in C.7.1's order the weakest, so ``not_recorded`` is the weakest status of all. For an
"or" row the group takes the *strongest* alternative (lowest weakness); on a tie a declared status beats an undeclared
one (D-48).

**Undeclared.** A pointer that is absent with no ``unk`` entry covering it is not asserted (C.2.3). It never counts as
``O`` or ``D``: it is reported as ``unk:not_recorded`` and flagged *undeclared*, so the tables can count it separately.

Pure and deterministic: records in, plain data out; nothing is read from disk but the package's own TOML.
"""

from __future__ import annotations

import tomllib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any, Final

from agentprov.aer.evidence import effective_tag, is_prefix, tag_class
from agentprov.aer.locators import pointer_exists, pointer_get
from agentprov.aer.types import UNKNOWN_REASONS
from agentprov.errors import AgentProvError

__all__ = [
    "FIELD_GROUPS_RESOURCE",
    "O35_GROUPS",
    "STATUSES",
    "ExecutionFieldStatus",
    "FieldGroup",
    "FieldGroupError",
    "Occurrence",
    "Selector",
    "evaluate",
    "field_groups",
    "field_groups_bytes",
    "message_roles",
    "parse_field_groups",
    "weakness",
]

FIELD_GROUPS_RESOURCE: Final = "field_groups.toml"
#: The O.3.5 list of group names, in O.3.5's order (the paper's normative requirement on the TOML file).
O35_GROUPS: Final = (
    "ctx", "tooldefs", "model_req", "model_served", "sampling", "usage", "finish", "reasoning", "sysprompt", "t_model",
    "t_tool", "passes", "env", "callid", "link", "payload", "outcome_logged", "checker",
)  # fmt: skip
#: Every cell or occurrence status, strongest first (the column order of the tables).
STATUSES: Final = ("O", "D", "I", *(f"unk:{r}" for r in reversed(UNKNOWN_REASONS)))
_WEAKNESS: Final = {s: i for i, s in enumerate(STATUSES)}
#: The record kinds of C.2.2 a selector may name (the header and the seal carry no group fields).
_KINDS: Final = frozenset({
    "actor", "scope", "message", "model_call", "tool_execution", "decision", "state_change", "fixture", "judgement",
    "activity", "artefact"})  # fmt: skip
_PART_TYPES: Final = frozenset({"text", "reasoning", "tool_call", "tool_result", "blob", "file", "uri", "refusal", "other"})
_OCCURRENCE_KEYS: Final = frozenset({"id", "record", "where", "absent", "named_by", "refers", "parts", "pointer", "array", "fallback"})
_SELECTOR_KEYS: Final = frozenset({"record", "where", "absent", "pointer"})


type Roles = tuple[tuple[str, tuple[str, ...]], ...]


class FieldGroupError(AgentProvError):
    """``field_groups.toml`` is malformed (a defect of the installed package), or a record cannot be evaluated."""

    code = "stats.field_groups.invalid"
    exit_code = 70


def weakness(status: str) -> int:
    """The position of ``status`` in :data:`STATUSES` (0 = ``O``, the strongest); ``KeyError`` for an unknown status."""
    return _WEAKNESS[status]


# ------------------------------------------------------------------------------------------------ model
@dataclass(frozen=True, slots=True)
class Selector:
    """Records of kind ``record`` whose top-level string members equal ``where`` and that lack every ``absent`` member.

    As the target of ``named_by``/``refers``, ``pointer`` is the member that names the other record."""

    record: str
    where: tuple[tuple[str, str], ...] = ()
    absent: tuple[str, ...] = ()
    pointer: str = ""
    #: ``(role, (verbatim roles…))`` from ``[message_roles]``: a message ``role`` filter matches any listed role.
    roles: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def _accepts(self, key: str, value: str, actual: object) -> bool:
        if key == "role" and self.record == "message":
            for name, members in self.roles:
                if name == value:
                    return actual in members
        return actual == value

    def matches(self, rec: Mapping[str, Any]) -> bool:
        if rec.get("k") != self.record:
            return False
        if not all(self._accepts(key, value, rec.get(key)) for key, value in self.where):
            return False
        return not any(name in rec for name in self.absent)


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One occurrence source of a group alternative (one ``[[group.alternative.occurrence]]`` table)."""

    id: str
    select: Selector
    pointer: str
    named_by: Selector | None = None
    refers: Selector | None = None
    parts: str | None = None
    array: bool = False
    fallback: str | None = None

    @property
    def pointers(self) -> tuple[str, ...]:
        """The AER pointers this occurrence reads (``/parts/<k>`` written with ``<k>`` for part selections)."""
        base = "/parts/<k>" if self.parts is not None else ""
        out = [base + self.pointer]
        if self.fallback is not None:
            out.append(base + self.fallback)
        return tuple(out)


@dataclass(frozen=True, slots=True)
class FieldGroup:
    """A field group of O.3.5: its id, label, spec citation and its alternatives (each a tuple of occurrences)."""

    id: str
    label: str
    spec: str
    alternatives: tuple[tuple[Occurrence, ...], ...]

    @property
    def occurrences(self) -> tuple[Occurrence, ...]:
        return tuple(o for alt in self.alternatives for o in alt)

    @property
    def records(self) -> tuple[str, ...]:
        """The record kinds the group reads, sorted."""
        return tuple(sorted({o.select.record for o in self.occurrences}))

    @property
    def pointers(self) -> tuple[str, ...]:
        """The AER JSON Pointers of the group, in file order, unique (M.6 ``field_groups()``)."""
        return tuple(dict.fromkeys(p for o in self.occurrences for p in o.pointers))

    def to_json(self) -> dict[str, Any]:
        return {
            "alternatives": [[_occurrence_json(o) for o in alt] for alt in self.alternatives],
            "id": self.id,
            "label": self.label,
            "pointers": list(self.pointers),
            "spec": self.spec,
        }


def _selector_json(s: Selector) -> dict[str, Any]:
    out: dict[str, Any] = {"record": s.record}
    if s.where:
        out["where"] = dict(s.where)
    if s.absent:
        out["absent"] = list(s.absent)
    if s.pointer:
        out["pointer"] = s.pointer
    return out


def _occurrence_json(o: Occurrence) -> dict[str, Any]:
    out: dict[str, Any] = {"id": o.id, "pointer": o.pointer, **_selector_json(o.select)}
    for name in ("named_by", "refers"):
        sel = getattr(o, name)
        if sel is not None:
            out[name] = _selector_json(sel)
    if o.parts is not None:
        out["parts"] = o.parts
    if o.array:
        out["array"] = True
    if o.fallback is not None:
        out["fallback"] = o.fallback
    return out


# ------------------------------------------------------------------------------------------------ loading
def _pointer(value: object, what: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (value == "" and not empty) or (value != "" and not value.startswith("/")):
        raise FieldGroupError(f"{what}: a JSON Pointer")
    return value


def _where(value: object, what: str) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise FieldGroupError(f"{what}: where is a table of strings")
    return tuple(sorted(value.items()))


def _absent(value: object, what: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise FieldGroupError(f"{what}: absent is a list of member names")
    return tuple(value)


def _kind(value: object, what: str) -> str:
    if value not in _KINDS:
        raise FieldGroupError(f"{what}: record is a C.2.2 record kind")
    assert isinstance(value, str)
    return value


def _selector(value: object, what: str, roles: Roles) -> Selector:
    if not isinstance(value, dict) or not set(value) <= _SELECTOR_KEYS or "pointer" not in value:
        raise FieldGroupError(f"{what}: a selector is {{record, where?, absent?, pointer}}")
    return Selector(_kind(value.get("record"), what), _where(value.get("where"), what), _absent(value.get("absent"), what),
                    _pointer(value["pointer"], what), roles)  # fmt: skip


def _roles(value: object) -> Roles:
    if value is None:
        return ()
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and k and isinstance(v, list) and v and k in v and all(isinstance(r, str) and r for r in v)
        for k, v in value.items()
    ):
        raise FieldGroupError("field groups: [message_roles] maps a role to a list of verbatim roles that includes it")
    return tuple(sorted((k, tuple(v)) for k, v in value.items()))


def _occurrence(table: object, what: str, roles: Roles = ()) -> Occurrence:
    if not isinstance(table, dict) or not set(table) <= _OCCURRENCE_KEYS:
        raise FieldGroupError(f"{what}: unknown occurrence keys")
    oid = table.get("id")
    if not isinstance(oid, str) or not oid:
        raise FieldGroupError(f"{what}: an occurrence has an id")
    what = f"{what} {oid}"
    parts = table.get("parts")
    if parts is not None and parts not in _PART_TYPES:
        raise FieldGroupError(f"{what}: parts names a C.3.4.1 part type")
    record = _kind(table.get("record"), what)
    if parts is not None and record != "message":
        raise FieldGroupError(f"{what}: parts are selected from messages")
    array = table.get("array", False)
    if not isinstance(array, bool):
        raise FieldGroupError(f"{what}: array is a boolean")
    fallback = table.get("fallback")
    return Occurrence(
        id=oid,
        select=Selector(record, _where(table.get("where"), what), _absent(table.get("absent"), what), "", roles),
        pointer=_pointer(table.get("pointer"), what, empty=parts is not None),
        named_by=_selector(table["named_by"], what, roles) if "named_by" in table else None,
        refers=_selector(table["refers"], what, roles) if "refers" in table else None,
        parts=parts,
        array=array,
        fallback=None if fallback is None else _pointer(fallback, what),
    )


def parse_field_groups(data: bytes) -> tuple[FieldGroup, ...]:
    """Parse and validate a field-groups TOML document (see the file's header for the schema)."""
    return _parse(data)[0]


def _parse(data: bytes) -> tuple[tuple[FieldGroup, ...], Roles]:
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise FieldGroupError(f"field groups: not valid TOML ({type(exc).__name__})") from None
    if not {"version", "group"} <= set(doc) <= {"version", "group", "message_roles"} or doc["version"] != 1 \
            or not isinstance(doc["group"], list):
        raise FieldGroupError("field groups: a document is {version = 1, [message_roles], [[group]]}")
    roles = _roles(doc.get("message_roles"))
    groups: list[FieldGroup] = []
    seen: set[str] = set()
    for table in doc["group"]:
        if not isinstance(table, dict) or set(table) != {"id", "label", "spec", "alternative"}:
            raise FieldGroupError("field groups: a group is {id, label, spec, [[alternative]]}")
        gid = table["id"]
        if not isinstance(gid, str) or not isinstance(table["label"], str) or not isinstance(table["spec"], str):
            raise FieldGroupError("field groups: id, label and spec are strings")
        alternatives: list[tuple[Occurrence, ...]] = []
        if not isinstance(table["alternative"], list) or not table["alternative"]:
            raise FieldGroupError(f"field group {gid}: at least one alternative")
        for alt in table["alternative"]:
            if not isinstance(alt, dict) or set(alt) != {"occurrence"} or not isinstance(alt["occurrence"], list) or not alt["occurrence"]:
                raise FieldGroupError(f"field group {gid}: an alternative holds at least one occurrence")
            occurrences = tuple(_occurrence(o, f"field group {gid}", roles) for o in alt["occurrence"])
            for o in occurrences:
                if o.id in seen:
                    raise FieldGroupError(f"field group {gid}: duplicate occurrence id {o.id}")
                seen.add(o.id)
            alternatives.append(occurrences)
        groups.append(FieldGroup(gid, table["label"], table["spec"], tuple(alternatives)))
    ids = [g.id for g in groups]
    if len(set(ids)) != len(ids):
        raise FieldGroupError("field groups: duplicate group id")
    return tuple(groups), roles


def field_groups_bytes() -> bytes:
    """The bytes of the packaged ``field_groups.toml``."""
    return (resources.files("agentprov.stats") / FIELD_GROUPS_RESOURCE).read_bytes()


@cache
def _packaged() -> tuple[tuple[FieldGroup, ...], Roles]:
    groups, roles = _parse(field_groups_bytes())
    if tuple(g.id for g in groups) != O35_GROUPS:
        raise FieldGroupError("field_groups.toml does not hold the O.3.5 list of groups in order (c3-groups-agree)")
    return groups, roles


def field_groups() -> tuple[FieldGroup, ...]:
    """The packaged field groups (validated once; their ids must be O.3.5's list, in order)."""
    return _packaged()[0]


def message_roles() -> dict[str, tuple[str, ...]]:
    """The packaged ``[message_roles]`` grouping (role -> the verbatim roles it groups; D.16.17 item 3)."""
    return dict(_packaged()[1])


# ------------------------------------------------------------------------------------------------ evaluation
@dataclass(slots=True)
class ExecutionFieldStatus:
    """The field-group evaluation of one execution.

    ``cells`` maps a group id to ``(status, undeclared)`` for every group with at least one occurrence. ``occurrences``
    counts, per occurrence id, the ``(status, undeclared)`` pairs of its occurrences."""

    cells: dict[str, tuple[str, bool]] = field(default_factory=dict)
    occurrences: dict[str, Counter[tuple[str, bool]]] = field(default_factory=dict)


def _unk_reason(rec: Mapping[str, Any], pointer: str, *, below: bool = True) -> str | None:
    """The first C.7.1 reason among ``unk`` entries at ``pointer``, enclosing it, or (with ``below``) below it."""
    unk = rec.get("unk")
    if not isinstance(unk, Mapping):
        return None
    found = {reason for key, reason in unk.items()
             if isinstance(key, str) and (is_prefix(key, pointer) or (below and is_prefix(pointer, key)))}  # fmt: skip
    for reason in UNKNOWN_REASONS:
        if reason in found:
            return reason
    return None


def _status_at(rec: Mapping[str, Any], pointer: str) -> str:
    reason = _unk_reason(rec, pointer)
    if reason is not None:
        return f"unk:{reason}"
    try:
        return tag_class(effective_tag(rec, pointer))
    except ValueError:
        raise FieldGroupError("a record has no valid evidence tag at a group pointer", code="stats.aer.tag") from None


def _occurrence_statuses(rec: Mapping[str, Any], pointer: str, occ: Occurrence) -> list[tuple[str, bool]]:
    if not pointer_exists(rec, pointer):
        reason = _unk_reason(rec, pointer)
        if reason is not None:
            return [(f"unk:{reason}", False)]
        if occ.fallback is not None:
            alternative = pointer[: len(pointer) - len(occ.pointer)] + occ.fallback
            if pointer_exists(rec, alternative) or _unk_reason(rec, alternative) is not None:
                return [(_status_at(rec, alternative), False)]
        return [("unk:not_recorded", True)]
    value = pointer_get(rec, pointer)
    if occ.array and isinstance(value, list) and value and _unk_reason(rec, pointer, below=False) is None:
        return [(_status_at(rec, f"{pointer}/{i}"), False) for i in range(len(value))]
    return [(_status_at(rec, pointer), False)]


def _named(records: Sequence[Mapping[str, Any]], sel: Selector) -> set[str]:
    out: set[str] = set()
    for rec in records:
        if sel.matches(rec):
            try:
                value = pointer_get(rec, sel.pointer)
            except KeyError:
                continue
            if isinstance(value, str):
                out.add(value)
    return out


def _ids(records: Sequence[Mapping[str, Any]], sel: Selector) -> set[str]:
    return {r["id"] for r in records if sel.matches(r) and isinstance(r.get("id"), str)}


def _collect(records: Sequence[Mapping[str, Any]], occ: Occurrence) -> list[tuple[str, bool]]:
    candidates = [r for r in records if occ.select.matches(r)]
    if occ.named_by is not None:
        names = _named(records, occ.named_by)
        candidates = [r for r in candidates if r.get("id") in names]
    if occ.refers is not None:
        targets = _ids(records, Selector(occ.refers.record, occ.refers.where, occ.refers.absent, "", occ.refers.roles))
        kept = []
        for r in candidates:
            try:
                value = pointer_get(r, occ.refers.pointer)
            except KeyError:
                continue
            if isinstance(value, str) and value in targets:
                kept.append(r)
        candidates = kept
    out: list[tuple[str, bool]] = []
    for rec in candidates:
        if occ.parts is None:
            out.extend(_occurrence_statuses(rec, occ.pointer, occ))
            continue
        parts = rec.get("parts")
        if not isinstance(parts, list):
            continue
        for k, part in enumerate(parts):
            if isinstance(part, Mapping) and part.get("t") == occ.parts:
                out.extend(_occurrence_statuses(rec, f"/parts/{k}{occ.pointer}", occ))
    return out


def _weakest(items: Sequence[tuple[str, bool]]) -> tuple[str, bool]:
    status = max((s for s, _ in items), key=weakness)
    undeclared = status == "unk:not_recorded" and all(u for s, u in items if s == status)
    return status, undeclared


def evaluate(records: Sequence[Mapping[str, Any]], groups: Sequence[FieldGroup] | None = None) -> ExecutionFieldStatus:
    """Evaluate every field group over the records of one AER (header and seal may be included; they are not selected).

    The caller decides the population (C.3.16: ``unit == agent_execution`` and ``execution_observed``)."""
    result = ExecutionFieldStatus()
    body = [r for r in records if isinstance(r, Mapping) and r.get("k") in _KINDS]
    for group in groups if groups is not None else field_groups():
        options: list[tuple[str, bool]] = []
        for alternative in group.alternatives:
            items: list[tuple[str, bool]] = []
            for occ in alternative:
                found = _collect(body, occ)
                result.occurrences[occ.id] = Counter(found)
                items.extend(found)
            if items:
                options.append(_weakest(items))
        if options:
            # the strongest alternative; on a tie a declared status beats an undeclared one
            result.cells[group.id] = min(options, key=lambda o: (weakness(o[0]), o[1]))
    return result
