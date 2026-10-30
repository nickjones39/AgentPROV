"""RH-1 (Inspect harness finding, 2026-10-22): a non-finite number in header.json.

Inspect writes ``NaN`` for an undefined metric: AgentHarm's ``avg_score_non_refusals`` is NaN when every sample was
judged a refusal, which a small live pilot easily produces. The strict loader refused the whole header, so the log was
one ``select.dialect_planned`` row and no execution. Now the reader and the mapper parse the header with the
``python-json`` profile (C.11.3) and tolerate a non-finite number under ``/results`` or ``/stats`` only (members the
mapper never reads), reporting the info issue ``inspect.header_nonfinite``; anywhere else the log stays planned.
"""

from __future__ import annotations

import json
from pathlib import Path

import inspect_support as support
import pytest

from agentprov.adapters.inspect.dialect import load_header
from agentprov.adapters.profiles import load_profile
from agentprov.ingest.loaders import strict_json_loads

PRODUCER = "0.3.263"  # the kexin-xu-01-agentharm band, the live harness's pin (D-661)


def _header(**results: object) -> dict:
    header = support.synthetic_header(PRODUCER)
    header["eval"]["task"] = "inspect_evals/agentharm"
    header["eval"]["packages"]["inspect_evals"] = "0.20.0"
    header["results"] = {"total_samples": 1, "completed_samples": 1, "scores": [
        {"name": "combined_scorer", "metrics": {"avg_score_non_refusals": {"name": "avg", "value": results.get("value", 0.5)},
                                                "avg_refusals": {"name": "avg", "value": 1.0}}}]}
    return header


def _float_objects(value: object) -> list[object]:
    """Every ``{"$float": ...}`` object anywhere in ``value`` (the form a mapped non-finite number would take)."""
    if isinstance(value, dict):
        return ([value] if "$float" in value else []) + [f for v in value.values() for f in _float_objects(v)]
    if isinstance(value, list):
        return [f for v in value for f in _float_objects(v)]
    return []


def _import(tmp_path: Path, header: dict) -> support.Imported:
    data = support.build_eval(header, {"1-1_epoch_1.json": support.basic_sample("1-1")})
    return support.import_log(data, tmp_path, path="logs/x.eval", profile=load_profile("kexin-xu-01-agentharm"))


def test_a_nan_metric_under_results_maps_with_an_info_issue(tmp_path):
    imp = _import(tmp_path, _header(value=float("nan")))
    assert imp.register == []
    (unit,) = imp.units
    assert not unit.outcome.degenerate
    assert "inspect.header_nonfinite" in unit.issue_codes()
    assert not _float_objects(unit.records)  # never mapped as a value (only the issue's detail text names it)


def test_a_nan_metric_under_results_validates(tmp_path):
    """D-710: the AER validator's locator resolver parses with the python-json profile, so the locators into the
    header (a1) resolve and the AER is valid in release mode."""
    imp = _import(tmp_path, _header(value=float("nan")))
    (unit,) = imp.units
    report = imp.validate(unit)
    assert report.ok, sorted({f.code for f in report.findings if f.severity == "error"})


def test_a_finite_header_maps_without_the_issue(tmp_path):
    imp = _import(tmp_path, _header(value=0.5))
    (unit,) = imp.units
    assert "inspect.header_nonfinite" not in unit.issue_codes()


def test_a_nan_in_a_mapped_member_keeps_the_log_planned(tmp_path):
    header = _header(value=0.5)
    header["eval"]["model_generate_config"]["temperature"] = float("nan")
    imp = _import(tmp_path, header)
    assert imp.units == []
    assert [(r["code"], "ingest.number.nonfinite" in r["detail"]) for r in imp.register] == [("select.dialect_planned", True)]


@pytest.mark.parametrize("raw", [b"NaN", b"Infinity", b"-Infinity", b"[NaN]", b'{"results": [1], "x": NaN}'])
def test_a_non_finite_root_or_mapped_member_is_a_typed_refusal(raw):
    """Review R2-1: a bare non-finite document crashed with IndexError; it is a typed ingest refusal (the log stays
    select.dialect_planned, as before D-710)."""
    from agentprov.errors import IngestError

    with pytest.raises(IngestError) as info:
        load_header(raw)
    assert info.value.code == "ingest.number.nonfinite"


def test_a_root_nan_header_log_stays_planned(tmp_path):
    """Review R2-1 through the reader: a header.json that is the bare constant NaN registers the log as planned."""
    data = support.build_eval(float("nan"), {"1-1_epoch_1.json": support.basic_sample("1-1")})  # header.json = NaN
    imp = support.import_log(data, tmp_path, path="logs/x.eval", profile=load_profile("kexin-xu-01-agentharm"))
    assert imp.units == []
    assert [(r["code"], "ingest.number.nonfinite" in r["detail"]) for r in imp.register] == [("select.dialect_planned", True)]


def test_literal_float_shaped_source_objects_are_not_counted():
    """Review R2-3: only the objects the python-json profile made count; a literal one-key {"$float": ...} object in the
    source is data, and does not refuse the log when it sits in a mapped member."""
    header = _header(value=float("nan"))
    header["eval"]["metadata"] = {"literal": {"$float": "NaN"}}
    count = load_header(json.dumps(header).encode())[1]
    assert count == 1
    header["results"]["scores"][0]["metrics"]["avg_score_non_refusals"]["value"] = 0.5
    assert load_header(json.dumps(header).encode())[1] == 0


def test_load_header_equals_the_strict_parse_of_a_finite_header():
    raw = json.dumps(_header(value=0.25)).encode()
    assert load_header(raw) == (strict_json_loads(raw), 0)
    nan = json.dumps(_header(value=float("nan"))).encode()
    header, n = load_header(nan)
    assert n == 1 and header["results"]["scores"][0]["metrics"]["avg_score_non_refusals"]["value"] == {"$float": "NaN"}
