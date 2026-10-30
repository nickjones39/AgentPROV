"""``agentprov migrate`` (MN N.2.14; J.3.0): gates G0, A and B on the CLI surface, exit codes, reports, notices, order."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agentprov.testing import golden


@pytest.fixture(autouse=True)
def _no_local_environment(monkeypatch):
    for name in ("AGENTPROV_BASELINE_CORPUS", "AGENTPROV_MIGRATION_WORK", "AGENTPROV_BASELINE_PYTHON", "AGENTPROV_BASELINE_WHEEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def empty_config(tmp_path) -> str:
    path = tmp_path / "local.toml"
    path.write_text("[env]\n")
    return str(path)


needs_golden = pytest.mark.skipif(not golden.golden_available(), reason="golden fixtures not found")


# ------------------------------------------------------------------------------------------------ surface


@pytest.mark.parametrize(
    "argv", [("migrate",), ("migrate", "gate"), ("migrate", "gate-a"), ("migrate", "gate-e"), ("migrate", "verify-baseline")]
)
def test_help_exits_zero_for_every_migrate_command(cli, argv):
    run = cli(*argv, "--help")
    assert run.code == 0 and "usage:" in run.out and run.err == ""


def test_a_gate_command_is_required(cli):
    run = cli("migrate")
    assert run.code == 2 and "a gate command is required" in run.err


@pytest.mark.parametrize("argv", [("migrate", "gate", "Z"), ("migrate", "gate-a", "--scope", "sample"), ("migrate", "gate-a", "--workers", "x")])
def test_bad_arguments_are_usage_errors(cli, argv):
    assert cli(*argv).code == 2


def test_g0_has_the_full_scope_only(cli):
    run = cli("migrate", "gate", "G0", "--scope", "golden")
    assert run.code == 2 and "full scope only" in run.err


def test_the_spellings_of_j30_and_the_gate_argument_are_the_same_command(cli):
    run = cli("migrate", "gate", "a", "--scope", "full", "--reports-dir", "/nonexistent-reports")
    other = cli("migrate", "gate-a", "--scope", "full", "--reports-dir", "/nonexistent-reports")
    assert run.code == other.code == 4


# ------------------------------------------------------------------------------------------------ refusals and environment


def test_g0_without_a_baseline_is_an_environment_error(cli, empty_config):
    run = cli("migrate", "gate", "G0", "--config", empty_config)
    assert run.code == 3 and "AGENTPROV_BASELINE_CORPUS" in run.err


def test_a_full_scope_gate_refuses_without_its_predecessor_report(cli, tmp_path, empty_config):
    run = cli("migrate", "gate", "A", "--scope", "full", "--config", empty_config, "--reports-dir", str(tmp_path / "none"))
    assert run.code == 4 and "gate G0" in run.err


def test_release_mode_refuses_in_process(cli):
    run = cli("migrate", "gate", "A", "--release", "--in-process")
    assert run.code == 4 and "--in-process" in run.err


# ------------------------------------------------------------------------------------------------ golden runs


@needs_golden
def test_gate_a_on_the_golden_set_passes_and_writes_the_report(cli, tmp_path, check_summary):
    target = tmp_path / "reports" / "A-golden.json"
    run = cli("migrate", "gate", "A", "--scope", "golden", "--workers", "2", "--report", str(target), "--json", "-q")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    assert summary["command"] == "migrate" and summary["counters"]["passed"] == 19 and summary["counters"]["failed"] == 0
    report = json.loads(target.read_text())
    assert report["gate"] == "A" and report["scope"] == "golden" and report["verdict"] == "pass"
    assert report["counts"] == {"expected": 19, "checked": 19, "passed": 19, "failed": 0, "skipped": 0}
    assert "gate A (golden, dev mode): pass" in run.err


@needs_golden
def test_gate_b_prints_the_regression_oracle_notice_even_when_quiet(cli, tmp_path):
    run = cli("migrate", "gate-b", "--workers", "2", "--report", str(tmp_path / "B.json"), "-q")
    assert run.code == 0, run.err
    assert "regression oracle" in run.err and "apv:RegressionOracle" in run.err
    assert json.loads((tmp_path / "B.json").read_text())["gate"] == "B"


@needs_golden
def test_gate_a_does_not_print_the_compat_notice(cli, tmp_path):
    run = cli("migrate", "gate-a", "--workers", "1", "--report", str(tmp_path / "A.json"), "-q")
    assert run.code == 0 and "regression oracle" not in run.err


@needs_golden
def test_default_report_location_is_reports_dir_gate_date_commit(cli, tmp_path):
    run = cli("migrate", "gate-a", "--workers", "1", "--reports-dir", str(tmp_path / "r"), "-q")
    assert run.code == 0, run.err
    files = list((tmp_path / "r" / "A").glob("*.json"))
    assert len(files) == 1 and files[0].stem[:4].isdigit()


@needs_golden
def test_without_reports_dir_the_report_goes_under_agentprov_home_never_the_repository(cli, tmp_path, monkeypatch):
    """CLI robustness item 4: ``migrate`` wrote into the checkout's migration/reports by default."""
    from agentprov.migration import gates

    home = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    before = sorted(gates.REPO_REPORTS_DIR.rglob("*")) if gates.REPO_REPORTS_DIR.exists() else None
    run = cli("migrate", "gate-a", "--workers", "1", "-q")
    assert run.code == 0, run.err
    assert len(list((home / "migration" / "reports" / "A").glob("*.json"))) == 1
    assert (sorted(gates.REPO_REPORTS_DIR.rglob("*")) if gates.REPO_REPORTS_DIR.exists() else None) == before


@needs_golden
def test_a_failing_gate_exits_1_and_lists_the_failure_without_content(cli, tmp_path, monkeypatch):
    first = golden.v1_pairs()[0]
    root = tmp_path / "fixtures"
    folder = root / "agentdojo_prov_v1" / "golden"
    folder.mkdir(parents=True)
    entries = []
    for role in (golden.ROLE_V1_TRANSCRIPT, golden.ROLE_COMPAT_GRAPH):
        item = first.file(role)
        shutil.copy(item.abspath, folder / Path(item.path).name)
    entry = {
        "id": first.id, "kind": "v1_pair", "origin": dict(first.origin),
        "files": [
            {"role": golden.ROLE_V1_TRANSCRIPT, "path": f"agentdojo_prov_v1/golden/{Path(first.file(golden.ROLE_V1_TRANSCRIPT).path).name}",
             "sha256": "0" * 64, "bytes": 1},
            {"role": golden.ROLE_COMPAT_GRAPH, "path": f"agentdojo_prov_v1/golden/{Path(first.file(golden.ROLE_COMPAT_GRAPH).path).name}",
             "sha256": "0" * 64, "bytes": 1},
        ],
    }
    entries.append(entry)
    (folder / "golden_index.json").write_text(json.dumps(entries))
    monkeypatch.setenv("AGENTPROV_GOLDEN_DIR", str(folder))
    target = tmp_path / "A.json"
    run = cli("migrate", "gate-a", "--workers", "1", "--report", str(target), "--json", "-q")
    assert run.code == 1
    summary = run.json()
    assert summary["counters"]["failed"] == 1
    assert json.loads(target.read_text())["verdict"] == "fail"
    assert "input.digest_mismatch" in run.out


@needs_golden
def test_gate_e_writes_the_semdiff_reports_and_prints_the_oracle_notice(cli, tmp_path):
    target = tmp_path / "E.json"
    run = cli("migrate", "gate-e", "--workers", "2", "--report", str(target), "--semdiff-dir", str(tmp_path / "semdiff"), "-q")
    assert run.code == 0, run.err
    assert "regression oracle" in run.err and "gate E (golden, dev mode): pass" in run.err
    assert "semdiff release:" in run.err and "unmapped 0" in run.err
    report = json.loads(target.read_text())
    assert report["gate"] == "E" and report["verdict"] == "pass" and report["counts"]["passed"] == 19
    names = sorted(p.name for p in (tmp_path / "semdiff").iterdir())
    assert names == ["semdiff-converted.golden.json", "semdiff-converted.golden.md", "semdiff-release.golden.json", "semdiff-release.golden.md"]
    assert json.loads((tmp_path / "semdiff" / "semdiff-converted.golden.json").read_text())["unmapped"] == 0


def test_gate_e_is_also_the_gate_argument_and_refuses_full_scope_without_predecessors(cli, tmp_path, empty_config):
    run = cli("migrate", "gate", "e", "--scope", "full", "--config", empty_config, "--reports-dir", str(tmp_path / "none"))
    assert run.code == 4 and "gate G0" in run.err
