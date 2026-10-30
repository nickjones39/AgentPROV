"""The semantics profile ``geminicli.tools`` version 1 (docs/architecture D.23.8; C.14; EF E.7.1, E.7.3).

Data plus small pure functions over one AER. What the profile yields, per record in AER file order (the yield order is
the annotation order):

- **fixture**: ``integrity`` of the ``environment_seed`` (the task workspace; ``unknown`` by the profile's data);
- **message**, per part: the user message (actor ``user``, the harness's task prompt) ``trusted``; agent output (actor
  ``agent``) ``trusted`` and, on a ``tool_call`` part, its ``role``; tool results: ``integrity`` of the producing tool,
  fail-closed;
- **tool_execution**: ``role``;
- **judgement**: ``outcome`` ``geminicli.misalignment_elicited`` for ``elicited`` (origin ``checker``), holding iff true.

An annotation's ``ev`` is ``weakest(premise tags, rule classes)`` (C.6.5 rule 3). Reads only the AER; standard library
and ``agentprov.{aer,sem}``.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from agentprov.aer.evidence import effective_tag, weakest
from agentprov.aer.rules import load_catalogue
from agentprov.aer.types import Json
from agentprov.sem.profiles import SemanticsProfileError
from agentprov.sem.types import INTEGRITY_VALUES, ROLE_VALUES, Annotation, Premise, TaintPolicy

if TYPE_CHECKING:
    from agentprov.aer.reader import AerDocument

__all__ = ["CITED_RULES", "DATA_FILES", "PROFILE_ID", "GeminiToolsProfile", "build"]

PROFILE_ID: Final = "geminicli.tools"
PROFILE_VERSION: Final = 1
DATA_FILES: Final = ("profile.toml", "tools.toml")
EVIDENCE: Final = ("observed", "code")

R_TABLE: Final = "geminicli.tool_table@1"
R_UNKNOWN: Final = "geminicli.unknown_tool@1"
R_AGENT: Final = "geminicli.integrity_agent_output@1"
R_USER: Final = "geminicli.integrity_user_prompt@1"
R_SEED: Final = "geminicli.integrity_workspace_seed@1"
R_ELICITED: Final = "geminicli.misalignment_meaning@1"
R_TAINT: Final = "geminicli.taint_sink_untrusted@1"

#: Every rule this profile cites (the catalogue test checks each exists, is active and has the class its annotations
#: need).
CITED_RULES: Final = (R_TABLE, R_UNKNOWN, R_AGENT, R_USER, R_SEED, R_ELICITED, R_TAINT)
NS: Final[Mapping[str, Json]] = MappingProxyType({})


class ProfileDataError(SemanticsProfileError):
    code = "sem.profile_data"


@dataclass(frozen=True, slots=True)
class Tables:
    """The parsed data files: the tool table, fixture integrity, the outcome claim and the taint policy."""

    tools: Mapping[str, tuple[tuple[str, ...], str]]  # name -> (roles, output integrity)
    fixtures: Mapping[str, str]  # fixture kind -> integrity
    outcomes: Mapping[str, Any]
    taint: TaintPolicy


def _strings(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProfileDataError(f"{where}: an array of strings is required")
    return list(value)


def _label(entry: Mapping[str, Any], where: str) -> tuple[tuple[str, ...], str]:
    roles = tuple(_strings(entry.get("roles"), where))
    evidence = _strings(entry.get("evidence"), where)
    integrity = entry.get("integrity")
    if not roles or any(r not in ROLE_VALUES for r in roles) or len(set(roles)) != len(roles) or \
            ("unknown" in roles and len(roles) > 1):
        raise ProfileDataError(f"{where}: roles must be distinct values of the E.7.1 vocabulary, unknown alone")
    if integrity not in INTEGRITY_VALUES or integrity == "trusted":
        raise ProfileDataError(f"{where}: output integrity is untrusted or unknown (no tool code is verified)")
    if not evidence or any(e not in EVIDENCE for e in evidence) or len(set(evidence)) != len(evidence):
        raise ProfileDataError(f"{where}: evidence must be distinct values of {EVIDENCE}")
    if not isinstance(entry.get("reason"), str) or not entry["reason"]:
        raise ProfileDataError(f"{where}: a reason is required")
    return roles, str(integrity)


def parse_tables(files: Mapping[str, bytes]) -> Tables:
    missing = [n for n in DATA_FILES if n not in files]
    extra = sorted(set(files) - set(DATA_FILES))
    if missing or extra:
        raise ProfileDataError(f"geminicli.tools@1 data files: missing {missing}, unexpected {extra}")
    doc = {name: tomllib.loads(files[name].decode("utf-8")) for name in DATA_FILES}
    tools: dict[str, tuple[tuple[str, ...], str]] = {}
    for entry in doc["tools.toml"].get("tool", []):
        name = str(entry.get("name"))
        if name in tools:
            raise ProfileDataError(f"tool {name!r}: repeated")
        tools[name] = _label(entry, f"tool {name!r}")
    prof = doc["profile.toml"]
    fixtures = {str(k): str(v) for k, v in prof.get("fixtures", {}).items()}
    if any(v not in INTEGRITY_VALUES for v in fixtures.values()):
        raise ProfileDataError("fixtures: integrity values of the C.14 vocabulary only")
    taint = prof["taint"]
    policy = TaintPolicy(str(taint["rule"]), frozenset(_strings(taint["subject_roles"], "taint")),
                         frozenset(_strings(taint["object_integrity"], "taint")))
    return Tables(MappingProxyType(tools), MappingProxyType(fixtures), MappingProxyType(dict(prof["outcomes"])), policy)


@dataclass(frozen=True)
class GeminiToolsProfile:
    """``geminicli.tools`` at version 1 (satisfies :class:`agentprov.sem.types.SemanticsProfile`)."""

    id: str
    version: int
    sha256: str
    tables: Tables
    classes: Mapping[str, str]
    rules: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({"geminicli": 1}))
    ns: Mapping[str, Json] = field(default_factory=lambda: NS)
    taint_policy: TaintPolicy | None = None

    # ------------------------------------------------------------------------------------------ helpers
    def _ann(self, aer: AerDocument, target: str, type_: str, value: Json, rules: Sequence[str],
             premises: Sequence[Premise]) -> Annotation:
        tags = [self.classes[r.split("#", 1)[0]] for r in rules]
        for p in premises:
            record = aer.get(p.id.split("#", 1)[0])
            if record is None:
                continue
            pointer = p.p if "#" not in p.id else f"/parts/{p.id.split('#', 1)[1]}{p.p}"
            tags.append(effective_tag(record, pointer))
        return Annotation(target, type_, value, weakest(*tags), tuple(rules), tuple(premises))  # type: ignore[arg-type]

    def tool_label(self, name: object) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        """``(roles, output integrity, rules)`` of a tool by name; fail-closed for a name no table lists."""
        found = self.tables.tools.get(name) if isinstance(name, str) else None
        if found is None:
            return ("unknown",), "unknown", (R_UNKNOWN,)
        return found[0], found[1], (R_TABLE,)

    # ------------------------------------------------------------------------------------------ annotate
    def annotate(self, aer: AerDocument) -> Iterator[Annotation]:
        for record in aer.records[1:]:
            kind = record.get("k")
            rid = str(record.get("id"))
            if kind == "fixture":
                integrity = self.tables.fixtures.get(str(record.get("kind")))
                if integrity is not None:
                    yield self._ann(aer, rid, "integrity", integrity, (R_SEED,), (Premise(rid, "/kind"),))
            elif kind == "message":
                yield from self._message(aer, record)
            elif kind == "tool_execution":
                roles, _integrity, rules = self.tool_label(record.get("name"))
                yield self._ann(aer, rid, "role", list(roles), rules, (Premise(rid, "/name"),))
            elif kind == "judgement":
                found = self._outcome(aer, record)
                if found is not None:
                    yield found

    def _message(self, aer: AerDocument, record: Mapping[str, Any]) -> Iterator[Annotation]:
        mid = str(record["id"])
        for k, part in enumerate(record.get("parts") or []):
            pid = f"{mid}#{k}"
            t = part.get("t")
            if t == "tool_result":
                name, premises = self._producer(aer, record, k)
                _roles, integrity, rules = self.tool_label(name)
                yield self._ann(aer, pid, "integrity", integrity, rules, premises)
            elif record.get("actor") == "agent":
                yield self._ann(aer, pid, "integrity", "trusted", (R_AGENT,), (Premise(mid, "/actor"),))
                if t == "tool_call":
                    roles, _integrity, rules = self.tool_label(part.get("name"))
                    yield self._ann(aer, pid, "role", list(roles), rules, (Premise(mid, f"/parts/{k}/name"),))
            elif record.get("actor") == "user" and record.get("role") == "user":
                yield self._ann(aer, pid, "integrity", "trusted", (R_USER,), (Premise(mid, "/actor"), Premise(mid, "/role")))

    @staticmethod
    def _producer(aer: AerDocument, record: Mapping[str, Any], k: int) -> tuple[object, list[Premise]]:
        """The tool name of a result part: its generating execution's name, else the part's own name, else none."""
        te = aer.get(str(record.get("generated_by")))
        if te is not None and te.get("k") == "tool_execution":
            return te.get("name"), [Premise(str(te["id"]), "/name")]
        part = (record.get("parts") or [])[k]
        return part.get("name"), [Premise(str(record["id"]), f"/parts/{k}")]

    def _outcome(self, aer: AerDocument, record: Mapping[str, Any]) -> Annotation | None:
        jid = str(record["id"])
        origin, value, name = record.get("origin"), record.get("value"), record.get("name")
        spec = self.tables.outcomes.get(str(name))
        if origin not in self.tables.outcomes["checker_origins"] or not isinstance(spec, dict) or not isinstance(value, bool):
            return None
        premises = (Premise(jid, "/name"), Premise(jid, "/value"), Premise(jid, "/origin"))
        return self._ann(aer, jid, "outcome", {"claim": str(spec["claim"]), "holds": value}, (R_ELICITED,), premises)


def build(profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> GeminiToolsProfile:
    """Build ``geminicli.tools@1`` from its data files (called by :func:`agentprov.adapters.semantics_profiles.load_semantics_profile`)."""
    if (profile_id, version) != (PROFILE_ID, PROFILE_VERSION):
        raise ProfileDataError(f"this code builds {PROFILE_ID}@{PROFILE_VERSION}, not {profile_id}@{version}")
    tables = parse_tables(files)
    catalogue = load_catalogue("geminicli", 1)
    classes: dict[str, str] = {}
    for ref in CITED_RULES:
        entry = catalogue.get(ref)
        if entry is None or not entry.citable:
            raise ProfileDataError(f"{ref} is not an active rule of the geminicli catalogue v1")
        classes[ref] = entry.cls
    return GeminiToolsProfile(profile_id, version, sha256, tables, MappingProxyType(classes), taint_policy=tables.taint)
