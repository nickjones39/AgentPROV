"""The v2.3 -> ``agentprov-prov/0.1`` semantic diff: the map, the edge classifier and the report of gate E (J.3.6; R-33).

**The map.** ``src/agentprov/prov/compat/semdiff-map.toml`` (owner EF) is the one machine-readable semantic diff: one row
per v2.3 element with its frozen counts, J's closed disposition, the EF catalogue rule ids of its counterpart, the bundles
and evidence classes those statements carry on the two v2.3 trees, and a matcher that tells gate E how to count it.
:func:`load_map` reads it from package resources and checks a closed schema (:func:`parse_map`).

**The classifier.** :func:`classify_execution` recomputes which v2.3 builder rule produced every edge of one compat graph,
with the predicates of the frozen port (``build_prov``; audit/provenance.md §4.1) evaluated on the transcript/v1 view of
the AER: R1 ``wasGeneratedBy`` and R2 ``wasAssociatedWith`` per tool activity, R3 first-turn query use, R4 previous-turn
exchange, R5 communication, R6 sink taint (deduplicated against R4 exactly as the builder does), and the gated R7/R8. It
reuses the port's own helpers (``unique_loc``, the labelling tables) and walks the pass/batch stream itself, so a change
in either side shows as an edge that is unclassified or missing. An edge produced by two rules (R4 and R6) is classified
once, with both reasons. Nodes and attributes are classified by node class and attribute name; anything the map does not
cover is ``unmapped``.

**The report.** :func:`build_report` joins the per-execution counts of one tree with the map into a
:class:`SemDiffReport` (``agentprov-semdiff/0.1``): ``rows[]``, ``unmapped``, ``overlaps``, the Inference-6 reading of the
taint edges, the AER measures behind the ``new`` rows, the counterpart statements of the derivation, spec versions and
digests. It holds no time, commit or path of the machine, so two runs give the same bytes (J.3.6 acceptance). Labels are
ids and counts only, never transcript text (MP-6).

Nothing here imports a benchmark package. The compat port is imported lazily (quarantine, MN M.5.2(3)).
"""

from __future__ import annotations

import json
import re
import tomllib
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any, Final

from agentprov.errors import AgentProvError
from agentprov.io.canonical import sha256_hex

MAP_FORMAT: Final = "agentprov-semdiff-map/0.1"
REPORT_FORMAT: Final = "agentprov-semdiff/0.1"
SEMDIFF_ID: Final = "adprov-v2.3-compat→agentprov-prov/0.1"
MAP_PACKAGE: Final = "agentprov.prov.compat"
MAP_RESOURCE: Final = "semdiff-map.toml"
MAP_RELPATH: Final = "src/agentprov/prov/compat/semdiff-map.toml"

#: J.3.6: the closed disposition vocabulary, normative for the map.
DISPOSITIONS: Final = ("kept", "reclassified", "moved", "replaced", "moved-to-assessment", "dropped", "new")
BUNDLES: Final = ("core", "inference", "assessment", "none")
EVIDENCE_CLASSES: Final = ("O", "D", "I")
SECTIONS: Final = ("relation", "node", "attribute")
TREES: Final = ("release", "converted")
#: The count keys of the map's frozen tables, per tree (J's column names: released / converted).
COUNT_KEYS: Final[Mapping[str, str]] = {"release": "released", "converted": "converted"}
#: The builder's rules (audit/provenance.md §4.1), plus ``ACT`` for the never-emitted ``actedOnBehalfOf``.
V23_RULES: Final = ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "ACT")
NODE_CLASSES: Final = ("ag_llm", "e_user_query", "a_k", "e_k", "ag_src")
RELATION_ENDPOINTS: Final[Mapping[str, tuple[str, str]]] = {
    "wasGeneratedBy": ("prov:entity", "prov:activity"),
    "used": ("prov:activity", "prov:entity"),
    "wasAssociatedWith": ("prov:activity", "prov:agent"),
    "wasInformedBy": ("prov:informed", "prov:informant"),
    "wasDerivedFrom": ("prov:generatedEntity", "prov:usedEntity"),
    "wasAttributedTo": ("prov:entity", "prov:agent"),
    "actedOnBehalfOf": ("prov:delegate", "prov:responsible"),
}
NODE_SECTIONS: Final = ("entity", "activity", "agent")
#: AER measures a ``new`` row may count (per execution, summed per tree); ``statements`` counts derived statements.
AER_MEASURES: Final = (
    "executions", "model_invocations", "assistant_messages", "system_messages", "later_user_messages", "requests",
    "unexecuted_requests", "fixtures", "judgements", "scopes", "other_actors",
)
STATEMENTS: Final = "statements"
#: ``frozen_extra`` measures besides ``value:<v>``.
EXTRA_MEASURES: Final = ("taint_pairs", "overlaps", "entailed_not_asserted")
#: Attributes whose values are counted (for ``value:<v>`` extras): labels and flags only, never content.
VALUE_ATTRIBUTES: Final = frozenset({"adprov:role", "adprov:integrity", "adprov:contains_injection_marker"})
RECOMPUTE: Final = ("phase 13",)

_RULE_REF = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+@[1-9][0-9]*$")
_ROW_REQUIRED: Final = frozenset(
    {"id", "section", "v23_element", "disposition", "targets", "bundle", "evidence_class", "counterpart"}
)
_ROW_OPTIONAL: Final = frozenset(
    {
        "rule", "node", "attribute", "on", "measure", "frozen", "frozen_extra", "frozen_source", "frozen_note",
        "recompute", "assumptions", "mentions", "content_status", "note", "ef", "j",
    }
)
_MATCHERS: Final = ("rule", "node", "attribute", "measure")
_MAP_KEYS: Final = frozenset({"format", "version", "from", "to", "catalogue", "trees"})


class SemDiffMapError(AgentProvError):
    """The semantic-diff map is malformed (broken package data, exit 70)."""

    code = "migration.semdiff.map_invalid"
    exit_code = 70


# ================================================================================================ the map


@dataclass(frozen=True, slots=True)
class MapRow:
    """One row of ``semdiff-map.toml``; see the file's header for the meaning of every key."""

    id: str
    section: str
    v23_element: str
    disposition: str
    targets: tuple[str, ...]
    bundle: tuple[str, ...]
    evidence_class: tuple[str, ...]
    counterpart: str
    rule: str | None = None
    node: str | None = None
    attribute: str | None = None
    on: tuple[str, ...] | None = None
    measure: str | None = None
    frozen: Mapping[str, int] = field(default_factory=dict)
    frozen_extra: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    frozen_source: str | None = None
    frozen_note: str | None = None
    recompute: str | None = None
    assumptions: tuple[str, ...] = ()
    mentions: tuple[str, ...] = ()
    content_status: str | None = None
    note: str | None = None
    ef: str | None = None
    j: str | None = None

    @property
    def rule_ids(self) -> tuple[str, ...]:
        """Every rule id the row names: targets, assumptions and mentions."""
        return (*self.targets, *self.assumptions, *self.mentions)


@dataclass(frozen=True, slots=True)
class SemDiffMap:
    format: str
    version: int
    source: str
    to: str
    catalogue: str
    trees: tuple[str, ...]
    rows: tuple[MapRow, ...]
    sha256: str

    def by_rule(self, rule: str) -> MapRow | None:
        return next((r for r in self.rows if r.rule == rule), None)

    def by_node(self, node: str) -> MapRow | None:
        return next((r for r in self.rows if r.node == node), None)

    def by_attribute(self, attribute: str, on: str) -> MapRow | None:
        for row in self.rows:
            if row.attribute == attribute and (row.on is None or on in row.on):
                return row
        return None

    def targets(self) -> set[str]:
        return {t for r in self.rows for t in r.targets}

    def allowed(self) -> dict[str, set[tuple[str, str]]]:
        """``rule id -> {(bundle, class)}`` over every row that targets the rule (the derivation cross-check)."""
        out: dict[str, set[tuple[str, str]]] = {}
        for row in self.rows:
            for target in row.targets:
                out.setdefault(target, set()).update((b, c) for b in row.bundle for c in row.evidence_class)
        return out


def _fail(source: str, message: str) -> SemDiffMapError:
    return SemDiffMapError(f"{source}: {message}")


def _str_list(row: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = row.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise _fail(where, f"{key} must be a list of strings")
    if len(set(value)) != len(value):
        raise _fail(where, f"{key} has duplicates")
    return tuple(value)


def _counts(value: Any, where: str) -> dict[str, int]:
    if not isinstance(value, dict) or not set(value) <= set(COUNT_KEYS.values()):
        raise _fail(where, "a count table has only the keys released and converted")
    for tree, n in value.items():
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise _fail(where, f"count {tree} must be a non-negative integer")
    return dict(value)


def _row(raw: Any, index: int, source: str) -> MapRow:
    where = f"{source} row {index}"
    if not isinstance(raw, dict):
        raise _fail(where, "not a table")
    keys = set(raw)
    if missing := _ROW_REQUIRED - keys:
        raise _fail(where, f"missing keys {sorted(missing)}")
    if unknown := keys - _ROW_REQUIRED - _ROW_OPTIONAL:
        raise _fail(where, f"unknown keys {sorted(unknown)} (the schema is closed)")
    for key in ("id", "section", "v23_element", "disposition", "counterpart", "frozen_source", "frozen_note",
                "recompute", "content_status", "note", "ef", "j", "rule", "node", "attribute", "measure"):
        if key in raw and (not isinstance(raw[key], str) or not raw[key]):
            raise _fail(where, f"{key} must be a non-empty string")
    where = f"{source} row {raw['id']!r}"
    if raw["section"] not in SECTIONS:
        raise _fail(where, f"section must be one of {SECTIONS}")
    if raw["disposition"] not in DISPOSITIONS:
        raise _fail(where, f"disposition {raw['disposition']!r} is not in J's closed vocabulary {DISPOSITIONS}")
    matchers = [m for m in _MATCHERS if m in raw]
    if len(matchers) != 1:
        raise _fail(where, f"exactly one matcher of {_MATCHERS} is required, found {matchers}")
    if "on" in raw and "attribute" not in raw:
        raise _fail(where, "on is allowed only with attribute")
    if "rule" in raw and raw["rule"] not in V23_RULES:
        raise _fail(where, f"rule must be one of {V23_RULES}")
    if "node" in raw and raw["node"] not in NODE_CLASSES:
        raise _fail(where, f"node must be one of {NODE_CLASSES}")
    if "measure" in raw and raw["measure"] not in (*AER_MEASURES, STATEMENTS):
        raise _fail(where, f"measure must be one of {(*AER_MEASURES, STATEMENTS)}")
    on = _str_list(raw, "on", where) if "on" in raw else None
    if on is not None and (not on or not set(on) <= set(NODE_CLASSES) | set(RELATION_ENDPOINTS)):
        raise _fail(where, "on lists node classes or relation types")
    targets = _str_list(raw, "targets", where)
    assumptions = _str_list(raw, "assumptions", where)
    mentions = _str_list(raw, "mentions", where)
    for ref in (*targets, *assumptions, *mentions):
        if not _RULE_REF.fullmatch(ref):
            raise _fail(where, f"{ref!r} is not a rule id of the form <ns>.<name>@<n>")
    if any(not t.startswith("aprov.") for t in targets):
        raise _fail(where, "targets are engine catalogue (aprov) rule ids; adapter rules go in assumptions")
    bundle = _str_list(raw, "bundle", where)
    classes = _str_list(raw, "evidence_class", where)
    if not bundle or not set(bundle) <= set(BUNDLES) or ("none" in bundle and len(bundle) > 1):
        raise _fail(where, f"bundle lists {BUNDLES[:3]}, or is exactly ['none']")
    if not set(classes) <= set(EVIDENCE_CLASSES):
        raise _fail(where, f"evidence_class lists {EVIDENCE_CLASSES}")
    if (bundle == ("none",)) != (not classes) or (bundle == ("none",)) != (not targets):
        raise _fail(where, "a row has targets and classes exactly when its bundle is not ['none']")
    if raw["disposition"] == "dropped" and bundle != ("none",):
        raise _fail(where, "a dropped element has no counterpart (bundle ['none'], no targets)")
    if "recompute" in raw and raw["recompute"] not in RECOMPUTE:
        raise _fail(where, f"recompute must be one of {RECOMPUTE}")
    frozen = _counts(raw.get("frozen", {}), where)
    extra_raw = raw.get("frozen_extra", {})
    if not isinstance(extra_raw, dict):
        raise _fail(where, "frozen_extra must be a table")
    extra: dict[str, dict[str, int]] = {}
    for name, value in extra_raw.items():
        if name not in EXTRA_MEASURES and not name.startswith("value:"):
            raise _fail(where, f"frozen_extra {name!r} is not one of {EXTRA_MEASURES} or value:<v>")
        extra[name] = _counts(value, where)
    if (frozen or extra) and "frozen_source" not in raw:
        raise _fail(where, "frozen counts need frozen_source")
    return MapRow(
        id=raw["id"], section=raw["section"], v23_element=raw["v23_element"], disposition=raw["disposition"],
        targets=targets, bundle=bundle, evidence_class=classes, counterpart=raw["counterpart"],
        rule=raw.get("rule"), node=raw.get("node"), attribute=raw.get("attribute"), on=on, measure=raw.get("measure"),
        frozen=frozen, frozen_extra=extra, frozen_source=raw.get("frozen_source"), frozen_note=raw.get("frozen_note"),
        recompute=raw.get("recompute"), assumptions=assumptions, mentions=mentions,
        content_status=raw.get("content_status"), note=raw.get("note"), ef=raw.get("ef"), j=raw.get("j"),
    )


def parse_map(data: bytes, *, source: str = MAP_RELPATH) -> SemDiffMap:
    """Parse and check ``semdiff-map.toml`` (closed schema; complete over the builder's rules and node classes)."""
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise _fail(source, f"not UTF-8 TOML ({type(exc).__name__})") from None
    if set(document) != {"map", "row"}:
        raise _fail(source, "the top level has exactly the tables [map] and [[row]]")
    header = document["map"]
    if not isinstance(header, dict) or set(header) != _MAP_KEYS:
        raise _fail(source, f"[map] has exactly the keys {sorted(_MAP_KEYS)}")
    if header["format"] != MAP_FORMAT:
        raise _fail(source, f"format must be {MAP_FORMAT!r}")
    if not isinstance(header["version"], int) or isinstance(header["version"], bool) or header["version"] < 1:
        raise _fail(source, "version must be a positive integer")
    if header["from"] != "adprov-v2.3-compat" or header["to"] != "agentprov-prov/0.1":
        raise _fail(source, "the map is from adprov-v2.3-compat to agentprov-prov/0.1")
    if list(header["trees"]) != list(TREES):
        raise _fail(source, f"trees must be {list(TREES)}")
    if not isinstance(document["row"], list) or not document["row"]:
        raise _fail(source, "no rows")
    rows = tuple(_row(raw, i, source) for i, raw in enumerate(document["row"]))
    ids = [r.id for r in rows]
    if len(set(ids)) != len(ids):
        raise _fail(source, "row ids are not unique")
    for key in ("rule", "node"):
        values = [getattr(r, key) for r in rows if getattr(r, key) is not None]
        if len(set(values)) != len(values):
            raise _fail(source, f"two rows match the same {key}")
    measures = [r.measure for r in rows if r.measure not in (None, STATEMENTS)]
    if len(set(measures)) != len(measures):
        raise _fail(source, "two rows count the same AER measure")
    attributes: dict[str, list[tuple[str, ...] | None]] = {}
    for row in rows:
        if row.attribute is None:
            continue
        for other in attributes.get(row.attribute, []):
            if other is None or row.on is None or set(other) & set(row.on):
                raise _fail(source, f"two rows match the attribute {row.attribute} on the same element")
        attributes.setdefault(row.attribute, []).append(row.on)
    if missing := set(V23_RULES) - {r.rule for r in rows}:
        raise _fail(source, f"no row for the builder rules {sorted(missing)}")
    if missing := set(NODE_CLASSES) - {r.node for r in rows}:
        raise _fail(source, f"no row for the node classes {sorted(missing)}")
    return SemDiffMap(
        format=header["format"], version=header["version"], source=header["from"], to=header["to"],
        catalogue=header["catalogue"], trees=tuple(header["trees"]), rows=rows, sha256=sha256_hex(data),
    )


def map_bytes() -> bytes:
    """The packaged map's bytes (package data, never a corpus copy)."""
    return resources.files(MAP_PACKAGE).joinpath(MAP_RESOURCE).read_bytes()


@cache
def load_map() -> SemDiffMap:
    return parse_map(map_bytes())


# ================================================================================================ the classifier

EdgeKey = tuple[str, str, str]  # (relation type, first endpoint, second endpoint) as the endpoints table orders them


@dataclass(slots=True)
class Prediction:
    """The edges and nodes the builder's predicates give for one view (default flags), plus the gated candidates."""

    edges: dict[EdgeKey, set[str]] = field(default_factory=dict)
    r7: set[EdgeKey] = field(default_factory=set)
    r8: set[EdgeKey] = field(default_factory=set)
    activities: set[str] = field(default_factory=set)
    outputs: set[str] = field(default_factory=set)
    source_agents: set[str] = field(default_factory=set)
    taint_pairs: int = 0

    def add(self, key: EdgeKey, reason: str) -> None:
        self.edges.setdefault(key, set()).add(reason)


def predict(view: Mapping[str, Any]) -> Prediction:
    """Recompute the builder's emission conditions (``build_prov``, default flags) over a transcript/v1 view.

    The walk follows the port step for step: every pass oldest first, the user query, the batch boundaries at assistant
    turns, ``seen``/``pending`` untrusted outputs, and the R4 de-duplication of R6. Node ids come from the port's
    ``unique_loc``; roles and integrity from its labelling tables.
    """
    from agentprov.prov.compat.adprov_v2_3.build_prov import _CHANNEL_OF, RESERVED_LOCS, unique_loc  # noqa: PLC0415
    from agentprov.prov.compat.adprov_v2_3.labeling import (  # noqa: PLC0415
        Label,
        NodeRole,
        classify_activity,
        entity_integrity,
    )

    out = Prediction()
    meta_turns = view.get("turns", []) or []
    passes = [a.get("turns") or [] for a in view.get("discarded_attempts") or []] + [meta_turns]
    stream = [(k, t) for k, pass_turns in enumerate(passes, start=1) for t in pass_turns]
    llm, query = "adprov:ag_llm", "adprov:e_user_query"
    seen_untrusted: list[str] = []
    pending_untrusted: list[str] = []
    prev_batch: list[str] = []
    cur_batch: list[str] = []
    prev_outputs: list[str] = []
    cur_outputs: list[str] = []
    seen_locs: set[str] = set(RESERVED_LOCS)
    step = 0
    attempt = 0
    for pass_no, turn in stream:
        if pass_no != attempt:
            attempt = pass_no
            seen_untrusted, pending_untrusted = [], []
            prev_batch, cur_batch = [], []
            prev_outputs, cur_outputs = [], []
        if turn.get("role") == "assistant":
            seen_untrusted.extend(pending_untrusted)
            pending_untrusted = []
            if cur_batch:
                prev_batch, cur_batch = cur_batch, []
                prev_outputs, cur_outputs = cur_outputs, []
            continue
        if turn.get("role") != "tool":
            continue
        step += 1
        loc = unique_loc(turn.get("tool_call_id") or f"tc_step{step}", seen_locs, step)
        seen_locs.add(loc)
        fn = turn.get("function") or "unknown_tool"
        activity, output = f"adprov:a_{loc}", f"adprov:e_{loc}"
        out.activities.add(activity)
        out.outputs.add(output)
        out.add(("wasGeneratedBy", output, activity), "R1")
        used_here: set[str] = set()
        if prev_batch:
            for informant, informant_output in zip(prev_batch, prev_outputs, strict=True):
                out.add(("wasInformedBy", activity, informant), "R5")
                out.add(("used", activity, informant_output), "R4")
                used_here.add(informant_output)
        else:
            out.add(("used", activity, query), "R3")
        if classify_activity(fn) == NodeRole.SINK:
            for prior in seen_untrusted:
                out.taint_pairs += 1
                out.add(("used", activity, prior), "R6")  # on an R4 edge this adds the second reason (one edge)
                out.r7.add(("wasDerivedFrom", output, prior))
        out.add(("wasAssociatedWith", activity, llm), "R2")
        if entity_integrity(fn) == Label.UNTRUSTED:
            pending_untrusted.append(output)
            agent = f"adprov:ag_src_{_CHANNEL_OF.get(fn) or 'external'}"
            out.r8.add(("wasAttributedTo", output, agent))
            out.source_agents.add(agent)
        cur_batch.append(activity)
        cur_outputs.append(output)
    return out


_RULE_ORDER = {r: i for i, r in enumerate(V23_RULES)}


def reason_label(reasons: Iterable[str]) -> str:
    """``"R4+R6"``: the reasons of one classified edge, in rule order."""
    return "+".join(sorted(reasons, key=_RULE_ORDER.__getitem__))


@dataclass(slots=True)
class ExecutionDiff:
    """What gate E measures on one execution. Counts, ids and codes only."""

    item: str
    tree: str
    reasons: Counter[str] = field(default_factory=Counter)  # "<relation>:<reason label>" -> classified edges
    rules: Counter[str] = field(default_factory=Counter)  # R1..R8, ACT: the row counts (R4 includes R4+R6)
    overlaps: int = 0
    taint_pairs: int = 0
    edges: int = 0
    unclassified: int = 0
    missing_edges: int = 0
    nodes: Counter[str] = field(default_factory=Counter)
    missing_nodes: int = 0
    attributes: Counter[tuple[str, str]] = field(default_factory=Counter)
    values: Counter[tuple[str, str]] = field(default_factory=Counter)
    unmapped: Counter[str] = field(default_factory=Counter)
    inference6: Counter[str] = field(default_factory=Counter)
    aer: Counter[str] = field(default_factory=Counter)
    unexecuted_listed: int = 0
    redact_overwritten: int = 0
    derivation: Counter[tuple[str, str, str]] = field(default_factory=Counter)  # (rule, bundle, class) -> statements
    derived_overwritten: int = 0
    derived_taints: int = 0  # aprov.a_taint@1 assessments of the agentdojo.suites@1 derivation
    b1: bool | None = None
    codes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.codes


def _value_label(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def classify_graph(diff: ExecutionDiff, view: Mapping[str, Any], graph: Mapping[str, Any], semdiff_map: SemDiffMap) -> None:
    """Classify every edge, node and attribute of one compat graph against the prediction for its view."""
    pred = predict(view)
    diff.taint_pairs = pred.taint_pairs
    for top in graph:
        if top != "prefix" and top not in NODE_SECTIONS and top not in RELATION_ENDPOINTS:
            diff.unmapped[f"section:{top}"] += 1
    # ------------------------------------------------------------------ edges
    observed: Counter[EdgeKey] = Counter()
    for relation, (first, second) in RELATION_ENDPOINTS.items():
        section = graph.get(relation) or {}
        for body in section.values() if isinstance(section, dict) else ():
            if not isinstance(body, dict) or not isinstance(body.get(first), str) or not isinstance(body.get(second), str):
                diff.unmapped[f"relation:{relation}:malformed"] += 1
                continue
            observed[(relation, body[first], body[second])] += 1
            for attr in body:
                if attr in (first, second):
                    continue
                if semdiff_map.by_attribute(attr, relation) is None:
                    diff.unmapped[f"attribute:{attr}@{relation}"] += 1
                else:
                    diff.attributes[(attr, relation)] += 1
    expected: Counter[EdgeKey] = Counter(pred.edges.keys())
    reasons: dict[EdgeKey, set[str]] = {k: set(v) for k, v in pred.edges.items()}
    for key in observed:  # the gated rules: an observed edge is classified iff its predicate holds
        if key in pred.r7:
            expected[key] = 1
            reasons[key] = {"R7"}
        elif key in pred.r8:
            expected[key] = 1
            reasons[key] = {"R8"}
    diff.edges = sum(observed.values())
    for key, n in observed.items():
        matched = min(n, expected.get(key, 0))
        diff.unclassified += n - matched
        if matched:
            label = reason_label(reasons[key])
            diff.reasons[f"{key[0]}:{label}"] += matched
            if label == "R4+R6":
                diff.overlaps += matched
            for rule in reasons[key]:
                if rule == "R6" and "R4" in reasons[key]:
                    continue  # the R6 row counts the taint-only part (J.1.3: used = R3 + R4 + R6-only)
                diff.rules[rule] += matched
    diff.missing_edges = sum(max(0, n - observed.get(key, 0)) for key, n in expected.items())
    if diff.unclassified:  # e.g. an actedOnBehalfOf edge: no predicate of the builder produces one
        diff.unmapped["edge:unclassified"] += diff.unclassified
    # ------------------------------------------------------------------ Inference 6 over the compat graph
    generated = {e: a for (rel, e, a) in observed if rel == "wasGeneratedBy"}
    entailed = {(a, generated[e]) for (rel, a, e) in observed if rel == "used" and e in generated}
    asserted = {(a, b) for (rel, a, b) in observed if rel == "wasInformedBy"}
    diff.inference6.update(
        entailed=len(entailed), asserted=len(asserted), entailed_not_asserted=len(entailed - asserted),
        asserted_not_entailed=len(asserted - entailed),
    )
    # ------------------------------------------------------------------ nodes and their attributes
    present: dict[str, set[str]] = {s: set() for s in NODE_SECTIONS}
    for section in NODE_SECTIONS:
        nodes = graph.get(section) or {}
        for ident, body in nodes.items() if isinstance(nodes, dict) else ():
            present[section].add(ident)
            cls: str | None = None
            if section == "entity":
                cls = "e_user_query" if ident == "adprov:e_user_query" else "e_k" if ident in pred.outputs else None
            elif section == "activity":
                cls = "a_k" if ident in pred.activities else None
            elif ident == "adprov:ag_llm":
                cls = "ag_llm"
            elif ident in pred.source_agents:
                cls = "ag_src"
            if cls is None:
                diff.unmapped[f"node:{section}"] += 1
                continue
            diff.nodes[cls] += 1
            for attr, value in (body.items() if isinstance(body, dict) else ()):
                if semdiff_map.by_attribute(attr, cls) is None:
                    diff.unmapped[f"attribute:{attr}@{cls}"] += 1
                    continue
                diff.attributes[(attr, cls)] += 1
                if attr in VALUE_ATTRIBUTES and isinstance(value, (str, bool, int)):
                    diff.values[(attr, _value_label(value))] += 1
    wanted = {
        "entity": {"adprov:e_user_query", *pred.outputs},
        "activity": pred.activities,
        "agent": {"adprov:ag_llm"},
    }
    diff.missing_nodes = sum(len(wanted[s] - present[s]) for s in NODE_SECTIONS)


def aer_measures(diff: ExecutionDiff, doc: Any) -> None:
    """The AER counts behind the ``new`` rows and the unexecuted-request and Overwritten cross-checks (J.3.5, R-08)."""
    messages = doc.of_kind("message")
    roles = Counter(str(m.get("role")) for m in messages)
    calls = {
        f"{m['id']}#{k}"
        for m in messages
        for k, p in enumerate(m.get("parts") or [])
        if isinstance(p, dict) and p.get("t") == "tool_call"
    }
    executed = {r["call"] for r in doc.of_kind("tool_execution") if "call" in r}
    issues = doc.seal.get("issues") or []
    listed = {i for issue in issues if issue.get("code") == "unexecuted_tool_call" for i in issue.get("ids", [])}
    diff.aer.update(
        executions=1,
        model_invocations=sum(1 for m in messages if m.get("role") == "assistant" and "generated_by" in m),
        assistant_messages=roles["assistant"],
        system_messages=roles["system"],
        later_user_messages=max(0, roles["user"] - 1),
        requests=len(calls),
        unexecuted_requests=len(calls - executed),
        fixtures=len(doc.of_kind("fixture")),
        judgements=len(doc.of_kind("judgement")),
        scopes=sum(1 for s in doc.of_kind("scope") if s.get("kind") != "thread"),
        other_actors=sum(1 for a in doc.of_kind("actor") if a.get("kind") != "llm_agent"),
    )
    diff.unexecuted_listed = len(listed)
    if listed != calls - executed:
        diff.codes.append("unexecuted.listed_mismatch")
    diff.redact_overwritten = sum(
        1
        for d in doc.of_kind("decision")
        if d.get("verdict") == "redact" and (d.get("unk") or {}).get("/original") == "overwritten"
    )


def _bundle_kind(raw: str) -> str:
    if raw == "inf":
        return "inference"
    if raw.startswith("assess"):
        return "assessment"
    return raw


#: The semantics profile gate E derives with (J.3.5: ``semantics(AER, agentdojo.suites@1)``).
SEMANTICS_PROFILE: Final = ("agentdojo.suites", 1)


def derivation_measures(diff: ExecutionDiff, doc: Any) -> None:
    """Annotate with ``agentdojo.suites@1``, derive ``agentprov-prov/0.1`` once with the SEM (core, inference and
    assessment bundles) and count its statements by (rule, bundle, class), the Overwritten pre-decision entities (the
    R-08 counterpart of ``adprov:defence_omitted``) and the taint assessments (the counterpart of the R6 pairs)."""
    from agentprov.adapters.semantics_profiles import load_semantics_profile  # noqa: PLC0415 - gate E only
    from agentprov.prov.engine import derive  # noqa: PLC0415 - the engine is only needed by gate E
    from agentprov.sem.engine import annotate  # noqa: PLC0415

    profile = load_semantics_profile(*SEMANTICS_PROFILE)
    result = derive(doc, [annotate(doc, profile)], sem_profiles={SEMANTICS_PROFILE: profile})
    for s in result.report.statements:
        diff.derivation[(str(s["rule"]), _bundle_kind(str(s["bundle"])), str(s["class"]))] += int(s["count"])
    for bundle in (result.document.get("bundle") or {}).values():
        for ident, body in (bundle.get("entity") or {}).items():
            claim = body.get("apv:claim")
            if isinstance(claim, dict) and claim.get("$") == "apv:PotentiallyInfluencedBy":
                diff.derived_taints += 1
            status = body.get("apv:contentStatus")
            if (
                body.get("apv:rule") == "aprov.decision@1"
                and isinstance(status, dict)
                and status.get("$") == "apv:Overwritten"
                and isinstance(ident, str)
            ):
                diff.derived_overwritten += 1


def finish_codes(diff: ExecutionDiff, semdiff_map: SemDiffMap) -> None:
    """Turn the measurements of one execution into its failure codes (gate E fails an execution on any of them)."""
    if diff.b1 is False:
        diff.codes.append("compat.graph_mismatch")
    if diff.unclassified:
        diff.codes.append("edges.unclassified")
    if diff.missing_edges:
        diff.codes.append("edges.missing")
    if diff.missing_nodes:
        diff.codes.append("nodes.missing")
    if sum(diff.unmapped.values()):
        diff.codes.append("unmapped")
    if diff.inference6["entailed_not_asserted"] != diff.rules["R6"] or diff.inference6["asserted_not_entailed"]:
        diff.codes.append("inference6.mismatch")
    omitted = diff.attributes.get(("adprov:defence_omitted", "e_k"), 0)  # the builder writes it only when true
    if not omitted == diff.redact_overwritten == diff.derived_overwritten:
        diff.codes.append("defence_omitted.overwritten_mismatch")
    if diff.derived_taints < diff.taint_pairs:
        # E.7.3 item 2: under unchanged labels every v2.3 sink -> untrusted-output pair is a taint assessment of the
        # request; more are allowed (fail-closed unknown tools; requests never executed), fewer are not.
        diff.codes.append("taint.not_reproduced")
    allowed = semdiff_map.allowed()
    for rule, bundle, cls in diff.derivation:
        if rule not in allowed:
            diff.codes.append(f"derivation.rule_unmapped:{rule}")
        elif (bundle, cls) not in allowed[rule]:
            diff.codes.append(f"derivation.class_unmapped:{rule}:{bundle}:{cls}")


# ================================================================================================ the report


@dataclass(frozen=True, slots=True)
class SemDiffReport:
    """``agentprov-semdiff/0.1`` for one tree (J.3.6). ``document`` is the JSON object; it holds no time or commit."""

    tree: str
    scope: str
    document: Mapping[str, Any]

    def json_text(self) -> str:
        return json.dumps(self.document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    def json_bytes(self) -> bytes:
        return self.json_text().encode("utf-8")

    @property
    def sha256(self) -> str:
        return sha256_hex(self.json_bytes())

    @property
    def unmapped(self) -> int:
        return int(self.document["unmapped"])

    def markdown(self) -> str:
        return render_markdown(self.document)


def _sum(diffs: Sequence[ExecutionDiff], name: str) -> Counter[Any]:
    total: Counter[Any] = Counter()
    for d in diffs:
        total.update(getattr(d, name))
    return total


def _counts_in_row(rule: str, label: str) -> bool:
    """Whether edges with reason ``label`` count in the row of ``rule``: an R4+R6 edge counts under R4 only (J.1.3)."""
    reasons = label.split("+")
    return rule in reasons and not (rule == "R6" and "R4" in reasons)


def _row_count(row: MapRow, totals: Mapping[str, Counter[Any]]) -> int:
    if row.rule is not None:
        return int(totals["rules"][row.rule])
    if row.node is not None:
        return int(totals["nodes"][row.node])
    if row.attribute is not None:
        return sum(n for (attr, on), n in totals["attributes"].items() if attr == row.attribute and (row.on is None or on in row.on))
    if row.measure == STATEMENTS:
        return sum(n for (rule, _b, _c), n in totals["derivation"].items() if rule in row.targets)
    return int(totals["aer"][row.measure])


def _extra_count(name: str, row: MapRow, totals: Mapping[str, Counter[Any]], scalars: Mapping[str, int]) -> int:
    if name.startswith("value:"):
        return int(totals["values"][(row.attribute, name.removeprefix("value:"))])
    return int(scalars[name])


def build_report(
    tree: str,
    scope: str,
    diffs: Sequence[ExecutionDiff],
    semdiff_map: SemDiffMap,
    *,
    spec_versions: Mapping[str, Any],
    inputs: Mapping[str, Any],
) -> SemDiffReport:
    """Join the executions of one tree with the map into the tree's :class:`SemDiffReport`."""
    totals = {name: _sum(diffs, name) for name in ("rules", "nodes", "attributes", "values", "aer", "derivation", "reasons", "unmapped", "inference6")}
    scalars = {
        "taint_pairs": sum(d.taint_pairs for d in diffs),
        "overlaps": sum(d.overlaps for d in diffs),
        "entailed_not_asserted": int(totals["inference6"]["entailed_not_asserted"]),
        "taint_assessments": sum(d.derived_taints for d in diffs),
    }
    rows: list[dict[str, Any]] = []
    labels = {key.split(":", 1)[1] for key in totals["reasons"]}
    for row in semdiff_map.rows:
        rule_labels = sorted(label for label in labels if row.rule is not None and _counts_in_row(row.rule, label))
        derived: dict[str, dict[str, int]] = {}
        for (rule, bundle, cls), n in sorted(totals["derivation"].items()):
            if rule in row.targets:
                derived.setdefault(rule, {})[f"{bundle}:{cls}"] = n
        entry: dict[str, Any] = {
            "id": row.id,
            "section": row.section,
            "v23_element": row.v23_element,
            "count": _row_count(row, totals),
            "frozen": row.frozen.get(COUNT_KEYS[tree]),
            "disposition": row.disposition,
            "targets": list(row.targets),
            "bundle": list(row.bundle),
            "evidence_class": list(row.evidence_class),
            "rules": rule_labels,
            "derived": derived,
        }
        if row.frozen_extra:
            entry["extra"] = {
                name: {"count": _extra_count(name, row, totals, scalars), "frozen": counts.get(COUNT_KEYS[tree])}
                for name, counts in sorted(row.frozen_extra.items())
            }
        if row.assumptions:
            entry["assumptions"] = list(row.assumptions)
        if row.content_status:
            entry["content_status"] = row.content_status
        if row.recompute:
            entry["recompute"] = row.recompute
        rows.append(entry)
    by_relation: dict[str, dict[str, int]] = {}
    for key, n in sorted(totals["reasons"].items()):
        relation, label = key.split(":", 1)
        by_relation.setdefault(relation, {})[label] = n
    used = sum(by_relation.get("used", {}).values())
    r6_only = int(totals["rules"]["R6"])
    unmapped_total = sum(totals["unmapped"].values())
    fired = {rule for (rule, _b, _c) in totals["derivation"]}
    document: dict[str, Any] = {
        "report": REPORT_FORMAT,
        "semdiff": SEMDIFF_ID,
        "tree": tree,
        "scope": scope,
        "spec_versions": dict(spec_versions),
        "map": {"path": MAP_RELPATH, "format": semdiff_map.format, "version": semdiff_map.version, "sha256": semdiff_map.sha256},
        "inputs": dict(inputs),
        "executions": len(diffs),
        "executions_passed": sum(1 for d in diffs if d.passed),
        "rows": rows,
        "unmapped": unmapped_total,
        "unmapped_elements": dict(sorted(totals["unmapped"].items())),
        "overlaps": {"R4+R6": scalars["overlaps"]},
        "edges": {
            "total": sum(d.edges for d in diffs),
            "classified": sum(d.edges - d.unclassified for d in diffs),
            "unclassified": sum(d.unclassified for d in diffs),
            "missing": sum(d.missing_edges for d in diffs),
            "by_relation": by_relation,
        },
        "nodes": {"by_class": dict(sorted(totals["nodes"].items())), "missing": sum(d.missing_nodes for d in diffs)},
        "attributes": {f"{attr}@{on}": n for (attr, on), n in sorted(totals["attributes"].items())},
        "inference6": dict(sorted(totals["inference6"].items())),
        "aer": dict(sorted(totals["aer"].items())),
        "defence_omitted": {
            "compat_entities": int(totals["attributes"][("adprov:defence_omitted", "e_k")]),
            "aer_redact_decisions_overwritten": sum(d.redact_overwritten for d in diffs),
            "derived_overwritten_entities": sum(d.derived_overwritten for d in diffs),
            "content_status": "apv:Overwritten",
        },
        "derivation": {
            "statements": sum(totals["derivation"].values()),
            "rules_fired": sorted(fired),
            "rules_not_targeted": sorted(fired - semdiff_map.targets()),
        },
        "values": {
            "used_total": used,
            "used_r3": int(totals["rules"]["R3"]),
            "used_r4": int(totals["rules"]["R4"]),
            "used_r6_only": r6_only,
            "taint_pairs": scalars["taint_pairs"],
            "taint_assessments": scalars["taint_assessments"],
            "overlaps_r4_r6": scalars["overlaps"],
            "was_informed_by": int(totals["rules"]["R5"]),
            "semdiff_used_taint_to_assessment": r6_only,
            "used_policy_pct": round(100.0 * r6_only / used, 2) if used else None,
        },
        "value_definitions": {
            "used_total": "prov:used edges of the compat graphs (= R3 + R4 + R6-only, J.1.3)",
            "used_r6_only": "used edges that only the R6 sink-taint policy produced (not also R4)",
            "taint_pairs": "sink -> untrusted-output pairs of R6, overlaps with R4 included (each becomes an assessment)",
            "semdiff_used_taint_to_assessment": "= used_r6_only: the used edges whose disposition is moved-to-assessment",
            "taint_assessments": "aprov.a_taint@1 assessments derived with agentdojo.suites@1; at least taint_pairs (E.7.3 item 2), more for fail-closed unknown tools and never-executed sink requests",
            "used_policy_pct": "100 * used_r6_only / used_total, two decimals: usage edges that were policy assertions encoded as facts (O claim c4-semdiff-taint)",
        },
    }
    return SemDiffReport(tree, scope, document)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value) if value else "—"
    return str(value)


def render_markdown(document: Mapping[str, Any]) -> str:
    """The Markdown rendering of one report (``semdiff-<tree>.md``): counts, dispositions and rule ids only."""
    lines = [
        f"# Semantic diff {document['semdiff']}: {document['tree']} tree ({document['scope']} scope)",
        "",
        f"Generated by `agentprov migrate gate-e` from `{document['map']['path']}` (map version {document['map']['version']}, "
        f"sha256 `{document['map']['sha256'][:16]}…`). Do not edit; numbers quoted elsewhere come from the JSON report.",
        "",
        f"- executions: {_fmt(document['executions'])} ({_fmt(document['executions_passed'])} passed)",
        f"- unmapped v2.3 elements: {_fmt(document['unmapped'])}",
        f"- edges: {_fmt(document['edges']['total'])} total, {_fmt(document['edges']['classified'])} classified, "
        f"{_fmt(document['edges']['unclassified'])} unclassified, {_fmt(document['edges']['missing'])} predicted but missing",
        f"- overlaps R4+R6 (one edge, both reasons): {_fmt(document['overlaps']['R4+R6'])}",
        f"- Inference 6 over the compat graphs: entailed {_fmt(document['inference6'].get('entailed'))}, asserted "
        f"{_fmt(document['inference6'].get('asserted'))}, entailed but not asserted "
        f"{_fmt(document['inference6'].get('entailed_not_asserted'))}",
        f"- used edges that were policy assertions (R6 only): {_fmt(document['values']['used_r6_only'])} of "
        f"{_fmt(document['values']['used_total'])} ({_fmt(document['values']['used_policy_pct'])} %)",
        "",
        "| v2.3 element | count | frozen (whole tree) | disposition | agentprov-prov/0.1 targets | bundle | class | v2.3 rules |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in document["rows"]:
        lines.append(
            f"| {row['v23_element']} | {_fmt(row['count'])} | {_fmt(row['frozen'])} | {row['disposition']} | "
            f"{_fmt(row['targets'])} | {_fmt(row['bundle'])} | {_fmt(row['evidence_class'])} | {_fmt(row['rules'])} |"
        )
    lines += ["", "## Edges by relation and reason", "", "| relation | reasons | edges |", "|---|---|---|"]
    for relation, labels in document["edges"]["by_relation"].items():
        for label, n in labels.items():
            lines.append(f"| {relation} | {label} | {_fmt(n)} |")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "AER_MEASURES",
    "DISPOSITIONS",
    "MAP_FORMAT",
    "MAP_RELPATH",
    "REPORT_FORMAT",
    "SEMDIFF_ID",
    "ExecutionDiff",
    "MapRow",
    "SemDiffMap",
    "SemDiffMapError",
    "SemDiffReport",
    "aer_measures",
    "build_report",
    "classify_graph",
    "derivation_measures",
    "finish_codes",
    "load_map",
    "map_bytes",
    "parse_map",
    "predict",
    "reason_label",
    "render_markdown",
]
