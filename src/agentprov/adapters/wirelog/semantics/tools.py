"""The semantics profile ``wirelog.tools`` version 1 (docs/architecture D.20.8; C.14; EF E.7.1, E.7.3).

Data plus small pure functions over one AER. What the profile yields, per record in AER file order (the yield order is
the annotation order):

- **fixture**: ``integrity`` (payloads ``untrusted``; a tool configuration ``untrusted`` when it carries one of the run's
  payloads verbatim, else ``unknown``);
- **message**, per part: the system prompt and the user's task ``trusted``; agent output (actor ``agent``) ``trusted``
  and, on a ``tool_call`` part, its ``role``; tool results: ``integrity`` (``untrusted`` where a payload is present or the
  text is an attacked first-batch document, else the producing tool's label, fail-closed), one ``injection_marker`` per
  payload fixture of the run (verbatim search, located by ``at``/``span``) and, where attacker content is present, an
  ``author`` naming the attacker; any other part ``unknown``;
- **tool_execution**: ``role``;
- **judgement**: ``outcome`` for ``hijack`` (``attack_succeeded``), ``exfiltration`` and ``silent``, only for a run with an
  attack and a checker origin.

An annotation's ``ev`` is ``weakest(premise tags, rule classes)`` (C.6.5 rule 3). Reads only the AER; standard library
and ``agentprov.{aer,sem}``.
"""

from __future__ import annotations

import hashlib
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

__all__ = ["CITED_RULES", "DATA_FILES", "PROFILE_ID", "WireLogToolsProfile", "build"]

PROFILE_ID: Final = "wirelog.tools"
PROFILE_VERSION: Final = 1
DATA_FILES: Final = ("documents.toml", "profile.toml", "tools.toml")
EVIDENCE: Final = ("observed", "code")

NORMALISER: Final = "wirelog.verbatim_match@1"
R_TABLE: Final = "wirelog.tool_table@1"
R_UNKNOWN: Final = "wirelog.unknown_tool@1"
R_AGENT: Final = "wirelog.integrity_agent_output@1"
R_FIXTURE: Final = "wirelog.integrity_payload_fixture@1"
R_TOOLDEFS: Final = "wirelog.integrity_tool_definitions@1"
R_SYSTEM: Final = "wirelog.integrity_system_prompt@1"
R_TASK: Final = "wirelog.integrity_task_prompt@1"
R_INJECTED: Final = "wirelog.integrity_injected_result@1"
R_MARKER: Final = "wirelog.payload_marker@1"
R_DOCUMENT: Final = "wirelog.first_batch_document@1"
R_HIJACK: Final = "wirelog.hijack_meaning@1"
R_EXFIL: Final = "wirelog.exfiltration_meaning@1"
R_SILENT: Final = "wirelog.silent_meaning@1"
R_TAINT: Final = "wirelog.taint_sink_untrusted@1"
_MEANING: Final = {"hijack": R_HIJACK, "exfiltration": R_EXFIL, "silent": R_SILENT}

#: Every rule this profile cites (the catalogue test checks each exists, is active and has the class its annotations
#: need).
CITED_RULES: Final = (R_TABLE, R_UNKNOWN, R_AGENT, R_FIXTURE, R_TOOLDEFS, R_SYSTEM, R_TASK, R_INJECTED, R_MARKER, R_DOCUMENT,
                      R_HIJACK, R_EXFIL, R_SILENT, R_TAINT, NORMALISER)
NS: Final[Mapping[str, Json]] = MappingProxyType({})


class ProfileDataError(SemanticsProfileError):
    code = "sem.profile_data"


@dataclass(frozen=True, slots=True)
class Tables:
    """The parsed data files: the tool table, the first-batch documents, the outcome claims and the taint policy."""

    tools: Mapping[str, tuple[tuple[str, ...], str]]  # name -> (roles, output integrity)
    documents: Mapping[str, bool]  # sha256 of a planted document -> attacked
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
        raise ProfileDataError(f"wirelog.tools@1 data files: missing {missing}, unexpected {extra}")
    doc = {name: tomllib.loads(files[name].decode("utf-8")) for name in DATA_FILES}
    tools: dict[str, tuple[tuple[str, ...], str]] = {}
    for entry in doc["tools.toml"].get("tool", []):
        name = str(entry.get("name"))
        if name in tools:
            raise ProfileDataError(f"tool {name!r}: repeated")
        tools[name] = _label(entry, f"tool {name!r}")
    documents: dict[str, bool] = {}
    for entry in doc["documents.toml"].get("document", []):
        digest, attacked = entry.get("sha256"), entry.get("attacked")
        if not isinstance(digest, str) or len(digest) != 64 or not isinstance(attacked, bool) or digest in documents:
            raise ProfileDataError(f"document {entry.get('variant')!r}: a unique sha256 and a boolean attacked are required")
        documents[digest] = attacked
    prof = doc["profile.toml"]
    if prof.get("matcher", {}).get("normaliser") != NORMALISER:
        raise ProfileDataError(f"wirelog.tools@1 uses the normaliser {NORMALISER}")
    taint = prof["taint"]
    policy = TaintPolicy(str(taint["rule"]), frozenset(_strings(taint["subject_roles"], "taint")),
                         frozenset(_strings(taint["object_integrity"], "taint")))
    return Tables(MappingProxyType(tools), MappingProxyType(documents), MappingProxyType(dict(prof["outcomes"])), policy)


def _obj(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings_in(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings_in(item)


@dataclass
class _Run:
    """What one annotate pass knows about the AER."""

    aer: AerDocument
    actors: set[str] = field(default_factory=set)
    payloads: list[tuple[str, str]] = field(default_factory=list)  # (fixture id, payload text)


@dataclass(frozen=True)
class WireLogToolsProfile:
    """``wirelog.tools`` at version 1 (satisfies :class:`agentprov.sem.types.SemanticsProfile`)."""

    id: str
    version: int
    sha256: str
    tables: Tables
    classes: Mapping[str, str]
    rules: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({"wirelog": 1}))
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
            elif kind == "judgement":
                found = self._outcome(run, record)
                if found is not None:
                    yield found

    def _fixture(self, run: _Run, record: Mapping[str, Any]) -> Annotation | None:
        fid = str(record["id"])
        kind = record.get("kind")
        if kind == "injection_payload":
            return self._ann(run, fid, "integrity", "untrusted", (R_FIXTURE,), (Premise(fid, "/kind"),))
        if kind == "tool_definitions":
            texts = list(_strings_in(record.get("content")))
            hit = next((pid for pid, payload in run.payloads if payload and any(payload in t for t in texts)), None)
            premises = [Premise(fid, "/content")]
            if hit is not None:
                premises.append(Premise(hit, "/content"))
            return self._ann(run, fid, "integrity", "untrusted" if hit is not None else "unknown", (R_TOOLDEFS,), premises)
        return None

    def _message(self, run: _Run, record: Mapping[str, Any]) -> Iterator[Annotation]:
        mid = str(record["id"])
        actor, role = record.get("actor"), record.get("role")
        for k, part in enumerate(record.get("parts") or []):
            pid = f"{mid}#{k}"
            t = part.get("t")
            if t == "tool_result":
                yield from self._result(run, record, k, pid)
            elif actor == "agent":
                yield self._ann(run, pid, "integrity", "trusted", (R_AGENT,), (Premise(mid, "/actor"),))
                if t == "tool_call":
                    roles, _integrity, rules = self.tool_label(part.get("name"))
                    yield self._ann(run, pid, "role", list(roles), rules, (Premise(mid, f"/parts/{k}/name"),))
            elif role == "system" and actor == "harness":
                yield self._ann(run, pid, "integrity", "trusted", (R_SYSTEM,), (Premise(mid, "/role"), Premise(mid, "/actor")))
            elif role == "user" and actor == "user":
                yield self._ann(run, pid, "integrity", "trusted", (R_TASK,), (Premise(mid, "/role"), Premise(mid, "/actor")))
            else:
                yield self._ann(run, pid, "integrity", "unknown", (R_UNKNOWN,), (Premise(mid, "/actor"),))

    def _result(self, run: _Run, record: Mapping[str, Any], k: int, pid: str) -> Iterator[Annotation]:
        mid = str(record["id"])
        part = (record.get("parts") or [])[k]
        text = part.get("text")
        text_pointer = f"/parts/{k}/text" if "text" in part else f"/parts/{k}/value"
        haystack = text if isinstance(text, str) else json.dumps(part.get("value"), ensure_ascii=False,
                                                                 separators=(",", ":"), sort_keys=False)
        markers: list[tuple[str, str, tuple[int, int] | None]] = []  # (fixture, status, span)
        for fid, payload in run.payloads:
            at = haystack.find(payload) if payload else -1
            if at < 0:
                markers.append((fid, "absent", None))
            else:
                markers.append((fid, "present", (at, at + len(payload)) if isinstance(text, str) else None))
        present = [m for m in markers if m[1] == "present"]
        attacked_doc = isinstance(text, str) and \
            self.tables.documents.get(hashlib.sha256(text.encode("utf-8")).hexdigest()) is True
        if present:
            yield self._ann(run, pid, "integrity", "untrusted", (R_INJECTED,),
                            (Premise(mid, text_pointer), Premise(present[0][0], "/content")))
        elif attacked_doc:
            yield self._ann(run, pid, "integrity", "untrusted", (R_INJECTED, R_DOCUMENT), (Premise(mid, text_pointer),))
        else:
            name, premises = self._producer(run, record)
            _roles, integrity, rules = self.tool_label(name)
            yield self._ann(run, pid, "integrity", integrity, rules, premises)
        for fid, status, span in markers:
            value: dict[str, Json] = {"fixture": fid, "status": status, "normaliser": NORMALISER}
            yield self._ann(run, pid, "injection_marker", value, (R_MARKER,),
                            (Premise(mid, text_pointer), Premise(fid, "/content")),
                            at="/text" if span is not None else None, span=span)
        if "att" in run.actors and (present or attacked_doc):
            if present:
                yield self._ann(run, pid, "author", {"actor": "att"}, (R_INJECTED,),
                                (Premise(mid, text_pointer), Premise(present[0][0], "/content")))
            else:
                yield self._ann(run, pid, "author", {"actor": "att"}, (R_INJECTED, R_DOCUMENT), (Premise(mid, text_pointer),))

    @staticmethod
    def _producer(run: _Run, record: Mapping[str, Any]) -> tuple[object, list[Premise]]:
        """The tool name of a result message: its generating execution's name (``None`` when not linked)."""
        te = run.aer.get(str(record.get("generated_by")))
        if te is not None and te.get("k") == "tool_execution":
            return te.get("name"), [Premise(str(te["id"]), "/name")]
        return None, [Premise(str(record["id"]), "/generated_by")]

    def _outcome(self, run: _Run, record: Mapping[str, Any]) -> Annotation | None:
        jid = str(record["id"])
        origin, value, name = record.get("origin"), record.get("value"), record.get("name")
        if origin not in self.tables.outcomes["checker_origins"] or name not in _MEANING:
            return None
        spec = _obj(self.tables.outcomes.get(str(name)))
        attack = _obj(run.aer.header.get("task")).get("attack_id")
        if spec.get("needs_attack") and attack is None:
            return None
        if value not in ("0", "1"):
            return None
        premises = (Premise(jid, "/name"), Premise(jid, "/value"), Premise(jid, "/origin"), Premise("exec", "/task/attack_id"))
        return self._ann(run, jid, "outcome", {"claim": str(spec["claim"]), "holds": value == "1"}, (_MEANING[str(name)],),
                         premises)


def build(profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> WireLogToolsProfile:
    """Build ``wirelog.tools@1`` from its data files (called by :func:`agentprov.adapters.semantics_profiles.load_semantics_profile`)."""
    if (profile_id, version) != (PROFILE_ID, PROFILE_VERSION):
        raise ProfileDataError(f"this code builds {PROFILE_ID}@{PROFILE_VERSION}, not {profile_id}@{version}")
    tables = parse_tables(files)
    catalogue = load_catalogue("wirelog", 1)
    classes: dict[str, str] = {}
    for ref in CITED_RULES:
        entry = catalogue.get(ref)
        if entry is None or not entry.citable:
            raise ProfileDataError(f"{ref} is not an active rule of the wirelog catalogue v1")
        classes[ref] = entry.cls
    return WireLogToolsProfile(profile_id, version, sha256, tables, MappingProxyType(classes), taint_policy=tables.taint)
