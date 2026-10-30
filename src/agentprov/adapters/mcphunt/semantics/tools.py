"""The semantics profile ``mcphunt.tools`` version 1 (docs/architecture D.21.8; C.14; EF E.7.1, E.7.3).

What the profile yields, per record in AER file order:

- **message**, per part: the system and user prompts ``trusted``; agent output ``trusted`` and, on a ``tool_call`` part,
  its ``role`` (the call names ``server__tool``); tool results: ``integrity`` (the tool's label, fail-closed) and
  ``channel`` (the server's);
- **tool_execution**: ``role`` (by its runtime's server and its tool name);
- **judgement**: ``outcome`` for ``outcome`` (``mcphunt.unsafe``) and ``task_completed`` (``user_task_solved``).

The canary flags are not annotations: the AER seal lists them (``mcphunt.canary_flagged``) as the withholding basis
(D-289). Reads only the AER; standard library and ``agentprov.{aer,sem}``.
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

__all__ = ["CITED_RULES", "DATA_FILES", "PROFILE_ID", "McpHuntToolsProfile", "build"]

PROFILE_ID: Final = "mcphunt.tools"
PROFILE_VERSION: Final = 1
PROFILE_VERSIONS: Final = (1, 2)  # 2: version 1's tables on the mcphunt catalogue version 2 (D-31 bump, regen items 38-41)
#: The ``mcphunt`` catalogue version each profile version declares (D-31; H.2.5: one catalogue version per corpus):
#: @1 reads the archived version 1, @2 reads version 2.
CATALOGUE_OF: Final = MappingProxyType({1: 1, 2: 2})
DATA_FILES: Final = ("profile.toml", "tools.toml")

R_TABLE: Final = "mcphunt.tool_table@1"
R_UNKNOWN: Final = "mcphunt.unknown_tool@1"
R_AGENT: Final = "mcphunt.integrity_agent_output@1"
R_PROMPT: Final = "mcphunt.integrity_principal_prompt@1"
R_CHANNEL: Final = "mcphunt.channel_by_server@1"
R_UNSAFE: Final = "mcphunt.unsafe_meaning@1"
R_COMPLETION: Final = "mcphunt.completion_meaning@1"
R_TAINT: Final = "mcphunt.taint_sink_untrusted@1"
CITED_RULES: Final = (R_TABLE, R_UNKNOWN, R_AGENT, R_PROMPT, R_CHANNEL, R_UNSAFE, R_COMPLETION, R_TAINT)
NS: Final[Mapping[str, Json]] = MappingProxyType({})


class ProfileDataError(SemanticsProfileError):
    code = "sem.profile_data"


@dataclass(frozen=True, slots=True)
class Tables:
    tools: Mapping[tuple[str, str], tuple[tuple[str, ...], str]]  # (server, tool) -> (roles, integrity)
    channels: Mapping[str, str]
    outcomes: Mapping[str, Any]
    taint: TaintPolicy


def _strings(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProfileDataError(f"{where}: an array of strings is required")
    return list(value)


def parse_tables(files: Mapping[str, bytes]) -> Tables:
    if sorted(files) != sorted(DATA_FILES):
        raise ProfileDataError(f"mcphunt.tools data files are {DATA_FILES}, got {sorted(files)}")
    doc = {name: tomllib.loads(files[name].decode("utf-8")) for name in DATA_FILES}
    tools: dict[tuple[str, str], tuple[tuple[str, ...], str]] = {}
    channels: dict[str, str] = {}
    for server in doc["tools.toml"].get("server", []):
        name, channel = server.get("name"), server.get("channel")
        if not isinstance(name, str) or not isinstance(channel, str) or name in channels:
            raise ProfileDataError(f"server {name!r}: a unique name and a channel are required")
        channels[name] = channel
        for entry in server.get("tools", []):
            where = f"tool {name}/{entry.get('name')}"
            roles = tuple(_strings(entry.get("roles"), where))
            integrity = entry.get("integrity")
            if not roles or any(r not in ROLE_VALUES for r in roles) or integrity not in INTEGRITY_VALUES \
                    or integrity == "trusted" or (name, entry.get("name")) in tools:
                raise ProfileDataError(f"{where}: E.7.1 roles, untrusted or unknown integrity, unique")
            tools[(name, str(entry["name"]))] = (roles, str(integrity))
    prof = doc["profile.toml"]
    taint = prof["taint"]
    policy = TaintPolicy(str(taint["rule"]), frozenset(_strings(taint["subject_roles"], "taint")),
                         frozenset(_strings(taint["object_integrity"], "taint")))
    return Tables(MappingProxyType(tools), MappingProxyType(channels), MappingProxyType(dict(prof["outcomes"])), policy)


def _split_call_name(name: object) -> tuple[str | None, str | None]:
    if not isinstance(name, str):
        return None, None
    server, sep, tool = name.partition("__")
    return (server, tool) if sep else (None, name)


@dataclass(frozen=True)
class McpHuntToolsProfile:
    """``mcphunt.tools`` at version 1 or 2 (satisfies :class:`agentprov.sem.types.SemanticsProfile`)."""

    id: str
    version: int
    sha256: str
    tables: Tables
    classes: Mapping[str, str]
    rules: Mapping[str, int]  # the catalogue version this profile version declares (CATALOGUE_OF); no default
    ns: Mapping[str, Json] = field(default_factory=lambda: NS)
    taint_policy: TaintPolicy | None = None

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

    def tool_label(self, server: object, tool: object) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        found = self.tables.tools.get((server, tool)) if isinstance(server, str) and isinstance(tool, str) else None
        if found is None:
            return ("unknown",), "unknown", (R_UNKNOWN,)
        return found[0], found[1], (R_TABLE,)

    def annotate(self, aer: AerDocument) -> Iterator[Annotation]:
        runtimes = {str(r["id"]): r.get("name") for r in aer.records[1:] if r.get("k") == "actor" and r.get("kind") == "tool_runtime"}
        for record in aer.records[1:]:
            kind = record.get("k")
            if kind == "message":
                yield from self._message(aer, record, runtimes)
            elif kind == "tool_execution":
                rid = str(record["id"])
                roles, _i, rules = self.tool_label(runtimes.get(str(record.get("actor"))), record.get("name"))
                yield self._ann(aer, rid, "role", list(roles), rules, (Premise(rid, "/name"), Premise(rid, "/actor")))
            elif kind == "judgement":
                found = self._outcome(aer, record)
                if found is not None:
                    yield found

    def _message(self, aer: AerDocument, record: Mapping[str, Any], runtimes: Mapping[str, Any]) -> Iterator[Annotation]:
        mid = str(record["id"])
        actor, role = record.get("actor"), record.get("role")
        for k, part in enumerate(record.get("parts") or []):
            pid = f"{mid}#{k}"
            t = part.get("t")
            if t == "tool_result":
                te = aer.get(str(record.get("generated_by")))
                if te is not None and te.get("k") == "tool_execution":
                    server = runtimes.get(str(te.get("actor")))
                    _r, integrity, rules = self.tool_label(server, te.get("name"))
                    premises = (Premise(str(te["id"]), "/name"), Premise(str(te["id"]), "/actor"))
                    yield self._ann(aer, pid, "integrity", integrity, rules, premises)
                    channel = self.tables.channels.get(server) if isinstance(server, str) else None
                    if channel is not None:
                        yield self._ann(aer, pid, "channel", channel, (R_CHANNEL,), premises)
                else:
                    yield self._ann(aer, pid, "integrity", "unknown", (R_UNKNOWN,), (Premise(mid, "/generated_by"),))
            elif actor == "agent":
                yield self._ann(aer, pid, "integrity", "trusted", (R_AGENT,), (Premise(mid, "/actor"),))
                if t == "tool_call":
                    server, tool = _split_call_name(part.get("name"))
                    roles, _i, rules = self.tool_label(server, tool)
                    yield self._ann(aer, pid, "role", list(roles), rules, (Premise(mid, f"/parts/{k}/name"),))
            elif role in ("system", "user") and actor in ("harness", "user"):
                yield self._ann(aer, pid, "integrity", "trusted", (R_PROMPT,), (Premise(mid, "/role"), Premise(mid, "/actor")))
            else:
                yield self._ann(aer, pid, "integrity", "unknown", (R_UNKNOWN,), (Premise(mid, "/actor"),))

    def _outcome(self, aer: AerDocument, record: Mapping[str, Any]) -> Annotation | None:
        jid = str(record["id"])
        if record.get("origin") not in self.tables.outcomes["checker_origins"]:
            return None
        name, value = record.get("name"), record.get("value")
        premises = (Premise(jid, "/name"), Premise(jid, "/value"), Premise(jid, "/origin"))
        if name == "outcome" and isinstance(value, str):
            if value in self.tables.outcomes["unsafe_values"]:
                return self._ann(aer, jid, "outcome", {"claim": "mcphunt.unsafe", "holds": True}, (R_UNSAFE,), premises)
            if value in self.tables.outcomes["safe_values"]:
                return self._ann(aer, jid, "outcome", {"claim": "mcphunt.unsafe", "holds": False}, (R_UNSAFE,), premises)
        if name == "task_completed" and isinstance(value, bool):
            return self._ann(aer, jid, "outcome", {"claim": "user_task_solved", "holds": value}, (R_COMPLETION,), premises)
        return None


def build(profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> McpHuntToolsProfile:
    """Build ``mcphunt.tools`` at version 1 or 2 from its data files."""
    if profile_id != PROFILE_ID or version not in PROFILE_VERSIONS:
        raise ProfileDataError(f"this code builds {PROFILE_ID} at versions {list(PROFILE_VERSIONS)}, not "
                               f"{profile_id}@{version}")
    tables = parse_tables(files)
    declared = CATALOGUE_OF[version]
    catalogue = load_catalogue("mcphunt", declared)
    classes: dict[str, str] = {}
    for ref in CITED_RULES:
        entry = catalogue.get(ref)
        if entry is None or not entry.citable:
            raise ProfileDataError(f"{ref} is not an active rule of the mcphunt catalogue v{declared}")
        classes[ref] = entry.cls
    return McpHuntToolsProfile(profile_id, version, sha256, tables, MappingProxyType(classes),
                               MappingProxyType({"mcphunt": declared}), taint_policy=tables.taint)
