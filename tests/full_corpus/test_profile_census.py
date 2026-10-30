"""Profile census: every ``observed`` count of every AgentDojo-family profile part, against its full pinned snapshot
(docs/architecture D.6.10 item 3, D.6.12 item 8; phase 10).

Local only (marker ``full_corpus``). For each profile of the ``agentdojo`` family with an ``[import]`` table and each part
with ``observed`` counts, the part's primary git pin is read from the bare, extraction-free fetch cache
(``$AGENTPROV_UPSTREAM_CACHE``, default ``$AGENTPROV_HOME/cache``); a part whose pinned commit is not in the cache is
skipped. Every blob is mapped and sealed and the census of :mod:`agentprov.adapters.agentdojo.census` must reproduce every
declared count exactly (``tools/agentdojo/profile_census.py``). About 2 minutes for the AgentDojo head part on an M2 Max
with 10 workers. Wave-2 profiles join automatically.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "agentdojo"))

import profile_census  # noqa: E402

from agentprov.adapters.profiles import load_profile  # noqa: E402

pytestmark = pytest.mark.full_corpus


def _parts() -> list[tuple[str, str]]:
    root = REPO / "src" / "agentprov" / "adapters" / "agentdojo" / "profiles"
    out = []
    for path in sorted(root.glob("*.profile.toml")):
        profile = load_profile(path.name.removesuffix(".profile.toml"))
        if profile.data.get("import", {}).get("mapper") != "agentdojo.tracelogger":
            continue
        if profile.data["import"].get("dialect") != "agentdojo.tracelogger":  # results containers: test_rescont (D-470)
            continue
        quirks = profile.data.get("family", {}).get("agentdojo", {}).get("quirk", ())
        parts = sorted({part for q in quirks for part in q.get("observed", {})})
        out.extend((profile.id, part) for part in parts)
    return out


@pytest.mark.parametrize(("profile_id", "part"), _parts())
def test_every_observed_count_is_reproduced(request: pytest.FixtureRequest, profile_id: str, part: str):
    if "full_corpus" not in str(request.config.getoption("markexpr")):
        pytest.skip("a full-snapshot census takes minutes: select it with `pytest -m full_corpus`")
    from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir

    profile = load_profile(profile_id)
    source = profile.data["source"]
    pin = profile_census.census_pin(profile, part)  # its own pin, or the primary pin serving it by variant_labels
    if pin.get("kind") != "git":
        pytest.skip(f"{profile_id} · {part}: not a git pin")
    recipe = Recipe.from_pin(pin, canonical_repo=source.get("canonical_repo"))
    if not Fetcher(resolve_cache_dir(None)).plan(recipe).cached:
        pytest.skip(f"{profile_id} · {part}: the pinned commit is not in the fetch cache (U-07)")
    report = profile_census.census(profile_id, part, workers=int(os.environ.get("AGENTPROV_JOBS", "10")))
    assert report["crashes"] == [] and report["status"].get("degenerate", 0) == 0, report["status"]
    assert report["differences"] == [], report["differences"]
