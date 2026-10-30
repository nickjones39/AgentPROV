"""D.11.2 / D.11.5 offline guarantee: importing the fork (every suite, the attack registry, the LLM module) and running
a scripted cell make **no** network attempt, counted by the socket guard (``netguard.attempts``; a library that
swallows ``NetworkBlocked``, as ``nltk.download`` does, would still be counted). Runs in a fresh interpreter with an
explicit environment that holds no key variable and no ``NLTK_DATA``.

It also records what the D.11.2 NLTK provisioning relies on: the installed fork imports ``nltk`` only lazily inside the
filter defences (``agent_pipeline/filter_defenses/*``), never at import; ``suite_gen_utils.py`` (the import-time
``nltk.download("punkt_tab")``) belongs to ``variant_generation``, which the installed package does not contain; and
the locked ``nltk`` loads ``punkt_tab`` from an unextracted zip under ``NLTK_DATA`` (checked here with a synthetic
zip, not the real data)."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
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
from agentprov_backend.autodojo import AutoDojoBackend
AutoDojoBackend().identity()
from support import run_scenario
results = []
with tempfile.TemporaryDirectory() as t:
    for name in ("autodojo_banking_important_instructions", "autodojo_banking_cache_replay"):
        results.append(run_scenario(Path(t) / name, name).result.status)
nltk_loaded = "nltk" in sys.modules
print(json.dumps({"attempts": netguard.attempts, "statuses": results, "nltk_imported": nltk_loaded,
                  "keys": sorted(k for k in __import__("os").environ if "KEY" in k or "TOKEN" in k)}))
"""


def _env() -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "HOME": "/nonexistent-home"}


def test_importing_the_fork_and_running_cells_makes_no_network_attempt():
    proc = subprocess.run([sys.executable, "-I", "-B", "-c", _CHILD, str(TESTS)], capture_output=True, env=_env(),
                          timeout=600, check=False)
    assert proc.returncode == 0, proc.stderr.decode()[-3000:]
    result = json.loads(proc.stdout.decode().strip().splitlines()[-1])
    assert result["attempts"] == []
    assert result["statuses"] == ["complete", "complete"]
    assert result["nltk_imported"] is False          # nltk is only imported by the (refused) filter defences
    assert result["keys"] == []


def test_nltk_is_imported_only_lazily_by_the_fork():
    import importlib.util

    import agentdojo

    root = Path(agentdojo.__file__).parent
    top_level = []
    for path in sorted(root.rglob("*.py")):
        if path.name.startswith("._"):
            continue  # AppleDouble files shipped by the fork (no Python source)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(("import nltk", "from nltk")):
                top_level.append(path.relative_to(root).as_posix())
    assert top_level == []
    assert importlib.util.find_spec("agentdojo.variant_generation") is None


def test_nltk_loads_punkt_tab_from_an_unextracted_zip(tmp_path):
    """The provisioning keeps ``tokenizers/punkt_tab.zip`` unextracted; nltk's ``find`` reads it from the zip."""
    root = tmp_path / "nltk_data" / "tokenizers"
    root.mkdir(parents=True)
    with zipfile.ZipFile(root / "punkt_tab.zip", "w") as z:
        for name, text in (("collocations.tab", ""), ("sent_starters.txt", ""), ("abbrev_types.txt", "dr\n"),
                           ("ortho_context.tab", "")):
            z.writestr(f"punkt_tab/english/{name}", text)
    code = ("import nltk, json; print(json.dumps(nltk.sent_tokenize('See Dr. Smith. He waits.')))")
    proc = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, timeout=120, check=False,
                          env={**_env(), "NLTK_DATA": str(tmp_path / "nltk_data")})
    assert proc.returncode == 0, proc.stderr.decode()[-2000:]
    assert json.loads(proc.stdout) == ["See Dr. Smith.", "He waits."]
    assert not (root / "punkt_tab").exists()          # nothing was extracted
