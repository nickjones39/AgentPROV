"""`agentprov import autodojo`: the live part has no import; the ROPE-hosted slice (part `rope-slice`, `via = "rope"`) is
imported through source rope, selected by its attack (D.3.1, D.3.3; D.6.13)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "rope"
#: The user's fetch cache, resolved at import time (the ``cli`` fixture then isolates $AGENTPROV_HOME); read only, and
#: only by the local ``full_corpus`` test below.
CACHE = os.environ.get("AGENTPROV_UPSTREAM_CACHE") or str(Path(os.environ.get("AGENTPROV_HOME") or Path.home() / ".agentprov") / "cache")


def test_restrict_attack_narrows_and_never_widens():
    from agentprov.adapters.runner.importer import ImportFilters
    from agentprov.cli.import_ import _restrict_attack

    assert _restrict_attack(ImportFilters(), "autodojo").select == {"attack": frozenset({"autodojo"})}
    chosen = ImportFilters(select={"attack": frozenset({"autodojo", "none"}), "suite": frozenset({"slack"})})
    assert _restrict_attack(chosen, "autodojo").select == {"attack": frozenset({"autodojo"}), "suite": frozenset({"slack"})}
    assert _restrict_attack(ImportFilters(select={"attack": frozenset({"none"})}), "autodojo").select["attack"] == frozenset()


@pytest.mark.full_corpus
def test_the_rope_slice_is_imported_via_rope(request: pytest.FixtureRequest, cli, tmp_path):
    """Local (marker ``full_corpus``): needs the ROPE pin in the user's fetch cache (tools/seed_git_cache.py)."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.raw.fetch import Fetcher, Recipe

    if "full_corpus" not in str(request.config.getoption("markexpr")):
        pytest.skip("reads the user's fetch cache: select it with `pytest -m full_corpus`")
    if not (FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the rope fixtures are not present")
    profile = load_profile("rope")
    pin = next(dict(p) for p in profile.data["source"]["pins"] if p.get("primary"))
    if not Fetcher(Path(CACHE)).plan(Recipe.from_pin(pin, canonical_repo=profile.data["source"]["canonical_repo"])).cached:
        pytest.skip("the ROPE pin is not in the fetch cache")
    run = cli("import", "autodojo", "--input", str(FIXTURES), "--verify-against-pin", "--until", "aer",
              "--cache-dir", CACHE, "--corpus", str(tmp_path / "c"), "--json")
    assert run.code == 0, run.err
    data = json.loads(run.out)
    autodojo = sum(1 for e in json.loads((FIXTURES / "SOURCE.json").read_bytes()) if "/autodojo/" in e["original_path"])
    assert (data["counters"]["mapped"], data["counters"]["filtered"]) == (autodojo, 12 - autodojo), data["counters"]
    assert any("imported via source rope" in n for n in data["notices"])
    assert any("--select attack=autodojo implied" in n for n in data["notices"])
    assert data["corpus"]["corpus_id"] == "rope"
