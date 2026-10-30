"""The pre-check's Level-2 sampler (``tools/precheck/l2_sample.py``): the pre-registered rule of README §4 on synthetic
unit rows only (determinism, bounds, proportional reduction, stratum floor), and the glob escaping of sampled labels."""

from __future__ import annotations

import fnmatch
import random
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[3] / "tools" / "precheck"


@pytest.fixture(scope="module")
def ls():
    sys.path.insert(0, str(TOOLS))
    try:
        import l2_sample

        yield l2_sample
    finally:
        sys.path.remove(str(TOOLS))


def _rows(sizes: dict[str, int], *, parse: str = "ok") -> list[dict[str, object]]:
    return [{"label": f"runs/{s}/u{i:04d}.json", "stratum": s, "parse": parse, "sha256": f"{i:064x}"}
            for s, n in sizes.items() for i in range(n)]


def test_fewer_than_30_units_takes_all(ls) -> None:
    doc = ls.select(_rows({"a": 3, "b": 20, "c": 6}), source="src", part="p", corpus_id="c")
    assert doc["n"] == 29 and doc["population"]["units"] == 29
    assert doc["quotas"] == {"a": 3, "b": 20, "c": 6}


def test_about_five_per_stratum(ls) -> None:
    doc = ls.select(_rows({f"s{i:02d}": 9 for i in range(10)}), source="src", part="p", corpus_id="c")
    assert set(doc["quotas"].values()) == {5} and doc["n"] == 50


def test_minimum_30_raises_k(ls) -> None:
    # 8 strata, one large: k = 5 gives 25, k = 6 gives 29, k = 7 reaches 32 (>= 30)
    sizes = {"a": 1, "b": 240, "c": 6, "d": 1, "e": 1, "f": 2, "g": 14, "h": 15}
    assert sum(ls.allocate(sizes).values()) == 32
    assert ls.allocate(sizes)["b"] == 7 and ls.allocate(sizes)["a"] == 1


def test_maximum_300_proportional_with_floor(ls) -> None:
    sizes = {f"s{i:03d}": (1 if i % 7 == 0 else 50) for i in range(100)}  # quotas 5 or 1, total 451 > 300
    quotas = ls.allocate(sizes)
    assert sum(quotas.values()) == 300
    assert all(q >= 1 for q in quotas.values())
    assert all(quotas[s] <= min(5, n) for s, n in sizes.items())
    # proportional: a stratum with quota 5 never gets fewer than one with quota 1
    assert min(q for s, q in quotas.items() if sizes[s] == 50) >= max(q for s, q in quotas.items() if sizes[s] == 1)


def test_rest_goes_in_sorted_stratum_order(ls) -> None:
    sizes = {f"s{i:03d}": 9 for i in range(70)}  # quotas 5 each = 350; floor(5*300/350) = 4 -> 280, 20 free
    quotas = ls.allocate(sizes)
    assert sum(quotas.values()) == 300
    assert [quotas[f"s{i:03d}"] for i in range(70)] == [5] * 20 + [4] * 50


def test_more_strata_than_maximum_keeps_one_each(ls) -> None:
    quotas = ls.allocate({f"s{i:03d}": 5 for i in range(320)})
    assert set(quotas.values()) == {1} and len(quotas) == 320


def test_draw_is_the_seeded_sample_of_sorted_labels(ls) -> None:
    rows = _rows({"x": 40, "y": 12})
    doc = ls.select(list(reversed(rows)), source="agentdojo", part="head", corpus_id="agentdojo-upstream")
    labels = sorted(r["label"] for r in rows if r["stratum"] == "x")
    expected = sorted(random.Random("20261011:precheck:agentdojo:head:x").sample(labels, doc["quotas"]["x"]))
    assert doc["strata"]["x"] == expected
    assert doc["labels"] == sorted(doc["strata"]["x"] + doc["strata"]["y"])
    assert doc["sha256"][doc["labels"][0]] is not None


def test_deterministic_and_independent_of_row_order(ls) -> None:
    rows = _rows({"a": 30, "b": 17, "c": 4})
    one = ls.select(rows, source="s", part="p", corpus_id="c")
    shuffled = rows[:]
    random.Random(7).shuffle(shuffled)
    two = ls.select(shuffled, source="s", part="p", corpus_id="c")
    assert one == two
    other = ls.select(rows, source="s", part="q", corpus_id="c")
    assert other["strata"] != one["strata"]  # the part is in the seed


def test_unparsed_units_stay_eligible(ls) -> None:
    rows = _rows({"a": 40}, parse="ingest.json.duplicate_key")
    doc = ls.select(rows, source="s", part="p", corpus_id="c")
    assert doc["n"] == 30 and doc["parse_not_ok_sampled"] == 30


def test_where_and_exclude_flags(ls) -> None:
    rows = _rows({"a": 10, "b": 10})
    for i, row in enumerate(rows):
        row["facets"] = {"attack_dir": "autodojo" if i % 2 else "none"}
        row["flags"] = ["local_path_model"] if i % 5 == 0 else []
    doc = ls.select(rows, source="s", part="p", corpus_id="c", where={"attack_dir": "autodojo"},
                    exclude_flags=["local_path_model"])
    assert doc["population"]["dropped_where"] == 10
    assert doc["population"]["dropped_flags"] == {"local_path_model": 2}
    assert doc["population"]["units"] == 8 and doc["n"] == 8


def test_duplicate_label_refused(ls) -> None:
    rows = _rows({"a": 2})
    rows.append(dict(rows[0], stratum="b"))
    with pytest.raises(SystemExit):
        ls.select(rows, source="s", part="p", corpus_id="c")


@pytest.mark.parametrize("label", [
    "results/runs[1]/a*b?.json", "data/x/model [enum alias]/banking/user_task_0/none/none.json", "a/b/c.json",
    "zip.zip!/logs/run[2]/x.eval", "weird]/name.json",
])
def test_escape_label_matches_only_itself(label: str) -> None:
    sys.path.insert(0, str(TOOLS))
    try:
        from l2_common import escape_label
    finally:
        sys.path.remove(str(TOOLS))
    glob = escape_label(label)
    assert fnmatch.fnmatchcase(label, glob)
    for other in (label + "x", "x" + label, label.replace("/", "_", 1), label.upper() if label.upper() != label else label + "/"):
        assert not fnmatch.fnmatchcase(other, glob)


def test_exclude_facet(ls) -> None:
    rows = _rows({"a": 6})
    for i, row in enumerate(rows):
        row["facets"] = {"h_model": "<local-path-model>" if i < 2 else "openai/gpt-4o"}
    doc = ls.select(rows, source="s", part="p", corpus_id="c", exclude_facets={"h_model": "<local-path-model>"})
    assert doc["population"]["dropped_facets"] == 2 and doc["n"] == 4
    assert doc["rule"]["exclude_facets"] == {"h_model": "<local-path-model>"}
