"""A calibrated preset (D-823) and the local-run estimate's measured time basis (D-826).

* ``calibrated = true`` needs ``calibration`` (the committed report) and a ``basis`` on every compute row;
* ``cell_seconds`` rows are ordered like the compute rows and pick a model's class; without a catch-all last row, a
  model above the last bound (or of unknown size) gets no measured time;
* the corpus record holds no float (H.1.4(3)): floats become decimal strings;
* ``agentprov estimate`` uses a calibrated preset's seconds per cell for a local endpoint on the preset's host only.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from agentprov import presets
from agentprov.errors import AgentProvError

BASE: dict[str, Any] = {
    "version": 2, "endpoint": "omlx", "start_stagger_per_worker_s": 1, "request_timeout_s": 900,
    "gpu_budget_fraction": 0.75, "reserve_gib": 16, "per_worker_reserve_gib": 0.5, "default_context_tokens": 32768,
    "kv_bytes": 2, "kv_trace_fallback_gib": 4, "server_max_concurrency_default": 8,
    "expected_host": {"os_family": "darwin", "arch": "arm64", "min_memory_gib": 240},
    "compute_caps": [{"max_active_params_b": 15, "jobs": 8, "basis": "measured"},
                     {"max_active_params_b": 40, "jobs": 6, "basis": "provisional"},
                     {"jobs": 4, "basis": "provisional"}],
}


def _parse(**extra: Any) -> presets.Preset:
    return presets._parse_preset("t", {**BASE, **extra}, "0" * 64)


def test_a_calibrated_preset_names_its_report_and_every_rows_basis() -> None:
    p = _parse(calibrated=True, calibration="docs/reports/mac-studio-calibration/README.md")
    assert p.calibrated and [r.basis for r in p.compute_caps] == ["measured", "provisional", "provisional"]
    assert p.to_json()["calibrated"] is True and p.to_json()["compute_caps"][0]["basis"] == "measured"
    with pytest.raises(AgentProvError):
        _parse(calibrated=True)  # no report
    rows = [dict(r) for r in BASE["compute_caps"]]
    del rows[2]["basis"]
    with pytest.raises(AgentProvError):
        _parse(calibrated=True, calibration="r", compute_caps=rows)
    with pytest.raises(AgentProvError):
        _parse(compute_caps=[{**BASE["compute_caps"][0], "basis": "guessed"}, *BASE["compute_caps"][1:]])


def test_the_shipped_preset_is_calibrated_from_version_2() -> None:
    p = presets.load_preset("m5ultra")
    assert p.version == 2 and p.calibrated is True and p.to_json()["calibrated"] is True
    assert p.calibration is not None and (Path(__file__).resolve().parents[2] / p.calibration).is_file()
    assert [r.basis for r in p.compute_caps] == ["measured", "provisional", "provisional"]
    for row in p.cell_seconds:  # every measured row cites a committed sweep report
        assert (Path(__file__).resolve().parents[2] / row.source).is_file()


def test_the_evidence_rows_digests_match_the_committed_reports() -> None:
    import hashlib

    root = Path(__file__).resolve().parents[2]
    cited = [s.split() for _, s in presets.load_preset("m5ultra").evidence if " sha256:" in s]
    assert cited
    for path, digest in cited:
        assert "sha256:" + hashlib.sha256((root / path).read_bytes()).hexdigest() == digest, path


def test_cell_seconds_rows_pick_the_models_class() -> None:
    p = _parse(cell_seconds=[{"max_active_params_b": 15, "p50": 30, "p90": 60, "jobs": 6, "source": "a"},
                             {"p50": 120, "p90": 240, "jobs": 4, "source": "b"}])
    assert p.cell_seconds_for(3).source == "a" and p.cell_seconds_for(70).source == "b"
    assert p.cell_seconds_for(None).source == "b"  # unknown A: the most conservative row
    assert "cell_seconds" in p.to_json() and _parse().cell_seconds_for(3) is None
    with pytest.raises(AgentProvError):
        _parse(cell_seconds=[{"p50": 60, "p90": 30, "jobs": 1, "source": "x"}])  # p90 < p50
    with pytest.raises(AgentProvError):
        _parse(cell_seconds=[{"p50": 1, "p90": 2, "jobs": 1}, {"max_active_params_b": 5, "p50": 1, "p90": 2, "jobs": 1}])


def test_without_a_catch_all_cell_seconds_row_unmeasured_classes_get_no_measured_time() -> None:
    p = _parse(cell_seconds=[{"max_active_params_b": 15, "p50": 30, "p90": 60, "jobs": 4, "source": "a"}])
    assert p.cell_seconds_for(6).source == "a"
    assert p.cell_seconds_for(70) is None and p.cell_seconds_for(None) is None  # the estimate keeps the priors' time


def test_corpus_json_has_no_floats() -> None:
    record = presets.corpus_json(presets.preset_record(_parse()))
    stack: list[Any] = [record]
    while stack:
        value = stack.pop()
        assert not isinstance(value, float)
        stack.extend(value.values() if isinstance(value, dict) else value if isinstance(value, list) else [])
    assert record["resolved"]["gpu_budget_fraction"] == "0.75"


def test_estimate_uses_measured_time_only_for_a_calibrated_local_preset_on_its_host(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov import settings
    from agentprov.cli import estimate as est

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path))
    calibrated = dataclasses.replace(
        _parse(calibrated=True, calibration="r", cell_seconds=[
            {"max_active_params_b": 15, "p50": 30, "p90": 60, "jobs": 6, "source": "tune-jobs a.json"},
            {"p50": 120, "p90": 240, "jobs": 4, "source": "tune-jobs b.json"}]), name="m5ultra")
    monkeypatch.setattr(presets, "load_preset", lambda name: calibrated)
    monkeypatch.setattr(presets, "check_host", lambda preset, host: [])
    settings.set("local_models.omlx.small.active_params_b", 3)
    row, label = est._local_time_basis("omlx", "small") or (None, "")
    assert row is not None and row.p50 == 30 and "measured at jobs 6" in label
    assert est._local_time_basis("omlx", "unknown")[0].p50 == 120  # type: ignore[index]
    assert est._local_time_basis("openai", "small") is None  # not a local endpoint
    monkeypatch.setattr(presets, "check_host", lambda preset, host: ["mismatch"])
    assert est._local_time_basis("omlx", "small") is None  # measured on another machine
    monkeypatch.setattr(presets, "load_preset", lambda name: dataclasses.replace(calibrated, calibrated=False))
    assert est._local_time_basis("omlx", "small") is None
