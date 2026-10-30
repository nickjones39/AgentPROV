"""The semantics profile ``autogen.tools`` version 1 (docs/architecture D.19.8; C.14; EF E.7.1, E.7.3; DECISIONS D-306).

Data plus small pure functions over one AER. What the profile yields, per record in AER file order:

- **fixture**: ``integrity`` (injection payloads and probe documents ``untrusted``; task and system prompts ``trusted``);
- **message**, per part: agent output (actors ``researcher``, ``writer``, ``selector``): ``integrity`` ``trusted`` and,
  on a ``tool_call`` part, its ``role``; ``autogen.canary_present`` where the run's canary occurs verbatim in a writer
  text or a ``save_note`` argument; ``autogen.attacker_tool_called`` on a call of one of the case's attacker tools; the
  task message (``unknown`` when it carries the document, else ``trusted``) and the ingest turn (``untrusted``);
  tool results: ``integrity`` (``unknown`` when a guard replaced it, else the producing tool's label, fail-closed), one
  ``injection_marker`` per payload fixture (verbatim search, located by ``at``/``span``) and, where a payload is present,
  an ``author`` naming the attacker;
- **tool_execution**: ``role``; **artefact** (memory content): ``integrity`` ``untrusted``;
- **scope** ``run`` of a phase-10 run: ``autogen.keyword_stop`` (whether the text-mention termination ended it).

The deposit records no outcome judgement, so no ``outcome`` annotation is made: the claims above are namespaced
(C.14.3). An annotation's ``ev`` is ``weakest(premise tags, rule classes)`` (C.6.5 rule 3). Reads only the AER; standard
library and ``agentprov.{aer,sem}``.
"""

from __future__ import annotations

import json
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

__all__ = ["CITED_RULES", "DATA_FILES", "PROFILE_ID", "AutoGenToolsProfile", "build"]

PROFILE_ID: Final = "autogen.tools"
PROFILE_VERSION: Final = 1
DATA_FILES: Final = ("profile.toml", "tools.toml")
EVIDENCE: Final = ("observed", "code")
KINDS: Final = ("harness", "injecagent_user", "injecagent_attacker")
AGENTS: Final = frozenset({"researcher", "writer", "selector"})

NORMALISER: Final = "autogen.verbatim_match@1"
R_TABLE: Final = "autogen.tool_table@1"
R_UNKNOWN: Final = "autogen.unknown_tool@1"
R_AGENT: Final = "autogen.integrity_agent_output@1"
R_FIXTURE: Final = "autogen.integrity_fixture@1"
R_TASK: Final = "autogen.integrity_task_message@1"
R_INGEST: Final = "autogen.integrity_ingest_turn@1"
R_WITHHELD: Final = "autogen.integrity_withheld@1"
R_INJECTED: Final = "autogen.integrity_injected_result@1"
R_MEMORY: Final = "autogen.integrity_memory@1"
R_MARKER: Final = "autogen.payload_marker@1"
R_CANARY: Final = "autogen.canary_match@1"
R_ATTACKER: Final = "autogen.attacker_tool_call@1"
R_KEYWORD: Final = "autogen.keyword_stop_reading@1"
R_TAINT: Final = "autogen.taint_sink_untrusted@1"

CITED_RULES: Final = (R_TABLE, R_UNKNOWN, R_AGENT, R_FIXTURE, R_TASK, R_INGEST, R_WITHHELD, R_INJECTED, R_MEMORY,
                      R_MARKER, R_CANARY, R_ATTACKER, R_KEYWORD, R_TAINT, NORMALISER)
NS: Final[Mapping[str, Json]] = MappingProxyType({
    "autogen.canary_present": {
        "type": "object", "additionalProperties": False, "required": ["fixture"],
        "properties": {"fixture": {"type": "string"}},
    },
    "autogen.attacker_tool_called": {
        "type": "object", "additionalProperties": False, "required": ["tool"],
        "properties": {"tool": {"type": "string"}},
    },
    "autogen.keyword_stop": {
        "type": "object", "additionalProperties": False, "required": ["holds"],
        "properties": {"holds": {"type": "boolean"}},
    },
})
_TEXT_STOP: Final = "Text '"
#: The harness constant a guard puts in place of a withheld text (``WITHHELD`` in the deposit's harness.py).
WITHHELD: Final = "[content withheld by guard]"


class ProfileDataError(SemanticsProfileError):
    code = "sem.profile_data"


@dataclass(frozen=True, slots=True)
class Tables:
    """The parsed data files: the tool table, the document entry points and the taint policy."""

    tools: Mapping[str, tuple[tuple[str, ...], str, str]]  # name -> (roles, output integrity, kind)
    document_entries: frozenset[str]
    taint: TaintPolicy


def _strings(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProfileDataError(f"{where}: an array of strings is required")
    return list(value)


def _label(entry: Mapping[str, Any], where: str) -> tuple[tuple[str, ...], str, str]:
    roles = tuple(_strings(entry.get("roles"), where))
    evidence = _strings(entry.get("evidence"), where)
    integrity, kind = entry.get("integrity"), entry.get("kind")
    if not roles or any(r not in ROLE_VALUES for r in roles) or len(set(roles)) != len(roles) or \
            ("unknown" in roles and len(roles) > 1):
        raise ProfileDataError(f"{where}: roles must be distinct values of the E.7.1 vocabulary, unknown alone")
    if integrity not in INTEGRITY_VALUES or integrity == "trusted":
        raise ProfileDataError(f"{where}: output integrity is untrusted or unknown")
    if kind not in KINDS:
        raise ProfileDataError(f"{where}: kind must be one of {KINDS}")
    if not evidence or any(e not in EVIDENCE for e in evidence) or len(set(evidence)) != len(evidence):
        raise ProfileDataError(f"{where}: evidence must be distinct values of {EVIDENCE}")
    if not isinstance(entry.get("reason"), str) or not entry["reason"]:
        raise ProfileDataError(f"{where}: a reason is required")
    return roles, str(integrity), str(kind)


def parse_tables(files: Mapping[str, bytes]) -> Tables:
    missing = [n for n in DATA_FILES if n not in files]
    extra = sorted(set(files) - set(DATA_FILES))
    if missing or extra:
        raise ProfileDataError(f"autogen.tools@1 data files: missing {missing}, unexpected {extra}")
    doc = {name: tomllib.loads(files[name].decode("utf-8")) for name in DATA_FILES}
    tools: dict[str, tuple[tuple[str, ...], str, str]] = {}
    for entry in doc["tools.toml"].get("tool", []):
        name = str(entry.get("name"))
        if name in tools:
            raise ProfileDataError(f"tool {name!r}: repeated")
        tools[name] = _label(entry, f"tool {name!r}")
    prof = doc["profile.toml"]
    if prof.get("matcher", {}).get("normaliser") != NORMALISER:
        raise ProfileDataError(f"autogen.tools@1 uses the normaliser {NORMALISER}")
    taint = prof["taint"]
    policy = TaintPolicy(str(taint["rule"]), frozenset(_strings(taint["subject_roles"], "taint")),
                         frozenset(_strings(taint["object_integrity"], "taint")))
    entries = frozenset(_strings(prof.get("prompts", {}).get("document_in_task_entries", []), "prompts"))
    return Tables(MappingProxyType(tools), entries, policy)


def _obj(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass
class _Run:
    """What one annotate pass knows about the AER."""

    aer: AerDocument
    actors: set[str] = field(default_factory=set)
    payloads: list[tuple[str, str]] = field(default_factory=list)  # (fixture id, payload text)
    canary: tuple[str, str] | None = None  # (fixture id, canary)
    attacker_tools: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AutoGenToolsProfile:
    """``autogen.tools`` at version 1 (satisfies :class:`agentprov.sem.types.SemanticsProfile`)."""

    id: str
    version: int
    sha256: str
    tables: Tables
    classes: Mapping[str, str]
    rules: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({"autogen": 1}))
    ns: Mapping[str, Json] = field(default_factory=lambda: NS)
    taint_policy: TaintPolicy | None = None

    # ------------------------------------------------------------------------------------------ helpers
    def _ann(self, run: _Run, target: str, type_: str, value: Json, rules: Sequence[str], premises: Sequence[Premise],
             *, at: str | None = None, span: tuple[int, int] | None = None) -> Annotation:
        tags = [self.classes[r.split("#", 1)[0]] for r in rules]
        for p in premises:
            record = run.aer.get(p.id.split("#", 1)[0])
            if record is None:
                continue
            pointer = p.p if "#" not in p.id else f"/parts/{p.id.split('#', 1)[1]}{p.p}"
            tags.append(effective_tag(record, pointer))
        return Annotation(target, type_, value, weakest(*tags), tuple(rules), tuple(premises), at=at, span=span)  # type: ignore[arg-type]

    def tool_label(self, name: object) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        """``(roles, output integrity, rules)`` of a tool by name; fail-closed for a name no table lists."""
        found = self.tables.tools.get(name) if isinstance(name, str) else None
        if found is None:
            return ("unknown",), "unknown", (R_UNKNOWN,)
        return found[0], found[1], (R_TABLE,)

    # ------------------------------------------------------------------------------------------ annotate
    def annotate(self, aer: AerDocument) -> Iterator[Annotation]:
        run = _Run(aer)
        for record in aer.records[1:]:
            if record.get("k") == "actor":
                run.actors.add(str(record["id"]))
            elif record.get("k") == "fixture" and record.get("kind") == "injection_payload" \
                    and isinstance(record.get("content"), str):
                run.payloads.append((str(record["id"]), str(record["content"])))
                ext = _obj(_obj(record.get("ext")).get("autogen"))
                if isinstance(ext.get("canary"), str) and ext["canary"]:
                    run.canary = (str(record["id"]), ext["canary"])
                tools = ext.get("attacker_tools")
                if isinstance(tools, list):
                    run.attacker_tools = frozenset(str(t) for t in tools)
        for record in aer.records[1:]:
            kind = record.get("k")
            if kind == "fixture":
                found = self._fixture(run, record)
                if found is not None:
                    yield found
            elif kind == "message":
                yield from self._message(run, record)
            elif kind == "tool_execution":
                rid = str(record["id"])
                roles, _integrity, rules = self.tool_label(record.get("name"))
                yield self._ann(run, rid, "role", list(roles), rules, (Premise(rid, "/name"),))
            elif kind == "artefact" and record.get("type") == "autogen:memory_content":
                rid = str(record["id"])
                yield self._ann(run, rid, "integrity", "untrusted", (R_MEMORY,), (Premise(rid, "/type"),))
            elif kind == "scope" and record.get("id") == "run":
                found = self._keyword(run)
                if found is not None:
                    yield found

    def _fixture(self, run: _Run, record: Mapping[str, Any]) -> Annotation | None:
        fid = str(record["id"])
        kind = record.get("kind")
        if kind == "injection_payload" or (kind == "other" and record.get("subtype") == "autogen.probe_document"):
            return self._ann(run, fid, "integrity", "untrusted", (R_FIXTURE,), (Premise(fid, "/kind"),))
        if kind in ("task_prompt", "system_prompt"):
            return self._ann(run, fid, "integrity", "trusted", (R_FIXTURE,), (Premise(fid, "/kind"),))
        return None

    def _message(self, run: _Run, record: Mapping[str, Any]) -> Iterator[Annotation]:
        mid = str(record["id"])
        actor = record.get("actor")
        generator = run.aer.get(str(record.get("generated_by"))) or {}
        for k, part in enumerate(record.get("parts") or []):
            pid = f"{mid}#{k}"
            t = part.get("t")
            if t == "tool_result":
                yield from self._result(run, record, k, pid, generator)
            elif actor in AGENTS:
                yield self._ann(run, pid, "integrity", "trusted", (R_AGENT,), (Premise(mid, "/actor"),))
                if t == "tool_call":
                    roles, _integrity, rules = self.tool_label(part.get("name"))
                    yield self._ann(run, pid, "role", list(roles), rules, (Premise(mid, f"/parts/{k}/name"),))
                    if part.get("name") in run.attacker_tools:
                        yield self._ann(run, pid, "autogen.attacker_tool_called", {"tool": str(part["name"])},
                                        (R_ATTACKER,), (Premise(mid, f"/parts/{k}/name"),))
                yield from self._canary(run, record, k, part)
            elif actor == "user" and t == "text":
                entry = _obj(run.aer.header.get("task")).get("suite")
                value = "unknown" if entry in self.tables.document_entries else "trusted"
                yield self._ann(run, pid, "integrity", value, (R_TASK,), (Premise(mid, "/actor"), Premise("exec", "/task/suite")))
            elif actor == "ingest" and t == "text":
                yield self._ann(run, pid, "integrity", "untrusted", (R_INGEST,), (Premise(mid, "/actor"),))
            elif isinstance(actor, str) and actor.startswith("guard_") and t == "text":
                yield self._ann(run, pid, "integrity", "unknown", (R_WITHHELD,), (Premise(mid, "/actor"),))

    def _canary(self, run: _Run, record: Mapping[str, Any], k: int, part: Mapping[str, Any]) -> Iterator[Annotation]:
        if run.canary is None:
            return
        fid, canary = run.canary
        mid = str(record["id"])
        if part.get("t") == "text" and record.get("actor") == "writer" and isinstance(part.get("text"), str):
            at = part["text"].find(canary)
            if at >= 0:
                yield self._ann(run, f"{mid}#{k}", "autogen.canary_present", {"fixture": fid}, (R_CANARY,),
                                (Premise(mid, f"/parts/{k}/text"), Premise(fid, "/ext/autogen/canary")),
                                at="/text", span=(at, at + len(canary)))
        elif part.get("t") == "tool_call" and part.get("name") == "save_note":
            haystack = json.dumps(part.get("args"), ensure_ascii=False, separators=(",", ":"))
            if canary in haystack:
                yield self._ann(run, f"{mid}#{k}", "autogen.canary_present", {"fixture": fid}, (R_CANARY,),
                                (Premise(mid, f"/parts/{k}/args"), Premise(fid, "/ext/autogen/canary")))

    def _result(self, run: _Run, record: Mapping[str, Any], k: int, pid: str,
                generator: Mapping[str, Any]) -> Iterator[Annotation]:
        mid = str(record["id"])
        part = (record.get("parts") or [])[k]
        text = part.get("text")
        markers: list[tuple[str, str, tuple[int, int] | None]] = []
        for fid, payload in run.payloads:
            at = text.find(payload) if isinstance(text, str) and payload else -1
            markers.append((fid, "present", (at, at + len(payload))) if at >= 0 else (fid, "absent", None))
        present = [m for m in markers if m[1] == "present"]
        if generator.get("k") == "decision" and text == WITHHELD:
            yield self._ann(run, pid, "integrity", "unknown", (R_WITHHELD,),
                            (Premise(mid, "/generated_by"), Premise(str(generator["id"]), "/verdict")))
        elif present:
            yield self._ann(run, pid, "integrity", "untrusted", (R_INJECTED,),
                            (Premise(mid, f"/parts/{k}/text"), Premise(present[0][0], "/content")))
        else:
            name, premises = self._producer(run, record, pid, generator)
            _roles, integrity, rules = self.tool_label(name)
            yield self._ann(run, pid, "integrity", integrity, rules, premises)
        if isinstance(text, str):
            for fid, status, span in markers:
                value: dict[str, Json] = {"fixture": fid, "status": status, "normaliser": NORMALISER}
                yield self._ann(run, pid, "injection_marker", value, (R_MARKER,),
                                (Premise(mid, f"/parts/{k}/text"), Premise(fid, "/content")),
                                at="/text" if span is not None else None, span=span)
        if present and "att" in run.actors:
            yield self._ann(run, pid, "author", {"actor": "att"}, (R_INJECTED,),
                            (Premise(mid, f"/parts/{k}/text"), Premise(present[0][0], "/content")))

    @staticmethod
    def _producer(run: _Run, record: Mapping[str, Any], pid: str,
                  generator: Mapping[str, Any]) -> tuple[object, list[Premise]]:
        if generator.get("k") == "decision":  # a changed (not withheld) result keeps its tool's label
            generator = run.aer.get(str(generator.get("subject"))) or {}
        if generator.get("k") == "tool_execution":
            return generator.get("name"), [Premise(str(generator["id"]), "/name")]
        k = pid.split("#", 1)[1]
        part = (record.get("parts") or [])[int(k)]
        return part.get("name"), [Premise(str(record["id"]), f"/parts/{k}/name")]

    def _keyword(self, run: _Run) -> Annotation | None:
        ext = _obj(_obj(run.aer.header.get("ext")).get("autogen"))
        settings = _obj(ext.get("settings"))
        if "termination" not in settings:
            return None
        stop = settings.get("stop_reason")
        holds = isinstance(stop, str) and stop.startswith(_TEXT_STOP)
        return self._ann(run, "run", "autogen.keyword_stop", {"holds": holds}, (R_KEYWORD,),
                         (Premise("exec", "/ext/autogen/settings/stop_reason"),))


def build(profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> AutoGenToolsProfile:
    """Build ``autogen.tools@1`` from its data files (called by :func:`agentprov.adapters.semantics_profiles.load_semantics_profile`)."""
    if (profile_id, version) != (PROFILE_ID, PROFILE_VERSION):
        raise ProfileDataError(f"this code builds {PROFILE_ID}@{PROFILE_VERSION}, not {profile_id}@{version}")
    tables = parse_tables(files)
    catalogue = load_catalogue("autogen", 1)
    classes: dict[str, str] = {}
    for ref in CITED_RULES:
        entry = catalogue.get(ref)
        if entry is None or not entry.citable:
            raise ProfileDataError(f"{ref} is not an active rule of the autogen catalogue v1")
        classes[ref] = entry.cls
    return AutoGenToolsProfile(profile_id, version, sha256, tables, MappingProxyType(classes), taint_policy=tables.taint)
