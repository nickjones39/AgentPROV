"""SEC-11: pydot never spawns Graphviz; ``dot`` is the one process ``render`` starts (G.10 SEC-11; K.12.6 static test;
K.5.12; G.8.6; T-10, T-11).

pydot builds DOT text, but its ``create``/``write`` methods and the 73 generated ``create_<fmt>``/``write_<fmt>`` methods
(pydot 4.0.1) start a Graphviz program themselves (``pydot.core.call_graphviz``: a temporary file, a program name looked
up on ``$PATH``). AgentPROV must call none of them, so that ``agentprov.render.dot.run_dot`` controls the only process
(absolute ``dot``, fixed argv, data on stdin, minimal environment).

* **Static.** An AST scan of ``src/agentprov``, ``capture/src`` and ``backends/shared/src``: pydot is imported only by
  ``render/dot.py`` and only inside functions; no other Graphviz binding (``graphviz``, ``pygraphviz``,
  ``networkx`` drawing, ``prov.dot``) is imported; no attribute, ``getattr`` string or alias of a pydot object names a
  spawning method; a generated ``create_<fmt>``/``write_<fmt>`` name is used nowhere. The scanner has a positive control
  (each forbidden pattern in a snippet is reported).
* **Dynamic** (``render`` extra; skipped without pydot, like ``tests/render``): with pydot's spawning entry points patched
  to fail and ``subprocess.Popen`` recorded, ``agentprov render --format dot`` starts no process at all, and
  ``--format svg`` (with Graphviz installed) starts exactly one: the absolute ``dot`` with ``-Tsvg``, no shell.

The phase-11 test ``tests/render/test_render.py::test_pydot_is_imported_only_inside_functions_and_never_asked_to_spawn_graphviz``
checks the render modules for calls on variables named ``graph``, ``pydot`` or ``g``; this file is the ban itself.
"""

from __future__ import annotations

import ast
import functools
import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

import corpus_harness as harness
import pytest

cli = harness.cli  # the corpus_harness fixture, bound in this module so pytest finds it

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ("src/agentprov", "capture/src", "backends/shared/src", "backends/inspect/src")
#: The output formats pydot 4.0.1 generates ``create_<fmt>`` and ``write_<fmt>`` methods for (``Dot.formats``).
PYDOT_FORMATS = (
    "canon", "cmap", "cmapx", "cmapx_np", "dia", "dot", "fig", "gd", "gd2", "gif", "hpgl", "imap", "imap_np", "ismap",
    "jpe", "jpeg", "jpg", "mif", "mp", "pcl", "pdf", "pic", "plain", "plain-ext", "png", "ps", "ps2", "svg", "svgz",
    "vml", "vmlz", "vrml", "vtx", "wbmp", "xdot", "xlib",
)  # fmt: skip
GENERATED = frozenset({f"create_{f}" for f in PYDOT_FORMATS} | {f"write_{f}" for f in PYDOT_FORMATS} | {"write_raw"})
SPAWNING = GENERATED | {"create", "write"}
#: Other Graphviz bindings, each of which starts Graphviz or links it in-process.
OTHER_BINDINGS = ("graphviz", "pygraphviz", "networkx.drawing.nx_pydot", "networkx.drawing.nx_agraph", "prov.dot")
#: The one module allowed to import pydot (inside functions).
PYDOT_HOME = "src/agentprov/render/dot.py"
HAVE_PYDOT = importlib.util.find_spec("pydot") is not None
needs_pydot = pytest.mark.skipif(not HAVE_PYDOT, reason="the render extra (pydot) is not installed")


# ------------------------------------------------------------------------------------------------ the scanner
def _imports(nodes: list[ast.AST]) -> list[tuple[ast.AST, str, str | None]]:
    """``(node, module, asname)`` for every import among ``nodes``; ``from a import b`` gives ``a.b``."""
    out: list[tuple[ast.AST, str, str | None]] = []
    for node in nodes:
        if isinstance(node, ast.Import):
            out += [(node, alias.name, alias.asname) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            out += [(node, f"{node.module}.{alias.name}", alias.asname) for alias in node.names]
            out.append((node, node.module, None))
    return out


def _module_aliases(nodes: list[ast.AST], imports: list[tuple[ast.AST, str, str | None]]) -> set[str]:
    """Names bound to the pydot module: ``import pydot [as x]``, ``from pydot import ...`` targets, and names assigned
    from a call of a function that returns it (``pydot = require_pydot()``)."""
    names = {"pydot"}
    for _node, module, asname in imports:
        if module == "pydot" or module.startswith("pydot."):
            names.add(asname or module.split(".")[-1] if module != "pydot" else asname or "pydot")
    for node in nodes:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if name == "require_pydot":
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _rooted_in(node: ast.AST, names: set[str]) -> bool:
    while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
        node = node.value if not isinstance(node, ast.Call) else node.func
    return isinstance(node, ast.Name) and node.id in names


def scan(source: str, label: str) -> list[str]:
    """Every pydot-spawning use in ``source`` (see the module docstring); the result names line and pattern only."""
    tree = ast.parse(source, filename=label)
    nodes = list(ast.walk(tree))
    imports = _imports(nodes)
    problems: list[str] = []
    for node, module, _asname in imports:
        if any(module == b or module.startswith(b + ".") for b in OTHER_BINDINGS):
            problems.append(f"{label}:{node.lineno} imports {module}")  # type: ignore[attr-defined]
        if (module == "pydot" or module.startswith("pydot.")) and label != PYDOT_HOME:
            problems.append(f"{label}:{node.lineno} imports pydot outside {PYDOT_HOME}")  # type: ignore[attr-defined]
    if isinstance(tree, ast.Module):
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
                    m == "pydot" or m.startswith("pydot.") for _n, m, _a in _imports([node])):
                problems.append(f"{label}:{node.lineno} imports pydot at module level")
    modules = _module_aliases(nodes, imports)
    assignments = [n for n in nodes if isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr))]
    # objects made by pydot (``pydot.Dot(...)``, ``pydot.graph_from_dot_data(...)``) and names copied from them
    objects: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in assignments:
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
                targets, value = [node.target], node.value
            if value is None or not _rooted_in(value, modules | objects):
                continue
            for target in targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name) and name.id not in objects and name.id not in modules:
                        objects.add(name.id)
                        changed = True
    tracked = modules | objects
    for node in nodes:
        if isinstance(node, ast.Attribute):
            if node.attr in GENERATED:
                problems.append(f"{label}:{node.lineno} names the pydot method {node.attr}")
            elif node.attr in SPAWNING and _rooted_in(node.value, tracked):
                problems.append(f"{label}:{node.lineno} calls pydot {node.attr}")
            elif node.attr == "call_graphviz":
                problems.append(f"{label}:{node.lineno} names pydot's call_graphviz")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "setattr"):
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                attr = node.args[1].value
                if attr in GENERATED or attr == "call_graphviz" or (attr in SPAWNING and _rooted_in(node.args[0], tracked)):
                    problems.append(f"{label}:{node.lineno} reaches pydot {attr} through getattr")
            elif len(node.args) >= 2 and _rooted_in(node.args[0], tracked):
                problems.append(f"{label}:{node.lineno} reaches a pydot attribute by a computed name")
        elif isinstance(node, ast.Name) and node.id == "call_graphviz":
            problems.append(f"{label}:{node.lineno} names pydot's call_graphviz")
    return sorted(set(problems))


def _sources() -> list[Path]:
    return sorted(p for root in SCANNED for p in (ROOT / root).rglob("*.py"))


@functools.cache
def _scan_codebase() -> tuple[int, tuple[str, ...]]:
    """``(files scanned, problems)`` over :data:`SCANNED`, computed once per session."""
    sources = _sources()
    problems = [p for path in sources for p in scan(path.read_text("utf-8"), path.relative_to(ROOT).as_posix())]
    return len(sources), tuple(problems)


# ------------------------------------------------------------------------------------------------ static tests
def test_sec11_no_module_imports_pydot_or_another_graphviz_binding_where_it_may_not():
    count, problems = _scan_codebase()
    assert count > 100 and (ROOT / PYDOT_HOME).is_file()
    assert [p for p in problems if "imports" in p] == []


def test_sec11_no_module_reaches_a_pydot_method_that_spawns_graphviz():
    assert [p for p in _scan_codebase()[1] if "imports" not in p] == []


def test_sec11_the_pydot_home_builds_text_only():
    """``render/dot.py`` turns the graph into text with ``to_string`` and passes it to ``run_dot``."""
    source = (ROOT / PYDOT_HOME).read_text("utf-8")
    assert "to_string()" in source and "require_pydot()" in source
    assert scan(source, PYDOT_HOME) == []


SNIPPETS = [
    pytest.param("def f():\n    import pydot\n    g = pydot.Dot()\n    g.write_svg('x')\n", "write_svg", id="generated"),
    pytest.param("def f():\n    import pydot\n    g = pydot.Dot()\n    g.create(format='svg')\n", "create", id="create"),
    pytest.param("def f():\n    import pydot\n    g = pydot.Dot()\n    h = g\n    h.write('x')\n", "write", id="alias"),
    pytest.param("def f():\n    import pydot as p\n    p.Dot().create()\n", "create", id="module-alias"),
    pytest.param("def f():\n    pydot = require_pydot()\n    d = pydot.Dot()\n    d.write('x')\n", "write", id="require"),
    pytest.param("def f(g):\n    getattr(g, 'create_png')()\n", "create_png", id="getattr"),
    pytest.param("def f():\n    import pydot\n    g = pydot.Dot()\n    getattr(g, name)()\n", "computed", id="computed"),
    pytest.param("def f():\n    from pydot.core import call_graphviz\n    call_graphviz('dot', [], '/t')\n", "call_graphviz",
                 id="call-graphviz"),
    pytest.param("import pydot\n", "module level", id="module-level"),
    pytest.param("def f():\n    import graphviz\n", "graphviz", id="graphviz"),
    pytest.param("def f():\n    from prov.dot import prov_to_dot\n", "prov.dot", id="prov-dot"),
]


@pytest.mark.parametrize(("source", "expected"), SNIPPETS)
def test_sec11_the_scanner_reports_each_forbidden_pattern(source, expected):
    """Positive control: a scan that reports nothing must not be a scan that sees nothing."""
    problems = scan(source, PYDOT_HOME if "graphviz" not in expected and "prov" not in expected else "x.py")
    assert any(expected in p for p in problems), problems


def test_sec11_the_scanner_leaves_ordinary_write_and_create_calls_alone():
    source = "def f(stream, proc):\n    stream.write(b'x')\n    proc.stdin.write(b'y')\n    obj.create()\n"
    assert scan(source, "src/agentprov/x.py") == []


# ------------------------------------------------------------------------------------------------ dynamic tests
@pytest.fixture
def render_corpus(tmp_path: Path) -> dict[str, Any]:
    import render_support as rs

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    return rs.build_corpus(tmp_path / "corpus", scratch, executions=2)


@pytest.fixture
def spawn_spy(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """pydot's spawning entry points fail; every ``subprocess.Popen`` is recorded (then run for real)."""
    import subprocess

    import pydot
    import pydot.core

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("pydot was asked to start Graphviz")

    for owner in (pydot.core.Dot, pydot.Dot):
        monkeypatch.setattr(owner, "create", forbidden)
        monkeypatch.setattr(owner, "write", forbidden)
    monkeypatch.setattr(pydot.core, "call_graphviz", forbidden)
    if hasattr(pydot, "call_graphviz"):
        monkeypatch.setattr(pydot, "call_graphviz", forbidden)
    calls: list[list[str]] = []
    real = subprocess.Popen

    class Spy(real):  # type: ignore[misc, valid-type]
        def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
            assert not kwargs.get("shell"), "a shell was requested"
            calls.append([os.fsdecode(a) for a in args] if isinstance(args, (list, tuple)) else [os.fsdecode(args)])
            super().__init__(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", Spy)
    return calls


@needs_pydot
@pytest.mark.render
@pytest.mark.parametrize("show_content", [False, True])
def test_sec11_render_to_dot_starts_no_process_and_never_reaches_pydot_spawning(cli, render_corpus, spawn_spy, tmp_path,
                                                                             show_content):
    out = tmp_path / "out"
    flags = ["--show-content"] if show_content else []
    run = cli("render", "--corpus", str(render_corpus["root"]), "--format", "dot", "--out", str(out), "--jobs", "1",
              "--ex", *render_corpus["exs"], *flags)
    assert run.code == 0, run.err
    assert spawn_spy == []
    assert len(list(out.rglob("*.dot"))) == len(render_corpus["exs"])


@needs_pydot
@pytest.mark.render
@pytest.mark.skipif(shutil.which("dot") is None, reason="the Graphviz dot binary is not installed")
def test_sec11_render_to_svg_starts_only_the_absolute_dot_with_a_fixed_argv(cli, render_corpus, spawn_spy, tmp_path):
    out = tmp_path / "out"
    run = cli("render", "--corpus", str(render_corpus["root"]), "--format", "svg", "--out", str(out), "--jobs", "1",
              "--ex", *render_corpus["exs"])
    assert run.code == 0, run.err
    rendered = [c for c in spawn_spy if c[1:] == ["-Tsvg"]]
    assert len(rendered) == len(render_corpus["exs"]) and all(os.path.isabs(c[0]) and Path(c[0]).name == "dot"
                                                               for c in rendered)
    assert all(c[1:] in (["-Tsvg"], ["-V"]) and Path(c[0]).name == "dot" for c in spawn_spy), spawn_spy
    assert len(list(out.rglob("*.svg"))) == len(render_corpus["exs"])
