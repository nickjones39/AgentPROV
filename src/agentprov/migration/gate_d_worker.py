"""Gate D, one execution (J.3.5): the unit of work that runs in a worker process of :mod:`agentprov.migration.gate_d`.

:func:`run_item` takes one sealed AER (read from a corpus, or the bytes of a golden mapping), annotates it with the semantics
profiles of its work item (``agentdojo.suites@1`` for the migration trees), derives ``agentprov-prov/0.1``, validates every D8
tier in release mode (a skipped check is a failure, MP-3) and runs the dedicated J.3.5 checks over the derived document:

* **never emit** (D7, as amended by A5 and AD-19): every ``used``, ``wasGeneratedBy``, ``wasAssociatedWith`` and ``wasInformedBy``
  cites a catalogue rule; ``wasInformedBy`` is the ``aprov.comm@1`` statement with ``apv:premise`` in the core or an inference
  bundle (its exactness is the Inference-6 closure check ``PV-NE-7``, required to pass); a ``ToolExecution`` uses only its own
  request, no activity is used and only entities are mentioned (R-21); a request is a member of its assistant message, typed
  ``prov:Collection`` (AD-19(a)); for the v1 trees, context membership appears only in ``inf.adprov-context_is_prefix-v1``;
  no relation carries a time, no ``"0"``/``""`` time literal appears and every time attribute restates a typed AER ``t``
  value (AD-19(d));
* **generic record kinds** (AD-15): the v1 and TraceLogger AERs hold 0 ``activity`` and 0 ``artefact`` records and the PROV
  holds 0 statements from G-ACT, G-USE, G-GEN and G-ASSOC;
* **per-execution cross-counts** (the decidable half of the J.3.5 table): ``ToolExecution`` activities, request entities,
  requests without execution (``apv:NotDispatched``, listed under ``unexecuted_tool_call``), the invocations that generate a
  held assistant message, the user and system message entities and ``wasGeneratedBy(tool_result, ToolExecution)`` against the
  AER.

The module never writes: a corpus is opened through :class:`~agentprov.corpus.reader.CorpusReader` (read-only, chain-checked) and
the result is a plain dictionary of codes, check statuses, digests, counts and timings (no payload text; MP-6). It imports
no gate machinery, so a worker process loads only the engines and validators.
"""

from __future__ import annotations

import hashlib
import io
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner.provjob import PROFILES, tier3_checks
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.validate import AerValidator, iter_lines
from agentprov.corpus.index import IndexRow
from agentprov.corpus.reader import CorpusReader
from agentprov.errors import AgentProvError
from agentprov.prov.engine import ProvDerivation, derive
from agentprov.prov.serialise.time import prov_time
from agentprov.prov.specs import SPEC_ID, load_spec
from agentprov.sem.engine import annotate, dumps_sem
from agentprov.sem.validate import validate_sem_document
from agentprov.validate import validate_prov

__all__ = [
    "GENERIC_RULES",
    "MIXTRAL_PATHS",
    "NATIVE_PROFILE",
    "WorkItem",
    "classify_tree",
    "run_item",
]

#: The semantics profile every migration AER is annotated with (J.3.5: ``semantics(AER, agentdojo.suites@1)``).
NATIVE_PROFILE: Final = "agentdojo.suites@1"
#: G-ACT, G-USE, G-GEN, G-ASSOC (AD-15): they contribute 0 statements on the migration trees.
GENERIC_RULES: Final = frozenset({"aprov.g_act@1", "aprov.g_use@1", "aprov.g_gen@1", "aprov.g_assoc@1"})
#: The one generic activity type the never-emit check admits in a migration AER (J.3.5 as amended, user decision
#: 2026-10-13): the TraceLogger mapper's environment load (regeneration-batch item 5, D-370), for which aer/0.1 has no
#: specialised kind. Its G-ACT/G-USE/G-ASSOC statements are admitted with it; any other generic record still fails.
EXEMPT_ACTIVITY_TYPES: Final = frozenset({"agentdojo:load_environment"})
#: The 7 upstream-only Mixtral logs at ``c274885`` that the converted tree lacks (J.4.1, R-28); native-only, reported apart.
MIXTRAL_PATHS: Final = frozenset(
    f"runs/mistralai_Mixtral-8x7B-Instruct-v0.1/{task}/none/none.json"
    for task in (
        "banking/user_task_0", "slack/user_task_0", "slack/user_task_1", "travel/user_task_0",
        "workspace/user_task_0", "workspace/user_task_1", "workspace/user_task_3",
    )
)  # fmt: skip
_ROUTING: Final = ("used", "wasGeneratedBy", "wasAssociatedWith", "wasInformedBy")
_NODES: Final = ("entity", "activity", "agent")
_TIME_KEYS: Final = ("prov:startTime", "prov:endTime", "prov:time")
_LEXICAL_KEYS: Final = ("apv:startTimeLexical", "apv:endTimeLexical")
_CONTEXT_METHOD: Final = "adprov.context_is_prefix@1"
_MIGRATION_TREES: Final = ("release", "converted", "native")


def classify_tree(row: IndexRow) -> str:
    """The J.3.5 tree an index row belongs to: ``release`` and ``converted`` (the v1 import of the two baseline trees),
    ``native`` (the June-2024 upstream import), else ``other`` (validated, but no cross-count table applies)."""
    adapter = row.adapter.split("@", 1)[0]
    snapshots = tuple(row.snapshot_ids)
    if adapter == "adprov.transcript_v1":
        if snapshots == ("release",):
            return "release"
        if snapshots in (("converted",), ("converted-legacy",)):
            return "converted"
    if adapter == "agentdojo.tracelogger" and row.source_id == "agentdojo" and snapshots == ("2024-06",):
        return "native"
    return "other"


@dataclass(frozen=True, slots=True)
class WorkItem:
    """One execution to check. Either ``root`` and ``row`` (a stored AER of a corpus, read-only) or ``aer`` and ``raw`` (the
    sealed bytes of a golden mapping and the source bytes its locators resolve against)."""

    label: str
    tree: str
    root: str | None = None
    state: str = "working"
    used_partial: bool = False
    shard_depth: int = 1
    row: IndexRow | None = None
    aer: bytes | None = None
    raw: bytes | None = None
    adapter: str = ""
    profiles: tuple[str, ...] = (NATIVE_PROFILE,)
    twice: bool = False  # golden scope: SEM and PROV are produced twice and must be byte-identical


# --------------------------------------------------------------------------------------------------------------- state

_READERS: dict[tuple[str, str], CorpusReader] = {}
_REGISTRY: list[RuleRegistry] = []


def _reader(item: WorkItem) -> CorpusReader:
    assert item.root is not None
    key = (item.root, item.state)
    found = _READERS.get(key)
    if found is None:
        found = CorpusReader(item.root, state=item.state, used_partial=item.used_partial, shard_depth=item.shard_depth)
        _READERS[key] = found
    return found


def _registry() -> RuleRegistry:
    if not _REGISTRY:
        _REGISTRY.append(RuleRegistry.default())
    return _REGISTRY[0]


class _BytesStore:
    """A raw store holding one object, for the tier-2 locator checks of a golden execution."""

    def __init__(self, raw: bytes) -> None:
        self.sha, self.raw = hashlib.sha256(raw).hexdigest(), raw

    def has(self, sha256: str) -> bool:
        return sha256 == self.sha

    def size(self, sha256: str) -> int:
        return len(self.raw)

    def read_bytes(self, sha256: str) -> bytes:
        return self.raw


# ------------------------------------------------------------------------------------------------------- the unit of work


def run_item(item: WorkItem) -> dict[str, Any]:
    """Check one execution. Never raises: a fault becomes the code ``gate_d.error:<code or type>`` (no message text)."""
    started = time.perf_counter()
    out: dict[str, Any] = {
        "item": item.label, "tree": item.tree, "subset": "matched", "unit": None, "codes": [], "checks": {},
        "m": {}, "digests": {}, "stored": {}, "t": {}, "statements": 0, "diagnostics": 0,
    }  # fmt: skip
    try:
        _run(item, out)
    except AgentProvError as exc:
        out["codes"].append(f"gate_d.error:{exc.code}")
    except Exception as exc:  # noqa: BLE001 - a fault fails the execution; the type only is kept (MP-6)
        out["codes"].append(f"gate_d.error:{type(exc).__name__}")
    out["t"]["total"] = time.perf_counter() - started
    out["codes"] = sorted(set(out["codes"]))
    return out


def _run(item: WorkItem, out: dict[str, Any]) -> None:
    codes: list[str] = out["codes"]
    t = out["t"]
    mark = time.perf_counter()
    store: Any
    if item.row is not None:
        reader = _reader(item)
        data = reader.aer_bytes(item.row)
        store = reader.raw_store()
    else:
        assert item.aer is not None and item.raw is not None
        data = item.aer
        store = _BytesStore(item.raw)
    doc = load_aer_bytes(data, verify=True)
    if item.row is not None and (doc.execution_digest != item.row.aer_digest or doc.ex != item.row.ex):
        codes.append("input.aer_digest_mismatch")
    out["unit"] = doc.header.get("unit")
    out["digests"]["aer"] = doc.execution_digest
    t["read"] = time.perf_counter() - mark

    # --- tier 2: the AER validator, release mode, locators resolved against the digest-checked raw store
    mark = time.perf_counter()
    aer_status = _validate_aer(data, store, doc)
    out["checks"]["d8.aer"] = aer_status
    if aer_status != "pass":
        codes.append("d8.aer" if aer_status == "fail" else "d8.aer.skipped")
    t["aer"] = time.perf_counter() - mark

    migration = item.tree in _MIGRATION_TREES
    if item.tree == "native":
        origin = (doc.header.get("artifacts") or [{}])[0].get("origin") or {}
        if out["unit"] == "outcome_only":
            out["subset"] = "outcome_only"
        elif origin.get("path") in MIXTRAL_PATHS:
            out["subset"] = "mixtral"

    # --- tier 3 and the PROV derivation
    mark = time.perf_counter()
    sems, profiles, sem_digests = _annotate(item, doc, out)
    t["sem"] = time.perf_counter() - mark
    mark = time.perf_counter()
    result = derive(doc, sems, sem_profiles=profiles, check_aer=False)
    t["derive"] = time.perf_counter() - mark
    if item.twice:
        again = [annotate(doc, PROFILES[ref]) for ref in item.profiles if ref in PROFILES]
        if [dumps_sem(a) for a in again] != [dumps_sem(s) for s in sems]:
            codes.append("determinism.sem")
        if derive(doc, again, sem_profiles=profiles, check_aer=False).prov_json != result.prov_json:
            codes.append("determinism.prov")
    prov_sha = hashlib.sha256(result.prov_json).hexdigest()
    out["digests"]["prov"] = prov_sha
    out["digests"]["sem"] = sem_digests
    out["statements"] = _statement_count(result)
    _compare_stored(item, out, prov_sha, sem_digests)

    # --- tier 4, release mode, with the gate-D migration checks for the v1 imports
    mark = time.perf_counter()
    v1 = item.adapter.split("@", 1)[0] == "adprov.transcript_v1"
    report = validate_prov(result.prov_json, doc, migration=v1, sems=sems)
    failed = [o.id for o in report.outcomes if o.status == "fail"]
    skipped = [o.id for o in report.outcomes if o.status == "skipped"]
    for outcome in report.outcomes:
        out["checks"][outcome.id] = outcome.status
    if failed:
        codes.append("d8.prov:" + ",".join(failed[:5]))
    if skipped:
        codes.append("d8.prov.skipped:" + ",".join(skipped[:5]))
    out["diagnostics"] = len(report.diagnostics)
    t["validate"] = time.perf_counter() - mark

    # --- the dedicated J.3.5 checks over the derived document
    mark = time.perf_counter()
    closure = report.get("PV-NE-7")
    if closure is None or closure.status != "pass":
        codes.append("ne.informed_by_closure")
    metrics = _dedicated(result, doc, codes, v1=v1, migration=migration)
    out["m"] = metrics
    if migration:
        _cross_counts(doc, metrics, codes)
    t["checks"] = time.perf_counter() - mark


def _validate_aer(data: bytes, store: Any, doc: AerDocument) -> str:
    profile = doc.header.get("profile") or {}
    digests: dict[tuple[str, int], str] = {}
    try:
        version = profile.get("version")
        package = load_profile(str(profile.get("id")), version if isinstance(version, int) and not isinstance(version, bool) else None)
        digests[(package.id, package.version)] = package.sha256
    except AgentProvError:
        return "fail"  # the AER names a mapping profile this package does not ship (AER-V35 cannot be decided)
    validator = AerValidator(store=store, catalogues=_registry(), mode="release", profile_digests=digests)
    for line, oversize in iter_lines(io.BytesIO(data)):
        validator.feed(line, oversize=oversize)
    report = validator.finish()
    if report.skipped:
        return "skipped"
    return "pass" if report.ok and report.passed else "fail"


def _annotate(
    item: WorkItem, doc: AerDocument, out: dict[str, Any]
) -> tuple[list[Any], dict[tuple[str, int], Any], dict[str, str]]:
    codes: list[str] = out["codes"]
    sems: list[Any] = []
    profiles: dict[tuple[str, int], Any] = {}
    digests: dict[str, str] = {}
    for ref in item.profiles:
        profile = PROFILES.get(ref)
        if profile is None:
            codes.append(f"sem.profile_unavailable:{ref}")
            continue
        sem = annotate(doc, profile)
        report = validate_sem_document(sem, doc, mode="release", profile=profile)
        for check, status in tier3_checks(report, ref).items():
            out["checks"][check] = status
        if report.skipped:
            codes.append(f"d8.sem.skipped:{ref}")
        if not (report.ok and not report.errors and not report.skipped):
            codes.append(f"d8.sem:{ref}")
        sems.append(sem)
        profiles[(profile.id, profile.version)] = profile
        digests[ref] = sem.digest
    return sems, profiles, digests


def _compare_stored(item: WorkItem, out: dict[str, Any], prov_sha: str, sem_digests: dict[str, str]) -> None:
    """Whether the re-derived outputs equal the index row's digests (informational: a catalogue or code bump that the
    regeneration batch has not applied yet shows here, and is not a gate-D failure)."""
    if item.row is None:
        return
    stored_prov = (item.row.prov or {}).get(SPEC_ID)
    out["stored"]["prov"] = None if stored_prov is None or stored_prov.digest is None else stored_prov.digest == prov_sha
    stored_sem = item.row.sem or {}
    out["stored"]["sem"] = (
        None if not stored_sem else all(s.digest == sem_digests.get(ref) for ref, s in stored_sem.items())
    )


def _statement_count(result: ProvDerivation) -> int:
    bundles = result.document.get("bundle") or {}
    return sum(len(items) for body in bundles.values() for items in body.values() if isinstance(items, dict))


# -------------------------------------------------------------------------------------------- the dedicated checks


def _types(body: dict[str, Any]) -> set[str]:
    value = body.get("prov:type", [])
    found = value if isinstance(value, list) else [value]
    return {str(v["$"]) for v in found if isinstance(v, dict) and "$" in v}


def _time_value(value: Any) -> Any:
    return value.get("$") if isinstance(value, dict) else value


def _exempt_generic(key: str, attrs: Mapping[str, Any], exempt: set[str]) -> bool:
    """A G-ACT/G-USE/G-ASSOC statement about an exempt activity (:data:`EXEMPT_ACTIVITY_TYPES`): the activity element
    itself (key ``x:<id>``), or a relation whose ``prov:activity`` is it."""
    nodes = {"x:" + a for a in exempt}
    return key in nodes or attrs.get("prov:activity") in nodes


def _dedicated(result: ProvDerivation, doc: AerDocument, codes: list[str], *, v1: bool, migration: bool) -> dict[str, int]:
    """The J.3.5 never-emit checks and the PROV-side counts of one execution. Appends failure codes, returns metrics."""
    rules = load_spec().rules
    info = {b.iri: b for b in result.bundles}
    bundles: dict[str, dict[str, Any]] = dict(result.document.get("bundle") or {})
    types: dict[str, set[str]] = {}
    activities: set[str] = set()
    entities: set[str] = set()
    for body in bundles.values():
        for section in _NODES:
            for key, attrs in (body.get(section) or {}).items():
                types.setdefault(key, set()).update(_types(attrs))
        activities.update(body.get("activity") or {})
        entities.update(body.get("entity") or {})

    typed_times = {
        prov_time(r["t"][end]) for r in doc.records if isinstance(r.get("t"), dict) for end in ("start", "end") if end in r["t"]
    } - {None}
    lexical = {v for r in doc.records if isinstance(r.get("t"), dict) for v in r["t"].values() if isinstance(v, str)}

    found: Counter[str] = Counter()
    gen_result_te = 0
    gen_message_by_entity: dict[str, set[str]] = {}
    request_members: Counter[str] = Counter()
    generic_statements = 0
    statements = 0
    exempt = {str(r.get("id")) for r in doc.records
              if r.get("k") == "activity" and r.get("type") in EXEMPT_ACTIVITY_TYPES}
    for iri, body in bundles.items():
        bundle = info.get(iri)
        kind = bundle.kind if bundle is not None else "unknown"
        methods = set(bundle.methods) if bundle is not None else set()
        for section, items in body.items():
            if not isinstance(items, dict):
                continue
            for key, attrs in items.items():
                if not isinstance(attrs, dict):
                    continue
                statements += 1
                rule = attrs.get("apv:rule")
                if section in _ROUTING and (not isinstance(rule, str) or rule not in rules):
                    found["ne.relation_without_rule"] += 1
                if isinstance(rule, str) and rule in GENERIC_RULES and not _exempt_generic(key, attrs, exempt):
                    generic_statements += 1
                _time_checks(section, attrs, typed_times, lexical, found)
                if section == "wasInformedBy":
                    if rule != "aprov.comm@1" or not attrs.get("apv:premise") or kind not in ("core", "inference"):
                        found["ne.informed_by"] += 1
                elif section == "used":
                    target, user = str(attrs.get("prov:entity")), str(attrs.get("prov:activity"))
                    if target in activities or (isinstance(target, str) and target not in entities):
                        found["ne.activity_used"] += 1
                    if "apv:ToolExecution" in types.get(user, set()):
                        own = rule == "aprov.use_request@1" and "apv:ToolCallRequest" in types.get(target, set())
                        if not (own or rule == "aprov.env_call@1"):
                            found["ne.tool_execution_usage"] += 1
                    inferred = (attrs.get("apv:evidenceClass") or {}).get("$") == "apv:Inferred"
                    if v1 and rule == "aprov.use_context@1" and not (
                        kind == "inference" and _CONTEXT_METHOD in methods and inferred
                    ):
                        found["ne.context_membership_in_core"] += 1
                elif section == "wasGeneratedBy":
                    act, ent = str(attrs.get("prov:activity")), str(attrs.get("prov:entity"))
                    if rule == "aprov.gen_result@1" and "apv:ToolExecution" in types.get(act, set()):
                        gen_result_te += 1
                    if rule == "aprov.gen_message@1":
                        gen_message_by_entity.setdefault(ent, set()).add(act)
                elif section == "mentionOf":
                    if attrs.get("prov:specificEntity") not in entities or attrs.get("prov:generalEntity") not in entities:
                        found["ne.mention_not_entity"] += 1
                elif section == "hadMember":
                    collection, member = str(attrs.get("prov:collection")), str(attrs.get("prov:entity"))
                    held = types.get(collection, set())
                    if "prov:Collection" not in held or "apv:AssistantMessage" not in held:
                        found["ne.request_collection"] += 1
                    if "apv:ToolCallRequest" in types.get(member, set()):
                        request_members[member] += 1
    requests = {k for k, v in types.items() if "apv:ToolCallRequest" in v}
    if any(request_members[r] != 1 for r in requests):
        found["ne.request_membership"] += 1
    if migration:
        if generic_statements or (not exempt and not GENERIC_RULES.isdisjoint(result.report.rules_fired)):
            found["ne.generic_statement"] += 1
        if any(r.get("k") in ("activity", "artefact") and str(r.get("id")) not in exempt for r in doc.records):
            found["ne.generic_record"] += 1
    codes.extend(sorted(found))

    invocations = {a for e, acts in gen_message_by_entity.items() if "apv:AssistantMessage" in types.get(e, set()) for a in acts}
    if not all("apv:ModelInvocation" in types.get(a, set()) for a in invocations):
        codes.append("xc.invocation_type")
    return {
        "te_prov": sum(1 for v in types.values() if "apv:ToolExecution" in v),
        "req_prov": len(requests),
        "unexec_prov": sum(1 for r in requests if _dispatch(bundles, r) == "apv:NotDispatched"),
        "inv_prov": len(invocations),
        "user_prov": sum(1 for v in types.values() if "apv:UserMessage" in v),
        "system_prov": sum(1 for v in types.values() if "apv:SystemMessage" in v),
        "gen_result_te": gen_result_te,
        "generic_statements": generic_statements,
        "statements": statements,
    }


def _dispatch(bundles: dict[str, dict[str, Any]], request: str) -> str | None:
    for body in bundles.values():
        attrs = (body.get("entity") or {}).get(request)
        if isinstance(attrs, dict) and "apv:dispatchStatus" in attrs:
            value = attrs["apv:dispatchStatus"]
            return str(value.get("$")) if isinstance(value, dict) else None
    return None


def _time_checks(section: str, attrs: dict[str, Any], typed: set[Any], lexical: set[str], found: Counter[str]) -> None:
    for key in _TIME_KEYS:
        if key not in attrs:
            continue
        value = _time_value(attrs[key])
        if section != "activity":
            found["ne.time_on_relation" if section not in _NODES else "ne.time_on_non_activity"] += 1
        elif value in ("0", "", 0):
            found["ne.time_sentinel"] += 1
        elif value not in typed:
            found["ne.time_untyped"] += 1
    for key in _LEXICAL_KEYS:
        if key not in attrs:
            continue
        value = _time_value(attrs[key])
        if value in ("0", "", 0):
            found["ne.time_sentinel"] += 1
        elif section != "activity" or value not in lexical:
            found["ne.time_untyped"] += 1


def _environment_loads_expected(doc: AerDocument) -> int:
    """The ``agentdojo:load_environment`` activities a migration AER must hold (regeneration-batch item 5, D-370), derived
    from the execution itself: one when the TraceLogger mapper recorded at least one ``injection_payload`` fixture (the
    suite loaded the environment with the run's injections), else none. Never a hand-set total."""
    adapter = doc.header.get("adapter")
    if not (isinstance(adapter, dict) and adapter.get("id") == "agentdojo.tracelogger"):
        return 0
    return 1 if any(f.get("kind") == "injection_payload" for f in doc.of_kind("fixture")) else 0


def _cross_counts(doc: AerDocument, m: dict[str, int], codes: list[str]) -> None:
    """The per-execution half of the J.3.5 invariants: the PROV counts equal the AER's (J.3.5 table; golden gate D)."""
    messages = doc.of_kind("message")
    roles = Counter(str(x.get("role")) for x in messages)
    executions = doc.of_kind("tool_execution")
    calls = {
        f"{x['id']}#{k}"
        for x in messages
        for k, p in enumerate(x.get("parts") or [])
        if isinstance(p, dict) and p.get("t") == "tool_call"
    }
    executed = {x["call"] for x in executions if "call" in x}
    listed = {
        i for issue in (doc.seal.get("issues") or []) if issue.get("code") == "unexecuted_tool_call" for i in issue.get("ids", [])
    }
    generated = [x for x in messages if x.get("role") == "assistant" and "generated_by" in x]
    activities = doc.of_kind("activity")
    env_load = sum(1 for a in activities if a.get("type") in EXEMPT_ACTIVITY_TYPES)
    m.update(
        te_aer=len(executions), req_aer=len(calls), unexec_aer=len(calls - executed), unexec_listed=len(listed),
        inv_aer=len(generated), user_aer=roles["user"], system_aer=roles["system"],
        zero_te=1 if not executions else 0,
        # J.3.5's activity count is of the v2.3 kinds: the exempt environment load (item 5) is counted apart, against
        # its derived expectation, so the table keeps its 0 and the exemption is still checked execution by execution
        activity_records=len(activities) - env_load, artefact_records=len(doc.of_kind("artefact")),
        env_load_activities=env_load, env_load_expected=_environment_loads_expected(doc),
    )  # fmt: skip
    if m["env_load_activities"] != m["env_load_expected"]:
        codes.append("xc.environment_load")
    if m["te_prov"] != m["te_aer"]:
        codes.append("xc.tool_executions")
    if m["req_prov"] != m["req_aer"]:
        codes.append("xc.requests")
    if not m["unexec_prov"] == m["unexec_aer"] == m["unexec_listed"] or listed != calls - executed:
        codes.append("xc.unexecuted")
    if not m["inv_prov"] == m["inv_aer"] == len({x["generated_by"] for x in generated}):
        codes.append("xc.model_invocations")
    if m["user_prov"] != m["user_aer"] or m["system_prov"] != m["system_aer"]:
        codes.append("xc.messages")
    if m["gen_result_te"] != m["te_aer"]:
        codes.append("xc.gen_result")
