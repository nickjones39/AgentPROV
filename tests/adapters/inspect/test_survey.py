"""The committed survey AgentHarm log through the whole pipeline (D.9.4; C.4.1 vector 4; DoD Q.11a on one log).

The committed fixture is one complete log (``gptoss_harmful``, 176 samples, K.4.1(5)); all six logs are the local
``full_corpus`` gate (``tests/full_corpus/test_inspect_survey.py``). The logs hold harmful requests by design: these
tests compare bytes, digests, ids and codes, and print nothing else (R-42).

Golden AER bytes are checked in under ``tests/fixtures/inspect/expected/`` (restricted_use, like their source).
Regenerate them deliberately with ``AGENTPROV_REGEN_INSPECT_GOLDEN=1`` after an intended mapping, profile or
catalogue change.
"""

from __future__ import annotations

import os

import pytest

import inspect_support as support
from agentprov.adapters.inspect.dialect import InspectEvalReader
from agentprov.adapters.inspect.mapper import InspectEvalMapper
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner import aer_bytes, map_unit
from agentprov.adapters.types import ArtefactRef, ExecutionUnit, Origin
from agentprov.aer.ids import import_execution_id
from agentprov.ingest.limits import IngestLimits
from agentprov.testing import golden

EXPECTED = support.REPO / "tests" / "fixtures" / "inspect" / "expected"
REGEN = "AGENTPROV_REGEN_INSPECT_GOLDEN"
GOLDEN_SAMPLES = ("samples/1-1_epoch_1.json", "samples/29-4_epoch_1.json")
VECTOR_4 = "ex_jrggvyihit3vlsxjpioqzyyc3s"
MEMBER_42 = support.FIXTURES / "agentharm_inspect__gptoss_benign__sample_42-1_epoch_1.json"
HEADER_42 = support.FIXTURES / "agentharm_inspect__gptoss_benign__header.json"
BENIGN_CONTAINER = "165eb60c5758ac18a4355bee2599349fb9ce104a277ad59c43e4e71be2323946"


def _require(path):
    """The AgentHarm fixtures are ``restricted_use``: the public export leaves them out (D-943), so their tests skip."""
    if not path.is_file():
        pytest.skip("the committed Inspect fixture log is absent")


def test_the_committed_log_is_the_pinned_blob():
    _require(support.committed_log())
    data = support.committed_log().read_bytes()
    size, sha, blob = support.SURVEY_LOGS[support.COMMITTED_LOG]
    assert (len(data), golden.sha256_hex(data), golden.git_blob_sha1(data)) == (size, sha, blob)


def test_every_sample_imports_seals_and_validates(committed):
    assert committed.register == [] and committed.events == []
    assert len(committed.units) == 176
    assert {r.disposition for r in committed.member_rows if r.label in ("header.json",) or r.label.startswith("samples/")} \
        == {"selected"}
    for u in committed.units:
        assert not u.outcome.degenerate, u.label
        report = committed.validate(u)
        assert report.ok, (u.label, sorted({f.code for f in report.errors}))
        assert u.header["dialect"] == {"id": "inspect.eval", "variant": "v2"}
        assert u.header["profile"]["id"] == "survey-agentharm"


def test_agent_call_accounting_is_consistent(committed):
    for u in committed.units:
        checks = [c for c in u.info.accounting.checks if c["id"] == "aer.acc.agent_calls_vs_assistant@1"]
        assert checks and all(c["verdict"] == "consistent" for c in checks), u.label
        assert u.info.accounting.status == "consistent", u.label


def test_judge_calls_are_auxiliary_and_in_scorer_scopes(committed):
    judged = 0
    for u in committed.units:
        scopes = {r["id"]: r for r in u.of_kind("scope")}
        for call in u.of_kind("model_call"):
            scope = scopes[call["scope"]]
            if call["role"] == "auxiliary":
                judged += 1
                assert scope.get("subtype") == "inspect.scorer" and u.by_id()[call["actor"]]["kind"] == "judge"
            else:
                assert call["actor"] == "agent" and scope["kind"] == "agent_invocation"
    assert judged >= 176  # every sample is scored by at least one judge call


def test_mapping_is_deterministic(committed, tmp_path):
    again = support.import_log(support.committed_log().read_bytes(), tmp_path / "raw", path=support.COMMITTED_LOG)
    assert [u.data for u in again.units[:20]] == [u.data for u in committed.units[:20]]


def test_c41_vector_4_known_answer():
    _require(MEMBER_42)
    data = MEMBER_42.read_bytes()
    golden.assert_matches_sha256(data, "3a04cbc50dee2ec447a4796004a4800e68d3ceb30a3f886a52db88b184fad35d", what="42-1 member")
    assert import_execution_id("inspect.eval/survey-agentharm", golden.sha256_hex(data), {"p": ""}) == VECTOR_4
    u = _map_member_42()
    assert u[0].header["ex"] == VECTOR_4 and u[0].header["source_key"] == {"sha256": golden.sha256_hex(data), "loc": {"p": ""}}


def _map_member_42():
    member, header = MEMBER_42.read_bytes(), HEADER_42.read_bytes()
    profile = load_profile("survey-agentharm")
    origin = Origin.member(BENIGN_CONTAINER, "samples/42-1_epoch_1.json", 93, "88f7401d", len(member))
    ref = ArtefactRef("a0", golden.sha256_hex(member), len(member), "application/json", origin, "primary", "native")
    header_ref = ArtefactRef("a1", golden.sha256_hex(header), len(header), "application/json",
                             Origin.member(BENIGN_CONTAINER, "header.json", 93, "c61e0863", len(header)), "supporting", "native")
    item = next(InspectEvalReader().parse(member, ref, limits=IngestLimits()))
    unit = ExecutionUnit(primary=item, auxiliary={"header": header_ref})
    mapper = InspectEvalMapper()
    outcome = map_unit(unit, mapper, profile, auxiliary={"header": header})
    data, info = aer_bytes(outcome, unit=unit, mapper=mapper, profile=profile)
    return support.Unit(unit, outcome, data, info, "samples/42-1_epoch_1.json"), data


def _golden_cases(committed) -> dict[str, bytes]:
    cases = {f"gptoss_harmful__{label.split('/')[1].removesuffix('.json')}": committed.unit(label).data
             for label in GOLDEN_SAMPLES}
    cases["gptoss_benign__42-1_epoch_1"] = _map_member_42()[1]
    return cases


def test_golden_aer_bytes(committed):
    cases = _golden_cases(committed)
    if os.environ.get(REGEN) == "1":
        EXPECTED.mkdir(parents=True, exist_ok=True)
        for name, data in cases.items():
            (EXPECTED / f"{name}.aer.jsonl").write_bytes(data)
    for name, data in cases.items():
        path = EXPECTED / f"{name}.aer.jsonl"
        if not path.is_file():
            pytest.fail(f"missing golden AER {path.name}: regenerate with {REGEN}=1")
        golden.assert_bytes_equal(path.read_bytes(), data, what=f"golden AER {name}")


def test_one_sample_derives_and_passes_tier4(committed):
    name, deterministic, passed, failed = support.derive_chain(("1-1", committed.unit(GOLDEN_SAMPLES[0]).data))
    assert deterministic and passed and failed == []


@pytest.mark.slow
def test_committed_log_derives_and_passes_tier4(committed):
    """DoD Q.11a on the committed log: import -> AER validate -> derive PROV -> tier 4, every sample."""
    jobs = [(u.label, u.data) for u in committed.units]
    with support.pool() as workers:
        results = list(workers.map(support.derive_chain, jobs))
    assert len(results) == 176
    assert [r for r in results if not (r[1] and r[2])] == []
