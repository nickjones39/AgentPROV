"""``agentprov.render`` (docs/architecture K.5.12; G.8.6; SEC-12): the graph model, the DOT text, the ``dot`` process.

The corpus is built in a temporary directory from a synthetic generic-kind execution derived by the real PROV engine
(``render_support``); no committed fixture is read. Tests that need ``pydot`` or the Graphviz ``dot`` binary skip with the
reason when it is absent (the ``render`` gate runs them in an environment that has both).
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import render_support as rs

from agentprov.render import dot as dotmod
from agentprov.render import graph, style
from agentprov.render.errors import (
    RenderEnvironmentError,
    RenderInputError,
    RenderOutputRefusedError,
    RenderProcessError,
)
from agentprov.render.output import assert_output_allowed, default_output_dir, output_stem

pytestmark = pytest.mark.render

SRC = Path(__file__).resolve().parents[2] / "src" / "agentprov"
HAVE_PYDOT = importlib.util.find_spec("pydot") is not None
needs_pydot = pytest.mark.skipif(not HAVE_PYDOT, reason="the render extra (pydot) is not installed")
needs_dot = pytest.mark.skipif(not HAVE_PYDOT or shutil.which("dot") is None, reason="needs pydot and the Graphviz dot binary")
posix_only = pytest.mark.skipif(os.name != "posix", reason="shell-script stand-ins for dot")


@pytest.fixture(scope="module")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    base = tmp_path_factory.mktemp("render-corpus")
    scratch = base / "scratch"
    scratch.mkdir()
    return rs.build_corpus(base / "corpus", scratch)


@pytest.fixture(scope="module")
def doc(corpus: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    ex = corpus["exs"][0]
    return ex, corpus["docs"][ex]


# ------------------------------------------------------------------------------------------------ model
def test_default_is_exactly_the_core_bundle(doc):
    ex, document = doc
    model = graph.build_model(document, ex=ex)
    core = next(b for k, b in document["bundle"].items() if ".core." in k)
    declared = {k for section in ("entity", "activity", "agent") for k in core.get(section, {})}
    assert {n.key for n in model.nodes} == declared and all(n.bundle == 0 for n in model.nodes)
    expected = sum(
        len([t for t in style.EDGE_TARGETS[s][1] if t in body and style.EDGE_TARGETS[s][0] in body])
        for s in style.EDGE_TARGETS
        for body in core.get(s, {}).values()
    )
    assert len(model.edges) == expected and all(e.kind == "core" and not e.link for e in model.edges)
    assert [b.kind for b in model.bundles] == ["core"]


def test_all_adds_the_assessment_bundle_with_its_own_style_and_overlay(doc):
    ex, document = doc
    core_only = graph.build_model(document, ex=ex)
    model = graph.build_model(document, ex=ex, mode="all")
    assert [b.kind for b in model.bundles] == ["core", "inference", "assessment"]
    assert {n.key for n in core_only.nodes} <= {n.key for n in model.nodes}
    assert any(n.kind == "assessment" for n in model.nodes) and any(e.link for e in model.edges)
    by = {n.key: n for n in model.nodes}
    assert by["x:af0"].integrity == "untrusted" and by["x:m0"].integrity == "unknown"
    assert by["x:te1"].role == "send_sink" and by["x:ac0"].role == "endorser"
    assert by["x:m1"].integrity is None and by["x:m1"].role is None  # no label: never drawn as trusted or neutral
    untrusted = style.node_attrs("entity", "D", "core", integrity="untrusted")
    unknown = style.node_attrs("entity", "D", "core", integrity="unknown")
    plain = style.node_attrs("entity", "D", "core")
    assert untrusted["fillcolor"] == "#FFAAAA" and unknown["fillcolor"] == "#D9D9D9" and plain["fillcolor"] == "#FFFC87"
    assert style.node_attrs("activity", "D", "core", role="send_sink")["fillcolor"] == "#B02E2E"
    assert style.node_attrs("activity", "D", "core", role="unknown")["fillcolor"] == "#D9D9D9"
    # evidence class is the border style; bundle is the colour
    assert [style.node_attrs("entity", c, "core")["style"] for c in ("O", "D", "I")] == ["filled", "filled,dashed", "filled,dotted"]
    assert style.edge_attrs("used", "I", "inference")["color"] == style.BUNDLE_COLOUR["inference"]
    assert style.edge_attrs("used", "I", "assessment")["color"] != style.edge_attrs("used", "I", "inference")["color"]


def test_inference_edges_are_styled_apart_from_the_core(doc):
    ex, document = doc
    model = graph.build_model(document, ex=ex, mode="all")
    inferred = [e for e in model.edges if e.kind == "inference"]
    assert inferred and all(e.cls == "I" for e in inferred)  # the inferred input link of ac2 (used, wasInformedBy)
    assert not any(e.kind == "inference" for e in graph.build_model(document, ex=ex).edges)


def test_model_is_sorted_and_ids_are_stable(doc):
    ex, document = doc
    a, b = graph.build_model(document, ex=ex, mode="all"), graph.build_model(document, ex=ex, mode="all")
    assert a == b
    ids = a.node_ids()
    assert len(set(ids.values())) == len(ids) and all(re.fullmatch(r"n[0-9a-f]{12}", v) for v in ids.values())
    core_ids = graph.build_model(document, ex=ex).node_ids()
    assert all(ids[k] == v for k, v in core_ids.items())  # the same node keeps its id across modes


def test_invalid_documents_are_typed_errors_not_tracebacks(doc):
    ex, document = doc
    for bad in ({"prefix": {}, "entity": 3}, [], "x", {}, {k: v for k, v in document.items() if k != "bundle"}):
        with pytest.raises(RenderInputError) as caught:
            graph.build_model(bad, ex=ex)
        assert caught.value.exit_code == 1 and caught.value.code.startswith("render.")


# ------------------------------------------------------------------------------------------------ DOT text
@needs_pydot
def test_dot_is_deterministic_in_process_and_across_hash_seeds(doc, corpus, tmp_path):
    ex, document = doc
    model = graph.build_model(document, ex=ex, mode="all")
    first = dotmod.build_dot(model)
    assert first == dotmod.build_dot(graph.build_model(document, ex=ex, mode="all"))
    outputs = set()
    for seed in ("1", "2", "3"):
        out = tmp_path / f"out{seed}"
        env = {**os.environ, "PYTHONHASHSEED": seed, "AGENTPROV_HOME": str(tmp_path / "home")}
        done = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "agentprov", "render", "--corpus", str(corpus["root"]), "--ex", ex, "--bundle", "all",
             "--format", "dot", "--out", str(out)],
            capture_output=True, env=env, check=False,
        )  # fmt: skip
        assert done.returncode == 0, done.stderr.decode()
        outputs.add(next(out.rglob("*.dot")).read_bytes())
    assert outputs == {first.encode("utf-8")}


@needs_pydot
def test_default_dot_has_no_data_derived_text_and_no_link_attributes(doc):
    ex, document = doc
    leaked = json.dumps(document)
    assert rs.PAYLOAD_PARTS[0] in leaked  # the hostile label is in the document (prov:label of ac3)
    for mode in ("core", "all"):
        text = dotmod.build_dot(graph.build_model(document, ex=ex, mode=mode))
        for part in rs.PAYLOAD_PARTS:
            assert part not in text
        assert "agent-under-test" not in text and "lookup" not in text  # apv:name and apv:toolName values
        assert not re.search(r"\b(URL|href|tooltip|image|shapefile|labeltooltip|edgeURL)\s*=", text)
        assert "<TABLE" not in text.upper() and "<<" not in text
        assert not rs.CONTROL.search(text)


@needs_pydot
@pytest.mark.filterwarnings("ignore::DeprecationWarning")  # pydot's parser uses deprecated pyparsing names
def test_show_content_dot_is_escaped_and_parses(doc, tmp_path):
    ex, document = doc
    text = dotmod.build_dot(graph.build_model(document, ex=ex, mode="all"), show_content=True, content_chars=500)
    assert "agent-under-test" in text and "lookup" in text  # content is shown on request
    assert "$(touch /tmp/pwned)" in text  # inert once quoted; shown as data
    assert not rs.CONTROL.search(text)  # no raw control or bidi
    assert "<U+001B>" in text and "<U+202E>" in text
    assert not re.search(r"\b(URL|href|tooltip|image|shapefile)\s*=", text)
    import pydot

    parsed = pydot.graph_from_dot_data(text)
    assert parsed and len(parsed[0].get_node_list()) + sum(len(s.get_node_list()) for s in parsed[0].get_subgraphs()) > 10


@needs_pydot
def test_labels_escape_quote_backslash_and_newline():
    assert style.dot_quote('a"b\\c\nd') == '"a\\"b\\\\c\\nd"'
    label = style.node_label(
        "x:n", "entity", {"apv:note": 'q"\\\n\x1b<U+0041>', "prov:type": {"$": "apv:T", "type": "prov:QUALIFIED_NAME"}},
        cls="O", show_content=True,
    )  # fmt: skip
    assert "\n" in label and label.count("\n") == 3  # id, type, class and the one content line: only structural breaks
    assert "<U+001B>" in label and "<U+003C>U+0041>" in label.replace("<<", "<")


_ENTITY_ATTACKS = ["x&#x202E;y", "&#27;[31m", "&#0;", "&#xE0041;", "&lt;U+0041&gt;", "&amp;#x202E;", "a&b"]


def test_dot_quote_writes_ampersand_as_an_entity_so_graphviz_cannot_decode_markup():
    for attack in _ENTITY_ATTACKS:
        quoted = style.dot_quote(attack)
        assert quoted.count("&") == quoted.count("&amp;")  # every ampersand is the first character of &amp;
        assert not re.search(r"&(?!amp;)", quoted)
    assert style.dot_quote("x&#x202E;y") == '"x&amp;#x202E;y"'


@pytest.mark.skipif(shutil.which("dot") is None, reason="needs the Graphviz dot binary")
def test_dot_quote_entities_stay_inert_in_the_graphviz_svg():
    import xml.dom.minidom

    for attack in _ENTITY_ATTACKS:
        node_label = style.dot_quote(attack)
        src = "digraph g { n [label=" + node_label + "]; }"
        out = subprocess.run(  # noqa: S603 - fixed argv, test input only
            [shutil.which("dot") or "dot", "-Tsvg"], input=src.encode(), capture_output=True, timeout=30, check=True
        ).stdout
        text = out.decode("utf-8")  # valid UTF-8 (the unescaped &#xE0041; made it invalid)
        xml.dom.minidom.parseString(out)  # well-formed XML (the unescaped &#27; made it ill-formed)
        assert not rs.CONTROL.search(text)  # no raw ESC or bidi override
        assert not re.search("[\U000e0000-\U000e007f]", text)  # no Unicode tag character
        assert "&amp;" in text or attack == ""  # the ampersand survives as text, not as a decoded character


def test_label_tokens_outside_the_trusted_grammars_are_replaced():
    label = style.node_label(
        "x:bad id\n; rm", "entity",
        {"apv:rule": 'evil"rule@1', "prov:type": [{"$": 'a b:c"', "type": "prov:QUALIFIED_NAME"}]}, cls=None,
    )  # fmt: skip
    assert label.splitlines()[0] == "(id)" and "(rule)" in label and "evil" not in label and '"' not in label


# ------------------------------------------------------------------------------------------------ the process
@needs_pydot
def test_missing_pydot_is_an_environment_error_and_the_package_still_imports(monkeypatch, doc):
    monkeypatch.setitem(sys.modules, "pydot", None)
    with pytest.raises(RenderEnvironmentError) as caught:
        dotmod.require_pydot()
    assert caught.value.exit_code == 3 and "uv sync --frozen --group docs --extra render" in str(caught.value)
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-B", "-c", "import sys; sys.modules['pydot'] = None; import agentprov.render, agentprov.render.graph, agentprov.render.dot, agentprov.render.style"],
        capture_output=True, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr.decode()


def test_missing_dot_binary_is_an_environment_error(monkeypatch):
    monkeypatch.setattr(dotmod.shutil, "which", lambda *_a, **_k: None)
    with pytest.raises(RenderEnvironmentError) as caught:
        dotmod.find_dot()
    assert caught.value.exit_code == 3 and caught.value.code == "render.dot_missing" and "graphviz" in str(caught.value).lower()


def _script(tmp_path: Path, body: str) -> str:
    path = tmp_path / "fakedot"
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


@posix_only
def test_run_dot_returns_stdout_and_passes_the_graph_on_stdin_only(tmp_path):
    exe = _script(tmp_path, 'echo "$@" > args.txt; cat; pwd > cwd.txt; env > /dev/null')
    assert dotmod.run_dot(exe, "digraph{}", "svg") == b"digraph{}"
    assert not (tmp_path / "args.txt").exists()  # it ran in its own empty temporary directory


@posix_only
def test_run_dot_takes_json_for_a_gui_layout_and_still_refuses_other_formats(tmp_path):
    """D-397: ``dot -Tjson`` under the same process controls; any other -T stays refused (no -Tcmapx, -Timap ...)."""
    exe = _script(tmp_path, 'test "$1" = "-Tjson" && cat')
    assert dotmod.run_dot(exe, "digraph{}", "json") == b"digraph{}"
    for fmt in ("cmapx", "imap", "dot", "-o/tmp/x"):
        with pytest.raises(ValueError):
            dotmod.run_dot(exe, "digraph{}", fmt)


@needs_dot
def test_real_dot_json_parses_with_the_strict_loader(doc):
    from agentprov.ingest.loaders import strict_json_loads

    ex, document = doc
    text = dotmod.build_dot(graph.build_model(document, ex=ex))
    layout = strict_json_loads(dotmod.run_dot(dotmod.find_dot(), text, "json"))
    assert isinstance(layout, dict) and layout.get("objects")


@posix_only
def test_run_dot_failure_timeout_and_output_cap(tmp_path):
    with pytest.raises(RenderProcessError) as failed:
        dotmod.run_dot(_script(tmp_path, "cat >/dev/null; echo oops >&2; exit 3"), "x", "png")
    assert failed.value.code == "render.dot_failed" and "oops" not in str(failed.value)
    with pytest.raises(RenderProcessError) as slow:
        dotmod.run_dot(_script(tmp_path, "sleep 30"), "x", "svg", timeout=0.5)
    assert slow.value.code == "render.dot_timeout"
    with pytest.raises(RenderProcessError) as big:
        dotmod.run_dot(_script(tmp_path, "cat >/dev/null; head -c 100000 /dev/zero"), "x", "svg", max_output=1000)
    assert big.value.code == "render.dot_output_cap"


@posix_only
def test_dot_is_the_only_process_with_a_fixed_argv_and_a_minimal_environment(tmp_path, monkeypatch, doc):
    started: list[dict[str, Any]] = []
    real = subprocess.Popen

    def spy(argv, **kwargs):
        started.append({"argv": list(argv), **kwargs})
        return real(argv, **kwargs)

    exe = _script(tmp_path, "cat >/dev/null; echo '<svg/>'")
    monkeypatch.setattr(dotmod.subprocess, "Popen", spy)
    monkeypatch.setenv("SECRET_TOKEN_FOR_TEST", "hunter2")
    ex, document = doc
    text = "digraph { label=\"" + rs.payload().replace('"', "'") + "\" }"
    dotmod.run_dot(exe, text, "svg")
    assert len(started) == 1 and started[0]["argv"] == [exe, "-Tsvg"]
    assert set(started[0]["env"]) <= {"PATH", "LANG", "TZ"} and started[0]["start_new_session"] is True
    assert all(part not in " ".join(started[0]["argv"]) for part in rs.PAYLOAD_PARTS)


@needs_dot
def test_svg_has_no_script_and_no_data_derived_link(doc, tmp_path):
    ex, document = doc
    paths, _ = graph.render_prov_graph(document, tmp_path / "g", ex=ex, formats=["svg", "dot"], bundles="all", show_content=True)
    svg = paths[1].read_bytes().decode("utf-8")
    assert svg.lstrip().startswith("<?xml") and "<svg" in svg
    assert not re.search(r"<script|href=|xlink:|onload|onclick|<image|<a ", svg, re.IGNORECASE)
    assert not re.search(r"[\x00-\x08\x0b-\x1f\x7f]", svg)


@needs_dot
def test_png_and_pdf_are_written_atomically_beside_the_dot(doc, tmp_path):
    ex, document = doc
    paths, _ = graph.render_prov_graph(document, tmp_path / "d" / "g", ex=ex, formats=["png", "pdf"])
    assert [p.suffix for p in paths] == [".dot", ".png", ".pdf"]
    assert paths[1].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and paths[2].read_bytes()[:4] == b"%PDF"
    assert not list((tmp_path / "d").glob("*.tmp-*"))


@needs_pydot
def test_dry_run_builds_the_text_and_writes_nothing(doc, tmp_path):
    ex, document = doc
    paths, text = graph.render_prov_graph(document, tmp_path / "x" / "g", ex=ex, formats=["svg"], dry_run=True)
    assert text.startswith("digraph prov {") and not (tmp_path / "x").exists() and paths[0].name == "g.dot"


# ------------------------------------------------------------------------------------------------ output location
def test_output_is_refused_inside_a_corpus_and_the_default_is_beside_it(corpus, tmp_path):
    root = corpus["root"]
    assert default_output_dir(root) == root.with_name("corpus-rendered")
    assert default_output_dir(Path("/x/rope.partial")) == Path("/x/rope-rendered")
    assert assert_output_allowed(tmp_path / "elsewhere", root) == (tmp_path / "elsewhere").resolve()
    for inside in (root, root / "prov", root / "new" / "dir"):
        with pytest.raises(RenderOutputRefusedError) as caught:
            assert_output_allowed(inside, root)
        assert caught.value.exit_code == 4
    link = tmp_path / "link"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(RenderOutputRefusedError):
        assert_output_allowed(link / "r", root)


def test_output_is_refused_in_the_final_directory_a_working_corpus_is_sealed_into(tmp_path):
    # CC-7r: rendering C.partial with --out C created C, after which the working corpus could not be resumed or sealed
    work = tmp_path / "C.partial"
    work.mkdir()
    (work / "executions.jsonl").write_bytes(b"")
    final = tmp_path / "C"
    for out in (final, final / "renders"):
        with pytest.raises(RenderOutputRefusedError) as caught:
            assert_output_allowed(out, work)
        assert caught.value.code == "render.output_in_corpus" and caught.value.exit_code == 4
        assert not final.exists()
    # the reverse: the corpus root is the final directory and its working twin exists (even before it holds an index)
    other = tmp_path / "D"
    other.mkdir()
    twin = tmp_path / "D.partial"
    twin.mkdir()
    for out in (twin, twin / "renders"):
        with pytest.raises(RenderOutputRefusedError) as caught:
            assert_output_allowed(out, other)
        assert caught.value.code == "render.output_in_corpus"
    # a plain sibling is still allowed, and the default name stays allowed
    assert assert_output_allowed(tmp_path / "C-rendered", work) == (tmp_path / "C-rendered").resolve()
    assert assert_output_allowed(default_output_dir(other), other) == (tmp_path / "D-rendered").resolve()


def test_the_default_output_is_named_from_the_resolved_corpus_path(tmp_path, monkeypatch):
    work = tmp_path / "C.partial"
    (work / "sub").mkdir(parents=True)
    beside = Path(os.path.realpath(tmp_path)) / "C-rendered"
    monkeypatch.chdir(work)
    assert default_output_dir(".") == beside  # was ValueError: PosixPath('.') has an empty name
    assert default_output_dir(work / "sub" / "..") == beside  # was C.partial/sub/..-rendered, inside the corpus
    monkeypatch.chdir(work / "sub")
    assert default_output_dir("..") == beside
    from agentprov.render.output import RenderOutputRequiredError

    with pytest.raises(RenderOutputRequiredError) as caught:
        default_output_dir("/")
    assert caught.value.exit_code == 2 and caught.value.code == "render.output_required"


def test_a_sealed_corpus_above_the_output_is_refused_with_its_own_code(tmp_path):
    from agentprov.corpus.layout import SealedCorpusError

    sealed = tmp_path / "sealed"
    sealed.mkdir()
    (sealed / "corpus.json").write_text(json.dumps({"sealed": True}))
    with pytest.raises(SealedCorpusError) as caught:
        assert_output_allowed(sealed / "renders", tmp_path / "other")
    assert caught.value.exit_code == 4


def test_output_stem_mirrors_the_prov_tree():
    label = "prov/agentprov-prov-0.1/3f/ex_" + "a" * 26 + ".prov.json"
    assert output_stem(Path("/o"), label, spec_dir="agentprov-prov-0.1") == Path("/o/agentprov-prov-0.1/3f/ex_" + "a" * 26)
    with pytest.raises(ValueError):
        output_stem(Path("/o"), "aer/3f/x.aer.jsonl", spec_dir="agentprov-prov-0.1")


# ------------------------------------------------------------------------------------------------ static rules
def _render_sources() -> list[Path]:
    return sorted((SRC / "render").glob("*.py")) + [SRC / "cli" / "render.py"]


def test_pydot_is_imported_only_inside_functions_and_never_asked_to_spawn_graphviz():
    for path in _render_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # module level only
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(n.split(".")[0] in ("pydot", "prov") for n in names), f"{path.name}: module-level import of {names}"
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("create", "write_svg", "write_png", "write_pdf", "write_raw", "write"):
                owner = node.value.id if isinstance(node.value, ast.Name) else ""
                assert owner not in ("graph", "pydot", "g"), f"{path.name}:{node.lineno} calls pydot {node.attr}"


def test_render_never_imports_prov_dot_or_writes_into_the_corpus_modules():
    for path in _render_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module != "prov.dot" and not node.module.startswith(("agentprov.corpus.writer", "agentprov.raw.store"))
