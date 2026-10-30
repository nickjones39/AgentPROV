"""End to end with the real Inspect backend environment (D-669; D-662..D-666): build, scripted run, import, validate.

``agentprov backends build inspect-agentharm`` builds the environment once per test session into a temporary
``$AGENTPROV_HOME``, offline from the uv cache, with the pinned AgentHarm dataset provisioned from AgentPROV's fetch
cache (``$AGENTPROV_UPSTREAM_CACHE``, default ``~/.agentprov/cache``; read only). ``agentprov run agentharm
--llm-script`` then runs a two-sample AgentHarm cell in the spawned Inspect worker with the scripted transport (agent and
both judges scripted; no network, no key). The `.eval` the worker writes is expanded and mapped by the unchanged
``inspect.eval`` reader and mapper (``LiveSessionPipeline(native_log=True)``), one execution per sample.

Marker ``backend_inspect``. Without the wheels in the uv cache or the dataset in the fetch cache the build fails and
every test here skips with the reason. Sample ids only; no dataset text is read or printed.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_fake import repo_root  # noqa: E402

pytestmark = [pytest.mark.backend_inspect, pytest.mark.slow,
              pytest.mark.skipif(os.name == "nt", reason="the backend environment is POSIX-only in v0.1")]

JUDGE = [{"reply": "text", "content": "Answer: No"}] * 20  # not a refusal: the run's metrics stay finite
SCRIPT = {"agent": [{"reply": "text", "content": "Done."}] * 4,
          "judges": {"refusal_judge": JUDGE, "semantic_judge": JUDGE}}


def _main(*argv: str) -> tuple[int, str, str]:
    import contextlib
    import io

    from agentprov.cli.main import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _fetch_cache() -> str:
    return os.environ.get("AGENTPROV_UPSTREAM_CACHE") or str(Path.home() / ".agentprov" / "cache")


@pytest.fixture(scope="session")
def live_home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    home = tmp_path_factory.mktemp("inspect-home")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AGENTPROV_HOME", str(home))
        mp.setenv("AGENTPROV_UPSTREAM_CACHE", _fetch_cache())
        mp.delenv("AGENTPROV_PROGRESS", raising=False)
        mp.chdir(repo_root())
        code, _out, err = _main("backends", "build", "inspect-agentharm", "--progress", "off")
    if code != 0:
        pytest.skip(f"the Inspect environment could not be built (exit {code}): {err.strip().splitlines()[-1:]}")
    return home


@pytest.fixture(autouse=True)
def _live_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if "live_home" in request.fixturenames:
        monkeypatch.setenv("AGENTPROV_HOME", str(request.getfixturevalue("live_home")))
        monkeypatch.setenv("AGENTPROV_UPSTREAM_CACHE", _fetch_cache())
        monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
        monkeypatch.chdir(repo_root())


def _marker(home: Path) -> dict[str, Any]:
    (env,) = list((home / "envs").iterdir())
    return json.loads((env / "AGENTPROV_ENV.json").read_text())


def test_the_build_provisions_the_dataset_and_passes_the_offline_check(live_home: Path) -> None:
    marker = _marker(live_home)
    assert marker["status"] == "complete" and marker["backend"] == "inspect-agentharm"
    assert marker["dataset"]["revision"] == "e23b3fe60a0da9037314b88e5ee3a0c054970dad"
    assert marker["t0_identity"]["task_files"]["inspect_evals/agentharm"] == marker["hello_identity"]["task_files_sha256"]
    code, _out, err = _main("backends", "build", "inspect-agentharm", "--offline-check", "--progress", "off")
    assert code == 0, err


def test_a_scripted_run_imports_one_valid_execution_per_sample(live_home: Path, tmp_path: Path) -> None:
    script = tmp_path / "script.json"
    script.write_text(json.dumps(SCRIPT))
    corpus = tmp_path / "corpus"
    argv = ("run", "agentharm", "--corpus", str(corpus), "--campaign", "e2e", "--task", "inspect_evals/agentharm",
            "--task-param", "split=test_public", "--samples", "limit:2", "--message-limit", "20",
            "--token-limit", "60000", "--time-limit", "600", "--judge", "refusal_judge=scripted-judge",
            "--judge", "semantic_judge=scripted-judge", "--llm-script", str(script), "--json", "--progress", "off")
    code, out, err = _main(*argv)
    summary = json.loads(out)
    assert code == 0, (err[-3000:], summary.get("failures"))
    partial = Path(str(corpus) + ".partial")
    manifest = json.loads((partial / "corpus.json").read_text())
    assert manifest["mode"] == "live" and manifest["synthetic"] is True and manifest["live"]["test_only"] is True
    rows = [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    for row in rows:
        assert row["mode"] == "import" and row["attempt"] is None and row["status"] in ("ok", "ok_with_issues")
        assert row["stages"]["validation"] == "ok" and row["stages"]["prov"] == {"agentprov-prov/0.1": "ok"}
        assert row["stages"]["sem"] == {"inspect.agentharm@2": "ok"}
        header = json.loads((partial / row["paths"]["aer"]).read_text().splitlines()[0])
        assert header["mode"] == "import" and header["dialect"]["id"] == "inspect.eval"
        assert header["profile"]["id"] == "agentharm-live"
    results = [json.loads(line) for line in (partial / "validation" / "results.jsonl").read_text().splitlines()]
    assert results and all(r["verdict"] == "pass" for r in results)
    # the capture/0.1 wire log is stored beside the .eval, with the capture origin of the session (D-665 (b))
    origins = [json.loads(line) for line in (partial / "raw" / "origins.jsonl").read_text().splitlines()]
    assert any(o["origin"]["kind"] == "capture" for o in origins)
    code, _out, err = _main("validate", "--corpus", str(partial), "--progress", "off")
    assert code == 0, err[-2000:]
    code, out, err = _main("recompute", "--corpus", str(partial), "--dry-run", "--json", "--progress", "off")
    assert code == 0, err[-2000:]



def _probe_shape(tmp_path: Path, campaign: str, script: dict[str, Any]) -> tuple[int, dict[str, Any], Path]:
    """A scripted run in the D-667 probe's shape: judges on the agent's model, one sample per cell, two cells in one
    worker (the shape that exposed D-743)."""
    path = tmp_path / f"{campaign}.json"
    path.write_text(json.dumps(script))
    corpus = tmp_path / campaign
    code, out, err = _main("run", "agentharm", "--corpus", str(corpus), "--campaign", campaign, "--task",
                           "inspect_evals/agentharm", "--task-param", "split=test_public", "--samples", "limit:2",
                           "--cell-size", "1", "--max-attempts", "1", "--message-limit", "10", "--token-limit", "60000",
                           "--time-limit", "600", "--judge", "refusal_judge=scripted-fake",
                           "--judge", "semantic_judge=scripted-fake", "--llm-script", str(path), "--json",
                           "--progress", "off")
    assert out, err[-3000:]
    return code, json.loads(out), Path(str(corpus) + ".partial")


def _wire_requests(partial: Path) -> list[dict[str, Any]]:
    requests = []
    for path in sorted((partial / "raw" / "objects").rglob("*.jsonl")):
        events = [json.loads(line) for line in path.read_text().splitlines()]
        if events and events[0]["type"] == "session.start":
            requests += [e for e in events if e["type"] == "llm.request"]
    return requests


def test_judges_on_the_agents_model_are_recorded_and_estimated_as_judges(live_home: Path, tmp_path: Path) -> None:
    """D-743: with judges on the agent's model, every cell gets its own models: each sample is scored, every judge
    request is recorded with role ``auxiliary`` under a judge actor, and the estimate's judge split (D-770, read from
    the AER) counts exactly those requests."""
    from agentprov.estimate.usage import execution_usage

    code, summary, partial = _probe_shape(tmp_path, "shape", SCRIPT)
    assert code == 0 and summary["counters"]["conclusive"] == 2, summary["counters"]
    requests = _wire_requests(partial)
    agent = [e for e in requests if e["actor"] == "agent"]
    judge = [e for e in requests if e["actor"].startswith("judge")]
    assert agent and judge and len(agent) + len(judge) == len(requests)
    assert all(e["data"]["role"] == "agent" for e in agent) and all(e["data"]["role"] == "auxiliary" for e in judge)
    usages = [execution_usage(p) for p in sorted((partial / "aer").rglob("*.aer.jsonl"))]
    assert len(usages) == 2 and all(u is not None for u in usages)
    assert sum(len(u.judge_tokens_in) for u in usages if u) == len(judge)
    assert sum(u.calls for u in usages if u) == len(agent)


def test_an_errored_sample_makes_the_run_inconclusive(live_home: Path, tmp_path: Path) -> None:
    """D-743: a sample that errors in the harness (Inspect's log still says "success") is not a clean result: the cell
    is incomplete, counted inconclusive, and the run exits 1."""
    judge = [{"reply": "text", "content": "Answer: No"}] * 20
    script = {"agent": [{"fail": "http", "status": 500}] * 8, "judges": {"refusal_judge": judge, "semantic_judge": judge}}
    code, summary, _partial = _probe_shape(tmp_path, "errored", script)
    assert code == 1, summary
    assert summary["counters"]["conclusive"] == 0 and summary["counters"]["inconclusive"] == 2, summary["counters"]

def test_preflight_probe_through_the_real_worker(live_home: Path, tmp_path: Path) -> None:
    """D-742: the scripted preflight probe through this backend's real worker (every live backend kind has one)."""
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps([{"reply": "tool_calls", "calls": [{"name": "get_probe_value",
                                                                     "args": {"key": "q7f3-probe"}}]}]))
    code, _out, err = _main("run", "agentharm", "--preflight-only", "--llm-script", str(probe), "--progress", "off")
    assert code == 0, err
    assert "tool_calls=structured" in err and "roles=accepted (instruction_followed)" in err
