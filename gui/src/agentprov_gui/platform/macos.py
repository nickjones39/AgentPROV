"""The macOS native chrome layer (D-440; macos-design §2.6; S15 of D-448). Darwin only.

THE only module that imports PyObjC (S15, enforced by ``tests/test_lint_native.py``). It adds what Qt 6.12 lacks:

1. an ``NSToolbar`` on the main window (unified style, icon-only, autosaved): each item shows an SF Symbol and triggers
   **the same ``QAction``** the menus and shortcuts use; an ``NSSearchToolbarItem`` whose text (the user's own input)
   goes only into the Viewer's id filter; an activity item showing a fixed-format job count; the window subtitle;
2. the Dock tile: a badge (running jobs) and a progress bar for the selected job;
3. notifications through ``UNUserNotificationCenter``, only in a signed ``.app`` bundle and once the user allowed them
   (authorisation is asked at install; dev runs, a pending answer and a refusal fall back to a Dock bounce);
4. the Window menu (``NSApp.setWindowsMenu_``) with Minimize, Zoom and Bring All to Front;
5. the accessibility display flags: Reduce Transparency, Differentiate Without Colour, Reduce Motion, Increase Contrast,
   and their change notification.

**Strings (S15):** this module receives only fixed strings, numbers and single-line ids already escaped by
``text.line`` (the window title and subtitle, the notification's corpus id), and applies ``text.clean`` to the
subtitle and notification text itself (escaped again only if a code point still would be: never a marker twice, GR-42). Never content, never an ``NSAttributedString``, never an ``NSTextView``.

**Fallback:** :func:`install` returns ``None`` (and the caller builds the Qt toolbar) when PyObjC is missing, the window
has no ``NSWindow``, the toolbar did not attach, or the window chrome above the content did not grow.
"""

from __future__ import annotations

import contextlib
import logging
import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget

from agentprov_gui.text import clean

__all__ = ["ITEMS", "DisplayFlags", "NativeChrome", "available", "install"]

log = logging.getLogger("agentprov_gui.platform.macos")

#: Toolbar items: identifier -> (SF Symbol, label). Every identifier names a QAction in the window's registry.
ITEMS: Final[Mapping[str, tuple[str, str]]] = {
    "toggleSidebar": ("sidebar.left", "Toggle Sidebar"),
    "openCorpus": ("folder", "Open Corpus"),
    "reload": ("arrow.clockwise", "Reload"),
    "newJob": ("plus", "New Job"),
    "devRun": ("hammer", "Dev Run"),
}
SEARCH_ID: Final = "search"
ACTIVITY_ID: Final = "activity"
_UNIFIED: Final = 3  # NSWindowToolbarStyleUnified (1 is Expanded: a separate title row above the toolbar)
_ICON_ONLY: Final = 2  # NSToolbarDisplayModeIconOnly


def available() -> bool:
    if sys.platform != "darwin":
        return False
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.platformName() != "cocoa":
        return False  # offscreen/minimal: a window id is not an NSView pointer
    try:
        import AppKit  # noqa: F401
        import objc  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(slots=True)
class DisplayFlags:
    reduce_transparency: bool = False
    differentiate_without_colour: bool = False
    reduce_motion: bool = False
    increase_contrast: bool = False


@dataclass(slots=True)
class NativeChrome:
    window: Any  # NSWindow
    toolbar: Any  # NSToolbar
    delegate: Any
    activity: Any  # NSTextField
    flags: DisplayFlags
    observers: list[Any] = field(default_factory=list)

    def set_subtitle(self, text: str) -> None:
        """``text`` is a fixed string or an id escaped by ``text.line`` (S15); ``clean`` here keeps it one line without
        escaping its markers twice (GR-42)."""
        self.window.setSubtitle_(clean(text, 200))

    def visible_text(self) -> list[str]:
        """The text the native chrome draws: window title, subtitle, activity item and search field (for the
        documentation screenshots' leak guard, ``gui/tools/screenshots.py``)."""
        out = [str(self.window.title() or ""), str(self.window.subtitle() or ""), str(self.activity.stringValue() or "")]
        for item in self.toolbar.items() or ():
            if str(item.itemIdentifier()) == SEARCH_ID:
                out.append(str(item.searchField().stringValue() or ""))
        return out

    def set_activity(self, running: int, ended: int) -> None:
        self.activity.setStringValue_(f"● {running} running" if running else f"{ended} jobs")
        _dock_badge(running)

    def set_progress(self, fraction: float | None) -> None:
        _dock_progress(fraction)

    def notify(self, title: str, body: str) -> None:
        _notify(title, body)


# ----------------------------------------------------------------------------------------------- PyObjC classes
_classes: dict[str, Any] = {}


def _make_classes() -> dict[str, Any]:
    """Objective-C classes are registered once per process."""
    if _classes:
        return _classes
    import AppKit
    import objc
    from Foundation import NSObject

    class AgentprovToolbarDelegate(NSObject):  # type: ignore[misc]
        def initWithActions_search_activity_(self, actions: Any, search: Any, activity: Any) -> Any:
            self = objc.super(AgentprovToolbarDelegate, self).init()
            if self is None:
                return None
            self.actions = actions
            self.search_callback = search
            self.activity_view = activity
            return self

        def toolbarDefaultItemIdentifiers_(self, toolbar: Any) -> Any:
            return [*ITEMS, AppKit.NSToolbarFlexibleSpaceItemIdentifier, ACTIVITY_ID, SEARCH_ID]

        def toolbarAllowedItemIdentifiers_(self, toolbar: Any) -> Any:
            return self.toolbarDefaultItemIdentifiers_(toolbar)

        def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(
            self, toolbar: Any, identifier: Any, inserted: bool
        ) -> Any:
            ident = str(identifier)
            if ident == SEARCH_ID:
                item = AppKit.NSSearchToolbarItem.alloc().initWithItemIdentifier_(identifier)
                item.searchField().setTarget_(self)
                item.searchField().setAction_("searchChanged:")
                item.setLabel_("Search")
                return item
            if ident == ACTIVITY_ID:
                item = AppKit.NSToolbarItem.alloc().initWithItemIdentifier_(identifier)
                item.setView_(self.activity_view)
                item.setLabel_("Activity")
                return item
            if ident not in ITEMS:
                return None
            symbol, label = ITEMS[ident]
            item = AppKit.NSToolbarItem.alloc().initWithItemIdentifier_(identifier)
            item.setLabel_(label)
            item.setToolTip_(label)
            image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol, label)
            if image is not None:
                item.setImage_(image)
            item.setTarget_(self)
            item.setAction_("performItem:")
            return item

        def performItem_(self, sender: Any) -> None:
            action = self.actions.get(str(sender.itemIdentifier()))
            if action is not None:
                action.trigger()

        def searchChanged_(self, sender: Any) -> None:
            if self.search_callback is not None:
                self.search_callback(str(sender.stringValue())[:200])

    class AgentprovFlagsObserver(NSObject):  # type: ignore[misc]
        def initWithCallback_(self, callback: Any) -> Any:
            self = objc.super(AgentprovFlagsObserver, self).init()
            if self is None:
                return None
            self.callback = callback
            return self

        def flagsChanged_(self, note: Any) -> None:
            self.callback(read_flags())

    _classes.update(delegate=AgentprovToolbarDelegate, observer=AgentprovFlagsObserver)
    return _classes


# ----------------------------------------------------------------------------------------------- pieces
def read_flags() -> DisplayFlags:
    import AppKit

    ws = AppKit.NSWorkspace.sharedWorkspace()
    return DisplayFlags(
        bool(ws.accessibilityDisplayShouldReduceTransparency()),
        bool(ws.accessibilityDisplayShouldDifferentiateWithoutColor()),
        bool(ws.accessibilityDisplayShouldReduceMotion()),
        bool(ws.accessibilityDisplayShouldIncreaseContrast()),
    )


def _ns_window(widget: QWidget) -> Any:
    import objc

    view = objc.objc_object(c_void_p=int(widget.winId()))
    return view.window() if view is not None else None


def _dock_badge(running: int) -> None:
    import AppKit

    AppKit.NSApp.dockTile().setBadgeLabel_(str(running) if running else "")


_progress: dict[str, Any] = {}


def _dock_progress(fraction: float | None) -> None:
    import AppKit

    tile = AppKit.NSApp.dockTile()
    if fraction is None:
        tile.setContentView_(None)
        tile.display()
        return
    if "view" not in _progress:
        size = tile.size()
        view = AppKit.NSImageView.alloc().initWithFrame_(((0, 0), (size.width, size.height)))
        view.setImage_(AppKit.NSApp.applicationIconImage())
        bar = AppKit.NSProgressIndicator.alloc().initWithFrame_(((size.width * 0.1, 4), (size.width * 0.8, 14)))
        bar.setStyle_(0)  # NSProgressIndicatorStyleBar
        bar.setIndeterminate_(False)
        bar.setMinValue_(0.0)
        bar.setMaxValue_(1.0)
        view.addSubview_(bar)
        _progress.update(view=view, bar=bar)
    _progress["bar"].setDoubleValue_(max(0.0, min(1.0, fraction)))
    tile.setContentView_(_progress["view"])
    tile.display()


_INTERPRETER_IDS: Final = ("org.python.", "com.apple.python")
_ALERT_SOUND: Final = 4 | 2  # UNAuthorizationOptionAlert | UNAuthorizationOptionSound
_ALLOWED: Final = (2, 3, 4)  # UNAuthorizationStatusAuthorized, Provisional, Ephemeral
#: Notification authorisation: ``requested`` once per process, ``granted`` set by the system's answer and, after a
#: refusal, by the current settings (GR-67).
_auth: dict[str, bool] = {}


def signed_bundle() -> bool:
    """True in AgentPROV's own ``.app``. A framework Python (python.org or Homebrew ``org.python.python``, Apple's
    ``com.apple.python3``) runs from a ``Python.app`` too, so an interpreter bundle is refused and its dev runs use the
    fallback. The bundle identifier is fixed with the signed build (G5); compare against it once it exists."""
    import Foundation

    bundle = Foundation.NSBundle.mainBundle()
    ident, path = str(bundle.bundleIdentifier() or ""), str(bundle.bundlePath() or "")
    if not ident or not path.endswith(".app") or path.rsplit("/", 1)[-1] == "Python.app":
        return False
    return not ident.lower().startswith(_INTERPRETER_IDS)


def _bounce() -> None:
    import AppKit

    AppKit.NSApp.requestUserAttention_(0)  # NSCriticalRequest, the same request QApplication.alert sends


def _bounce_on_main() -> None:
    """Completion handlers run on a background queue; AppKit is called on the main thread only."""
    import Foundation

    Foundation.NSOperationQueue.mainQueue().addOperationWithBlock_(_bounce)


def _authorised(granted: bool, error: Any) -> None:
    _auth["granted"] = bool(granted) and error is None
    log.info("notification authorisation granted: %s", _auth["granted"])


def _settings(settings: Any) -> None:
    """Completion handler of ``getNotificationSettings``: a background queue, so it only records the status."""
    _auth["granted"] = settings is not None and settings.authorizationStatus() in _ALLOWED


def _request_authorisation() -> None:
    """Ask once per process, in a signed bundle only. Called at install (GR-67), so the answer is normally known before
    the first long job ends; a dev run never asks."""
    if _auth.get("requested") or not signed_bundle():
        return
    import UserNotifications as UN

    _auth["requested"] = True
    UN.UNUserNotificationCenter.currentNotificationCenter().requestAuthorizationWithOptions_completionHandler_(
        _ALERT_SOUND, _authorised)


def _added(error: Any) -> None:
    if error is not None:
        log.info("notification refused (code %s); Dock bounce instead", error.code())
        _bounce_on_main()


def _notify(title: str, body: str) -> None:
    """A notification in a signed bundle once the user allowed it; a Dock bounce otherwise (macos-design §6).
    Authorisation is asked once (at install, or here if it was not), so a notification while the answer is pending, or
    after a refusal, bounces; after a refusal the current settings are read again (this never prompts), so notifications
    allowed later in System Settings are used without a restart (GR-67). Fixed text
    plus escaped ids, passed through ``clean`` so nothing but one line reaches ``UNNotificationContent`` (S15) and no
    marker is escaped twice (GR-42)."""
    title, body = clean(title, 120), clean(body, 240)

    if not signed_bundle():
        _bounce()
        return
    import UserNotifications as UN

    _request_authorisation()
    center = UN.UNUserNotificationCenter.currentNotificationCenter()
    if not _auth.get("granted"):
        if _auth.get("granted") is False:
            center.getNotificationSettingsWithCompletionHandler_(_settings)
        _bounce()
        return
    content = UN.UNMutableNotificationContent.alloc().init()
    content.setTitle_(title)
    content.setBody_(body)
    # One identifier per notification: a shared one makes a later job's notification replace an earlier one.
    request = UN.UNNotificationRequest.requestWithIdentifier_content_trigger_(f"job-{uuid.uuid4().hex}", content, None)
    center.addNotificationRequest_withCompletionHandler_(request, _added)


def _window_menu(title: str = "Window") -> bool:
    """Make the menu bar's Window menu the AppKit windows menu, with the standard actions."""
    import AppKit

    main = AppKit.NSApp.mainMenu()
    if main is None:
        return False
    for i in range(main.numberOfItems()):
        item = main.itemAtIndex_(i)
        if str(item.title()) == title and item.submenu() is not None:
            menu = item.submenu()
            if menu.numberOfItems() == 0:
                for label, selector, key in (("Minimize", "performMiniaturize:", "m"), ("Zoom", "performZoom:", ""),
                                             ("Bring All to Front", "arrangeInFront:", "")):
                    menu.addItemWithTitle_action_keyEquivalent_(label, selector, key)
            AppKit.NSApp.setWindowsMenu_(menu)
            return True
    return False


# ----------------------------------------------------------------------------------------------- install
def install(
    widget: QWidget,
    actions: Mapping[str, QAction],
    *,
    on_search: Callable[[str], None] | None = None,
    on_flags: Callable[[DisplayFlags], None] | None = None,
) -> NativeChrome | None:
    """Attach the native chrome to ``widget``'s window, or return ``None`` (the caller uses the Qt toolbar)."""
    if not available():
        return None
    missing = [k for k in ITEMS if k not in actions]
    if missing:
        log.info("native chrome: actions missing (%s); Qt toolbar", ",".join(missing))
        return None
    window: Any = None
    toolbar: Any = None
    try:
        import AppKit

        classes = _make_classes()
        window = _ns_window(widget)
        if window is None:
            log.info("native chrome: no NSWindow; Qt toolbar")
            return None
        before = window.frame().size.height - window.contentLayoutRect().size.height  # chrome above the content
        activity = AppKit.NSTextField.labelWithString_("")
        delegate = classes["delegate"].alloc().initWithActions_search_activity_(dict(actions), on_search, activity)
        toolbar = AppKit.NSToolbar.alloc().initWithIdentifier_("main")
        toolbar.setDelegate_(delegate)
        toolbar.setDisplayMode_(_ICON_ONLY)
        toolbar.setAllowsUserCustomization_(False)
        toolbar.setAutosavesConfiguration_(True)
        window.setToolbar_(toolbar)
        window.setToolbarStyle_(_UNIFIED)
        after = window.frame().size.height - window.contentLayoutRect().size.height
        # AppKit keeps the content size and grows the frame, so the chrome above the content must grow (measured on
        # macOS 27, unified style: 28 -> 52 pt); macos-design §2.6 said "the content rect shrinks", which holds for a fixed frame.
        attached = window.toolbar() == toolbar
        if not attached or not after > before:
            window.setToolbar_(None)
            log.info("native chrome: smoke check failed (toolbar %s, chrome %s -> %s); Qt toolbar", attached, before,
                     after)
            return None
        chrome = NativeChrome(window, toolbar, delegate, activity, read_flags())
        _window_menu()
        if on_flags is not None:
            observer = classes["observer"].alloc().initWithCallback_(on_flags)
            AppKit.NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
                observer, "flagsChanged:", AppKit.NSWorkspaceAccessibilityDisplayOptionsDidChangeNotification, None
            )
            chrome.observers.append(observer)
    except Exception as exc:
        # A late failure must not leave the toolbar attached: its delegate is released on return, so its items would
        # be dead beside the caller's Qt toolbar. Detach it, as the smoke check does.
        if window is not None and toolbar is not None:
            with contextlib.suppress(Exception):
                if window.toolbar() == toolbar:
                    window.setToolbar_(None)
        log.info("native chrome: %s; Qt toolbar", type(exc).__name__)
        return None
    try:
        _request_authorisation()  # GR-67: before the first notification, not at it
    except Exception as exc:  # notifications then fall back to the Dock bounce; the chrome stays
        log.info("notification authorisation: %s", type(exc).__name__)
    return chrome


def capture_window_png(widget: QWidget, path: str) -> bool:
    """Render ``widget``'s window, native toolbar included, to a PNG (``cacheDisplayInRect``; no screen recording).
    For documentation screenshots only (``gui/tools/screenshots.py``)."""
    if not available():
        return False
    import AppKit

    window = _ns_window(widget)
    if window is None:
        return False
    frame_view = window.contentView().superview()
    rect = frame_view.bounds()
    rep = frame_view.bitmapImageRepForCachingDisplayInRect_(rect)
    frame_view.cacheDisplayInRect_toBitmapImageRep_(rect, rep)
    data = rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, None)
    return bool(data is not None and data.writeToFile_atomically_(path, True))
