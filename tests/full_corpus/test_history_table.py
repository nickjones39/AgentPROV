"""The AgentDojo history indexes and table against the real blobless history of ethz-spylab/agentdojo (D.6.16).

Local only (marker ``full_corpus``): needs the history cache that ``agentprov fetch --profile agentdojo-upstream --history
--allow-network`` makes (``$AGENTPROV_UPSTREAM_CACHE``, default ``$AGENTPROV_HOME/cache``); a missing index skips the test.
Nothing here uses the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "agentdojo"))

import history_table  # noqa: E402

from agentprov.adapters.agentdojo.profile import family_table  # noqa: E402
from agentprov.adapters.profiles import load_profile  # noqa: E402
from agentprov.raw.fetch import Fetcher, Recipe, resolve_cache_dir  # noqa: E402

pytestmark = pytest.mark.full_corpus


def _recipes() -> dict[str, Recipe]:
    source = load_profile("agentdojo-upstream").data["source"]
    return {
        part: Recipe.from_pin(next(dict(p) for p in source["pins"] if p.get("part") == part and p.get("primary") is True),
                              canonical_repo=source["canonical_repo"])
        for part in ("2024-06", "head")
    }


@pytest.fixture(scope="module")
def indexes():
    fetcher = Fetcher(resolve_cache_dir(None))
    out = {}
    for part, recipe in _recipes().items():
        index = fetcher.history_index(recipe)
        if index is None:
            pytest.skip(f"no history index for {part}: run `agentprov fetch --profile agentdojo-upstream --history --allow-network`")
        out[part] = (recipe, index)
    return out


def test_the_shipped_table_is_what_the_tool_regenerates_from_the_history(indexes):
    assert history_table.build(resolve_cache_dir(None)) == history_table.DEFAULT_OUT.read_text(encoding="utf-8")


def test_every_blob_of_both_pinned_trees_has_an_introducing_commit_the_table_lists(indexes):
    table = family_table(load_profile("agentdojo-upstream")).history
    assert table is not None
    for part, (recipe, index) in indexes.items():
        entries, _ = Fetcher(resolve_cache_dir(None)).git_tree(Recipe(kind="git", repo=recipe.repo, commit=recipe.commit))
        tree = {e.path: e.oid for e in entries if e.is_blob}
        assert {p for p, _b in index.rows} == set(tree), part
        assert all(index.lookup(p, oid) is not None for p, oid in tree.items()), part
        runs = [(p, oid) for p, oid in tree.items() if p.startswith("runs/")]
        assert len(runs) == recipe.expected_files, part
        for path, oid in runs:
            assert table.date(index.rows[(path, oid)]) == index.date_of(index.rows[(path, oid)]), (part, path)


def test_a_blob_present_in_both_trees_has_the_same_introducing_commit(indexes):
    (_r1, june), (_r2, head) = indexes["2024-06"], indexes["head"]
    shared = set(june.rows) & set(head.rows)
    assert len(shared) > 10000
    assert all(june.rows[k] == head.rows[k] for k in shared)
    assert all(june.date_of(c) == head.date_of(c) for c in set(june.rows.values()) if c in head.commits)


def _eras(index, table):
    counts: dict[str, int] = {}
    for (path, _blob), commit in index.rows.items():
        if path.startswith("runs/"):
            era = table.era(commit)
            key = era.candidate + ("" if era.registered else " (pre_versioning)")
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def test_the_era_distribution_of_both_pinned_trees(indexes):
    """The counts reproduce the investigation: 18,241 June-2024 files predate the label (18,234 baseline + 7 Mixtral); the
    head tree's 11,765 new-format files are the 2025-07-25 batch, and 14,182 head files are the baseline's unchanged ones."""
    table = family_table(load_profile("agentdojo-upstream")).history
    assert table is not None
    assert _eras(indexes["2024-06"][1], table) == {"v1 (pre_versioning)": 18241}
    head = _eras(indexes["head"][1], table)
    assert head == {"v1": 4470, "v1 (pre_versioning)": 14182, "v1.1": 1088, "v1.1.1": 2259, "v1.2": 2915, "v1.2.1": 11765}
    assert sum(head.values()) - head["v1.2.1"] == 24914  # the old-format (v0.k11) files: the ones that record no version
