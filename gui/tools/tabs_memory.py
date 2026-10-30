"""Viewer tabs memory (D-843; build log, "Viewer execution tabs"): open ``--tabs`` executions of a corpus (by default
those with the largest PROV documents; ``--pick median``: those around the median size), one Viewer tab each, and
print one JSON line with the process RSS after the corpus opened and after each tab's graph was drawn.

``--live N`` overrides how many tabs keep a live graph scene (``viewer.LIVE_SCENES``) for a comparison. Offscreen Qt;
the corpus is opened read-only and the layout cache goes to a temporary directory, never inside the corpus. Run it
through ``tools/suite_queue.py --class import``::

    python gui/tools/tabs_memory.py CORPUS [--tabs 12] [--live 4] [--pick largest|median]
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import psutil
from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication

from agentprov_gui.ui import viewer as viewer_mod

MIB = 1024 * 1024


def _wait(app: QApplication, cond: object, timeout: float = 600.0) -> None:
    end = time.monotonic() + timeout
    while not cond():  # type: ignore[operator]
        if time.monotonic() > end:
            raise SystemExit("timed out")
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)


def _pick(tree: Path, n: int, how: str) -> list[tuple[int, str]]:
    """(size, id) of ``n`` agentprov-prov/0.1 documents: the largest, or those around the median (file sizes only;
    nothing is read)."""
    sizes = sorted(((p.stat().st_size, p.name.removesuffix(".prov.json"))
                    for p in (tree / "prov" / "agentprov-prov-0.1").rglob("*.prov.json")), reverse=True)
    if how == "median":
        start = max(0, len(sizes) // 2 - n // 2)
        return sizes[start:start + n]
    return sizes[:n]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--tabs", type=int, default=viewer_mod.MAX_TABS)
    ap.add_argument("--live", type=int, default=None)
    ap.add_argument("--pick", choices=("largest", "median"), default="largest")
    args = ap.parse_args()
    if args.live is not None:
        viewer_mod.LIVE_SCENES = args.live
    proc = psutil.Process()
    app = QApplication([])
    with tempfile.TemporaryDirectory() as cache:
        v = viewer_mod.ViewerPage([args.corpus.parent], Path(cache))
        v.resize(1600, 1000)
        v.show()
        rss = {"start": proc.memory_info().rss // MIB}
        v.open_path(args.corpus)
        _wait(app, lambda: v.table is not None and v.reader is not None)
        assert v.table is not None and v.reader is not None
        rss["corpus"] = proc.memory_info().rss // MIB
        rows = {v.table.ex(i): i for i in range(len(v.table))}
        per_tab = []
        started = time.perf_counter()
        picked = _pick(v.reader.root, args.tabs, args.pick)
        for _size, ex in picked:
            pane = v.open_row(v.model.order.index(rows[ex]))
            assert pane is not None
            _wait(app, lambda p=pane: p.state != "loading" and (p.graph.scene_ is not None or p.state == "failed"))
            app.processEvents()
            nodes = len(pane.graph.scene_.nodes) if pane.graph.scene_ is not None else 0
            per_tab.append({"nodes": nodes, "rss_mib": proc.memory_info().rss // MIB,
                            "live_scenes": sum(p.graph.scene_ is not None for p in v.exec_tabs.values())})
        print(json.dumps({"live_scenes": viewer_mod.LIVE_SCENES, "pick": args.pick, "tabs": len(per_tab),
                          "prov_bytes": [size for size, _ex in picked], "rss_mib": rss,
                          "per_tab": per_tab, "peak_rss_mib": max(t["rss_mib"] for t in per_tab),
                          "seconds": round(time.perf_counter() - started, 2)}))


if __name__ == "__main__":
    main()
