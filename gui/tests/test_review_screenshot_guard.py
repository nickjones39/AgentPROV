"""GUI review GR-15: the documentation screenshot leak guard (``gui/tools/screenshots.py``). Its key shapes missed
Google, Hugging Face, fine-grained GitHub, Bearer/JWT and AWS-secret tokens, and ``visible_strings`` missed group box
titles, rich text panes, status bar messages, header labels, tree children and the native title bar's subtitle."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "screenshots.py"
A = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij0123456789"


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("agentprov_gui_screenshots_tool", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SH = _tool()
KEY = "sk" + "-" + A[:24]

SHAPES = {
    "google": "AI" + "za" + A[:35],
    "huggingface": "hf" + "_" + A[:34],
    "github-fine-grained": "github" + "_pat_" + A[:30] + "_" + A[:20],
    "bearer": "Authorization: " + "Bear" + "er " + A[10:40],
    "jwt": "ey" + "J" + A[:20] + "." + "ey" + "J" + A[5:25] + "." + A[:20],
    "aws-secret": "secret " + A[:40].replace("0", "/") + " end",
}
SAFE = {
    "sha256-hex": ("0123456789abcdef" * 4),
    "sha1-hex": ("0123456789abcdef" * 3)[:40],
    "sha1-hex-upper": ("0123456789ABCDEF" * 3)[:40],
    "corpus-id": "agentdojo-dev",
    "relative-path": "corpora/agentdojo-dev/executions.jsonl",
    "prose": "the bearer of the record",
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_key_shapes_match(name: str) -> None:
    assert SH.LEAKS.search(SHAPES[name]), name


@pytest.mark.parametrize("name", sorted(SAFE))
def test_ordinary_strings_do_not_match(name: str) -> None:
    assert not SH.LEAKS.search(SAFE[name]), name


# GR-63: an AWS secret next to '/' or '+' (a path or URL segment) is still caught; longer runs and hex digests are not
AWS = "wJalr" + "XUtnFEMI/K7MDENG/bPxRfiCY" + "EXAMPLEKEY"
AWS_ADJACENT = {
    "after-slash": "secrets/" + AWS,
    "before-slash": AWS + "/x",
    "s3-segment": "s3://bkt/" + AWS + "/obj",
    "after-plus": "a+" + AWS,
    "before-plus": AWS + "+a",
}
AWS_SAFE = {
    "sha256-hex-in-path": "blobs/sha256/" + ("0123456789abcdef" * 4),
    "base64-44": A[:44],
    "base64-64": (A * 2)[:64],
    "base64-88-in-path": "data/" + (A * 2)[:88] + "/x",
    "base64-41-after-plus": "a+" + A[:41],
}


@pytest.mark.parametrize("name", sorted(AWS_ADJACENT))
def test_aws_secret_next_to_slash_or_plus_matches(name: str) -> None:
    assert SH.LEAKS.search(AWS_ADJACENT[name]), name


@pytest.mark.parametrize("name", sorted(AWS_SAFE))
def test_aws_shape_skips_longer_runs_and_digests(name: str) -> None:
    assert not SH.LEAKS.search(AWS_SAFE[name]), name


def _group_box(parent: Any) -> Any:
    from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout

    box = QGroupBox(KEY, parent)
    QVBoxLayout(box).addWidget(QLabel("x"))
    return box


def _text_edit(parent: Any) -> Any:
    from PySide6.QtWidgets import QTextEdit

    edit = QTextEdit(parent)
    edit.setPlainText(KEY)
    return edit


def _text_browser(parent: Any) -> Any:
    from PySide6.QtWidgets import QTextBrowser

    browser = QTextBrowser(parent)
    browser.setPlainText(KEY)
    return browser


def _tree_child(parent: Any) -> Any:
    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

    tree = QTreeWidget(parent)
    tree.setHeaderLabels(["statement", "value"])
    top = QTreeWidgetItem(tree, ["document", ""])
    QTreeWidgetItem(QTreeWidgetItem(top, ["bundle", ""]), ["entity", KEY])
    tree.expandAll()
    return tree


def _table_header(parent: Any) -> Any:
    from PySide6.QtWidgets import QTableWidget

    table = QTableWidget(1, 1, parent)
    table.setHorizontalHeaderLabels([KEY])
    return table


def _vertical_header(parent: Any) -> Any:
    from PySide6.QtWidgets import QTableWidget

    table = QTableWidget(1, 1, parent)
    table.setVerticalHeaderLabels([KEY])
    return table


WIDGETS: dict[str, Callable[[Any], Any]] = {
    "group-box": _group_box,
    "text-edit": _text_edit,
    "text-browser": _text_browser,
    "tree-child": _tree_child,
    "table-header": _table_header,
    "vertical-header": _vertical_header,
}


@pytest.mark.parametrize("name", sorted(WIDGETS))
def test_guard_sees_widget_text(qapp: Any, name: str) -> None:
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    root = QWidget()
    QVBoxLayout(root).addWidget(WIDGETS[name](root))
    root.resize(420, 320)
    root.show()
    qapp.processEvents()
    try:
        assert any(KEY in s for s in SH.visible_strings(root)), name
        with pytest.raises(SystemExit):
            SH.guard(root, name)
    finally:
        root.close()


def test_guard_sees_status_bar_message(qapp: Any) -> None:
    from PySide6.QtWidgets import QLabel, QMainWindow

    window = QMainWindow()
    window.setCentralWidget(QLabel("c"))
    window.resize(420, 320)
    window.show()
    window.statusBar().showMessage(KEY)
    qapp.processEvents()
    try:
        with pytest.raises(SystemExit):
            SH.guard(window, "status")
    finally:
        window.close()


def test_tree_walk_is_capped(qapp: Any) -> None:
    from PySide6.QtGui import QStandardItem, QStandardItemModel
    from PySide6.QtWidgets import QTreeView

    model = QStandardItemModel()
    for i in range(30):
        top = QStandardItem(f"t{i}")
        top.appendRows([QStandardItem(f"c{i}.{j}") for j in range(400)])
        model.appendRow(top)
    view = QTreeView()
    view.setModel(model)
    view.show()
    qapp.processEvents()
    try:
        strings = SH.visible_strings(view)
        assert "c0.0" in strings and len(strings) <= 6000
    finally:
        view.close()


class _Window:
    def __init__(self, title: str, subtitle: str) -> None:
        self._title, self._subtitle = title, subtitle

    def title(self) -> str:
        return self._title

    def subtitle(self) -> str:
        return self._subtitle


class _Field:
    def __init__(self, value: str) -> None:
        self.value = value

    def stringValue(self) -> str:
        return self.value


class _Item:
    def __init__(self, ident: str, value: str) -> None:
        self.ident, self.field = ident, _Field(value)

    def itemIdentifier(self) -> str:
        return self.ident

    def searchField(self) -> _Field:
        return self.field


class _Toolbar:
    def __init__(self, items: list[_Item]) -> None:
        self._items = items

    def items(self) -> list[_Item]:
        return self._items


def _chrome(subtitle: str, search: str = "") -> Any:
    from agentprov_gui.platform import macos

    return macos.NativeChrome(_Window("AgentPROV", subtitle), _Toolbar([_Item(macos.SEARCH_ID, search)]), None,
                              _Field("0 jobs"), macos.DisplayFlags())


def test_native_chrome_text_is_scanned(qapp: Any) -> None:
    from PySide6.QtWidgets import QLabel

    for chrome in (_chrome(KEY), _chrome("Viewer", KEY)):
        root = QLabel("c")
        root.chrome = chrome  # type: ignore[attr-defined]
        root.show()
        qapp.processEvents()
        try:
            assert KEY in SH.visible_strings(root)
            with pytest.raises(SystemExit):
                SH.guard(root, "native")
        finally:
            root.close()


def test_native_chrome_visible_text() -> None:
    assert _chrome("Viewer", "query").visible_text() == ["AgentPROV", "Viewer", "0 jobs", "query"]


# F-11: the repository's own GitHub links are not secrets; their segments are checked one by one
OWN_LINKS = {
    "readme": "https://github.com/nickjones39/AgentPROV/blob/main/docs/architecture/README.md",
    "tree": "see github.com/nickjones39/AgentPROV/tree/main/docs/reports/gui/g5-cross-platform.md for the plan",
    "cli": "https://github.com/nickjones39/AgentPROV/blob/main/docs/architecture/MN_repo_cli.md#n212-stats",
}


@pytest.mark.parametrize("name", sorted(OWN_LINKS))
def test_the_repositorys_own_links_are_not_flagged(name: str) -> None:
    text = OWN_LINKS[name]
    assert SH.LEAKS.search(text), "the false positive F-11 fixes (the raw pattern still flags it)"
    assert SH.leak_hits(text) == [], name


def test_a_secret_inside_an_own_link_segment_or_beside_one_is_still_caught() -> None:
    assert SH.leak_hits("https://github.com/nickjones39/AgentPROV/blob/" + A[:40].replace("0", "Q") + "/x.md")
    assert SH.leak_hits(OWN_LINKS["readme"] + " key " + AWS)  # outside the link: the full check
    assert SH.leak_hits("https://github.com/nickjones39/AgentPROV/issues?q=" + KEY)  # an sk- key in a query


@pytest.mark.parametrize("text", [
    "https://github.com/someone-else/AgentPROVfork/blob/main/docs/architecture/README.md",  # not this repository
    "https://github.com/nickjones39/AgentPROV-mirror/blob/main/docs/architecture/README.md",  # a different repository
    "s3://bkt/" + AWS + "/obj",
])
def test_other_urls_get_the_full_check(text: str) -> None:
    assert SH.leak_hits(text) == [m.group(0) for m in SH.LEAKS.finditer(text)]
