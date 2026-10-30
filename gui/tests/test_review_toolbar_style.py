"""GR-37 (D-440, macos-design §2.6): the native toolbar uses the unified style, so the title and the toolbar share one
row. The constants are checked against AppKit's own enum values; importing AppKit creates no window, so this runs
headless on macOS and is skipped elsewhere."""

from __future__ import annotations

import sys

import pytest

from agentprov_gui.platform import macos

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="AppKit is macOS-only")


def test_toolbar_constants_match_appkit() -> None:
    appkit = pytest.importorskip("AppKit")
    assert appkit.NSWindowToolbarStyleUnified == macos._UNIFIED  # 1 would be Expanded: a separate title row
    assert appkit.NSToolbarDisplayModeIconOnly == macos._ICON_ONLY
