"""Typed views of the 13 AER record kinds and the closed vocabularies of ``aer/0.1`` (C.2.4, C.3).

The ``TypedDict`` classes mirror the field tables of C.3 for static checking and documentation; the
authoritative contract is the validator (:mod:`agentprov.aer.validate`) and the published JSON Schema. Records
are plain ``dict`` objects at run time (they come from JSON).

The vocabularies below are the *single* in-code definition of each closed list of section C; the validator, the
writer and the accounting module read them from here. Every one is a ``frozenset`` or an ordered ``tuple``, so
nothing depends on set iteration order for any output.
"""

from __future__ import annotations

from typing import Final, NotRequired, TypedDict

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]

# ------------------------------------------------------------------------------------------------ vocabularies
#: Evidence parties for a bare ``O`` (C.6.2).
PARTIES: Final = frozenset({"capture", "source", "provider", "benchmark", "config", "replay"})
#: Evidence classes, strongest first (C.6.1).
EVIDENCE_CLASSES: Final = ("O", "D", "I")
#: The seven unknown reasons in the order of C.7.1 (the order breaks ties for "the first reason").
UNKNOWN_REASONS: Final = (
    "not_recorded",
    "lost",
    "overwritten",
    "withheld",
    "ambiguous",
    "not_captured",
    "not_applicable",
)
UNKNOWN_REASON_SET: Final = frozenset(UNKNOWN_REASONS)
AFTER_BASES: Final = frozenset({"causal", "time", "pos", "proto"})
MODES: Final = frozenset({"import", "live"})
UNITS: Final = frozenset({"agent_execution", "outcome_only", "scenario"})
ARTEFACT_ROLES: Final = frozenset({"primary", "capture_log", "native_log", "supporting"})
PROV_PRIMARY: Final = frozenset({"native", "byte_derived", "secondary", "unknown"})
ORIGIN_KINDS: Final = frozenset({"git", "hf", "zenodo", "url", "corpus", "capture", "member", "local"})
ORIGIN_MEMBER_METHODS: Final = frozenset({0, 8, 93})
INSTRUMENTATION_KINDS: Final = frozenset(
    {"behaviour_preserving", "request_modifying", "harness_policy", "attack_parameter", "test_only"}
)
INSTRUMENTATION_RECORDED: Final = frozenset({"full", "summary", "none"})
RELATIONS: Final = frozenset({"supersedes", "superseded_by", "replays", "duplicate_of"})
ACTOR_KINDS: Final = frozenset(
    {
        "llm_agent",
        "user",
        "simulated_user",
        "attacker",
        "defense",
        "judge",
        "tool_runtime",
        "environment",
        "harness",
        "benchmark",
        "other",
    }
)
SCOPE_KINDS: Final = frozenset({"run", "attempt", "agent_invocation", "subagent", "thread", "other"})
SCOPE_STATUS: Final = frozenset({"ok", "error", "aborted", "limit"})
PART_TYPES: Final = frozenset(
    {"text", "reasoning", "tool_call", "tool_result", "blob", "file", "uri", "refusal", "other"}
)
MODEL_CALL_ROLES: Final = frozenset({"agent", "auxiliary"})
MODEL_CALL_STATUS: Final = frozenset({"kept", "discarded", "error", "cached"})
SENT_TRANSFORMS: Final = frozenset(
    {"error_substitution", "role_rewrite", "reasoning_passback", "formatting", "truncation", "other"}
)
TOOL_EXECUTION_STATUS: Final = frozenset({"ok", "error", "invalid"})
DECISION_VERDICTS: Final = frozenset({"allow", "deny", "modify", "redact", "escalate", "terminate", "other"})
STATE_TARGETS: Final = frozenset({"environment", "agent_store", "sandbox", "other"})
FIXTURE_KINDS: Final = frozenset(
    {
        "injection_payload",
        "attack_plan",
        "task_prompt",
        "system_prompt",
        "tool_definitions",
        "environment_seed",
        "ground_truth",
        "other",
    }
)
JUDGEMENT_ORIGINS: Final = frozenset({"checker", "harness_default", "harness_rule", "recomputed"})
ACTIVITY_STATUS: Final = frozenset({"ok", "error", "aborted"})
DUR_CLOCKS: Final = frozenset({"wall", "monotonic"})
ACCOUNTING_VERDICTS: Final = ("consistent", "unverifiable", "inconsistent")  # weakest to strongest finding
JSON_PATCH_OPS: Final = frozenset({"add", "remove", "replace", "move", "copy", "test"})

#: Core seal issue codes (C.12.3, single closed list).
CORE_ISSUE_CODES: Final = frozenset(
    {
        "unparseable_artefact",
        "unsupported_variant",
        "adapter_defect",
        "ex_conflict",
        "identity_unresolved",
        "identity_conflict",
        "earlier_attempts_unobservable",
        "retry_passes_inferred",
        "no_execution_observed",
        "incomplete_run",
        "aborted_attempt",
        "unexecuted_tool_call",
        "missing_tool_result",
        "orphan_tool_result",
        "call_result_link_conflict",
        "unattributed_additional_user_message",
        "missing_generated_by",
        "outcome_imposed_by_runner",
        "no_outcome_recorded",
        "accounting_inconsistent",
        "accounting_unverifiable",
        "live_native_divergence",
        "capture_error",
        "capture_unsealed",
        "capture_redaction",
        "dangling_source_ref",
    }
)

#: Ext prefixes that are never declarable or usable as ``activity``/``artefact``/``subtype`` namespaces (C.10).
RESERVED_PREFIXES: Final = frozenset({"lex", "aer", "sem", "apv", "cap"})
#: ``activity.type`` names that belong to a specialised kind (C.3.13 / K.5.1 item 7).
SPECIALISED_KIND_NAMES: Final = frozenset(
    {"message", "model_call", "tool_execution", "decision", "state_change", "fixture", "judgement"}
)

# ------------------------------------------------------------------------------------------------ shared types


class Locator(TypedDict, total=False):
    """A source locator (C.9.1): exactly one of the nine member combinations."""

    a: str
    p: str
    bytes: list[int]
    line: int
    o: str
    blob: str


class Time(TypedDict, total=False):
    start: str
    end: str
    start_naive: str
    end_naive: str
    dur_s: float
    dur_clock: str
    mono_start_ns: int
    mono_end_ns: int
    raw: dict[str, str]


class Usage(TypedDict, total=False):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    calls: int


class Model(TypedDict, total=False):
    requested: str
    served: str
    provider: str
    endpoint: str


class Code(TypedDict, total=False):
    dist: str
    dist_version: str
    repo: str
    commit: str
    wheel_sha256: str


BlobRef = TypedDict("BlobRef", {"$blob": str, "bytes": int, "media": NotRequired[str]})


class AfterEdge(TypedDict):
    id: str
    b: str


class Record(TypedDict, total=False):
    """The envelope of C.2.2 plus ``k``-specific members (kept as ``Json`` here; see the per-kind classes)."""

    k: str
    id: str
    ev: str
    by: str
    evf: dict[str, str]
    rule: list[str]
    src: list[Locator]
    unk: dict[str, str]
    after: list[AfterEdge]
    ext: dict[str, dict[str, Json]]


class Task(TypedDict, total=False):
    benchmark: str
    suite: str
    environment: str
    task_id: str
    attack_id: str | None
    attack_target_id: str | None
    defense_id: str | None


class Instrumentation(TypedDict, total=False):
    id: str
    kind: str
    recorded: str
    params: Json
    detail: str
    code_ref: dict[str, str]


class Artefact(TypedDict):
    """A raw-artefact descriptor of ``execution.artifacts`` (not the record kind ``artefact``)."""

    id: str
    role: str
    prov_primary: str
    sha256: str
    bytes: int
    media: str
    origin: dict[str, Json]


class ExecutionRecord(Record, total=False):
    aer: str
    ex: str
    mode: str
    unit: str
    source_key: dict[str, Json]
    artifacts: list[Artefact]
    adapter: dict[str, str]
    dialect: dict[str, str]
    profile: dict[str, Json]
    rules: dict[str, int]
    ns: dict[str, str]
    canon: str
    hash: str
    capture: dict[str, Json]
    related: list[dict[str, str]]
    task: Task
    instrumentation: list[Instrumentation]


class ActorRecord(Record, total=False):
    kind: str
    subtype: str
    name: str
    role: str
    model: Model
    params: Json
    version: str
    code: Code
    on_behalf_of: str


class ScopeRecord(Record, total=False):
    kind: str
    subtype: str
    parent: str
    actor: str
    index: int
    scored: bool
    spawned_by: str
    t: Time
    status: str
    usage: Usage


class MessageRecord(Record, total=False):
    scope: str
    role: str
    actor: str
    parts: list[dict[str, Json]]
    generated_by: str


class ModelCallRecord(Record, total=False):
    actor: str
    role: str
    scope: str
    input: list[str | dict[str, Json]]
    tools: str
    params: dict[str, Json]
    status: str
    reason: str
    retry_of: str
    finish_reason: str
    usage: Usage
    served_model: str
    response_id: str
    request: BlobRef
    response: BlobRef
    t: Time


class ToolExecutionRecord(Record, total=False):
    actor: str
    scope: str
    call: str
    requested_by: str
    authorised_by: str
    name: str
    args: Json
    args_effective: Json
    status: str
    exception: dict[str, str]
    returned: Json
    t: Time


class DecisionRecord(Record, total=False):
    actor: str
    scope: str
    subject: str
    verdict: str
    subtype: str
    reason: str
    original: str | BlobRef
    t: Time


class StateChangeRecord(Record, total=False):
    scope: str
    cause: str
    target: str
    subtype: str
    canon: str
    before_sha256: str
    after_sha256: str
    changed: bool
    patch: list[dict[str, Json]]
    diff: dict[str, Json]
    snapshot_before: BlobRef
    snapshot_after: BlobRef
    t: Time


class FixtureRecord(Record, total=False):
    kind: str
    subtype: str
    vector: str
    content: Json
    media: str
    actor: str


class JudgementRecord(Record, total=False):
    actor: str
    subject: str
    name: str
    value: Json
    origin: str
    revises: str
    generated_by: str
    inputs: list[str]
    t: Time


class ActivityRecord(Record, total=False):
    type: str
    actor: str
    scope: str
    inputs: list[str]
    t: Time
    status: str
    label: str


class ArtefactRecord(Record, total=False):
    type: str
    content: Json
    content_ref: BlobRef
    sha256: str
    media: str
    generated_by: str


class Check(TypedDict):
    id: str
    scope: str
    verdict: str
    observed: dict[str, int]
    reason: NotRequired[str]


class Issue(TypedDict):
    code: str
    ids: list[str]
    rule: str
    detail: NotRequired[str]


class SealRecord(TypedDict):
    k: str
    id: str
    n_records: int
    records_sha256: str
    accounting: dict[str, Json]
    issues: list[Issue]
    blobs: NotRequired[list[str]]


#: The kind-specific TypedDicts, by record kind (documentation and static typing only).
RECORD_TYPES: Final[dict[str, type]] = {
    "execution": ExecutionRecord,
    "actor": ActorRecord,
    "scope": ScopeRecord,
    "message": MessageRecord,
    "model_call": ModelCallRecord,
    "tool_execution": ToolExecutionRecord,
    "decision": DecisionRecord,
    "state_change": StateChangeRecord,
    "fixture": FixtureRecord,
    "judgement": JudgementRecord,
    "activity": ActivityRecord,
    "artefact": ArtefactRecord,
    "seal": SealRecord,
}
