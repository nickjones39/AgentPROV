"""Gate C6, producer half (docs/architecture J.3.4 row C6; K.9.2; markers ``agentdojo`` + ``old_package``).

The same scripted scenario runs through the frozen baseline package and through this backend; this test produces both
sides' outputs as files, and the core comparer ``tests/migration/test_c6_old_vs_new.py`` (Python 3.14, which has the
capture mapper, the v1 view and the compat builder) compares them. The split is forced by the environments: the old side
needs the baseline interpreter, the new side this project's AgentDojo environment, the comparison the core package, and
no environment may hold two of them (J.1.6; AD-01).

For every scenario of :mod:`agentprov_backend.testing.c6` it writes, under ``$AGENTPROV_C6_WORK/<scenario>/``:

* ``scenario.json``: the scenario bundle (steps, the rendered wire responses, the old and new configurations);
* ``new/session/``: the sealed ``capture/0.1`` session of ``AgentDojoBackend.execute`` (``gateway_compat``, scripted
  transport, pipeline name ``<shorthand>/<model id>+prov``, display-name preset for attacked cells) and
  ``new/result.json``;
* ``old/``: what ``tools/migration/baseline_probe.py c6`` wrote under ``$AGENTPROV_BASELINE_PYTHON`` (``-I -B``, a
  scrubbed environment, the scenario directory as working directory): the generator's ``transcript.json`` and
  ``graph.json`` when it wrote them, ``requests/<n>.json`` and ``probe.json``;

and ``manifest.json`` (both environments' identities). It asserts only what each side must do on its own (the new
session verifies sealed with the expected status; the old generator wrote its pair or recorded the failure as
expected; neither side ran out of script) and that both sides made the **same number of wire requests**, the one
port-fidelity fact that needs no mapping. Without ``AGENTPROV_BASELINE_PYTHON`` it skips with the reason; without
``AGENTPROV_C6_WORK`` it writes into a temporary directory (nothing is compared then).
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from agentprov_backend.testing.c6 import C6_SCENARIOS, bundle

from support import assert_capture_invariants, run_cell

pytestmark = pytest.mark.old_package

REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE = REPO_ROOT / "tools" / "migration" / "baseline_probe.py"
ENV_BASELINE_PYTHON = "AGENTPROV_BASELINE_PYTHON"
ENV_WORK = "AGENTPROV_C6_WORK"


def _baseline_python() -> Path:
    value = os.environ.get(ENV_BASELINE_PYTHON, "").strip()
    if not value:
        pytest.skip(f"{ENV_BASELINE_PYTHON} is not set: build the baseline environment with "
                    "tools/migration/build_baseline_env.py (old_package gate)")
    path = Path(value).expanduser()
    if not path.is_file():
        pytest.fail(f"{ENV_BASELINE_PYTHON} does not name an interpreter")
    return path


@pytest.fixture(scope="module")
def work(tmp_path_factory: pytest.TempPathFactory) -> Path:
    value = os.environ.get(ENV_WORK, "").strip()
    root = Path(value).expanduser() if value else tmp_path_factory.mktemp("c6")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _probe(python: Path, args: list[str], cwd: Path) -> None:
    home = cwd / ".home"
    home.mkdir(exist_ok=True)
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "TZ": "UTC", "LC_ALL": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([str(python), "-I", "-B", str(PROBE), *args], cwd=cwd, env=env, capture_output=True,
                          timeout=600)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")[-2000:]


@pytest.mark.parametrize("name", sorted(C6_SCENARIOS))
def test_c6_scenario_both_sides(name: str, work: Path) -> None:
    python = _baseline_python()
    sc = C6_SCENARIOS[name]
    data = bundle(sc)
    d = work / name
    if d.exists():
        import shutil

        shutil.rmtree(d)
    (d / "new").mkdir(parents=True)
    (d / "scenario.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------ new side
    new = data["new"]
    run = run_cell(d, new["cell"], new["agent"], data["steps"], backend_config=new["backend_config"],
                   session_dir=d / "new" / "session")
    assert_capture_invariants(run)
    assert run.result.status == sc.expect_status
    assert run.transport.remaining == 0, "the new side did not consume the whole script"
    (d / "new" / "result.json").write_text(json.dumps(
        {"status": run.result.status, "outcome": run.result.outcome, "capture_head": run.result.capture_head,
         "n_requests": len(run.transport.bodies)}, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------ old side
    _probe(python, ["c6", "--scenario", str(d / "scenario.json"), "--out", str(d / "old")], d)
    probe = json.loads((d / "old" / "probe.json").read_text(encoding="utf-8"))
    assert not probe["script_exhausted"], "the baseline asked for more responses than the script has"
    assert (d / "old" / "transcript.json").is_file() == sc.expect_old_written
    assert (d / "old" / "graph.json").is_file() == sc.expect_old_written
    assert (probe["row"]["error"] is None) == sc.expect_old_written

    # ------------------------------------------------------------------ the one comparison that needs no mapping
    assert probe["n_requests"] == len(run.transport.bodies), (probe["n_requests"], len(run.transport.bodies))


def test_c6_manifest(work: Path) -> None:
    python = _baseline_python()
    import importlib.metadata as md

    ident = work / ".baseline-identity"
    _probe(python, ["identity", "--out", str(ident)], work)
    baseline = json.loads((ident / "probe.json").read_text(encoding="utf-8"))
    record_path = python.parent.parent / "AGENTPROV_BASELINE.json"
    record: Any = json.loads(record_path.read_text(encoding="utf-8")) if record_path.is_file() else None
    manifest = {
        "format": "agentprov-c6-work/1",
        "scenarios": sorted(C6_SCENARIOS),
        "new": {"python": sys.version.split()[0], "platform": platform.platform(),
                "versions": {n: md.version(n) for n in ("agentdojo", "openai", "agentprov-backend",
                                                        "agentprov-capture")}},
        "old": {"python": baseline["python"], "versions": baseline["versions"],
                "direct_url": baseline["direct_url"], "env_record": record},
    }
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert baseline["versions"]["agentdojo-prov"] == "1.0.0"
