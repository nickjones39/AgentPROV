"""D-460: a corpus built while a catalogue was edited in place (the drift window between ``afe7038`` and the D-31 bumps).

Such a corpus records a catalogue version the package ships (``agentdojo`` 1, archived) with other bytes: its AERs cite
rules the shipped version lacks. ``validate``, ``recompute`` and ``verify`` report it once, as ``aer.rules.drift`` ("check at
the building commit"), not as per-rule errors (``aer.rule.missing``, ``aer.rule.class``, ``pv.linkage.method``).

The fixture is the small AgentDojo working corpus of ``derive_support`` turned into a drift-window corpus. Every AER header
declares ``agentdojo`` 1 (resealed, index digests updated), and ``derivation.json`` records ``agentdojo`` 1 with the bytes
the AERs were mapped against (today's catalogue), as an import at ``8e6d632f`` did. Fixture text is never printed.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import derive_support as ds
import pytest

from agentprov.aer.rules import RuleRegistry, load_catalogue
from agentprov.aer.validate import AerValidator
from agentprov.cli.main import main
from agentprov.io.canonical import jcs_bytes
from agentprov.testing import fs_guard


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)


@pytest.fixture(scope="module")
def drift_window(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("drift-window")
    src = ds.agentdojo_corpus(tmp, count=2)
    partial = ds.partial(src)
    current = load_catalogue("agentdojo")
    assert current.version > 1 and current.digest != load_catalogue("agentdojo", 1).digest
    rows = []
    for row in ds.rows(partial):
        path = partial / row["paths"]["aer"]
        lines = path.read_bytes().splitlines(keepends=True)
        header = json.loads(lines[0])
        assert header["rules"]["agentdojo"] == current.version
        header["rules"]["agentdojo"] = 1
        body = [jcs_bytes(header) + b"\n", *lines[1:-1]]
        seal = json.loads(lines[-1])
        seal["records_sha256"] = hashlib.sha256(b"".join(body)).hexdigest()
        os.chmod(path, 0o644)
        path.write_bytes(b"".join([*body, jcs_bytes(seal) + b"\n"]))
        row["digests"]["aer"] = "sha256:" + seal["records_sha256"]
        rows.append(row)
    (partial / "executions.jsonl").write_bytes(b"".join(jcs_bytes(r) + b"\n" for r in rows))
    derivation_path = partial / "derivation.json"
    derivation = json.loads(derivation_path.read_text())
    for stage in derivation["stages"]:
        if stage["stage"] == "aer":
            stage["rules"] = {**stage["rules"], "agentdojo": 1}
            stage["rules_sha256"] = {**stage["rules_sha256"], "agentdojo": "sha256:" + current.digest}
    derivation_path.write_text(json.dumps(derivation, indent=2, sort_keys=True) + "\n")
    return src


def _copy(src: Path, dest: Path) -> Path:
    shutil.copytree(ds.partial(src), ds.partial(dest), symlinks=True)
    return dest


def _run(capsys: pytest.CaptureFixture[str], *argv: str, guard: Path) -> tuple[int, dict[str, Any], str]:
    capsys.readouterr()
    with fs_guard.unchanged(guard):
        code = main([*argv, "--json", "--progress", "off"])
    out, err = capsys.readouterr()
    lines = out.splitlines()
    return code, (json.loads(lines[-1]) if lines else {}), err


def test_the_fixture_is_a_drift_window_corpus(drift_window):
    """Without D-460 the AER tier reads the archived v1 and reports per-rule errors: the misleading output it replaces."""
    partial = ds.partial(drift_window)
    codes: set[str] = set()
    for row in ds.rows(partial):
        validator = AerValidator(store=None, catalogues=RuleRegistry.default(), mode="dev")
        for line in (partial / row["paths"]["aer"]).read_bytes().splitlines(keepends=True):
            validator.feed(line)
        codes |= {f.code for f in validator.finish().errors}
    assert codes & {"aer.rule.missing", "aer.rule.class"}, codes


def test_validate_reports_one_drift_finding_and_no_per_rule_errors(capsys, drift_window, tmp_path):
    src = _copy(drift_window, tmp_path / "src")
    code, summary, err = _run(capsys, "validate", "--corpus", str(src), guard=ds.partial(src))
    assert code == 1, err
    text = json.dumps(summary)
    assert [n for n in summary["notices"] if n.startswith("aer.rules.drift: catalogue agentdojo@1: ")]
    assert "check at the building commit" in text
    assert summary["counters"]["rules_drift"] == 1 and summary["counters"]["failed"] == summary["counters"]["executions"]
    assert summary["issues_by_code"]["aer.rules.drift"] == 1
    assert all(f["detail"] == "checks: aer.rules.drift" for f in summary["failures"])
    for misleading in ("aer.rule.missing", "aer.rule.class", "pv.linkage"):
        assert misleading not in text


def test_verify_chain_reports_drift_and_rederive_does_not_run(capsys, drift_window, tmp_path):
    src = _copy(drift_window, tmp_path / "src")
    code, summary, err = _run(capsys, "verify", "--corpus", str(ds.partial(src)), "--level", "chain", guard=ds.partial(src))
    text = json.dumps(summary)
    assert code == 1, err
    assert "aer.rules.drift" in text and "check at the building commit" in text and "rules.mismatch" not in text
    code, summary, err = _run(capsys, "verify", "--corpus", str(ds.partial(src)), "--level", "rederive", "--in-process",
                              guard=ds.partial(src))
    text = json.dumps(summary)
    assert code == 1 and "rederive.unavailable" in text and "rederive.failed" not in text, err


def test_recompute_reports_drift_and_refuses_to_write(capsys, drift_window, tmp_path):
    src = _copy(drift_window, tmp_path / "src")
    code, summary, err = _run(capsys, "recompute", "--corpus", str(src), "--dry-run", "--in-process",
                              guard=ds.partial(src))
    assert any(n.startswith("version drift: aer: catalogue agentdojo v1 recorded with other bytes")
               for n in summary["notices"]), summary.get("notices")
    assert summary["issues_by_code"].get("aer.rules.drift") == 1 and "rules.mismatch" not in summary["issues_by_code"]
    out = tmp_path / "new"
    code, _summary, err = _run(capsys, "recompute", "--corpus", str(src), "--out", str(out), "--in-process",
                               guard=ds.partial(src))
    assert code == 4 and "aer.rules.drift" in err and "recompute at the building commit" in err
    assert not out.exists() and not ds.partial(out).exists()
