"""GUI review GR-39: notifications in the signed bundle ask for authorisation once and fall back to the Dock bounce
unless it was granted, report a failed request through a completion handler, and use a unique identifier per
notification. ``signed_bundle()`` refuses a framework Python's ``Python.app`` (python.org or Homebrew
``org.python.python``, Apple's ``com.apple.python3``), whose dev runs used to take the notification path.

No PyObjC is called: ``Foundation``, ``AppKit`` and ``UserNotifications`` are stub modules in ``sys.modules``."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from typing import Any

import pytest

PY_APP = "/Library/Frameworks/Python.framework/Versions/3.14/Resources/" + "Python" + ".app"
CLT_APP = "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/" + "Python.app"
OWN_APP = "/Applications/" + "AgentPROV.app"


class _Center:
    def __init__(self) -> None:
        self.auth: list[tuple[int, Callable[..., None]]] = []
        self.added: list[tuple[str, Any]] = []
        self.settings: list[Callable[..., None]] = []

    def requestAuthorizationWithOptions_completionHandler_(self, options: int, handler: Callable[..., None]) -> None:
        self.auth.append((options, handler))

    def getNotificationSettingsWithCompletionHandler_(self, handler: Callable[..., None]) -> None:
        self.settings.append(handler)

    def addNotificationRequest_withCompletionHandler_(self, request: str, handler: Any) -> None:
        self.added.append((request, handler))


class _Stubs:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.bundle = ("", "")
        self.bounces: list[int] = []
        self.center = _Center()
        found = types.ModuleType("Foundation")
        found.NSBundle = types.SimpleNamespace(  # type: ignore[attr-defined]
            mainBundle=lambda: types.SimpleNamespace(bundleIdentifier=lambda: self.bundle[0] or None,
                                                     bundlePath=lambda: self.bundle[1]))
        found.NSOperationQueue = types.SimpleNamespace(  # type: ignore[attr-defined]
            mainQueue=lambda: types.SimpleNamespace(addOperationWithBlock_=lambda block: block()))
        appkit = types.ModuleType("AppKit")
        appkit.NSApp = types.SimpleNamespace(requestUserAttention_=self.bounces.append)  # type: ignore[attr-defined]
        un = types.ModuleType("UserNotifications")
        un.UNUserNotificationCenter = types.SimpleNamespace(  # type: ignore[attr-defined]
            currentNotificationCenter=lambda: self.center)
        un.UNMutableNotificationContent = types.SimpleNamespace(  # type: ignore[attr-defined]
            alloc=lambda: types.SimpleNamespace(init=lambda: types.SimpleNamespace(setTitle_=lambda _t: None,
                                                                                   setBody_=lambda _b: None)))
        un.UNNotificationRequest = types.SimpleNamespace(  # type: ignore[attr-defined]
            requestWithIdentifier_content_trigger_=lambda ident, _c, _t: ident)
        for name, mod in (("Foundation", found), ("AppKit", appkit), ("UserNotifications", un)):
            monkeypatch.setitem(sys.modules, name, mod)


@pytest.fixture
def stubs(monkeypatch: pytest.MonkeyPatch) -> _Stubs:
    from agentprov_gui.platform import macos

    monkeypatch.setattr(macos, "_auth", {})
    return _Stubs(monkeypatch)


def test_interpreter_bundles_are_not_the_signed_app(stubs: _Stubs) -> None:
    from agentprov_gui.platform import macos

    for bundle in (("org.python." + "python", PY_APP), ("com.apple." + "python3", CLT_APP), ("", "/x/.venv/bin")):
        stubs.bundle = bundle
        assert not macos.signed_bundle(), bundle
        macos._notify("Job finished", "import corpus-a: ok")
    assert len(stubs.bounces) == 3
    assert not stubs.center.auth and not stubs.center.added
    stubs.bundle = ("org.example." + "agentprov", OWN_APP)
    assert macos.signed_bundle()


def test_authorisation_is_requested_once_and_bounces_until_granted(stubs: _Stubs) -> None:
    from agentprov_gui.platform import macos

    stubs.bundle = ("org.example." + "agentprov", OWN_APP)
    macos._notify("Job finished", "import corpus-a: ok")
    macos._notify("Job finished", "derive corpus-b: failed")
    assert len(stubs.center.auth) == 1  # asked once, the answer still pending
    assert not stubs.center.added and len(stubs.bounces) == 2
    options, handler = stubs.center.auth[0]
    assert options & 4 and options & 2  # UNAuthorizationOptionAlert | UNAuthorizationOptionSound
    handler(False, None)  # denied
    macos._notify("Job finished", "x")
    assert len(stubs.center.auth) == 1 and not stubs.center.added and len(stubs.bounces) == 3


def test_granted_requests_have_unique_ids_and_a_completion_handler(stubs: _Stubs) -> None:
    from agentprov_gui.platform import macos

    stubs.bundle = ("org.example." + "agentprov", OWN_APP)
    macos._notify("Job finished", "first")
    stubs.center.auth[0][1](True, None)
    bounced = len(stubs.bounces)
    macos._notify("Job finished", "import corpus-a: ok")
    macos._notify("Job finished", "derive corpus-b: failed")
    ids = [ident for ident, _h in stubs.center.added]
    assert len(ids) == 2 and len(set(ids)) == 2, ids
    handlers = [h for _i, h in stubs.center.added]
    assert all(callable(h) for h in handlers)
    assert len(stubs.bounces) == bounced
    handlers[0](types.SimpleNamespace(code=lambda: 1))  # the system refused the request: bounce instead
    assert len(stubs.bounces) == bounced + 1
    handlers[1](None)
    assert len(stubs.bounces) == bounced + 1


def _status(value: int) -> Any:
    return types.SimpleNamespace(authorizationStatus=lambda: value)


def test_authorisation_requested_at_install_delivers_the_first_notification(stubs: _Stubs) -> None:
    """GR-67: asked when the native chrome is installed, the answer is known before the first long job ends."""
    from agentprov_gui.platform import macos

    stubs.bundle = ("org.example." + "agentprov", OWN_APP)
    macos._request_authorisation()
    macos._request_authorisation()
    assert len(stubs.center.auth) == 1
    stubs.center.auth[0][1](True, None)  # the system answers before any job ends
    macos._notify("Job finished", "import corpus-a: ok")
    assert len(stubs.center.added) == 1 and not stubs.bounces
    stubs.bundle = ("org.python." + "python", PY_APP)
    macos._auth.clear()
    macos._request_authorisation()  # a dev run never asks
    assert len(stubs.center.auth) == 1


def test_a_refusal_is_rechecked_so_a_later_grant_takes_effect(stubs: _Stubs) -> None:
    """GR-67: notifications enabled later in System Settings are used without a restart."""
    from agentprov_gui.platform import macos

    stubs.bundle = ("org.example." + "agentprov", OWN_APP)
    macos._request_authorisation()
    stubs.center.auth[0][1](False, None)  # denied
    macos._notify("Job finished", "x")
    assert len(stubs.bounces) == 1 and not stubs.center.added
    assert len(stubs.center.settings) == 1  # the current status is read again (never prompts)
    stubs.center.settings[0](_status(1))  # still denied
    macos._notify("Job finished", "y")
    assert len(stubs.bounces) == 2 and not stubs.center.added
    stubs.center.settings[-1](_status(2))  # the user allowed them in System Settings
    macos._notify("Job finished", "z")
    assert len(stubs.center.added) == 1 and len(stubs.bounces) == 2
    assert len(stubs.center.auth) == 1
