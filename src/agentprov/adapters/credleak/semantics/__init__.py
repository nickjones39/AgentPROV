"""The credential-leak semantics profile ``credleak.tools`` (docs/architecture D.19.9; C.14; EF E.7).

A semantics profile reads one AER and yields standoff annotations (role, integrity, channel) from the tables in
``credleak.tools-<version>/tables.toml``; the SEM engine numbers and seals them. Version 2 (D-605, D-31) has version
1's tables unchanged and declares the ``credleak`` rule catalogue version 2 (:data:`CATALOGUE_OF`; one catalogue version
per corpus, H.2.5); version 1 stays for the corpora that recorded it. Every annotation is class ``I``: the tables are
the profile author's reading of the harness's tool names, not a verified property of its implementation (rules
``credleak.tool_role_table@1``, ``credleak.tool_output_label_table@1``, ``credleak.observation_label_table@1``).

* a ``tool_call`` part and a ``tool_execution`` get ``role`` from the tool table (``["unknown"]`` for a name that is not
  listed exactly, so the malformed names some models emitted are never read as a known tool);
* a ``tool_result`` part gets ``integrity`` (and ``channel``) from the tool execution that generated it (``unknown``
  when the tool is not listed);
* the scripted user message gets an ``integrity`` from its actor (no ``channel``: C.14.3 allows it on ``tool_result``
  parts and artefacts only).

The harness's detector judgements are not interpreted here (no ``outcome``): their polarity is the study's, and the
deposit corrected one of them after the runs (census §6). Taint policy: sink roles plus ``unknown`` over ``untrusted``
and ``unknown`` integrity (``credleak.taint_sink_untrusted@1``).

This package imports only the standard library and ``agentprov.{aer,sem}`` (D.2.1 boundary test).
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from agentprov.aer.types import Json
from agentprov.sem.profiles import SemanticsProfileError
from agentprov.sem.types import INTEGRITY_VALUES, ROLE_VALUES, Annotation, Premise, TaintPolicy

if TYPE_CHECKING:
    from agentprov.aer.reader import AerDocument

__all__ = ["CATALOGUE_OF", "PROFILE_ID", "CredleakToolsProfile", "build_profile"]

PROFILE_ID: Final = "credleak.tools"
#: The ``credleak`` catalogue version each profile version declares (D-31 option B; D-605).
CATALOGUE_OF: Final = MappingProxyType({1: 1, 2: 2})
_TABLES: Final = "tables.toml"
_RULE_ROLE: Final = "credleak.tool_role_table@1"
_RULE_OUTPUT: Final = "credleak.tool_output_label_table@1"
_RULE_OBSERVATION: Final = "credleak.observation_label_table@1"
_RULE_TAINT: Final = "credleak.taint_sink_untrusted@1"
_UNKNOWN_ROLES: Final = ("unknown",)


def _label(entry: Mapping[str, Any], where: str) -> tuple[str, str | None]:
    integrity, channel = entry.get("integrity"), entry.get("channel")
    if integrity not in INTEGRITY_VALUES:
        raise SemanticsProfileError(f"{where}: integrity {integrity!r} is not in the closed vocabulary")
    if channel is not None and (not isinstance(channel, str) or not channel):
        raise SemanticsProfileError(f"{where}: channel must be a non-empty string")
    return str(integrity), channel


class CredleakToolsProfile:
    """``credleak.tools@<version>``: the tool and observation tables of the study's coding-agent harness."""

    ns: Mapping[str, Json] = {}

    def __init__(self, profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> None:
        if profile_id != PROFILE_ID or version not in CATALOGUE_OF or _TABLES not in files:
            raise SemanticsProfileError(f"not the credleak semantics profile: {profile_id}@{version}")
        self._id, self._version, self._sha256 = profile_id, version, sha256
        doc = tomllib.loads(files[_TABLES].decode("utf-8"))
        self._tools: dict[str, tuple[tuple[str, ...], str, str | None]] = {}  # name -> (roles, integrity, channel)
        for entry in doc.get("tool", []):
            roles = tuple(entry.get("roles", ()))
            if not roles or any(r not in ROLE_VALUES for r in roles):
                raise SemanticsProfileError(f"tool {entry.get('name')!r}: roles must be a non-empty subset of the vocabulary")
            integrity, channel = _label(entry, f"tool {entry.get('name')!r}")
            if entry["name"] in self._tools:
                raise SemanticsProfileError(f"tool {entry['name']!r} is listed twice")
            self._tools[str(entry["name"])] = (roles, integrity, channel)
        self._observations: dict[str, str] = {}
        for entry in doc.get("observation", []):
            integrity, channel = _label(entry, f"observation {entry.get('actor')!r}")
            if channel is not None:
                raise SemanticsProfileError(f"observation {entry.get('actor')!r}: C.14.3 allows no channel on this part kind")
            self._observations[str(entry["actor"])] = integrity
        taint = doc["taint"]
        subjects, objects = frozenset(taint["subject_roles"]), frozenset(taint["object_integrity"])
        if not subjects <= frozenset(ROLE_VALUES) or not objects <= frozenset(INTEGRITY_VALUES):
            raise SemanticsProfileError("the taint policy names values outside the closed vocabularies")
        self._taint = TaintPolicy(rule=_RULE_TAINT, subject_roles=subjects, object_integrity=objects)

    @property
    def id(self) -> str:
        return self._id

    @property
    def version(self) -> int:
        return self._version

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def rules(self) -> Mapping[str, int]:
        return {"credleak": CATALOGUE_OF[self._version]}

    @property
    def taint_policy(self) -> TaintPolicy | None:
        return self._taint

    def annotate(self, aer: AerDocument) -> Iterator[Annotation]:
        """Yield the annotations in AER file order (deterministic; reads only the AER)."""
        for rec in aer.records:
            kind = rec.get("k")
            if kind == "message":
                yield from self._message(aer, rec)
            elif kind == "tool_execution":
                yield Annotation(str(rec["id"]), "role", list(self._roles(rec.get("name"))), "I", (_RULE_ROLE,),
                                 (Premise(str(rec["id"]), "/name"),))

    def _roles(self, name: object) -> tuple[str, ...]:
        entry = self._tools.get(name) if isinstance(name, str) else None
        return entry[0] if entry is not None else _UNKNOWN_ROLES

    def _message(self, aer: AerDocument, msg: Mapping[str, Any]) -> Iterator[Annotation]:
        mid = str(msg["id"])
        parts = msg.get("parts")
        if not isinstance(parts, list):
            return
        generator = aer.get(str(msg["generated_by"])) if isinstance(msg.get("generated_by"), str) else None
        execution = generator if generator is not None and generator.get("k") == "tool_execution" else None
        observation = self._observations.get(str(msg.get("actor"))) if msg.get("role") == "user" else None
        for index, part in enumerate(parts):
            if not isinstance(part, dict):
                continue
            target, t = f"{mid}#{index}", part.get("t")
            if t == "tool_call":
                yield Annotation(target, "role", list(self._roles(part.get("name"))), "I", (_RULE_ROLE,),
                                 (Premise(mid, f"/parts/{index}/name"),))
            elif t == "tool_result" and execution is not None:
                name = execution.get("name")
                entry = self._tools.get(name) if isinstance(name, str) else None
                integrity, channel = ("unknown", None) if entry is None else entry[1:]
                premises = (Premise(str(execution["id"]), "/name"),)
                yield Annotation(target, "integrity", integrity, "I", (_RULE_OUTPUT,), premises)
                if channel is not None:
                    yield Annotation(target, "channel", channel, "I", (_RULE_OUTPUT,), premises)
            if observation is not None:
                yield Annotation(target, "integrity", observation, "I", (_RULE_OBSERVATION,),
                                 (Premise(mid, "/actor"), Premise(mid, "/role")))


def build_profile(profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> CredleakToolsProfile:
    """The entry point of :func:`agentprov.adapters.semantics_profiles.load_semantics_profile` (C.14.1)."""
    return CredleakToolsProfile(profile_id, version, files, sha256)
