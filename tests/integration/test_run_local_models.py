"""``agentprov run`` with a local model server (D-691..D-695), against the fake backend environment and a stub server.

No benchmark package, no model and no network beyond loopback: :mod:`live_fake` provides the environment (its worker
writes canned capture logs), :class:`agentprov.testing.local_server.StubServer` the server. The planned-status gate is
admitted as if scripted (as in ``test_run_spawn.real_model``), ``.env`` is empty, and the paid-call preflight probe is
replaced by a canned verdict.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from agentprov.testing.local_server import StubServer

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
def local(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """The gates a test can pass without a model: planned status admitted, empty ``.env``, consent recorded, and the
    preflight probe answered with a clean verdict (structured tool calls, roles accepted)."""
    from agentprov.cli import run as run_mod

    calls: list[str] = []
    gate = run_mod._live_capability
    monkeypatch.setattr(run_mod, "_live_capability", lambda source, result, *, scripted: gate(source, result, scripted=True))
    monkeypatch.setattr(run_mod, "_read_env_file", lambda args, root: {})
    consent = run_mod._consent

    def record_consent(*args: Any, **kwargs: Any) -> None:
        calls.append("consent")
        consent(*args, **kwargs)

    def canned_probe(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append("preflight")
        return {"reachable": True, "roles_accepted": True, "roles": "accepted", "http_status": 200,
                "tool_calls": "structured", "params": {"not_transmitted": []}}

    monkeypatch.setattr(run_mod, "_consent", record_consent)
    monkeypatch.setattr(run_mod, "_preflight", canned_probe)
    yield calls


def _dry(cli: Callable[..., Run], tmp_path: Path, *extra: str) -> Run:
    return cli("run", "agentdojo", "--dry-run", "--containment", "vm", "--corpus", str(tmp_path / "corpus"),
               "--campaign", "t", "--suite", "banking", "--progress", "off", *extra)


def test_dry_run_shows_the_local_model_and_the_zero_cost_estimate(home: Path, tmp_path: Path, cli, local) -> None:
    make_fake_env(home, "ok")
    with StubServer("ollama") as srv:
        run = _dry(cli, tmp_path, "--endpoint", "ollama", "--base-url", srv.base_url, "--model-id", "tiny-llm:1b")
    assert run.code == 0, run.err
    assert "model tiny-llm:1b on ollama" in run.err and "server ollama 0.0.1-stub" in run.err
    assert "digest sha256:" + "a" * 64 in run.err and "quantization_level Q4_K_M" in run.err
    assert "estimate: cost $0.00 (local endpoint); time: needs a measured throughput" in run.err
    assert not (home / "cache" / "model-digests.jsonl").exists()  # a dry run writes nothing (N.1.6)
    assert local == []  # no consent asked and no probe made by a dry run


def test_a_missing_model_id_lists_the_served_models(home: Path, tmp_path: Path, cli, local) -> None:
    make_fake_env(home, "ok")
    with StubServer("lmstudio") as srv:
        run = _dry(cli, tmp_path, "--model", "lmstudio", "--base-url", srv.base_url)
    assert run.code == 3 and "no model id" in run.err and "tiny-model-4bit" in run.err, run.err


def test_an_unserved_model_and_the_wrong_server_kind_are_refused(home: Path, tmp_path: Path, cli, local) -> None:
    make_fake_env(home, "ok")
    with StubServer("vllm") as srv:
        missing = _dry(cli, tmp_path, "--endpoint", "vllm", "--base-url", srv.base_url, "--model-id", "nope")
        wrong = _dry(cli, tmp_path, "--endpoint", "omlx", "--base-url", srv.base_url, "--model-id", "stub-org/tiny-model-4bit")
    assert missing.code == 3 and "stub-org/tiny-model-4bit" in missing.err, missing.err
    assert wrong.code == 4 and "vllm, not omlx" in wrong.err, wrong.err


def test_a_non_loopback_base_url_is_refused(home: Path, tmp_path: Path, cli, local) -> None:
    make_fake_env(home, "ok")
    run = _dry(cli, tmp_path, "--model", "lmstudio", "--base-url", "http://8.8.8.8:1234/v1", "--model-id", "m",
               "--allow-lan-endpoint")
    assert run.code == 4 and "refused" in run.err, run.err


def test_a_lan_base_url_needs_the_opt_in(home: Path, tmp_path: Path, cli, local) -> None:
    make_fake_env(home, "ok")
    run = _dry(cli, tmp_path, "--model", "lmstudio", "--base-url", "http://192.168.1.20:1234/v1", "--model-id", "m")
    assert run.code == 4 and "must be loopback" in run.err, run.err


def test_lmstudio_without_native_tool_use_needs_allow_text_tool_calls(home: Path, tmp_path: Path, cli, local) -> None:
    make_fake_env(home, "ok")
    with StubServer("lmstudio") as srv:
        refused = _dry(cli, tmp_path, "--model", "lmstudio", "--base-url", srv.base_url, "--model-id", "plain-model")
        allowed = _dry(cli, tmp_path, "--model", "lmstudio", "--base-url", srv.base_url, "--model-id", "plain-model",
                       "--allow-text-tool-calls")
    assert refused.code == 4 and "tool-use system prompt" in refused.err, refused.err
    assert allowed.code == 0, allowed.err


def test_local_options_need_a_local_endpoint(home: Path, tmp_path: Path, cli, local) -> None:
    for extra in (("--base-url", "http://127.0.0.1:1/v1"), ("--no-hash-weights",), ("--allow-lan-endpoint",)):
        run = _dry(cli, tmp_path, "--model", "deepseek", *extra)
        assert run.code == 2 and "goes with a local endpoint" in run.err, run.err


def test_a_run_records_the_local_model(home: Path, tmp_path: Path, cli, local) -> None:
    """The manifest carries the plan's identity record and the accepted served ids, consent names no billing, and T0
    re-observes the model before each cell (the fake worker's canned logs make no model call, so A12 has nothing to
    check here; tests/cli/test_live_units.py covers it)."""
    make_fake_env(home, "ok")
    with StubServer("ollama") as srv:
        run = cli("run", "agentdojo", "--containment", "vm", "--corpus", str(tmp_path / "corpus"), "--campaign", "t",
                  "--suite", "banking", "--progress", "off", "--endpoint", "ollama", "--base-url", srv.base_url,
                  "--model-id", "tiny-llm:1b", "--i-consent-to-api-costs", "--accept-served-model", "tiny-llm:latest",
                  "--max-attempts", "1", "--canary", "1", "--repeats", "2")
        shows = [s for s in srv.seen if s["method"] == "POST"]
    assert local == ["consent", "preflight"]
    assert "local model server: no provider billing" in run.err
    assert run.code == 0, run.err
    live = json.loads((tmp_path / "corpus.partial" / "corpus.json").read_text())["live"]
    (record,) = live["local_models"].values()
    assert record["model_id"] == "tiny-llm:1b" and record["server_identity"]["digest"] == "sha256:" + "a" * 64
    assert live["accepted_served_models"] == ["tiny-llm:latest"]
    assert live["model_requested"] == "tiny-llm:1b"
    assert len(shows) == 3  # the plan's observation, then T0's re-observation before each of the two cells


def test_a_model_changed_mid_campaign_stops_the_campaign_at_the_canary(home: Path, tmp_path: Path, cli, local) -> None:
    """A14: the server re-serves the same tag with another digest after the plan was made; T0's per-cell observation
    says so, the worker records it, and the canary stops the campaign."""
    from agentprov.testing.local_server import default_models

    make_fake_env(home, "ok")
    with StubServer("ollama") as srv:
        from agentprov.cli import run as run_mod

        resolve = run_mod._resolve_local

        def then_swap(*args: Any, **kwargs: Any) -> Any:
            out = resolve(*args, **kwargs)
            models = default_models("ollama")
            models[0]["digest"] = "d" * 64  # re-pulled under the same name
            srv.set("/api/tags", 200, {"models": models})
            return out

        mp = pytest.MonkeyPatch()
        mp.setattr(run_mod, "_resolve_local", then_swap)
        try:
            run = cli("run", "agentdojo", "--containment", "vm", "--corpus", str(tmp_path / "corpus"), "--campaign",
                      "t", "--suite", "banking", "--progress", "off", "--endpoint", "ollama", "--base-url",
                      srv.base_url, "--model-id", "tiny-llm:1b", "--i-consent-to-api-costs", "--max-attempts", "1",
                      "--canary", "1", "--repeats", "3")
        finally:
            mp.undo()
    assert run.code == 1 and "the canary found a misconfiguration" in run.err, run.err
    live = json.loads((tmp_path / "corpus.partial" / "corpus.json").read_text())["live"]
    assert live["quality"]["models"]["scripted-fake"]["local_model_drift"] == 1


def test_run_takes_the_base_url_from_settings_then_the_flag(home: Path, tmp_path: Path, cli, local) -> None:
    """D-699: --base-url > .env > agentprov settings > the registry default."""
    from agentprov import settings

    make_fake_env(home, "ok")
    with StubServer("ollama") as srv, StubServer("ollama") as other:
        settings.set("endpoints.ollama.base_url", srv.base_url)
        from_settings = _dry(cli, tmp_path, "--endpoint", "ollama", "--model-id", "tiny-llm:1b")
        from_flag = _dry(cli, tmp_path, "--endpoint", "ollama", "--model-id", "tiny-llm:1b", "--base-url", other.base_url)
    assert from_settings.code == 0 and f"({srv.base_url}; server ollama" in from_settings.err, from_settings.err
    assert from_flag.code == 0 and f"({other.base_url}; server ollama" in from_flag.err


def test_the_static_local_names_equal_the_registry() -> None:
    from agentprov.cli.live.localmodels import local_endpoint_names
    from agentprov.cli.run import ENDPOINT_NAMES, LOCAL_ENDPOINT_NAMES

    assert sorted(LOCAL_ENDPOINT_NAMES) == local_endpoint_names()
    assert set(LOCAL_ENDPOINT_NAMES) <= set(ENDPOINT_NAMES)
