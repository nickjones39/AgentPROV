"""Features this platform cannot run, in the window (D-1064): each such control disabled with the CLI's message as its
tooltip, and a short notice where the action would appear.

The facts are :mod:`agentprov_gui.platform_limits` (the configured CLI's ``agentprov info --format json``). A gated
control stays visible; its tooltip is the table's message ("… available on macOS and Linux. On Windows … not available
…: reason. See the user guide, …"), shown although the control is disabled. The notice is a card with a badge ("Not
available on Windows x86_64"), where the feature works and why not here, and a "How to run it" link that opens the
guide's section: on the Docs page when the notice is in the main window, else in a guide window of its own (a modal
dialog would hide the main window's page). Everything else stays enabled.

:func:`apply` replaces the app's answer and tells every page (``notifier().changed``); a page re-gates its controls.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from agentprov_gui import platform_limits
from agentprov_gui.platform_limits import Limit, PlatformLimits
from agentprov_gui.ui import forms
from agentprov_gui.ui.forms import StatusBadge
from agentprov_gui.ui.safe import (
    set_combo_item_tooltip,
    set_control_tooltip,
    set_help_tooltip,
    set_unavailable_tooltip,
)

__all__ = ["GUIDE_LINK", "PlatformNotice", "apply", "gate", "gate_action", "gate_combo_item", "notifier", "open_guide",
           "set_docs"]

#: the notice's link (its accessible name is mapped in ``parity.PRESENTATIONAL``)
GUIDE_LINK = "Open the user guide on how to run it"


class _Notifier(QObject):
    changed = Signal()


_NOTIFIER: list[_Notifier] = []
#: the main window's Docs page and how to show it (set_docs); empty: a guide window of its own
_DOCS: list[tuple[Any, Callable[[], None]]] = []


def notifier() -> _Notifier:
    if not _NOTIFIER:
        _NOTIFIER.append(_Notifier())
    return _NOTIFIER[0]


def apply(limits: PlatformLimits | None) -> None:
    """Make ``limits`` the app's answer (``None``: unknown) and tell every page."""
    platform_limits.set_current(limits)
    notifier().changed.emit()


def gate(widget: QWidget, limit: Limit | None) -> None:
    """Disable ``widget`` with ``limit``'s message as its tooltip, or (``None``) enable it with its own tooltip again.
    Only for a control nothing else disables (Run Live's buttons have their own gate)."""
    set_unavailable_tooltip(widget, limit.message if limit is not None else None)
    widget.setEnabled(limit is None)


def gate_action(action: QAction, limit: Limit | None) -> None:
    """A menu action: it stays in its menu, disabled, with the message as its tooltip (the menu shows tooltips)."""
    set_unavailable_tooltip(action, limit.message if limit is not None else None)
    action.setEnabled(limit is None)


def gate_combo_item(box: QComboBox, text: str, limit: Limit | None, *, after: int = 0) -> None:
    """Show the choice ``text`` disabled, with the message as its tooltip, while ``limit`` applies (inserted at
    ``after`` + 1 when missing); a choice that only the limit added is removed again once it no longer applies."""
    index = box.findText(text)
    if limit is None:
        if index >= 0 and box.itemData(index, Qt.ItemDataRole.UserRole) == "platform":
            box.removeItem(index)
        return
    if index < 0:
        index = min(after + 1, box.count())
        box.insertItem(index, text, "platform")
    model = box.model()
    item = model.item(index) if hasattr(model, "item") else None
    if item is not None:
        item.setEnabled(False)
    set_combo_item_tooltip(box, index, limit.message)


def set_docs(page: Any, show: Callable[[], None]) -> None:
    """The main window's Docs page (``follow(QUrl)``) and how to bring it to the front."""
    _DOCS.clear()
    _DOCS.append((page, show))


def open_guide(guide: str, origin: QWidget) -> None:
    """Open the guide's section ``guide`` (``07-live-runs.md#platforms``): on the main window's Docs page when
    ``origin`` is in that window, else in a guide window of ``origin``'s window, which a modal dialog leaves usable."""
    if not guide:
        return
    url = QUrl(guide)
    checkout = None
    if _DOCS:
        page, show = _DOCS[0]
        try:
            here = origin.window() is page.window()
        except RuntimeError:  # that window is gone
            _DOCS.clear()
        else:
            if here:
                show()
                page.follow(url)
                return
            checkout = page.checkout
    from agentprov_gui.ui.help import DocsPage

    window = DocsPage(checkout, origin.window())
    window.setWindowFlag(Qt.WindowType.Window, True)
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    window.setWindowTitle("AgentPROV user guide")
    window.resize(980, 720)
    window.show()
    window.follow(url)


class PlatformNotice(QFrame):
    """The inline notice for one feature: a card with the badge "Not available on PLATFORM", where it works and why not
    here, and "How to run it". Hidden while the feature is available (or nothing is known)."""

    def __init__(self, feature: str, *, name: str, subject: str | None = None, parent: QWidget | None = None,
                 card: bool = True) -> None:
        """``card``: a card of its own (on a page or a summary); false inside a section's card (a row of it)."""
        super().__init__(parent)
        self.feature, self.subject = feature, subject
        self.limit: Limit | None = None
        if card:
            self.setProperty("apvRole", "card")
        self.setAccessibleName(name)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*((14, 10, 14, 10) if card else (0, 0, 0, 0)))
        lay.setSpacing(6)
        self.badge = StatusBadge("", name=f"{name}: platform", kind="warn", parent=self)
        set_help_tooltip(self.badge, "This platform cannot run the feature; it works on the platforms named below.")
        lay.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.text = forms.caption("", name=f"{name}: why", parent=self, role="secondary")
        lay.addWidget(self.text)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.link = forms.link_button("How to run it", name=GUIDE_LINK, parent=self)
        self.link.clicked.connect(self._open)
        set_control_tooltip(self.link, "Opens the user guide's section on where this works and how to run it there.")
        row.addWidget(self.link)
        row.addStretch(1)
        lay.addLayout(row)
        self.setVisible(False)
        self.refresh()

    def refresh(self, limits: PlatformLimits | None = None) -> Limit | None:
        """Show or hide the notice for ``limits`` (default: the app's answer); returns the limit that applies."""
        return self.show_limit((limits or platform_limits.current()).get(self.feature, self.subject))

    def show_limit(self, limit: Limit | None) -> Limit | None:
        """Show the notice for ``limit`` (a form's command decides which feature), or hide it for ``None``."""
        self.limit = limit
        self.setVisible(limit is not None)
        if limit is not None:
            self.badge.set_status(limit.headline, "warn")
            self.text.set_plain(limit.explanation)
            set_help_tooltip(self.text, limit.message)
            self.link.setVisible(bool(limit.guide))
        return limit

    def set_subject(self, subject: str | None) -> Limit | None:
        self.subject = subject
        return self.refresh()

    def _open(self) -> None:
        if self.limit is not None:
            open_guide(self.limit.guide, self)
