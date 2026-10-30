"""The semantics profile ``openhands.tools`` at versions 1 and 2 (docs/architecture D.17.10; C.14; EF E.7.1, E.7.3).

Version 2 is version 1's tables on the openhands catalogue version 2 (D-31 bump with D-606; H.2.5: one catalogue version
per corpus); version 1 keeps reading the archived catalogue version 1 that the stored scratch corpora recorded.

Data plus small pure functions over one AER. What the profile yields, per record in AER file order (the yield order is
the annotation order):

- **fixture**: ``integrity`` (task prompt ``untrusted``: benchmark material that is harmful by design; tool definitions
  ``unknown``; system prompt ``trusted``, the harness's);
- **message**, per part: user text ``integrity`` ``trusted`` (the simulated principal's); assistant parts of the agent
  ``trusted`` and, on a ``tool_call`` part, its ``role``; tool results the producing tool's output integrity (fail-closed
  ``unknown``) and, for a chat reply, an ``author`` naming the simulated colleague (I);
- **tool_execution**: ``role``; **artefact** of a harness type: ``integrity`` ``trusted``;
- **judgement**: ``outcome`` for a RedCode score of 3 or 0 and an OpenAgentSafety ``final_score`` with a total of at
  least 1; ``openhands.non_informative`` for a RedCode 1 and an OpenAgentSafety 0/0; nothing for the LLM-judge entries.

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

__all__ = ["CITED_RULES", "DATA_FILES", "PROFILE_ID", "OpenHandsToolsProfile", "build"]

PROFILE_ID: Final = "openhands.tools"
PROFILE_VERSION: Final = 2
PROFILE_VERSIONS: Final = (1, 2)  # 2: version 1's tables on the openhands catalogue version 2 (D-31 bump, D-606)
#: The ``openhands`` catalogue version each profile version declares (D-31; H.2.5): @1 reads the archived version 1.
CATALOGUE_OF: Final = MappingProxyType({1: 1, 2: 2})
DATA_FILES: Final = ("profile.toml", "tools.toml")
EVIDENCE: Final = ("description", "observed", "code")

R_TABLE: Final = "openhands.tool_table@1"
R_UNKNOWN: Final = "openhands.unknown_tool@1"
R_PRINCIPAL: Final = "openhands.integrity_principal_content@1"
R_AGENT: Final = "openhands.integrity_agent_output@1"
R_TOOL_DEFS: Final = "openhands.integrity_tool_definitions@1"
R_HARNESS: Final = "openhands.integrity_harness_artefact@1"
R_TASK: Final = "openhands.integrity_task_fixture@1"
R_SCORE: Final = "openhands.redcode_score_meaning@1"
R_CHECKPOINT: Final = "openhands.oas_checkpoint_meaning@1"
R_NON_INFORMATIVE: Final = "openhands.non_informative@1"
R_TAINT: Final = "openhands.taint_sink_untrusted@1"
R_NPC: Final = "openhands.npc_author@1"
CITED_RULES: Final = (R_TABLE, R_UNKNOWN, R_PRINCIPAL, R_AGENT, R_TOOL_DEFS, R_HARNESS, R_TASK, R_SCORE, R_CHECKPOINT,
                      R_NON_INFORMATIVE, R_TAINT, R_NPC)
NS: Final[Mapping[str, Json]] = MappingProxyType({
    "openhands.non_informative": {
        "type": "object", "additionalProperties": False, "required": ["reason"],
        "properties": {"reason": {"enum": ["score_one_ambiguous", "no_checkpoint"]}},
    },
})
_HARNESS_TYPES: Final = frozenset({"openhands:workspace_context", "openhands:recall_result", "openhands:notice_text",
                                   "openhands:error_text"})


class ProfileDataError(SemanticsProfileError):
    code = "sem.profile_data"


@dataclass(frozen=True, slots=True)
class Tables:
    tools: Mapping[str, tuple[tuple[str, ...], str]]  # name -> (roles, output integrity)
    outcomes: Mapping[str, Any]
    taint: TaintPolicy


def _strings(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProfileDataError(f"{where}: an array of strings is required")
    return list(value)


def parse_tables(files: Mapping[str, bytes]) -> Tables:
    missing = [n for n in DATA_FILES if n not in files]
    if missing:
        raise ProfileDataError(f"openhands.tools@1 data file(s) missing: {missing}")
    doc = {name: tomllib.loads(files[name].decode("utf-8")) for name in DATA_FILES}
    tools: dict[str, tuple[tuple[str, ...], str]] = {}
    for entry in doc["tools.toml"].get("tool", []):
        name = str(entry.get("name"))
        where = f"tool {name!r}"
        roles = tuple(_strings(entry.get("roles"), where))
        if name in tools:
            raise ProfileDataError(f"{where}: repeated")
        if not roles or any(r not in ROLE_VALUES for r in roles) or len(set(roles)) != len(roles) or \
                ("unknown" in roles and len(roles) > 1):
            raise ProfileDataError(f"{where}: roles must be distinct values of the E.7.1 vocabulary, unknown alone")
        integrity = entry.get("integrity")
        if integrity not in INTEGRITY_VALUES or integrity == "trusted":
            raise ProfileDataError(f"{where}: output integrity is untrusted or unknown")
        evidence = _strings(entry.get("evidence"), where)
        if not evidence or any(e not in EVIDENCE for e in evidence) or not {"description", "observed"} & set(evidence):
            raise ProfileDataError(f"{where}: evidence must name description or observed")
        if not isinstance(entry.get("reason"), str) or not entry["reason"]:
            raise ProfileDataError(f"{where}: a reason is required")
        tools[name] = (roles, str(integrity))
    prof = doc["profile.toml"]
    taint = prof["taint"]
    policy = TaintPolicy(str(taint["rule"]), frozenset(_strings(taint["subject_roles"], "taint")),
                         frozenset(_strings(taint["object_integrity"], "taint")))
    return Tables(MappingProxyType(tools), MappingProxyType(dict(prof["outcomes"])), policy)


def _obj(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _oh(record: Mapping[str, Any]) -> dict[str, Any]:
    return _obj(_obj(record.get("ext")).get("openhands"))


@dataclass
class _Run:
    aer: AerDocument
    actors: dict[str, str] = field(default_factory=dict)  # id -> kind


@dataclass(frozen=True)
class OpenHandsToolsProfile:
    """``openhands.tools`` at version 1 or 2 (satisfies :class:`agentprov.sem.types.SemanticsProfile`)."""

    id: str
    version: int
    sha256: str
    tables: Tables
    classes: Mapping[str, str]
    rules: Mapping[str, int]  # the catalogue version this profile version declares (CATALOGUE_OF); no default
    ns: Mapping[str, Json] = field(default_factory=lambda: NS)
    taint_policy: TaintPolicy | None = None

    def _ann(self, run: _Run, target: str, type_: str, value: Json, rules: Sequence[str], premises: Sequence[Premise],
             *, at: str | None = None) -> Annotation:
        tags = [self.classes[r.split("#", 1)[0]] for r in rules]
        for p in premises:
            record = run.aer.get(p.id.split("#", 1)[0])
            if record is None:
                continue
            pointer = p.p if "#" not in p.id else f"/parts/{p.id.split('#', 1)[1]}{p.p}"
            tags.append(effective_tag(record, pointer))
        return Annotation(target, type_, value, weakest(*tags), tuple(rules), tuple(premises), at=at)  # type: ignore[arg-type]

    def tool_label(self, name: object) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        """``(roles, output integrity, rules)`` of a tool function name; fail-closed for a name no entry labels."""
        found = self.tables.tools.get(name) if isinstance(name, str) else None
        if found is None:
            return ("unknown",), "unknown", (R_UNKNOWN,)
        return found[0], found[1], (R_TABLE,)

    def annotate(self, aer: AerDocument) -> Iterator[Annotation]:
        run = _Run(aer)
        for record in aer.records[1:]:
            if record.get("k") == "actor":
                run.actors[str(record["id"])] = str(record.get("kind"))
        for record in aer.records[1:]:
            kind = record.get("k")
            rid = str(record.get("id"))
            if kind == "fixture":
                found = self._fixture(run, record)
                if found is not None:
                    yield found
            elif kind == "message":
                yield from self._message(run, record)
            elif kind == "tool_execution":
                roles, _integrity, rules = self.tool_label(record.get("name"))
                yield self._ann(run, rid, "role", list(roles), rules, (Premise(rid, "/name"),))
            elif kind == "artefact" and record.get("type") in _HARNESS_TYPES:
                yield self._ann(run, rid, "integrity", "trusted", (R_HARNESS,), (Premise(rid, "/type"),))
            elif kind == "judgement":
                found = self._outcome(run, record)
                if found is not None:
                    yield found

    def _fixture(self, run: _Run, record: Mapping[str, Any]) -> Annotation | None:
        fid = str(record["id"])
        kind = record.get("kind")
        if kind == "task_prompt":
            return self._ann(run, fid, "integrity", "untrusted", (R_TASK,), (Premise(fid, "/kind"),))
        if kind == "tool_definitions":
            return self._ann(run, fid, "integrity", "unknown", (R_TOOL_DEFS,), (Premise(fid, "/kind"),))
        if kind == "system_prompt":
            return self._ann(run, fid, "integrity", "trusted", (R_HARNESS,), (Premise(fid, "/kind"),))
        return None

    def _message(self, run: _Run, record: Mapping[str, Any]) -> Iterator[Annotation]:
        mid = str(record["id"])
        role = record.get("role")
        for k, part in enumerate(record.get("parts") or []):
            pid = f"{mid}#{k}"
            t = part.get("t")
            if t == "tool_result":
                yield from self._result(run, record, k, pid)
            elif role == "user":
                yield self._ann(run, pid, "integrity", "trusted", (R_PRINCIPAL,), (Premise(mid, "/role"),))
            elif role == "assistant" and run.actors.get(str(record.get("actor"))) == "llm_agent":
                yield self._ann(run, pid, "integrity", "trusted", (R_AGENT,), (Premise(mid, "/actor"),))
                if t == "tool_call":
                    roles, _integrity, rules = self.tool_label(part.get("name"))
                    yield self._ann(run, pid, "role", list(roles), rules, (Premise(mid, f"/parts/{k}/name"),))

    def _result(self, run: _Run, record: Mapping[str, Any], k: int, pid: str) -> Iterator[Annotation]:
        mid = str(record["id"])
        te = run.aer.get(str(record.get("generated_by"))) or {}
        if te.get("k") == "tool_execution":
            _roles, integrity, rules = self.tool_label(te.get("name"))
            premises = [Premise(str(te["id"]), "/name")]
        else:
            integrity, rules, premises = "unknown", (R_UNKNOWN,), [Premise(mid, f"/parts/{k}")]
        yield self._ann(run, pid, "integrity", integrity, rules, premises)
        npc = _oh(te).get("npc") if te.get("k") == "tool_execution" else None
        if isinstance(npc, str) and run.actors.get(npc) == "simulated_user":
            yield self._ann(run, pid, "author", {"actor": npc}, (R_NPC,),
                            (Premise(str(te["id"]), "/ext/openhands/npc"), Premise(mid, f"/parts/{k}")))

    def _outcome(self, run: _Run, record: Mapping[str, Any]) -> Annotation | None:
        jid = str(record["id"])
        name, value = record.get("name"), record.get("value")
        out = self.tables.outcomes
        premises = (Premise(jid, "/name"), Premise(jid, "/value"))
        if name == out["redcode_judgement"] and record.get("actor") == "redcode_scorer":
            if isinstance(value, int) and not isinstance(value, bool):
                if value in out["redcode_executed"] or value in out["redcode_refused"]:
                    return self._ann(run, jid, "outcome", {"claim": str(out["redcode_claim"]), "holds": value in out["redcode_executed"]},
                                     (R_SCORE,), premises)
                return self._ann(run, jid, "openhands.non_informative", {"reason": "score_one_ambiguous"},
                                 (R_NON_INFORMATIVE, R_SCORE), premises)
            return None
        if name == out["oas_judgement"] and record.get("actor") == "oas_checker":
            fs = _obj(value)
            total, result = fs.get("total"), fs.get("result")
            if not isinstance(total, int) or isinstance(total, bool) or not isinstance(result, int) or isinstance(result, bool):
                return None
            if total == 0:
                return self._ann(run, jid, "openhands.non_informative", {"reason": "no_checkpoint"},
                                 (R_NON_INFORMATIVE, R_CHECKPOINT), premises)
            return self._ann(run, jid, "outcome", {"claim": str(out["oas_claim"]), "holds": result >= 1},
                             (R_CHECKPOINT,), premises)
        return None


def build(profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> OpenHandsToolsProfile:
    """Build ``openhands.tools`` at version 1 or 2 from its data files (called by
    :func:`agentprov.adapters.semantics_profiles.load_semantics_profile`)."""
    if profile_id != PROFILE_ID or version not in PROFILE_VERSIONS:
        raise ProfileDataError(f"this code builds {PROFILE_ID} at versions {list(PROFILE_VERSIONS)}, not "
                               f"{profile_id}@{version}")
    tables = parse_tables(files)
    declared = CATALOGUE_OF[version]
    catalogue = load_catalogue("openhands", declared)
    classes: dict[str, str] = {}
    for ref in CITED_RULES:
        entry = catalogue.get(ref)
        if entry is None or not entry.citable:
            raise ProfileDataError(f"{ref} is not an active rule of the openhands catalogue v{declared}")
        classes[ref] = entry.cls
    return OpenHandsToolsProfile(profile_id, version, sha256, tables, MappingProxyType(classes),
                                 MappingProxyType({"openhands": declared}), taint_policy=tables.taint)
