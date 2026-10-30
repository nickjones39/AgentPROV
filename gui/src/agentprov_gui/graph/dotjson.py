"""``dot -Tjson`` under the G.8.6 process controls, and its output parsed strictly (design §7.1 step 4; S5). No Qt.

**Interim copy of the controls.** ``render.dot.run_dot`` accepts only ``svg``, ``png`` and ``pdf``; D-397 adds
``json`` (owned by the CLI robustness session). Until it lands, this module applies the same controls itself, and
``tests/test_graph_layout.py`` checks them: a fixed argv (the absolute ``dot`` from ``render.dot.find_dot``, ``-Tjson``
and fixed ``-G`` flags), the DOT text on stdin and nothing from the document in argv, an environment of ``PATH``,
``LANG`` and ``TZ`` only, an empty temporary working directory, a new session (the whole group is killed on timeout), a
wall-time limit, stdout capped at 64 MiB (written to a file in the temporary directory, so no pipe can fill), stderr
kept to its last 64 KiB and never parsed.

**Parsing.** The JSON goes through the core's strict loader under limits. Only geometry is read: ``bb``, each object's
``name``, ``pos``, ``width``, ``height``, and each edge's ``tail``, ``head`` and spline ``pos``. Every ``_draw_`` and
``_ldraw_`` operation (which can carry text) is ignored: labels are drawn from the model (S5).
"""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.render.dot import MAX_OUTPUT_BYTES, STDERR_KEEP_BYTES, find_dot

__all__ = ["DotFailed", "Layout", "dot_environment", "parse_dot_json", "run_dot_json"]

_ENV_KEYS: Final = ("PATH", "LANG", "TZ")
_NUM: Final = r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_POINT: Final = re.compile(rf"({_NUM}),({_NUM})")
_BB: Final = re.compile(rf"({_NUM}),({_NUM}),({_NUM}),({_NUM})")
_LIMITS: Final = IngestLimits().replace(max_json_bytes=MAX_OUTPUT_BYTES)
POINTS_PER_INCH: Final = 72.0


class DotFailed(AgentProvError):
    """``dot`` did not produce a usable layout (missing, timeout, output cap, exit status, malformed output)."""

    code = "gui.dot.failed"


@dataclass(frozen=True, slots=True)
class Layout:
    """Node boxes and edge polylines in scene coordinates (y down), plus the bounding size."""

    engine: str  # dot | layered
    width: float
    height: float
    nodes: Mapping[str, tuple[float, float, float, float]]  # key -> (cx, cy, w, h)
    edges: Sequence[tuple[str, str, tuple[tuple[float, float], ...]]]  # (src key, dst key, control points)

    def to_json(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "size": [self.width, self.height],
            "nodes": {k: list(v) for k, v in sorted(self.nodes.items())},
            "edges": [[s, d, [list(p) for p in pts]] for s, d, pts in self.edges],
        }


def dot_environment() -> dict[str, str]:
    return {key: os.environ[key] for key in _ENV_KEYS if key in os.environ}


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    if os.name == "posix":
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        proc.kill()


def run_dot_json(dot_text: str, *, flags: Sequence[str] = (), timeout: float = 15.0, exe: str | None = None) -> bytes:
    """Run ``dot -Tjson`` over ``dot_text`` (see the module docstring); the JSON bytes, or :class:`DotFailed`."""
    for flag in flags:
        if not re.fullmatch(r"-G[a-z0-9]+=[A-Za-z0-9.]+", flag):
            raise ValueError("layout flags are fixed -G settings")
    try:
        program = exe or find_dot()
    except AgentProvError as exc:
        raise DotFailed("Graph layout needs Graphviz 'dot'", code="gui.dot.missing") from exc
    with tempfile.TemporaryDirectory(prefix="agentprov-gui-dot-") as cwd:
        out_path = os.path.join(cwd, "out.json")
        err_path = os.path.join(cwd, "err.txt")
        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            proc = subprocess.Popen(  # noqa: S603 - fixed argv, absolute executable, data on stdin only (G.8.6)
                [program, "-Tjson", *flags],
                stdin=subprocess.PIPE,
                stdout=out,
                stderr=err,
                cwd=cwd,
                env=dot_environment(),
                close_fds=True,
                start_new_session=os.name == "posix",
            )
            try:
                proc.communicate(dot_text.encode("utf-8"), timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_group(proc)
                proc.wait()
                raise DotFailed(f"'dot' did not finish within {timeout:.0f} s", code="gui.dot.timeout") from None
            except BaseException:
                _kill_group(proc)
                proc.wait()
                raise
        size = os.path.getsize(out_path)
        if size > MAX_OUTPUT_BYTES:
            raise DotFailed("'dot' output exceeds the cap", code="gui.dot.output_cap")
        if proc.returncode != 0:
            kept = min(os.path.getsize(err_path), STDERR_KEEP_BYTES)
            raise DotFailed(f"'dot' exited with status {proc.returncode} ({kept} bytes of stderr kept)",
                            code="gui.dot.status")
        with open(out_path, "rb") as fh:
            return fh.read(MAX_OUTPUT_BYTES)


def _point(text: object) -> tuple[float, float]:
    if not isinstance(text, str):
        raise DotFailed("a position is not a string", code="gui.dot.output")
    m = _POINT.fullmatch(text.strip())
    if m is None:
        raise DotFailed("a position is not 'x,y'", code="gui.dot.output")
    return float(m.group(1)), float(m.group(2))


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise DotFailed("a size is not a number", code="gui.dot.output")
    try:
        return float(value)
    except ValueError:
        raise DotFailed("a size is not a number", code="gui.dot.output") from None


def _spline(text: object) -> list[tuple[float, float]]:
    """The control points of a ``pos`` spline (``e,x,y`` / ``s,x,y`` end markers first, then the B-spline points)."""
    if not isinstance(text, str):
        raise DotFailed("an edge position is not a string", code="gui.dot.output")
    start: tuple[float, float] | None = None
    end: tuple[float, float] | None = None
    points: list[tuple[float, float]] = []
    for token in text.split(";")[0].split():
        if token.startswith("e,"):
            end = _point(token[2:])
        elif token.startswith("s,"):
            start = _point(token[2:])
        else:
            points.append(_point(token))
    if start is not None:
        points.insert(0, start)
    if end is not None:
        points.append(end)
    return points


def parse_dot_json(data: bytes, names: Mapping[str, str]) -> Layout:
    """Geometry of ``dot -Tjson`` output. ``names`` maps the DOT node id to the node key; unknown ids are refused."""
    try:
        doc = strict_json_loads(data, _LIMITS)
    except IngestError as exc:
        raise DotFailed(f"'dot' output is not strict JSON ({exc.code})", code="gui.dot.output") from None
    if not isinstance(doc, dict):
        raise DotFailed("'dot' output is not an object", code="gui.dot.output")
    bb = doc.get("bb")
    m = _BB.fullmatch(bb.strip()) if isinstance(bb, str) else None
    if m is None:
        raise DotFailed("'dot' output has no bounding box", code="gui.dot.output")
    x0, y0, x1, y1 = (float(g) for g in m.groups())
    top = y1

    def flip(p: tuple[float, float]) -> tuple[float, float]:
        return (p[0] - x0, top - p[1])

    nodes: dict[str, tuple[float, float, float, float]] = {}
    gvid: dict[int, str] = {}
    objects = doc.get("objects", [])
    if not isinstance(objects, list):
        raise DotFailed("'dot' objects is not a list", code="gui.dot.output")
    for obj in objects:
        if not isinstance(obj, dict) or "nodes" in obj or "subgraphs" in obj:
            continue  # a cluster or subgraph object, never a node
        name = obj.get("name")
        if not isinstance(name, str) or name not in names:
            raise DotFailed("'dot' output names a node the GUI did not send", code="gui.dot.output")
        cx, cy = flip(_point(obj.get("pos")))
        w = _number(obj.get("width")) * POINTS_PER_INCH
        h = _number(obj.get("height")) * POINTS_PER_INCH
        nodes[names[name]] = (cx, cy, w, h)
        vid = obj.get("_gvid")
        if isinstance(vid, int) and not isinstance(vid, bool):
            gvid[vid] = names[name]
    edges: list[tuple[str, str, tuple[tuple[float, float], ...]]] = []
    raw_edges = doc.get("edges", [])
    if not isinstance(raw_edges, list):
        raise DotFailed("'dot' edges is not a list", code="gui.dot.output")
    for edge in raw_edges:
        if not isinstance(edge, dict):
            continue
        tail, head = edge.get("tail"), edge.get("head")
        if tail not in gvid or head not in gvid:
            raise DotFailed("'dot' output has an edge between unknown nodes", code="gui.dot.output")
        pts = tuple(flip(p) for p in _spline(edge.get("pos")))
        edges.append((gvid[tail], gvid[head], pts))
    return Layout("dot", x1 - x0, y1 - y0, nodes, edges)
