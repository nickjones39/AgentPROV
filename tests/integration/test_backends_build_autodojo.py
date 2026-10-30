"""``agentprov backends build autodojo`` for real (D.11.2; MN N.2.10; DoD row 9): the locked ``--no-config`` sync of
``backends/autodojo`` into a temporary ``$AGENTPROV_HOME`` (offline from the uv cache; ``AGENTPROV_TEST_BUILD_NETWORK=1``
lets uv download, as the CI job ``backend-autodojo`` does), then ``--offline-check``.

Asserted: the environment name ``autodojo-aa458794``; the marker's fork pin (PEP 610), lock digest, recorded
``hello`` identity and worker backend ``autodojo``; ``nltk_sha256`` recorded (``null`` while the recipe is unpinned or
uncached, with the NLTK status); the sandbox-exec feasibility probe recorded. Marker ``backend_autodojo`` (the core CI
job deselects it). Without the uv cache and without the network flag the build fails and the test skips."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_fake import repo_root  # noqa: E402

pytestmark = [pytest.mark.backend_autodojo, pytest.mark.slow,
              pytest.mark.skipif(os.name == "nt", reason="the backend environment is POSIX-only in v0.1")]

PIN = "aa458794b7eb7f082e94daeac4c0f55bfc0c90cc"


def _main(*argv: str) -> tuple[int, str, str]:
    from agentprov.cli.main import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def test_build_and_offline_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(home))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)
    monkeypatch.chdir(repo_root())
    argv = ["backends", "build", "autodojo", "--progress", "off"]
    if os.environ.get("AGENTPROV_TEST_BUILD_NETWORK") == "1":
        argv.append("--allow-network")
    code, _out, err = _main(*argv)
    if code != 0:
        pytest.skip(f"the AutoDojo environment could not be built (exit {code}): {err.strip().splitlines()[-1:]}")
    env = home / "envs" / "autodojo-aa458794"
    marker = json.loads((env / "AGENTPROV_ENV.json").read_text())
    assert marker["status"] == "complete" and marker["backend"] == "autodojo" and marker["commit"] == PIN
    assert marker["fork"] == {"kind": "git", "repo": "https://github.com/xhOwenMa/AutoDojo", "commit": PIN,
                              "subdirectory": "agentdojo"}
    assert marker["hello_identity"]["source"] == marker["fork"]
    assert marker["hello_worker"]["backend"] == "autodojo"
    assert "nltk_sha256" in marker and marker["nltk"]["status"] in ("provisioned", "recipe_unpinned", "not_cached")
    assert (marker["nltk_sha256"] is None) == (marker["nltk"]["status"] != "provisioned")
    assert marker["sandbox_status"] in ("passed", "failed", "not_applicable")
    assert {"shopping", "github", "dailylife"} <= set(marker["hello_identity"]["suite_set"])
    assert not (repo_root() / "backends" / "autodojo" / ".venv" / "AGENTPROV_ENV.json").exists()
    code, _out, err = _main("backends", "build", "autodojo", "--offline-check", "--progress", "off")
    assert code == 0, err
