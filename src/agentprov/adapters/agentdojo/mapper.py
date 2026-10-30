"""Mapper ``agentdojo.tracelogger``: AgentDojo TraceLogger run logs -> AER ``aer/0.1`` (docs/architecture D.6.5-D.6.7).

One AER per file, records in the D.6.5 order: the ``execution`` header, the actors (``bench``, ``user``, ``agent``,
``env``, ``att``, ``def<n>``), the ``run`` and ``att0`` scopes, one fixture per injection payload, the messages with the
activities that generate them (each activity immediately before its message; references point backwards only), and the
two judgements. The normative worked example is C.16.1, which this mapper reproduces byte for byte with the shipped
profile (``tests/adapters/agentdojo/test_mapper.py``). Implementation choices the spec leaves open are recorded in
D.6.11.

Mapped variants (D.6.2): ``v0.k11`` (phase 6) and ``v1.k14`` / ``v1.k14.incomplete`` (phase 10; phase 8 mapped them for
the live-versus-native check only), each only where the profile declares it (``[import] variants``, or ``[import]
native.variants`` of a live profile). Every other recognised variant raises :class:`~agentprov.errors.UnsupportedVariant`,
so the runner seals a degenerate AER with ``unsupported_variant`` (D.2.8 case 3).

Profile-driven behaviour (D.6.12): the layout and its facets (:mod:`~agentprov.adapters.agentdojo.layout`), the identity
mode (:mod:`~agentprov.adapters.agentdojo.identity`), the benchmark of each suite and the meaning of the ``v1.k14``
version label (``version_label_semantics``), the retry semantics, the system-prompt variant labels, the quirks, and
which D rules are cited at D: a D rule of the family is cited for a log only where the profile's ``[harness]
verified_code`` lists a commit its catalogue ``code`` cites, else through its ``_unverified`` twin (D.5.4, D-24;
:mod:`~agentprov.adapters.agentdojo.citation`). Every record is then weakened to the class of the rules that justify it
(C.6.5 rule 1, :func:`~agentprov.adapters.code_verification.weaken_to_rule_class`), so a twin moves its statements into
the inference bundles. Seal issues cite the rule they name as given, except where they report the reading of a statement
(the retry and run-error rules), which they cite as the statement does. Source-specific quirks run through the hooks of
:mod:`~agentprov.adapters.agentdojo.quirks`.

Lexical hints (C.11.4) are mandatory here while ``render_converted`` is a migration gate: every object and number copied
from the log (payloads, message text, call ``args``, the embedded ``tool_call`` args, ``duration``) is encoded through
:func:`agentprov.aer.canon.encode_value`, which records ``ext.lex`` at the pointer where the value lands.

Pure (A-2): the output is a function of the unit's bytes and origin, this code, the profile and the catalogues. The
mapper never raises for the content of an in-scope file except :class:`~agentprov.errors.MalformedArtefact` (a
structural key of the wrong type) and :class:`~agentprov.errors.UnsupportedVariant`; everything else is mapped as far as
it goes and reported through seal issues (D.2.8).
"""

from __future__ import annotations

import datetime
import fnmatch
import hashlib
import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, Final, Literal, NamedTuple, TypeGuard

from agentprov.adapters.agentdojo import quirks as quirk_hooks
from agentprov.adapters.agentdojo.citation import citations
from agentprov.adapters.agentdojo.history_table import origin_introduced_under
from agentprov.adapters.agentdojo.dialect import DIALECT_ID, FLAG_MALFORMED, MAPPED_VARIANTS
from agentprov.adapters.agentdojo.identity import Identity, resolve
from agentprov.adapters.agentdojo.profile import FamilyTable, family_table
from agentprov.adapters.agentdojo.redact import NAMESPACE as REDACT_NS
from agentprov.adapters.agentdojo.redact import NAMESPACE_IRI as REDACT_NS_IRI
from agentprov.adapters.agentdojo.redact import RULE as R_REDACTED
from agentprov.adapters.agentdojo.redact import Redactor, parse_redact_rules, redact_value
from agentprov.adapters.agentdojo.quirks import (
    BatchIntervention,
    CallBatch,
    HookView,
    InputNotLogged,
    LogEnd,
    MessageAuthor,
    OrphanRequest,
    QuirkHook,
    TextMessage,
    ToolDecision,
    ToolMessage,
    UserAuthor,
    UserMessage,
)
from agentprov.adapters.code_verification import weaken_to_rule_class
from agentprov.adapters.environment_load import environment_load
from agentprov.adapters.surrogates import scrub_keys, surrogates
from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import MalformedArtefact, UnsupportedVariant

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "NAMESPACES", "TraceLoggerMapper", "declared_variants",
           "tool_status"]

ADAPTER_ID: Final = "agentdojo.tracelogger"
ADAPTER_VERSION: Final = "0.1.0"
#: Catalogues this mapper cites; the header lists them at the shipped versions (C.3.1 ``rules``).
CATALOGUES: Final = ("aer", "agentdojo")
NAMESPACES: Final = {"agentdojo": "https://w3id.org/agentprov/ns/agentdojo#"}
#: The PI-detector replacement text (pi_detector.py l. 46 at c274885); the profile's quirk params take precedence.
DEFAULT_SENTINEL: Final = "<Data omitted because a prompt injection was detected>"
_INVALID_PREFIXES: Final = ("Empty function name provided", "Invalid tool ")
#: The C.7.3 deny-list: a source value in it never enters a typed field.
_SENTINELS: Final = frozenset({"", "0", "unknown", "none", "null", "n/a", "na", "-"})


def _placeholder(value: str) -> bool:
    """A C.7.3 deny-listed string (``none``, ``unknown``, ``-``, ...): never a value of a typed slot (AER-V17)."""
    return value.strip().lower() in _SENTINELS


def _usable(value: object) -> TypeGuard[str]:
    """A non-empty string that is no placeholder: usable in a typed header slot (regeneration-batch item 88, CD-11)."""
    return isinstance(value, str) and bool(value) and not _placeholder(value)


def _ambiguous_tool_names(records: Sequence[dict[str, Any]]) -> None:
    """Regeneration-batch item 87 (CD-10), as the Inspect mapper's BF-22: a tool whose real name is on the C.7.3
    deny-list (a model may call ``none``) keeps its verbatim name, declared ``unk ambiguous`` (C.7.2(2)), instead of
    failing AER-V17 and collapsing the log into an ``adapter_defect`` AER."""
    for rec in records:
        pointers: list[str] = []
        if rec.get("k") == "tool_execution" and isinstance(rec.get("name"), str) and _placeholder(rec["name"]):
            pointers.append("/name")
        if rec.get("k") == "message":
            for k, part in enumerate(rec.get("parts") or ()):
                if (isinstance(part, dict) and part.get("t") in ("tool_call", "tool_result")
                        and isinstance(part.get("name"), str) and _placeholder(part["name"])):
                    pointers.append(f"/parts/{k}/name")
        if pointers:
            unk = rec.setdefault("unk", {})
            for pointer in pointers:
                unk.setdefault(pointer, "ambiguous")


_BLOCK_KEYS: Final = frozenset({"type", "content"})


class BlockParts(NamedTuple):
    """The parts of one content value, the indices of its null-content text blocks, and its number of unknown blocks."""

    parts: list[dict[str, Any]]
    null_text_blocks: list[int]
    unknown: int


def content_block_parts(content: object, base: int, enc: Callable[[object, str], Any]) -> BlockParts:
    """R-CONTENT: ``null`` -> one null text part; a string -> one text part; blocks -> one part per block. Shared by the
    TraceLogger and capture mappers, so both read content identically (``enc(value, pointer)`` is the record's encoder).

    A block is ``{type, content}`` (AgentDojo's content blocks; a thinking block may carry ``id``, the provider's
    signature). Regeneration-batch items 90 and 77 (core reviews CD-13, CD-14, CA-19): a text or thinking block of any
    other key set, or whose content is neither a string nor null, is kept verbatim as an ``other`` part, and counted in
    ``unknown`` (the caller raises ``agentdojo.unknown_message_shape`` once per such block), never truncated; a thinking
    ``id`` is the reasoning part's ``signature``; a text block whose content is null is a null text part whose index the
    caller writes to ``ext.agentdojo.null_text_blocks`` (so it is not read as ``content: null``, D.6.6)."""
    if content is None:
        return BlockParts([{"t": "text", "text": None}], [], 0)
    if isinstance(content, str):
        return BlockParts([{"t": "text", "text": enc(content, f"/parts/{base}/text")}], [], 0)
    parts: list[dict[str, Any]] = []
    null_blocks: list[int] = []
    unknown = 0
    for block in content if isinstance(content, list) else ():
        k = base + len(parts)
        kind, keys, body = block.get("type"), set(block), block.get("content")
        readable = body is None or isinstance(body, str)
        if kind == "text" and keys == _BLOCK_KEYS and readable:
            parts.append({"t": "text", "text": enc(body, f"/parts/{k}/text")})
            if body is None:
                null_blocks.append(k)
        elif (kind == "thinking" and keys in (_BLOCK_KEYS, _BLOCK_KEYS | {"id"}) and readable
              and (block.get("id") is None or isinstance(block["id"], str))):
            part = {"t": "reasoning", "text": enc(body, f"/parts/{k}/text")}
            if isinstance(block.get("id"), str):
                part["signature"] = enc(block["id"], f"/parts/{k}/signature")
            parts.append(part)
        elif kind == "redacted_thinking":
            parts.append({"t": "reasoning", "text": None, "redacted": True})
        else:
            parts.append({"t": "other", "type": "agentdojo.unknown_block", "value": enc(block, f"/parts/{k}/value")})
            unknown += 1
    return BlockParts(parts, null_blocks, unknown)


def run_duration(run: _Rec, duration: object) -> tuple[dict[str, Any], dict[str, str]]:
    """``(t, unk)`` of the run scope from the logged ``duration`` (a ``time.time()`` difference, wall clock).
    Regeneration-batch item 96 (R-10j-4): a negative value (the clock went backwards) is no duration (C.8.3 ``dur_s >= 0``):
    it stays verbatim in ``t.raw.dur`` (its JSON lexical form), declared ``ambiguous``, so the log can still be sealed."""
    if isinstance(duration, int | float) and not isinstance(duration, bool) and duration < 0:
        return {"raw": {"dur": json.dumps(duration)}}, {"/t/dur_s": "ambiguous"}
    return {"dur_s": run.enc(duration, "/t/dur_s"), "dur_clock": "wall"}, {}


def _real_naive(value: str) -> bool:
    """A calendar-valid naive date and time (``fromisoformat`` takes any number of fractional digits)."""
    try:
        datetime.datetime.fromisoformat(value)
    except ValueError:
        return False
    return True

_NAIVE_TS: Final = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2}) ([0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?)")
_MODEL_CALL_UNKNOWN: Final = ("/finish_reason", "/params", "/request", "/response", "/t", "/tools", "/usage")
_CALL_KEYS: Final = frozenset({"function", "args", "id", "placeholder_args"})
_SHAPES: Final = {
    "system": frozenset({"role", "content"}),
    "user": frozenset({"role", "content"}),
    "assistant": frozenset({"role", "content", "tool_calls"}),
    "tool": frozenset({"role", "content", "tool_call_id", "tool_call", "error"}),
}
#: The rule a detected quirk's issue cites (``agentdojo.undeclared_quirk``; D.6.4).
_QUIRK_RULES: Final = {
    "agentdojo.benign_security_constant": "agentdojo.benign_security_constant@1",
    "agentdojo.dos_security_not_utility": "agentdojo.dos_security_rule@1",
    "agentdojo.silent_rerun_last_pass_only": "agentdojo.null_final_implies_three_passes@1",
    "agentdojo.injection_task_as_user_task_prepass": "agentdojo.injection_task_as_user_task@1",
    "agentdojo.empty_messages_with_outcome": "agentdojo.no_execution_observed@1",
    "agentdojo.empty_messages_without_outcome": "agentdojo.no_execution_observed@1",
    "agentdojo.run_error_imposes_outcome": "agentdojo.run_error_imposed_outcome@1",
    "agentdojo.incomplete_run": "agentdojo.incomplete_run@1",
    "agentdojo.provider_call_id_anomalies": "agentdojo.positional_match@1",
    "agentdojo.unexecuted_trailing_calls": "agentdojo.unexecuted_trailing_calls@1",
    "agentdojo.pi_detector_redaction": "agentdojo.pi_detector_sentinel@1",
    "agentdojo.tool_filter_aux_llm": "agentdojo.tool_filter_aux_message@1",
    "agentdojo.repeat_user_prompt_reinsertion": "agentdojo.repeat_user_prompt_copy@1",
    "agentdojo.spotlighting_delimiters": "agentdojo.spotlighting_content@1",
}
#: Defence id -> the quirk whose declaration activates its D.6.6 rows.
_DEFENCE_QUIRKS: Final = {
    "tool_filter": "agentdojo.tool_filter_aux_llm",
    "repeat_user_prompt": "agentdojo.repeat_user_prompt_reinsertion",
    "spotlighting_with_delimiting": "agentdojo.spotlighting_delimiters",
    "transformers_pi_detector": "agentdojo.pi_detector_redaction",
    "piguard_detector": "agentdojo.pi_detector_redaction",
    "prompt_guard_2_detector": "agentdojo.pi_detector_redaction",
}
#: The defences whose replacement of a tool output by the sentinel the PI-detector row (D.6.6) reads, unless the quirk's
#: ``params.defences`` names others. AgentDyn's PIGuard and PromptGuard 2 detectors share ``PromptInjectionDetector.transform``.
_DEFAULT_DETECTORS: Final = ("transformers_pi_detector",)
#: The retry rule each ``[harness] retry_semantics`` value is cited under (D.6.5 Step 3).
_RETRY_RULES: Final = {
    "agentdojo.final_content_none_max3": "agentdojo.null_final_implies_three_passes@1",
    "agentdyn.last_assistant_content_none_max3": "agentdyn.last_assistant_content_none_max3@1",
}


#: The 14-key variant written by AgentDojo >= 0.1.30 (D.6.2).
V1_K14: Final = "v1.k14"
#: The tag a local model's raw completion writes per tool call (``agentdojo.local_model_tag_count@1``; issue #202).
_LOCAL_TAG: Final = "<function="
_LOCAL_QUIRK: Final = "agentdojo.local_model_raw_completion"


def declared_variants(profile: Any) -> frozenset[str]:
    """The TraceLogger variants ``profile`` maps (D.6.12 item 1): its ``[import] variants`` and, for a **live** profile,
    the variants of the native log of its sessions (``[import] native.variants``, D.10.4a)."""
    imp = profile.data.get("import", {}) if hasattr(profile, "data") else {}
    native = imp.get("native")
    variants = [*imp.get("variants", ()), *(native.get("variants", ()) if isinstance(native, Mapping) else ())]
    return frozenset(str(v) for v in variants)


def tool_status(error: object) -> str:
    """``agentdojo.tool_status_from_error@1``."""
    if error is None:
        return "ok"
    text = str(error)
    if text.startswith("ValidationError") or text.startswith(_INVALID_PREFIXES):
        return "invalid"
    return "error"


def _loc(pointer: str) -> dict[str, Any]:
    return {"a": "a0", "p": pointer}


def single_text_block(content: object) -> str | None:
    """The text of a content list holding exactly one ``{"type": "text", "content": <str>}`` block, else ``None``.

    AgentDojo >= 0.1.30 writes every tool result as ``[text_content_block_from_string(formatted)]``
    (``tool_execution.py`` l. 76-113 at 0.1.35); its text is the tool output the model sees (D.10.4a)."""
    if isinstance(content, list) and len(content) == 1:
        block = content[0]
        if isinstance(block, dict) and set(block) == {"type", "content"} and block.get("type") == "text" \
                and isinstance(block.get("content"), str):
            return str(block["content"])
    return None


_ORIGIN_PATH: Final = {"a": "a0", "o": "/path"}
#: A ``member`` origin (an archive member, C.3.12) carries the member name as ``label``, which the layout reads (D-156).
_ORIGIN_LABEL: Final = {"a": "a0", "o": "/label"}


def _lexical(value: object) -> str:
    """The lexical form of a JSON value: member order and int/float typing kept (D.6.6.1 "equal with their hints")."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class _Rec:
    """A record under construction: fields plus its lexical hints."""

    def __init__(self, **fields: Any) -> None:
        self.data: dict[str, Any] = dict(fields)
        self.lex = LexHints()

    def enc(self, value: object, pointer: str) -> Any:
        return encode_value(value, at=pointer, lex=self.lex)

    def ext(self) -> dict[str, Any]:
        ext = self.data.setdefault("ext", {})
        agentdojo: dict[str, Any] = ext.setdefault("agentdojo", {})
        return agentdojo

    def done(self) -> dict[str, Any]:
        out = dict(self.data)
        if self.lex:
            ext = dict(out.get("ext") or {})
            ext["lex"] = self.lex.as_dict()
            out["ext"] = ext
        return out


#: The DRIFT variants (``drift_mapper.DRIFT_VARIANTS``, spelled here because that module imports this one).
_DRIFT: Final = frozenset({"drift.k18.messages", "drift.k18.conversations"})
#: The results-container dialect and its mapped variants (``results_reader``; D-471, routed edit R-10q-1).
_RESULTS_DIALECT: Final = "agentdojo.results_container"
_RESULTS: Final = frozenset({"rc.k7", "rc.k12"})


class TraceLoggerMapper:
    """``Mapper`` for ``agentdojo.tracelogger`` (D.2.4, D.6.5)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    #: ``v0.k11``/``v1.k14*`` by :class:`_Build`; the DRIFT variants by ``drift_mapper.DriftBuild`` (D-270, regeneration-
    #: batch item 22, RT-1), which has this mapper's id and version, so execution ids do not depend on the class
    accepts: Final = frozenset((DIALECT_ID, v) for v in MAPPED_VARIANTS | _DRIFT) | frozenset((_RESULTS_DIALECT, v) for v in _RESULTS)
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES
    #: The import runner hands this mapper the profile's context artefacts (D.6.12 item 6); quirk hooks may cite them.
    consumes_context: Final = True

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        if unit.primary.dialect == _RESULTS_DIALECT:
            from agentprov.adapters.agentdojo.results_mapper import ResultsBuild  # D-471 (lazy: it imports this module)

            yield from ResultsBuild(unit, ctx).run()
            return
        if unit.primary.variant in _DRIFT:
            from agentprov.adapters.agentdojo.drift_mapper import DriftBuild  # D-270 (lazy: drift_mapper imports this module)

            yield from DriftBuild(unit, ctx).run()
            return
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """Fail closed (R-22): ``unknown`` here; the header says ``native`` when the origin is a pinned publisher
        origin of the profile (D.6.5 Step 1), which only the mapper can see."""
        return "unknown"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3), with its error issue reported through ``ctx``."""
        if unit.primary.dialect == _RESULTS_DIALECT:  # D-471
            from agentprov.adapters.agentdojo.results_mapper import results_degenerate_header

            return results_degenerate_header(unit, ctx, issue_code=issue_code, detail=detail)
        value = unit.primary.value if isinstance(unit.primary.value, dict) else {}
        fam = family_table(ctx.profile)
        facets = {"variant": unit.primary.variant,
                  "introduced_under": origin_introduced_under(fam.history, unit.primary.artefact.origin.to_json())}
        bench_rule = citations(fam, facets).cite("agentdojo.benchmark_from_dialect@1")
        suite_name = value.get("suite_name")
        task: dict[str, Any] = {
            "benchmark": fam.benchmark_of(suite_name) if _usable(suite_name)
            else str(fam.benchmark.get("benchmark", "agentdojo")),
        }
        header: dict[str, Any] = {
            "k": "execution",
            "id": "exec",
            "aer": "0.1",
            "ex": ctx.ex,
            "mode": unit.mode,
            "unit": "agent_execution",
            "source_key": {"sha256": unit.primary.artefact.sha256, "loc": unit.primary.locator.key()},
            "artifacts": [_artefact_json(unit, ctx)],
            "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
            "dialect": {"id": DIALECT_ID, "variant": unit.primary.variant},
            "profile": ctx.profile.header(),
            "rules": ctx.catalogue_versions(CATALOGUES),
            "ns": dict(NAMESPACES),
            "canon": "jcs-rfc8785",
            "hash": "sha256",
            "task": task,
            "ev": "D",
            "rule": [ctx.rule(bench_rule)],
            "unk": {"/instrumentation": "not_recorded"},
        }
        suite, task_id = value.get("suite_name"), value.get("user_task_id")
        # an empty name is no identity; a usable task id is kept even when the suite is not (the core schema requires
        # task.task_id; a header without one is refused and the unit registered failed, raw kept: an open item, D.2.8)
        if _usable(task_id):
            lex = LexHints()
            usable_suite = _usable(suite)
            if usable_suite:
                task["suite"] = encode_value(suite, at="/task/suite", lex=lex)
            task["task_id"] = encode_value(task_id, at="/task/task_id", lex=lex)
            header.update(ev="O", by="config", evf={"/task/benchmark": "D"},
                          rule=[ctx.rule(bench_rule, "/task/benchmark")],
                          src=[*([_loc("/suite_name")] if usable_suite else []), _loc("/user_task_id")])
        else:  # D-219: a map job that failed before reading the value did not capture it (aer/0.2 allows the omission)
            header["unk"]["/task/task_id"] = "not_captured" if unit.primary.value is None else "not_recorded"
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule("agentdojo.tracelogger_record_shape@1"), severity="error",
                  detail=detail)
        # item 105: a degenerate AER names the raw path too (artifacts[0].origin.path), so it is redacted as well
        redactor = Redactor(ctx.profile.id, ctx.profile.version,
                            parse_redact_rules(fam.data.get("redact", ()), f"profile {ctx.profile.id!r}"),
                            {"pipeline_name": observed_pipeline_names(value.get("pipeline_name"), fam,
                                                                      unit.primary.artefact.origin.data)})
        if redact_records(redactor, ctx, header, []):  # the citation's catalogue is declared (C.3.1 rules)
            header["rules"] = ctx.catalogue_versions(sorted(set(header["rules"]) | {REDACT_NS}))
        weaken_to_rule_class(header)
        return header


def observed_pipeline_names(logged: object, fam: FamilyTable, origin: Mapping[str, Any]) -> list[str]:
    """The observed strings of scope ``pipeline_name`` (item 105): the logged name and the raw ``pipeline_dir`` facet of
    the origin path, which D-510 (A) assumes equal. Registering the directory too keeps an account out of
    ``artifacts[].origin.path`` should they ever differ, and covers a degenerate unit with no parsed name."""
    names = [logged] if isinstance(logged, str) and logged else []
    layout = fam.layout
    facets = layout.match(origin.get("path") or origin.get("label")) if layout is not None else None
    raw_dir = (facets or {}).get("pipeline_dir")
    if isinstance(raw_dir, str) and raw_dir and raw_dir not in names:
        names.append(raw_dir)
    return names


def redact_records(redactor: Redactor, ctx: Any, head: dict[str, Any], records: list[dict[str, Any]]) -> int:
    """Apply a profile's redaction (D-476) to the finished records, as ResultsBuild does: each redacted pointer cites
    ``rescont.value_redacted@1``; one info issue per unit counts them; the header names the ``rescont`` namespace."""
    redacted = 0
    for record in (head, *records):
        redacted += len(redactor.apply(record, lambda p: ctx.rule(R_REDACTED, p)))
    if redacted:
        ctx.issue("rescont.value_redacted", ids=["exec"], rule=ctx.rule(R_REDACTED), severity="info", detail=str(redacted))
        head["ns"] = dict(sorted({**head.get("ns", {}), REDACT_NS: REDACT_NS_IRI}.items()))
    return redacted


def _artefact_json(unit: ExecutionUnit, ctx: MappingContext) -> dict[str, Any]:
    """``artifacts[0]`` with ``prov_primary`` per D.6.5 Step 1: ``native`` for a log fetched from one of the profile's
    pinned publisher origins (git commit of the canonical repository, or a pinned DOI), else as given (fail closed)."""
    art = unit.primary.artefact
    out = art.to_json()
    origin = art.origin
    source = ctx.profile.data.get("source", {})
    pins = source.get("pins", ())
    if origin.kind == "git" and origin.data.get("repo") == source.get("canonical_repo"):
        if any(p.get("kind") == "git" and p.get("commit") == origin.data.get("commit") for p in pins):
            out["prov_primary"] = "native"
    elif origin.kind == "zenodo" and any(p.get("kind") == "zenodo" and p.get("doi") == origin.data.get("doi") for p in pins):
        out["prov_primary"] = "native"
    return out


class _Build:
    """One mapping run."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        item = unit.primary
        if FLAG_MALFORMED in item.flags:
            raise MalformedArtefact(f"TraceLogger {item.variant} object without its structural keys")
        if item.variant not in MAPPED_VARIANTS or item.variant not in declared_variants(ctx.profile):
            raise UnsupportedVariant(f"TraceLogger variant {item.variant} is recognised; the profile does not map it")
        if not isinstance(item.value, dict):
            raise MalformedArtefact("the located item is not a TraceLogger object")
        self.unit = unit
        self.ctx = ctx
        self.item = item
        self.doc: dict[str, Any] = item.value
        self.doc, self.surrogate_keys = scrub_keys(self.doc)  # item 7 (F-01, D-378): keys cannot be $utf16-wrapped
        self.fam: FamilyTable = family_table(ctx.profile)
        self.issues: list[tuple[str, list[str], str, str, str | None]] = []
        self.detected: set[str] = set()
        self.cited: dict[str, str] = {}  # context label -> artefact id (a1, a2, ...)
        self.cited_refs: list[dict[str, Any]] = []
        self._read_fields()
        origin = item.artefact.origin.data
        layout = self.fam.layout
        self.path_facets = layout.match(origin.get("path") or origin.get("label")) if layout is not None else None
        facets = dict(self.path_facets or {})
        # regeneration-batch item 105 (D-476, D-510 (A)): a declared pipeline_name redaction rewrites the logged name
        # wherever the AER holds it (also inside artifacts[].origin.path); identity reads the redacted directory label
        # and the redacted name, so identity rows and profile selectors never name an account
        rules = parse_redact_rules(self.fam.data.get("redact", ()), f"profile {ctx.profile.id!r}")
        self.redactor = Redactor(ctx.profile.id, ctx.profile.version, rules,
                                 {"pipeline_name": observed_pipeline_names(self.pipeline_name, self.fam, origin)})
        if rules:  # identity keys hold only labels; an arm path above the directory may hold it too (bug pass NF-2)
            for name in ("pipeline_dir", "model_dir"):
                if isinstance(facets.get(name), str):
                    facets[name] = "/".join(redact_value(rules, "pipeline_name", seg, salt=ctx.profile.id)[0]
                                            for seg in str(facets[name]).split("/"))
        self.facets: dict[str, str | None] = {
            **facets,
            "pipeline_dir": facets.get("pipeline_dir"),
            "attack_dir": facets.get("attack_dir", "none" if self.attack is None else self.attack),
            "task_dir": facets.get("task_dir", self.task_id),
            "suite": facets.get("suite", self.suite),
            "variant": item.variant,
            "introduced_under": origin_introduced_under(self.fam.history, item.artefact.origin.to_json()),  # D-84
        }
        self.ident: Identity = resolve(self.fam.identity, facets, self.redactor.label(self.pipeline_name),
                                       self.fam.rows_for(item.artefact.origin))
        self.cite = citations(self.fam, self.facets)  # D.5.4, D-24: a D rule or its _unverified twin, per log
        self.r_ordered = self.cite.cite("agentdojo.messages_append_ordered@1")
        self.r_one_call = self.cite.cite("agentdojo.assistant_msg_has_one_call@1")
        self.r_one_exec = self.cite.cite("agentdojo.tool_msg_is_one_execution@1")
        self.r_timestamp = self.cite.cite("agentdojo.naive_local_timestamp@1")
        self.benchmark = self.fam.benchmark_of(self.suite)
        # D.6.12 item 7: the hooks of the declared source-specific quirks whose selector matches this file
        registered = quirk_hooks.hooks()
        matched = [(registered[q.id], q) for q in self.fam.quirks if q.id in registered and q.matches(self.facets)]
        # defences: the identity's, plus those a hook names; actors def0, def1, ... sorted by name (erratum E6)
        self.defence_rules: dict[str, str] = {}
        from_identity = self._identity_defence_rule()
        for name in self.ident.defences:
            self.defence_rules[name] = from_identity
        for hook, quirk in matched:
            if hook.defences is not None:
                for name in hook.defences(self._view(quirk, {})):
                    self.defence_rules.setdefault(str(name), hook.rules[0])
        self.def_ids: dict[str, str] = {name: f"def{n}" for n, name in enumerate(sorted(self.defence_rules))}
        self.hooks: list[tuple[QuirkHook, HookView]] = [(hook, self._view(quirk, self.def_ids)) for hook, quirk in matched]
        self.n_mc = self.n_te = self.n_dc = 0

    def _view(self, quirk: Any, def_ids: Mapping[str, str]) -> HookView:
        context = {role.removeprefix("context:"): ref for role, ref in sorted(self.unit.auxiliary.items())
                   if role.startswith("context:")}
        return HookView(quirk, dict(self.facets), self.item.variant, self.doc, self.fam, dict(def_ids), self.R,
                        context, lambda label: self.ctx.open_auxiliary(f"context:{label}"), self._cite_context,
                        self._hook_issue, self.ident.model)

    def _hook_issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning",
                    detail: str | None = None) -> None:
        """``HookView.issue`` (D.6.13): a seal issue raised by a quirk hook."""
        self.issue(code, ids, rule, severity=severity, detail=detail)

    def _cite_context(self, label: str) -> str:
        """Add context artefact ``label`` to the header's ``artifacts`` (role ``supporting``); its id ``a<n>``."""
        if label not in self.cited:
            ref = self.unit.auxiliary[f"context:{label}"]
            self.cited[label] = f"a{len(self.cited) + 1}"
            self.cited_refs.append({**ref.to_json(), "id": self.cited[label], "role": "supporting"})
        return self.cited[label]

    def _identity_read(self) -> bool:
        """Whether the identity's source was there to read (a layout directory, or the logged ``pipeline_name``)."""
        return self.ident.pipeline_dir is not None if self.ident.source == "path" else self.ident.model is not None

    def _identity_src(self) -> dict[str, Any]:
        if self.ident.source != "path":
            return _loc("/pipeline_name")
        # the layout is read from the origin's path, or from a member origin's label, as ``path_facets`` is (D-156)
        return dict(_ORIGIN_LABEL) if self.item.artefact.origin.kind == "member" else dict(_ORIGIN_PATH)

    def _identity_defence_rule(self) -> str:
        """``agentdojo.defence_suffix@1`` for directory suffixes; the identity rule for table rows and name suffixes."""
        return "agentdojo.defence_suffix@1" if self.ident.source == "path" and not self.fam.table_rows else self.ident.model_rule

    def _defence_model(self, name: str, actor: dict[str, Any]) -> dict[str, Any]:
        """D-588: an identity-table row's ``defence_model`` (the model the row's own defence runs on, e.g. Progent's policy
        model) is that defence actor's ``model.requested``, asserted under the identity rule (class I, like the row's
        other values); without one the model stays not recorded."""
        row = self.ident.row
        model = row.get("defence_model") if row is not None and name in self.ident.defences else None
        if model is None:
            return actor
        actor["model"] = {"requested": str(model)}
        actor["rule"].append(self.R(self.ident.model_rule, "/model"))
        actor["unk"] = {"/model/provider": "not_recorded", "/model/served": "not_recorded", "/version": "not_recorded"}
        return actor

    def _namespaces(self) -> dict[str, str]:
        out = dict(NAMESPACES)
        for hook, _view in self.hooks:
            out.update(hook.namespaces)
        return dict(sorted(out.items()))

    # ---------------------------------------------------------------------------------------------- helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors MappingContext.rule
        """A statement's rule citation: the D rule or its ``_unverified`` twin (D.5.4), with an optional pointer."""
        return self.ctx.rule(self.cite.cite(rule_id), pointer)

    def C(self, rule_id: str) -> str:  # noqa: N802 - the class of what R cites
        """The class (``D`` or ``I``) of the rule :meth:`R` cites for ``rule_id``."""
        return self.cite.cls(rule_id)

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        """A seal issue citing ``rule`` as given (pass ``self.cite.cite(rule)`` to cite a statement's reading)."""
        self.ctx.issue(code, ids=list(ids), rule=self.ctx.rule(rule), severity=severity, detail=detail)  # type: ignore[arg-type]

    def quirk_on(self, quirk_id: str) -> bool:
        return self.fam.applies(quirk_id, self.facets)

    def detect(self, quirk_id: str) -> bool:
        """Note a quirk seen in the data; ``True`` when the profile declares it for this file (then it is applied)."""
        self.detected.add(quirk_id)
        return self.quirk_on(quirk_id)

    def _read_fields(self) -> None:
        d = self.doc

        def text(key: str, *, nullable: bool = False, typed: bool = False) -> Any:
            value = d.get(key)
            if typed and isinstance(value, str) and value and _placeholder(value):
                # regeneration-batch item 88 (CD-11): a deny-listed name in a typed header slot identifies nothing either
                raise MalformedArtefact(f"{key}: placeholder")
            if (isinstance(value, str) and value) or (nullable and value is None):
                return value
            # an empty name (suite, task, pipeline, attack, injection task) identifies nothing: the record is malformed
            # (D.2.8), never a placeholder in the header (AER-V17)
            raise MalformedArtefact(f"{key}: empty" if value == "" else f"{key}: unexpected value type")

        self.suite = text("suite_name", typed=True)
        self.task_id = text("user_task_id", typed=True)
        self.pipeline_name = text("pipeline_name")
        self.attack = text("attack_type", nullable=True, typed=True)
        self.target = text("injection_task_id", nullable=True, typed=True)
        self.error = text("error", nullable=True)
        if not isinstance(d.get("injections"), dict):
            raise MalformedArtefact("injections: unexpected value type")
        if not isinstance(d.get("messages"), list):
            raise MalformedArtefact("messages: unexpected value type")
        self.messages: list[Any] = d["messages"]
        for name in ("utility", "security"):
            value = d.get(name)
            if name in d and value is not None and not isinstance(value, bool):
                raise MalformedArtefact(f"{name}: unexpected value type")
        duration = d.get("duration")
        if duration is not None and (isinstance(duration, bool) or not isinstance(duration, int | float)):
            raise MalformedArtefact("duration: unexpected value type")
        self.dos = set(self.fam.benchmark.get("dos_attacks", ()))
        self.v1 = self.item.variant in (V1_K14, f"{V1_K14}.incomplete")  # K14 key set (outcome keys may be missing)
        if self.v1:  # D.6.5: the three version fields of K14 (strings; a non-string is kept out of the typed slots)
            self.benchmark_version = d.get("benchmark_version")
            self.evaluation_timestamp = d.get("evaluation_timestamp")
            self.package_version = d.get("agentdojo_package_version")

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        body: list[Any] = []
        header = self._header()
        self._path_agreement()
        self._identity_issues()
        conflict = getattr(self, "id_style_conflict", None)
        if conflict is not None:
            header.ext()["id_style_provider"] = conflict
            header.data["evf"]["/ext/agentdojo/id_style_provider"] = "I"
            header.data["rule"].append(self.R(self.ident.model_rule, "/ext/agentdojo/id_style_provider"))
        for hook, view in self.hooks:  # D.6.13: header facts of a source-specific quirk, under the hook's namespaces
            if hook.execution is not None:
                hook.execution(view, header.data)
        self._actors(body)
        self._scopes(body)
        self._fixtures(body)
        self._environment_load(body)
        self._messages(body)
        self._log_end(body)
        self._judgements(body)
        self._undeclared_quirks()
        records = [record.done() if isinstance(record, _Rec) else record for record in body]
        head = header.done()
        _ambiguous_tool_names(records)
        redact_records(self.redactor, self.ctx, head, records)
        surrogates(self, (head, *records), "agentdojo")
        for record in (head, *records):  # C.6.5 rule 1: no field stronger than an I rule (a twin) that justifies it
            weaken_to_rule_class(record)
        # C.3.1 ``rules``: every catalogue cited in the file (the mapper's own, plus those a quirk hook cites)
        cited = {str(ref).split(".", 1)[0] for r in (head, *records) for ref in r.get("rule", ())}
        cited |= {str(i.get("rule", "")).split(".", 1)[0] for i in getattr(self.ctx, "issues", ()) if i.get("rule")}
        head["rules"] = self.ctx.catalogue_versions(sorted(set(CATALOGUES) | cited))
        if self.cited_refs:  # context artefacts a hook cited (role supporting, D.6.12 item 6)
            head["artifacts"] = [*head["artifacts"], *self.cited_refs]
        yield head
        yield from records

    # ---------------------------------------------------------------------------------------------- header
    def _header(self) -> _Rec:
        h = _Rec()
        task: dict[str, Any] = {
            "benchmark": self.benchmark,
            "suite": h.enc(self.suite, "/task/suite"),
            "task_id": h.enc(self.task_id, "/task/task_id"),
            "attack_id": h.enc(self.attack, "/task/attack_id"),
            "attack_target_id": h.enc(self.target, "/task/attack_target_id"),
        }
        evf: dict[str, str] = {"/task/benchmark": "D"}
        rules = [self.R("agentdojo.benchmark_from_dialect@1", "/task/benchmark")]
        unk: dict[str, str] = {"/instrumentation": "not_recorded"}
        src = [_loc("/suite_name"), _loc("/user_task_id"), _loc("/attack_type"), _loc("/injection_task_id")]
        names = sorted(self.def_ids)
        defence_rule = self.defence_rules[names[0]] if len(names) == 1 else self._identity_defence_rule()
        unresolved_row = bool(self.fam.table_rows) and self.ident.model is None  # D.4.5: an unknown directory is never guessed
        if (not self._identity_read() or unresolved_row) and not names:
            unk["/task/defense_id"] = "not_recorded"
        elif len(names) > 1:
            unk["/task/defense_id"] = "ambiguous"
            src.append(self._identity_src())
        else:
            task["defense_id"] = names[0] if names else None
            evf["/task/defense_id"] = "I"
            src.append(self._identity_src())
        rules.append(self.R(defence_rule, "/task/defense_id"))
        ext = h.ext()
        ext["pipeline_name"] = h.enc(self.pipeline_name, "/ext/agentdojo/pipeline_name")
        ext["error"] = h.enc(self.error, "/ext/agentdojo/error")
        if self.attack is None and self.task_id.startswith("injection_task_"):
            if self.detect("agentdojo.injection_task_as_user_task_prepass"):
                ext["task_kind"] = "injection_task_as_user_task"
                evf["/ext/agentdojo/task_kind"] = "D"
                rules.append(self.R("agentdojo.injection_task_as_user_task@1", "/ext/agentdojo/task_kind"))
        elif self.attack in self.dos:
            if self.detect("agentdojo.dos_security_not_utility"):
                ext["task_kind"] = "dos"
                evf["/ext/agentdojo/task_kind"] = "D"
                rules.append(self.R("agentdojo.dos_placeholder_injection_task@1", "/ext/agentdojo/task_kind"))
        self._history_fields(ext, evf, rules, src)
        extra = sorted(f.partition(":")[2] for f in self.item.flags if f.startswith("extra:"))
        if extra:
            ext["extra"] = {k: h.enc(self.doc[k], json_pointer("ext", "agentdojo", "extra", k)) for k in extra}
            src.extend(_loc(json_pointer(k)) for k in extra)
            self.issues_now("agentdojo.unknown_top_level_key", ["exec"], "agentdojo.tracelogger_record_shape@1", severity="info")
        self.unit_kind = "outcome_only" if not self.messages else "agent_execution"
        art = self.item.artefact
        h.data.update(
            {
                "k": "execution",
                "id": "exec",
                "aer": "0.1",
                "ex": self.ctx.ex,
                "mode": "import",
                "unit": self.unit_kind,
                "source_key": {"sha256": art.sha256, "loc": {"p": ""}},
                "artifacts": [_artefact_json(self.unit, self.ctx)],
                "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
                "dialect": {"id": DIALECT_ID, "variant": self.item.variant},
                "profile": self.ctx.profile.header(),
                "rules": self.ctx.catalogue_versions(CATALOGUES),
                "ns": self._namespaces(),
                "canon": "jcs-rfc8785",
                "hash": "sha256",
                "task": task,
                "ev": "O",
                "by": "config",
                "evf": evf,
                "rule": rules,
                "src": src,
                "unk": unk,
            }
        )
        return h

    def _history_fields(self, ext: dict[str, Any], evf: dict[str, str], rules: list[str], src: list[dict[str, Any]]) -> None:
        """D.6.16: ``ext.agentdojo.committed_no_later_than`` (D) and ``benchmark_era`` (I) from the git origin's
        ``introduced_in_commit`` and the profile's history table. Neither is written without that commit id (no history
        index when the file was imported), without a table for the origin's repository, or for a commit the table does not
        list (then ``agentdojo.history_commit_unlisted``): nothing is guessed. The date is never a PROV time and never the
        timestamp of any record. The era is only a candidate for a file that records no benchmark version."""
        table = self.fam.history
        origin = self.item.artefact.origin
        commit = origin.data.get("introduced_in_commit")
        if table is None or origin.kind != "git" or origin.data.get("repo") != table.repo or not isinstance(commit, str):
            return
        date = table.date(commit)
        if date is None:
            self.issue("agentdojo.history_commit_unlisted", ["exec"], "agentdojo.committed_no_later_than@1", detail=commit[:12])
            return
        where = {"a": "a0", "o": "/introduced_in_commit"}
        ext["committed_no_later_than"] = date
        evf["/ext/agentdojo/committed_no_later_than"] = "D"
        rules.append(self.R("agentdojo.committed_no_later_than@1", "/ext/agentdojo/committed_no_later_than"))
        src.append(where)
        recorded = (
            self.v1 and isinstance(self.benchmark_version, str) and self.benchmark_version.strip().lower() not in _SENTINELS
        )
        era = table.era(commit)
        if not recorded and era is not None:
            value: dict[str, Any] = {"candidate": era.candidate, "basis": "registered" if era.registered else "pre_versioning"}
            if era.next_version is not None and era.next_cut_date is not None:
                value["next"] = {"version": era.next_version, "cut_date": era.next_cut_date}
            ext["benchmark_era"] = value
            evf["/ext/agentdojo/benchmark_era"] = "I"
            rules.append(self.R("agentdojo.benchmark_era_from_commit@1", "/ext/agentdojo/benchmark_era"))

    def issues_now(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        self.issue(code, ids, rule, severity=severity, detail=detail)

    def _path_agreement(self) -> None:
        """R-PATH (D.6.3): the layout components agree with the fields; a mismatch is reported, never corrected."""
        facets = self.path_facets
        if facets is None:
            return
        wanted = self.ctx.profile.data.get("import", {}).get("path_must_agree", ())
        attack_dir = facets.get("attack_dir")
        alias = self.fam.identity.get("attack_dir_alias", {})  # D.4.4 ROPE: a directory standing for an attack name
        observed = {
            "suite_name": (facets.get("suite"), self.suite),
            "user_task_id": (facets.get("task_dir"), self.task_id),
            "attack_type": (alias.get(attack_dir, attack_dir), "none" if self.attack is None else self.attack),
            "injection_task_id": (facets.get("file"), "none" if self.target is None else self.target),
        }
        for field in wanted:
            pair = observed.get(field)
            if pair is not None and pair[0] is not None and pair[0] != pair[1]:
                self.issue("agentdojo.path_field_mismatch", ["exec"], "agentdojo.log_path_layout@1", detail=str(field))

    def _identity_issues(self) -> None:
        if self.ident.model is None:
            self.issue("identity_unresolved", ["agent"], self.ident.model_rule)
        elif self.ident.pipeline_name_mismatch:
            self.issue("agentdojo.pipeline_name_mismatch", ["exec"], self.ident.model_rule)
        if self.ident.provider is not None:
            self._id_style()

    def _id_style(self) -> None:
        """D.6.5 Step 2: call-id styles that name another provider than the resolved identity's give
        ``identity_conflict``; both values stay, the style in ``ext.agentdojo.id_style_provider`` (D.6.11 item 5: only
        for an identity that names a provider)."""
        styles = dict(self.fam.identity.get("id_style_corroboration", {}))
        seen: set[str] = set()
        for message in self.messages:
            for call in (message.get("tool_calls") or ()) if isinstance(message, dict) else ():
                ident = call.get("id") if isinstance(call, dict) else None
                if isinstance(ident, str) and ident:
                    seen.update(style for glob, style in styles.items() if fnmatch.fnmatchcase(ident, glob))
        others = sorted(s for s in seen if s != self.ident.provider)
        if others:
            self.id_style_conflict = others[0]
            self.issue("identity_conflict", ["agent"], self.ident.model_rule, detail="call-id style " + others[0])

    # ---------------------------------------------------------------------------------------------- actors
    def _bench_v1(self) -> _Rec:
        """D.6.5 Step 2, ``v1.k14``: ``version`` = ``benchmark_version`` and ``code.dist_version`` =
        ``agentdojo_package_version`` (O by source; quirk ``package_version_not_code_identity``), no commit."""
        bench = _Rec(k="actor", id="bench", kind="benchmark", name=self.benchmark, ev="D", by="source")
        rules = [self.R("agentdojo.benchmark_from_dialect@1")]
        evf: dict[str, str] = {}
        unk: dict[str, str] = {}
        src: list[dict[str, Any]] = []
        if isinstance(self.benchmark_version, str) and self.benchmark_version.strip().lower() not in _SENTINELS:
            bench.data["version"] = bench.enc(self.benchmark_version, "/version")
            evf["/version"] = "O"
            src.append(_loc("/benchmark_version"))
            meaning = self.fam.version_label_semantics(self.suite)
            if meaning != "suite_version":  # D.6.12 item 5: the label is verbatim; its reading is the profile's
                bench.ext()["version_label_semantics"] = meaning
                evf["/ext/agentdojo/version_label_semantics"] = "I"
                rules.append(self.R("agentdojo.version_label_semantics@1", "/ext/agentdojo/version_label_semantics"))
        else:
            unk["/version"] = "not_recorded"
        if isinstance(self.package_version, str) and self.package_version.strip().lower() not in _SENTINELS:
            bench.data["code"] = {"dist": "agentdojo", "dist_version": bench.enc(self.package_version, "/code/dist_version")}
            evf["/code"] = "O"
            evf["/code/dist"] = "D"
            rules.append(self.R("agentdojo.benchmark_from_dialect@1", "/code/dist"))
            src.append(_loc("/agentdojo_package_version"))
            unk["/code/commit"] = "not_recorded"
        else:
            unk["/code"] = "not_recorded"
        bench.data["rule"] = rules
        if evf:
            bench.data.update(evf=evf, src=src)
        else:
            del bench.data["by"]
        bench.data["unk"] = unk
        return bench

    def _actors(self, body: list[Any]) -> None:
        if self.v1:
            body.append(self._bench_v1())
        else:
            body.append({"k": "actor", "id": "bench", "kind": "benchmark", "name": self.benchmark, "ev": "D",
                         "rule": [self.R("agentdojo.benchmark_from_dialect@1")],
                         "unk": {"/code": "not_recorded", "/version": "not_recorded"}})
        body.append({"k": "actor", "id": "user", "kind": "simulated_user", "ev": "D", "rule": [self.R("agentdojo.user_is_simulated@1")]})
        agent: dict[str, Any] = {"k": "actor", "id": "agent", "kind": "llm_agent", "on_behalf_of": "user", "ev": "D"}
        if self.ident.model is not None:
            model: dict[str, Any] = {"requested": self.ident.model}
            model_unk = {"/model/provider": "not_recorded", "/model/served": "not_recorded", "/params": "not_recorded"}
            if self.ident.provider is not None:  # D.4.5: an identity-table row's provider, asserted under the same rule
                model["provider"] = self.ident.provider
                del model_unk["/model/provider"]
            agent.update(model=model, evf={"/model": "I"},
                         rule=[self.R("agentdojo.user_is_simulated@1"), self.R(self.ident.model_rule, "/model")],
                         src=[self._identity_src()], unk=model_unk)
        else:
            agent.update(rule=[self.R("agentdojo.user_is_simulated@1")], unk={"/model": "not_recorded", "/params": "not_recorded"})
        body.append(agent)
        body.append({"k": "actor", "id": "env", "kind": "tool_runtime", "name": "agentdojo.FunctionsRuntime", "on_behalf_of": "agent",
                     "ev": "D", "evf": {"/on_behalf_of": "I"},
                     "rule": [self.R("agentdojo.functions_runtime@1"), self.R("agentdojo.auto_execution_unverified@1", "/on_behalf_of")]})
        if self.attack is not None:
            att = _Rec(k="actor", id="att", kind="attacker", ev="O", by="config", src=[_loc("/attack_type")])
            att.data["name"] = att.enc(self.attack, "/name")
            body.append(att)
        for name, did in self.def_ids.items():
            body.append(self._defence_model(name, {"k": "actor", "id": did, "kind": "defense", "name": name, "ev": "I",
                         "rule": [self.R(self.defence_rules[name])], "src": [self._identity_src()],
                         "unk": {"/model": "not_recorded", "/version": "not_recorded"}}))
        for hook, view in self.hooks:  # D.6.13: e.g. the correcting party of a released recomputation
            if hook.actors is not None:
                body.extend(dict(actor) for actor in hook.actors(view))

    # ---------------------------------------------------------------------------------------------- scopes
    def _run_start_v1(self, run: _Rec) -> None:
        """D.6.5 Step 3, ``v1.k14``: ``evaluation_timestamp`` is the naive local time of TraceLogger construction
        (C.8.5): ``t.start_naive`` (``T`` separator) and ``t.raw.start`` verbatim, ``unk /t/start ambiguous``."""
        stamp = self.evaluation_timestamp
        if not isinstance(stamp, str):
            return
        t = run.data.setdefault("t", {})
        unk = run.data.setdefault("unk", {})
        unk.pop("/t", None)
        unk["/t/start"] = "ambiguous"
        unk["/t/end"] = "not_recorded"
        match = _NAIVE_TS.fullmatch(stamp)
        if match is not None and _real_naive(f"{match.group(1)}T{match.group(2)}"):
            # regeneration-batch item 92 (CD-16): only a real date and time (no 30 February, no hour 25); else raw only
            t["start_naive"] = f"{match.group(1)}T{match.group(2)}"
        t.setdefault("raw", {})["start"] = run.enc(stamp, "/t/raw/start")
        run.data["src"] = [s for s in run.data.get("src", []) if s.get("p") != ""] + [_loc("/evaluation_timestamp")]
        run.data["rule"] = [self.R(self.r_timestamp, "/t/start")]

    def _scopes(self, body: list[Any]) -> None:
        run = _Rec(k="scope", id="run", kind="run", actor="agent", ev="O", by="source")
        duration = self.doc.get("duration")
        if duration is not None:
            run.data["t"], unk = run_duration(run, duration)
            run.data["src"] = [_loc("/duration")]
            run.data["unk"] = {"/status": "not_recorded", "/t/end": "not_recorded", "/t/start": "not_recorded", **unk}
        else:
            run.data["src"] = [_loc("")]
            run.data["unk"] = {"/status": "not_recorded", "/t": "not_recorded"}
        if self.v1:
            self._run_start_v1(run)
        body.append(run)
        if not self.messages:
            return
        att = _Rec(k="scope", id="att0", kind="attempt", parent="run", actor="agent", scored=True, ev="D")
        rules = [self.R("agentdojo.log_holds_last_pass@1")]
        if self.fam.retry_semantics == "agentdyn.last_assistant_content_none_max3":  # the last assistant message anywhere
            last = next((m for m in reversed(self.messages) if isinstance(m, dict) and m.get("role") == "assistant"), None)
        else:  # agentdojo.final_content_none_max3: model_output_from_messages reads the final message
            last = self.messages[-1]
        null_final = isinstance(last, dict) and last.get("role") == "assistant" and "content" in last and last["content"] is None
        if null_final and self.error is None and self.detect("agentdojo.silent_rerun_last_pass_only"):
            retry = self.cite.cite(_RETRY_RULES.get(self.fam.retry_semantics, "agentdojo.null_final_implies_three_passes@1"))
            att.data["index"] = 2
            att.ext()["pre_state_not_initial"] = True
            rules += [self.R(retry, "/ext/agentdojo/pre_state_not_initial"), self.R(retry, "/index")]
            self.issue("retry_passes_inferred", ["att0"], retry)
            self.issue("earlier_attempts_unobservable", ["att0"], retry)
        else:
            att.data["unk"] = {"/index": "lost"}
            self.issue("earlier_attempts_unobservable", ["att0"], self.cite.cite("agentdojo.log_holds_last_pass@1"))
        att.data["rule"] = rules
        body.append(att)

    # ---------------------------------------------------------------------------------------------- fixtures
    def _fixtures(self, body: list[Any]) -> None:
        for i, (vector, payload) in enumerate(self.doc["injections"].items()):
            rec = _Rec(k="fixture", id=f"fx{i}", kind="injection_payload", ev="O", by="benchmark",
                       src=[_loc(json_pointer("injections", vector))])
            rec.data["vector"] = rec.enc(vector, "/vector")
            rec.data["content"] = rec.enc(payload, "/content")
            if self.attack is not None:
                rec.data.update(actor="att", evf={"/actor": "I"},
                                rule=[self.R("agentdojo.payload_attributed_to_attacker@1", "/actor")])
            for hook, view in self.hooks:  # D.6.13: e.g. the payload's link to an attack cache
                if hook.fixture is not None:
                    hook.fixture(view, vector, rec.data)
            body.append(rec)

    def _environment_load(self, body: list[Any]) -> None:
        """Item 5 (C2, D-370): the suite loads the environment with the run's injections before the passes, so the run
        used every payload: one ``agentdojo:load_environment`` activity of the run scope, by the benchmark, whose inputs
        are the payload fixtures (``aprov.g_use@1``; ``apv:partOf`` the run)."""
        fixtures = [r.data["id"] for r in body if isinstance(r, _Rec) and r.data.get("k") == "fixture"
                    and r.data.get("kind") == "injection_payload"]
        if fixtures:
            body.append(environment_load(fixtures, self.R, self.C))

    # ---------------------------------------------------------------------------------------------- messages
    def _shape(self, message: object) -> str | None:
        """The role of a message of a known ChatMessage shape, else ``None`` (kept verbatim, D.6.6 last row)."""
        if not isinstance(message, dict):
            return None
        role = message.get("role")
        keys = _SHAPES.get(role) if isinstance(role, str) else None
        if keys is None or set(message) != keys:
            return None
        content = message.get("content")
        if not (content is None or isinstance(content, str) or (isinstance(content, list) and all(isinstance(b, dict) for b in content))):
            return None
        if role == "assistant":
            calls = message.get("tool_calls")
            if calls is not None and not (isinstance(calls, list) and all(self._call_ok(c) for c in calls)):
                return None
        if role == "tool":
            if not self._call_ok(message.get("tool_call")) or not (message.get("error") is None or isinstance(message.get("error"), str)):
                return None
        return str(role)

    @staticmethod
    def _call_ok(call: object) -> bool:
        # regeneration-batch item 91 (CD-14): a non-string id (an int would fail provider_call_id, a dict is
        # unhashable) is no FunctionCall shape: the message is kept verbatim instead of collapsing the log
        return (isinstance(call, dict) and set(call) <= _CALL_KEYS and {"function", "args"} <= set(call)
                and isinstance(call["function"], str) and isinstance(call["args"], dict)
                and (call.get("id") is None or isinstance(call["id"], str)))

    def _content_parts(self, rec: _Rec, content: object, base: int = 0) -> list[dict[str, Any]]:
        """R-CONTENT through :func:`content_block_parts` (shared with the capture mapper)."""
        found = content_block_parts(content, base, rec.enc)
        for _ in range(found.unknown):
            self.issue("agentdojo.unknown_message_shape", [str(rec.data["id"])], "agentdojo.tracelogger_record_shape@1")
        if found.null_text_blocks:
            rec.ext()["null_text_blocks"] = found.null_text_blocks
        return found.parts

    def _messages(self, body: list[Any]) -> None:
        msgs = self.messages
        self.inputs: list[str] = []
        self.prev: str | None = None
        self.first_user: tuple[str, str] | None = None  # (id, lexical form of its content)
        self.filter_prompt_seen = False
        self.filter_pending = False
        self.batches: list[dict[str, Any]] = []  # agent assistant messages with calls: {"msg", "calls", "results"}
        self.agent_assistants: list[str] = []
        self.agent_calls: dict[str, list[str]] = {}  # agent assistant message id -> its tool_call part ids
        self.te_of: dict[int, str] = {}  # tool message index -> its tool_execution id (for the log_end hooks)
        self.request_of: dict[int, str] = {}  # tool message index -> the assistant message whose call it answers
        forms: set[str] = set()
        i = 0
        while i < len(msgs):
            message = msgs[i]
            role = self._shape(message)
            if role is not None and message.get("content") is not None:
                forms.add("string" if isinstance(message["content"], str) else "blocks")
            if role == "assistant":
                j = i + 1
                tools: list[int] = []
                while j < len(msgs) and self._shape(msgs[j]) == "tool":
                    tools.append(j)
                    j += 1
                self._assistant(body, i, message, tools)
                i = j
                continue
            if role == "tool":
                self._tool(body, i, message, None, None, 0)
            elif role in ("system", "user"):
                self._plain(body, i, message, role)
            elif (decided := self._hook_user_decision(i, message)) is not None:
                self._user_decision(body, i, message, decided[0])
            else:
                self._unknown(body, i, message)
            self.filter_pending = self.filter_pending and role == "user"
            i += 1
        if len(forms) > 1:
            self.issue("agentdojo.mixed_content_forms", ["exec"], "agentdojo.tracelogger_record_shape@1", severity="info")
        self._trailing_calls()

    def _after_pos(self, rec: _Rec, evf: dict[str, str], rules: list[str]) -> None:
        if self.prev is not None:
            rec.data["after"] = [{"b": "pos", "id": self.prev}]
            evf["/after"] = self.C(self.r_ordered)
            rules.append(self.R(self.r_ordered, "/after"))

    def _push(self, mid: str) -> None:
        self.inputs.append(mid)
        self.prev = mid

    def _plain(self, body: list[Any], i: int, message: Mapping[str, Any], role: str) -> None:
        mid = f"m{i}"
        rec = _Rec(k="message", id=mid, scope="att0", role=role, ev="O", by="source", src=[_loc(f"/messages/{i}")])
        rec.data["parts"] = self._content_parts(rec, message.get("content"))
        evf: dict[str, str] = {}
        rules: list[str] = []
        if role == "system":
            author = self._message_author(i, message, "system")  # D-586: a defence insert, or the harness prompt after one
            if author is not None:
                self._authored_system(rec, message, author, evf, rules)
            elif i == 0:
                rec.data["actor"] = "bench"
                evf["/actor"] = "D"
                rules.append(self.R("agentdojo.system_prompt_from_harness@1", "/actor"))
                self._prompt_variant(rec, message.get("content"), evf, rules)
            else:
                rec.data["unk"] = {"/actor": "not_recorded"}
        elif self.first_user is None:
            rec.data["actor"] = "user"
            evf["/actor"] = "D"
            rules.append(self.R("agentdojo.user_is_simulated@1", "/actor"))
            self.first_user = (mid, _lexical(message.get("content")))
        else:
            self._later_user(rec, message, evf, rules)
        self._after_pos(rec, evf, rules)
        if evf:
            rec.data["evf"] = evf
        if rules:
            rec.data["rule"] = rules
        body.append(rec)
        self._push(mid)

    def _prompt_variant(self, rec: _Rec, content: object, evf: dict[str, str], rules: list[str]) -> None:
        """D.6.6 system row: label ``ext.agentdojo.system_prompt_variant`` by the SHA-256 of the system text (a string,
        or the texts of text blocks joined by a newline, ``get_text_content_as_str``) against the variants the profile
        pins for this file's facets (D); an unknown digest gives the info issue ``agentdojo.system_prompt_unrecognised``.
        With no variant declared for the facets nothing is labelled or flagged (D.6.11 item 9)."""
        variants = [v for v in self.fam.prompt_variants if v.matches(self.facets)]
        if not variants:
            return
        text: str | None = content if isinstance(content, str) else None
        if isinstance(content, list) and content and all(
                isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("content"), str) for b in content):
            text = "\n".join(str(b["content"]) for b in content)
        digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest() if text is not None else None  # item 145
        found = next((v for v in variants if v.sha256 is not None and v.sha256 == digest), None)
        rule = "agentdojo.system_prompt_variant_digest@1"
        if found is None:
            self.issue("agentdojo.system_prompt_unrecognised", [str(rec.data["id"])], rule, severity="info")
            return
        rec.ext()["system_prompt_variant"] = found.label
        evf["/ext/agentdojo/system_prompt_variant"] = "D"
        rules.append(self.R(rule, "/ext/agentdojo/system_prompt_variant"))

    def _message_author(self, i: int, message: Mapping[str, Any], role: Literal["system", "assistant"]) -> MessageAuthor | None:
        """A hook's :class:`MessageAuthor` for a system message or an agent assistant message without calls (D-586). The
        author must be a defence actor of the file (or ``bench`` for a system message); an assistant author needs a
        verdict. Without such a hook nothing is read (byte-neutral for every other profile)."""
        if not any(hook.message_author is not None for hook, _view in self.hooks):
            return None
        content = message.get("content")
        text: str | None = content if isinstance(content, str) else None
        if isinstance(content, list) and content and all(
                isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("content"), str) for b in content):
            text = "\n".join(str(b["content"]) for b in content)
        # a lone surrogate (D-23) is digested as its code unit, so it can never raise; it matches no listed text
        digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest() if text is not None else None
        view = TextMessage(i, role, text, digest)
        for hook, hook_view in self.hooks:
            if hook.message_author is not None:
                author = hook.message_author(hook_view, view)
                if author is None:
                    continue
                if role == "assistant" and (author.verdict is None or author.actor not in self.def_ids):
                    continue
                if role == "system" and author.actor != "bench" and author.actor not in self.def_ids:
                    continue
                return author
        return None

    def _authored_system(self, rec: _Rec, message: Mapping[str, Any], author: MessageAuthor, evf: dict[str, str],
                         rules: list[str]) -> None:
        """D-586: a system message whose author a hook names: a defence insert, or a harness prompt (labelled as at
        index 0) that stands after one."""
        rec.data["actor"] = "bench" if author.actor == "bench" else self.def_ids[author.actor]
        evf["/actor"] = self.C(author.rules[0])
        rules.append(self.R(author.rules[0], "/actor"))
        if author.actor == "bench":
            self._prompt_variant(rec, message.get("content"), evf, rules)

    def _defence_reply(self, body: list[Any], rec: _Rec, mc_id: str, author: MessageAuthor, i: int) -> None:
        """D-586: a defence replaced the model's reply. The model call stays; a decision by the defence about it (the
        reply ``/original`` overwritten) generates the message, which the defence wrote."""
        dc_id = f"dc{self.n_dc}"
        self.n_dc += 1
        defence, rule = self.def_ids[author.actor], author.rules[0]
        body.append({"k": "decision", "id": dc_id, "actor": defence, "scope": "att0", "subject": mc_id,
                     "verdict": author.verdict, "after": [{"b": "causal", "id": mc_id}], "ev": self.C(rule),
                     "rule": [self.R(rule), self.R("aer.decision_after_subject@1", "/after")],
                     "src": [_loc(f"/messages/{i}/content")],
                     "unk": {"/original": "overwritten", "/reason": "not_recorded", "/t": "not_recorded"}})
        rec.data.update(actor=defence, generated_by=dc_id, after=[{"b": "causal", "id": dc_id}])
        rec.data["evf"] = {"/actor": self.C(rule), "/after": self.C(rule), "/generated_by": self.C(rule)}
        kept = [r for r in rec.data["rule"] if "empty_assistant_text_ambiguous" in r]
        rec.data["rule"] = [self.R(rule, "/actor"), self.R(rule, "/generated_by"),
                            self.R("aer.output_after_generator@1", "/after"), *kept]

    def _later_user(self, rec: _Rec, message: Mapping[str, Any], evf: dict[str, str], rules: list[str]) -> None:
        assert self.first_user is not None
        mid = str(rec.data["id"])
        tf = self.def_ids.get("tool_filter")
        rup = self.def_ids.get("repeat_user_prompt")
        if tf is not None and not self.filter_prompt_seen and self.detect("agentdojo.tool_filter_aux_llm"):
            self.filter_prompt_seen = True
            self.filter_pending = True
            rec.data["actor"] = tf
            evf["/actor"] = "I"
            rules.append(self.R("agentdojo.tool_filter_aux_message@1", "/actor"))
            return
        if rup is not None and _lexical(message.get("content")) == self.first_user[1] and self.detect("agentdojo.repeat_user_prompt_reinsertion"):
            rec.data["actor"] = rup
            rec.ext()["copy_of"] = self.first_user[0]
            evf["/actor"] = "I"
            evf["/ext/agentdojo/copy_of"] = "I"
            rules.append(self.R("agentdojo.repeat_user_prompt_copy@1", "/actor"))
            rules.append(self.R("agentdojo.repeat_user_prompt_copy@1", "/ext/agentdojo/copy_of"))
            return
        author = self._hook_later_user(UserMessage(int(mid[1:]), message))
        if author is not None:  # D-376: a defence wrote it (e.g. CaMeL's interpreter feedback)
            rec.data["actor"] = self.def_ids[author.defence]
            evf["/actor"] = self.C(author.rules[0])
            rules.append(self.R(author.rules[0], "/actor"))
            return
        rec.data["actor"] = "user"
        evf["/actor"] = "I"
        rules.append(self.R("agentdojo.additional_user_message_unattributed@1", "/actor"))
        self.issue("unattributed_additional_user_message", [mid], "agentdojo.additional_user_message_unattributed@1")

    def _hook_later_user(self, view: UserMessage) -> UserAuthor | None:
        """A hook's :class:`UserAuthor` for a later plain user message; the author must be a defence actor of the file."""
        for hook, hook_view in self.hooks:
            if hook.later_user_message is not None:
                author = hook.later_user_message(hook_view, view)
                if author is not None and author.defence in self.def_ids:
                    return author
        return None

    def _hook_agent_input(self) -> InputNotLogged | None:
        """A hook's :class:`InputNotLogged` for the file's agent model calls (D-376)."""
        for hook, hook_view in self.hooks:
            if hook.agent_input is not None:
                declared = hook.agent_input(hook_view)
                if declared is not None:
                    return declared
        return None

    def _unknown(self, body: list[Any], i: int, message: object) -> None:
        mid = f"m{i}"
        role = message.get("role") if isinstance(message, dict) else None
        rec = _Rec(k="message", id=mid, scope="att0", ev="O", by="source", src=[_loc(f"/messages/{i}")])
        rec.data["role"] = rec.enc(role, "/role") if isinstance(role, str) and role else "agentdojo.unknown"
        rec.data["parts"] = [{"t": "other", "type": "agentdojo.unknown_message", "value": rec.enc(message, "/parts/0/value")}]
        rec.data["unk"] = {"/actor": "not_recorded"}
        evf: dict[str, str] = {}
        rules: list[str] = []
        self._after_pos(rec, evf, rules)
        if evf:
            rec.data.update(evf=evf, rule=rules)
        body.append(rec)
        self.issue("agentdojo.unknown_message_shape", [mid], "agentdojo.tracelogger_record_shape@1")
        self._push(mid)

    # ---------------------------------------------------------------------------------------------- assistant
    def _assistant(self, body: list[Any], i: int, message: Mapping[str, Any], tools: Sequence[int]) -> None:
        calls_raw = message.get("tool_calls")
        aux_actor = self.def_ids.get("tool_filter")
        aux = self.filter_pending and aux_actor is not None and not calls_raw
        self.filter_pending = False
        mc_id = f"mc{self.n_mc}"
        self.n_mc += 1
        not_logged = None if aux else self._hook_agent_input()
        mc = _Rec(k="model_call", id=mc_id, actor=aux_actor if aux else "agent", role="auxiliary" if aux else "agent",
                  scope="att0", status="kept")
        if not_logged is None:
            mc.data["input"] = list(self.inputs)
        mc_rules = [self.R("agentdojo.tool_filter_aux_message@1" if aux else self.r_one_call)]
        if self.prev is not None:
            mc.data["after"] = [{"b": "pos", "id": self.prev}]
            mc_rules.append(self.R(self.r_ordered, "/after"))
        mc_class = "I" if aux else self.C(self.r_one_call)
        mc.data["ev"] = mc_class
        if not_logged is None:
            mc_rules.append(self.R("agentdojo.context_is_prefix@1", "/input"))
            if mc_class == "D":
                mc.data["evf"] = {"/input": "I"}
        else:  # D-376: the model was sent a list the log does not hold
            mc_rules.append(self.R(not_logged.rules[0], "/input"))
        mc.data["rule"] = mc_rules
        mc.data["unk"] = {key: "not_recorded" for key in _MODEL_CALL_UNKNOWN}
        if not_logged is not None:
            mc.data["unk"]["/input"] = "not_recorded"
            mc.data["unk"] = dict(sorted(mc.data["unk"].items()))
        body.append(mc)

        mid = f"m{i}"
        rec = _Rec(k="message", id=mid, scope="att0", role="assistant", generated_by=mc_id,
                   after=[{"b": "causal", "id": mc_id}], ev="O", by="source", src=[_loc(f"/messages/{i}")])
        parts = self._content_parts(rec, message.get("content"))
        unk: dict[str, str] = {}
        if aux:
            rec.data["actor"] = aux_actor
            evf = {"/actor": "I", "/after": "I", "/generated_by": "I"}
            rules = [self.R("agentdojo.tool_filter_aux_message@1", "/actor"),
                     self.R("agentdojo.tool_filter_aux_message@1", "/generated_by"),
                     self.R("aer.output_after_generator@1", "/after")]
        else:
            rec.data["actor"] = "agent"
            evf = {"/after": self.C(self.r_one_call), "/generated_by": self.C(self.r_one_call)}
            rules = [self.R(self.r_one_call, "/generated_by"), self.R("aer.output_after_generator@1", "/after")]
        for k, content_part in enumerate(parts):
            if content_part.get("t") == "text" and content_part.get("text") == "":
                unk[f"/parts/{k}/text"] = "ambiguous"
                rules.append(self.R("agentdojo.empty_assistant_text_ambiguous@1", f"/parts/{k}/text"))
        calls: list[list[Any]] = []
        placeholders: dict[str, Any] = {}
        anomalous = False
        for call in calls_raw or ():
            k = len(parts)
            part: dict[str, Any] = {"t": "tool_call", "name": rec.enc(call["function"], f"/parts/{k}/name"),
                                    "args": rec.enc(call["args"], f"/parts/{k}/args")}
            if "id" in call:
                part["provider_call_id"] = rec.enc(call["id"], f"/parts/{k}/provider_call_id")
                if call["id"] == "":
                    unk[f"/parts/{k}/provider_call_id"] = "ambiguous"
                if not call["id"]:
                    anomalous = True
            else:
                unk[f"/parts/{k}/provider_call_id"] = "not_recorded"
                anomalous = True
            unk[f"/parts/{k}/args_raw"] = "not_recorded"
            if "placeholder_args" in call:
                placeholders[str(k)] = rec.enc(call["placeholder_args"], json_pointer("ext", "agentdojo", "placeholder_args", str(k)))
            parts.append(part)
            calls.append([part_id(mid, k), call, False])
        ids = [c[1].get("id") for c in calls]
        if len([x for x in ids if isinstance(x, str) and x]) != len({x for x in ids if isinstance(x, str) and x}):
            anomalous = True
        if anomalous:
            self.detected.add("agentdojo.provider_call_id_anomalies")
        if placeholders:
            rec.ext()["placeholder_args"] = placeholders
        if calls_raw is None and "tool_calls" not in message:
            rec.ext()["calls_form"] = "absent"
        elif calls_raw == []:
            rec.ext()["calls_form"] = "empty_list"
        if self.v1 and calls and self.detect("agentdojo.args_mutated_in_place"):
            rules.append(self.R("agentdojo.args_are_effective@1"))  # unscoped: args are O by source (D.6.11 item 7)
        if not aux and self.quirk_on(_LOCAL_QUIRK):
            self._local_tags(rec, mid, message.get("content"), len(calls))
        rec.data["parts"] = parts
        rec.data["evf"] = evf
        rec.data["rule"] = rules
        if unk:
            rec.data["unk"] = unk
        reply = None if aux or calls_raw else self._message_author(i, message, "assistant")
        if reply is not None:  # D-586: the defence replaced the model's reply
            self._defence_reply(body, rec, mc_id, reply, i)
        body.append(rec)
        self._push(mid)
        if not aux and reply is None:
            self.agent_assistants.append(mid)
            self.agent_calls[mid] = [str(c[0]) for c in calls]
        batch = {"msg": mid, "calls": calls, "results": 0}
        if calls:
            self.batches.append(batch)
        links = self._link(batch, [self.messages[t] for t in tools])
        batch["by_id"] = any(tag == "D" for _i, tag, _p in links)  # the D.6.6.1 id path links all results or none
        for position, t in enumerate(tools):
            self._tool(body, t, self.messages[t], batch if calls or tools else None, links[position], position)

    def _local_tags(self, rec: _Rec, mid: str, content: object, n_calls: int) -> None:
        """D.6.6 local-model row (quirk ``local_model_raw_completion``, declared pipelines only): the number of
        ``<function=`` tags in the raw completion text goes to ``ext.agentdojo.local_model_tag_count``; more tags than
        parsed calls gives ``agentdojo.local_parse_drop_possible`` (I, ``agentdojo.local_model_tag_count@1``)."""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(str(b.get("content")) for b in content
                             if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("content"), str))
        else:
            return
        tags = text.count(_LOCAL_TAG)
        if tags == 0:
            return
        rec.ext()["local_model_tag_count"] = tags
        if tags > n_calls:
            self.issue("agentdojo.local_parse_drop_possible", [mid], "agentdojo.local_model_tag_count@1")

    def _link(self, batch: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> list[tuple[int | None, str, str | None]]:
        """D.6.6.1: ``(call index, evidence tag, problem issue)`` per tool message of the batch."""
        calls = batch["calls"]
        ids = [c[1].get("id") for c in calls]
        tcids = [r.get("tool_call_id") for r in results]
        unique = bool(calls) and all(isinstance(x, str) and x for x in ids) and len(set(ids)) == len(ids)
        if unique and all(t in ids for t in tcids) and len(set(map(str, tcids))) == len(tcids):
            return [(ids.index(t), "D", None) for t in tcids]
        out: list[tuple[int | None, str, str | None]] = []
        for p, result in enumerate(results):
            if p >= len(calls):
                out.append((None, "I", "orphan_tool_result"))
                continue
            echo, call = result.get("tool_call") or {}, calls[p][1]
            if echo.get("function") == call.get("function") and _lexical(echo.get("args")) == _lexical(call.get("args")):
                out.append((p, "I", None))
            else:
                out.append((None, "I", "call_result_link_conflict"))
        return out

    # ---------------------------------------------------------------------------------------------- tool messages
    def _tool(self, body: list[Any], i: int, message: Mapping[str, Any], batch: dict[str, Any] | None,
              link: tuple[int | None, str, str | None] | None, position: int) -> None:
        index, tag, problem = link if link is not None else (None, "I", "orphan_tool_result")
        link_rule = "agentdojo.call_id_unique_match@1" if tag == "D" else "agentdojo.positional_match@1"
        call_part: str | None = None
        call: Mapping[str, Any] | None = None
        if batch is not None and index is not None:
            call_part, call = batch["calls"][index][0], batch["calls"][index][1]
            batch["calls"][index][2] = True
        if batch is not None:
            batch["results"] += 1
        view = ToolMessage(i, message, call, call_part)
        decision = self._hook_decision(view)
        orphan = self._hook_orphan(view) if problem == "orphan_tool_result" and call_part is None else None
        if decision is not None:
            self._decision_message(body, view, decision[0], decision[1], batch, tag, link_rule, problem)
            return
        echo = message["tool_call"]
        error = message.get("error")
        content = message.get("content")
        te_id = f"te{self.n_te}"
        self.n_te += 1
        te = _Rec(k="tool_execution", id=te_id, actor="env", scope="att0", ev=self.C(self.r_one_exec), by="source")
        self.te_of[i] = te_id
        if batch is not None:
            self.request_of[i] = batch["msg"]
        te.data["name"] = te.enc(echo["function"], "/name")
        te.data["args"] = te.enc(echo["args"], "/args")
        te.data["status"] = tool_status(error)
        evf: dict[str, str] = {"/args": "O", "/name": "O"}
        rules = [self.R(self.r_one_exec), self.R(link_rule, "/call"), self.R("agentdojo.tool_status_from_error@1", "/status")]
        unk = {"/args_effective": "not_recorded", "/returned": "not_recorded", "/t": "not_recorded"}
        if self.v1 and self.quirk_on("agentdojo.args_mutated_in_place"):
            # D.6.6 v1.k14 row: the logged args are post-normalisation, i.e. the effective arguments (D)
            te.data["args_effective"] = te.enc(echo["args"], "/args_effective")
            evf["/args_effective"] = "D"
            rules.append(self.R("agentdojo.args_are_effective@1", "/args_effective"))
            del unk["/args_effective"]
        after: list[dict[str, str]] = []
        if call_part is not None and batch is not None:
            te.data["call"] = call_part
            after.append({"b": "causal", "id": batch["msg"]})
            if tag != "D":
                evf["/call"] = tag
        elif orphan is not None:  # a hook: an execution a defence requested, with no assistant call (C.3.7 requested_by)
            te.data["requested_by"] = self.def_ids[orphan.requester]
            evf["/requested_by"] = "I"
            rules.remove(self.R(link_rule, "/call"))  # there is no call to link: exactly one of call, requested_by, unk /call
            rules.append(self.R(orphan.rules[0], "/requested_by"))
        else:
            unk["/call"] = "ambiguous"
        if call_part is not None:
            rules.append(self.R("aer.execution_after_call@1", "/after"))
        if position > 0 and self.prev is not None:
            after.append({"b": "pos", "id": self.prev})
            rules.append(self.R("agentdojo.tools_executed_sequentially@1", "/after"))
        if after:
            te.data["after"] = after
        te.data.update(evf=evf, rule=rules, src=[_loc(f"/messages/{i}/tool_call"), _loc(f"/messages/{i}/error")], unk=unk)
        for hook, hook_view in self.hooks:
            if hook.tool_execution is not None:
                hook.tool_execution(hook_view, view, te.data)
        body.append(te)

        detector = self._detector()
        sentinel_seen = self._is_sentinel(content)
        redacted = sentinel_seen and detector is not None
        if sentinel_seen:
            redacted = self.detect("agentdojo.pi_detector_redaction") and redacted
        generator = te_id
        if redacted:
            assert detector is not None
            dc_id = f"dc{self.n_dc}"
            self.n_dc += 1
            body.append({"k": "decision", "id": dc_id, "actor": self.def_ids[detector], "scope": "att0",
                         "subject": te_id, "verdict": "redact", "after": [{"b": "causal", "id": te_id}], "ev": "I",
                         "rule": [self.R("agentdojo.pi_detector_sentinel@1"), self.R("aer.decision_after_subject@1", "/after")],
                         "src": [_loc(f"/messages/{i}/content")],
                         "unk": {"/original": "overwritten", "/reason": "not_recorded", "/t": "not_recorded"}})
            generator = dc_id

        mid = f"m{i}"
        msg = _Rec(k="message", id=mid, scope="att0", role="tool", generated_by=generator,
                   after=[{"b": "causal", "id": generator}], ev="O", by="source", src=[_loc(f"/messages/{i}")])
        part = self._result_part(msg, content, error, mid)
        mevf: dict[str, str] = {}
        mrules: list[str] = []
        munk: dict[str, str] = {}
        if redacted:
            assert detector is not None
            msg.data["actor"] = self.def_ids[detector]
            mevf.update({"/actor": "I", "/after": "I", "/generated_by": "I"})
            mrules += [self.R("agentdojo.pi_detector_sentinel@1", "/actor"), self.R("agentdojo.pi_detector_sentinel@1", "/generated_by")]
        else:
            msg.data["actor"] = "env"
            mevf.update({"/after": self.C(self.r_one_exec), "/generated_by": self.C(self.r_one_exec)})
            mrules.append(self.R(self.r_one_exec, "/generated_by"))
        if call_part is not None:
            part["responds_to"] = call_part
            mevf["/parts/0/responds_to"] = tag
        elif orphan is not None:
            munk["/parts/0/responds_to"] = "not_recorded"
        else:
            munk["/parts/0/responds_to"] = "ambiguous"
        mrules.append(self.R(orphan.rules[0] if orphan is not None and call_part is None else link_rule, "/parts/0/responds_to"))
        mrules.append(self.R("aer.output_after_generator@1", "/after"))
        tcid = message.get("tool_call_id")
        if call is None or "id" not in call or _lexical(call.get("id")) != _lexical(tcid):
            msg.ext()["tool_call_id"] = msg.enc(tcid, "/ext/agentdojo/tool_call_id")
        if self.def_ids.get("spotlighting_with_delimiting") is not None and self.detect("agentdojo.spotlighting_delimiters"):
            msg.ext()["content_state"] = "post_defence"
            mevf["/ext/agentdojo/content_state"] = "I"
            mrules.append(self.R("agentdojo.spotlighting_content@1", "/ext/agentdojo/content_state"))
        msg.data["parts"] = [part]
        msg.data.update(evf=mevf, rule=mrules)
        if munk:
            msg.data["unk"] = munk
        body.append(msg)
        self._push(mid)
        if orphan is not None:
            self.issue(problem or "orphan_tool_result", [te_id, mid], orphan.rules[0], severity=orphan.severity)
        elif problem is not None:
            self.issue(problem, [te_id, mid], link_rule)

    def _hook_orphan(self, view: ToolMessage) -> OrphanRequest | None:
        """A hook's :class:`OrphanRequest` for a tool message no assistant call answers; the requester must be a defence
        actor of this file, else the message stays an ambiguous execution."""
        for hook, hook_view in self.hooks:
            if hook.orphan_tool_result is not None:
                request = hook.orphan_tool_result(hook_view, view)
                if request is not None and request.requester in self.def_ids:
                    return request
        return None

    def _result_part(self, msg: _Rec, content: object, error: object, mid: str) -> dict[str, Any]:
        part: dict[str, Any] = {"t": "tool_result"}
        block = single_text_block(content) if self.v1 else None
        if block is not None:  # v1.k14: the executor wraps the formatted output in one text block (D.10.4a)
            part["text"] = msg.enc(block, "/parts/0/text")
        elif isinstance(content, list):
            part["value"] = msg.enc(content, "/parts/0/value")
            self.issue("agentdojo.multi_block_tool_content", [mid], "agentdojo.tracelogger_record_shape@1", severity="info")
        else:
            part["text"] = msg.enc(content, "/parts/0/text")
        part["error"] = msg.enc(error, "/parts/0/error")
        return part

    def _log_end(self, body: list[Any]) -> None:
        """The ``log_end`` hooks (D.6.6 abort row, R10): at most one ``decision`` after the messages, about how the log
        ends. Nothing is written for a profile without such a hook."""
        if not any(hook.log_end is not None for hook, _v in self.hooks):
            return
        msgs = self.messages
        last = len(msgs) - 1 if msgs else None
        role = msgs[last].get("role") if last is not None and isinstance(msgs[last], Mapping) else None
        trailing: list[int] = []
        if last is not None:
            k = last
            while k >= 0 and isinstance(msgs[k], Mapping) and msgs[k].get("role") == "tool":
                trailing.insert(0, k)
                k -= 1
        requests = {self.request_of[k] for k in trailing if k in self.request_of}
        end = LogEnd(index=last, role=str(role) if isinstance(role, str) else None,
                     tool_executions=tuple(self.te_of[k] for k in trailing if k in self.te_of),
                     tool_messages=tuple(f"m{k}" for k in trailing),
                     request=next(iter(requests)) if len(requests) == 1 else None)
        for hook, hook_view in self.hooks:
            if hook.log_end is None:
                continue
            decision = hook.log_end(hook_view, end)
            if decision is None:
                continue
            actor = self.def_ids.get(decision.defence)
            if actor is None:
                raise ValueError(f"hook {hook.quirk_id}: defence {decision.defence!r} is not an actor of this file")
            if decision.subject not in (*end.tool_executions, *end.tool_messages, end.request):
                raise ValueError(f"hook {hook.quirk_id}: {decision.subject!r} is not an id of the log's end")
            dc_id = f"dc{self.n_dc}"
            self.n_dc += 1
            body.append({"k": "decision", "id": dc_id, "actor": actor, "scope": "att0", "subject": decision.subject,
                         "verdict": decision.verdict, "after": [{"b": "causal", "id": end.tool_messages[-1]
                                                                 if end.tool_messages else decision.subject}],
                         "ev": decision.ev,
                         "rule": [*(self.R(r) for r in decision.rules), self.R("aer.decision_after_subject@1", "/after")],
                         "src": [_loc(f"/messages/{last}")] if last is not None else [_loc("")],
                         "unk": {"/reason": "not_recorded", "/t": "not_recorded"}})
            return

    def _hook_decision(self, view: ToolMessage) -> tuple[ToolDecision, QuirkHook] | None:
        """D.6.6 row precedence: the PI-detector sentinel row first, then the hooks' decision rows (denials, declines)."""
        if not any(hook.tool_message is not None for hook, _v in self.hooks):
            return None
        if self._is_sentinel(view.message.get("content")) and self._detector() is not None:
            return None
        for hook, hook_view in self.hooks:
            if hook.tool_message is not None:
                decision = hook.tool_message(hook_view, view)
                if decision is not None:
                    return decision, hook
        return None

    def _decision_message(self, body: list[Any], view: ToolMessage, decision: ToolDecision, hook: QuirkHook,
                          batch: dict[str, Any] | None, tag: str, link_rule: str, problem: str | None) -> None:
        """A tool message that records a defence decision (RF-3): ``dc<n>`` with no ``tool_execution``, then the message
        ``generated_by`` it (D.6.6 denial and decline rows; :class:`~agentprov.adapters.agentdojo.quirks.ToolDecision`)."""
        i, message = view.index, view.message
        actor = self.def_ids.get(decision.defence)
        if actor is None:
            raise ValueError(f"hook {hook.quirk_id}: defence {decision.defence!r} is not an actor of this file")
        subject = view.call_part or (batch["msg"] if batch is not None else None)
        if subject is None:
            # regeneration-batch item 93 (CD-23): no call part and no batch, so nothing the decision was about is
            # recorded; the previous message is no subject by position (invariant 2). The defence's message stays, with
            # no decision and no execution (AD-03), its generator not recorded and its call ambiguous.
            self._subjectless_decline(body, view, decision, link_rule)
            return
        dc_id = f"dc{self.n_dc}"
        self.n_dc += 1
        dc = _Rec(k="decision", id=dc_id, actor=actor, scope="att0", subject=subject, verdict=decision.verdict, ev=decision.ev)
        cause = batch["msg"] if batch is not None else subject.split("#", 1)[0]
        dc.data["after"] = [{"b": "causal", "id": cause}]
        rules = [self.R(r) for r in decision.rules] + [self.R("aer.decision_after_subject@1", "/after")]
        rules += [self.R(r, p) for r, p in decision.scoped]
        unk = {"/t": "not_recorded"}
        src = [_loc(f"/messages/{i}")]
        evf = dict(decision.evf)
        if decision.reason is not None:
            field = "error" if decision.reason == "error" else "content"
            value = message.get(field) if field == "error" else view.text
            if isinstance(value, str):
                dc.data["reason"] = dc.enc(value, "/reason")
                dc.data["by"] = "source"
                evf["/reason"] = "O"
                src = [_loc(f"/messages/{i}/{field}")]
            else:
                unk["/reason"] = "not_recorded"
        else:
            unk["/reason"] = "not_recorded"
        if evf:
            dc.data["evf"] = dict(sorted(evf.items()))
        dc.data.update(rule=rules, src=src, unk=unk)
        for ns, members in decision.ext.items():
            dc.data.setdefault("ext", {})[ns] = dict(members)
        body.append(dc)
        mid = f"m{i}"
        msg = _Rec(k="message", id=mid, scope="att0", role="tool", actor=actor, generated_by=dc_id,
                   after=[{"b": "causal", "id": dc_id}], ev="O", by="source", src=[_loc(f"/messages/{i}")])
        part = self._result_part(msg, message.get("content"), message.get("error"), mid)
        mevf: dict[str, str] = {"/actor": decision.ev, "/after": decision.ev, "/generated_by": decision.ev}
        mrules = [self.R(decision.rules[0], "/actor"), self.R(decision.rules[0], "/generated_by")]
        munk: dict[str, str] = {}
        if view.call_part is not None:
            part["responds_to"] = view.call_part
            mevf["/parts/0/responds_to"] = tag
        else:
            munk["/parts/0/responds_to"] = "ambiguous"
        mrules += [self.R(link_rule, "/parts/0/responds_to"), self.R("aer.output_after_generator@1", "/after")]
        tcid = message.get("tool_call_id")
        if view.call is None or "id" not in view.call or _lexical(view.call.get("id")) != _lexical(tcid):
            msg.ext()["tool_call_id"] = msg.enc(tcid, "/ext/agentdojo/tool_call_id")
        msg.data.update(parts=[part], evf=mevf, rule=mrules)
        if munk:
            msg.data["unk"] = munk
        body.append(msg)
        self._push(mid)
        if problem is not None:
            self.issue(problem, [dc_id, mid], link_rule)

    def _subjectless_decline(self, body: list[Any], view: ToolMessage, decision: ToolDecision, link_rule: str) -> None:
        """A defence-written tool message (the hook's rule attributes it) whose refused call is nowhere in the log."""
        i, message = view.index, view.message
        actor = self.def_ids[decision.defence]
        mid = f"m{i}"
        msg = _Rec(k="message", id=mid, scope="att0", role="tool", actor=actor, ev="O", by="source",
                   src=[_loc(f"/messages/{i}")])
        part = self._result_part(msg, message.get("content"), message.get("error"), mid)
        msg.ext()["tool_call_id"] = msg.enc(message.get("tool_call_id"), "/ext/agentdojo/tool_call_id")
        msg.data.update(parts=[part], evf={"/actor": decision.ev}, rule=[self.R(decision.rules[0], "/actor")],
                        unk={"/generated_by": "not_recorded", "/parts/0/responds_to": "ambiguous"})
        body.append(msg)
        self._push(mid)
        self.issue("orphan_tool_result", [mid], link_rule)

    def _hook_user_decision(self, i: int, message: object) -> tuple[ToolDecision, QuirkHook] | None:
        """A ``user`` message of an unknown key set that a hook turns into a defence-authored message (D.6.6 ``error``-key
        row). It needs an earlier agent assistant message to be the decision's subject, a string ``content`` or one text
        block, and a string ``error`` (the reason); anything else stays an unknown shape."""
        if not isinstance(message, dict) or message.get("role") != "user" or not self.agent_assistants:
            return None
        content = message.get("content")
        if not (isinstance(content, str) or (isinstance(content, list) and all(isinstance(b, dict) for b in content))):
            return None
        view = UserMessage(i, message)
        for hook, hook_view in self.hooks:
            if hook.user_message is not None:
                decision = hook.user_message(hook_view, view)
                if decision is not None and decision.reason != "content" and (
                        decision.reason is None or isinstance(message.get("error"), str)):
                    return decision, hook
        return None

    def _user_decision(self, body: list[Any], i: int, message: Mapping[str, Any], decision: ToolDecision) -> None:
        """A defence-authored ``user`` message: a ``decision`` (subject: the rejected call part of the previous agent
        assistant message when it made exactly one call, else that message) and the message ``generated_by`` it, role kept."""
        actor = self.def_ids.get(decision.defence)
        if actor is None:
            raise ValueError(f"hook: defence {decision.defence!r} is not an actor of this file")
        assistant = self.agent_assistants[-1]
        parts = self.agent_calls.get(assistant, [])
        subject = parts[0] if len(parts) == 1 else assistant
        dc_id = f"dc{self.n_dc}"
        self.n_dc += 1
        dc = _Rec(k="decision", id=dc_id, actor=actor, scope="att0", subject=subject, verdict=decision.verdict, ev=decision.ev)
        dc.data["after"] = [{"b": "causal", "id": assistant}]
        rules = [self.R(r) for r in decision.rules] + [self.R("aer.decision_after_subject@1", "/after")]
        rules += [self.R(r, p) for r, p in decision.scoped]  # D.6.13: a hook's tags and scoped rules, as for tool decisions
        unk = {"/t": "not_recorded"}
        src = [_loc(f"/messages/{i}")]
        evf = dict(decision.evf)
        value = message.get("error")
        if decision.reason == "error" and isinstance(value, str):
            dc.data["reason"] = dc.enc(value, "/reason")
            dc.data["by"] = "source"
            evf["/reason"] = "O"
            src = [_loc(f"/messages/{i}/error")]
        else:
            unk["/reason"] = "not_recorded"
        if evf:
            dc.data["evf"] = dict(sorted(evf.items()))
        dc.data.update(rule=rules, src=src, unk=unk)
        for ns, members in decision.ext.items():
            dc.data.setdefault("ext", {})[ns] = dict(members)
        body.append(dc)
        mid = f"m{i}"
        msg = _Rec(k="message", id=mid, scope="att0", role="user", actor=actor, generated_by=dc_id,
                   after=[{"b": "causal", "id": dc_id}], ev="O", by="source", src=[_loc(f"/messages/{i}")])
        msg.data["parts"] = self._content_parts(msg, message.get("content"))
        msg.data.update(evf={"/actor": decision.ev, "/after": decision.ev, "/generated_by": decision.ev},
                        rule=[self.R(decision.rules[0], "/actor"), self.R(decision.rules[0], "/generated_by"),
                              self.R("aer.output_after_generator@1", "/after")])
        body.append(msg)
        self._push(mid)

    def _sentinel(self) -> str:
        quirk = self.fam.quirk("agentdojo.pi_detector_redaction")
        value = quirk.params.get("sentinel") if quirk is not None else None
        return value if isinstance(value, str) else DEFAULT_SENTINEL

    def _is_sentinel(self, content: object) -> bool:
        """Whether a tool message's content is the PI-detector replacement: the sentinel string, or (``v1.k14``) the one
        text block holding it (``PromptInjectionDetector.transform`` writes ``[text_content_block_from_string(...)]``)."""
        text = single_text_block(content) if self.v1 else None
        return (content if text is None else text) == self._sentinel()

    def _detector(self) -> str | None:
        """The defence actor whose redaction the sentinel row reads: the first of the quirk's ``params.defences`` (default
        ``transformers_pi_detector``) that is an actor of this file."""
        quirk = self.fam.quirk("agentdojo.pi_detector_redaction")
        names = quirk.params.get("defences", _DEFAULT_DETECTORS) if quirk is not None else _DEFAULT_DETECTORS
        return next((str(n) for n in names if str(n) in self.def_ids), None)

    def _trailing_calls(self) -> None:
        """Calls with no tool message: ``unexecuted_tool_call`` in the last agent message, else ``missing_tool_result``."""
        last = self.agent_assistants[-1] if self.agent_assistants else None
        for batch in self.batches:
            # regeneration-batch item 89 (CD-12): linked by id, every unlinked call has no tool message, whatever its
            # index; by position, results at p < k that did not link are conflicts (call_result_link_conflict)
            pending = [pid for k, (pid, _call, linked) in enumerate(batch["calls"])
                       if not linked and (batch.get("by_id") or k >= batch["results"])]
            if not pending:
                continue
            if (dropped := self._hook_unexecuted(batch, pending)) is not None:  # D-592: a defence dropped them
                self.issue("unexecuted_tool_call", pending, dropped.rules[0])
                continue
            if batch["msg"] == last:
                self.detect("agentdojo.unexecuted_trailing_calls")
                self.issue("unexecuted_tool_call", pending, self.cite.cite("agentdojo.unexecuted_trailing_calls@1"))
            else:
                self.issue("missing_tool_result", pending, self.cite.cite("agentdojo.unexecuted_trailing_calls@1"), severity="error")

    def _hook_unexecuted(self, batch: Mapping[str, Any], pending: Sequence[str]) -> BatchIntervention | None:
        """A hook's :class:`BatchIntervention` for calls with no tool message (D-592)."""
        view = CallBatch(str(batch["msg"]), tuple(c[1] for c in batch["calls"]), tuple(pending))
        for hook, hook_view in self.hooks:
            if hook.unexecuted_calls is not None and (found := hook.unexecuted_calls(hook_view, view)) is not None:
                return found
        return None

    # ---------------------------------------------------------------------------------------------- judgements
    def _judgements(self, body: list[Any]) -> None:
        d = self.doc
        ids: list[str] = []
        missing = [k for k in ("utility", "security", "duration") if k not in d]
        null_outcome = False
        for spec in self.fam.outcomes.get("judgements", ()):
            name, field = str(spec["name"]), str(spec["field"])
            if field not in d:
                continue
            value = d[field]
            null_outcome = null_outcome or value is None
            jid = f"j{len(ids)}"
            src = [_loc(json_pointer(field))]
            if name == "security":
                src.append(_loc("/attack_type"))
            src.append(_loc("/error"))
            if self.error is not None:
                self.detect("agentdojo.run_error_imposes_outcome")
                origin, rule = "harness_default", self._run_error_rule()
            elif name == "security" and self.attack is None:
                self.detect("agentdojo.benign_security_constant")
                origin, rule = "harness_default", "agentdojo.benign_security_constant@1"
            elif name == "security" and self.attack in self.dos:
                self.detect("agentdojo.dos_security_not_utility")
                origin, rule = "harness_rule", "agentdojo.dos_security_rule@1"
            else:
                origin, rule = "checker", "agentdojo.checker_outcome@1"
            record: dict[str, Any] = {"k": "judgement", "id": jid, "actor": "bench", "subject": "run", "name": name,
                                      "value": value, "origin": origin, "ev": "O", "by": "benchmark",
                                      "evf": {"/origin": self.C(rule)},  # the origin takes its rule's class (AER-V14)
                                      "rule": [self.R(rule, "/origin")], "src": src}
            if origin == "checker":  # what the checker read is not recorded; the suite's checker inputs are asserted
                record["unk"] = {"/inputs": "not_recorded"}
                record["rule"].append(self.R("agentdojo.checker_inputs_unverified@1", "/inputs"))
            body.append(record)
            ids.append(jid)
        if self.error is not None and ids:
            self.issue("outcome_imposed_by_runner", ids, self.cite.cite(self._run_error_rule()))
        recorded = [r for r in body if isinstance(r, dict) and r.get("k") == "judgement"]
        for hook, view in self.hooks:  # D.6.7 "Recomputations": released by the source, beside the recorded ones
            for extra in (hook.judgements(view, recorded) if hook.judgements is not None else ()):
                body.append({"k": "judgement", "id": f"j{len(ids)}", **{k: v for k, v in extra.items() if k != "id"}})
                ids.append(f"j{len(ids)}")
        if missing or null_outcome:
            self.detect("agentdojo.incomplete_run")
            code = "no_outcome_recorded" if not ids and not self.messages else "incomplete_run"
            self.issue(code, ["run"], "agentdojo.incomplete_run@1")
        if self.unit_kind == "outcome_only":
            self.detect("agentdojo.empty_messages_with_outcome" if ids else "agentdojo.empty_messages_without_outcome")
            self.issue("no_execution_observed", ["exec"], "agentdojo.no_execution_observed@1")

    def _run_error_rule(self) -> str:
        """The outcome-origin rule of a run error (D.6.7 row 1): the first rule of the profile's declared
        ``run_error_imposes_outcome`` quirk (``agentdyn.json_decode_error_imposed@1``, ``survey.internal_server_error_patch@1``),
        else ``agentdojo.run_error_imposed_outcome@1``."""
        quirk = self.fam.quirk("agentdojo.run_error_imposes_outcome")
        if quirk is not None and quirk.rules and quirk.matches(self.facets):
            return quirk.rules[0]
        return "agentdojo.run_error_imposed_outcome@1"

    def _undeclared_quirks(self) -> None:
        """D.6.4: a quirk seen in the data that the profile does not declare for this file is reported, not applied."""
        for defence, quirk in _DEFENCE_QUIRKS.items():
            if defence in self.def_ids:
                self.detected.add(quirk)
        for quirk_id in sorted(self.detected):
            if not self.quirk_on(quirk_id):
                self.issue("agentdojo.undeclared_quirk", ["exec"], _QUIRK_RULES[quirk_id], detail=quirk_id)
