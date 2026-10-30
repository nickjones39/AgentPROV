"""The semantics profile ``agentdojo.suites``, versions 1 and 2 (docs/architecture C.14, C.14.8; EF E.7.1, E.7.3; D.1).

Data plus small pure functions. The data are the profile directory ``agentdojo.suites-<version>/`` (``profile.toml``,
``labels.toml``, the generated ``suite_tools.toml``, and at version 2 ``reviewed_tables.toml``); :func:`build` parses
them once, and :meth:`SuitesProfile.annotate` reads only the AER. Version 2 adds reviewed tool tables for suites of
other benchmarks (C.14.8); for benchmark ``agentdojo`` it annotates exactly as version 1. What the profile yields, per
record in AER file order (the yield order is the annotation order):

- **fixture** of a kind in ``[integrity.fixtures]``: ``integrity`` (``injection_payload`` → ``untrusted``); other kinds
  ``unknown``.
- **message**, per content part ``#k``:
  - a ``tool_result`` part: ``integrity`` from the producing tool (the ``tool_execution`` that generated the message,
    or the subject of the ``redact`` decision that did), then its ``channel`` when the tool has one, then one
    ``injection_marker`` per payload fixture;
  - any other part: ``integrity`` from the message author (``[integrity.trusted_authors]``), else ``unknown``;
  - a ``tool_call`` part (the request) additionally gets its ``role``.
- **tool_execution**: ``role``.
- **judgement**: ``outcome`` with explicit polarity, never for ``origin: harness_default``.

A tool is *known* only when it is in the applicable suite tool table (:meth:`SuitesProfile.known_tools`): the
``suite_tools.toml`` table of an ``agentdojo`` suite, or a reviewed table (a tool with the same label in every code
state the table lists); an unknown tool gets integrity ``unknown`` and role ``["unknown"]`` and no channel
(fail-closed, C.14.3). Rule classes come from the ``agentdojo`` catalogue; an annotation's ``ev`` is
``weakest(premise tags, rule classes)`` (C.6.5 rule 3).
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from agentprov.aer.evidence import effective_tag, weakest
from agentprov.aer.rules import load_catalogue
from agentprov.aer.types import Json
from agentprov.adapters.agentdojo.citation import INDEPENDENT, NAMESPACES
from agentprov.adapters.agentdojo.history_table import HistoryTable, origin_introduced_under
from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.agentdojo.semantics import markers
from agentprov.adapters.code_verification import TWIN_SUFFIX, Citations, VerifiedCode, parse_verified_code
from agentprov.adapters.profiles import load_profile
from agentprov.errors import ProfileError
from agentprov.sem.types import (
    INTEGRITY_VALUES,
    ROLE_VALUES,
    Annotation,
    Premise,
    TaintPolicy,
)

if TYPE_CHECKING:
    from agentprov.aer.reader import AerDocument

PROFILE_ID: Final = "agentdojo.suites"
PROFILE_VERSION: Final = 1
PROFILE_VERSIONS: Final = (1, 2, 3)  # 3: version 2 plus the reviewed AgentDyn tables (regeneration-batch item 27 (b))
DATA_FILES: Final = ("labels.toml", "profile.toml", "suite_tools.toml")
#: The data files per version (version 2 adds the reviewed tables, C.14.8).
#: The ``agentdojo`` catalogue version each profile version declares (D-31 addendum, user decisions 2026-10-13): @1 stays
#: on the archived catalogue version 1 (every stored corpus reads it); @2 and @3, read by no stored corpus, moved to 2 in
#: place, and regenerated corpora read them (one catalogue version per corpus, H.2.5; item 1 applies through @2).
CATALOGUE_OF: Final = MappingProxyType({1: 1, 2: 2, 3: 2})
DATA_FILES_OF: Final = MappingProxyType({1: DATA_FILES, 2: (*DATA_FILES, "reviewed_tables.toml"),
                                          3: (*DATA_FILES, "reviewed_tables.toml")})

# Rule ids cited by this profile (all in the ``agentdojo`` catalogue at version 1).
R_TABLE: Final = "agentdojo.suite_tool_table@1"
R_EXTERNAL: Final = "agentdojo.integrity_external_content@1"
R_STATE: Final = "agentdojo.integrity_system_state@1"
R_REDACTED: Final = "agentdojo.integrity_redacted_output@1"
R_PRINCIPAL: Final = "agentdojo.integrity_principal_content@1"
R_AGENT: Final = "agentdojo.integrity_agent_output@1"
R_FIXTURE: Final = "agentdojo.integrity_payload_fixture@1"
R_UNKNOWN_TOOL: Final = "agentdojo.unknown_tool@1"
R_UNKNOWN_AUTHOR: Final = "agentdojo.unknown_author@1"
R_CHANNEL: Final = "agentdojo.channel_table@1"
R_READ: Final = "agentdojo.read_tools@1"
R_SINK: Final = "agentdojo.sink_tools@1"
R_NEUTRAL: Final = "agentdojo.neutral_tools@1"
R_MARKER: Final = "agentdojo.injection_marker_yaml@1"
R_MARKER_AMBIGUOUS: Final = "agentdojo.injection_marker_ambiguous@1"
R_UTILITY: Final = "agentdojo.utility_meaning@1"
R_PREPASS: Final = "agentdojo.injection_task_as_user_task@1"
R_POLARITY: Final = "agentdojo.security_polarity@1"
R_DOS: Final = "agentdojo.dos_security_rule@1"
R_TAINT: Final = "agentdojo.taint_sink_untrusted@1"
R_REVIEWED_TABLE: Final = "agentdojo.reviewed_suite_table@1"
R_REVIEWED_LABEL: Final = "agentdojo.reviewed_tool_label@1"
R_UNESCAPE: Final = markers.AUTODOJO_UNESCAPE
#: Version 2 (regeneration-batch items 6 and 4): a payload fragment, and a success with no payload visible.
R_PARTIAL: Final = "agentdojo.partial_payload@1"
R_HIDDEN: Final = "agentdojo.success_without_visible_payload@1"
T_PARTIAL: Final = "agentdojo.partial_payload"
T_HIDDEN: Final = "agentdojo.success_without_visible_payload"
#: The namespaced annotation types of version 2 and the JSON Schemas of their values (C.14.2 ``ns``).
NS_V2: Final[Mapping[str, Json]] = MappingProxyType({
    T_PARTIAL: {"type": "object", "additionalProperties": False, "required": ["fixture", "chars"],
                "properties": {"fixture": {"type": "string"}, "chars": {"type": "integer", "minimum": markers.PREFIX_CHARS}}},
    T_HIDDEN: {"type": "object", "additionalProperties": False, "required": ["fixtures"],
               "properties": {"fixtures": {"type": "array", "items": {"type": "string"}}}},
})

#: Every rule this profile cites, in a fixed order (the catalogue test checks each exists, is active and has the class
#: its annotations need).
CITED_RULES: Final = (
    R_TABLE, R_EXTERNAL, R_STATE, R_REDACTED, R_PRINCIPAL, R_AGENT, R_FIXTURE, R_UNKNOWN_TOOL, R_UNKNOWN_AUTHOR,
    R_CHANNEL, R_READ, R_SINK, R_NEUTRAL, R_MARKER, R_MARKER_AMBIGUOUS, R_UTILITY, R_PREPASS, R_POLARITY, R_DOS,
    R_TAINT, *markers.NORMALISERS,
)
#: The D rules version 2 cites through their ``_unverified`` twins for a log whose producing code the rule's ``code`` list
#: does not cite (D-86, D.5.4); the normalisers are harness-independent (``citation.INDEPENDENT``).
TWINNED: Final = (R_MARKER, R_UTILITY, R_PREPASS, R_POLARITY, R_DOS, R_UNESCAPE)


def _twin(ref: str) -> str:
    name, _, n = ref.partition("@")
    return f"{name}{TWIN_SUFFIX}@{n}"


#: The rules cited at each version: version 2 adds the reviewed-table rules (C.14.8), the AutoDojo payload unescape (B1)
#: and the twins (D-86).
_CITED_2: Final = (*CITED_RULES, R_REVIEWED_TABLE, R_REVIEWED_LABEL, R_UNESCAPE, *(_twin(r) for r in TWINNED),
                   markers.YAML_NORM_STRICT, R_PARTIAL, R_HIDDEN)
#: Version 3 cites exactly version 2's rules (it adds data only: the reviewed AgentDyn tables, item 27 (b)); items 4, 6
#: and 8 (yaml_norm@2, the partial and hidden-success annotations) are version 2's and so version 3's.
CITED_RULES_OF: Final = MappingProxyType({1: CITED_RULES, 2: _CITED_2, 3: _CITED_2})
#: ``[marker]`` keys of version 2: the payload-side unescape and the ``cache_match`` forms that establish the escape.
_UNESCAPE_MARKER: Final = {"payload_unescape": R_UNESCAPE, "payload_unescape_link": ["exact", "wrapped"]}
#: The ``[selection]`` keys of the reviewed tables and the values version 2 requires (absent at version 1).
_REVIEWED_SELECTION: Final = {"reviewed_tables": "reviewed_tables.toml",
                               "reviewed_code_states": "same_label_in_every_state"}

_ROLE_ORDER: Final = {role: i for i, role in enumerate(ROLE_VALUES)}
_PRINCIPAL_ROLES: Final = frozenset({"system", "user"})


class ProfileDataError(ValueError):
    """The profile's data files are missing or inconsistent with its code (a packaging defect, never input data)."""


@dataclass(frozen=True, slots=True)
class ToolLabel:
    """The labels of one known tool."""

    integrity: str
    integrity_rule: str
    roles: tuple[str, ...]
    role_rules: tuple[str, ...]
    channel: str | None
    channel_rule: str = R_CHANNEL

    def same_label(self, other: ToolLabel) -> bool:
        """Whether two labels state the same roles, integrity and channel (the rules citing them aside)."""
        return (self.roles, self.integrity, self.channel) == (other.roles, other.integrity, other.channel)


@dataclass(frozen=True, slots=True)
class Tables:
    """The parsed profile data."""

    versions: Mapping[str, Mapping[str, frozenset[str]]]
    code_states: Mapping[str, Mapping[str, frozenset[str]]]
    benchmark: str
    untrusted: frozenset[str]
    sink_roles: Mapping[str, tuple[str, ...]]
    endorsers: frozenset[str]
    channels: Mapping[str, str]
    trusted_authors: Mapping[str, frozenset[str]]
    fixture_integrity: Mapping[str, str]
    dos_attacks: frozenset[str]
    prepass_task_kind: str
    prepass_claim: str
    checker_origins: frozenset[str]
    fixture_kinds: frozenset[str]
    #: Version 2: per (benchmark, suite) of a reviewed table, the known tools and their labels (the tools with the same
    #: label in every code state the table lists, C.14.8). Empty at version 1.
    reviewed: Mapping[tuple[str, str], Mapping[str, ToolLabel]] = field(default_factory=lambda: MappingProxyType({}))
    #: Version 2 (B1): the ``ext.autodojo.cache_match`` forms under which a payload is also read with AutoDojo's escape
    #: undone (empty at version 1).
    unescape_links: frozenset[str] = frozenset()

    def label(self, tool: str) -> ToolLabel:
        """The labels of a tool *known* to the applicable table (the caller checks membership)."""
        roles = list(self.sink_roles.get(tool, ()))
        rules = [R_SINK] if roles else []
        untrusted = tool in self.untrusted
        if untrusted:
            roles.append("content_source")
            rules.append(R_READ)
        if tool in self.endorsers:
            roles.append("endorser")
        if not roles:
            roles, rules = ["neutral"], [R_NEUTRAL]
        roles.sort(key=_ROLE_ORDER.__getitem__)
        return ToolLabel("untrusted" if untrusted else "trusted", R_EXTERNAL if untrusted else R_STATE,
                         tuple(roles), tuple(rules), self.channels.get(tool))


def _str_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProfileDataError(f"{where}: expected a list of strings")
    return list(value)


def _suite_tables(table: Any, where: str) -> dict[str, dict[str, frozenset[str]]]:
    if not isinstance(table, dict):
        raise ProfileDataError(f"{where}: expected a table")
    out: dict[str, dict[str, frozenset[str]]] = {}
    for key, entry in table.items():
        suites = entry.get("suites") if isinstance(entry, dict) else None
        if not isinstance(suites, dict):
            raise ProfileDataError(f"{where}.{key}: no suites table")
        out[key] = {suite: frozenset(_str_list(tools, f"{where}.{key}.suites.{suite}")) for suite, tools in suites.items()}
    return out


def _reviewed_label(entry: Any, where: str) -> ToolLabel:
    """One tool's label in one code state of a reviewed table."""
    if not isinstance(entry, dict):
        raise ProfileDataError(f"{where}: expected a table")
    unexpected = set(entry) - {"roles", "integrity", "channel", "code", "reason"}
    if unexpected:
        raise ProfileDataError(f"{where}: unknown keys {sorted(unexpected)}")
    roles = _str_list(entry.get("roles"), f"{where}.roles")
    if (not roles or len(set(roles)) != len(roles) or not set(roles) <= set(ROLE_VALUES) or "unknown" in roles
            or ("neutral" in roles and len(roles) > 1)):
        raise ProfileDataError(f"{where}.roles: a non-empty set of known roles, neutral alone, never unknown")
    integrity = entry.get("integrity")
    if integrity not in INTEGRITY_VALUES:
        raise ProfileDataError(f"{where}.integrity: not an integrity value")
    if (integrity == "untrusted") != ("content_source" in roles):
        raise ProfileDataError(f"{where}: integrity is untrusted exactly when the tool is a content_source")
    channel = entry.get("channel")
    if channel is not None and (not isinstance(channel, str) or not channel):
        raise ProfileDataError(f"{where}.channel: expected a non-empty string")
    for key in ("code", "reason"):
        if not isinstance(entry.get(key), str) or not entry[key]:
            raise ProfileDataError(f"{where}.{key}: every reviewed label states its evidence")
    return ToolLabel(str(integrity), R_REVIEWED_LABEL, tuple(sorted(roles, key=_ROLE_ORDER.__getitem__)),
                     (R_REVIEWED_LABEL,), channel, R_REVIEWED_LABEL)


def parse_reviewed(doc: Mapping[str, Any], benchmark: str) -> dict[tuple[str, str], Mapping[str, ToolLabel]]:
    """The reviewed tables (C.14.8): per (benchmark, suite), the tools that every listed code state labels alike."""
    tables = doc.get("table")
    if not isinstance(tables, list) or not tables:
        raise ProfileDataError("reviewed_tables.toml: no [[table]]")
    out: dict[tuple[str, str], Mapping[str, ToolLabel]] = {}
    for i, table in enumerate(tables):
        where = f"table[{i}]"
        key = (table.get("benchmark"), table.get("suite")) if isinstance(table, dict) else (None, None)
        if not all(isinstance(k, str) and k for k in key):
            raise ProfileDataError(f"{where}: benchmark and suite must be non-empty strings")
        if key[0] == benchmark:  # an agentdojo suite reads suite_tools.toml and labels.toml, never a reviewed table
            raise ProfileDataError(f"{where}: a reviewed table names a benchmark other than {benchmark!r}")
        if key in out:
            raise ProfileDataError(f"{where}: a second table for {key}")
        states = table.get("code_state")
        if not isinstance(states, list) or not states:
            raise ProfileDataError(f"{where}: no [[table.code_state]]")
        ids = [s.get("id") if isinstance(s, dict) else None for s in states]
        if not all(isinstance(s, str) and s for s in ids) or len(set(ids)) != len(ids):
            raise ProfileDataError(f"{where}: code states need distinct ids")
        labels: list[dict[str, ToolLabel]] = []
        for state in states:
            tools = state.get("tools")
            if not isinstance(tools, dict) or not tools or not isinstance(state.get("commit"), str):
                raise ProfileDataError(f"{where}.{state['id']}: a code state names its commit and labels its tools")
            labels.append({tool: _reviewed_label(entry, f"{where}.{state['id']}.tools.{tool}")
                           for tool, entry in tools.items()})
        first, *rest = labels
        out[(str(key[0]), str(key[1]))] = MappingProxyType({
            tool: label for tool, label in sorted(first.items())
            if all(tool in other and other[tool].same_label(label) for other in rest)
        })
    return out


def parse_tables(files: Mapping[str, bytes], version: int = PROFILE_VERSION) -> Tables:
    """Parse and cross-check the profile's data files at ``version``."""
    expected = DATA_FILES_OF.get(version)
    if expected is None:
        raise ProfileDataError(f"this code builds {PROFILE_ID} at versions {list(PROFILE_VERSIONS)}, not {version}")
    if set(files) != set(expected):
        raise ProfileDataError(f"profile files must be exactly {list(expected)}; got {sorted(files)}")
    try:
        prof = tomllib.loads(files["profile.toml"].decode("utf-8"))
        labels = tomllib.loads(files["labels.toml"].decode("utf-8"))
        tools = tomllib.loads(files["suite_tools.toml"].decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ProfileDataError(f"profile data is not TOML: {exc}") from None
    head = prof.get("profile", {})
    if (head.get("id"), head.get("version"), head.get("rules")) != (PROFILE_ID, version, {"agentdojo": CATALOGUE_OF[version]}):
        raise ProfileDataError("profile.toml [profile] does not match the code")
    marker = prof["marker"]
    if (tuple(_str_list(marker["normalisers"], "marker.normalisers")) != markers.NORMALISERS_OF[2 if version >= 2 else 1]
            or marker["prefix_chars"] != markers.PREFIX_CHARS):
        raise ProfileDataError("profile.toml [marker] does not match the normaliser registry")
    unescape = {k: marker.get(k) for k in _UNESCAPE_MARKER if k in marker}
    if unescape != (_UNESCAPE_MARKER if version >= 2 else {}):
        raise ProfileDataError(f"profile.toml [marker]: the payload unescape is {_UNESCAPE_MARKER} at version 2 and "
                               "absent at version 1")
    taint = prof["taint"]
    if taint.get("rule") != R_TAINT:
        raise ProfileDataError("profile.toml [taint] names another rule")
    sink_roles: dict[str, tuple[str, ...]] = {}
    for tool, entry in labels["roles"]["sink"].items():
        roles = tuple(_str_list(entry.get("roles"), f"roles.sink.{tool}"))
        if not roles or any(r not in ("write_sink", "send_sink", "execute_sink") for r in roles):
            raise ProfileDataError(f"roles.sink.{tool}: a sink must hold sink roles only")
        sink_roles[tool] = roles
    fixture_integrity = dict(labels["integrity"]["fixtures"])
    if any(v not in INTEGRITY_VALUES for v in fixture_integrity.values()):
        raise ProfileDataError("integrity.fixtures: not an integrity value")
    outcomes, selection = prof["outcomes"], prof["selection"]
    if (selection.get("label_tables"), selection.get("unrecorded_label")) != ("versions", "intersection"):
        raise ProfileDataError("profile.toml [selection] names a rule this code does not implement")
    reviewed_keys = {k: selection.get(k) for k in _REVIEWED_SELECTION if k in selection}
    if reviewed_keys != (_REVIEWED_SELECTION if version >= 2 else {}):
        raise ProfileDataError(f"profile.toml [selection]: the reviewed tables are {_REVIEWED_SELECTION} at version 2 "
                               "and absent at version 1")
    reviewed: dict[tuple[str, str], Mapping[str, ToolLabel]] = {}
    if version >= 2:
        try:
            reviewed = parse_reviewed(tomllib.loads(files["reviewed_tables.toml"].decode("utf-8")),
                                      str(selection["benchmark"]))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise ProfileDataError(f"reviewed_tables.toml is not TOML: {exc}") from None
    return Tables(
        versions=MappingProxyType(_suite_tables(tools.get("versions"), "versions")),
        code_states=MappingProxyType(_suite_tables(tools.get("code_states"), "code_states")),
        benchmark=str(selection["benchmark"]),
        untrusted=frozenset(_str_list(labels["integrity"]["untrusted_tools"], "integrity.untrusted_tools")),
        sink_roles=MappingProxyType(sink_roles),
        endorsers=frozenset(_str_list(labels["roles"]["endorser_tools"], "roles.endorser_tools")),
        channels=MappingProxyType({str(k): str(v) for k, v in labels["channels"].items()}),
        trusted_authors=MappingProxyType({role: frozenset(_str_list(kinds, f"trusted_authors.{role}"))
                                          for role, kinds in labels["integrity"]["trusted_authors"].items()}),
        fixture_integrity=MappingProxyType(fixture_integrity),
        dos_attacks=frozenset(_str_list(outcomes["dos_attacks"], "outcomes.dos_attacks")),
        prepass_task_kind=str(outcomes["prepass_task_kind"]),
        prepass_claim=str(outcomes["prepass_claim"]),
        checker_origins=frozenset(_str_list(outcomes["checker_origins"], "outcomes.checker_origins")),
        fixture_kinds=frozenset(_str_list(marker["fixture_kinds"], "marker.fixture_kinds")),
        reviewed=MappingProxyType(reviewed),
        unescape_links=frozenset(_UNESCAPE_MARKER["payload_unescape_link"]) if version >= 2 else frozenset(),
    )


def _obj(value: Any) -> dict[str, Any]:
    """``value`` when it is a JSON object, else an empty one (records are untyped dicts at run time)."""
    return value if isinstance(value, dict) else {}


def _has(record: Mapping[str, Any], pointer: str) -> bool:
    node: Any = record
    for token in pointer.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isascii() and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            return False
    return True


@dataclass(slots=True)
class _Run:
    """Per-execution state of one ``annotate`` call."""

    aer: AerDocument
    known: frozenset[str]
    table_premises: tuple[Premise, ...]
    actor_kinds: dict[str, str] = field(default_factory=dict)
    #: the selection rule cited beside every tool label, and the reviewed labels when a reviewed table applies (C.14.8)
    table_rule: str = R_TABLE
    reviewed: Mapping[str, ToolLabel] | None = None
    #: the rule each cited rule resolves to for this log (version 2: a D rule or its twin, D-86; version 1: itself)
    cite: Callable[[str], str] = str


@dataclass(frozen=True, slots=True)
class SuitesProfile:
    """``agentdojo.suites`` at version 1 or 2 (satisfies :class:`agentprov.sem.types.SemanticsProfile`)."""

    id: str
    version: int
    sha256: str
    tables: Tables
    classes: Mapping[str, str]
    rules: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({"agentdojo": 1}))
    ns: Mapping[str, Json] = field(default_factory=lambda: MappingProxyType({}))
    taint_policy: TaintPolicy | None = None

    # ------------------------------------------------------------------------------------------ table selection
    def known_tools(self, aer: AerDocument) -> tuple[frozenset[str], tuple[Premise, ...]]:
        """The applicable suite tool table and the premises the selection read (``agentdojo.suite_tool_table@1``, or
        ``agentdojo.reviewed_suite_table@1`` for a reviewed table)."""
        known, premises, _reviewed = self._select(aer)
        return known, premises

    def _select(self, aer: AerDocument) -> tuple[frozenset[str], tuple[Premise, ...], Mapping[str, ToolLabel] | None]:
        """:meth:`known_tools` plus the reviewed labels when a reviewed table applies (``None`` otherwise)."""
        header = aer.header
        task = _obj(header.get("task"))
        premises = [Premise("exec", p) for p in ("/task/benchmark", "/task/suite") if _has(header, p)]
        bench = next((r for r in aer.of_kind("actor") if r.get("kind") == "benchmark"), None)
        label = bench.get("version") if bench is not None else None
        if isinstance(label, str):
            premises.append(Premise(str(_obj(bench).get("id")), "/version"))
            # D.6.12 item 5: a label the source profile reads as no suite version selects no versioned table; the
            # selection falls back to the unrecorded-label rule (the intersection), fail-closed
            meaning = _obj(_obj(_obj(bench).get("ext")).get("agentdojo")).get("version_label_semantics")
            if isinstance(meaning, str):
                premises.append(Premise(str(_obj(bench).get("id")), "/ext/agentdojo/version_label_semantics"))
                label = None
        suite = task.get("suite")
        t = self.tables
        benchmark = task.get("benchmark")
        reviewed = t.reviewed.get((benchmark, suite)) if isinstance(benchmark, str) and isinstance(suite, str) else None
        if reviewed is not None:  # C.14.8: a reviewed table covers unlabelled runs only; a recorded label selects none
            return (frozenset() if isinstance(label, str) else frozenset(reviewed)), tuple(premises), reviewed
        if task.get("benchmark") != t.benchmark or not isinstance(suite, str):
            return frozenset(), tuple(premises), None
        if isinstance(label, str):
            return t.versions.get(label, {}).get(suite, frozenset()), tuple(premises), None
        candidates = [tables[suite] for tables in (*t.versions.values(), *t.code_states.values()) if suite in tables]
        if not candidates:
            return frozenset(), tuple(premises), None
        return frozenset.intersection(*candidates), tuple(premises), None

    # ------------------------------------------------------------------------------------------ helpers
    def _ann(self, target: str, type_: str, value: Json, rules: tuple[str, ...], premises: tuple[Premise, ...],
             run: _Run, *, at: str | None = None, span: tuple[int, int] | None = None) -> Annotation:
        rules = tuple(run.cite(r) for r in rules)
        tags = [self.classes[r] for r in rules]
        for premise in premises:
            record = run.aer.get(premise.id)
            if record is not None:
                tags.append(effective_tag(record, premise.p))
        return Annotation(target=target, type=type_, value=value, ev=weakest(*tags),  # type: ignore[arg-type]
                          rule=rules, premises=premises, at=at, span=span)

    def _tool_of(self, run: _Run, message: Mapping[str, Any], part: Mapping[str, Any],
                 k: int) -> tuple[str | None, tuple[Premise, ...], bool]:
        """``(tool name, premises, redacted)`` of a tool result; ``None`` when no tool is linked."""
        aer = run.aer
        gen_id = message.get("generated_by")
        gen = aer.get(gen_id) if isinstance(gen_id, str) else None
        if gen is not None and gen.get("k") == "tool_execution" and isinstance(gen.get("name"), str):
            return gen["name"], (Premise(gen["id"], "/name"),), False
        if gen is not None and gen.get("k") == "decision":
            subject_id = gen.get("subject")
            subject = aer.get(subject_id) if isinstance(subject_id, str) else None
            if (gen.get("verdict") == "redact" and subject is not None and subject.get("k") == "tool_execution"
                    and isinstance(subject.get("name"), str)):
                return subject["name"], (Premise(subject["id"], "/name"), Premise(gen["id"], "/subject")), True
            # D-274 (regeneration-batch item 23): DRIFT's isolation pass forwards the execution's output, edited or not,
            # so the tool is the subject's, without R_REDACTED (the output may be unchanged)
            if (gen.get("verdict") == "other" and gen.get("subtype") == "drift.isolation_pass" and subject is not None
                    and subject.get("k") == "tool_execution" and isinstance(subject.get("name"), str)):
                return subject["name"], (Premise(subject["id"], "/name"), Premise(gen["id"], "/subject")), False
            return None, (Premise(gen["id"], "/verdict"),), False
        if gen is None and isinstance(part.get("responds_to"), str):
            base, _, ordinal = part["responds_to"].partition("#")
            call = aer.part(part["responds_to"])
            if call is not None and call.get("t") == "tool_call" and isinstance(call.get("name"), str):
                return call["name"], (Premise(base, f"/parts/{ordinal}/name"),), False
        return None, (Premise(str(message["id"]), f"/parts/{k}"),), False

    def _label(self, run: _Run, tool: str) -> ToolLabel:
        """The label of a tool known to the run's table (the reviewed one when a reviewed table applies)."""
        return run.reviewed[tool] if run.reviewed is not None else self.tables.label(tool)

    def _tool_role(self, run: _Run, target: str, tool: str | None, premises: tuple[Premise, ...]) -> Annotation:
        if tool is not None and tool in run.known:
            label = self._label(run, tool)
            return self._ann(target, "role", list(label.roles), (*label.role_rules, run.table_rule),
                             premises + run.table_premises, run)
        return self._ann(target, "role", ["unknown"], (R_UNKNOWN_TOOL, run.table_rule), premises + run.table_premises,
                         run)

    # ------------------------------------------------------------------------------------------ annotate
    def annotate(self, aer: AerDocument) -> Iterator[Annotation]:
        known, table_premises, reviewed = self._select(aer)
        run = _Run(aer, known, table_premises,
                   {str(a["id"]): str(a.get("kind")) for a in aer.of_kind("actor") if isinstance(a.get("id"), str)},
                   R_TABLE if reviewed is None else R_REVIEWED_TABLE, reviewed,
                   sem_citations(aer).cite if self.version >= 2 else str)
        fixtures = [f for f in aer.of_kind("fixture") if f.get("kind") in self.tables.fixture_kinds]
        for record in aer.records[1:]:
            kind = record.get("k")
            if kind == "fixture":
                yield self._fixture(run, record)
            elif kind == "message":
                yield from self._message(run, record, fixtures)
            elif kind == "tool_execution":
                name = record.get("name") if isinstance(record.get("name"), str) else None
                yield self._tool_role(run, str(record["id"]), name, (Premise(str(record["id"]), "/name"),))
            elif kind == "judgement":
                outcome = self._outcome(run, record)
                if outcome is not None:
                    yield outcome
                    hidden = self._hidden_success(run, record, outcome, fixtures) if self.version >= 2 else None
                    if hidden is not None:
                        yield hidden

    def _fixture(self, run: _Run, fixture: Mapping[str, Any]) -> Annotation:
        fid = str(fixture["id"])
        value = self.tables.fixture_integrity.get(str(fixture.get("kind")))
        if value is not None:
            return self._ann(fid, "integrity", value, (R_FIXTURE,), (Premise(fid, "/kind"),), run)
        return self._ann(fid, "integrity", "unknown", (R_UNKNOWN_AUTHOR,), (Premise(fid, "/kind"),), run)

    def _message(self, run: _Run, message: Mapping[str, Any], fixtures: list[dict[str, Any]]) -> Iterator[Annotation]:
        mid = str(message["id"])
        raw_parts = message.get("parts")
        parts: list[Any] = raw_parts if isinstance(raw_parts, list) else []
        role = message.get("role")
        actor = message.get("actor")
        author_kind = run.actor_kinds.get(actor) if isinstance(actor, str) else None
        author_premises = tuple(Premise(mid, p) for p in ("/role", "/actor") if p[1:] in message)
        trusted_kinds = self.tables.trusted_authors.get(role) if isinstance(role, str) else None
        for k, part in enumerate(parts):
            if not isinstance(part, dict):
                continue
            target = f"{mid}#{k}"
            t = part.get("t")
            if t == "tool_result" and role == "tool":
                yield from self._tool_result(run, message, part, k, fixtures)
                continue
            if trusted_kinds is not None and author_kind in trusted_kinds:
                rule = R_PRINCIPAL if role in _PRINCIPAL_ROLES else R_AGENT
                yield self._ann(target, "integrity", "trusted", (rule,), author_premises, run)
            else:
                yield self._ann(target, "integrity", "unknown", (R_UNKNOWN_AUTHOR,), author_premises, run)
            if t == "tool_result":  # a tool result outside a tool message: no producing tool to read
                yield from self._markers(run, mid, part, k, fixtures)
            if t == "tool_call":
                name = part.get("name") if isinstance(part.get("name"), str) else None
                yield self._tool_role(run, target, name, (Premise(mid, f"/parts/{k}/name"),))

    def _tool_result(self, run: _Run, message: Mapping[str, Any], part: Mapping[str, Any], k: int,
                     fixtures: list[dict[str, Any]]) -> Iterator[Annotation]:
        mid = str(message["id"])
        target = f"{mid}#{k}"
        tool, premises, redacted = self._tool_of(run, message, part, k)
        if tool is not None and tool in run.known:
            label = self._label(run, tool)
            rules = (label.integrity_rule, run.table_rule) + ((R_REDACTED,) if redacted else ())
            yield self._ann(target, "integrity", label.integrity, rules, premises + run.table_premises, run)
            if label.channel is not None:
                yield self._ann(target, "channel", label.channel, (label.channel_rule, run.table_rule),
                                premises + run.table_premises, run)
        else:
            yield self._ann(target, "integrity", "unknown", (R_UNKNOWN_TOOL, run.table_rule),
                            premises + run.table_premises, run)
        yield from self._markers(run, mid, part, k, fixtures)

    def _markers(self, run: _Run, mid: str, part: Mapping[str, Any], k: int,
                 fixtures: list[dict[str, Any]]) -> Iterator[Annotation]:
        if not fixtures:
            return
        target = f"{mid}#{k}"
        text = part.get("text")
        payloads = [f.get("content") if isinstance(f.get("content"), str) else None for f in fixtures]
        strict = self.version >= 2  # item 8: yaml_norm@2
        if isinstance(text, str):
            results = markers.marker_statuses(text, payloads, strict)
        else:
            results = [markers.MarkerResult("gap", markers.YAML_NORM_STRICT if strict else markers.YAML_NORM)
                       for _ in fixtures]
        # version 2 (B1): a payload AutoDojo escaped, by its established cache link, is also read with the escape undone
        linked = [isinstance(text, str) and payload is not None and result.status != "present"
                  and _obj(_obj(fixture.get("ext")).get("autodojo")).get("cache_match") in self.tables.unescape_links
                  for fixture, payload, result in zip(fixtures, payloads, results, strict=True)]
        unescaped = [markers.autodojo_unescape(p) if hit and p is not None else None for hit, p in zip(linked, payloads,
                                                                                                  strict=True)]
        if any(linked) and isinstance(text, str):
            second = markers.marker_statuses(text, unescaped, strict)
            results = [again if hit and again.status == "present" else first
                       for hit, first, again in zip(linked, results, second, strict=True)]
        else:
            linked = [False] * len(fixtures)
        text_premise = Premise(mid, f"/parts/{k}/text") if isinstance(text, str) else Premise(mid, f"/parts/{k}")
        for fixture, payload, result, hit, alt in zip(fixtures, payloads, results, linked, unescaped, strict=True):
            fid = str(fixture["id"])
            premises: tuple[Premise, ...] = (text_premise, Premise(fid, "/content" if payload is not None else ""))
            value: dict[str, Json] = {"fixture": fid, "status": result.status, "normaliser": result.normaliser}
            rules = (R_MARKER, R_MARKER_AMBIGUOUS) if result.status == "ambiguous" else (R_MARKER,)
            searched = payload
            if hit and result.status == "present":
                rules, searched = (R_MARKER, R_UNESCAPE), alt
                premises = (*premises, Premise(fid, "/ext/autodojo/cache_match"))
            at = "/text" if isinstance(text, str) else None
            span = markers.payload_span(text, searched) if result.status == "present" and isinstance(text, str) \
                and searched is not None else None
            yield self._ann(target, "injection_marker", value, rules, premises, run, at=at, span=span)
            if strict and result.status == "absent" and isinstance(text, str) and payload is not None:
                chars = markers.longest_payload_run(text, alt if hit and alt is not None else payload, strict)
                if chars is not None:  # item 6 (C3): a fragment of the payload, the marker stays absent
                    yield self._ann(target, T_PARTIAL, {"fixture": fid, "chars": chars}, (R_PARTIAL,),
                                    (text_premise, Premise(fid, "/content")), run)

    def _hidden_success(self, run: _Run, judgement: Mapping[str, Any], outcome: Annotation,
                        fixtures: list[dict[str, Any]]) -> Annotation | None:
        """Item 4 (C1): a held, targeted attack success whose payload no message part shows (no ``present`` or
        ``ambiguous`` reading, no partial run) gets ``agentdojo.success_without_visible_payload`` (assessment only;
        it generalises the banking ``user_task_15`` account confound). Fail-closed: no trajectory (an outcome-only log),
        a part whose text cannot be read (a tool result kept as a value, an unknown shape) or a payload that is not a
        string gives no flag."""
        value = outcome.value
        if not (isinstance(value, dict) and value.get("claim") == "attack_succeeded" and value.get("holds") is True):
            return None
        task = _obj(run.aer.header.get("task"))
        payloads = [f.get("content") for f in fixtures]
        if task.get("attack_id") in self.tables.dos_attacks or not payloads \
                or not all(isinstance(p, str) and p for p in payloads):
            return None
        if run.aer.header.get("unit") != "agent_execution" or not run.aer.of_kind("message"):
            return None  # no trajectory (an outcome-only log): "not visible" would be vacuous
        if self._payload_visible(run, fixtures, [str(p) for p in payloads]) is not False:
            return None
        jid = str(judgement["id"])
        premises = (Premise(jid, "/value"), Premise("exec", "/task/attack_id"),
                    *(Premise(str(f["id"]), "/content") for f in fixtures))
        return self._ann(jid, T_HIDDEN, {"fixtures": [str(f["id"]) for f in fixtures]}, (R_HIDDEN,), premises, run)

    def _payload_visible(self, run: _Run, fixtures: list[dict[str, Any]], payloads: list[str]) -> bool | None:
        """Whether some payload is visible in some message part: ``True``, ``False``, or ``None`` when a part cannot be
        read as text. The readings are the markers' (``yaml_norm@2`` and its fallbacks; for an AutoDojo-linked payload
        also with the escape undone) and item 6's partial run."""
        alts = [markers.autodojo_unescape(p) if _obj(_obj(f.get("ext")).get("autodojo")).get("cache_match")
                in self.tables.unescape_links else None for f, p in zip(fixtures, payloads, strict=True)]
        searched = [*payloads, *(a for a in alts if a is not None)]
        for message in run.aer.of_kind("message"):
            parts = message.get("parts")
            for part in parts if isinstance(parts, list) else ():
                if not isinstance(part, dict):
                    return None
                text = part.get("text")
                if part.get("t") in ("tool_call", "blob", "file", "uri") or (text is None and part.get("t") != "tool_result"
                                                                           and part.get("t") != "other"):
                    continue
                if not isinstance(text, str):
                    return None  # a tool result kept as a value or an unknown shape: unreadable here (fail-closed)
                if any(r.status in ("present", "ambiguous") for r in markers.marker_statuses(text, searched, True)):
                    return True
                if any(markers.longest_payload_run(text, p, True) is not None for p in searched):
                    return True
        return False

    def _outcome(self, run: _Run, judgement: Mapping[str, Any]) -> Annotation | None:
        t = self.tables
        jid, name, origin, value = str(judgement["id"]), judgement.get("name"), judgement.get("origin"), judgement.get("value")
        if not isinstance(value, bool) or origin == "harness_default":
            return None
        header = run.aer.header
        task = _obj(header.get("task"))
        ext = _obj(_obj(header.get("ext")).get("agentdojo"))
        if name == "utility" and origin in t.checker_origins:
            if ext.get("task_kind") == t.prepass_task_kind:
                return self._ann(jid, "outcome", {"claim": t.prepass_claim, "holds": value}, (R_UTILITY, R_PREPASS),
                                 (Premise(jid, "/value"), Premise("exec", "/ext/agentdojo/task_kind")), run)
            return self._ann(jid, "outcome", {"claim": "user_task_solved", "holds": value}, (R_UTILITY,),
                             (Premise(jid, "/value"),), run)
        if name != "security" or not isinstance(task.get("attack_id"), str):
            return None
        premises = (Premise(jid, "/value"), Premise(jid, "/origin"), Premise("exec", "/task/attack_id"))
        if task["attack_id"] in t.dos_attacks and origin in ("harness_rule", *t.checker_origins):
            return self._ann(jid, "outcome", {"claim": "attack_succeeded", "holds": value}, (R_POLARITY, R_DOS),
                             premises, run)
        if origin in t.checker_origins:
            return self._ann(jid, "outcome", {"claim": "attack_succeeded", "holds": value}, (R_POLARITY,), premises, run)
        return None


@cache
def _source_facts(profile_id: str, sha256: str, version: int | None = None) -> tuple[tuple[VerifiedCode, ...], HistoryTable | None]:
    """The ``verified_code`` and the AgentDojo history table of the packaged source profile ``profile_id`` at the header's
    ``version`` (an archived one too, D-31) when its digest is ``sha256``, else none."""
    try:
        profile = load_profile(profile_id, version)
    except ProfileError:
        return (), None
    if profile.sha256 != sha256:
        return (), None
    if profile.family == "agentdojo":
        fam = family_table(profile)
        return fam.verified_code, fam.history
    table = profile.family_table()  # read-only mappings, not dicts
    entries = table.get("verified_code", ()) if profile.family == "adprov" else ()
    return parse_verified_code(entries, f"profile {profile_id!r}"), None


def sem_citations(aer: AerDocument) -> Citations:
    """D-86: the citation policy of the mappers (D.5.4), for the SEM rules this profile cites. The verified commits are the
    ``verified_code`` of the source profile the AER header names, read only when the packaged profile has the header's
    digest (otherwise none: every D rule is cited through its twin, fail-closed). The facets are those the AER records:
    the dialect ``variant``, for adprov transcripts ``transcript`` (``released`` or ``converted``), and
    ``introduced_under`` from the primary artefact's git origin and the profile's history table (D-84); a
    ``verified_code`` entry selecting any other facet does not apply (fail-closed)."""
    header = aer.header
    profile = _obj(header.get("profile"))
    pid, sha, version = profile.get("id"), profile.get("sha256"), profile.get("version")
    version = version if isinstance(version, int) and not isinstance(version, bool) else None
    verified, history = _source_facts(pid, sha, version) if isinstance(pid, str) and isinstance(sha, str) else ((), None)
    artefacts = header.get("artifacts")
    primary = artefacts[0] if isinstance(artefacts, list) and artefacts and isinstance(artefacts[0], dict) else {}
    variant = _obj(header.get("dialect")).get("variant")
    transcript = _obj(_obj(_obj(header.get("ext")).get("adprov")).get("v1")).get("variant")
    facets = {"variant": variant if isinstance(variant, str) else None,
              "transcript": transcript if isinstance(transcript, str) else None,
              "introduced_under": origin_introduced_under(history, _obj(primary.get("origin")))}
    return Citations(verified, facets, namespaces=NAMESPACES, independent=INDEPENDENT)


def build(profile_id: str, version: int, files: Mapping[str, bytes], sha256: str) -> SuitesProfile:
    """Build ``agentdojo.suites`` at version 1 or 2 from its data files (called by
    :func:`agentprov.adapters.semantics_profiles.load_semantics_profile`)."""
    if profile_id != PROFILE_ID or version not in PROFILE_VERSIONS:
        raise ProfileDataError(f"this code builds {PROFILE_ID} at versions {list(PROFILE_VERSIONS)}, "
                               f"not {profile_id}@{version}")
    tables = parse_tables(files, version)
    declared = CATALOGUE_OF[version]  # D-31: version 1 is archived; suites@1 reads it, @2/@3 read 2
    catalogue = load_catalogue("agentdojo", declared)
    classes: dict[str, str] = {}
    for ref in CITED_RULES_OF[version]:
        entry = catalogue.get(ref)
        if entry is None or not entry.citable:
            raise ProfileDataError(f"{ref} is not an active rule of the agentdojo catalogue v{declared}")
        classes[ref] = entry.cls
    prof = tomllib.loads(files["profile.toml"].decode("utf-8"))["taint"]
    policy = TaintPolicy(rule=R_TAINT, subject_roles=frozenset(_str_list(prof["subject_roles"], "taint.subject_roles")),
                         object_integrity=frozenset(_str_list(prof["object_integrity"], "taint.object_integrity")))
    if not policy.subject_roles <= set(ROLE_VALUES) or not policy.object_integrity <= set(INTEGRITY_VALUES):
        raise ProfileDataError("profile.toml [taint] holds a value outside the SEM vocabularies")
    return SuitesProfile(id=profile_id, version=version, sha256=sha256, tables=tables,
                         classes=MappingProxyType(classes), rules=MappingProxyType({"agentdojo": declared}),
                         taint_policy=policy, ns=NS_V2 if version >= 2 else MappingProxyType({}))
