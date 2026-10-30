"""The GUI's layered layout, engine (b) of design §7.1 (research §M12). Pure Python, deterministic, no Qt.

For graphs ``dot`` cannot lay out in time (all-bundle documents, anything above 600 nodes or 1,500 edges):

1. cycles are broken by reversing the back edges of a DFS that visits nodes in model order;
2. ranks are longest-path ranks, tail before head (the same direction as ``dot`` with ``rankdir=LR``, so both engines
   and ``agentprov render`` agree);
3. the order inside each rank comes from four barycentre sweeps (alternately against the previous and the next rank),
   ties broken by model order;
4. coordinates: one column per rank, as wide as its widest node; rows evenly spaced. A rank taller than
   ``max(30, 1.5·√n)`` rows wraps into several adjacent sub-columns, and nodes without any edge go to a grid after the
   last rank: without both, the unconnected assessment and inference elements of a large all-bundle document fill one
   rank 3,000 rows tall and every edge crosses the whole drawing (measured: a 19,768 × 196,460 pt layout);
5. edges are straight segments between box sides.

The result depends only on the node order, the edge list and the node sizes: no clock, hash seed or randomness.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Final

from agentprov_gui.graph.dotjson import Layout

__all__ = ["layered_layout"]

RANK_GAP: Final = 60.0
ROW_GAP: Final = 18.0
SWEEPS: Final = 4


def _acyclic(n: int, adj: list[list[int]]) -> set[tuple[int, int]]:
    """The back edges of an iterative DFS in index order (edges to reverse)."""
    state = [0] * n  # 0 new, 1 on stack, 2 done
    back: set[tuple[int, int]] = set()
    for root in range(n):
        if state[root]:
            continue
        stack: list[tuple[int, int]] = [(root, 0)]
        state[root] = 1
        while stack:
            v, i = stack[-1]
            if i < len(adj[v]):
                stack[-1] = (v, i + 1)
                w = adj[v][i]
                if state[w] == 1:
                    back.add((v, w))
                elif state[w] == 0:
                    state[w] = 1
                    stack.append((w, 0))
            else:
                state[v] = 2
                stack.pop()
    return back


def layered_layout(
    keys: Sequence[str],
    edges: Sequence[tuple[str, str]],
    sizes: Mapping[str, tuple[float, float]],
) -> Layout:
    """Lay out ``keys`` (in this order) with ``edges`` (src, dst); ``sizes`` gives each node's (w, h) in points."""
    index = {k: i for i, k in enumerate(keys)}
    n = len(keys)
    pairs = sorted({(index[s], index[d]) for s, d in edges if s in index and d in index and s != d})
    adj: list[list[int]] = [[] for _ in range(n)]
    for s, d in pairs:
        adj[s].append(d)
    back = _acyclic(n, adj)
    dag = sorted({(d, s) if (s, d) in back else (s, d) for s, d in pairs})
    succ: list[list[int]] = [[] for _ in range(n)]
    pred: list[list[int]] = [[] for _ in range(n)]
    indeg = [0] * n
    for s, d in dag:
        succ[s].append(d)
        pred[d].append(s)
        indeg[d] += 1
    # longest-path ranks over a topological order (Kahn's algorithm; the queue keeps index order)
    import heapq

    rank = [0] * n
    queue = [i for i in range(n) if indeg[i] == 0]
    heapq.heapify(queue)
    while queue:
        v = heapq.heappop(queue)
        for w in succ[v]:
            rank[w] = max(rank[w], rank[v] + 1)
            indeg[w] -= 1
            if indeg[w] == 0:
                heapq.heappush(queue, w)
    n_ranks = (max(rank) + 1) if n else 0
    layers: list[list[int]] = [[] for _ in range(n_ranks)]
    for v in range(n):
        layers[rank[v]].append(v)
    pos: list[float] = [0.0] * n
    for layer in layers:
        for i, v in enumerate(layer):
            pos[v] = float(i)

    def sweep(layer: list[int], neighbours: list[list[int]]) -> None:
        def key(v: int) -> tuple[float, int]:
            ns = neighbours[v]
            return ((sum(pos[u] for u in ns) / len(ns)) if ns else pos[v], v)

        layer.sort(key=key)
        for i, v in enumerate(layer):
            pos[v] = float(i)

    for k in range(SWEEPS):
        if k % 2 == 0:
            for layer in layers[1:]:
                sweep(layer, pred)
        else:
            for layer in reversed(layers[:-1]):
                sweep(layer, succ)

    # coordinates: wrap tall ranks, then grid the isolated nodes after the last rank
    connected = [bool(succ[v] or pred[v]) for v in range(n)]
    max_rows = max(30, int(math.sqrt(max(n, 1)) * 1.5))
    columns: list[list[int]] = []
    for layer in layers:
        members = [v for v in layer if connected[v]]
        columns.extend(members[i:i + max_rows] for i in range(0, len(members), max_rows))
    isolated = [v for v in range(n) if not connected[v]]
    columns.extend(isolated[i:i + max_rows] for i in range(0, len(isolated), max_rows))
    layers = [c for c in columns if c]
    widths = [max((sizes[keys[v]][0] for v in layer), default=0.0) for layer in layers]
    xs: list[float] = []
    x = 0.0
    for col_w in widths:
        xs.append(x + col_w / 2)
        x += col_w + RANK_GAP
    row_h = max((sizes[k][1] for k in keys), default=20.0) + ROW_GAP
    tallest = max((len(layer) for layer in layers), default=0)
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for r, layer in enumerate(layers):
        offset = (tallest - len(layer)) * row_h / 2  # centre short ranks
        for i, v in enumerate(layer):
            bw, bh = sizes[keys[v]]
            boxes[keys[v]] = (xs[r], offset + i * row_h + row_h / 2, bw, bh)
    lines: list[tuple[str, str, tuple[tuple[float, float], ...]]] = []
    for s, d in pairs:
        sk, dk = keys[s], keys[d]
        sx, sy, sw, _ = boxes[sk]
        dx, dy, dw, _ = boxes[dk]
        start = (sx + sw / 2, sy) if dx >= sx else (sx - sw / 2, sy)
        end = (dx - dw / 2, dy) if dx >= sx else (dx + dw / 2, dy)
        lines.append((sk, dk, (start, end)))
    width = max(x - RANK_GAP, 0.0)
    height = tallest * row_h
    return Layout("layered", width, height, boxes, lines)
