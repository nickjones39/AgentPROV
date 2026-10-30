"""GUI preferences in ``QSettings`` (design §6.6; D-445 state restoration). Never a key, never corpus text.

The "Show content" switches are deliberately **not** stored (S2): they reset whenever a corpus is opened.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Final

from PySide6.QtCore import QSettings

from agentprov_gui import text as T
from agentprov_gui.about import default_checkout
from agentprov_gui.paths import default_corpus_roots

__all__ = ["Settings"]

ORG: Final = "AgentPROV"
APP: Final = "AgentPROV GUI"

_log = logging.getLogger("agentprov_gui.settings")


def _path_ok(value: str) -> bool:
    """False for a path string with a control character (GR-66): a NUL makes ``os.stat`` raise ``ValueError``."""
    return not any(ord(c) < 0x20 or ord(c) == 0x7F for c in value)


class Settings:
    def __init__(self, store: QSettings | None = None) -> None:
        self.store = store or QSettings(ORG, APP)

    def _get(self, key: str, default: str) -> str:
        value = self.store.value(key, default)
        return value if isinstance(value, str) else default

    @property
    def theme(self) -> str:
        v = self._get("appearance/theme", "system")
        return v if v in ("system", "light", "dark") else "system"

    @theme.setter
    def theme(self, value: str) -> None:
        self.store.setValue("appearance/theme", value)

    @property
    def graph_palette(self) -> str:
        v = self._get("appearance/graph_palette", "accessible")
        return v if v in ("accessible", "exact") else "accessible"

    @graph_palette.setter
    def graph_palette(self, value: str) -> None:
        self.store.setValue("appearance/graph_palette", value)

    @property
    def content_limit(self) -> int:
        try:
            v = int(self._get("viewer/content_limit", str(T.CONTENT_CHARS_DEFAULT)))
        except ValueError:
            v = T.CONTENT_CHARS_DEFAULT
        return max(1, min(v, T.CONTENT_CHARS_MAX))

    @content_limit.setter
    def content_limit(self, value: int) -> None:
        self.store.setValue("viewer/content_limit", str(max(1, min(value, T.CONTENT_CHARS_MAX))))

    @property
    def corpus_roots(self) -> list[Path]:
        """The stored roots; a value with a control character is dropped and the default used (GR-66)."""
        raw = self.store.value("paths/corpus_roots")
        if isinstance(raw, str):
            raw = [raw] if raw else []
        if isinstance(raw, list) and all(isinstance(x, str) for x in raw) and raw:
            if all(_path_ok(x) for x in raw):
                return [Path(x) for x in raw]
            _log.warning("stored corpus roots hold a control character; using the default")
        return default_corpus_roots()

    @corpus_roots.setter
    def corpus_roots(self, roots: list[Path]) -> None:
        """Roots with a control character are refused (GR-66); nothing is stored when none is left."""
        kept = [str(p) for p in roots if _path_ok(str(p))]
        if kept:
            self.store.setValue("paths/corpus_roots", kept)

    @property
    def native_chrome(self) -> bool:
        """Settings › Experimental › "Native macOS toolbar" (D-440; on by default)."""
        return self._get("experimental/native_chrome", "true") != "false"

    @native_chrome.setter
    def native_chrome(self, value: bool) -> None:
        self.store.setValue("experimental/native_chrome", "true" if value else "false")

    @property
    def checkout(self) -> Path | None:
        """The checkout, absolute: a value typed or stored as ``ck`` or ``~/ck`` is expanded and made absolute (GR-51).

        A stored value with a control character is dropped and the default used (GR-66)."""
        v = self._get("paths/checkout", "")
        if not _path_ok(v):
            _log.warning("stored checkout holds a control character; using the default")
            v = ""
        return Path(os.path.abspath(Path(v).expanduser())) if v else default_checkout()

    @checkout.setter
    def checkout(self, value: Path | None) -> None:
        """A path with a control character is refused (GR-66): the stored value is left unchanged."""
        if value is not None and not _path_ok(str(value)):
            return
        self.store.setValue("paths/checkout", os.path.abspath(value.expanduser()) if value else "")
