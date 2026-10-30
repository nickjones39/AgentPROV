"""The profile census: the ``observed`` counts of a profile's quirks, recomputed from sealed AERs (docs/architecture
D.6.10 item 3, D.6.12 item 8).

Every ``observed`` key a profile declares for a part is a sum over the AERs of that part's full pinned snapshot of a
per-file count. The per-file functions of the generic quirks are :data:`GENERIC`; a source-specific quirk supplies its
own through ``QuirkHook.census`` (:mod:`agentprov.adapters.agentdojo.quirks`). Nothing here reads source bytes: the
census reads only what the mapper wrote (records, rule citations and seal issues), so a count that cannot be recomputed
from the AER is not a checkable count.

* :func:`census_file` -> ``{quirk id: {key: count}}`` for one AER (every known key);
* :func:`add` sums them; :func:`declared` reads a profile's ``observed`` table for a part;
* :func:`compare` lists every declared key whose measured total differs, and every declared key no function computes.

``tools/agentdojo/profile_census.py`` drives it over a snapshot in the bare fetch cache; the ``full_corpus`` test
``tests/full_corpus/test_profile_census.py`` asserts the comparison is empty for every profile part whose snapshot is
present locally.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Final

from agentprov.adapters.agentdojo.profile import FamilyTable
from agentprov.adapters.agentdojo import quirks
from agentprov.adapters.agentdojo.quirks import CensusFile
from agentprov.adapters.code_verification import reading_of

__all__ = ["GENERIC", "add", "census_file", "compare", "declared"]

Count = Callable[[CensusFile], int]


def _task(cf: CensusFile) -> Mapping[str, Any]:
    task = cf.header.get("task")
    return task if isinstance(task, Mapping) else {}


def _tool_call_parts(cf: CensusFile) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    out: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for record in cf.of_kind("message"):
        if record.get("role") == "assistant":
            out.extend((record, p) for p in record.get("parts", ()) if p.get("t") == "tool_call")
    return out


def _id_unk(cf: CensusFile, reason: str) -> int:
    n = 0
    for record in cf.of_kind("message"):
        if record.get("role") == "assistant":
            n += sum(1 for pointer, why in (record.get("unk") or {}).items()
                     if pointer.endswith("/provider_call_id") and why == reason)
    return n


def _null_ids(cf: CensusFile) -> int:
    return sum(1 for _m, part in _tool_call_parts(cf) if "provider_call_id" in part and part["provider_call_id"] is None)


def _duplicate_ids(cf: CensusFile) -> int:
    for record in cf.of_kind("message"):
        if record.get("role") == "assistant":
            named = [p.get("provider_call_id") for p in record.get("parts", ()) if p.get("t") == "tool_call"]
            named = [i for i in named if isinstance(i, str) and i]
            if len(named) != len(set(named)):
                return 1
    return 0


def _colliding_empty_ids(cf: CensusFile) -> int:
    """1 when the file has two or more calls with an empty id: positional links only (D.6.6.1 item 2)."""
    return int(sum(1 for _m, p in _tool_call_parts(cf) if p.get("provider_call_id") == "") >= 2)


def _repeated_ids(cf: CensusFile) -> int:
    """1 when a non-empty call id occurs more than once anywhere in the file."""
    named = [p.get("provider_call_id") for _m, p in _tool_call_parts(cf)]
    named = [i for i in named if isinstance(i, str) and i]
    return int(len(named) != len(set(named)))


def _placeholders(cf: CensusFile, *, null_only: bool) -> int:
    n = 0
    for record in cf.of_kind("message"):
        values = ((record.get("ext") or {}).get("agentdojo") or {}).get("placeholder_args") or {}
        n += sum(1 for v in values.values() if not null_only or v is None)
    return n


def _tag_turns(cf: CensusFile) -> int:
    n = 0
    for record in cf.of_kind("message"):
        tags = ((record.get("ext") or {}).get("agentdojo") or {}).get("local_model_tag_count")
        calls = sum(1 for p in record.get("parts", ()) if p.get("t") == "tool_call")
        n += int(isinstance(tags, int) and tags > 0 and calls == 0)
    return n


def _bench_code_unknown(cf: CensusFile) -> int:
    bench = next((r for r in cf.of_kind("actor") if r.get("id") == "bench"), {})
    variant = (cf.header.get("dialect") or {}).get("variant", "")
    return int(str(variant).startswith("v1.k14") and "/code" in (bench.get("unk") or {}))


def _cites(rule: str) -> Count:
    return lambda cf: int(cf.cites(rule))


def _issue(*codes: str) -> Count:
    return lambda cf: int(any(cf.has_issue(c) for c in codes))


def _trailing(cf: CensusFile) -> list[Mapping[str, Any]]:
    """The ``unexecuted_tool_call`` issues of the trailing-calls rule (a defence's dropped calls cite its own rule, D-592)."""
    return [i for i in cf.issues if i.get("code") == "unexecuted_tool_call"
            and reading_of(str(i.get("rule", ""))) == "agentdojo.unexecuted_trailing_calls@1"]


def _defence(name: str) -> Count:
    return lambda cf: int(_task(cf).get("defense_id") == name)


#: Per-file counts of the generic quirks (D.6.4), by quirk id and ``observed`` key.
GENERIC: Final[Mapping[str, Mapping[str, Count]]] = {
    "agentdojo.benign_security_constant": {
        "files": lambda cf: int(_task(cf).get("attack_id") is None),
        "origin_rule_applied": _cites("agentdojo.benign_security_constant@1"),
    },
    "agentdojo.dos_security_not_utility": {"files": _cites("agentdojo.dos_security_rule@1")},
    "agentdojo.silent_rerun_last_pass_only": {"null_final_logs": _issue("retry_passes_inferred")},
    "agentdojo.injection_task_as_user_task_prepass": {"files": _cites("agentdojo.injection_task_as_user_task@1")},
    "agentdojo.empty_messages_with_outcome": {"files": lambda cf: int(cf.header.get("unit") == "outcome_only")},
    "agentdojo.empty_messages_without_outcome": {
        "files": lambda cf: int(cf.header.get("unit") == "outcome_only" and not cf.of_kind("judgement")),
    },
    "agentdojo.run_error_imposes_outcome": {"files": _issue("outcome_imposed_by_runner")},
    "agentdojo.incomplete_run": {
        "files": _issue("incomplete_run", "no_outcome_recorded"),
        "null_outcome_files": lambda cf: int(any(j.get("value") is None for j in cf.of_kind("judgement"))),
    },
    "agentdojo.provider_call_id_anomalies": {
        "logs_with_absent_or_empty_ids": lambda cf: int(bool(_id_unk(cf, "not_recorded") or _id_unk(cf, "ambiguous"))),
        "calls_id_absent": lambda cf: _id_unk(cf, "not_recorded"),
        "calls_id_empty": lambda cf: _id_unk(cf, "ambiguous"),
        "calls_id_null": _null_ids,
        "null_ids": _null_ids,
        "logs_with_null_ids": lambda cf: int(_null_ids(cf) > 0),
        "logs_with_duplicate_ids": _duplicate_ids,
        "logs_with_colliding_empty_ids": _colliding_empty_ids,
        "logs_with_repeated_ids": _repeated_ids,
    },
    "agentdojo.args_mutated_in_place": {"files": _cites("agentdojo.args_are_effective@1")},
    "agentdojo.unexecuted_trailing_calls": {
        "calls": lambda cf: sum(len(i.get("ids", ())) for i in _trailing(cf)),
        "logs": lambda cf: int(bool(_trailing(cf))),
        "traces": lambda cf: int(bool(_trailing(cf))),
    },
    "agentdojo.pi_detector_redaction": {
        "logs": _cites("agentdojo.pi_detector_sentinel@1"),
        "redactions": lambda cf: sum(1 for r in cf.of_kind("decision") if r.get("verdict") == "redact"),
        "redacted_tool_messages": lambda cf: sum(1 for r in cf.of_kind("decision") if r.get("verdict") == "redact"),
    },
    "agentdojo.tool_filter_aux_llm": {
        "logs": _defence("tool_filter"),
        "logs_with_filter_messages": _cites("agentdojo.tool_filter_aux_message@1"),
    },
    "agentdojo.repeat_user_prompt_reinsertion": {
        "logs": _defence("repeat_user_prompt"),
        "logs_with_copies": _cites("agentdojo.repeat_user_prompt_copy@1"),
    },
    "agentdojo.spotlighting_delimiters": {
        "logs": _defence("spotlighting_with_delimiting"),
        "logs_with_tool_results": _cites("agentdojo.spotlighting_content@1"),
    },
    "agentdojo.local_model_raw_completion": {
        "turns_more_tags_than_calls": lambda cf: len(cf.issue_ids("agentdojo.local_parse_drop_possible")),
        "turns_tags_no_calls": _tag_turns,
    },
    "agentdojo.placeholder_args_never_injection_evidence": {
        "present": lambda cf: _placeholders(cf, null_only=False),
        "present_and_null": lambda cf: _placeholders(cf, null_only=True),
    },
    "agentdojo.package_version_not_code_identity": {"files_without_package_version": _bench_code_unknown},
}


def _functions() -> dict[str, dict[str, Count]]:
    out = {quirk: dict(keys) for quirk, keys in GENERIC.items()}
    for quirk_id, hook in quirks.hooks().items():
        out.setdefault(quirk_id, {}).update(hook.census)
    return out


def census_file(cf: CensusFile) -> dict[str, dict[str, int]]:
    """Every known count of one AER, by quirk id and key."""
    return {quirk: {key: int(fn(cf)) for key, fn in keys.items()} for quirk, keys in _functions().items()}


def add(totals: dict[str, dict[str, int]], one: Mapping[str, Mapping[str, int]]) -> dict[str, dict[str, int]]:
    """Add one file's counts into ``totals`` (in place) and return it."""
    for quirk, keys in one.items():
        bucket = totals.setdefault(quirk, {})
        for key, value in keys.items():
            bucket[key] = bucket.get(key, 0) + int(value)
    return totals


def declared(table: FamilyTable, part: str) -> dict[str, dict[str, int]]:
    """The profile's ``observed`` counts for ``part``, by quirk id (quirks without counts for the part are omitted)."""
    return {q.id: dict(q.observed[part]) for q in table.quirks if part in q.observed}


def compare(table: FamilyTable, part: str, measured: Mapping[str, Mapping[str, int]]) -> list[str]:
    """Every declared count of ``part`` that the measured totals do not reproduce, and every one nothing computes."""
    known = _functions()
    problems: list[str] = []
    for quirk, keys in sorted(declared(table, part).items()):
        for key, value in sorted(keys.items()):
            if key not in known.get(quirk, {}):
                problems.append(f"{quirk}.{key}: no census function computes it")
            elif measured.get(quirk, {}).get(key, 0) != value:
                problems.append(f"{quirk}.{key}: declared {value}, measured {measured.get(quirk, {}).get(key, 0)}")
    return problems


def totals_of(files: Iterable[CensusFile]) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = {}
    for cf in files:
        add(totals, census_file(cf))
    return totals
