"""Offline guarantee and the D-681 import audit (D-688 T4), in a fresh interpreter with an explicit environment that
holds no key variable: importing AgentDyn (every suite version, the attack registry, the LLM module) and running the
scripted cells S1..S4 make **no** network attempt (``netguard.attempts``), and import none of the seven dependencies
overridden out of the environment and nothing under ``agentdojo.defenses`` (the vendored CaMeL, DRIFT and Progent)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent

_CHILD = r"""
import json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from agentprov_backend.testing import netguard
netguard.install()
time.sleep = lambda s: None
import agentdojo, agentdojo.attacks, agentdojo.agent_pipeline.llms.openai_llm, agentdojo.benchmark, agentdojo.logging
from agentdojo.task_suite.load_suites import get_suites
for version in ("v1", "v1.1", "v1.1.1", "v1.1.2", "v1.2", "v1.2.1", "v1.2.2"):
    get_suites(version)
from agentprov_backend.agentdyn import AgentDynBackend
AgentDynBackend().identity()
AgentDynBackend().catalogue()
from support import SCENARIOS, run_scenario
statuses = []
with tempfile.TemporaryDirectory() as t:
    for name in SCENARIOS:
        statuses.append(run_scenario(Path(t) / name, name).result.status)
mods = sorted(m for m in sys.modules if m.split(".")[0] in {
    "cyclopts", "pydantic_ai", "tiktoken", "vertexai", "jsonref", "openapi_pydantic", "json_repair", "camel",
    "secagent"} or m.startswith("agentdojo.defenses"))
print(json.dumps({"attempts": netguard.attempts, "statuses": statuses, "modules": mods,
                  "keys": sorted(k for k in __import__("os").environ if "KEY" in k or "TOKEN" in k)}))
"""


def test_agentdyn_runs_offline_and_imports_nothing_overridden_or_from_defences():
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "HOME": "/nonexistent-home"}
    proc = subprocess.run([sys.executable, "-I", "-B", "-c", _CHILD, str(TESTS)], capture_output=True, env=env,
                          timeout=600, check=False)
    assert proc.returncode == 0, proc.stderr.decode()[-3000:]
    result = json.loads(proc.stdout.decode().strip().splitlines()[-1])
    assert result["attempts"] == []
    assert result["statuses"] == ["complete"] * 4
    assert result["modules"] == []
    assert result["keys"] == []


def test_the_overridden_dependencies_are_not_installed():
    import importlib.util

    for name in ("cyclopts", "pydantic_ai", "tiktoken", "vertexai", "jsonref", "openapi_pydantic", "json_repair"):
        assert importlib.util.find_spec(name) is None, name
