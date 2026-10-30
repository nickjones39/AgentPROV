"""Helpers for the ``agentops`` adapter tests (imported as ``agentops_support``; not collected).

The committed fixtures (tests/fixtures/agentops/, chosen by criterion and copied byte-identically from the pinned
archives in memory; SOURCE.json lists each member's container, label, CRC-32, size and sha256) sit at their member labels
below ``runs/`` (run files of the pilot-traces tar) and ``tasks/`` (task YAMLs of the code zip, byte-identical to the
``tasks`` git pin at tag v1.0, so a task is mapped under its ``git`` origin at that commit). The files hold
prompt-injection payloads by design: they are data, and no helper prints their content.

* :func:`map_label` maps one run the way the import pipeline's ``map`` job does (the reader's ``auxiliary_for`` plan,
  ``map_artefact_total`` with the auxiliary rows), the run under a ``member`` origin and its task under a ``git`` origin
  (D-154 method), returning the
  sealed AER and its SEM and PROV;
* :func:`modified` maps a run whose parsed JSON a test changed (derived inputs for cases the snapshot does not hold).
"""

from __future__ import annotations

import json
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from agentprov.adapters.agentops.dialect import AgentOpsTraceReader
from agentprov.adapters.runner import MapOutcome, aer_bytes, map_artefact_total
from agentprov.adapters.runner.importer import _AuxListing, aux_media, git_blob_sha1
from agentprov.adapters.semantics_profiles import load_semantics_profile
from agentprov.adapters.types import Origin
from agentprov.aer.reader import AerDocument, load_aer_bytes
from agentprov.io.canonical import sha256_hex

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures" / "agentops"
PROFILE = "agentops-bench-pilot"
TAR_SHA256 = "e185bfd037fa9fa5727dbae0eb8eba421dfb5011dfec6f4dc60b111d51e7a85f"
ZIP_SHA256 = "852a372da1d797adc5a60a95ea8f5194d8b652d4d5c19738eab152f7a57c1fed"
ZIP_ROOT = "kunwarshivam-agentops-bench-9153772/"  # the zip's root; a task's git path is its member label without it
TASKS_REPO = "https://github.com/kunwarshivam/agentops-bench"
TASKS_COMMIT = "c7b29be6c0d8201d3025d4abc1244935b83586d6"  # tag v1.0 (the tasks pin)
ROOT = "pilot_v1_seeded/"

#: Fixture criterion -> member label (docs/reports/phase10i/README.md §7; tools: the phase-10i scratch scripts).
F = {
    "payloads_failure_multicall": ROOT + "mistral_large/openrouter_mistralai_mistral-large-2512/adversarial/data_analysis_018_run2.json",
    "repeated_name_step": ROOT + "llama4_scout/openrouter_meta-llama_llama-4-scout/adversarial/data_analysis_015_run1.json",
    "empty_trace": ROOT + "qwen3_max/openrouter_qwen_qwen3-max/noisy/safety_008_run2.json",
    "loop_stuck_refusal": ROOT + "opus_4_7/anthropic_claude-opus-4-7/adversarial/code_020_run2.json",
    "noisy_safety_failure": ROOT + "llama4_scout/openrouter_meta-llama_llama-4-scout/noisy/safety_001_run2.json",
    "clean_safety_plain": ROOT + "gpt55/openai_gpt-5.5/clean/safety_018_run2.json",
    "unlisted_tool_name": ROOT + "qwen3_max/openrouter_qwen_qwen3-max/adversarial/data_analysis_014_run3.json",
    "dispatch_error": ROOT + "llama4_scout/openrouter_meta-llama_llama-4-scout/adversarial/tool_use_014_run3.json",
    "api_error_after_steps": ROOT + "qwen3_max/openrouter_qwen_qwen3-max/clean/safety_020_run3.json",
    "openrouter_payload": ROOT + "mistral_large/openrouter_mistralai_mistral-large-2512/adversarial/safety_020_run2.json",
    "timeout": ROOT + "deepseek_v32/openrouter_deepseek_deepseek-v3.2/adversarial/research_018_run1.json",
    "anthropic_payload": ROOT + "opus_4_7_part2/anthropic_claude-opus-4-7/adversarial/safety_020_run2.json",
    "task_with_context": ROOT + "llama4_scout/openrouter_meta-llama_llama-4-scout/adversarial/code_001_run3.json",
}
#: The fixtures whose PROV fails tier-4 linkage because the core engine gives an I-class unexecuted_tool_call no source
#: pointer (routed to the orchestrator; docs/reports/phase10i/README.md §9).
FAULT_FIXTURES = ("payloads_failure_multicall", "repeated_name_step", "noisy_safety_failure")


@cache
def source_entries() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads((FIXTURES / "SOURCE.json").read_text(encoding="utf-8")))


def entry(label: str) -> dict[str, Any]:
    return next(e for e in source_entries() if e["label"] == label)


def run_bytes(label: str) -> bytes:
    return (FIXTURES / "runs" / label).read_bytes()


def tasks_files() -> dict[str, bytes]:
    """Path in the ``tasks`` git pin -> bytes of every committed task YAML (copied from the zip member of that path)."""
    return {str(e["label"]).removeprefix(ZIP_ROOT): (FIXTURES / e["sample_file"]).read_bytes() for e in source_entries()
            if str(e["sample_file"]).startswith("tasks/")}


def member_origin(container: str, label: str, data: bytes, method: int = 0) -> Origin:
    return Origin.member(container, label, method, zlib.crc32(data), len(data))


@dataclass
class Mapped:
    label: str
    outcome: MapOutcome
    data: bytes
    doc: AerDocument
    sem: Any = None
    prov: Any = None

    @property
    def records(self) -> list[dict[str, Any]]:
        return self.doc.records

    @property
    def header(self) -> dict[str, Any]:
        return self.doc.header

    @property
    def issues(self) -> list[dict[str, Any]]:
        return list(self.doc.seal.get("issues", []))

    def codes(self) -> list[str]:
        return [i["code"] for i in self.issues]

    def get(self, rid: str) -> dict[str, Any]:
        found = self.doc.get(rid)
        assert found is not None, rid
        return found

    def of(self, kind: str) -> list[dict[str, Any]]:
        return self.doc.of_kind(kind)

    def annotations(self, type_: str | None = None) -> list[dict[str, Any]]:
        assert self.sem is not None
        return [a for a in self.sem.annotations if type_ is None or a["type"] == type_]


def map_label(label: str, *, data: bytes | None = None, tasks: Mapping[str, bytes] | None = None, sem: bool = False,
              prov: bool = False) -> Mapped:
    """Map one run as the import pipeline's ``map`` job would (auxiliary rows from the reader's plan)."""
    tasks = dict(tasks_files() if tasks is None else tasks)
    reader = AgentOpsTraceReader()
    listing = _AuxListing([label], {"tasks": list(tasks)})
    plan = reader.auxiliary_for(label, listing)
    rows: list[dict[str, Any]] = []
    blobs: dict[str, bytes] = {}
    for role, ref in sorted(plan.items()):
        path = ref.removeprefix("tasks:")
        raw = tasks[path]
        origin = Origin.git(TASKS_REPO, TASKS_COMMIT, path, git_blob_sha1(raw))
        rows.append({"role": role, "label": ref, "media": aux_media(ref), "sha256": sha256_hex(raw), "size": len(raw),
                     "origin": origin.to_json()})
        blobs[role] = raw
    primary = run_bytes(label) if data is None else data
    outcome, _unit = map_artefact_total(primary, member_origin(TAR_SHA256, label, primary), profile_id=PROFILE,
                                        auxiliary=rows, auxiliary_bytes=blobs)
    sealed, _info = aer_bytes(outcome)
    doc = load_aer_bytes(sealed)
    result = Mapped(label, outcome, sealed, doc)
    if sem or prov:
        from agentprov.sem.engine import annotate

        profile = load_semantics_profile("agentops.tools", SEM_VERSION)
        result.sem = annotate(doc, profile)
        if prov:
            from agentprov.prov.engine import derive

            result.prov = derive(doc, [result.sem], sem_profiles={(profile.id, profile.version): profile})
    return result


def modified(criterion: str, change: Callable[[dict[str, Any]], None], *, label: str | None = None, sem: bool = False,
             prov: bool = False, tasks: Mapping[str, bytes] | None = None) -> Mapped:
    """Map a derived run: the fixture's JSON with ``change`` applied (compact re-serialisation, never written to disk)."""
    value = json.loads(run_bytes(F[criterion]))
    change(value)
    data = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return map_label(label or F[criterion], data=data, sem=sem, prov=prov, tasks=tasks)

#: The semantics profile version the current profile selects (D-31 bump with regen items 34-37; @1 reads catalogue v1).
SEM_VERSION = 2


# --------------------------------------------------------------- in-memory runs (test_redact, test_withhold_e2e)


def _call(name: str, args: Any = None) -> dict[str, Any]:
    return {"tool_name": name, "arguments": {"code": "print(1)"} if args is None else args,
            "timestamp": "2026-01-01T00:00:00Z"}


def _result(name: str, result: Any, payload: str | None = None) -> dict[str, Any]:
    return {"tool_name": name, "result": result, "latency_ms": 1.0, "injected_failure": None, "injected_payload": payload}


def run_json(steps: list[dict[str, Any]], condition: str = "adversarial", final: str | None = "done") -> dict[str, Any]:
    return {"task_id": "safety/001", "agent_id": "openai/gpt-x", "condition": condition, "run_number": 1,
            "trace": {"task_id": "safety/001", "agent_id": "openai/gpt-x", "condition": condition, "steps": steps,
                      "total_input_tokens": 10 * len(steps), "total_output_tokens": 5 * len(steps), "total_cost_usd": 0.0,
                      "wall_time_seconds": 1.0, "completed": True, "final_output": final, "error": None},
            "scores": {}}


def step(n: int, calls: list[dict[str, Any]], results: list[dict[str, Any]], reasoning: str | None = "think") -> dict[str, Any]:
    return {"step_number": n, "llm_input_tokens": 10, "llm_output_tokens": 5, "reasoning": reasoning,
            "tool_calls": calls, "tool_results": results}
