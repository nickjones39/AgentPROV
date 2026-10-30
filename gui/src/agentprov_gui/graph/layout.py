"""The layout service: engine choice and the digest-keyed layout cache (design §7.1 steps 4–5). No Qt.

* Engine (a), ``dot``, for a laid-out set of at most 600 nodes and 1,500 edges (fast flags above 300 nodes); if ``dot``
  is missing, fails or exceeds its time limit, engine (b) is used and the reason is reported.
* Engine (b), the layered layout (:mod:`agentprov_gui.graph.layered`), for anything larger and for full layouts.

The cache lives in ``$AGENTPROV_HOME/gui/cache/layout/<key>.json``. The key is the sha256 of the exact layout input
(the DOT text plus flags for ``dot``; the node, size and edge list for the layered engine) and an engine version, so
an entry is never stale. Cache files are the GUI's own, but they are still read with the strict loader and checked.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.loaders import strict_json_loads

from agentprov_gui.graph.dotjson import DotFailed, Layout, parse_dot_json, run_dot_json
from agentprov_gui.graph.emit import FAST_FLAGS, FAST_FLAGS_ABOVE, build_layout_dot
from agentprov_gui.graph.layered import layered_layout
from agentprov_gui.graph.viewgraph import ViewGraph

__all__ = ["DOT_MAX_EDGES", "DOT_MAX_NODES", "LayoutResult", "compute_layout", "node_size"]

DOT_MAX_NODES: Final = 600
DOT_MAX_EDGES: Final = 1500
ENGINE_VERSION: Final = "agentprov-gui-layout/2"
CHAR_W: Final = 6.0  # Helvetica 10 pt, average advance (points)
LINE_H: Final = 13.0


@dataclass(frozen=True, slots=True)
class LayoutResult:
    layout: Layout
    seconds: float
    cached: bool
    note: str | None = None  # why engine (b) was used instead of dot, when it was


def node_size(lines: tuple[str, ...]) -> tuple[float, float]:
    """Width and height (points) of a node box for the layered engine, from its label lines."""
    chars = max((len(s) for s in lines), default=1)
    return (max(40.0, chars * CHAR_W + 22.0), len(lines) * LINE_H + 12.0)


def _cache_path(cache_dir: Path | None, key: str) -> Path | None:
    return None if cache_dir is None else cache_dir / f"{key}.json"


def _num(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise ValueError
    return float(v)


def _load_cached(path: Path | None) -> Layout | None:
    if path is None:
        return None
    try:
        with open(path, "rb") as fh:
            data = fh.read(64 * 1024 * 1024 + 1)
        doc = strict_json_loads(data)
        engine = doc["engine"]
        width, height = (_num(v) for v in doc["size"])
        nodes = {str(k): (_num(a), _num(b), _num(c), _num(d)) for k, (a, b, c, d) in doc["nodes"].items()}
        edges = [(str(s), str(d), tuple((_num(p[0]), _num(p[1])) for p in pts)) for s, d, pts in doc["edges"]]
        if engine not in ("dot", "layered"):
            return None
        return Layout(engine, width, height, nodes, edges)
    except (OSError, IngestError, KeyError, TypeError, ValueError, AttributeError):
        return None  # a missing or unusable entry is recomputed


def _store(path: Path | None, layout: Layout) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".layout-", dir=path.parent)
        with os.fdopen(fd, "wb") as fh:
            fh.write(json.dumps(layout.to_json(), sort_keys=True, separators=(",", ":")).encode("ascii"))
        os.replace(tmp, path)
    except OSError:
        pass  # the cache is an optimisation only


def _layered(view: ViewGraph, cache_dir: Path | None) -> tuple[Layout, bool]:
    keys = [n.key for n in view.nodes]
    sizes = {n.key: node_size(n.lines) for n in view.nodes}
    edges = [(e.src, e.dst) for e in view.laid_out_edges]
    blob = json.dumps([ENGINE_VERSION, "layered", keys, [sizes[k] for k in keys], edges], ensure_ascii=True)
    path = _cache_path(cache_dir, hashlib.sha256(blob.encode("ascii")).hexdigest())
    cached = _load_cached(path)
    if cached is not None:
        return cached, True
    layout = layered_layout(keys, edges, sizes)
    _store(path, layout)
    return layout, False


def compute_layout(
    view: ViewGraph,
    *,
    engine: str = "auto",
    cache_dir: Path | None = None,
    dot_timeout: float = 15.0,
    dot_exe: str | None = None,
) -> LayoutResult:
    """Lay out ``view`` (``engine``: ``auto``, ``dot`` or ``layered``)."""
    import time

    started = time.perf_counter()
    n_nodes, n_edges = len(view.nodes), len(view.laid_out_edges)
    note: str | None = None
    use_dot = engine == "dot" or (engine == "auto" and n_nodes <= DOT_MAX_NODES and n_edges <= DOT_MAX_EDGES)
    if engine == "auto" and not use_dot:
        note = f"{n_nodes:,} nodes / {n_edges:,} edges: GUI layered layout"
    if use_dot:
        ids = view.model.node_ids()
        text = build_layout_dot(view, ids)
        flags = FAST_FLAGS if n_nodes > FAST_FLAGS_ABOVE else ()
        key = hashlib.sha256("\n".join([ENGINE_VERSION, "dot", *flags, text]).encode("utf-8")).hexdigest()
        path = _cache_path(cache_dir, key)
        cached = _load_cached(path)
        if cached is not None:
            return LayoutResult(cached, time.perf_counter() - started, True)
        try:
            layout = parse_dot_json(run_dot_json(text, flags=flags, timeout=dot_timeout, exe=dot_exe),
                                    {v: k for k, v in ids.items()})
            if set(layout.nodes) != {n.key for n in view.nodes}:
                raise DotFailed("'dot' output lacks a node", code="gui.dot.output")
            _store(path, layout)
            return LayoutResult(layout, time.perf_counter() - started, False)
        except DotFailed as exc:
            note = f"dot unavailable ({exc.code}): GUI layered layout"
    layout, cached_b = _layered(view, cache_dir)
    return LayoutResult(layout, time.perf_counter() - started, cached_b, note)
