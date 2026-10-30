"""D-541: ``agentprov.api.rows(corpus, "lineage")`` from a sealed manifest (MN M.6; O.3.5 F5).

The rows come from ``corpus.json`` ``sources[]`` (the snapshots and the profile's ``[lineage]`` recorded at sealing)
and ``raw/origins.jsonl``; nothing is read from the profile files themselves. A working corpus has no
``sources[].lineage`` and still raises ``ApiUnavailable``. The fixture is the sealed three-log corpus ``mini-mit``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agentprov import api

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "unit" / "release"),
                str(Path(__file__).resolve().parents[1] / "unit" / "corpus")]
import release_support as rs  # noqa: E402

COLUMNS = {"from_node", "to_node", "relation", "n", "basis"}
UPSTREAM = "https://github.com/ethz-spylab/agentdojo@c274885610efaaafec38b6d3eb07152ba7ff3f94"


@pytest.fixture
def sealed(tmp_path_factory: pytest.TempPathFactory, tmp_path: Path) -> Path:
    return rs.sealed(tmp_path_factory, tmp_path / "corpora")


def test_lineage_rows_of_a_sealed_corpus(sealed):
    rows = list(api.rows(api.open_corpus(sealed), "lineage"))
    assert rows and all(set(r) == COLUMNS for r in rows)
    by = {(r["from_node"], r["to_node"], r["relation"]): r for r in rows}
    snapshot = by[("agentdojo", UPSTREAM, "snapshot_of")]
    assert snapshot["n"] == 3 and snapshot["basis"] == "corpus.json"
    mirror = by[("agentdojo", "agentdojo-inspect", "mirror")]  # path runs/**: every one of the three logs
    assert mirror["n"] == 3 and mirror["basis"] == "profile [lineage]; raw/origins.jsonl"
    assert by[("agentdojo", "adprov-v1/converted-legacy", "derived_conversion")]["n"] == 0
    assert by[("agentdojo", "agent-security-tools-survey/zenodo-bundled-runs", "mirror")]["n"] == 0
    assert not [r for r in rows if r["relation"] == "byte_identical"]  # no digest has two origins here
    assert rows == list(api.rows(api.open_corpus(sealed), "lineage"))  # deterministic order


def test_a_corpus_without_recorded_lineage_says_so(sealed):
    def drop(manifest: dict) -> None:
        for source in manifest["sources"]:
            source.pop("lineage", None)

    rs.restamp(sealed, drop)
    with pytest.raises(api.ApiUnavailable, match="lineage"):
        list(api.rows(api.open_corpus(sealed, verify="none"), "lineage"))
