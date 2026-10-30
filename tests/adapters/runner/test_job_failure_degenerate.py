"""A crashed or limited map job never drops its file (D.2.8 case 3; D.2.9 note items 6 and 12): the pinned contract per family.

On the job-failure path (``importer._Pipeline._job_failure``) the parent has no parsed value: it builds the fallback unit
from the stored artefact (``degenerate_unit``: digest, size, pinned origin, document-root locator) and asks the family's
``degenerate_header`` for the header. Two outcomes are possible, and both keep the evidence:

* the family names the task from the artefact's **path or label** (credleak, DTap, OpenHands, AgentOps, geminicli, Inspect): a
  degenerate AER seals (``adapter_defect``);
* the family names the task only from the **parsed value** (the AgentDojo/TraceLogger family with DRIFT and the
  results dialect, adprov, FooBench): since D-219 (``aer/0.2``, deferrals part C) the header omits ``task.task_id`` with
  ``unk {"/task/task_id": "not_captured"}`` (a map job that failed before reading the value), which the validator allows
  only in a degenerate file, and a degenerate AER seals. Under ``aer/0.1`` the write gate refused such a header
  (``aer.schema.required`` at ``/task/task_id``; the known open item of D.2.9 note 6). A unit whose value was read but
  holds no task id still declares ``not_recorded`` and is refused, as before.

Not assessed: the live capture paths (``agentdojo-live``, ``autodojo-live``, ``agentdyn-live``; ``capture_mapper``), whose fallback is built
by the session pipeline from a verified capture log, not from an import candidate. The D-219 header edits move the
``adapter_code_sha256`` of the agentdojo, adprov and foobench families (class 1); only crash-path AERs change.
"""

from __future__ import annotations

import zlib
from importlib import resources
from typing import Any

import pytest

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import MapContext, _degenerate, _family_classes, aer_bytes, degenerate_unit
from agentprov.aer.ids import import_execution_id, mapping_id
from agentprov.aer.rules import RuleRegistry
from agentprov.aer.writer import AerWriteError
from agentprov.raw.origins import Origin

SHA = "ab" * 32
SIZE = 1234
REPO, COMMIT, BLOB = "https://example.org/repo", "0" * 40, "1" * 40


def _member(label: str) -> Origin:
    return Origin.member("cd" * 32, label, 8, zlib.crc32(label.encode()), SIZE)


def _git(path: str) -> Origin:
    return Origin.git(REPO, COMMIT, path, BLOB)


#: The pinned outcome per family on the job-failure path: ``"seals"`` (a degenerate AER) or ``"refused"`` (the write
#: gate refuses the header for want of ``/task/task_id``; the importer registers a failed ``map.adapter_defect``). Every
#: shipped family seals since D-219.
EXPECTED: dict[str, str] = {
    "credleak": "seals",
    "dtap": "seals",
    "openhands": "seals",
    "agentops": "seals",
    "geminicli": "seals",
    "qwencode": "seals",
    "inspect": "seals",
    "autogen": "seals",  # the file-level header is named by the run file's phase label (D.22)
    "wirelog": "seals",  # phase 10m: a run named by its response log's label (wirelog.unreadable_run)
    "mcphunt": "seals",  # phase 10m: a document named by its label (mcphunt.unreadable_document)
    "agentdojo": "seals",  # D-219: aer/0.2, unk {"/task/task_id": "not_captured"}
    "adprov": "seals",  # D-219: aer/0.2, unk {"/task/task_id": "not_captured"}
    "foobench": "seals",  # D-219: aer/0.2, unk {"/task/task_id": "not_captured"}
}
#: A realistic origin of each profile's path or label grammar (the families that name the task from it need one; the
#: others get :data:`DEFAULT_ORIGIN`, which they ignore).
ORIGINS: dict[str, Origin] = {
    "credleak-p15b": _member(
        "p15b-run-data/01-injection-map/T1-file-document/test-model/run__T1__test-model__T1.9__2026-06-11T08-00-00-000Z.json"),
    "dtap-bench": _git("openaisdk/gpt-5.2/code/benign/math/57/20260220_133459.json"),
    "openagentsafety": _git("prefix/evaluation/gpt-4o/traj_safety-x.json"),
    "redcode-exec-openhands": _member("results/OH/qwen3-coder-30b-a3b/S1/bash/trajectory/oh_18_10_sh_S1-3b57f5.json"),
    "agentops-bench-pilot": _member("runs/pilot_v1_seeded/gpt55/openai_gpt-5.5/clean/safety_018_run2.json"),
    "code-agent-misalignment-geminicli": _member("RESULTS_build/cells/gemini_cli__MiniMax-M2/SK-SQLRAW__m01/gemini_stream.jsonl"),
    "redcode-exec-qwencode": _member("results/Qwen/qwen3-coder-30b-a3b-instruct/S1/python/trajectory/qwen_3_25_S1.json"),
    **{p: _member("samples/42-1_epoch_1.json")
       for p in ("survey-agentharm", "agentharm-live", "fragfuse-agentharm", "kexin-xu-01-agentharm", "whistlebench",
                 "controlarena-persistent", "atia-benchmark")},
    "autogen-guard-placement": _member("autogen-guard-placement/results/phase6/tool/runs.jsonl"),
    "what-surrounds": _member("runs_named/nova-micro__operator_spoof__0004/response_raw.json"),
    "mcphunt": Origin.from_json({"kind": "hf", "repo": "lihaonan0716/mcphunt-agent-traces", "revision": "0" * 40,
                                 "path": "data/agent_traces/main/model_a.json"}),
}
DEFAULT_ORIGIN = _git("runs/model/banking/user_task_0/none/none.json")
#: The live capture profiles (not import candidates) and a profile with no import table.
NOT_ASSESSED = {"agentdojo-live", "autodojo-live", "agentdyn-live", "autodojo-via-rope"}


def _profiles(family: str) -> list[str]:
    node = resources.files("agentprov").joinpath("adapters", family, "profiles")
    return sorted(p.name.removesuffix(".profile.toml") for p in node.iterdir() if p.name.endswith(".profile.toml"))


CASES = [(family, p) for family in sorted(EXPECTED) for p in _profiles(family) if p not in NOT_ASSESSED]


def _seal_fallback(profile_id: str, origin: Origin) -> tuple[bytes, Any]:
    """What ``_job_failure`` + ``_seal`` do with a crashed job's file: the fallback unit, its degenerate outcome, sealed."""
    profile = load_profile(profile_id)
    imp = profile.data["import"]
    _reader, mapper = _family_classes(str(imp["dialect"]), str(imp["mapper"]))
    unit = degenerate_unit(SHA, SIZE, origin, profile=profile, mapper=mapper)
    mapping = mapping_id(mapper.mapper_id, profile.id)
    ex = import_execution_id(mapping, SHA, unit.primary.locator.key())
    rules = RuleRegistry.default()
    outcome = _degenerate(unit, mapper, MapContext(profile, rules, mapping, ex), "adapter_defect", "worker.error")
    return aer_bytes(outcome, registry=rules)


@pytest.mark.parametrize(("family", "profile_id"), CASES)
def test_a_crashed_job_keeps_its_file_as_the_family_contract_says(family, profile_id):
    import json

    origin = ORIGINS.get(profile_id, DEFAULT_ORIGIN)
    if EXPECTED[family] == "seals":
        data, info = _seal_fallback(profile_id, origin)
        header = json.loads(data.split(b"\n", 1)[0])
        assert header["source_key"] == {"sha256": SHA, "loc": {"p": ""}}
        assert header["task"].get("task_id") or header.get("unk", {}).get("/task/task_id") == "not_captured"
        assert "adapter_defect" in {str(i.get("code")) for i in info.issues}
    else:
        with pytest.raises(AerWriteError) as refused:
            _seal_fallback(profile_id, origin)
        findings = {(f.code, getattr(f, "pointer", None)) for f in refused.value.findings}
        assert ("aer.schema.required", "/task/task_id") in findings


def test_every_shipped_profile_is_covered():
    """A new family or profile must get an EXPECTED entry (or be a live profile), so the contract stays pinned."""
    from agentprov.adapters.profiles import profile_families

    assert set(profile_families()) <= set(EXPECTED)
    shipped = {p for family in profile_families() for p in _profiles(family)}
    assert shipped - {p for _f, p in CASES} - NOT_ASSESSED == set()
