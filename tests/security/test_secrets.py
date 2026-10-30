"""SEC-25 (K.12.11, G.9.2): how the live CLI reads ``.env``, and what it records about a custom endpoint.

``python-dotenv`` lives in the ``live`` extra, which the core CI job does not install, so a stub module stands in for
it; the stub fails the test if ``load_dotenv`` (which writes ``os.environ``) is ever called. Values here are synthetic.
"""

from __future__ import annotations

import argparse
import os
import sys
import types
from pathlib import Path

import pytest

from agentprov.cli.common import CommandResult
from agentprov.cli.live.envs import repository_root
from agentprov.cli.run import CliUsageError, LiveRefused, _read_env_file, _real_agent


def _parse(path: Path) -> dict[str, str | None]:
    pairs = (line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)
    return {k.strip(): v.strip() for k, v in pairs}


@pytest.fixture
def stub_dotenv(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    calls: list[Path] = []
    module = types.ModuleType("dotenv")
    module.dotenv_values = lambda path: (calls.append(Path(path)), _parse(Path(path)))[1]  # type: ignore[attr-defined]
    module.load_dotenv = lambda *a, **k: pytest.fail("load_dotenv writes os.environ")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dotenv", module)
    return calls


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "sub").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "agentprov"\n', encoding="utf-8")
    (root / ".env").write_text("DEEPSEEK_MODEL=from-root\nSENTINEL_KEY=sentinel-root-value\n", encoding="utf-8")
    (root / "sub" / ".env").write_text("DEEPSEEK_MODEL=from-cwd\n", encoding="utf-8")
    return root


def _args(**kw: object) -> argparse.Namespace:
    base = dict(env_file=None, model="deepseek", endpoint=None, model_id=None, allow_custom_endpoint=False,
                temperature=None, reasoning_effort=None, llm_element=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_sec25_env_is_read_from_the_repository_root_never_the_current_directory(
        repo: Path, stub_dotenv: list[Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo / "sub")
    before = dict(os.environ)
    root = repository_root()
    values = _read_env_file(_args(), root)
    assert root == repo.resolve() or root == repo
    assert values["DEEPSEEK_MODEL"] == "from-root" and stub_dotenv == [root / ".env"]
    assert dict(os.environ) == before and "SENTINEL_KEY" not in os.environ


def test_sec25_env_file_names_the_file_and_a_missing_one_is_a_usage_error(
        repo: Path, stub_dotenv: list[Path], tmp_path: Path) -> None:
    other = tmp_path / "keys.env"
    other.write_text("DEEPSEEK_MODEL=from-env-file\n", encoding="utf-8")
    assert _read_env_file(_args(env_file=str(other)), repo)["DEEPSEEK_MODEL"] == "from-env-file"
    with pytest.raises(CliUsageError):
        _read_env_file(_args(env_file=str(tmp_path / "missing.env")), repo)
    (repo / ".env").unlink()
    assert _read_env_file(_args(), repo) == {}  # no .env at the root: nothing, and never a fallback to the cwd


def test_sec25_a_custom_endpoint_is_accepted_only_with_the_flag_and_then_recorded() -> None:
    values = {"DEEPSEEK_API_KEY": "sk-sentinel-not-a-real-key-0123456789", "DEEPSEEK_MODEL": "m",
              "DEEPSEEK_BASE_URL": "https://proxy.example/v1"}
    with pytest.raises(LiveRefused):
        _real_agent(_args(), values, CommandResult())
    result = CommandResult()
    agent, _ = _real_agent(_args(allow_custom_endpoint=True), values, result)
    assert agent["base_url"] == "https://proxy.example/v1"
    assert any("--allow-custom-endpoint" in n and "(recorded)" in n for n in result.notices)
    for refused in ("http://proxy.example/v1", "https://proxy.example/v1?key=1"):  # never relaxed by the flag
        with pytest.raises(LiveRefused) as exc:
            _real_agent(_args(allow_custom_endpoint=True), dict(values, DEEPSEEK_BASE_URL=refused), CommandResult())
        assert exc.value.code == "cli.refused.endpoint"
