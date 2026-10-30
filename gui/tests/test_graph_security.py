"""S5 (D-396, D-397): graph input. DOT is built only from ``render.style``'s trusted grammars; no link attribute; ``dot``
runs under the G.8.6 controls; its JSON is parsed strictly; draw operations that carry text are ignored; labels come
from the model. A hostile PROV document (strings assembled at run time) yields no data-derived string in the DOT text,
in the layout or in the scene."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from agentprov.render.graph import build_model

from _corpus_support import first_prov, poison
from agentprov_gui.graph import dotjson
from agentprov_gui.graph.emit import build_layout_dot
from agentprov_gui.graph.layout import compute_layout
from agentprov_gui.graph.viewgraph import full_view, overlay_view

needs_dot = pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz dot is not installed")
FORBIDDEN_ATTRS = re.compile(r"\b(URL|href|tooltip|image|shapefile|target|xlabel|headlabel|taillabel)\s*=", re.I)


def _fragments(strings: list[str]) -> list[str]:
    """Distinctive pieces of the hostile strings (what must never appear)."""
    return ["bold", "click", "passwd", "txt.exe", "[31m", "line2", "ignore previous", "&#x202E;"]


def test_hostile_document_still_validates(mini_corpus: Path, hostile: list[str]) -> None:
    ex, doc = first_prov(mini_corpus)
    bad, placed = poison(doc, hostile)
    assert placed, "the fixture document has free-text attributes to poison"
    model = build_model(bad, ex=ex, mode="all")
    assert model.nodes


def test_dot_text_has_no_data_strings_and_no_links(mini_corpus: Path, hostile: list[str]) -> None:
    ex, doc = first_prov(mini_corpus)
    bad, _ = poison(doc, hostile)
    model = build_model(bad, ex=ex, mode="all")
    for view in (overlay_view(model), full_view(model)):
        text = build_layout_dot(view, model.node_ids())
        for frag in _fragments(hostile):
            assert frag not in text
        assert not FORBIDDEN_ATTRS.search(text)
        assert "\x1b" not in text and "\u202e" not in text and "<" not in text


@needs_dot
def test_layout_and_scene_carry_no_data_strings(qapp: object, mini_corpus: Path, hostile: list[str],
                                                tmp_path: Path) -> None:
    from PySide6.QtWidgets import QGraphicsSimpleTextItem

    from agentprov_gui.graph.scene import GraphScene
    from agentprov_gui.ui import theme

    ex, doc = first_prov(mini_corpus)
    bad, _ = poison(doc, hostile)
    model = build_model(bad, ex=ex, mode="all")
    for view, engine in ((overlay_view(model), "auto"), (full_view(model), "layered")):
        result = compute_layout(view, engine=engine, cache_dir=tmp_path / "cache")
        assert result.layout.engine == ("dot" if engine == "auto" else "layered")
        scene = GraphScene(view, result.layout, theme.graph_palette(dark=False))
        texts = [item.text() for item in scene.items() if isinstance(item, QGraphicsSimpleTextItem)]
        assert texts
        for t in texts:
            for frag in _fragments(hostile):
                assert frag not in t
            assert "\x1b" not in t and "\u202e" not in t


def test_dot_process_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixed argv, DOT on stdin, PATH/LANG/TZ only, empty temporary cwd, new session, files instead of pipes."""
    seen: dict[str, object] = {}

    class FakePopen:
        def __init__(self, argv: list[str], **kwargs: object) -> None:
            seen["argv"], seen["kwargs"] = argv, kwargs
            self.returncode = 0
            self.pid = 0
            out = kwargs["stdout"]
            out.write(b'{"bb":"0,0,10,10","objects":[],"edges":[]}')  # type: ignore[attr-defined]

        def communicate(self, data: bytes, timeout: float) -> tuple[None, None]:
            seen["stdin"], seen["timeout"] = data, timeout
            return None, None

    monkeypatch.setenv("SECRET_API_KEY", "x" * 8)
    monkeypatch.setattr(dotjson.subprocess, "Popen", FakePopen)
    out = dotjson.run_dot_json("digraph{}", flags=("-Gnslimit=2",), exe="/usr/bin/dot", timeout=7)
    assert out.startswith(b"{")
    assert seen["argv"] == ["/usr/bin/dot", "-Tjson", "-Gnslimit=2"]
    kwargs = seen["kwargs"]
    assert isinstance(kwargs, dict)
    assert set(kwargs["env"]) <= {"PATH", "LANG", "TZ"}
    assert kwargs["start_new_session"] is True and kwargs["close_fds"] is True
    assert Path(kwargs["cwd"]).name.startswith("agentprov-gui-dot-")
    assert seen["stdin"] == b"digraph{}" and seen["timeout"] == 7
    with pytest.raises(ValueError):
        dotjson.run_dot_json("digraph{}", flags=("-o/tmp/x",), exe="/usr/bin/dot")


def test_dot_json_parser_ignores_text_ops_and_refuses_unknown_nodes() -> None:
    data = (b'{"bb":"0,0,100,50","objects":[{"_gvid":0,"name":"n1","pos":"10,20","width":"1","height":"0.5",'
            b'"_ldraw_":[{"op":"T","text":"<b>x</b>"}],"label":"<b>x</b>"}],"edges":[]}')
    layout = dotjson.parse_dot_json(data, {"n1": "xd:a"})
    assert layout.nodes["xd:a"] == (10.0, 30.0, 72.0, 36.0)  # y flipped
    with pytest.raises(dotjson.DotFailed):
        dotjson.parse_dot_json(data, {"n2": "xd:b"})
    with pytest.raises(dotjson.DotFailed):
        dotjson.parse_dot_json(b'{"bb":"0,0,1,1","objects":[{"name":"n1","pos":"x"}]}', {"n1": "k"})
    with pytest.raises(dotjson.DotFailed):
        dotjson.parse_dot_json(b'{"bb": NaN}', {})
