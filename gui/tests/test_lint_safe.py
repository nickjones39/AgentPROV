"""S1 (D-396): text-bearing widgets that could interpret markup are made only in ``ui/safe.py``.

Banned elsewhere: ``QLabel``, ``QMessageBox``, ``QTextBrowser``, ``QTextEdit``, ``QGraphicsTextItem``, ``QFormLayout``,
``QInputDialog``, ``QWizard``, ``QToolTip``, ``QDesktopServices``, ``QProgressDialog`` (its label is ``AutoText``),
``QErrorMessage``, ``QStaticText``, ``QTextDocumentFragment``, ``QWhatsThis``, ``QSystemTrayIcon``, ``QSplashScreen``;
the calls ``setHtml``, ``setMarkdown``, ``insertHtml``, ``setToolTip``, ``setTabToolTip``, ``setItemToolTip``,
``setWhatsThis``, ``setTabWhatsThis``, ``setItemWhatsThis``, ``fromHtml``, ``setOpenExternalLinks``, ``openUrl``,
``setTextFormat``; and the names ``RichText``, ``AutoText``, ``MarkdownText``, ``ToolTipRole`` and ``WhatsThisRole``
(item models answer tooltips through ``safe.is_tooltip_role`` / ``safe.safe_tooltip``). A bare ``showMessage`` stays
allowed: ``QStatusBar`` draws plain text, and the markup-capable owners (``QErrorMessage``, ``QSystemTrayIcon``,
``QSplashScreen``, whose ``drawContents`` renders a rich-text message as HTML) are caught by their class names."""

from __future__ import annotations

import ast

import pytest

from _ast_support import modules, rel

BANNED_NAMES = frozenset({
    "QLabel", "QMessageBox", "QTextBrowser", "QTextEdit", "QGraphicsTextItem", "QFormLayout", "QInputDialog", "QWizard",
    "QWizardPage", "QToolTip", "QDesktopServices", "RichText", "AutoText", "MarkdownText", "ToolTipRole",
    "convertFromPlainText", "QProgressDialog", "QErrorMessage", "QStaticText", "QTextDocumentFragment", "QWhatsThis",
    "QSystemTrayIcon", "WhatsThisRole", "QSplashScreen",
})  # fmt: skip
BANNED_CALLS = frozenset({
    "setHtml", "setMarkdown", "insertHtml", "setToolTip", "setTabToolTip", "setWhatsThis", "setOpenExternalLinks",
    "openUrl", "setTextFormat", "setStatusTip", "appendHtml", "setTabWhatsThis", "setItemWhatsThis", "fromHtml",
    "setItemToolTip",
})  # fmt: skip
SAFE = "ui/safe.py"


def _tree_violations(where: str, tree: ast.Module) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            out.append(f"{where}:{node.lineno}: {node.id}")
        elif isinstance(node, ast.Attribute) and (node.attr in BANNED_NAMES or node.attr in BANNED_CALLS):
            out.append(f"{where}:{node.lineno}: .{node.attr}")
        elif isinstance(node, ast.alias) and node.name.rsplit(".", 1)[-1] in BANNED_NAMES:
            out.append(f"{where}:{getattr(node, 'lineno', 0)}: import {node.name}")
    return out


def _violations() -> list[str]:
    out: list[str] = []
    for path, tree in modules():
        if rel(path) != SAFE:
            out.extend(_tree_violations(rel(path), tree))
    return out


def test_no_markup_capable_widgets_outside_safe() -> None:
    bad = _violations()
    assert not bad, "S1 violations:\n" + "\n".join(bad)


@pytest.mark.parametrize(
    "source",
    [
        "from PySide6.QtWidgets import QProgressDialog",
        "d = QProgressDialog(data, 'c', 0, 1)",
        "QErrorMessage().showMessage(data)",
        "t = QStaticText(data)",
        "item.setData(0, Qt.ItemDataRole.WhatsThisRole, data)",
        "tabs.setTabWhatsThis(0, data)",
        "box.setItemWhatsThis(0, data)",
        "w.setWhatsThis(data)",
        "f = QTextDocumentFragment.fromHtml(data)",
        "QSystemTrayIcon().showMessage('t', data)",
        "QWhatsThis.showText(p, data)",
        "from PySide6.QtWidgets import QSplashScreen",
        "QSplashScreen().showMessage(data)",
        "box.setItemToolTip(0, data)",
    ],
)
def test_lint_flags_markup_capable_api(source: str) -> None:
    assert _tree_violations("synthetic.py", ast.parse(source)), source


def test_lint_leaves_status_bar_message_alone() -> None:
    # QStatusBar draws plain text, so a bare ``showMessage`` stays allowed.
    assert not _tree_violations("synthetic.py", ast.parse("self.statusBar().showMessage(msg)"))


def test_safe_label_is_plain(qapp: object, hostile: list[str]) -> None:
    from PySide6.QtCore import Qt

    from agentprov_gui.ui.safe import SafeLabel

    for s in hostile:
        label = SafeLabel(s, name="test")
        assert label.textFormat() == Qt.TextFormat.PlainText
        assert not label.openExternalLinks()
        assert label.text() == s  # shown literally
        label.setTextFormat(Qt.TextFormat.RichText)  # a later caller cannot switch it
        assert label.textFormat() == Qt.TextFormat.PlainText
        assert label.accessibleName() == "test"


def test_safe_message_box_is_plain(qapp: object, hostile: list[str]) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    from agentprov_gui.ui.safe import safe_message_box

    box = safe_message_box(None, "t", hostile[0], informative=hostile[1], detailed=hostile[2])
    assert box.textFormat() == Qt.TextFormat.PlainText
    for label in box.findChildren(QLabel):
        assert label.textFormat() == Qt.TextFormat.PlainText
        assert not label.openExternalLinks()


@pytest.mark.parametrize("index", range(8))
def test_tooltip_escapes(qapp: object, hostile: list[str], index: int) -> None:
    from agentprov_gui.ui.safe import safe_tooltip

    tip = safe_tooltip(hostile[index])
    for tag in ("<b>", "<a ", "<img"):
        assert tag not in tip.lower()
    assert "\x1b" not in tip and "\u202e" not in tip
