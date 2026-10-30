"""DOT text and the ``dot`` process (MN N.2.13; G.8.6; K.5.12; baseline ``visualize.py:187-231``).

* :func:`build_dot` builds the DOT text of a :class:`~agentprov.render.graph.GraphModel` with ``pydot`` and returns
  ``Dot.to_string()``. ``pydot`` builds text only: its ``create`` and ``write_*`` methods spawn Graphviz themselves and
  are never called (a static test checks this), so this module controls the one subprocess. The text is deterministic:
  nodes, edges and clusters are added in the model's sorted order, ids are derived from the node keys, and nothing
  depends on a clock, a path or hash randomisation.
* :func:`run_dot` runs ``dot -T<fmt>`` with the DOT text on stdin and nothing from the document in argv. ``dot`` is
  resolved once with ``shutil.which``; the environment is ``PATH``, ``LANG`` and ``TZ`` only; the working directory is an
  empty temporary directory; the child has its own session so a timeout can kill the whole group; the wall time is
  120 s; stdout is capped at 64 MiB and stderr is kept to its last 64 KiB and never parsed.

``pydot`` is imported inside functions only, so ``import agentprov.render`` works without the ``render`` extra; a missing
``pydot`` or ``dot`` is a :class:`~agentprov.render.errors.RenderEnvironmentError` (exit 3) with an install hint.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import tempfile
import threading
from typing import TYPE_CHECKING, Any, Final

from agentprov.ingest.quote import escape_untrusted
from agentprov.render import style
from agentprov.render.errors import EXTRA_HINT, RenderEnvironmentError, RenderProcessError

if TYPE_CHECKING:
    from types import ModuleType

    from agentprov.render.graph import DrawNode, GraphModel

__all__ = [
    "DOT_TIMEOUT_S",
    "MAX_LAYOUT_EDGES",
    "MAX_OUTPUT_BYTES",
    "RUN_FORMATS",
    "STDERR_KEEP_BYTES",
    "build_dot",
    "find_dot",
    "graphviz_version",
    "require_pydot",
    "run_dot",
]

DOT_TIMEOUT_S: Final = 120.0
#: The image layout limit (edges drawn, edge labels included). Graphviz ``dot`` time grows sharply with the edges of an
#: ``--bundle all`` graph: 715 edges took 29 s, 983 edges 114 s and 1,714 edges more than 320 s of CPU with labels
#: (docs/reports/gui/research.md §M7b), against the 120 s timeout. Above it ``dot`` is not started (``--max-edges``).
MAX_LAYOUT_EDGES: Final = 800
MAX_OUTPUT_BYTES: Final = 64 * 1024 * 1024
#: The ``-T`` formats :func:`run_dot` accepts: the image formats of ``render`` and ``json`` (the layout, D-397).
RUN_FORMATS: Final = ("svg", "png", "pdf", "json")
STDERR_KEEP_BYTES: Final = 64 * 1024
_ENV_KEYS: Final = ("PATH", "LANG", "TZ")
_DIRECTIONS: Final = ("LR", "TB")
_INSTALL_DOT: Final = "install Graphviz (macOS: brew install graphviz; Debian and Ubuntu: apt install graphviz)"


# ----------------------------------------------------------------------------------------------- DOT text
def require_pydot() -> ModuleType:
    """The ``pydot`` module, or a :class:`RenderEnvironmentError` (exit 3) naming the extra."""
    try:
        import pydot
    except ImportError:
        raise RenderEnvironmentError(
            f"the render extra (pydot) is not installed; run: {EXTRA_HINT}", code="render.extra_missing"
        ) from None
    return pydot


def build_dot(
    model: GraphModel,
    *,
    direction: str = "LR",
    show_content: bool = False,
    content_chars: int = style.DEFAULT_CONTENT_CHARS,
) -> str:
    """The DOT text of ``model`` (a pure function of the model and the options; see the module docstring)."""
    if direction not in _DIRECTIONS:
        raise ValueError("direction is LR or TB")
    pydot = require_pydot()
    graph = pydot.Dot(
        "prov",
        graph_type="digraph",
        rankdir=direction,
        label=style.dot_quote(model.title),
        labelloc="t",
        fontname="Helvetica",
        fontsize="11",
    )
    ids = model.node_ids()
    clustered = len(model.bundles) > 1
    clusters: dict[int, Any] = {}
    titles = {b.index: b for b in model.bundles}
    for node in model.nodes:
        gnode = pydot.Node(ids[node.key], label=style.dot_quote(_label(node, show_content, content_chars)), **_node_attrs(node))
        if clustered and node.bundle is not None:
            if node.bundle not in clusters:  # a cluster exists only if the bundle declares a drawn node
                bundle = titles[node.bundle]
                clusters[node.bundle] = pydot.Cluster(
                    f"{bundle.index}",  # pydot prefixes the name with "cluster_"
                    label=style.dot_quote(bundle.title),
                    style="rounded",
                    color=style.BUNDLE_COLOUR.get(bundle.kind, "#808080"),
                    fontname="Helvetica",
                    fontsize="10",
                )
            clusters[node.bundle].add_node(gnode)
        else:
            graph.add_node(gnode)
    for index in sorted(clusters):
        graph.add_subgraph(clusters[index])
    for edge in model.edges:
        if edge.link:
            attrs = dict(style.ANNOTATION_LINK_STYLE)
        else:
            attrs = style.edge_attrs(edge.relation, edge.cls, edge.kind)
        graph.add_edge(pydot.Edge(ids[edge.src], ids[edge.dst], label=style.dot_quote(edge.relation), **attrs))
    return str(graph.to_string())


def _node_attrs(node: DrawNode) -> dict[str, str]:
    return style.node_attrs(node.section, node.cls, node.kind, integrity=node.integrity, role=node.role)


def _label(node: DrawNode, show_content: bool, content_chars: int) -> str:
    tags: list[str] = []
    if node.integrity is not None:
        tags.append(f"integrity: {node.integrity}")
    if node.role is not None:
        tags.append(f"role: {node.role}")
    if node.bundle is None:
        tags.append("(declared outside the drawn bundles)")
    return style.node_label(
        node.key, node.section, node.attrs, cls=node.cls, tags=tuple(tags), show_content=show_content, content_chars=content_chars
    )


# ----------------------------------------------------------------------------------------------- the process
def find_dot() -> str:
    """The absolute path of the Graphviz ``dot`` binary, or a :class:`RenderEnvironmentError` (exit 3)."""
    found = shutil.which("dot")
    if found is None:
        raise RenderEnvironmentError(f"the Graphviz 'dot' binary is not on PATH; {_INSTALL_DOT}", code="render.dot_missing")
    return found


def _environment() -> dict[str, str]:
    return {key: os.environ[key] for key in _ENV_KEYS if key in os.environ}


def _spawn_kwargs() -> dict[str, Any]:
    return {"start_new_session": True} if os.name == "posix" else {}


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    if os.name == "posix":
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        proc.kill()


def run_dot(exe: str, dot_text: str, fmt: str, *, timeout: float = DOT_TIMEOUT_S, max_output: int = MAX_OUTPUT_BYTES) -> bytes:
    """Run ``<exe> -T<fmt>`` over ``dot_text`` and return the output bytes (the caller writes them atomically).

    ``json`` (D-397) is Graphviz's laid-out graph as JSON, for a GUI that draws the layout itself; it is produced
    under the same process controls and is untrusted output like any other format (parse it with the strict loader)."""
    if fmt not in RUN_FORMATS:
        raise ValueError("fmt is svg, png, pdf or json")
    out = bytearray()
    err = bytearray()
    overflow = threading.Event()

    with tempfile.TemporaryDirectory(prefix="agentprov-render-") as cwd:
        proc = subprocess.Popen(  # noqa: S603 - fixed argv, absolute executable, data on stdin only (G.8.6)
            [exe, f"-T{fmt}"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=_environment(),
            **_spawn_kwargs(),
        )
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None

        def feed() -> None:
            with contextlib.suppress(BrokenPipeError, OSError):
                proc.stdin.write(dot_text.encode("utf-8"))  # type: ignore[union-attr]
            with contextlib.suppress(BrokenPipeError, OSError):
                proc.stdin.close()  # type: ignore[union-attr]

        def drain_out() -> None:
            while chunk := proc.stdout.read(65536):  # type: ignore[union-attr]
                if len(out) + len(chunk) > max_output:
                    overflow.set()
                    _kill_group(proc)
                    return
                out.extend(chunk)

        def drain_err() -> None:
            while chunk := proc.stderr.read(65536):  # type: ignore[union-attr]
                err.extend(chunk)
                if len(err) > STDERR_KEEP_BYTES:
                    del err[: len(err) - STDERR_KEEP_BYTES]

        threads = [threading.Thread(target=f, daemon=True) for f in (feed, drain_out, drain_err)]
        for thread in threads:
            thread.start()
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(proc)
            proc.wait()
        finally:
            for thread in threads:
                thread.join(timeout=10)
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                with contextlib.suppress(OSError, ValueError):
                    pipe.close()
    if timed_out:
        raise RenderProcessError(
            f"graphviz 'dot' did not finish within {timeout:.0f} s (the .dot text was written; a large graph lays out "
            "faster as --bundle core, or lay the .dot out offline)", code="render.dot_timeout",
        )
    if overflow.is_set():
        raise RenderProcessError(f"graphviz 'dot' produced more than {max_output} bytes", code="render.dot_output_cap")
    if proc.returncode != 0:
        raise RenderProcessError(
            f"graphviz 'dot' exited with status {proc.returncode} ({len(err)} bytes of stderr kept)", code="render.dot_failed"
        )
    return bytes(out)


def graphviz_version(exe: str) -> str | None:
    """The version token of ``dot -V`` (for the run summary), or ``None`` if it cannot be read."""
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, absolute executable
            [exe, "-V"], capture_output=True, timeout=20, check=False, env=_environment(), stdin=subprocess.DEVNULL
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = escape_untrusted((done.stderr or done.stdout).decode("utf-8", "replace"), max_chars=200)
    marker = "version "
    if marker not in text:
        return None
    return text.split(marker, 1)[1].split()[0] if text.split(marker, 1)[1].split() else None
