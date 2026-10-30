"""Full-scope gates A, B and E on the frozen baseline trees (J.2.6, J.3.2, J.3.3, J.3.6; K.20). Local only (marker ``full_corpus``).

Needs ``AGENTPROV_BASELINE_CORPUS`` (or ``migration/local.toml``) and an explicit ``pytest -m full_corpus``. A run takes about a quarter of an hour per gate; the
numbers are 17,664 release and 18,027 converted transcripts, 35,691 in all. Nothing is printed except counts and codes.
Normally these gates are run through ``agentprov migrate gate A|B --scope full`` and the report is committed under
``docs/reports/migration/``; this module executes the same code as a test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentprov.migration import gates

REPO = Path(__file__).resolve().parents[2]
RELEASE, CONVERTED = 17_664, 18_027

pytestmark = pytest.mark.full_corpus


@pytest.fixture(scope="module")
def cfg(request: pytest.FixtureRequest) -> gates.MigrationConfig:
    if "full_corpus" not in str(request.config.getoption("markexpr")):
        pytest.skip("a full-scope run takes about half an hour: select it with `pytest -m full_corpus`")
    config = gates.MigrationConfig.from_env(config_file=REPO / "migration" / "local.toml", workers=10)
    if config.baseline_corpus is None or not config.baseline_corpus.is_dir():
        pytest.skip("AGENTPROV_BASELINE_CORPUS is not set to the AgentDojo-PROV baseline checkout (full_corpus gate)")
    return config


@pytest.fixture(scope="module")
def g0(cfg):
    report = gates.verify_baseline(cfg)
    assert report.verdict == "pass", [(c.check, c.detail) for c in report.checks if c.status == "fail"]
    return report


def _all_pass(report: gates.GateReport) -> None:
    assert report.verdict == "pass", (report.counts, report.failures[:5])
    assert report.counts == {"expected": RELEASE + CONVERTED, "checked": RELEASE + CONVERTED, "passed": RELEASE + CONVERTED, "failed": 0, "skipped": 0}


def test_gate_a_v1_identity_on_all_35691_transcripts(cfg, g0):
    report = gates.gate_a_v1_identity(cfg, scope="full")
    _all_pass(report)
    checks = report.details["checks"]
    assert checks["release"]["A1"] == checks["release"]["A2"] == RELEASE
    assert checks["converted"]["A1"] == checks["converted"]["A2"] == CONVERTED


def test_gate_b_compat_graph_bytes_on_all_35691_transcripts(cfg, g0):
    report = gates.gate_b_compat_bytes(cfg, scope="full")
    _all_pass(report)
    checks = report.details["checks"]
    assert checks["release"]["B1"] == checks["release"]["B2"] == RELEASE
    assert checks["converted"]["B1"] == checks["converted"]["B2"] == CONVERTED


def test_semdiff_all(cfg, g0):
    """K.7.4 item 5 / J.3.6 at full scope (phase 13): gate E passes, nothing is unmapped, and every frozen count of the
    map reconciles (J.1.3: used = R3 + R4 + R6-only = 121,496 / 111,499; the frozen.* checks of the report)."""
    report, semdiffs = gates.gate_e_semdiff(cfg, scope="full")
    _all_pass(report)
    assert all(c.status == "pass" for c in report.checks if c.check.startswith("frozen."))
    assert semdiffs["release"].document["values"]["used_total"] == 121_496
    assert semdiffs["converted"].document["values"]["used_total"] == 111_499
    assert semdiffs["release"].unmapped == semdiffs["converted"].unmapped == 0
