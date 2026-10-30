"""The experimental live PROV preview window (design §9; D-398; G4). **Off by default**: opened only by the user,
per running ``run`` job, from the job dashboard; it never starts by itself.

* The banner says "Preview: provisional graph from the capture stream. Not corpus provenance; …" and a PREVIEW
  watermark sits on the canvas. Nothing is saved or exported; there is no comparison with corpus PROV.
* The helper process (``python -I -m agentprov_gui.preview AGENTPROV_HOME``, below-normal priority) tails the capture
  logs of the sessions the job's ``session`` progress events name, reading envelope metadata only, and sends deltas
  over its stdout. A reader thread queues them; the canvas is redrawn at most once per second.
* Placement is layered in event order, appended per event (no ``dot``): the Run and its agents on top, one column per
  pass, the pass's model calls, tool executions and decisions below it. Everything is drawn "provisional": dashed and
  desaturated. Labels come from the helper's fixed vocabulary (never data) and are plain text items.
* Closing the window closes the helper's stdin; it exits, and the run is unaffected.
"""

from __future__ import annotations

import contextlib
import json
import queue
import subprocess
import sys
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Final

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

from agentprov_gui import text as T
from agentprov_gui.jobs.manager import allowlisted_env
from agentprov_gui.preview.model import BANNER
from agentprov_gui.ui.safe import SafeLabel

__all__ = ["PreviewWindow"]

REDRAW_MS: Final = 1000
_W, _H, _GAP = 150.0, 34.0, 18.0
_GREY: Final = {"run": "#8a8f98", "agent": "#9a8fa0", "pass": "#8f9a8f", "model": "#8f98a8", "tool": "#a89a8a",
                "decision": "#a88f8f", "outcome": "#9aa08a"}


class PreviewWindow(QDialog):
    def __init__(self, home: Path, sessions: Callable[[], Iterable[str]], *, title: str = "",
                 helper: list[str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Live Preview (experimental)" + (f" · {T.window_title(T.line(title, 60))}" if title else ""))
        self.setAccessibleName("Live preview")
        self.resize(900, 640)
        self.sessions_fn = sessions
        lay = QVBoxLayout(self)
        banner = SafeLabel(BANNER, name="Preview banner", parent=self)
        banner.setWordWrap(True)
        lay.addWidget(banner)
        self.status = SafeLabel("Waiting for the run's sessions…", name="Preview status", parent=self)
        lay.addWidget(self.status)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setAccessibleName("Provisional graph (preview)")
        lay.addWidget(self.view, 1)
        self.nodes: dict[str, dict[str, Any]] = {}  # id -> {kind, label, session, order, items}
        self.edges: list[tuple[str, str, str]] = []
        self.watched: set[str] = set()
        self.stopped: dict[str, str] = {}
        self._dirty = False
        self._inbox: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=100_000)
        argv = helper or ([sys.executable, "--preview-helper", str(home)] if getattr(sys, "frozen", False)
                          else [sys.executable, "-I", "-m", "agentprov_gui.preview", str(home)])  # G5 dispatches the flag
        self.proc: subprocess.Popen[bytes] | None = subprocess.Popen(  # noqa: S603 - this package's own module
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, close_fds=True,
            env=allowlisted_env())
        threading.Thread(target=self._read, name="preview-reader", daemon=True).start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(REDRAW_MS)
        self._tick()

    # ------------------------------------------------------------------------------------------ helper
    def _read(self) -> None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        for raw in proc.stdout:
            if len(raw) > 4096:
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if isinstance(msg, dict):
                with contextlib.suppress(queue.Full):
                    self._inbox.put_nowait(msg)

    def _watch(self) -> None:
        proc = self.proc
        if proc is None or proc.stdin is None:
            return
        for session in self.sessions_fn():
            if session not in self.watched:
                self.watched.add(session)
                try:
                    proc.stdin.write(json.dumps({"watch": session}).encode() + b"\n")
                    proc.stdin.flush()
                except (BrokenPipeError, OSError, ValueError):
                    return

    def _tick(self) -> None:
        self._watch()
        while True:
            try:
                msg = self._inbox.get_nowait()
            except queue.Empty:
                break
            self.apply(msg)
        if self._dirty:
            self.redraw()
        n_models = sum(1 for n in self.nodes.values() if n["kind"] == "model")
        n_tools = sum(1 for n in self.nodes.values() if n["kind"] in ("tool", "decision"))
        stopped = f"; {len(self.stopped)} log(s) stopped" if self.stopped else ""
        self.status.set_plain(f"{len(self.watched)} session(s) watched · {n_models} model call(s) · {n_tools} tool "
                              f"execution(s) or decision(s){stopped}")

    def apply(self, msg: dict[str, Any]) -> None:
        op, nid = msg.get("op"), str(msg.get("id", ""))[:200]
        kind, label = str(msg.get("kind", ""))[:20], str(msg.get("label", ""))[:80]
        session = str(msg.get("session", ""))[:64]
        if op == "node" and nid and nid not in self.nodes and kind in _GREY:
            self.nodes[nid] = {"kind": kind, "label": label, "session": session, "order": len(self.nodes)}
            self._dirty = True
        elif op == "close" and nid in self.nodes:
            if label:
                self.nodes[nid]["label"] = label
            if kind in _GREY:
                self.nodes[nid]["kind"] = kind
            self._dirty = True
        elif op == "edge":
            src, dst = str(msg.get("src", ""))[:200], str(msg.get("dst", ""))[:200]
            if src in self.nodes and dst in self.nodes:
                self.edges.append((src, dst, kind))
                self._dirty = True
        elif op == "stopped":
            self.stopped[session] = label

    # ------------------------------------------------------------------------------------------ drawing
    def placement(self) -> dict[str, tuple[float, float]]:
        """Layered placement in event order: per session a band; the Run and agents on top; each pass a column."""
        pos: dict[str, tuple[float, float]] = {}
        sessions = sorted({n["session"] for n in self.nodes.values()},
                          key=lambda s: min(n["order"] for n in self.nodes.values() if n["session"] == s))
        part_of = {src: dst for src, dst, kind in self.edges if kind == "part_of"}
        y0 = 0.0
        for s in sessions:
            mine = sorted((nid for nid, n in self.nodes.items() if n["session"] == s),
                          key=lambda nid: self.nodes[nid]["order"])
            top = [nid for nid in mine if self.nodes[nid]["kind"] in ("run", "agent", "outcome")]
            for i, nid in enumerate(top):
                pos[nid] = (i * (_W + _GAP), y0)
            passes = [nid for nid in mine if self.nodes[nid]["kind"] == "pass"]
            depth = 0
            for col, pid in enumerate(passes):
                pos[pid] = (col * (_W + _GAP), y0 + _H + _GAP)
                children = [nid for nid in mine if part_of.get(nid) == pid]
                for row, nid in enumerate(children):
                    pos[nid] = (col * (_W + _GAP), y0 + (row + 2) * (_H + _GAP))
                depth = max(depth, len(children))
            loose = [nid for nid in mine if nid not in pos]
            for i, nid in enumerate(loose):
                pos[nid] = (len(passes) * (_W + _GAP), y0 + (i + 1) * (_H + _GAP))
            y0 += (depth + 3) * (_H + _GAP) + _GAP
        return pos

    def redraw(self) -> None:
        self._dirty = False
        self.scene.clear()
        pos = self.placement()
        pen_edge = QPen(QColor("#9aa0a6"))
        pen_edge.setStyle(Qt.PenStyle.DashLine)
        for src, dst, _kind in self.edges:
            if src in pos and dst in pos:
                (x1, y1), (x2, y2) = pos[src], pos[dst]
                line = QGraphicsLineItem(x1 + _W / 2, y1 + _H / 2, x2 + _W / 2, y2 + _H / 2)
                line.setPen(pen_edge)
                self.scene.addItem(line)
        for nid, (x, y) in pos.items():
            node = self.nodes[nid]
            rect = QGraphicsRectItem(x, y, _W, _H)
            pen = QPen(QColor(_GREY[node["kind"]]))
            pen.setStyle(Qt.PenStyle.DashLine)
            rect.setPen(pen)
            rect.setBrush(QBrush(QColor(_GREY[node["kind"]]).lighter(170)))
            self.scene.addItem(rect)
            label = QGraphicsSimpleTextItem(T.line(node["label"] or node["kind"], 40))
            label.setPos(x + 6, y + 9)
            self.scene.addItem(label)
        mark = QGraphicsSimpleTextItem("PREVIEW")
        font = QFont()
        font.setPointSize(36)
        font.setBold(True)
        mark.setFont(font)
        mark.setBrush(QBrush(QColor(128, 128, 128, 60)))
        mark.setPos(0, -70)
        self.scene.addItem(mark)

    def closeEvent(self, event: Any) -> None:
        self.timer.stop()
        proc, self.proc = self.proc, None
        if proc is not None:
            try:
                if proc.stdin is not None:
                    proc.stdin.close()  # EOF: the helper exits; the run is unaffected
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
        super().closeEvent(event)
