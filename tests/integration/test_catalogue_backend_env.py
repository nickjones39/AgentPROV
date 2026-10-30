"""D-652 against a real backend environment (opt-in): the worker op ``catalogue`` of this checkout's
``backends/shared`` source, run by a backend environment's interpreter, and T0's ``checked_catalogue`` over its reply.

Skipped unless ``AGENTPROV_TEST_BACKEND_PYTHON`` names a backend interpreter, e.g. ``backends/agentdojo/.venv/bin/python``
or ``$AGENTPROV_HOME/envs/autodojo-<commit>/bin/python``. The worker runs with ``-I -B`` (no bytecode written), the
network guard on (``AGENTPROV_BLOCK_NETWORK=1``) and a temporary ``HOME``; nothing is synced, built or downloaded. The
core never imports the benchmark: only the subprocess does.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ENV_PYTHON = os.environ.get("AGENTPROV_TEST_BACKEND_PYTHON")
REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(not ENV_PYTHON, reason="set AGENTPROV_TEST_BACKEND_PYTHON to a backend interpreter")

_DRIVER = ("import sys; sys.path.insert(0, sys.argv[1]); "
           "from agentprov_backend.worker import main; sys.exit(main())")


def _replies(tmp_path: Path, *messages: dict[str, object]) -> list[dict[str, object]]:
    lines = "".join(json.dumps({"v": "agentprov-backend/0.1", **m}) + "\n" for m in messages)
    env = {"AGENTPROV_BLOCK_NETWORK": "1", "HOME": str(tmp_path), "PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8"}
    done = subprocess.run([str(ENV_PYTHON), "-I", "-B", "-c", _DRIVER, str(REPO / "backends" / "shared" / "src")],
                          input=lines.encode(), capture_output=True, env=env, timeout=600, check=False)
    assert done.returncode == 0, done.stderr.decode(errors="replace")[-2000:]
    return [json.loads(line) for line in done.stdout.splitlines()]


def test_the_catalogue_of_a_real_backend_passes_the_t0_checks(tmp_path: Path) -> None:
    from agentprov.cli.run import checked_catalogue

    hello, reply, refused = _replies(
        tmp_path, {"op": "hello", "nonce": "n", "expect": {}}, {"op": "catalogue", "req": "c"},
        {"op": "catalogue", "req": "d", "benchmark_version": "v0-not-a-version"}, {"op": "shutdown"})
    assert hello["op"] == "hello_ok" and reply["op"] == "catalogue_ok" and refused["op"] == "catalogue_refused"
    backend = hello["worker"]["backend"]  # type: ignore[index]
    doc = checked_catalogue(reply["catalogue"], str(backend))
    names = {s["name"] for s in doc["suites"]}
    assert {"workspace", "travel", "banking", "slack"} <= names  # the four AgentDojo suites, in both backends
    assert all(s["user_tasks"] and s["injection_tasks"] for s in doc["suites"])
    assert all(isinstance(s["tool_definition_chars"], int) and s["tool_definition_chars"] > 0 for s in doc["suites"])
    attacks = {a["name"]: a for a in doc["attacks"]}
    assert "important_instructions" in attacks and not attacks["important_instructions"]["dos"]
    assert {n for n, a in attacks.items() if a["dos"]} >= {"dos", "captcha_dos", "felony_dos", "offensive_email_dos",
                                                           "swearwords_dos"}
    if backend == "autodojo":
        assert attacks["ours"]["refused"] and attacks["autodojo"]["needs"] == ["--autodojo-cache", "--autodojo-variant"]
    else:
        assert all(a["refused"] is None and not a["needs"] for a in attacks.values())
