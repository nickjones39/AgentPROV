"""``agentdojo.tracelogger`` reader: classification and robustness (docs/architecture D.6.2-D.6.3, D.6.10 item 4).

* Classification by key set: every variant of D.6.2, flags for missing outcome keys and extra keys, foreign input.
* Hypothesis property tests: arbitrary key orders, content forms and call-id forms classify consistently; mutation
  fuzzing of real logs never raises anything but ``MalformedArtefact`` or ``IngestError``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from agentdojo_support import C161_PATH, C274885, REPO_URL, base_log, c161_bytes, log_bytes, native_entries
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agentprov.adapters.agentdojo.dialect import (
    FLAG_MALFORMED,
    K11,
    K14,
    KD18_BASE,
    TraceLoggerReader,
    classify,
)
from agentprov.adapters.types import ArtefactRef, Origin
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.testing import golden

LIMITS = IngestLimits()


def _artefact(raw: bytes) -> ArtefactRef:
    origin = Origin.git(REPO_URL, C274885, "runs/gpt-4o-2024-05-13/banking/user_task_1/important_instructions/injection_task_2.json",
                        golden.git_blob_sha1(raw))
    return ArtefactRef("a0", hashlib.sha256(raw).hexdigest(), len(raw), "application/json", origin)


def _k14() -> dict[str, Any]:
    return base_log(benchmark_version="v1.2", evaluation_timestamp="2025-07-01 10:00:00", agentdojo_package_version="0.1.35")


def _drift(key: str) -> dict[str, Any]:
    doc: dict[str, Any] = dict.fromkeys(KD18_BASE, None)
    doc.update(suite_name="banking", user_task_id="user_task_1", pipeline_name="drift", build_constraints=True)
    doc[key] = []
    return doc


@pytest.mark.parametrize(("doc", "variant", "flags"), [
    (base_log(), "v0.k11", set()),
    (_k14(), "v1.k14", set()),
    ({k: v for k, v in _k14().items() if k != "utility"}, "v1.k14.incomplete", {"missing:utility"}),
    ({k: v for k, v in base_log().items() if k not in ("utility", "security")}, "v0.k11", {"missing:security", "missing:utility"}),
    (base_log(error_type="x"), "v0.k11", {"extra:error_type"}),
    (_drift("messages"), "drift.k18.messages", set()),
    (_drift("conversations"), "drift.k18.conversations", set()),
    ({k: v for k, v in base_log().items() if k != "pipeline_name"}, "pre_v0", set()),
])
def test_variants_by_key_set(doc, variant, flags):
    result = classify(doc)
    assert result.match and result.dialect == "agentdojo.tracelogger" and result.variant == variant
    assert set(result.flags) == flags


def test_key_sets_are_the_spec_sets():
    assert len(K11) == 11 and len(K14) == 14 and K11 < K14
    assert set(base_log()) == K11


@pytest.mark.parametrize("value", [[], 1, "x", {"suite_name": "a"}, {"suite_name": "a", "user_task_id": "b"}])
def test_foreign_input_does_not_match(value):
    assert not classify(value).match


def test_missing_structural_keys_are_flagged_and_mapped_as_malformed():
    doc = {k: v for k, v in base_log().items() if k != "injections"}
    raw = log_bytes(doc)
    sniff = TraceLoggerReader().sniff(raw, label="x", limits=LIMITS)
    assert sniff.match and "missing_structural_keys" in sniff.reasons
    item = next(TraceLoggerReader().parse(raw, _artefact(raw), limits=LIMITS))
    assert FLAG_MALFORMED in item.flags


def test_strict_parse_rejects_duplicate_keys_and_bom():
    reader = TraceLoggerReader()
    dup = b'{"suite_name": "a", "suite_name": "b", "user_task_id": "c", "messages": []}'
    assert not reader.sniff(dup, label="x", limits=LIMITS).match
    with pytest.raises(IngestError):
        next(reader.parse(dup, _artefact(dup), limits=LIMITS))
    bom = b"\xef\xbb\xbf" + log_bytes(base_log())
    assert not reader.sniff(bom, label="x", limits=LIMITS).match


def test_real_logs_are_v0_k11():
    if not golden.golden_available():
        pytest.skip(golden.golden_skip_reason() or "no golden fixtures")
    reader = TraceLoggerReader()
    raws = [e.native_bytes() for e in native_entries()] + [c161_bytes()]
    for raw in raws:
        sniff = reader.sniff(raw, label=C161_PATH, limits=LIMITS)
        assert sniff.match and sniff.variant == "v0.k11" and not sniff.flags
        item = next(reader.parse(raw, _artefact(raw), limits=LIMITS))
        assert item.locator.p == "" and item.variant == "v0.k11"


# ------------------------------------------------------------------------------------------------ properties
_content = st.one_of(st.none(), st.text(max_size=5), st.lists(st.fixed_dictionaries({"type": st.sampled_from(["text", "thinking"]),
                                                                                       "content": st.text(max_size=3)}), max_size=2))
_call_id = st.one_of(st.just(None), st.just(""), st.text(min_size=1, max_size=4), st.just("<absent>"))


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(order=st.permutations(sorted(K11)), content=_content, cid=_call_id, k14=st.booleans())
def test_classification_ignores_key_order_and_content_forms(order, content, cid, k14):
    doc = _k14() if k14 else base_log()
    doc["messages"][-1]["content"] = content
    call = doc["messages"][2]["tool_calls"][0]
    if cid == "<absent>":
        del call["id"]
    else:
        call["id"] = cid
    keys = list(order) + [k for k in doc if k not in order]
    shuffled = {k: doc[k] for k in keys}
    expected = classify(doc)
    got = TraceLoggerReader().sniff(json.dumps(shuffled).encode(), label="x", limits=LIMITS)
    assert (got.match, got.variant, got.flags) == (expected.match, expected.variant, expected.flags)


def _seed_logs() -> list[bytes]:
    seeds = [log_bytes(base_log()), log_bytes(_k14())]
    if golden.golden_available():
        seeds += [e.native_bytes() for e in native_entries()[:3]]
    return seeds


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_mutation_fuzzing_raises_only_typed_errors(data):
    """Byte mutations of real logs: sniff never raises; parse and map raise only the typed errors (D.6.10 item 4)."""
    from agentprov.adapters.agentdojo.mapper import TraceLoggerMapper
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner import map_unit
    from agentprov.adapters.types import ExecutionUnit

    seeds = _seed_logs()
    raw = bytearray(seeds[data.draw(st.integers(0, len(seeds) - 1))])  # an index, so no fixture text is ever printed
    for _ in range(data.draw(st.integers(1, 4))):
        op = data.draw(st.sampled_from(["flip", "cut", "dup", "insert"]))
        at = data.draw(st.integers(0, max(0, len(raw) - 1)))
        if op == "flip" and raw:
            raw[at] = data.draw(st.integers(0, 255))
        elif op == "cut":
            del raw[at:at + data.draw(st.integers(1, 40))]
        elif op == "dup":
            raw[at:at] = raw[at:at + data.draw(st.integers(1, 40))]
        else:
            raw[at:at] = data.draw(st.sampled_from([b'"', b"{", b"]", b",", b"null", b"1e999", b"\\u0000", b'"role":"tool",']))
    blob = bytes(raw)
    reader = TraceLoggerReader()
    sniff = reader.sniff(blob, label="x", limits=LIMITS)
    try:
        items = list(reader.parse(blob, _artefact(blob), limits=LIMITS))
    except (MalformedArtefact, IngestError):
        return
    assert sniff.match
    # mapping never raises for content: a malformed structure becomes a degenerate AER (D.2.8)
    outcome = map_unit(ExecutionUnit(items[0]), TraceLoggerMapper(), load_profile("agentdojo-upstream"))
    assert outcome.records and outcome.records[0]["k"] == "execution"
    assert outcome.error_code != "adapter.defect", "the mapper raised an unexpected exception (adapter_defect)"
    from agentprov.adapters.runner import aer_bytes
    from agentprov.aer.writer import AerWriteError

    try:
        aer_bytes(outcome)  # the core writer accepts every record set the mapper yields ...
    except AerWriteError:
        # ... except a degenerate header that cannot name its task: task.task_id is required in aer/0.1, so the unit is
        # registered failed with its raw bytes kept (D.2.8; the documented open item in regen-batch.md)
        assert outcome.error_code == "adapter.malformed_artefact" and "task_id" not in outcome.records[0]["task"]


@pytest.mark.parametrize(("key", "value"), [("suite_name", 5), ("suite_name", ""), ("user_task_id", ""),
                                            ("user_task_id", None), ("pipeline_name", ""), ("attack_type", ""),
                                            ("injection_task_id", "")])
def test_an_unusable_identity_name_seals_a_degenerate_aer(key, value):
    """D.2.8: a TraceLogger object whose suite, task, pipeline, attack or injection-task name is empty or of the wrong
    type is malformed and maps to a degenerate AER; an empty name never reaches the header (AER-V17). A usable task id
    is kept, so the core writer accepts the AER; without one the writer refuses it (task.task_id is required in
    aer/0.1) and the unit is registered failed with its raw bytes kept (the documented open item). Found by
    ``test_mutation_fuzzing_raises_only_typed_errors`` (a cut that emptied ``suite_name``)."""
    from agentprov.adapters.agentdojo.mapper import TraceLoggerMapper
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner import aer_bytes, map_unit
    from agentprov.adapters.types import ExecutionUnit
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.aer.writer import AerWriteError

    doc = json.loads(_seed_logs()[0])
    doc[key] = value
    blob = json.dumps(doc).encode("utf-8")
    items = list(TraceLoggerReader().parse(blob, _artefact(blob), limits=LIMITS))
    outcome = map_unit(ExecutionUnit(items[0]), TraceLoggerMapper(), load_profile("agentdojo-upstream"))
    assert outcome.error_code == "adapter.malformed_artefact"
    assert "" not in outcome.records[0]["task"].values()
    if key == "user_task_id":
        with pytest.raises(AerWriteError, match="aer.schema.required"):
            aer_bytes(outcome)
        return
    header = load_aer_bytes(aer_bytes(outcome)[0]).header
    assert header["task"]["task_id"] == doc["user_task_id"] and "/task/task_id" not in header["unk"]
