"""The semantics profile ``dtap.tools`` versions 1 and 2 (docs/architecture D.16.9, D.16.6; C.14; EF E.7.1, E.7.3).

Version 2 (D-607; the D-31 addendum's option B) is version 1's tables and code on the ``dtap`` rule catalogue version 2
(:data:`CATALOGUE_OF`); version 1 reads the archived catalogue version 1 for the corpora that record it.

Data plus small pure functions over one AER. What the profile yields, per record in AER file order (the yield order is
the annotation order):

- **fixture**: ``integrity`` (payload and attack-goal fixtures ``untrusted``; a logged tool-definition fixture
  ``unknown``); on the tool-definition fixture, one ``dtap.description_marker`` per ``tool``/``skill`` payload fixture;
- **message**, per part: user text: one ``dtap.prompt_marker`` per ``prompt`` payload fixture, then ``integrity``
  (``trusted``; ``untrusted`` when a prompt payload is present) and, for a present payload, an ``author`` naming the
  attacker (I); agent output (actor ``agent``): ``integrity`` ``trusted`` and, on a ``tool_call`` part, its ``role``;
  tool results: ``integrity`` (the producing tool's label: ``untrusted`` or ``unknown``, fail-closed) and one core
  ``injection_marker`` per ``environment``/``skill`` payload fixture;
- **tool_execution**: ``role``; **artefact** of a harness type: ``integrity`` ``trusted``;
- **judgement**: ``outcome`` (never for ``harness_default``, which gets ``dtap.non_informative`` instead);
- at the end: ``dtap.agent_output_marker`` for a payload found only in agent output, and one ``dtap.exposure`` per payload
  fixture (target the run scope; value ``{fixture, channel, class}``).

Markers use the census matcher ``dtap.alnum_norm@1`` (:mod:`agentprov.adapters.dtap.matcher`). An annotation's ``ev`` is
``weakest(premise tags, rule classes)`` (C.6.5 rule 3). The exposure classes rest on AER fields only (the payload
fixture's content, a D copy of the joined configuration, and the logged parts), so an observed class stays D in the
assessment bundle; ``configured_only`` and ``partial_match`` are I. Reads only the AER; standard library and
``agentprov.{aer,sem,adapters.dtap.matcher}``.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from agentprov.adapters.dtap.matcher import needles, normalise, serialise, windows
from agentprov.aer.canon import pointer_escape
from agentprov.aer.evidence import effective_tag, weakest
from agentprov.aer.rules import load_catalogue
from agentprov.aer.types import Json
from agentprov.sem.profiles import SemanticsProfileError
from agentprov.sem.types import INTEGRITY_VALUES, ROLE_VALUES, Annotation, Premise, TaintPolicy

if TYPE_CHECKING:
    from agentprov.aer.reader import AerDocument

__all__ = ["CITED_RULES", "DATA_FILES", "PROFILE_ID", "DtapToolsProfile", "build"]

PROFILE_ID: Final = "dtap.tools"
PROFILE_VERSION: Final = 3
#: The ``dtap`` catalogue version each profile version declares (D-31: version 1 is archived; ``@1`` reads it).
CATALOGUE_OF: Final = MappingProxyType({1: 1, 2: 2, 3: 3})  # 3: version 2's tables on catalogue dtap 3 (D-934)
#: The first version with regen item 54's handling of a payload with no recorded vector or content (the step type as
#: channel; ``/kind`` premises). ``@1`` keeps its behaviour as before item 54 (D-31 owner ruling 2026-10-21; D-607).
ITEM_54_SINCE: Final = 2
DATA_FILES: Final = ("builtins.toml", "domains.toml", "labels.toml", "profile.toml", "servers.toml")
#: The evidence a label may rest on (D.16.9), strongest first: the logged tool description, the logged arguments and
#: results, the task configurations. A label needs one of the first two; ``config`` only corroborates.
EVIDENCE: Final = ("description", "observed", "config")
#: OpenClaw logs every tool with this server; its own (unprefixed) tools are labelled under it (D.16.9).
OPENCLAW: Final = "openclaw"
NORMALISER: Final = "dtap.alnum_norm@1"

R_TABLE: Final = "dtap.tool_table@1"
R_PREFIX: Final = "dtap.openclaw_prefix_split@1"
R_DOMAIN: Final = "dtap.unknown_server_domain_match@1"
R_UNKNOWN: Final = "dtap.unknown_tool@1"
R_PRINCIPAL: Final = "dtap.integrity_principal_content@1"
R_PROMPT_PAYLOAD: Final = "dtap.integrity_prompt_payload@1"
R_AGENT: Final = "dtap.integrity_agent_output@1"
R_FIXTURE: Final = "dtap.integrity_payload_fixture@1"
R_TOOL_DEFS: Final = "dtap.integrity_tool_definitions@1"
R_HARNESS: Final = "dtap.integrity_harness_artefact@1"
R_ENV: Final = "dtap.env_marker@1"
R_WINDOW: Final = "dtap.marker_partial_window@1"
R_DESCRIPTION: Final = "dtap.description_marker@1"
R_PROMPT: Final = "dtap.prompt_marker@1"
R_AGENT_OUT: Final = "dtap.agent_output_marker@1"
R_CLASS: Final = "dtap.exposure_class@1"
R_CONFIGURED: Final = "dtap.configured_exposure_unverified@1"
R_AUTHOR: Final = "dtap.direct_prompt_replaces_user_unverified@1"
R_TASK: Final = "dtap.task_success_meaning@1"
R_ATTACK: Final = "dtap.attack_success_polarity@1"
R_CONTROL: Final = "dtap.control_attack_judgement@1"
R_NON_INFORMATIVE: Final = "dtap.non_informative@1"
R_TAINT: Final = "dtap.taint_sink_untrusted@1"

#: Every rule this profile cites (the catalogue test checks each exists, is active and has the class its annotations
#: need).
CITED_RULES: Final = (
    R_TABLE, R_PREFIX, R_DOMAIN, R_UNKNOWN, R_PRINCIPAL, R_PROMPT_PAYLOAD, R_AGENT, R_FIXTURE, R_TOOL_DEFS, R_HARNESS, R_ENV,
    R_WINDOW, R_DESCRIPTION, R_PROMPT, R_AGENT_OUT, R_CLASS, R_CONFIGURED, R_AUTHOR, R_TASK, R_ATTACK, R_CONTROL,
    R_NON_INFORMATIVE, R_TAINT, NORMALISER,
)
_STATUSES: Final[list[Json]] = ["present", "absent", "ambiguous", "gap"]
_MARKER: Final[dict[str, Json]] = {
    "type": "object", "additionalProperties": False, "required": ["fixture", "status", "normaliser"],
    "properties": {"fixture": {"type": "string"}, "status": {"enum": _STATUSES}, "normaliser": {"type": "string"}},
}
CLASSES: Final = ("observed_tool_output", "observed_description_log", "observed_user_step", "partial_match",
                  "agent_output_only", "logged_absent", "configured_only", "unmatchable")
NS: Final[Mapping[str, Json]] = MappingProxyType({
    "dtap.exposure": {
        "type": "object", "additionalProperties": False, "required": ["fixture", "channel", "class"],
        "properties": {"fixture": {"type": "string"}, "channel": {"enum": ["environment", "tool", "skill", "prompt", "other"]},
                       "class": {"enum": list(CLASSES)}},
    },
    "dtap.description_marker": {
        "type": "object", "additionalProperties": False, "required": ["fixture", "status", "normaliser", "placement"],
        "properties": {"fixture": {"type": "string"}, "status": {"enum": _STATUSES}, "normaliser": {"type": "string"},
                       "placement": {"enum": ["entry", "entry_mismatch", "log", "none"]}},
    },
    "dtap.prompt_marker": _MARKER,
    "dtap.agent_output_marker": _MARKER,
    "dtap.non_informative": {
        "type": "object", "additionalProperties": False, "required": ["origin"], "properties": {"origin": {"type": "string"}},
    },
})
_HARNESS_TYPES: Final = frozenset({"dtap:tool_name_list", "dtap:error_text"})
_ORDER: Final = {"none": 0, "partial": 1, "full": 2}


class ProfileDataError(SemanticsProfileError):
    code = "sem.profile_data"


@dataclass(frozen=True, slots=True)
class Tables:
    """The parsed data files: tool inventory per server, built-ins, reviewed labels, outcome and taint settings."""

    servers: Mapping[str, frozenset[str]]
    builtins: Mapping[str, tuple[tuple[str, ...], str]]  # name -> (roles, output integrity)
    labels: Mapping[tuple[str, str], tuple[tuple[str, ...], str]]  # (server, tool) -> (roles, output integrity)
    domains: Mapping[str, frozenset[str]]  # domain -> the MCP servers its configurations enable
    outcomes: Mapping[str, Any]
    taint: TaintPolicy
    min_needle: int
    window: int


def _strings(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProfileDataError(f"{where}: an array of strings is required")
    return list(value)


def _label(entry: Mapping[str, Any], where: str) -> tuple[tuple[str, ...], str]:
    """``(roles, integrity)`` of one reviewed entry; its evidence, integrity and reason are checked (D.16.9)."""
    roles = tuple(_strings(entry.get("roles"), where))
    evidence = _strings(entry.get("evidence"), where)
    integrity = entry.get("integrity")
    if not roles or any(r not in ROLE_VALUES for r in roles) or len(set(roles)) != len(roles) or \
            ("unknown" in roles and len(roles) > 1):
        raise ProfileDataError(f"{where}: roles must be distinct values of the E.7.1 vocabulary, unknown alone")
    if integrity not in INTEGRITY_VALUES or integrity == "trusted":
        raise ProfileDataError(f"{where}: output integrity is untrusted or unknown (no tool code is verified)")
    if not evidence or any(e not in EVIDENCE for e in evidence) or len(set(evidence)) != len(evidence) or \
            not {"description", "observed"} & set(evidence):
        raise ProfileDataError(f"{where}: evidence must name description or observed (a name alone is not enough)")
    if not isinstance(entry.get("reason"), str) or not entry["reason"]:
        raise ProfileDataError(f"{where}: a reason is required")
    return roles, str(integrity)


def parse_tables(files: Mapping[str, bytes]) -> Tables:
    missing = [n for n in DATA_FILES if n not in files]
    if missing:
        raise ProfileDataError(f"dtap.tools@1 data file(s) missing: {missing}")
    doc = {name: tomllib.loads(files[name].decode("utf-8")) for name in DATA_FILES}
    servers = {str(s["name"]): frozenset(_strings(s.get("tools", []), f"server {s.get('name')}"))
               for s in doc["servers.toml"].get("server", [])}
    builtins: dict[str, tuple[tuple[str, ...], str]] = {}
    for entry in doc["builtins.toml"].get("builtin", []):
        name = str(entry.get("name"))
        if name in builtins:
            raise ProfileDataError(f"builtin {name!r}: repeated")
        builtins[name] = _label(entry, f"builtin {name!r}")
    labels: dict[tuple[str, str], tuple[tuple[str, ...], str]] = {}
    for entry in doc["labels.toml"].get("label", []):
        key = (str(entry.get("server")), str(entry.get("tool")))
        if key in labels:
            raise ProfileDataError(f"label {key!r}: repeated")
        if key[1] not in servers.get(key[0], frozenset()):
            raise ProfileDataError(f"label {key!r}: the tool is not in the server's inventory")
        labels[key] = _label(entry, f"label {key!r}")
    domains = {str(d["name"]): frozenset(_strings(d.get("servers", []), f"domain {d.get('name')}"))
               for d in doc["domains.toml"].get("domain", [])}
    prof = doc["profile.toml"]
    taint = prof["taint"]
    policy = TaintPolicy(str(taint["rule"]), frozenset(_strings(taint["subject_roles"], "taint")),
                         frozenset(_strings(taint["object_integrity"], "taint")))
    matcher = prof["matcher"]
    if matcher.get("normaliser") != NORMALISER:
        raise ProfileDataError("dtap.tools@1 uses the normaliser dtap.alnum_norm@1")
    return Tables(MappingProxyType(servers), MappingProxyType(builtins), MappingProxyType(labels), MappingProxyType(domains),
                  MappingProxyType(dict(prof["outcomes"])), policy, int(matcher["min_needle"]), int(matcher["window"]))


def _obj(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dtap(record: Mapping[str, Any]) -> dict[str, Any]:
    return _obj(_obj(record.get("ext")).get("dtap"))


@dataclass
class _Payload:
    fid: str
    channel: str  # environment | tool | skill | prompt | other
    needles: list[str]
    injected_tool: str | None


@dataclass
class _Run:
    """What one annotate pass knows about the AER."""

    aer: AerDocument
    actors: set[str] = field(default_factory=set)
    payloads: list[_Payload] = field(default_factory=list)
    tools_fixture: dict[str, Any] | None = None
    norm: dict[str, str] = field(default_factory=dict)  # part id / pseudo id -> normalised text
    # per payload: location kind -> list of (target, status, premise pointer record id, pointer)
    found: dict[str, dict[str, list[tuple[str, str, str, str]]]] = field(default_factory=dict)
    tool_parts: list[tuple[str, str]] = field(default_factory=list)  # (message id, pointer) of every tool result
    user_parts: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class DtapToolsProfile:
    """``dtap.tools`` at version 1 or 2 (satisfies :class:`agentprov.sem.types.SemanticsProfile`)."""

    id: str
    version: int
    sha256: str
    tables: Tables
    classes: Mapping[str, str]
    rules: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({"dtap": 1}))
    ns: Mapping[str, Json] = field(default_factory=lambda: NS)
    taint_policy: TaintPolicy | None = None

    # ------------------------------------------------------------------------------------------ helpers
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

    def tool_label(self, name: object, server: object, domain: object = None) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        """``(roles, output integrity, rules)`` of a tool as logged (``server``, ``tool_name``) in a run of ``domain``;
        fail-closed (``dtap.unknown_tool@1``) for a tool no table labels. Also used by ``tools/dtap/tool_census.py``.

        Server ``"unknown"``: a listed harness built-in (``builtins.toml``); otherwise, when the name is in the inventory
        of exactly one MCP server that the run's domain configures, that server's label
        (``dtap.unknown_server_domain_match@1``: openaisdk logs a failed MCP call with server ``"unknown"``)."""
        unknown: tuple[str, ...] = ("unknown",)
        if not isinstance(name, str):
            return unknown, "unknown", (R_UNKNOWN,)
        if server == "unknown":
            builtin = self.tables.builtins.get(name)
            if builtin is not None:
                return builtin[0], builtin[1], (R_TABLE,)
            candidates = [s for s in sorted(self.tables.domains.get(domain, ()) if isinstance(domain, str) else ())
                          if name in self.tables.servers.get(s, frozenset())]
            matched = self.tables.labels.get((candidates[0], name)) if len(candidates) == 1 else None
            return (unknown, "unknown", (R_UNKNOWN,)) if matched is None else (matched[0], matched[1], (R_TABLE, R_DOMAIN))
        split: tuple[str, ...] = ()
        if server == OPENCLAW:
            prefix = max((s for s in self.tables.servers if name.startswith(s + "_")), key=len, default=None)
            split = (R_PREFIX,)
            if prefix is not None:
                server, name = prefix, name[len(prefix) + 1:]
        if not isinstance(server, str) or name not in self.tables.servers.get(server, frozenset()):
            return unknown, "unknown", (R_UNKNOWN, *split)
        found = self.tables.labels.get((server, name))
        if found is None:
            return unknown, "unknown", (R_UNKNOWN, *split)
        return found[0], found[1], (R_TABLE, *split)

    def _tool(self, run: _Run, name: object, server: object) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        return self.tool_label(name, server, _obj(_dtap(run.aer.header).get("path_facets")).get("domain"))

    @staticmethod
    def _domain_premise(rules: Sequence[str]) -> list[Premise]:
        """The run's domain is a premise of a label resolved by the domain match."""
        return [Premise("exec", "/ext/dtap/path_facets/domain")] if R_DOMAIN in rules else []

    # ------------------------------------------------------------------------------------------ annotate
    def annotate(self, aer: AerDocument) -> Iterator[Annotation]:
        run = _Run(aer)
        self._prepare(run)
        for record in aer.records[1:]:
            kind = record.get("k")
            if kind == "fixture":
                yield from self._fixture(run, record)
            elif kind == "message":
                yield from self._message(run, record)
            elif kind == "tool_execution":
                yield self._execution(run, record)
            elif kind == "artefact" and record.get("type") in _HARNESS_TYPES:
                rid = str(record["id"])
                yield self._ann(run, rid, "integrity", "trusted", (R_HARNESS,), (Premise(rid, "/type"),))
            elif kind == "judgement":
                found = self._outcome(run, record)
                if found is not None:
                    yield found
        yield from self._agent_output(run)
        yield from self._exposures(run)

    def _prepare(self, run: _Run) -> None:
        for record in run.aer.records[1:]:
            kind = record.get("k")
            if kind == "actor":
                run.actors.add(str(record["id"]))
            elif kind == "fixture" and record.get("kind") == "injection_payload":
                vector = record.get("vector")
                step = _obj(_dtap(record).get("step"))
                # the vector's channel, else (@2 only: regen item 54, version-gated by the D-31 owner's ruling of
                # 2026-10-21) the configured step type of a step without its vector field; @1 keeps "other"
                fallback = step.get("type") if self.version >= ITEM_54_SINCE else "other"
                channel = vector.split(":", 1)[0] if isinstance(vector, str) else fallback
                channel = channel if channel in ("environment", "tool", "skill", "prompt") else "other"
                tool = step.get("injected_tool")
                payload = _Payload(str(record["id"]), channel, needles(record.get("content"), minimum=self.tables.min_needle),
                                   tool if isinstance(tool, str) else None)
                run.payloads.append(payload)
                run.found[payload.fid] = {}
            elif kind == "fixture" and record.get("kind") == "tool_definitions":
                run.tools_fixture = record
            elif kind == "message":
                for k, part in enumerate(record.get("parts") or []):
                    pid = f"{record['id']}#{k}"
                    if part.get("t") == "tool_result":
                        run.tool_parts.append((str(record["id"]), f"/parts/{k}"))
                        run.norm[pid] = normalise(serialise(part.get("text", part.get("value"))))
                    elif record.get("role") == "user":
                        run.user_parts.append((str(record["id"]), f"/parts/{k}"))
                        run.norm[pid] = normalise(serialise(part.get("text", part.get("value"))))
                    elif record.get("role") == "agent":
                        body = part.get("text") if part.get("t") == "text" else {"name": part.get("name"), "args": part.get("args")}
                        run.norm[pid] = normalise(serialise(body if body is not None else part.get("value")))
        final = _dtap(run.aer.header).get("final_response")
        if isinstance(final, str):
            run.norm["exec"] = normalise(final)

    def _match(self, payload: _Payload, text: str) -> str:
        best = "none"
        for needle in payload.needles:
            if needle in text:
                return "full"
            if best == "none" and any(w in text for w in windows(needle, self.tables.window)):
                best = "partial"
        return best

    def _status(self, payload: _Payload, level: str) -> str:
        if not payload.needles:
            return "gap"
        return {"full": "present", "partial": "ambiguous", "none": "absent"}[level]

    def _marker_rules(self, status: str, rule: str) -> tuple[str, ...]:
        return (R_WINDOW,) if status == "ambiguous" else (rule,)

    # ------------------------------------------------------------------------------------------ records
    def _fixture(self, run: _Run, record: Mapping[str, Any]) -> Iterator[Annotation]:
        fid = str(record["id"])
        kind = record.get("kind")
        if kind == "injection_payload" or (kind == "other" and str(record.get("subtype", "")).startswith("dtap.attack_goal")):
            yield self._ann(run, fid, "integrity", "untrusted", (R_FIXTURE,), (Premise(fid, "/kind"),))
        elif kind == "tool_definitions":
            yield self._ann(run, fid, "integrity", "unknown", (R_TOOL_DEFS,), (Premise(fid, "/kind"),))
            yield from self._descriptions(run, record)

    def _entries(self, content: object) -> list[tuple[str, str, str]]:
        """``(pointer, entry name, normalised text)`` of every entry of a logged tool list (``server:tool`` keys, a
        ``{server: [{name, description}]}`` map, or a list of named entries)."""
        out: list[tuple[str, str, str]] = []
        if isinstance(content, dict):
            for key, value in content.items():
                if isinstance(value, list):
                    for i, entry in enumerate(value):
                        name = _obj(entry).get("name")
                        out.append((f"/content/{pointer_escape(key)}/{i}", f"{key}:{name}", normalise(serialise(entry))))
                else:
                    out.append((f"/content/{pointer_escape(key)}", str(key), normalise(serialise({key: value}))))
        elif isinstance(content, list):
            for i, entry in enumerate(content):
                name = _obj(entry).get("name")
                out.append((f"/content/{i}", str(name), normalise(serialise(entry))))
        return out

    def _descriptions(self, run: _Run, record: Mapping[str, Any]) -> Iterator[Annotation]:
        fid = str(record["id"])
        entries = self._entries(record.get("content"))
        whole = normalise(serialise(record.get("content")))
        for payload in run.payloads:
            if payload.channel not in ("tool", "skill"):
                continue
            named = [e for e in entries if payload.injected_tool is not None and e[1] == payload.injected_tool]
            placement, at, level = "none", None, "none"
            for pointer, _name, text in named:
                level = self._match(payload, text)
                if level != "none":
                    placement, at = "entry", pointer
                    break
            if level == "none":
                for pointer, _name, text in entries:
                    found = self._match(payload, text)
                    if found != "none":
                        placement, at, level = ("entry_mismatch" if payload.injected_tool else "log"), pointer, found
                        break
            if level == "none":
                level = self._match(payload, whole)
                placement = "log" if level != "none" else "none"
            status = self._status(payload, level)
            value: dict[str, Json] = {"fixture": payload.fid, "status": status, "normaliser": NORMALISER, "placement": placement}
            premises = (Premise(fid, at or "/content"), Premise(payload.fid, "/content"))
            run.found[payload.fid].setdefault("description", []).append((fid, status, fid, at or "/content"))
            yield self._ann(run, fid, "dtap.description_marker", value, self._marker_rules(status, R_DESCRIPTION), premises, at=at)

    def _message(self, run: _Run, record: Mapping[str, Any]) -> Iterator[Annotation]:
        mid = str(record["id"])
        role = record.get("role")
        for k, part in enumerate(record.get("parts") or []):
            pid = f"{mid}#{k}"
            t = part.get("t")
            if t == "tool_result":
                yield from self._result(run, record, k, pid)
            elif role == "user":
                yield from self._user_part(run, mid, k, pid)
            elif role == "agent" and record.get("actor") == "agent":
                yield self._ann(run, pid, "integrity", "trusted", (R_AGENT,), (Premise(mid, "/actor"),))
                if t == "tool_call":
                    roles, _integrity, rules = self._tool(run, part.get("name"), _dtap(record).get("server"))
                    premises = [Premise(mid, f"/parts/{k}/name")]
                    if "server" in _dtap(record):
                        premises.append(Premise(mid, "/ext/dtap/server"))
                    yield self._ann(run, pid, "role", list(roles), rules, premises + self._domain_premise(rules))

    def _user_part(self, run: _Run, mid: str, k: int, pid: str) -> Iterator[Annotation]:
        text = run.norm.get(pid, "")
        present: list[str] = []
        for payload in run.payloads:
            if payload.channel != "prompt":
                continue
            status = self._status(payload, self._match(payload, text) if payload.needles else "none")
            run.found[payload.fid].setdefault("user", []).append((pid, status, mid, f"/parts/{k}"))
            annotation = self._ann(run, pid, "dtap.prompt_marker",
                                   {"fixture": payload.fid, "status": status, "normaliser": NORMALISER},
                                   self._marker_rules(status, R_PROMPT), (Premise(mid, f"/parts/{k}"), Premise(payload.fid, "/content")))
            if status == "present":
                present.append(payload.fid)
            yield annotation
        if present:
            yield self._ann(run, pid, "integrity", "untrusted", (R_PROMPT_PAYLOAD,),
                            (Premise(mid, f"/parts/{k}"), Premise(present[0], "/content")))
            if "att" in run.actors:
                yield self._ann(run, pid, "author", {"actor": "att"}, (R_AUTHOR,),
                                (Premise(mid, f"/parts/{k}"), Premise(present[0], "/content")))
        else:
            yield self._ann(run, pid, "integrity", "trusted", (R_PRINCIPAL,), (Premise(mid, "/role"),))

    def _producer(self, run: _Run, record: Mapping[str, Any]) -> tuple[object, object, list[Premise]]:
        """The tool name and server of a result message, through its generating execution and that call's message."""
        te = run.aer.get(str(record.get("generated_by")))
        if te is None or te.get("k") != "tool_execution" or not isinstance(te.get("call"), str):
            return None, None, [Premise(str(record["id"]), "/generated_by")] if "generated_by" in record else []
        call_mid = str(te["call"]).split("#", 1)[0]
        call_msg = run.aer.get(call_mid) or {}
        premises = [Premise(str(te["id"]), "/name"), Premise(str(te["id"]), "/call")]
        if "server" in _dtap(call_msg):
            premises.append(Premise(call_mid, "/ext/dtap/server"))
        return te.get("name"), _dtap(call_msg).get("server"), premises

    def _result(self, run: _Run, record: Mapping[str, Any], k: int, pid: str) -> Iterator[Annotation]:
        mid = str(record["id"])
        name, server, premises = self._producer(run, record)
        _roles, integrity, rules = self._tool(run, name, server)
        premises = (premises or [Premise(mid, f"/parts/{k}")]) + self._domain_premise(rules)
        yield self._ann(run, pid, "integrity", integrity, rules, premises)
        part = (record.get("parts") or [])[k]
        text_pointer = f"/parts/{k}/text" if "text" in part else f"/parts/{k}/value"
        text = run.norm.get(pid, "")
        for payload in run.payloads:
            if payload.channel not in ("environment", "skill"):
                continue
            status = self._status(payload, self._match(payload, text) if payload.needles else "none")
            run.found[payload.fid].setdefault("tool_output", []).append((pid, status, mid, f"/parts/{k}"))
            value: dict[str, Json] = {"fixture": payload.fid, "status": status, "normaliser": NORMALISER}
            yield self._ann(run, pid, "injection_marker", value, self._marker_rules(status, R_ENV),
                            (Premise(mid, text_pointer), Premise(payload.fid, "/content")))

    def _execution(self, run: _Run, record: Mapping[str, Any]) -> Annotation:
        rid = str(record["id"])
        server: object = None
        premises = [Premise(rid, "/name")]
        if isinstance(record.get("call"), str):
            call_mid = str(record["call"]).split("#", 1)[0]
            server = _dtap(run.aer.get(call_mid) or {}).get("server")
            if server is not None:
                premises.append(Premise(call_mid, "/ext/dtap/server"))
            roles, _integrity, rules = self._tool(run, record.get("name"), server)
            premises += self._domain_premise(rules)
        else:
            roles, rules = ("unknown",), (R_UNKNOWN,)
        return self._ann(run, rid, "role", list(roles), rules, premises)

    def _outcome(self, run: _Run, record: Mapping[str, Any]) -> Annotation | None:
        jid = str(record["id"])
        origin, value, name = record.get("origin"), record.get("value"), record.get("name")
        if origin == "harness_default":
            return self._ann(run, jid, "dtap.non_informative", {"origin": "harness_default"}, (R_NON_INFORMATIVE,),
                             (Premise(jid, "/origin"),))
        if origin not in self.tables.outcomes["checker_origins"] or not isinstance(value, bool):
            return None
        premises = (Premise(jid, "/name"), Premise(jid, "/value"), Premise(jid, "/origin"))
        if name == "task_success":
            return self._ann(run, jid, "outcome", {"claim": str(self.tables.outcomes["task_success"]), "holds": value},
                             (R_TASK,), premises)
        if name == "attack_success":
            threat = _obj(_dtap(run.aer.header).get("path_facets")).get("threat")
            if threat == self.tables.outcomes["control_threat"]:
                return self._ann(run, jid, "outcome", {"claim": str(self.tables.outcomes["control_claim"]), "holds": value},
                                 (R_CONTROL,), (*premises, Premise("exec", "/ext/dtap/path_facets/threat")))
            return self._ann(run, jid, "outcome", {"claim": str(self.tables.outcomes["attack_success"]), "holds": value},
                             (R_ATTACK,), premises)
        return None

    # ------------------------------------------------------------------------------------------ end of file
    def _agent_output(self, run: _Run) -> Iterator[Annotation]:
        locations = [pid for pid in run.norm if pid != "exec" and self._is_agent(run, pid)]
        if "exec" in run.norm:
            locations.append("exec")
        for payload in run.payloads:
            if not payload.needles or any(s in ("present", "ambiguous") for rows in run.found[payload.fid].values()
                                          for _t, s, _r, _p in rows):
                continue
            for pid in locations:
                level = self._match(payload, run.norm[pid])
                if level == "none":
                    continue
                status = self._status(payload, level)
                value: dict[str, Json] = {"fixture": payload.fid, "status": status, "normaliser": NORMALISER}
                if pid == "exec":
                    premise, target, at = Premise("exec", "/ext/dtap/final_response"), "exec", "/ext/dtap/final_response"
                else:
                    mid, _, k = pid.partition("#")
                    premise, target, at = Premise(mid, f"/parts/{k}"), pid, None
                run.found[payload.fid].setdefault("agent", []).append((target, status, premise.id, premise.p))
                yield self._ann(run, target, "dtap.agent_output_marker", value, self._marker_rules(status, R_AGENT_OUT),
                                (premise, Premise(payload.fid, "/content")), at=at)
                break

    @staticmethod
    def _is_agent(run: _Run, pid: str) -> bool:
        record = run.aer.get(pid.split("#", 1)[0]) or {}
        return record.get("role") == "agent" and record.get("actor") == "agent"

    def _exposures(self, run: _Run) -> Iterator[Annotation]:
        tools_fx = str(run.tools_fixture["id"]) if run.tools_fixture is not None else None
        for payload in run.payloads:
            rows = run.found[payload.fid]
            value: dict[str, Json] = {"fixture": payload.fid, "channel": payload.channel}
            # premises that exist: under @2 a payload whose content or vector is not recorded (unk, regen item 54) cites
            # /kind; @1 keeps its original premises /content and /vector (D-31 owner ruling 2026-10-21)
            fixture = run.aer.get(payload.fid) or {}
            gated = self.version >= ITEM_54_SINCE
            content = Premise(payload.fid, "/content" if "content" in fixture or not gated else "/kind")
            vector = Premise(payload.fid, "/vector" if "vector" in fixture or not gated else "/kind")
            located = {"environment": ("tool_output",), "skill": ("tool_output", "description"),
                       "tool": ("description",), "prompt": ("user",)}.get(payload.channel, ())
            observed = {"tool_output": "observed_tool_output", "description": "observed_description_log",
                        "user": "observed_user_step"}
            if not payload.needles:
                cls, rules, premises = "unmatchable", (R_CLASS,), [content]
            elif hit := next(((loc, r) for loc in located for r in rows.get(loc, []) if r[1] == "present"), None):
                loc, row = hit
                cls, rules, premises = observed[loc], (R_CLASS,), [content, Premise(row[2], row[3])]
            elif hit := next(((loc, r) for loc in located for r in rows.get(loc, []) if r[1] == "ambiguous"), None):
                _loc, row = hit
                cls, rules, premises = "partial_match", (R_WINDOW,), [content, Premise(row[2], row[3])]
            elif agent := next((r for r in rows.get("agent", []) if r[1] == "present"), None):
                cls, rules, premises = "agent_output_only", (R_CLASS,), [content, Premise(agent[2], agent[3])]
            elif agent := next((r for r in rows.get("agent", []) if r[1] == "ambiguous"), None):
                cls, rules, premises = "partial_match", (R_WINDOW,), [content, Premise(agent[2], agent[3])]
            else:
                logged: list[Premise] = []
                if "tool_output" in located:
                    logged += [Premise(m, p) for m, p in run.tool_parts]
                if "description" in located and tools_fx is not None:
                    logged.append(Premise(tools_fx, "/content"))
                if "user" in located:
                    logged += [Premise(m, p) for m, p in run.user_parts]
                if logged:
                    cls, rules, premises = "logged_absent", (R_CLASS,), [content, *logged]
                else:
                    cls, rules = "configured_only", (R_CONFIGURED,)
                    premises = [vector, Premise("exec", "/ext/dtap/join")]
            value["class"] = cls
            yield self._ann(run, "run", "dtap.exposure", value, rules, premises)


def build(profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> DtapToolsProfile:
    """Build ``dtap.tools@1``, ``@2`` or ``@3`` from its data files (called by :func:`agentprov.adapters.semantics_profiles.load_semantics_profile`)."""
    if profile_id != PROFILE_ID or version not in CATALOGUE_OF:
        raise ProfileDataError(f"this code builds {PROFILE_ID}@{sorted(CATALOGUE_OF)}, not {profile_id}@{version}")
    tables = parse_tables(files)
    declared = CATALOGUE_OF[version]
    catalogue = load_catalogue("dtap", declared)
    classes: dict[str, str] = {}
    for ref in CITED_RULES:
        entry = catalogue.get(ref)
        if entry is None or not entry.citable:
            raise ProfileDataError(f"{ref} is not an active rule of the dtap catalogue v{declared}")
        classes[ref] = entry.cls
    return DtapToolsProfile(profile_id, version, sha256, tables, MappingProxyType(classes),
                            rules=MappingProxyType({"dtap": declared}), taint_policy=tables.taint)
