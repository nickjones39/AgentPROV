"""``test_validation_all`` (K.7.4 item 4; J.3.5): every stored AER of the migration corpora re-derives SEM and PROV and passes
strict validation with no skips. Local only (marker ``full_corpus``); it runs the code of ``agentprov migrate gate-d``.

Inputs: ``AGENTPROV_GATE_D_CORPORA``, the corpora separated by ``os.pathsep`` (one per tree: the v1 import of the release tree, the
v1 import of the converted tree, the native June-2024 import). ``AGENTPROV_GATE_D_ACCEPT_GAPS`` (comma separated trees) records a
tree without stored AERs, as ``--accept-gap`` does: as of phase 11 no stored AERs of the converted tree exist, so a run over the
two existing corpora sets it to ``converted``. ``AGENTPROV_GATE_D_LIMIT`` runs a sample. A full run takes about an hour with ten
workers; select it with ``pytest -m full_corpus``. Nothing is written into the corpora.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentprov.migration import gate_d, gates

pytestmark = pytest.mark.full_corpus

ENV_CORPORA = "AGENTPROV_GATE_D_CORPORA"
ENV_GAPS = "AGENTPROV_GATE_D_ACCEPT_GAPS"
ENV_LIMIT = "AGENTPROV_GATE_D_LIMIT"


def test_validation_all(request: pytest.FixtureRequest) -> None:
    if "full_corpus" not in str(request.config.getoption("markexpr")):
        pytest.skip("a full-scope run takes about an hour: select it with `pytest -m full_corpus`")
    corpora = [Path(p) for p in os.environ.get(ENV_CORPORA, "").split(os.pathsep) if p]
    if not corpora:
        pytest.skip(f"{ENV_CORPORA} is not set (the corpora of the migration trees, separated by {os.pathsep!r})")
    gaps = [g for g in os.environ.get(ENV_GAPS, "").split(",") if g]
    limit = int(os.environ[ENV_LIMIT]) if os.environ.get(ENV_LIMIT) else None
    cfg = gates.MigrationConfig.from_env(workers=10, strict=True)
    run = gate_d.gate_d_validate(cfg, scope="full", corpora=corpora, limit=limit, accept_gaps=gaps)
    report = run.report
    failed = [(c.check, c.detail) for c in report.checks if c.status == "fail"]
    assert report.verdict == "pass", (report.counts, failed[:10], report.failures[:5])
    assert report.counts["failed"] == 0 and report.counts["skipped"] == 0
    skipped = sum(
        counts.get("skipped", 0) for tree in report.details["trees"].values() for counts in tree["check_statuses"].values()
    )
    assert skipped == 0  # a skipped check is a failure (MP-3)
