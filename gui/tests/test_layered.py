"""Engine (b), the layered layout: deterministic, cycle-safe, tail before head, tall ranks wrapped."""

from __future__ import annotations

from agentprov_gui.graph.layered import layered_layout


def _sizes(keys: list[str]) -> dict[str, tuple[float, float]]:
    return {k: (60.0, 30.0) for k in keys}


def test_deterministic_and_directed() -> None:
    keys = [f"n{i}" for i in range(30)]
    edges = [(f"n{i}", f"n{i + 1}") for i in range(29)] + [("n0", "n5"), ("n3", "n20")]
    a = layered_layout(keys, edges, _sizes(keys))
    b = layered_layout(keys, edges, _sizes(keys))
    assert a == b
    for s, d in edges:
        assert a.nodes[s][0] < a.nodes[d][0]  # tail left of head, as dot with rankdir=LR


def test_cycles_do_not_hang_and_every_node_is_placed() -> None:
    keys = ["a", "b", "c", "d"]
    edges = [("a", "b"), ("b", "c"), ("c", "a"), ("c", "d"), ("d", "d")]
    lay = layered_layout(keys, edges, _sizes(keys))
    assert set(lay.nodes) == set(keys)
    assert len(lay.edges) == 4  # the self-loop is dropped


def test_tall_ranks_wrap_and_isolated_nodes_grid() -> None:
    keys = ["root", *(f"leaf{i}" for i in range(500)), *(f"iso{i}" for i in range(500))]
    edges = [("root", f"leaf{i}") for i in range(500)]
    lay = layered_layout(keys, edges, _sizes(keys))
    assert lay.height < 60 * 40 * 2  # bounded height, not 500 rows
    assert set(lay.nodes) == set(keys)
