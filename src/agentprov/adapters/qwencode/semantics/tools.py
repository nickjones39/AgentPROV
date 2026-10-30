"""The semantics profile ``qwencode.tools``, versions 1 and 2 (docs/architecture D.24.7; C.14; EF E.7.1, E.7.3).

Data plus small pure functions over one AER. What the profile yields, per record in AER file order (the yield order is
the annotation order):

- **fixture**: ``integrity`` by kind (the RedCode request ``untrusted``, the execution rules ``trusted``);
- **message**, per part: agent output (actor ``agent``) ``trusted`` and, on a ``tool_call`` part, its ``role``; tool
  results: ``integrity`` of the producing tool, fail-closed;
- **tool_execution**: ``role``;
- **judgement**: ``outcome`` for ``score``: ``attack_succeeded`` holds for 3 and not for 0; 1 is
  ``qwencode.non_informative`` (D-576, as the OpenHands part of the deposit). At version 2 any other score gets no
  annotation (the rule covers these three only; regen item 127, NF-21); version 1 reads every other integer as
  ``qwencode.non_informative``, as the scratch trial corpora recorded it.

The data are the directory ``qwencode.tools-<version>/``; version 1 declares the catalogue version 1 (read from
``rules/archive/``) and version 2 the catalogue version 2 (D-31, the twins owner's ruling of 2026-10-21, option A, as
``agentdojo.suites``).

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

__all__ = ["CITED_RULES", "DATA_FILES", "PROFILE_ID", "QwenToolsProfile", "build"]

PROFILE_ID: Final = "qwencode.tools"
PROFILE_VERSION: Final = 2
PROFILE_VERSIONS: Final = (1, 2)
#: The ``qwencode`` catalogue version each profile version declares and reads (D-31; H.2.5: one catalogue version per
#: corpus): @1 stays on the archived catalogue version 1, which the scratch trial corpora recorded; @2 reads version 2.
CATALOGUE_OF: Final = MappingProxyType({1: 1, 2: 2})
DATA_FILES: Final = ("profile.toml", "tools.toml")
EVIDENCE: Final = ("observed", "code")

R_TABLE: Final = "qwencode.tool_table@1"
R_UNKNOWN: Final = "qwencode.unknown_tool@1"
R_AGENT: Final = "qwencode.integrity_agent_output@1"
R_PROMPT: Final = "qwencode.integrity_task_prompt@1"
R_RULES: Final = "qwencode.integrity_rules@1"
R_SCORE: Final = "qwencode.score_meaning@1"
R_TAINT: Final = "qwencode.taint_sink_untrusted@1"

#: Every rule this profile cites (the catalogue test checks each exists, is active and has the class its annotations
#: need).
CITED_RULES: Final = (R_TABLE, R_UNKNOWN, R_AGENT, R_PROMPT, R_RULES, R_SCORE, R_TAINT)
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


def parse_tables(files: Mapping[str, bytes], version: int = PROFILE_VERSION) -> Tables:
    """Parse and cross-check the profile's data files at ``version``."""
    if version not in PROFILE_VERSIONS:
        raise ProfileDataError(f"this code builds {PROFILE_ID} at versions {list(PROFILE_VERSIONS)}, not {version}")
    missing = [n for n in DATA_FILES if n not in files]
    extra = sorted(set(files) - set(DATA_FILES))
    if missing or extra:
        raise ProfileDataError(f"{PROFILE_ID}@{version} data files: missing {missing}, unexpected {extra}")
    doc = {name: tomllib.loads(files[name].decode("utf-8")) for name in DATA_FILES}
    head = doc["profile.toml"].get("profile", {})
    if (head.get("id"), head.get("version"), head.get("rules")) != (PROFILE_ID, version, {"qwencode": CATALOGUE_OF[version]}):
        raise ProfileDataError(f"profile.toml [profile]: id {PROFILE_ID}, version {version} and rules "
                               f"{{qwencode = {CATALOGUE_OF[version]}}} are required")
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
    outcomes = prof.get("outcomes", {})
    scores: list[int] = []
    keys = ("executed", "refused", "non_informative") if version >= 2 else ()
    for key in keys:  # regen item 127 (NF-21), version 2: every read score is listed
        values = outcomes.get(key)
        if not isinstance(values, list) or not values or not all(isinstance(v, int) and not isinstance(v, bool) for v in values):
            raise ProfileDataError(f"outcomes.{key}: a non-empty array of integers is required")
        scores += values
    if len(set(scores)) != len(scores):
        raise ProfileDataError("outcomes: executed, refused and non_informative are disjoint")
    taint = prof["taint"]
    policy = TaintPolicy(str(taint["rule"]), frozenset(_strings(taint["subject_roles"], "taint")),
                         frozenset(_strings(taint["object_integrity"], "taint")))
    return Tables(MappingProxyType(tools), MappingProxyType(fixtures), MappingProxyType(dict(prof["outcomes"])), policy)


@dataclass(frozen=True)
class QwenToolsProfile:
    """``qwencode.tools`` at version 1 or 2 (satisfies :class:`agentprov.sem.types.SemanticsProfile`)."""

    id: str
    version: int
    sha256: str
    tables: Tables
    classes: Mapping[str, str]
    rules: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({"qwencode": 1}))
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
                    rule = R_PROMPT if record.get("kind") == "task_prompt" else R_RULES
                    yield self._ann(aer, rid, "integrity", integrity, (rule,), (Premise(rid, "/kind"),))
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

    @staticmethod
    def _producer(aer: AerDocument, record: Mapping[str, Any], k: int) -> tuple[object, list[Premise]]:
        """The tool name of a result part: its generating execution's name, else the part's own name, else none."""
        te = aer.get(str(record.get("generated_by")))
        if te is not None and te.get("k") == "tool_execution":
            return te.get("name"), [Premise(str(te["id"]), "/name")]
        part = (record.get("parts") or [])[k]
        return part.get("name"), [Premise(str(record["id"]), f"/parts/{k}")]

    def _outcome(self, aer: AerDocument, record: Mapping[str, Any]) -> Annotation | None:
        out = self.tables.outcomes
        jid = str(record["id"])
        value, name = record.get("value"), record.get("name")
        if name != out.get("judgement") or isinstance(value, bool) or not isinstance(value, int):
            return None
        premises = (Premise(jid, "/name"), Premise(jid, "/value"))
        if value in out["executed"] or value in out["refused"]:
            return self._ann(aer, jid, "outcome", {"claim": str(out["claim"]), "holds": value in out["executed"]},
                             (R_SCORE,), premises)
        if self.version < 2 or value in out["non_informative"]:  # version 1: every other integer (as recorded)
            return self._ann(aer, jid, "outcome", {"claim": str(out["non_informative_claim"]), "holds": True}, (R_SCORE,),
                             premises)
        return None  # version 2: a score the rule does not cover has no reading (regen item 127, NF-21)


def build(profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> QwenToolsProfile:
    """Build ``qwencode.tools`` at ``version`` from its data files (called by
    :func:`agentprov.adapters.semantics_profiles.load_semantics_profile`)."""
    if profile_id != PROFILE_ID or version not in PROFILE_VERSIONS:
        raise ProfileDataError(f"this code builds {PROFILE_ID} at versions {list(PROFILE_VERSIONS)}, not {profile_id}@{version}")
    tables = parse_tables(files, version)
    catalogue = load_catalogue("qwencode", CATALOGUE_OF[version])
    classes: dict[str, str] = {}
    for ref in CITED_RULES:
        entry = catalogue.get(ref)
        if entry is None or not entry.citable:
            raise ProfileDataError(f"{ref} is not an active rule of the qwencode catalogue v{CATALOGUE_OF[version]}")
        classes[ref] = entry.cls
    return QwenToolsProfile(profile_id, version, sha256, tables, MappingProxyType(classes),
                            rules=MappingProxyType({"qwencode": CATALOGUE_OF[version]}), taint_policy=tables.taint)
