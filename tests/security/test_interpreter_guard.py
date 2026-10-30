"""SEC-26 / K.12.12: interpreter guard (AD-16 as ruled). ``sys.version_info`` is monkeypatched."""

from __future__ import annotations

import json
import pathlib
import warnings

import pytest

from agentprov import envinfo
from agentprov.cli.main import build_parser
from agentprov.envinfo import (
    InterpreterAdvisoryRefusedError,
    InterpreterUnpatchedError,
    InterpreterUnpatchedWarning,
    interpreter_advisory,
    refuse_advisory_manifest,
    require_patched_for_archive,
)

BELOW = (3, 14, 7)
PATCHED = [(3, 14, 8), (3, 14, 9), (3, 15, 0)]


def _set_version(monkeypatch: pytest.MonkeyPatch, version: tuple[int, int, int]) -> None:
    monkeypatch.setattr("sys.version_info", (*version, "final", 0))


def test_floor_constant():
    assert envinfo.INTERPRETER_FLOOR == (3, 14, 8)


def test_dev_mode_below_floor_warns_and_returns_record(monkeypatch):
    _set_version(monkeypatch, BELOW)
    with pytest.warns(InterpreterUnpatchedWarning) as caught:
        record = require_patched_for_archive(release=False)
    text = str(caught[0].message)
    assert "ingest.interpreter.unpatched" in text
    assert "CVE-2026-15310" in text and "CVE-2026-19672" in text
    assert record is not None
    assert record.to_json() == {
        "floor": "3.14.8",
        "python_version": "3.14.7",
        "missing": ["CVE-2026-15310", "CVE-2026-19672"],
    }
    json.dumps(record.to_json())


def test_warning_is_not_a_user_warning():
    # pyproject turns UserWarning from agentprov.* into errors; the guard must not be affected.
    assert not issubclass(InterpreterUnpatchedWarning, UserWarning)


def test_release_mode_below_floor_refuses(monkeypatch):
    _set_version(monkeypatch, BELOW)
    with pytest.raises(InterpreterUnpatchedError) as excinfo:
        require_patched_for_archive(release=True)
    err = excinfo.value
    assert err.code == "ingest.interpreter.unpatched"
    assert err.exit_code == 3
    assert "3.14.8" in str(err) and "3.14.7" in str(err) and "0.12.22" in str(err)


@pytest.mark.parametrize("version", PATCHED)
@pytest.mark.parametrize("release", [False, True])
def test_at_or_above_floor_is_silent(monkeypatch, version, release):
    _set_version(monkeypatch, version)
    assert interpreter_advisory() is None
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert require_patched_for_archive(release=release) is None


def test_advisory_reports_exact_micro_version(monkeypatch):
    _set_version(monkeypatch, (3, 14, 0))
    advisory = interpreter_advisory()
    assert advisory is not None and advisory.python_version == "3.14.0"


def test_manifest_with_advisory_is_refused_with_exit_4(monkeypatch):
    _set_version(monkeypatch, BELOW)
    with pytest.warns(InterpreterUnpatchedWarning):
        record = require_patched_for_archive(release=False)
    assert record is not None
    manifest = {"producer": {"python_version": "3.14.7", "interpreter_advisory": record.to_json()}}
    _set_version(monkeypatch, (3, 14, 8))  # whatever interpreter runs `package`
    with pytest.raises(InterpreterAdvisoryRefusedError) as excinfo:
        refuse_advisory_manifest(manifest)
    assert excinfo.value.exit_code == 4


@pytest.mark.parametrize(
    "manifest",
    [{}, {"producer": {}}, {"producer": {"interpreter_advisory": None}}, {"producer": None}],
)
def test_manifest_without_advisory_is_accepted(manifest):
    refuse_advisory_manifest(manifest)


def test_no_override_flag_exists():
    parser = build_parser()
    options = {opt for action in parser._actions for opt in action.option_strings}
    assert "--allow-unpatched-interpreter" not in options
    src = pathlib.Path(__file__).resolve().parents[2] / "src"
    assert not any("allow-unpatched-interpreter" in p.read_text(encoding="utf-8") for p in src.rglob("*.py"))
