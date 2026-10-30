"""``agentprov run`` machine outputs for the GUI estimate (D-651 ``--dry-run --plan-json``; D-652 ``--catalogue``),
against the fake backend environment of ``live_fake`` (no benchmark package, no network, no key).

D-651: the plan document's rows agree with the dry-run counters (``cells_planned``, ``cells_done_before``), also after a
settled attempt, and the human dry-run output is byte-unchanged by the flag. D-652: the worker's catalogue reaches
stdout rebuilt from its checked members only; a malformed reply is a protocol error (exit 3); a worker built before the
op exists asks for a rebuild (exit 5); ``--catalogue`` takes nothing but SOURCE and ``--benchmark-version``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_fake import make_fake_env, repo_root  # noqa: E402

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the fake environment uses a POSIX venv layout")


class Run(NamedTuple):
    code: int
    out: str
    err: str


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "aphome"
    path.mkdir()
    monkeypatch.setenv("AGENTPROV_HOME", str(path))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    monkeypatch.chdir(repo_root())
    return path


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str]) -> Callable[..., Run]:
    from agentprov.cli.main import main

    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main(list(argv))
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


@pytest.fixture
def script(tmp_path: Path) -> str:
    path = tmp_path / "script.json"
    path.write_text("[]")
    return str(path)


def _run(cli: Callable[..., Run], tmp_path: Path, script: str, *extra: str) -> Run:
    return cli("run", "agentdojo", "--corpus", str(tmp_path / "corpus"), "--campaign", "t", "--suite", "banking",
               "--llm-script", script, "--max-attempts", "1", "--progress", "off", *extra)


def _summary(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "summary.json").read_text())


def _human(err: str) -> str:
    """The human stderr lines without the wall-clock line."""
    return "\n".join(line for line in err.splitlines() if not re.search(r"finished in \d", line))


# ---------------------------------------------------------------------------------------------- D-651
def test_plan_json_rows_agree_with_the_dry_run_counters(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "ok")
    run = _run(cli, tmp_path, script, "--dry-run", "--plan-json", "--repeats", "2",
               "--summary-json", str(tmp_path / "summary.json"))
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    counters = _summary(tmp_path)["counters"]
    assert doc["format"] == "agentprov-run-dry-plan/0.1" and doc["repeats"] == 2
    assert doc["units"] == counters["cells_planned"] == len(doc["cells"]) * 2
    assert doc["settled"] == counters["cells_done_before"] == sum(c["settled"] for c in doc["cells"]) == 0
    (cell,) = doc["cells"]
    assert cell == {"cell_key": "banking/user_task_1/none/none", "suite": "banking", "user_task_id": "user_task_1",
                    "injection_task_id": None, "attack": None, "kind": "user_task", "settled": 0}
    assert re.fullmatch(r"[0-9a-f]{64}", doc["plan_sha256"]) and doc["config_digest"].startswith("sha256:")
    assert not (tmp_path / "corpus.partial").exists()  # still a dry run: nothing written


def test_plan_json_counts_settled_units_by_the_campaign_rule(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "ok")
    first = _run(cli, tmp_path, script)
    assert first.code in (0, 1), first.err
    run = _run(cli, tmp_path, script, "--dry-run", "--plan-json", "--summary-json", str(tmp_path / "summary.json"))
    doc = json.loads(run.out)
    counters = _summary(tmp_path)["counters"]
    assert doc["settled"] == counters["cells_done_before"] == sum(c["settled"] for c in doc["cells"])
    assert doc["units"] == counters["cells_planned"]


def test_the_human_dry_run_output_is_unchanged_by_the_flag(home: Path, tmp_path: Path, cli, script: str) -> None:
    make_fake_env(home, "ok")
    plain = _run(cli, tmp_path, script, "--dry-run")
    with_json = _run(cli, tmp_path, script, "--dry-run", "--plan-json")
    assert plain.code == with_json.code == 0
    assert plain.out == ""  # without the flag stdout carries nothing (no --json)
    assert _human(plain.err) == _human(with_json.err).replace('"plan_json":true', '"plan_json":false')
    assert "banking/user_task_1/none/none" in plain.err


@pytest.mark.parametrize("extra", [("--plan-json",), ("--dry-run", "--plan-json", "--json"),
                                   ("--dry-run", "--plan-json", "--m5ultra")])
def test_plan_json_usage_errors(home: Path, tmp_path: Path, cli, script: str, extra: tuple[str, ...]) -> None:
    make_fake_env(home, "ok")
    if "--m5ultra" in extra:  # a preset dry run has no cells (and refuses a script)
        run = cli("run", "agentdojo", "--progress", "off", *extra)
    else:
        run = _run(cli, tmp_path, script, *extra)
    assert run.code == 2 and "--plan-json" in run.err, run.err


# ---------------------------------------------------------------------------------------------- D-652
def test_catalogue_prints_the_checked_document(home: Path, tmp_path: Path, cli) -> None:
    make_fake_env(home, "ok")
    run = cli("run", "agentdojo", "--catalogue", "--benchmark-version", "v1.1", "--progress", "off",
              "--summary-json", str(tmp_path / "summary.json"))
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert doc["format"] == "agentprov-backend-catalogue/0.1" and doc["backend"] == "agentdojo"
    assert doc["benchmark_version"] == "v1.1" and "extra_member" not in doc
    assert [a["name"] for a in doc["attacks"]] == ["important_instructions", "dos", "autodojo"] and doc["attacks"][1]["dos"]
    assert doc["attacks"][2]["needs"] == ["--autodojo-cache", "--autodojo-variant"]
    assert doc["suites"][0]["user_tasks"] == ["user_task_0", "user_task_1"]
    assert doc["suites"][0]["tool_definition_chars"] == 4321
    summary = _summary(tmp_path)
    assert summary["dry_run"] is True and summary["counters"] == {"attacks": 3, "injection_tasks": 1, "suites": 1,
                                                                  "user_tasks": 2}
    assert not (home / "staging").exists() or not any((home / "staging").iterdir())


def test_catalogue_from_an_old_worker_asks_for_a_rebuild(home: Path, cli) -> None:
    make_fake_env(home, "oldworker")
    run = cli("run", "agentdojo", "--catalogue", "--progress", "off")
    assert run.code == 5 and "backends build agentdojo" in run.err and run.out == "", run.err


def test_a_malformed_catalogue_is_a_protocol_error(home: Path, cli) -> None:
    make_fake_env(home, "badcatalogue")
    run = cli("run", "agentdojo", "--catalogue", "--progress", "off")
    assert run.code == 3 and "malformed catalogue" in run.err and run.out == "", run.err


@pytest.mark.parametrize("extra", [("--suite", "banking"), ("--model", "deepseek"), ("--json",), ("--dry-run",)])
def test_catalogue_takes_only_source_and_benchmark_version(home: Path, cli, extra: tuple[str, ...]) -> None:
    make_fake_env(home, "ok")
    run = cli("run", "agentdojo", "--catalogue", "--progress", "off", *extra)
    assert run.code == 2 and "--catalogue" in run.err, run.err


def test_the_catalogue_worker_gets_no_key_and_no_network(home: Path, cli, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov.cli.live import worker as worker_mod

    seen: list[dict[str, str]] = []
    real = worker_mod.BackendWorker.__init__

    def capture(self: Any, spec: Any, **kw: Any) -> None:
        seen.append(dict(spec.env))
        real(self, spec, **kw)

    monkeypatch.setattr(worker_mod.BackendWorker, "__init__", capture)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-not-a-key")
    make_fake_env(home, "ok")
    run = cli("run", "agentdojo", "--catalogue", "--progress", "off")
    assert run.code == 0, run.err
    (env,) = seen
    assert env["AGENTPROV_BLOCK_NETWORK"] == "1" and "placeholder-not-a-key" not in json.dumps(env)
