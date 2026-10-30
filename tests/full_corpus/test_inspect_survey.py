"""DoD Q.11a: all 6 survey AgentHarm logs (1,056 samples) import, derive and validate end to end (D.9.4; K.7.4; R-07).

Local only (marker ``full_corpus``; select it with ``pytest -m full_corpus``). The logs are read from a clone of the
survey at the pinned commit ``89c4db2c…`` (``$AGENTPROV_SURVEY_CLONE``); each one is checked against its size, sha256
and git blob id first. Only one of the six is a committed fixture (K.4.1(5)). The chain per sample: raw store ->
versioned ``expand`` (T1 job, in process) -> reader plan -> mapper -> writer (seal) -> store-aware AER validation in
release mode -> ``agentprov-prov/0.1`` derive (twice, byte-compared) -> tier-4 validation. About five minutes with six
workers on an M2 Max. Nothing is printed except counts and codes (R-42).
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters" / "inspect"))

import inspect_support as support  # noqa: E402

from agentprov.testing import golden  # noqa: E402

pytestmark = [pytest.mark.full_corpus, pytest.mark.slow]

#: Recorded 2026-10-08 (D.9.5): per log, (samples, issues by code).
EXPECTED: dict[str, tuple[int, dict[str, int]]] = {
    "coder_benign": (176, {"inspect.sample_limit": 9, "dangling_source_ref": 4, "missing_tool_result": 4}),
    "coder_harmful": (176, {}),
    "gptoss_benign": (176, {"inspect.sample_limit": 33}),
    "gptoss_harmful": (176, {}),
    "qwen14_benign": (176, {"inspect.sample_limit": 6, "dangling_source_ref": 12, "missing_tool_result": 12}),
    "qwen14_harmful": (176, {"inspect.sample_limit": 6}),
}


def _import(rel: str, tmp: Path) -> tuple[str, int, int, dict[str, int], dict[str, int], list[tuple[str, bytes]]]:
    clone = support.survey_clone()
    assert clone is not None
    data = (clone / rel).read_bytes()
    size, sha, blob = support.SURVEY_LOGS[rel]
    assert (len(data), golden.sha256_hex(data), golden.git_blob_sha1(data)) == (size, sha, blob), rel
    imported = support.import_log(data, tmp, path=rel)
    assert imported.register == [] and imported.events == []
    issues: Counter[str] = Counter()
    accounting: Counter[str] = Counter()
    valid = 0
    for u in imported.units:
        assert not u.outcome.degenerate, u.label
        issues.update(u.issue_codes())
        accounting[u.info.accounting.status] += 1
        report = imported.validate(u)
        valid += int(report.ok)
    return rel.split("/")[2], len(imported.units), valid, dict(issues), dict(accounting), [(u.label, u.data) for u in imported.units]


@pytest.fixture(scope="module")
def survey(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory):
    if "full_corpus" not in str(request.config.getoption("markexpr")):
        pytest.skip("the six-log run takes about five minutes: select it with `pytest -m full_corpus`")
    if support.survey_clone() is None:
        pytest.skip(f"no survey clone at the pinned commit: set {support.UPSTREAM_ENV} (full_corpus gate)")
    return [_import(rel, tmp_path_factory.mktemp("survey-raw")) for rel in support.SURVEY_LOGS]


def test_all_1056_samples_import_seal_and_validate(survey):
    assert sum(n for _name, n, *_ in survey) == 1056
    for name, n, valid, issues, accounting, _aers in survey:
        assert (n, issues) == EXPECTED[name], name
        assert valid == n and accounting == {"consistent": n}, name


def test_all_1056_samples_derive_and_pass_tier4(survey):
    jobs = [(f"{name}:{label}", data) for name, *_rest, aers in survey for label, data in aers]
    with support.pool() as workers:
        results = list(workers.map(support.derive_chain, jobs, chunksize=8))
    assert len(results) == 1056
    assert [r[0] for r in results if not r[1]] == []  # derivation is deterministic
    assert [(r[0], r[3]) for r in results if not r[2]] == []  # every tier-4 check passes
