"""Index facets, the generic cell, evidence classes, oracles and completeness of one execution (HL H.3.2, H.3.3, H.7.4).

Everything here is a **pure function of the execution's AER and SEM documents** (H.3.3(3)), so the index can be
re-derived from the stored files (``derive``/``recompute``, ``verify --level chain``). Nothing is taken from an adapter:
``corpus/`` sits below ``adapters/`` (M.5.1), and invariant 1 forbids a framework from redefining these values. The
decisions taken here are recorded as D-34 (``docs/reports/phase11/decisions/D-34.md``).

* :func:`compute_facets` gives the H.3.3 core facets and their evidence classes: ``task`` (the AER header ``task``,
  verbatim), ``framework`` (the H.2.4 ``fw`` id of the ``benchmark`` actor, :func:`framework_identity`),
  ``model.requested`` / ``model.served`` (of the ``llm_agent`` actors and the agent-role model calls), the eight
  ``n.*`` counts, ``generic_types`` and ``outcome`` (AER judgement + SEM outcome polarity, R-18). Adapter facets
  ``x.<ns>.<name>`` and ``--pipeline`` are deferred (D-34).
* :func:`compute_cell` gives the generic cell of H.7.4: the AER ``task`` members, the benchmark actor's suite-set label,
  the requested agent model, the digest of the declared attack parameters and the live repeat index. A member the AER
  marks unknown is ``{"$unk": <reason>}`` and the logical key is then ``null`` (H.7.4(3)).
* :func:`completeness_of` / :func:`index_completeness` is the B2 completeness rule (H.3.2(2)), re-implemented here
  because ``corpus/`` may not import ``adapters/``. A test pins it equal to
  ``agentprov.adapters.runner.importer.index_completeness``.
* :func:`oracles_for` flags regression-oracle output (R-55).

**Evidence classes** (H.3.3(4); C.6). ``ev`` holds, for every facet and every cell member whose value comes from AER or
SEM fields, the *weakest* effective class (:func:`agentprov.aer.evidence.weakest`) of those fields: a facet is only as
reliable as its weakest input. A count's class is the weakest existence class (``ev``) of the records counted. A facet
that rests on no field (an empty array, a zero count, an absent ``task`` or framework) and a member that is unknown, or
``null`` by definition (``repeat`` of an import), have no entry. The ``outcome`` elements carry their own per-member
``ev`` (as H.2.4's ``ev`` does), so an observed checker value and an inferred polarity stay distinguishable.

**No floats** (H.1.4(3)). A non-integral number copied from an AER or SEM value (a judgement score) is written
``{"$dec": "<its JCS spelling>"}``; :func:`corpus_value` does the conversion.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Collection, Iterable, Mapping
from typing import Any, Final

from agentprov.aer.canon import pointer_escape, pointer_unescape
from agentprov.aer.evidence import effective_tag, is_prefix, tag_class, weakest
from agentprov.aer.reader import AerDocument
from agentprov.aer.rules import load_catalogue
from agentprov.aer.types import UNKNOWN_REASONS
from agentprov.corpus.index import (
    CORE_FACET_TYPES,
    COUNT_FACETS,
    DECIMAL_KEY,
    ORACLE_SPECS,
    ORACLE_STATUS,
    UNKNOWN_KEY,
    FacetMembers,
    logical_key,
)
from agentprov.errors import AgentProvError
from agentprov.io.canonical import base32_lower_nopad, jcs_bytes, sha256_hex
from agentprov.sem.types import SemDocument

__all__ = [
    "CORE_FACET_SCHEMA",
    "DEGENERATE_CODES",
    "LOSS_CODES",
    "FacetError",
    "completeness_of",
    "header_rule_class",
    "kept_results",
    "proven_loss_codes",
    "compute_cell",
    "compute_facets",
    "corpus_value",
    "facet_members",
    "facet_schema",
    "framework_identity",
    "index_completeness",
    "oracles_for",
]

# ------------------------------------------------------------------------------------------------ completeness (B2)
#: Seal issues of a degenerate AER (D.2.8 case 3). Equal to the importer's ``_DEGENERATE_CODES`` (pinned by a test).
DEGENERATE_CODES: Final = frozenset({"unparseable_artefact", "unsupported_variant", "adapter_defect"})
#: Seal issues an adapter rule raises only when it proves loss (H.3.2(2): ``known_incomplete``). Equal to the importer's
#: ``_LOSS_CODES`` (pinned by a test). ``missing_tool_result`` is a declared loss (regeneration-batch item 11, E2-b2).
LOSS_CODES: Final = frozenset({"incomplete_run", "retry_passes_inferred", "aborted_attempt", "missing_tool_result"})


def proven_loss_codes(issues: Iterable[Mapping[str, Any]], rule_class: Callable[[str], str],
                      kept_results: Collection[str] = ()) -> frozenset[str]:
    """The loss codes among ``issues`` that a class-D rule proves (H.3.2(2): "an adapter rule proves loss"; D-24, B6).

    A loss issue citing only an I rule (the retry inference under an ``_unverified`` twin, D.5.4) infers the loss and
    does not prove it; an issue without a rule proves nothing. A ``missing_tool_result`` whose every listed execution is
    in ``kept_results`` (it generated an artefact holding its result: a declared removal, e.g. the react ``submit``
    message, regeneration-batch item 16) loses nothing. ``rule_class`` maps a rule reference without pointer to its
    class. One function for the importer and for ``derive``/``recompute`` (D-372)."""
    proven: set[str] = set()
    for issue in issues:
        code, rule = issue.get("code"), issue.get("rule")
        if code not in LOSS_CODES or not isinstance(rule, str):
            continue
        ids = issue.get("ids")
        if code == "missing_tool_result" and isinstance(ids, list) and ids and all(i in kept_results for i in ids):
            continue
        if rule_class(rule.partition("#")[0]) == "D":
            proven.add(str(code))
    return frozenset(proven)


def kept_results(records: Iterable[Mapping[str, Any]]) -> frozenset[str]:
    """The ids that generated an ``artefact`` record (``generated_by``): executions whose result the AER keeps."""
    return frozenset(str(r["generated_by"]) for r in records
                     if r.get("k") == "artefact" and isinstance(r.get("generated_by"), str))


def header_rule_class(header: Mapping[str, Any]) -> Callable[[str], str]:
    """The class of a rule reference in the catalogue version the AER header declares (``D`` when not shipped or not
    declared: the reader then fails elsewhere, and loss stays proven as before the D-24 rule)."""
    raw = header.get("rules")
    declared: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}

    def cls(ref: str) -> str:
        namespace = ref.split(".", 1)[0]
        version = declared.get(namespace)
        try:
            entry = load_catalogue(namespace, version if isinstance(version, int) else None).get(ref)
        except AgentProvError:
            return "D"
        return entry.cls if entry is not None else "D"

    return cls


def index_completeness(*, degenerate: bool, accounting: str, checks_evaluated: int, unit_kind: str,
                       seal_codes: frozenset[str] | set[str]) -> str:
    """The index ``completeness`` of an execution (H.3.2(2) as amended by phase-10 analysis B2).

    ``known_incomplete`` when the seal accounting is ``inconsistent`` or an adapter rule proves loss. ``verified_complete``
    only when the seal accounting is ``consistent`` **because at least one accounting check was evaluated** and the unit
    is an ``agent_execution`` (vacuous accounting is not verification). A degenerate AER and every other case is
    ``unverifiable``. Same inputs and result as ``agentprov.adapters.runner.importer.index_completeness``.
    """
    if degenerate:
        return "unverifiable"
    if accounting == "inconsistent" or seal_codes & LOSS_CODES:
        return "known_incomplete"
    if accounting == "consistent" and checks_evaluated > 0 and unit_kind == "agent_execution":
        return "verified_complete"
    return "unverifiable"


def completeness_of(aer: AerDocument) -> str:
    """:func:`index_completeness` read from a stored AER: the header ``unit`` and the seal's accounting and issues, the
    loss codes reduced to those a class-D rule proves (:func:`proven_loss_codes`), exactly as the importer does.

    The importer's ``degenerate`` flag is observable in the AER as a :data:`DEGENERATE_CODES` seal issue (D.2.8 case 3).
    """
    seal = aer.seal
    issues = [i for i in seal.get("issues", ()) if isinstance(i, Mapping)]
    codes = {str(i.get("code")) for i in issues}
    if codes & LOSS_CODES:  # D-24/B6 and item 11: only a loss a class-D rule proves counts (D-372)
        kept = kept_results(aer.records) if "missing_tool_result" in codes else frozenset()
        codes -= (codes & LOSS_CODES) - proven_loss_codes(issues, header_rule_class(aer.header), kept)
    accounting = seal.get("accounting")
    status = str(accounting.get("status")) if isinstance(accounting, Mapping) else ""
    checks = accounting.get("checks") if isinstance(accounting, Mapping) else None
    return index_completeness(
        degenerate=bool(codes & DEGENERATE_CODES),
        accounting=status,
        checks_evaluated=len(checks) if isinstance(checks, list) else 0,
        unit_kind=str(aer.header.get("unit")),
        seal_codes=codes,
    )


# ------------------------------------------------------------------------------------------------ facet schema
_FACET_RULES: Final[Mapping[str, str]] = {
    "task": "/task",  # a JSON Pointer into the AER execution header: a verbatim copy
    "framework": "corpus.facet_framework@1",
    "model.requested": "corpus.facet_model_requested@1",
    "model.served": "corpus.facet_model_served@1",
    **dict.fromkeys(COUNT_FACETS, "corpus.facet_counts@1"),
    "generic_types": "corpus.facet_generic_types@1",
    "outcome": "corpus.facet_outcome@1",
}
#: The ``FacetDecl`` entries of the core facets (H.3.3(1)), in H.3.3(2) order, for ``corpus.json`` ``facet_schema``.
#: ``from`` is a JSON Pointer for a verbatim copy and a ``corpus`` rule id for a computed facet (the ids are declared in
#: the corpus rule catalogue with sealing, U3). Every core facet may carry class ``I``: a facet is as weak as its inputs.
CORE_FACET_SCHEMA: Final[tuple[Mapping[str, Any], ...]] = tuple(
    {"core": True, "from": _FACET_RULES[name], "may_be_inferred": True, "name": name, "type": kind}
    for name, kind in CORE_FACET_TYPES.items()
)


def facet_schema() -> list[dict[str, Any]]:
    """A fresh copy of :data:`CORE_FACET_SCHEMA` (adapter facets are deferred, D-34)."""
    return [dict(d) for d in CORE_FACET_SCHEMA]


class FacetError(AgentProvError):
    """The facets of an execution cannot be computed from its AER and SEM (``corpus.facet.invalid``)."""

    code = "corpus.facet.invalid"
    exit_code = 1


# ------------------------------------------------------------------------------------------------ helpers
def corpus_value(value: Any) -> Any:
    """A JSON value with every float replaced by ``{"$dec": "<JCS spelling>"}`` (H.1.4(3); D-34), and an integer outside
    +-(2^53 - 1) likewise (the AER wraps those as ``$int`` already, so this is defensive). Iterative copy."""
    if isinstance(value, float) or (isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**53 - 1):
        return {DECIMAL_KEY: jcs_bytes(value).decode("ascii")}
    if isinstance(value, Mapping):
        return {str(k): corpus_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [corpus_value(v) for v in value]
    return value


def _unknown_reason(record: Mapping[str, Any], pointer: str) -> str | None:
    """The C.7.1 reason when ``record``'s ``unk`` covers ``pointer`` (the key equals it or is a ``/``-prefix of it); the
    first reason in C.7.1 order when several keys cover it; ``None`` when the value is not declared unknown."""
    unk = record.get("unk")
    if not isinstance(unk, Mapping):
        return None
    reasons = {str(r) for key, r in unk.items() if isinstance(key, str) and is_prefix(key, pointer)}
    if not reasons:
        return None
    return next((r for r in UNKNOWN_REASONS if r in reasons), sorted(reasons)[0])


_MISSING: Final = object()


def _resolve(record: Mapping[str, Any], pointer: str) -> Any:
    """The value at a JSON Pointer of object members (no array indices are needed here), or :data:`_MISSING`."""
    node: Any = record
    for token in pointer.split("/")[1:]:
        if not isinstance(node, Mapping):
            return _MISSING
        key = pointer_unescape(token)
        if key not in node:
            return _MISSING
        node = node[key]
    return node


def _known_str(record: Mapping[str, Any], pointer: str) -> str | None:
    """The string at ``pointer`` when it is present and not declared unknown; ``None`` otherwise."""
    if _unknown_reason(record, pointer) is not None:
        return None
    value = _resolve(record, pointer)
    return value if isinstance(value, str) else None


def _cls(record: Mapping[str, Any], pointer: str) -> str:
    return tag_class(effective_tag(record, pointer))


def _of_kind(aer: AerDocument, kind: str) -> list[dict[str, Any]]:
    return [r for r in aer.records if r.get("k") == kind]


# ------------------------------------------------------------------------------------------------ framework (H.2.4)
def framework_identity(aer: AerDocument) -> dict[str, Any] | None:
    """The H.2.4 framework identity recorded on the execution's ``benchmark`` actor, without ``executions`` (a corpus
    aggregate) and without ``tool_definitions_sha256`` / ``system_prompt_sha256`` (manifest members, sealing, U3).

    ``fw = "fw_" + b32(sha256("aer-fw/1\\n" + JCS(core)))[:16]`` with ``core = {distribution, source,
    source_tree_sha256, suite_set}``. From the actor: ``distribution`` = ``code.dist``, ``reported_version`` =
    ``code.dist_version`` (verbatim), ``source`` = the ``code`` members ``repo``, ``commit`` and ``wheel_sha256`` that
    are recorded (a commit or wheel origin; ``null`` when none is), ``suite_set`` = the actor's ``version`` (C.3: the
    suite-set label lives there). ``source_tree_sha256`` is a live-capture digest that ``aer/0.1`` does not record, so it
    is ``null``. A value the actor declares unknown is ``null``. ``None`` when there is no benchmark actor, more than one,
    or when distribution, source and suite set are all unknown (an id over nothing would merge unrelated frameworks).
    ``ev`` gives the class of each non-null field.
    """
    benches = [a for a in _of_kind(aer, "actor") if a.get("kind") == "benchmark"]
    if len(benches) != 1:
        return None
    bench = benches[0]
    distribution = _known_str(bench, "/code/dist")
    reported = _known_str(bench, "/code/dist_version")
    suite_set = _known_str(bench, "/version")
    source_members = {k: v for k in ("commit", "repo", "wheel_sha256") if (v := _known_str(bench, f"/code/{k}")) is not None}
    source = source_members or None
    if distribution is None and source is None and suite_set is None:
        return None
    core = {"distribution": distribution, "source": source, "source_tree_sha256": None, "suite_set": suite_set}
    fw = "fw_" + base32_lower_nopad(hashlib.sha256(b"aer-fw/1\n" + jcs_bytes(core)).digest())[:16]
    ev: dict[str, str] = {}
    if distribution is not None:
        ev["distribution"] = _cls(bench, "/code/dist")
    if reported is not None:
        ev["reported_version"] = _cls(bench, "/code/dist_version")
    if source is not None:
        ev["source"] = weakest(*(_cls(bench, f"/code/{k}") for k in source))
    if suite_set is not None:
        ev["suite_set"] = _cls(bench, "/version")
    return {
        "distribution": distribution,
        "ev": ev,
        "fw": fw,
        "reported_version": reported,
        "source": source,
        "source_tree_sha256": None,
        "suite_set": suite_set,
    }


# ------------------------------------------------------------------------------------------------ facets (H.3.3)
_COUNT_KINDS: Final[Mapping[str, str]] = {
    "n.messages": "message",
    "n.model_calls": "model_call",
    "n.tool_executions": "tool_execution",
    "n.decisions": "decision",
    "n.judgements": "judgement",
    "n.state_changes": "state_change",
    "n.activities": "activity",
    "n.artefacts": "artefact",
}
_OUTCOME_SEM: Final = ("claim", "holds", "score", "scale")


def _check_sem(aer: AerDocument, sem: Mapping[str, SemDocument]) -> None:
    for ref, doc in sem.items():
        if doc.ex != aer.ex or doc.aer_digest != aer.execution_digest:
            raise FacetError(f"the SEM document of {ref} does not annotate this AER (execution digest differs; D9 chain)")


def _outcome(aer: AerDocument, sem: Mapping[str, SemDocument]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for judgement in _of_kind(aer, "judgement"):
        jid = str(judgement.get("id"))
        element: dict[str, Any] = dict.fromkeys(("name", "value", "origin", *_OUTCOME_SEM))
        ev: dict[str, str] = {}
        for member in ("name", "origin"):
            text = _known_str(judgement, f"/{member}")
            if text is not None:
                element[member] = text
                ev[member] = _cls(judgement, f"/{member}")
        if _unknown_reason(judgement, "/value") is None and judgement.get("value") is not None:
            element["value"] = corpus_value(judgement["value"])
            ev["value"] = _cls(judgement, "/value")
        found = [a for ref in sorted(sem) for a in sem[ref].on(jid, "outcome")]
        if len({jcs_bytes(a.get("value")) for a in found}) > 1:
            raise FacetError("two outcome annotations of one judgement disagree (SEM polarity is ambiguous)")
        if found:
            annotation = found[0]
            value = annotation.get("value")
            if isinstance(value, Mapping):
                for member in _OUTCOME_SEM:
                    if value.get(member) is not None:
                        element[member] = corpus_value(value[member])
                        ev[member] = _cls(annotation, f"/value/{member}")
        element["ev"] = ev
        out.append(element)
    return out


def compute_facets(aer: AerDocument, sem: Mapping[str, SemDocument] | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    """The H.3.3 core facets of one execution and their evidence classes ``(facets, ev)``.

    ``sem`` maps a semantics-profile reference (``<id>@<version>``) to the execution's verified SEM document; every
    document must annotate this AER (its ``aer_digest`` equals the AER execution digest), otherwise
    :class:`FacetError`. Without SEM, the outcome members ``claim``, ``holds``, ``score`` and ``scale`` are ``null``.
    """
    sem = dict(sem or {})
    _check_sem(aer, sem)
    header = aer.header
    facets: dict[str, Any] = {}
    ev: dict[str, str] = {}

    task = header.get("task")
    if isinstance(task, Mapping):
        facets["task"] = corpus_value(task)
        tags = [_cls(header, "/task/" + pointer_escape(str(k))) for k in task]
        ev["task"] = weakest(*tags) if tags else _cls(header, "/task")
    else:
        facets["task"] = None

    identity = framework_identity(aer)
    facets["framework"] = identity["fw"] if identity else None
    if identity:
        core_tags = [identity["ev"][k] for k in ("distribution", "source", "suite_set") if k in identity["ev"]]
        ev["framework"] = weakest(*core_tags)

    agents = [a for a in _of_kind(aer, "actor") if a.get("kind") == "llm_agent"]
    requested: dict[str, list[str]] = {}
    served: dict[str, list[str]] = {}
    for agent in agents:
        for pointer, bucket in (("/model/requested", requested), ("/model/served", served)):
            text = _known_str(agent, pointer)
            if text is not None:
                bucket.setdefault(text, []).append(_cls(agent, pointer))
    for call in _of_kind(aer, "model_call"):
        if call.get("role") == "agent":
            text = _known_str(call, "/served_model")
            if text is not None:
                served.setdefault(text, []).append(_cls(call, "/served_model"))
    for name, bucket in (("model.requested", requested), ("model.served", served)):
        facets[name] = sorted(bucket)
        if bucket:
            ev[name] = weakest(*(t for tags in bucket.values() for t in tags))

    for name, kind in _COUNT_KINDS.items():
        records = _of_kind(aer, kind)
        facets[name] = len(records)
        existence = [str(r["ev"]) for r in records if isinstance(r.get("ev"), str)]
        if existence:
            ev[name] = weakest(*existence)

    generic: dict[str, list[str]] = {}
    for record in (*_of_kind(aer, "activity"), *_of_kind(aer, "artefact")):
        kind_type = record.get("type")
        if isinstance(kind_type, str):
            generic.setdefault(kind_type, []).append(_cls(record, "/type"))
    facets["generic_types"] = sorted(generic)
    if generic:
        ev["generic_types"] = weakest(*(t for tags in generic.values() for t in tags))

    outcome = _outcome(aer, sem)
    facets["outcome"] = outcome
    outcome_tags = [t for element in outcome for t in element["ev"].values()]
    if outcome_tags:
        ev["outcome"] = weakest(*outcome_tags)
    return facets, ev


# ------------------------------------------------------------------------------------------------ cell (H.7.4)
#: The AER ``task`` members (C.3.1 ``Task``, a closed object) in cell order; ``benchmark`` and ``task_id`` are required.
TASK_MEMBERS: Final = ("benchmark", "suite", "environment", "task_id", "attack_id", "attack_target_id", "defense_id")
_REQUIRED_TASK: Final = frozenset({"benchmark", "task_id"})


def _unknown(reason: str) -> dict[str, str]:
    return {UNKNOWN_KEY: reason}


def compute_cell(aer: AerDocument, *, repeat: int | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    """The generic cell of one execution and the evidence classes of its members ``(cell, ev)`` (H.7.4; D-34).

    Members (names follow the AER, as the ``task`` facet does):

    * every ``task`` member that the header records, or declares unknown; ``benchmark`` and ``task_id`` are required
      (C.3.1), so their absence makes them unknown (``not_recorded``); an absent optional member is not a coordinate;
    * ``suite_set``: the ``benchmark`` actor's ``version`` (the suite-set label, C.3.1); absent without a benchmark actor;
      ``ambiguous`` with more than one;
    * ``model``: the requested model of the ``llm_agent`` actors (a string; a sorted array when several agents request
      different models); unknown when no agent actor records it;
    * ``attack_params_sha256``: ``"sha256:" + sha256(JCS([{id, params}…]))`` over the header's ``attack_parameter``
      instrumentation items, sorted by id (CAP-8); unknown when such an item records no ``params``; absent when the
      header declares no such item (including a header whose ``instrumentation`` is itself unrecorded: D-34);
    * ``repeat``: ``null`` for an import; for a live execution the run ledger's repeat index, which the caller passes
      (the capture log does not hold it, MN N.2.1b), unknown when it is not given.

    Its keys ``ev`` are ``cell.<member>``. The logical key is :func:`agentprov.corpus.index.logical_key` of the cell when no
    member is unknown, else ``null``.
    """
    header = aer.header
    cell: dict[str, Any] = {}
    ev: dict[str, str] = {}
    task = header.get("task")
    for member in TASK_MEMBERS:
        pointer = f"/task/{member}"
        reason = _unknown_reason(header, pointer)
        if reason is not None:
            cell[member] = _unknown(reason)
        elif isinstance(task, Mapping) and member in task:
            cell[member] = corpus_value(task[member])
            ev[f"cell.{member}"] = _cls(header, pointer)
        elif member in _REQUIRED_TASK:
            cell[member] = _unknown("not_recorded")

    actors = _of_kind(aer, "actor")
    benches = [a for a in actors if a.get("kind") == "benchmark"]
    if len(benches) > 1:
        cell["suite_set"] = _unknown("ambiguous")
    elif benches:
        bench = benches[0]
        reason = _unknown_reason(bench, "/version")
        if reason is not None:
            cell["suite_set"] = _unknown(reason)
        elif "version" in bench:
            cell["suite_set"] = corpus_value(bench["version"])
            ev["cell.suite_set"] = _cls(bench, "/version")

    agents = [a for a in actors if a.get("kind") == "llm_agent"]
    models: dict[str, str] = {}
    model_reason: str | None = None if agents else "not_recorded"
    for agent in agents:
        reason = _unknown_reason(agent, "/model/requested")
        text = _known_str(agent, "/model/requested")
        if text is None:
            model_reason = model_reason or reason or "not_recorded"
        else:
            models[text] = weakest(models[text], _cls(agent, "/model/requested")) if text in models else _cls(
                agent, "/model/requested")
    if model_reason is not None:
        cell["model"] = _unknown(model_reason)
    else:
        names = sorted(models)
        cell["model"] = names[0] if len(names) == 1 else names
        ev["cell.model"] = weakest(*models.values())

    items = header.get("instrumentation")
    if isinstance(items, list):
        params = [(i, item) for i, item in enumerate(items) if isinstance(item, Mapping) and item.get("kind") == "attack_parameter"]
        if params:
            if any("params" not in item or _unknown_reason(header, f"/instrumentation/{i}/params") for i, item in params):
                cell["attack_params_sha256"] = _unknown("not_recorded")
            else:
                listed = sorted(({"id": item.get("id"), "params": item["params"]} for _, item in params),
                                key=lambda d: jcs_bytes(d.get("id")))
                cell["attack_params_sha256"] = "sha256:" + sha256_hex(jcs_bytes(listed))
                ev["cell.attack_params_sha256"] = weakest(*(_cls(header, f"/instrumentation/{i}/params") for i, _ in params))

    if header.get("mode") == "live":
        if repeat is None:
            cell["repeat"] = _unknown("not_recorded")
        else:
            if isinstance(repeat, bool) or not isinstance(repeat, int) or repeat < 0:
                raise FacetError("a repeat index is a non-negative integer")
            cell["repeat"] = repeat
            ev["cell.repeat"] = "O"  # the run ledger's own record (L.2.2: attempt and repeat index, class O)
    else:
        if repeat is not None:
            raise FacetError("an imported execution has no repeat index")
        cell["repeat"] = None
    return cell, ev


# ------------------------------------------------------------------------------------------------ oracles and members
def oracles_for(prov_specs: Iterable[str], gate_reports: Mapping[str, str | None] | None = None) -> dict[str, dict[str, Any]]:
    """The row ``oracles``: one ``{gate_report, status: apv:RegressionOracle}`` per regression-oracle spec among the specs
    with output (R-55); ``{}`` when there is none. ``gate_reports`` maps a spec to its gate report's ``sha256:`` digest."""
    reports = gate_reports or {}
    return {spec: {"gate_report": reports.get(spec), "status": ORACLE_STATUS} for spec in sorted(set(prov_specs)) if spec in ORACLE_SPECS}


def facet_members(
    aer: AerDocument,
    sem: Mapping[str, SemDocument] | None = None,
    *,
    repeat: int | None = None,
    prov_specs: Iterable[str] = (),
    gate_reports: Mapping[str, str | None] | None = None,
) -> FacetMembers:
    """The five full-row members of one execution (H.3.1): ``logical_key``, ``cell``, ``facets``, ``ev``, ``oracles``.

    ``prov_specs`` are the specs with PROV output for this execution (``paths.prov``). The result is validated by
    :class:`agentprov.corpus.index.FacetMembers`.
    """
    facets, facet_ev = compute_facets(aer, sem)
    cell, cell_ev = compute_cell(aer, repeat=repeat)
    unknown = any(isinstance(v, Mapping) and set(v) == {UNKNOWN_KEY} for v in cell.values())
    key = None if unknown or not cell else logical_key(cell)
    return FacetMembers(key, cell, facets, {**facet_ev, **cell_ev}, oracles_for(prov_specs, gate_reports))
